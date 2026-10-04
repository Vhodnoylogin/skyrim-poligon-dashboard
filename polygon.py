"""Skyrim-Polygon: durable chat orders, game execution and raw evidence return.

Tags: testing, tools, devbench
Runtime data is local-only. No mod diagnosis, code changes or implicit retries.
"""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
from urllib.request import Request, urlopen
import uuid

HERE = Path(__file__).resolve().parent
SAFE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,79}")
SHA = re.compile(r"[0-9a-f]{64}")
READ_KINDS = {"state", "player", "refs", "scene", "vm", "world_observer"}


def session_root(explicit=None):
    """Resolve host data independently of the source checkout's location."""
    if explicit is not None:
        return Path(explicit).resolve()
    configured = os.environ.get("SKYRIM_POLYGON_ROOT")
    if configured:
        return Path(configured).resolve()
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "local/skyrim-polygon/config.json").is_file():
            return candidate
    raise ValueError("Set --root or SKYRIM_POLYGON_ROOT to the host session directory (outside Git)")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def required_string(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Required nonempty string: " + key)
    return value


def owner_evidence(approval, path, require_deadline=True):
    evidence = approval.get("ownerAuthorization")
    if not isinstance(evidence, dict):
        raise ValueError("Separate ownerAuthorization evidence required")
    for key in ("threadId", "messageId", "quote", "verifiedBy"):
        required_string(evidence, key)
    evidence["path"] = str((path.parent / required_string(evidence, "path")).resolve())
    if not SHA.fullmatch(evidence.get("sha256", "")) or digest(evidence["path"]) != evidence["sha256"]:
        raise ValueError("Owner evidence hash mismatch")
    if evidence["quote"] not in Path(evidence["path"]).read_text(encoding="utf-8-sig"):
        raise ValueError("Owner quote absent from evidence")
    deadline = approval.get("deadlineUtc")
    if (require_deadline or deadline is not None) and (type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline <= time.time()):
        raise ValueError("Future finite UTC Unix deadline required")
    return evidence


class Polygon:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.local = self.root / "local/skyrim-polygon"
        self.local.mkdir(parents=True, exist_ok=True)
        if any((p / ".git").exists() for p in [self.local, *self.local.parents]):
            raise ValueError("Polygon runtime must be outside Git")
        self.db = self.local / "queue.sqlite3"
        with self.connect() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, mode TEXT NOT NULL, subject TEXT NOT NULL,
              origin TEXT NOT NULL, status TEXT NOT NULL, submitted REAL NOT NULL,
              request TEXT NOT NULL, packet TEXT, note TEXT NOT NULL DEFAULT '',
              delivery TEXT, mailbox_id TEXT);
            CREATE TABLE IF NOT EXISTS events (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT, at REAL, status TEXT, note TEXT);
            CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, started REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS cycles (
              id TEXT PRIMARY KEY, authorization TEXT NOT NULL,
              status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS releases (id TEXT PRIMARY KEY, authorization TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS released_orders (id TEXT PRIMARY KEY, release_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cycle_slots (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
              cycle_id TEXT NOT NULL, iteration INTEGER NOT NULL, order_id TEXT UNIQUE NOT NULL,
              request TEXT NOT NULL, status TEXT NOT NULL, receipt TEXT, note TEXT NOT NULL DEFAULT '',
              UNIQUE(cycle_id,iteration));
            CREATE UNIQUE INDEX IF NOT EXISTS one_install_run_slot ON cycle_slots((1))
              WHERE status IN ('reserved','blocked');
            CREATE TABLE IF NOT EXISTS pipeline_holds (id TEXT PRIMARY KEY, note TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_game ON jobs((1))
              WHERE status='running';
            """)

    @contextlib.contextmanager
    def connect(self):
        con = sqlite3.connect(self.db, timeout=15)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def host(self):
        return read(self.local / "config.json")

    def register_cycle(self, path):
        """Register separately verified human approval, never from submit()."""
        path = Path(path).resolve()
        approval = read(path)
        if approval.get("schemaVersion") != 1 or not SAFE_ID.fullmatch(approval.get("id", "")):
            raise ValueError("Cycle needs schemaVersion1 and safe id")
        for key in ("sourceChat", "sourceThreadId", "subject", "profile", "scopeId", "task", "stopCriteria"):
            required_string(approval, key)
        if not isinstance(approval.get("allowedChanges"), list) or not approval["allowedChanges"]:
            raise ValueError("Define allowedChanges")
        if type(approval.get("maxIterations")) is not int or approval["maxIterations"] < 1:
            raise ValueError("Positive finite maxIterations required")
        owner_evidence(approval, path)
        canonical = json.dumps(approval, sort_keys=True, ensure_ascii=False)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT authorization FROM cycles WHERE id=?", (approval["id"],)).fetchone()
            if row:
                if row["authorization"] != canonical:
                    raise ValueError("Cycle id already registered with different approval")
                return {"id": approval["id"], "duplicate": True}
            con.execute("INSERT INTO cycles(id,authorization,status) VALUES(?,?,'active')", (approval["id"], canonical))
        return {"id": approval["id"], "status": "active"}

    def release_batch(self, path):
        """Snapshot a ready batch only after the owner's manual start command."""
        path = Path(path).resolve()
        approval = read(path)
        if approval.get("schemaVersion") != 1 or not SAFE_ID.fullmatch(approval.get("id", "")):
            raise ValueError("Batch needs schemaVersion1 and safe id")
        owner_evidence(approval, path, require_deadline=False)
        ids = approval.get("orderIds")
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("List exact unique ready orderIds")
        canonical = json.dumps(approval, sort_keys=True, ensure_ascii=False)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute("SELECT authorization FROM releases WHERE id=?", (approval["id"],)).fetchone()
            if existing:
                if existing["authorization"] != canonical:
                    raise ValueError("Batch id already used with different approval")
                return {"id": approval["id"], "duplicate": True}
            for job in ids:
                row = con.execute("SELECT * FROM jobs WHERE id=?", (job,)).fetchone()
                if not row or row["status"] != "queued" or json.loads(row["request"]).get("cycle") is not None:
                    raise ValueError("Batch accepts ready standard automatic orders only")
                if con.execute("SELECT id FROM released_orders WHERE id=?", (job,)).fetchone():
                    raise ValueError("Order already belongs to a released batch")
            con.execute("INSERT INTO releases VALUES(?,?)", (approval["id"], canonical))
            for job in ids:
                con.execute("INSERT INTO released_orders VALUES(?,?)", (job, approval["id"]))
                self.event(con, job, "released", approval["id"])
        return {"id": approval["id"], "releasedOrders": ids}

    def cycle_state(self, cycle):
        with self.connect() as con:
            row = con.execute("SELECT * FROM cycles WHERE id=?", (cycle,)).fetchone()
        if not row:
            raise ValueError("Unknown cycle")
        return dict(row)

    def request_slot(self, path):
        """Queue preparation intent without touching installed files or starting a game."""
        path = Path(path).resolve()
        request = read(path)
        if request.get("schemaVersion") != 1:
            raise ValueError("Slot needs schemaVersion1")
        for key in ("id", "cycleId", "orderId"):
            if not SAFE_ID.fullmatch(required_string(request, key)):
                raise ValueError("Safe slot/cycle/order id required")
        required_string(request, "sourceChat")
        required_string(request, "sourceThreadId")
        writes = request.get("writePaths")
        if not isinstance(writes, list) or not writes or any(not isinstance(p, str) or not p.strip() for p in writes):
            raise ValueError("Declare every planned install/profile writePath")
        request["writePaths"] = [str((path.parent / p).resolve()) for p in writes]
        canonical = json.dumps(request, sort_keys=True, ensure_ascii=False)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            duplicate = con.execute("SELECT request FROM cycle_slots WHERE id=?", (request["id"],)).fetchone()
            if duplicate:
                if duplicate["request"] != canonical:
                    raise ValueError("Slot id reused with different content")
                return {"id": request["id"], "duplicate": True}
            row = con.execute("SELECT * FROM cycles WHERE id=? AND status='active'", (request["cycleId"],)).fetchone()
            if not row:
                raise ValueError("Slot needs independently authorized active cycle")
            approval = json.loads(row["authorization"])
            if time.time() >= approval["deadlineUtc"] or digest(approval["ownerAuthorization"]["path"]) != approval["ownerAuthorization"]["sha256"]:
                raise ValueError("Slot approval expired or provenance changed")
            for key in ("sourceChat", "sourceThreadId"):
                if request[key] != approval[key]:
                    raise ValueError("Slot origin mismatch")
            iteration = request.get("iteration")
            if type(iteration) is not int or not 1 <= iteration <= approval["maxIterations"]:
                raise ValueError("Slot iteration limit")
            previous = [j for j in con.execute("SELECT request,status FROM jobs")
                        if (json.loads(j["request"]).get("cycle") or {}).get("id") == request["cycleId"]]
            if len(previous) != iteration - 1 or any(j["status"] != "delivered" for j in previous):
                raise ValueError("Slot needs delivered previous iterations without branches")
            con.execute("INSERT INTO cycle_slots(id,cycle_id,iteration,order_id,request,status) VALUES(?,?,?,?,?,'waiting')",
                        (request["id"], request["cycleId"], iteration, request["orderId"], canonical))
        return {"id": request["id"], "status": "waiting"}

    def slots(self):
        with self.connect() as con:
            return [dict(row) for row in con.execute("SELECT * FROM cycle_slots ORDER BY seq")]

    def environment_idle(self):
        self.executor()
        from skyrim_autotest import native
        names = {"skyrimvr.exe", "sksevr_loader.exe", "vrserver.exe", "vrmonitor.exe", "vrcompositor.exe",
                 "vrstartup.exe", "vrdashboard.exe", "vrwebhelper.exe", "vrprismhost.exe"}
        return not any(p["name"].lower() in names for p in native.processes())

    def grant_slot(self):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT id FROM pipeline_holds").fetchone():
                return {"status": "pipeline_held"}
            existing = con.execute("SELECT * FROM cycle_slots WHERE status IN ('reserved','blocked')").fetchone()
            if existing:
                cycle = con.execute("SELECT * FROM cycles WHERE id=?", (existing["cycle_id"],)).fetchone()
                approval = json.loads(cycle["authorization"])
                if existing["status"] == "reserved" and (cycle["status"] != "active" or time.time() >= approval["deadlineUtc"]):
                    # Never release a possibly half-installed environment on a timeout.
                    con.execute("UPDATE cycle_slots SET status='blocked',note='Stopped/expired owner; installation review required' WHERE id=?", (existing["id"],))
                    result = dict(existing)
                    result["status"] = "blocked"
                    return result
                return dict(existing)
            if con.execute("SELECT id FROM jobs WHERE status='running'").fetchone():
                return {"status": "game_busy"}
            # A manually released finite batch finishes before changing its installation.
            if con.execute("SELECT jobs.id FROM jobs JOIN released_orders ON jobs.id=released_orders.id WHERE jobs.status='queued'").fetchone():
                return {"status": "manual_batch_pending"}
            if not con.execute("SELECT id FROM cycle_slots WHERE status='waiting'").fetchone():
                return {"status": "idle"}
            if not self.environment_idle():
                return {"status": "external_game_or_vr_busy"}
            for row in con.execute("SELECT * FROM cycle_slots WHERE status='waiting' ORDER BY seq").fetchall():
                cycle = con.execute("SELECT * FROM cycles WHERE id=?", (row["cycle_id"],)).fetchone()
                approval = json.loads(cycle["authorization"])
                if cycle["status"] != "active" or time.time() >= approval["deadlineUtc"] or digest(approval["ownerAuthorization"]["path"]) != approval["ownerAuthorization"]["sha256"]:
                    con.execute("UPDATE cycle_slots SET status='cancelled',note='Approval stopped/expired/changed' WHERE id=?", (row["id"],))
                    continue
                con.execute("UPDATE cycle_slots SET status='reserved' WHERE id=?", (row["id"],))
                result = dict(row)
                result["status"] = "reserved"
                return result
        return {"status": "idle"}

    def pipeline_status(self):
        with self.connect() as con:
            return {"holds": [dict(r) for r in con.execute("SELECT * FROM pipeline_holds")],
                    "slots": [dict(r) for r in con.execute("SELECT * FROM cycle_slots ORDER BY seq")],
                    "activeOrders": [r["id"] for r in con.execute("SELECT id FROM jobs WHERE status='running'")]}

    def hold_pipeline(self, issue, note):
        if not isinstance(note, str) or not note.strip():
            raise ValueError("Pipeline hold needs evidence/reason")
        with self.connect() as con:
            con.execute("INSERT OR IGNORE INTO pipeline_holds VALUES(?,?)", (issue, note))
        return {"id": issue, "status": "held"}

    def clear_pipeline(self, issue, path):
        path = Path(path).resolve()
        evidence = read(path)
        owner_evidence(evidence, path, require_deadline=False)
        if evidence.get("holdId") != issue or evidence.get("installationSettled") is not True:
            raise ValueError("Exact hold and reviewed shared environment required")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT id FROM jobs WHERE status='running'").fetchone():
                raise ValueError("Recover active session before pipeline clearance")
            con.execute("DELETE FROM pipeline_holds WHERE id=?", (issue,))
            self.event(con, issue, "pipeline_cleared", json.dumps(evidence, sort_keys=True))
        return {"id": issue, "status": "cleared"}

    def slot_notified(self, slot, receipt):
        if not isinstance(receipt, str) or not receipt.strip():
            raise ValueError("Successful exact-origin app grant receipt required")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM cycle_slots WHERE id=?", (slot,)).fetchone()
            if not row or row["status"] != "reserved":
                raise ValueError("No reserved slot")
            cycle = con.execute("SELECT * FROM cycles WHERE id=?", (row["cycle_id"],)).fetchone()
            approval = json.loads(cycle["authorization"])
            if cycle["status"] != "active" or time.time() >= approval["deadlineUtc"]:
                raise ValueError("Preparation grant expired or cycle stopped")
            if row["receipt"]:
                return {"id": slot, "duplicate": True}
            con.execute("UPDATE cycle_slots SET receipt=? WHERE id=?", (receipt, slot))
        return {"id": slot, "status": "notified"}

    def clear_slot(self, slot, path):
        """Owner-reviewed installation/recovery clearance, never timeout expiry."""
        path = Path(path).resolve()
        clearance = read(path)
        owner_evidence(clearance, path, require_deadline=False)
        if clearance.get("slotId") != slot or clearance.get("installationSettled") is not True:
            raise ValueError("Exact slot and settled installation evidence required")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM cycle_slots WHERE id=?", (slot,)).fetchone()
            if not row:
                raise ValueError("Unknown slot")
            if con.execute("SELECT id FROM jobs WHERE status='running'").fetchone():
                raise ValueError("Recover active game before clearing installation slot")
            order = con.execute("SELECT status FROM jobs WHERE id=?", (row["order_id"],)).fetchone()
            if order and order["status"] == "queued":
                raise ValueError("Withdraw/reconcile submitted order before clearance")
            con.execute("UPDATE cycle_slots SET status='released',note=? WHERE id=?",
                        (json.dumps(clearance, sort_keys=True), slot))
        return {"id": slot, "status": "released"}

    def stop_cycle(self, cycle, status, note):
        if status not in ("cancelled", "complete", "blocked") or not isinstance(note, str) or not note.strip():
            raise ValueError("Terminal cycle status and reason required")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT status FROM cycles WHERE id=?", (cycle,)).fetchone()
            if not row:
                raise ValueError("Unknown cycle")
            if row["status"] != "active":
                if row["status"] != status:
                    raise ValueError("Stopped cycles cannot be reopened or relabelled")
                return {"id": cycle, "duplicate": True}
            con.execute("UPDATE cycles SET status=?,note=? WHERE id=?", (status, note, cycle))
        return {"id": cycle, "status": status, "notice": "No new launches; active session still requires native recovery/restoration"}

    def validate_cycle(self, con, order):
        cycle = order.get("cycle")
        if cycle is None:
            return
        if not isinstance(cycle, dict):
            raise ValueError("cycle must reference a separately registered approval")
        if con.execute("SELECT id FROM jobs WHERE status='running' AND id != ?", (order["id"],)).fetchone():
            raise ValueError("Active session/recovery stops cycle admission")
        row = con.execute("SELECT * FROM cycles WHERE id=?", (required_string(cycle, "id"),)).fetchone()
        if not row or row["status"] != "active":
            raise ValueError("Cycle is not separately authorized and active")
        approval = json.loads(row["authorization"])
        if time.time() >= approval["deadlineUtc"]:
            raise ValueError("Cycle deadline reached")
        evidence = approval["ownerAuthorization"]
        if digest(evidence["path"]) != evidence["sha256"]:
            raise ValueError("Owner authorization provenance changed")
        for key in ("sourceChat", "sourceThreadId", "subject"):
            if order[key] != approval[key]:
                raise ValueError("Cycle scope/origin mismatch: " + key)
        if order["profile"] != approval["profile"] and order.get("profileSelection", {}).get("mode") != "exclusive":
            raise ValueError("Cycle baseline profile mismatch")
        if order["mode"] != "automatic" or cycle.get("scopeId") != approval["scopeId"]:
            raise ValueError("Cycle requires authorized automatic scope")
        iteration = cycle.get("iteration")
        if type(iteration) is not int or not 1 <= iteration <= approval["maxIterations"]:
            raise ValueError("Cycle iteration limit reached or invalid")
        required_string(cycle, "buildId")
        slot = con.execute("SELECT * FROM cycle_slots WHERE id=? AND status='reserved'", (required_string(cycle, "slotId"),)).fetchone()
        if not slot or (slot["cycle_id"], slot["iteration"], slot["order_id"]) != (cycle["id"], iteration, order["id"]):
            raise ValueError("Cycle order requires its exclusive install/run slot")
        if not slot["receipt"]:
            raise ValueError("Slot grant must have an exact-origin delivery receipt")
        previous_rows = []
        for job in con.execute("SELECT * FROM jobs WHERE id != ?", (order["id"],)):
            request = json.loads(job["request"])
            if isinstance(request.get("cycle"), dict) and request["cycle"].get("id") == cycle["id"]:
                previous_rows.append((job, request))
        if len(previous_rows) != iteration - 1:
            raise ValueError("Cycle iterations must form one nonbranching chain")
        if iteration == 1:
            if any(cycle.get(k) is not None for k in ("previousOrderId", "previousPacketSha256", "decision")):
                raise ValueError("First iteration cannot claim a predecessor")
            return
        previous, request = max(previous_rows, key=lambda pair: pair[1]["cycle"]["iteration"])
        if cycle.get("previousOrderId") != previous["id"] or previous["status"] != "delivered":
            raise ValueError("Previous iteration must be delivered to its exact origin")
        if digest(previous["packet"]) != cycle.get("previousPacketSha256"):
            raise ValueError("Previous packet provenance mismatch")
        packet = read(previous["packet"])
        if packet.get("restored") is not True or packet["executionOutcome"] not in ("passed", "failed"):
            raise ValueError("Blocked/interrupted/unrestored result stops the cycle")
        names = {Path(entry["path"]).name for entry in packet["files"]}
        if not {"self-checks.json", "profile-archive.json"} <= names:
            raise ValueError("Required tooling/profile lifecycle evidence missing")
        for entry in packet["files"]:
            if digest(entry["path"]) != entry["sha256"] or Path(entry["path"]).stat().st_size != entry["bytes"]:
                raise ValueError("Evidence manifest mismatch")
            if Path(entry["path"]).name == "self-checks.json" and read(entry["path"]).get("findings"):
                raise ValueError("Tooling/recovery findings stop the cycle")
            if Path(entry["path"]).name == "profile-archive.json":
                archive = read(entry["path"])
                if Path(archive["originalProfile"]).exists():
                    raise ValueError("Temporary profile remains in MO2")
                for pin in archive["files"]:
                    if digest(pin["path"]) != pin["sha256"]:
                        raise ValueError("Archived profile/save evidence changed")
            if Path(entry["path"]).name == "service-findings.jsonl":
                notes = [json.loads(line) for line in Path(entry["path"]).read_text(encoding="utf-8").splitlines() if line.strip()]
                if any(n.get("category") in ("tool_bug", "tool_suspected_bug") for n in notes):
                    raise ValueError("Tooling problems stop the cycle")
        decision = cycle.get("decision")
        if not isinstance(decision, dict) or not SHA.fullmatch(decision.get("sha256", "")) or digest(required_string(decision, "path")) != decision["sha256"]:
            raise ValueError("Pinned origin analysis decision required")
        analysis = read(decision["path"])
        if (analysis.get("cycleId"), analysis.get("previousOrderId"), analysis.get("previousPacketSha256"), analysis.get("sourceThreadId"), analysis.get("action")) != (cycle["id"], previous["id"], cycle["previousPacketSha256"], order["sourceThreadId"], "fix-and-retest"):
            raise ValueError("Decision must analyze this exact predecessor for fix-and-retest")
        required_string(analysis, "reason")
        if any(analysis.get(key) is not True for key in ("withinScope", "evidenceComplete", "toolingHealthy", "criteriaUnmet")):
            raise ValueError("Uncertain evidence/tooling/scope or fulfilled criteria stops the cycle")
        if cycle["buildId"] == request["cycle"]["buildId"] or sorted(p["sha256"] for p in order["inputs"]) == sorted(p["sha256"] for p in request["inputs"]):
            raise ValueError("Fix iteration requires a new build id and installed input hashes")

    def check_launch_authorization(self, order):
        with self.connect() as con:
            if con.execute("SELECT id FROM pipeline_holds").fetchone():
                raise ValueError("Shared tooling/recovery pipeline is held for owner review")
            slot = con.execute("SELECT * FROM cycle_slots WHERE status IN ('reserved','blocked')").fetchone()
            if slot and (slot["status"] == "blocked" or slot["order_id"] != order["id"]):
                raise ValueError("Another installation/run slot owns the shared environment")
            if order.get("cycle") is not None:
                self.validate_cycle(con, order)
            else:
                row = con.execute("SELECT authorization FROM releases JOIN released_orders ON releases.id=release_id WHERE released_orders.id=?", (order["id"],)).fetchone()
                if not row:
                    raise ValueError("Standard order awaits the owner's manual batch start")
                approval = json.loads(row["authorization"])
                evidence = approval["ownerAuthorization"]
                deadline = approval.get("deadlineUtc")
                if (deadline is not None and time.time() >= deadline) or digest(evidence["path"]) != evidence["sha256"]:
                    raise ValueError("Manual batch start expired or provenance changed")
            self.validate_profile_selection(order)

    @staticmethod
    def validate_profile_selection(order):
        selection = order.get("profileSelection", {"mode": "active"})
        if not isinstance(selection, dict) or selection.get("mode") not in ("active", "exclusive"):
            raise ValueError("Profile selection must be active or exclusive")
        if selection["mode"] == "active":
            return
        required_string(selection, "reason")
        if selection.get("authority") == "cycle-origin":
            if not isinstance(order.get("cycle"), dict):
                raise ValueError("Origin-selected exclusive profile requires an authorized full cycle")
        elif selection.get("authority") == "owner":
            evidence = selection.get("ownerAuthorization")
            if not isinstance(evidence, dict):
                raise ValueError("Exclusive standard profile requires direct owner evidence")
            for key in ("threadId", "messageId", "quote", "path", "verifiedBy"):
                required_string(evidence, key)
            if not SHA.fullmatch(evidence.get("sha256", "")) or digest(evidence["path"]) != evidence["sha256"]:
                raise ValueError("Exclusive profile owner provenance mismatch")
            if evidence["quote"] not in Path(evidence["path"]).read_text(encoding="utf-8-sig"):
                raise ValueError("Exclusive profile owner quote absent")
        else:
            raise ValueError("Exclusive profile needs owner or cycle-origin authority")

    def source_profile(self, order, runner):
        """Read actual MO2 selection; the runner creates/activates its own copy."""
        self.validate_profile_selection(order)
        if order.get("profileSelection", {}).get("mode") == "exclusive":
            selected = order["profile"]
        elif any(p["name"].lower() == "modorganizer.exe" for p in runner.native.processes()):
            selected = runner.request(runner.P.bridge_port, "ping", token=runner.P.bridge_token.read_text().strip())["profile"]
        else:
            text = runner.P.mo2_ini.read_text(encoding="utf-8-sig")
            values = re.findall(r"(?m)^selected_profile=(.*?)\r?$", text)
            if len(values) != 1:
                raise ValueError("Actual active MO2 profile is unavailable/ambiguous")
            selected = values[0]
            if selected.startswith("@ByteArray(") and selected.endswith(")"):
                selected = selected[len("@ByteArray("):-1]
            # QSettings escaped strings need a real bridge read, not a guessed decode.
            if "\\" in selected or selected.startswith("@"):
                raise ValueError("Read the active MO2 profile through its bridge; unsupported INI encoding")
        if selected != order["profile"] or Path(selected).name != selected or selected in (".", ".."):
            raise ValueError("Active profile differs from order provenance; prepare a new order")
        write(self.evidence_dir(order["id"]) / "profile-selection.json",
              {"sourceProfile": selected, "selection": order.get("profileSelection", {"mode": "active"}),
               "copyOwner": "skyrim-autotest", "originalProfilePreserved": True})
        return selected

    def executor(self):
        location = Path(self.host()["executor"]).resolve()
        if not (location / "skyrim_autotest/scenarios.py").is_file():
            raise ValueError("Configured executor is unavailable")
        sys.path.insert(0, str(location))
        from skyrim_autotest.scenarios import validate
        return location, validate

    @staticmethod
    def event(con, job, status, note=""):
        con.execute("INSERT INTO events(id,at,status,note) VALUES(?,?,?,?)",
                    (job, time.time(), status, note))

    def submit(self, path):
        path = Path(path).resolve()
        order = read(path)
        if order.get("schemaVersion") != 1 or not SAFE_ID.fullmatch(order.get("id", "")):
            raise ValueError("schemaVersion1 and safe id required")
        for key in ("subject", "sourceChat", "sourceThreadId", "profile", "purpose"):
            required_string(order, key)
        if order.get("mode") not in ("automatic", "assisted"):
            raise ValueError("mode must be automatic or assisted")
        if not isinstance(order.get("collect"), list) or not order["collect"]:
            raise ValueError("List the requested data in collect")
        # Pins apply to installed subject files/dependencies, not merely a Git commit.
        pins = order.get("inputs")
        if not isinstance(pins, list) or not pins:
            raise ValueError("Pin at least one installed subject input")
        for pin in pins:
            if not isinstance(pin, dict) or not SHA.fullmatch(pin.get("sha256", "")):
                raise ValueError("Every input needs path and lowercase sha256")
            pin["path"] = str((path.parent / required_string(pin, "path")).resolve())
            if not Path(pin["path"]).is_file() or digest(pin["path"]) != pin["sha256"]:
                raise ValueError("Missing/changed pinned input: " + pin["path"])
        if order["mode"] == "automatic":
            config = (path.parent / required_string(order, "config")).resolve()
            from_location, validate = self.executor()
            from skyrim_autotest.config import load
            resolved = load(config)
            scenario_path = (path.parent / required_string(order, "scenario")).resolve()
            scenario = read(scenario_path)
            validate(scenario)
            order["scenarioData"] = scenario
            order["resolvedConfig"] = resolved
            order["originalScenarioHash"] = digest(scenario_path)
        else:
            queries = order.get("observations")
            if not isinstance(queries, list) or not 1 <= len(queries) <= 8:
                raise ValueError("Assisted mode needs 1..8 read-only observations")
            for query in queries:
                if query.get("tool") != "inspect" or query.get("args", {}).get("kind") not in READ_KINDS:
                    raise ValueError("Assisted collector accepts supported inspect kinds only")
                if query["args"].get("action", "snapshot") not in ("snapshot", "capabilities"):
                    raise ValueError("Assisted observations cannot mutate the game")
            if not isinstance(order.get("playerSteps"), list) or not order["playerSteps"]:
                raise ValueError("Assisted mode needs playerSteps")
        if isinstance(order.get("cycle"), dict) and isinstance(order["cycle"].get("decision"), dict):
            decision = order["cycle"]["decision"]
            decision["path"] = str((path.parent / required_string(decision, "path")).resolve())
        if isinstance(order.get("profileSelection"), dict) and isinstance(order["profileSelection"].get("ownerAuthorization"), dict):
            evidence = order["profileSelection"]["ownerAuthorization"]
            evidence["path"] = str((path.parent / required_string(evidence, "path")).resolve())
        canonical = json.dumps(order, ensure_ascii=False, sort_keys=True)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            previous = con.execute("SELECT request FROM jobs WHERE id=?", (order["id"],)).fetchone()
            if previous:
                if previous["request"] != canonical:
                    raise ValueError("Order id already used for different content; create a new id")
                return {"id": order["id"], "duplicate": True}
            self.validate_cycle(con, order)
            self.validate_profile_selection(order)
            status = "queued" if order["mode"] == "automatic" else "waiting_player"
            con.execute("INSERT INTO jobs(id,mode,subject,origin,status,submitted,request) VALUES(?,?,?,?,?,?,?)",
                        (order["id"], order["mode"], order["subject"], order["sourceChat"], status, time.time(), canonical))
            self.event(con, order["id"], status)
        return {"id": order["id"], "status": status}

    def get(self, job):
        with self.connect() as con:
            row = con.execute("SELECT * FROM jobs WHERE id=?", (job,)).fetchone()
        if not row:
            raise ValueError("Unknown order: " + job)
        return dict(row)

    def claim(self, mode="automatic", job=None):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT id FROM pipeline_holds").fetchone():
                return None
            if con.execute("SELECT id FROM jobs WHERE status='running'").fetchone():
                return None
            if job:
                if con.execute("SELECT id FROM cycle_slots WHERE status IN ('reserved','blocked')").fetchone():
                    return None
                row = con.execute("SELECT * FROM jobs WHERE id=? AND mode=? AND status='waiting_player'", (job, mode)).fetchone()
            else:
                row = None
                slot = con.execute("SELECT * FROM cycle_slots WHERE status IN ('reserved','blocked')").fetchone()
                for candidate in con.execute("SELECT * FROM jobs WHERE mode=? AND status='queued' ORDER BY submitted,id", (mode,)).fetchall():
                    if slot and (slot["status"] == "blocked" or slot["order_id"] != candidate["id"]):
                        continue
                    request = json.loads(candidate["request"])
                    if request.get("cycle") is not None or con.execute("SELECT id FROM released_orders WHERE id=?", (candidate["id"],)).fetchone():
                        row = candidate
                        break
            if not row:
                return None
            con.execute("UPDATE jobs SET status='running',note='' WHERE id=?", (row["id"],))
            self.event(con, row["id"], "running")
            return dict(row)

    def evidence_dir(self, job):
        return self.local / "orders" / job

    def verify_inputs(self, order):
        for pin in order["inputs"]:
            if digest(pin["path"]) != pin["sha256"]:
                raise ValueError("Pinned input changed: " + pin["path"])

    def runtime_pins(self, order):
        pins = [{"path": str(p), "sha256": digest(p)} for p in sorted((self.executor()[0] / "skyrim_autotest").iterdir()) if p.is_file() and p.suffix in (".py", ".h", ".json")]
        return pins

    def matching_runs(self, order):
        matches = []
        runs = Path(order["resolvedConfig"]["runtime"]) / "runs"
        for path in runs.glob("*/state.json"):
            state = read(path)
            if state.get("order", {}).get("id") == order["id"]:
                matches.append((path, state))
        return matches

    def self_checks(self, job, run):
        findings = []
        folder = self.evidence_dir(job)
        pin_file = folder / "executor-pins.json"
        if pin_file.exists():
            for pin in read(pin_file):
                if not Path(pin["path"]).is_file() or digest(pin["path"]) != pin["sha256"]:
                    findings.append({"component": "skyrim-autotest", "kind": "changed_build", "path": pin["path"], "confirmed": True})
        if run:
            result = read(Path(run) / "result.json")
            if result.get("restored") is not True or result.get("restoreErrors"):
                findings.append({"component": "skyrim-autotest", "kind": "restoration_unverified", "details": result.get("restoreErrors"), "confirmed": True})
        order = json.loads(self.get(job)["request"])
        if order.get("cycle"):
            try:
                if not run:
                    raise ValueError("No run lifecycle evidence")
                state = read(Path(run) / "state.json")
                archive = Path(state["profileArchive"]).resolve()
                original = Path(state["testProfile"]).resolve()
                if (state.get("order", {}).get("id") != job or state.get("done") is not True or
                    state.get("restored") is not True or archive != (Path(run) / "test-profile").resolve() or
                    not archive.is_dir() or original.exists()):
                    raise ValueError("Run/profile archive ownership or restoration unverified")
                pins = [{"path": str(p.resolve()), "sha256": digest(p), "bytes": p.stat().st_size}
                        for p in sorted(archive.rglob("*")) if p.is_file()]
                if not pins:
                    raise ValueError("Profile archive is empty")
                write(folder / "profile-archive.json", {"originalProfile": str(original), "archive": str(archive), "files": pins})
            except (KeyError, OSError, ValueError) as error:
                findings.append({"component": "skyrim-autotest", "kind": "profile_archive_unverified", "details": str(error), "confirmed": True})
        observer_samples = []
        sources = ([Path(run) / "steps.jsonl"] if run else []) + [folder / "observations.jsonl"]
        def quality(value, path="", depth=0):
            if depth > 20:
                return []
            flags = []
            if isinstance(value, dict):
                for key, child in value.items():
                    key_path = path + "." + key
                    if key in ("callbackBusyDrops", "dropped", "ringGap", "gap", "truncated") and child:
                        flags.append({"field": key_path, "value": child})
                    if key in ("unavailable", "unsupported", "busy") and child is True:
                        flags.append({"field": key_path, "value": child})
                    flags.extend(quality(child, key_path, depth + 1))
            elif isinstance(value, list):
                for i, child in enumerate(value): flags.extend(quality(child, path + "." + str(i), depth + 1))
            return flags
        for source in sources:
            if not source.exists(): continue
            for line in source.read_text(encoding="utf-8").splitlines():
                try: event = json.loads(line)
                except ValueError: continue
                candidates = [event] + event.get("observations", [])
                for item in candidates:
                    query = item.get("query", item)
                    if query.get("args", {}).get("kind") == "world_observer":
                        response = item.get("response", item.get("result"))
                        observer_samples.append({"at": item.get("at", event.get("at")), "response": response, "qualityFlags": quality(response)})
        # This report is deliberately separate from mod acceptance or diagnosis.
        write(folder / "self-checks.json", {"checkedAt": time.time(), "findings": findings, "observerSamples": observer_samples,
              "observerReview": "Review collected responses for capability/version, identity, phase, unavailable fields, gaps and drops. Unsupported coverage is not automatically a bug.",
              "subjectAnalysis": None})
        return findings

    def note(self, job, category, text):
        row = self.get(job)
        if row["status"] == "delivered":
            raise ValueError("Already delivered: send a separately identified follow-up")
        name = "service-findings.jsonl" if category.startswith("tool_") else "player-notes.jsonl"
        folder = self.evidence_dir(job)
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / name).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"at": time.time(), "category": category, "text": text}, ensure_ascii=False) + "\n")
        if row["packet"]:
            packet = read(row["packet"])
            self.finish(job, packet["executionOutcome"], packet["reason"], packet["runDirectory"], packet["restored"])
        if category in ("tool_bug", "tool_suspected_bug"):
            self.hold_pipeline(job, "Shared tooling finding: " + text)
            cycle = json.loads(row["request"]).get("cycle")
            if cycle and self.cycle_state(cycle["id"])["status"] == "active":
                self.stop_cycle(cycle["id"], "blocked", "Tooling finding in " + job)
        return {"id": job, "recorded": str(folder / name)}

    def finish(self, job, outcome, note, run=None, restored=None):
        row = self.get(job)
        order = json.loads(row["request"])
        folder = self.evidence_dir(job)
        folder.mkdir(parents=True, exist_ok=True)
        findings = self.self_checks(job, run)
        files = []
        roots = [folder] + ([Path(run)] if run else [])
        # Do not expose snapshot backups, credentials or private save copies.
        for directory in roots:
            for p in directory.iterdir():
                if p.is_file() and p.name != "packet.json" and p.suffix in (".json", ".jsonl", ".log"):
                    files.append({"path": str(p), "sha256": digest(p), "bytes": p.stat().st_size})
        packet = {"schemaVersion": 1, "orderId": job, "mode": order["mode"],
                  "sourceChat": order["sourceChat"], "sourceThreadId": order["sourceThreadId"],
                  "subject": order["subject"], "executionOutcome": outcome,
                  "reason": note, "runDirectory": str(run) if run else None,
                  "restored": restored, "files": files, "requestedData": order["collect"],
                  "analysis": None, "finishedAt": time.time()}
        packet["sourceProfile"] = order["profile"]
        if order.get("cycle") is not None:
            packet["cycle"] = order["cycle"]
        packet_path = folder / "packet.json"
        write(packet_path, packet)
        with self.connect() as con:
            status = "blocked" if outcome == "blocked" else "recorded"
            con.execute("UPDATE jobs SET status=?,packet=?,note=? WHERE id=?", (status, str(packet_path), note, job))
            self.event(con, job, status, note)
            if order.get("cycle") and (outcome not in ("passed", "failed") or restored is not True or findings):
                con.execute("UPDATE cycles SET status='blocked',note=? WHERE id=? AND status='active'",
                            ("Execution/tooling/restoration requires owner review: " + job, order["cycle"]["id"]))
            if order.get("cycle"):
                healthy = outcome in ("passed", "failed") and restored is True and not findings
                con.execute("UPDATE cycle_slots SET status=?,note=? WHERE order_id=? AND status='reserved'",
                            ("released" if healthy else "blocked", "Restored run complete" if healthy else "Installation/recovery review required", job))
            if findings:
                con.execute("INSERT OR IGNORE INTO pipeline_holds VALUES(?,?)", (job, "Shared executor/restoration/profile evidence requires review"))
        return packet

    def reconcile(self):
        """An interrupted order is never automatically requeued or rerun."""
        with self.connect() as con:
            rows = con.execute("SELECT * FROM jobs WHERE status='running' AND mode='automatic'").fetchall()
        reconciled = []
        for row in rows:
            order = json.loads(row["request"])
            matches = self.matching_runs(order)
            if len(matches) > 1:
                raise ValueError("Multiple executions for one order; manual evidence review required")
            if matches and matches[0][1].get("done"):
                path, state = matches[0]
                self.finish(row["id"], state.get("result", "failed"), state.get("reason", ""), path.parent, state.get("restored"))
                reconciled.append(row["id"])
        return reconciled

    def execute_next(self):
        self.reconcile()
        row = self.claim()
        if not row:
            return {"status": "idle_or_busy"}
        order = json.loads(row["request"])
        folder = self.evidence_dir(row["id"])
        folder.mkdir(parents=True, exist_ok=True)
        write(folder / "request.json", order)
        try:
            self.check_launch_authorization(order)
            self.verify_inputs(order)
            write(folder / "executor-pins.json", self.runtime_pins(order))
            write(folder / "config.json", order["resolvedConfig"])
            write(folder / "scenario.json", order["scenarioData"])
            with (folder / "executor.log").open("w", encoding="utf-8") as log:
                child = subprocess.run([sys.executable, str(HERE / "polygon.py"), "--root", str(self.root), "_execute", row["id"]],
                                       stdout=log, stderr=subprocess.STDOUT, shell=False)
            self.reconcile()
            if self.get(row["id"])["status"] == "running":
                # No complete restoration evidence: leave active barrier in place.
                if child.returncode == 2 and not self.matching_runs(order):
                    return self.finish(row["id"], "blocked", "Executor refused before a game session; see executor.log")
                return {"id": row["id"], "status": "running", "reason": "Recovery/evidence reconciliation required; automatic retries prohibited"}
            return read(self.get(row["id"])["packet"])
        except (ValueError, OSError) as error:
            if self.matching_runs(order):
                return {"id": row["id"], "status": "running", "reason": "Execution may have started: recover before releasing active barrier", "error": str(error)}
            return self.finish(row["id"], "blocked", str(error))

    def child_execute(self, job):
        row = self.get(job)
        if row["status"] != "running" or row["mode"] != "automatic":
            raise ValueError("No automatic claim")
        with self.connect() as con:
            con.execute("INSERT INTO attempts(id,started) VALUES(?,?)", (job, time.time()))
        order = json.loads(row["request"])
        self.check_launch_authorization(order)
        self.verify_inputs(order)
        for pin in read(self.evidence_dir(job) / "executor-pins.json"):
            if digest(pin["path"]) != pin["sha256"]:
                raise ValueError("Executor changed after claim")
        self.executor()
        from skyrim_autotest import runner
        from skyrim_autotest.config import load
        runner.configure(load(self.evidence_dir(job) / "config.json"))
        return runner.run(self.source_profile(order, runner), self.evidence_dir(job) / "scenario.json",
                          restart_idle_mo2=True, order={"id": job, "owner": order["sourceChat"]})

    def recover_active(self):
        with self.connect() as con:
            rows = con.execute("SELECT * FROM jobs WHERE status='running' AND mode='automatic'").fetchall()
        if not rows:
            return {"status": "no_active_automatic_order"}
        row = rows[0]
        order = json.loads(row["request"])
        executor, _ = self.executor()
        # Native runner recovery verifies live process ownership; never bypass it.
        result = subprocess.run([sys.executable, str(executor / "run.py"), "--config", str(self.evidence_dir(row["id"]) / "config.json"), "recover"], capture_output=True, text=True)
        if result.returncode:
            return {"status": "recovery_refused", "output": result.stdout, "error": result.stderr}
        recovered = self.reconcile()
        if not recovered and not self.matching_runs(order):
            self.finish(row["id"], "blocked", "Interrupted before a recorded game session; no automatic retry")
        return {"reconciled": recovered, "status": self.get(row["id"])["status"]}

    def assisted_start(self, job):
        row = self.get(job)
        order = json.loads(row["request"])
        if order["mode"] != "assisted":
            raise ValueError("Not an assisted order")
        self.verify_inputs(order)
        if not self.claim("assisted", job):
            raise ValueError("Another order active, or this order already started")
        folder = self.evidence_dir(job)
        folder.mkdir(parents=True, exist_ok=True)
        write(folder / "request.json", order)
        # A private consumer cursor never advances another chat's voice cursor.
        heard = self.root / "local/voice/heard.jsonl"
        cursor = 0
        if heard.exists():
            for line in heard.read_text(encoding="utf-8").splitlines():
                try:
                    cursor = max(cursor, json.loads(line).get("seq", 0))
                except ValueError:
                    pass
        write(folder / "assisted-state.json", {"voiceCursor": cursor, "voiceSession": None, "startedAt": time.time()})
        return {"id": job, "status": "running", "playerSteps": order["playerSteps"], "notice": "Attach only. No game/SteamVR/MO2 launch, input or shutdown."}

    def assisted_poll(self, job):
        row = self.get(job)
        if row["status"] != "running" or row["mode"] != "assisted":
            raise ValueError("Assisted session is not active")
        order = json.loads(row["request"])
        folder = self.evidence_dir(job)
        state = read(folder / "assisted-state.json")
        host = self.host()
        samples, voice, errors = [], [], []
        verified_port = None
        try:
            for file in host["devbenchRuntimeFiles"]:
                if not Path(file).is_file():
                    continue
                runtime = read(file)
                port = runtime.get("port")
                if type(port) is not int or not 1 <= port <= 65535:
                    continue
                with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=3) as response:
                    health = json.load(response)
                self.executor()
                from skyrim_autotest import native
                identity = native.identity(health["pid"])
                if Path(identity["path"]).resolve() != Path(host["gameExecutable"]).resolve() or not native.alive(identity):
                    raise ValueError("DevBench does not belong to the configured live game")
                previous = state.get("gameIdentity")
                if previous and previous != identity:
                    raise ValueError("Game process changed during assisted session; finish this order")
                state["gameIdentity"] = identity
                samples.append({"at": time.time(), "health": health, "identity": identity})
                verified_port = port
                break
            if verified_port is None:
                raise ValueError("No verified live DevBench endpoint; no guessed port")
        except Exception as error:
            errors.append({"game": str(error), "unavailable": True})
        for query in order["observations"]:
            try:
                if verified_port is None:
                    raise ValueError("Game endpoint unavailable")
                req = Request(f"http://127.0.0.1:{verified_port}/api/tool/inspect", data=json.dumps(query["args"]).encode(), headers={"Content-Type": "application/json"})
                with urlopen(req, timeout=3) as response:
                    value = json.load(response)
                samples.append({"at": time.time(), "query": query, "response": value})
            except Exception as error:
                errors.append({"query": query, "error": str(error), "unavailable": True})
        # Probe listener health separately; game failure does not disable hearing.
        voice_health = None
        try:
            with urlopen("http://127.0.0.1:8931/api/health", timeout=1) as response:
                voice_health = json.load(response)
            identity = [voice_health.get("pid"), voice_health.get("since")]
            if state.get("voiceSession") is not None and state["voiceSession"] != identity:
                errors.append({"voice": "Listener restarted; cursor reset", "gap": True})
                state["voiceCursor"] = 0
                state["voiceAfterRestart"] = time.time()
            state["voiceSession"] = identity
        except Exception as error:
            errors.append({"voice": str(error), "unavailable": True})
        heard = self.root / "local/voice/heard.jsonl"
        if heard.exists():
            records = []
            for line in heard.read_text(encoding="utf-8").splitlines():
                try:
                    records.append(json.loads(line))
                except ValueError:
                    pass
            # Only consume new records when the listener is live; retain session baseline.
            def fresh(record):
                boundary = state.get("voiceAfterRestart")
                if boundary is None: return True
                try:
                    return datetime.fromisoformat(record["at"]).timestamp() >= boundary
                except (ValueError, KeyError, TypeError):
                    return False
            voice = [r for r in records if r.get("seq", 0) > state["voiceCursor"] and fresh(r)] if voice_health else []
            if voice:
                state["voiceCursor"] = max(r["seq"] for r in voice)
        result = {"at": time.time(), "observations": samples, "voice": voice, "voiceHealth": voice_health, "errors": errors}
        with (folder / "observations.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
        write(folder / "assisted-state.json", state)
        return result

    def voice_start(self, device):
        if os.name != "nt":
            raise ValueError("Headset audio requires Windows")
        script = Path(required_string(self.host(), "voiceListener")).resolve()
        if not script.is_file():
            raise ValueError("Configured voiceListener is unavailable; acquire/configure the independent listener")
        result = subprocess.run([sys.executable, str(script), "--devices"], capture_output=True, text=True, encoding="utf-8")
        if result.returncode or not device.strip() or device.casefold() not in result.stdout.casefold():
            raise ValueError("Select an actual headset microphone from asr-listen.py --devices; no default-device fallback")
        folder = self.local / "voice"
        folder.mkdir(exist_ok=True)
        with (folder / "listener.log").open("a", encoding="utf-8") as log:
            child = subprocess.Popen([sys.executable, str(script), "--device", device, "--wake", "полигон", "--heartbeat", "0"], stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        return {"pid": child.pid, "device": device, "wakeWord": "полигон", "healthRequired": "http://127.0.0.1:8931/api/health", "notice": "Launch is not microphone qualification; verify health and an actual spoken phrase. Existing listener ownership is respected."}

    def pending(self):
        with self.connect() as con:
            rows = con.execute("SELECT * FROM jobs WHERE status IN ('recorded','blocked') AND delivery IS NULL ORDER BY submitted").fetchall()
        out = []
        for row in rows:
            packet = read(row["packet"])
            order = json.loads(row["request"])
            if any(packet[k] != order[k] for k in ("sourceChat", "sourceThreadId")) or packet["orderId"] != row["id"]:
                raise ValueError("Packet origin/order mismatch; delivery refused")
            out.append({"orderId": row["id"], "threadId": order["sourceThreadId"],
                        "sourceChat": order["sourceChat"], "packet": row["packet"], "packetSha256": digest(row["packet"]),
                        "text": f"Skyrim-Polygon order {row['id']}: {packet['executionOutcome']}. Raw evidence packet: {row['packet']}. Read and analyze once in the originating chat. This notification alone does not authorize fixes or a new test; continuing requires a separately owner-authorized active cycle."})
        return out

    def delivered(self, job, receipt):
        if not isinstance(receipt, str) or not receipt.strip():
            raise ValueError("Verified delivery receipt required")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM jobs WHERE id=?", (job,)).fetchone()
            if not row or row["status"] not in ("recorded", "blocked", "delivered"):
                raise ValueError("No result to deliver")
            if row["status"] == "delivered":
                return {"id": job, "duplicate": True}
            con.execute("UPDATE jobs SET status='delivered',delivery=? WHERE id=?", (receipt, job))
            self.event(con, job, "delivered", receipt)
        return {"id": job, "status": "delivered"}

    def board(self):
        with self.connect() as con:
            rows = con.execute("SELECT * FROM jobs ORDER BY submitted DESC").fetchall()
            result = []
            for row in rows:
                item = {k: row[k] for k in ("id", "mode", "subject", "origin", "status", "submitted", "note", "packet", "delivery")}
                cycle = json.loads(row["request"]).get("cycle")
                item["workflow"] = "full-cycle" if cycle is not None else "standard"
                item["cycleId"] = cycle["id"] if isinstance(cycle, dict) else None
                item["awaitingOwnerStart"] = row["mode"] == "automatic" and row["status"] == "queued" and cycle is None and not con.execute("SELECT id FROM released_orders WHERE id=?", (row["id"],)).fetchone()
                result.append(item)
        return result

    def serve(self, port):
        polygon = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/board.json":
                    body, mime = json.dumps(polygon.board(), ensure_ascii=False).encode(), "application/json"
                elif self.path == "/":
                    body, mime = (HERE / "board.html").read_bytes(), "text/html; charset=utf-8"
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="Host session directory outside Git; alternatively SKYRIM_POLYGON_ROOT")
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("order", type=Path)
    register = sub.add_parser("cycle-register", help="Only after verifying a direct owner start; never inferred from an order")
    register.add_argument("authorization", type=Path)
    batch = sub.add_parser("batch-release", help="Only after the owner asks Polygon to start prepared standard orders")
    batch.add_argument("authorization", type=Path)
    ticket = sub.add_parser("slot-request")
    ticket.add_argument("request", type=Path)
    for name in ("slots", "slot-next"):
        sub.add_parser(name)
    sub.add_parser("pipeline-status")
    hold = sub.add_parser("pipeline-hold")
    hold.add_argument("id")
    hold.add_argument("--note", required=True)
    clear = sub.add_parser("pipeline-clear")
    clear.add_argument("id")
    clear.add_argument("evidence", type=Path)
    notified = sub.add_parser("slot-notified")
    notified.add_argument("id")
    notified.add_argument("--note", required=True)
    clearance = sub.add_parser("slot-clear")
    clearance.add_argument("id")
    clearance.add_argument("evidence", type=Path)
    state = sub.add_parser("cycle-show")
    state.add_argument("id")
    stop = sub.add_parser("cycle-stop")
    stop.add_argument("id")
    stop.add_argument("--status", choices=["cancelled", "complete", "blocked"], required=True)
    stop.add_argument("--note", required=True)
    for name in ("board", "next", "reconcile", "outbox", "recover-active"):
        sub.add_parser(name)
    for name in ("show", "assisted-start", "assisted-poll", "assisted-finish", "_execute", "delivered"):
        item = sub.add_parser(name)
        item.add_argument("id")
        if name in ("assisted-finish", "delivered"):
            item.add_argument("--note", required=True)
    server = sub.add_parser("serve")
    server.add_argument("--port", type=int, default=8934)
    voice = sub.add_parser("voice-start")
    voice.add_argument("--device", required=True)
    note = sub.add_parser("note")
    note.add_argument("id")
    note.add_argument("--category", choices=["observation", "player_instruction", "tool_bug", "tool_suspected_bug", "tool_improvement"], required=True)
    note.add_argument("--text", required=True)
    args = parser.parse_args(argv)
    try:
        polygon = Polygon(session_root(args.root))
        if args.command == "submit": result = polygon.submit(args.order)
        elif args.command == "cycle-register": result = polygon.register_cycle(args.authorization)
        elif args.command == "batch-release": result = polygon.release_batch(args.authorization)
        elif args.command == "slot-request": result = polygon.request_slot(args.request)
        elif args.command == "slots": result = polygon.slots()
        elif args.command == "slot-next": result = polygon.grant_slot()
        elif args.command == "pipeline-status": result = polygon.pipeline_status()
        elif args.command == "pipeline-hold": result = polygon.hold_pipeline(args.id, args.note)
        elif args.command == "pipeline-clear": result = polygon.clear_pipeline(args.id, args.evidence)
        elif args.command == "slot-notified": result = polygon.slot_notified(args.id, args.note)
        elif args.command == "slot-clear": result = polygon.clear_slot(args.id, args.evidence)
        elif args.command == "cycle-show": result = polygon.cycle_state(args.id)
        elif args.command == "cycle-stop": result = polygon.stop_cycle(args.id, args.status, args.note)
        elif args.command == "board": result = polygon.board()
        elif args.command == "show": result = polygon.get(args.id)
        elif args.command == "next": result = polygon.execute_next()
        elif args.command == "reconcile": result = polygon.reconcile()
        elif args.command == "recover-active": result = polygon.recover_active()
        elif args.command == "outbox": result = polygon.pending()
        elif args.command == "delivered": result = polygon.delivered(args.id, args.note)
        elif args.command == "assisted-start": result = polygon.assisted_start(args.id)
        elif args.command == "assisted-poll": result = polygon.assisted_poll(args.id)
        elif args.command == "assisted-finish":
            row = polygon.get(args.id)
            if row["mode"] != "assisted" or row["status"] != "running": raise ValueError("No active assisted session")
            result = polygon.finish(args.id, "collected", args.note)
        elif args.command == "_execute": return polygon.child_execute(args.id)
        elif args.command == "serve": return polygon.serve(args.port)
        elif args.command == "voice-start": result = polygon.voice_start(args.device)
        elif args.command == "note": result = polygon.note(args.id, args.category, args.text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

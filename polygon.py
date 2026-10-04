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
DEFAULT_ROOT = HERE.parents[4]
SAFE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,79}")
SHA = re.compile(r"[0-9a-f]{64}")
READ_KINDS = {"state", "player", "refs", "scene", "vm", "world_observer"}


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
        canonical = json.dumps(order, ensure_ascii=False, sort_keys=True)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            previous = con.execute("SELECT request FROM jobs WHERE id=?", (order["id"],)).fetchone()
            if previous:
                if previous["request"] != canonical:
                    raise ValueError("Order id already used for different content; create a new id")
                return {"id": order["id"], "duplicate": True}
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
            if con.execute("SELECT id FROM jobs WHERE status='running'").fetchone():
                return None
            if job:
                row = con.execute("SELECT * FROM jobs WHERE id=? AND mode=? AND status='waiting_player'", (job, mode)).fetchone()
            else:
                row = con.execute("SELECT * FROM jobs WHERE mode=? AND status='queued' ORDER BY submitted,id LIMIT 1", (mode,)).fetchone()
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
        return {"id": job, "recorded": str(folder / name)}

    def finish(self, job, outcome, note, run=None, restored=None):
        row = self.get(job)
        order = json.loads(row["request"])
        folder = self.evidence_dir(job)
        folder.mkdir(parents=True, exist_ok=True)
        self.self_checks(job, run)
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
        packet_path = folder / "packet.json"
        write(packet_path, packet)
        with self.connect() as con:
            status = "blocked" if outcome == "blocked" else "recorded"
            con.execute("UPDATE jobs SET status=?,packet=?,note=? WHERE id=?", (status, str(packet_path), note, job))
            self.event(con, job, status, note)
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
        self.verify_inputs(order)
        for pin in read(self.evidence_dir(job) / "executor-pins.json"):
            if digest(pin["path"]) != pin["sha256"]:
                raise ValueError("Executor changed after claim")
        self.executor()
        from skyrim_autotest import runner
        from skyrim_autotest.config import load
        runner.configure(load(self.evidence_dir(job) / "config.json"))
        return runner.run(order["profile"], self.evidence_dir(job) / "scenario.json",
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
        tools = HERE.parent
        script = tools / "asr-listen.py"
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
            out.append({"orderId": row["id"], "threadId": packet["sourceThreadId"],
                        "sourceChat": packet["sourceChat"], "packet": row["packet"],
                        "text": f"Skyrim-Polygon order {row['id']}: {packet['executionOutcome']}. Raw evidence packet: {row['packet']}. No mod diagnosis performed; analyze in the originating chat."})
        return out

    def delivered(self, job, receipt):
        row = self.get(job)
        if row["status"] not in ("recorded", "blocked", "delivered"):
            raise ValueError("No result to deliver")
        with self.connect() as con:
            con.execute("UPDATE jobs SET status='delivered',delivery=? WHERE id=?", (receipt, job))
            self.event(con, job, "delivered", receipt)

    def board(self):
        with self.connect() as con:
            rows = con.execute("SELECT id,mode,subject,origin,status,submitted,note,packet,delivery FROM jobs ORDER BY submitted DESC").fetchall()
        return [dict(row) for row in rows]

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
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("order", type=Path)
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
    polygon = Polygon(args.root)
    try:
        if args.command == "submit": result = polygon.submit(args.order)
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

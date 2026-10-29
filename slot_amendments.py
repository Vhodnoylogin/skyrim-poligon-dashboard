"""Explicit reviewed revision of an ungranted preparation draft, never a test retry."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def text_sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _pin(pin, parent):
    import polygon as m
    if not isinstance(pin, dict) or set(pin) != {"path", "sha256"}:
        raise ValueError("Exact file-backed amendment pin required")
    path = (parent / m.required_string(pin, "path")).resolve()
    if not m.SHA.fullmatch(pin.get("sha256", "")) or m.digest(path) != pin["sha256"]:
        raise ValueError("Amendment evidence pin changed")
    pin["path"] = str(path)
    return path


def _document(pin, parent):
    path = _pin(pin, parent)
    with path.open('rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("Amendment review/request must be a bounded JSON document")
    if hashlib.sha256(raw).hexdigest() != pin['sha256']:
        raise ValueError("Amendment document changed while reading its pinned bytes")
    value = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Amendment review/request must be a JSON object")
    return path, value


def _writes(values, parent):
    if not isinstance(values, list) or not values or any(not isinstance(p, str) or not p.strip() for p in values):
        raise ValueError("Declare every reviewed preparation writePath")
    result = [str((parent / p).resolve()) for p in values]
    if len({os.path.normcase(p) for p in result}) != len(result):
        raise ValueError("Duplicate amendment writePath")
    return result


class SlotAmendments:
    def amend_slot(self, slot, path):
        """Amend metadata only; preserve one physical reservation and all old evidence."""
        import polygon as m
        path = Path(path).resolve()
        with path.open('rb') as stream:
            source_bytes = stream.read(1024 * 1024 + 1)
        if len(source_bytes) > 1024 * 1024:
            raise ValueError("Preparation amendment must be a bounded JSON document")
        amendment = json.loads(source_bytes.decode('utf-8-sig'))
        required = {"schemaVersion", "id", "slotId", "cycleId", "iteration", "orderId",
                    "sourceChat", "sourceThreadId", "previousRequestSha256", "replacementRequest",
                    "review", "ownerAuthorization"}
        if (not isinstance(amendment, dict) or amendment.get("schemaVersion") != 1 or
                not required <= set(amendment) or set(amendment) - required - {"originalClearance"}):
            raise ValueError("Exact preparation amendment fields/schemaVersion1 required")
        for key in ("id", "slotId", "cycleId", "orderId"):
            if not m.SAFE_ID.fullmatch(m.required_string(amendment, key)):
                raise ValueError("Safe amendment/slot/cycle/order id required")
        if amendment["slotId"] != slot or not m.SHA.fullmatch(amendment.get("previousRequestSha256", "")):
            raise ValueError("Exact prior slot/request hash required")
        m.owner_evidence(amendment, path, require_deadline=False)
        replacement_path, replacement = _document(amendment["replacementRequest"], path.parent)
        replacement["writePaths"] = _writes(replacement.get("writePaths"), replacement_path.parent)
        review_path, review = _document(amendment["review"], path.parent)
        for key in ("reason", "verifiedBy", "reviewerThreadId"):
            m.required_string(review, key)
        if review["reviewerThreadId"] == amendment["sourceThreadId"]:
            raise ValueError("Preparation amendment requires an independent reviewer")
        expected = {key: amendment[key] for key in ("slotId", "cycleId", "iteration", "orderId", "sourceChat", "sourceThreadId", "previousRequestSha256")}
        expected.update(schemaVersion=1, replacementRequestSha256=amendment["replacementRequest"]["sha256"],
                        neverGranted=True, neverAcknowledged=True, noSubmittedOrder=True,
                        liveWrites=False, physicalGameStarts=0, withinOriginalAllowedChanges=True)
        if (any(type(review.get(key)) is not type(value) or review.get(key) != value for key, value in expected.items()) or
                _writes(review.get("allowedWritePaths"), review_path.parent) != replacement["writePaths"]):
            raise ValueError("Exact independent zero-effect and bounded write-scope review required")
        evidence = review.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError("Independent zero-effect review needs pinned evidence")
        for item in evidence:
            _pin(item, review_path.parent)
        clearance = None
        if "originalClearance" in amendment:
            clearance_path, clearance = _document(amendment["originalClearance"], path.parent)
            m.owner_evidence(clearance, clearance_path, require_deadline=False)
        snapshot = {"amendment": amendment, "review": review,
                    "replacementRequest": replacement,
                    "sourceFile": {"path": str(path), "sha256": hashlib.sha256(source_bytes).hexdigest()}}
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            # Exact duplicate recognition is read-only even after a later grant.
            # Reusing an amendment id can never renew FIFO, limits or permission.
            for event in con.execute("SELECT note FROM events WHERE status='slot_draft_amended'"):
                old = json.loads(event["note"])
                if old.get("amendment", {}).get("id") == amendment["id"]:
                    if old.get("amendment") != amendment or old.get("review") != review or old.get("replacementRequest") != replacement:
                        raise ValueError("Amendment id already used with different content")
                    current = con.execute("SELECT request,status FROM cycle_slots WHERE id=?", (slot,)).fetchone()
                    return {"id": slot, "amendmentId": amendment["id"], "duplicate": True,
                            "status": current['status'], "currentlyApplied": current['request'] == canonical(replacement),
                            "currentRequestSha256": text_sha(current['request'])}
            row = con.execute("SELECT * FROM cycle_slots WHERE id=?", (slot,)).fetchone()
            if not row or row["status"] not in ("waiting", "released") or row["receipt"] is not None:
                raise ValueError("Only never-granted/unacknowledged preparation drafts may be amended")
            original = json.loads(row["request"])
            identities = {"slotId": row["id"], "cycleId": row["cycle_id"], "iteration": row["iteration"],
                          "orderId": row["order_id"], "sourceChat": original["sourceChat"], "sourceThreadId": original["sourceThreadId"]}
            if (any(type(amendment.get(k)) is not type(v) or amendment[k] != v for k, v in identities.items()) or
                    text_sha(row["request"]) != amendment["previousRequestSha256"]):
                raise ValueError("Preparation amendment origin/iteration/order/prior request changed")
            if {k: v for k, v in original.items() if k != "writePaths"} != {k: v for k, v in replacement.items() if k != "writePaths"}:
                raise ValueError("Preparation amendment may change only writePaths")
            if replacement["writePaths"] == original["writePaths"]:
                raise ValueError("Preparation amendment must correct writePaths")
            cycle = con.execute("SELECT * FROM cycles WHERE id=?", (row["cycle_id"],)).fetchone()
            if not cycle or cycle["status"] != "active":
                raise ValueError("Preparation amendment needs the same active owner cycle")
            approval = json.loads(cycle["authorization"])
            if time.time() >= approval["deadlineUtc"] or m.digest(approval["ownerAuthorization"]["path"]) != approval["ownerAuthorization"]["sha256"]:
                raise ValueError("Original cycle deadline/provenance changed")
            if any(amendment["ownerAuthorization"].get(k) != approval["ownerAuthorization"].get(k)
                   for k in ("threadId", "messageId", "quote", "path", "sha256")):
                raise ValueError("Amendment must retain the original owner authority")
            if (amendment["sourceChat"] != approval["sourceChat"] or amendment["sourceThreadId"] != approval["sourceThreadId"] or
                    type(amendment["iteration"]) is not int or not 1 <= amendment["iteration"] <= approval["maxIterations"]):
                raise ValueError("Original cycle origin/iteration limits changed")
            for table, column in (("jobs", "id"), ("attempts", "id"), ("platform_attempts", "id"),
                                  ("session_members", "order_id"), ("retry_attempts", "order_id"),
                                  ("released_orders", "id")):
                if con.execute(f"SELECT 1 FROM {table} WHERE {column}=?", (row["order_id"],)).fetchone():
                    raise ValueError("Submitted or attempted subject cannot amend its preparation draft")
            history = con.execute("SELECT status,note FROM events WHERE id=?", (slot,)).fetchall()
            if any(event["status"] not in ("slot_requested", "slot_cleared", "slot_draft_amended") for event in history):
                raise ValueError("Prior grant/ack/unknown slot history prevents draft amendment")
            for event in history:
                if event["status"] == "slot_cleared" and json.loads(event["note"]).get("originalSlot", {}).get("status") != "waiting":
                    raise ValueError("Retained clearance history does not prove an ungranted waiting draft")
            # Old versions did not log grants. A released legacy row is not proof
            # of never-granted state: retain its exact pinned pre-clear review.
            if row["status"] == "released":
                if "originalClearance" not in amendment:
                    raise ValueError("Released draft needs its pinned original waiting-state clearance")
                if (json.loads(row["note"]) != clearance or clearance.get("slotId") != slot or
                        clearance.get("installationSettled") is not True or
                        clearance.get("review", {}).get("oldTicketStatus") != "waiting"):
                    raise ValueError("Original clearance must match retained pre-clear waiting evidence")
                snapshot["originalClearance"] = clearance
            elif "originalClearance" in amendment:
                raise ValueError("Waiting draft has no released original clearance")
            if time.time() >= approval['deadlineUtc']:
                raise ValueError('Original cycle deadline elapsed during amendment review')
            snapshot.update(originalSlot=dict(row), cycleAuthorizationSha256=text_sha(cycle["authorization"]))
            self.event(con, slot, "slot_draft_amended", canonical(snapshot))
            event_seq = con.execute("SELECT last_insert_rowid()").fetchone()[0]
            note = canonical({"kind": "slot-draft-amendment/1", "amendmentId": amendment["id"], "auditEventSeq": event_seq})
            con.execute("UPDATE cycle_slots SET request=?,status='waiting',note=? WHERE id=?",
                        (canonical(replacement), note, slot))
        return {"id": slot, "amendmentId": amendment["id"], "status": "waiting", "auditEventSeq": event_seq,
                "notice": "Preparation metadata only; no grant, installation, test retry, budget extension or hold clearance"}

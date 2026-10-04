"""Queue ownership, immutable inputs, delivery and assisted boundaries."""
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("polygon", Path(__file__).with_name("polygon.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Tests(unittest.TestCase):
    def test_root_from_checkout_location_is_never_guessed(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True), patch.object(mod.Path, "cwd", return_value=Path(folder)):
            with self.assertRaisesRegex(ValueError, "--root"):
                mod.session_root()

    def test_explicit_root_wins_and_nested_cwd_finds_host(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"SKYRIM_POLYGON_ROOT": folder}, clear=True):
            root = Path(folder).resolve()
            self.assertEqual(mod.session_root(), root)
            self.assertEqual(mod.session_root(root / "other"), root / "other")
            mod.write(root / "local/skyrim-polygon/config.json", {})
            with patch.dict(os.environ, {}, clear=True), patch.object(mod.Path, "cwd", return_value=root / "nested"):
                self.assertEqual(mod.session_root(), root)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.p = mod.Polygon(self.root)
        self.input = self.root / "subject.dll"
        self.input.write_bytes(b"test build")
        self.order = {"schemaVersion": 1, "id": "test-1", "mode": "assisted", "subject": "Fixture mod",
                      "sourceChat": "fixture", "sourceThreadId": "thread-1", "profile": "Test",
                      "purpose": "Collect state", "collect": ["state"],
                      "inputs": [{"path": str(self.input), "sha256": mod.digest(self.input)}],
                      "playerSteps": ["Enter fixture"], "observations": [{"tool": "inspect", "args": {"kind": "state"}}]}
        self.file = self.root / "order.json"

    def submit(self):
        mod.write(self.file, self.order)
        return self.p.submit(self.file)

    def test_duplicate_is_idempotent_changed_order_rejected(self):
        self.submit()
        self.assertTrue(self.submit()["duplicate"])
        self.order["purpose"] = "Different test"
        with self.assertRaises(ValueError): self.submit()
        self.assertEqual(len(self.p.board()), 1)

    def test_changed_installed_build_refuses_before_claim(self):
        self.submit()
        self.input.write_bytes(b"new build")
        with self.assertRaises(ValueError): self.p.assisted_start("test-1")
        self.assertEqual(self.p.get("test-1")["status"], "waiting_player")

    def test_assisted_not_picked_by_automatic_worker(self):
        self.submit()
        self.assertIsNone(self.p.claim())

    def test_two_connections_cannot_claim_two_game_sessions(self):
        self.submit()
        self.order["id"] = "test-2"
        self.submit()
        other = mod.Polygon(self.root)
        self.assertIsNotNone(self.p.claim("assisted", "test-1"))
        self.assertIsNone(other.claim("assisted", "test-2"))

    def test_assisted_start_has_no_game_launch_and_own_voice_cursor(self):
        self.submit()
        heard = self.root / "local/voice/heard.jsonl"
        heard.parent.mkdir(parents=True)
        heard.write_text('{"seq":8,"text":"old"}\n', encoding="utf-8")
        shared = heard.with_name("cursor")
        shared.write_text("3")
        with patch.object(mod.subprocess, "run", side_effect=AssertionError("No subprocess allowed")):
            self.p.assisted_start("test-1")
        state = mod.read(self.p.evidence_dir("test-1") / "assisted-state.json")
        self.assertEqual(state["voiceCursor"], 8)
        self.assertEqual(shared.read_text(), "3")

    def test_assisted_mutation_rejected(self):
        self.order["observations"] = [{"tool": "console", "args": {"command": "coc QASmoke"}}]
        with self.assertRaises(ValueError): self.submit()
        self.order["observations"] = [{"tool": "inspect", "args": {"kind": "world_observer", "action": "delete"}}]
        with self.assertRaises(ValueError): self.submit()

    def test_packet_is_raw_delivery_pending_until_receipt(self):
        self.submit()
        self.p.assisted_start("test-1")
        packet = self.p.finish("test-1", "collected", "Player finished")
        self.assertIsNone(packet["analysis"])
        self.assertIsNone(packet["restored"])
        self.assertEqual(self.p.pending()[0]["threadId"], "thread-1")
        self.p.delivered("test-1", "App tool returned success")
        self.assertFalse(self.p.pending())

    def test_unfinished_run_retains_active_barrier(self):
        self.submit()
        # Simulate a crashed automatic worker, not a live game.
        order = dict(self.order, mode="automatic", resolvedConfig={"runtime": str(self.root / "runtime")})
        with self.p.connect() as con:
            con.execute("UPDATE jobs SET mode='automatic',status='running',request=? WHERE id='test-1'", (json.dumps(order),))
        state_path = self.root / "runtime/runs/run-1/state.json"
        mod.write(state_path, {"order": {"id": "test-1"}, "done": False, "restored": False})
        self.assertEqual(self.p.reconcile(), [])
        self.assertEqual(self.p.get("test-1")["status"], "running")
        self.assertIsNone(self.p.claim())

    def test_completed_run_reconciles_without_rerun(self):
        self.submit()
        order = dict(self.order, mode="automatic", resolvedConfig={"runtime": str(self.root / "runtime")})
        with self.p.connect() as con:
            con.execute("UPDATE jobs SET mode='automatic',status='running',request=? WHERE id='test-1'", (json.dumps(order),))
        folder = self.root / "runtime/runs/run-1"
        mod.write(folder / "state.json", {"order": {"id": "test-1"}, "done": True, "restored": True, "result": "failed"})
        mod.write(folder / "result.json", {"restored": True, "result": "failed", "restoreErrors": []})
        with patch.object(mod.subprocess, "run", side_effect=AssertionError("Must not rerun")):
            self.assertEqual(self.p.reconcile(), ["test-1"])
            self.assertEqual(self.p.reconcile(), [])
        self.assertEqual(mod.read(self.p.get("test-1")["packet"])["executionOutcome"], "failed")

    def test_no_delivery_of_unexecuted_order(self):
        self.submit()
        with self.assertRaises(ValueError): self.p.delivered("test-1", "fake receipt")

    def test_listener_restart_marks_gap_without_replaying_old_speech(self):
        self.submit()
        self.p.assisted_start("test-1")
        mod.write(self.p.local / "config.json", {"devbenchRuntimeFiles": []})
        state_file = self.p.evidence_dir("test-1") / "assisted-state.json"
        state = mod.read(state_file)
        state.update(voiceSession=[999, 1], voiceCursor=8)
        mod.write(state_file, state)
        heard = self.root / "local/voice/heard.jsonl"
        heard.parent.mkdir(parents=True, exist_ok=True)
        heard.write_text('{"seq":9,"at":"1970-01-01T00:01:39+00:00","text":"old"}\n'
                         '{"seq":1,"at":"1970-01-01T00:01:41+00:00","text":"new"}\n', encoding="utf-8")
        with patch.object(mod.time, "time", return_value=100), patch.object(mod, "urlopen", return_value=io.StringIO('{"pid":1,"since":100}')):
            result = self.p.assisted_poll("test-1")
        self.assertEqual([r["text"] for r in result["voice"]], ["new"])
        self.assertTrue(any(e.get("gap") for e in result["errors"]))


if __name__ == "__main__": unittest.main()

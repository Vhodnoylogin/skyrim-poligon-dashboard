"""Queue ownership, immutable inputs, delivery and assisted boundaries."""
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import time
import types
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
        native_idle = patch.object(mod.Polygon, "environment_idle", return_value=True)
        native_idle.start()
        self.addCleanup(native_idle.stop)
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

    def automatic_submit(self, cycle=None):
        self.order.update(mode="automatic", config="config.json", scenario="scenario.json")
        if cycle is not None:
            self.order["cycle"] = cycle
            try:
                approval = json.loads(self.p.cycle_state(cycle["id"])["authorization"])
            except ValueError:
                approval = None
            if approval and 1 <= cycle["iteration"] <= approval["maxIterations"] and self.order["sourceThreadId"] == approval["sourceThreadId"]:
                slots = [s for s in self.p.slots() if (s["cycle_id"], s["iteration"]) == (cycle["id"], cycle["iteration"])]
                if not slots:
                    slot_id = "slot-" + self.order["id"]
                    ticket = self.root / (slot_id + ".json")
                    mod.write(ticket, {"schemaVersion": 1, "id": slot_id, "cycleId": cycle["id"],
                              "iteration": cycle["iteration"], "orderId": self.order["id"],
                              "sourceChat": self.order["sourceChat"], "sourceThreadId": self.order["sourceThreadId"],
                              "writePaths": [str(self.input)]})
                    self.p.request_slot(ticket)
                    grant = self.p.grant_slot()
                    if grant.get("id") == slot_id and grant["status"] == "reserved":
                        self.p.slot_notified(slot_id, "Offline exact-origin grant receipt")
                    cycle["slotId"] = slot_id
                else:
                    cycle["slotId"] = slots[0]["id"]
        mod.write(self.root / "config.json", {"runtime": str(self.root / "runtime")})
        mod.write(self.root / "scenario.json", {"fixture": "offline"})
        # A stub config/scenario parser: no external runtime or process is used.
        config = types.ModuleType("skyrim_autotest.config")
        config.load = mod.read
        with patch.object(self.p, "executor", return_value=(self.root, lambda s: None)), patch.dict(mod.sys.modules, {"skyrim_autotest.config": config}):
            return self.submit()

    def approval(self, cycle=True, **changes):
        evidence = self.root / "owner-start.txt"
        evidence.write_text("Owner: start the full cycle for Fixture mod; or start this ready batch.", encoding="utf-8")
        value = {"schemaVersion": 1, "id": "cycle-1" if cycle else "batch-1", "deadlineUtc": time.time() + 3600,
                 "ownerAuthorization": {"threadId": "owner-thread", "messageId": "owner-turn", "quote": "Owner: start",
                                        "path": str(evidence), "sha256": mod.digest(evidence), "verifiedBy": "fixture"}}
        if cycle:
            value.update(sourceChat="fixture", sourceThreadId="thread-1", subject="Fixture mod", profile="Test",
                         scopeId="fixture-task", task="Fix the fixture", allowedChanges=["Fixture module"],
                         stopCriteria="Fixture acceptance", maxIterations=3)
        else:
            value["orderIds"] = ["test-1"]
        value.update(changes)
        path = self.root / (value["id"] + ".json")
        mod.write(path, value)
        return path

    def cycle(self, iteration=1, **changes):
        return dict(id="cycle-1", scopeId="fixture-task", iteration=iteration, buildId="build-" + str(iteration), **changes)

    def completed_cycle_iteration(self):
        self.p.register_cycle(self.approval())
        self.automatic_submit(self.cycle())
        self.assertIsNotNone(self.p.claim())
        self.finish_cycle_fixture("test-1", "run-1")
        self.p.delivered("test-1", "App receipt for thread-1/test-1")
        packet_path = Path(self.p.get("test-1")["packet"])
        decision = self.root / "analysis.json"
        mod.write(decision, {"cycleId": "cycle-1", "previousOrderId": "test-1", "previousPacketSha256": mod.digest(packet_path),
                  "sourceThreadId": "thread-1", "action": "fix-and-retest", "reason": "Bounded fixture fix",
                  "withinScope": True, "evidenceComplete": True, "toolingHealthy": True, "criteriaUnmet": True})
        self.order["id"] = "test-2"
        self.input.write_bytes(b"fixed installed build")
        self.order["inputs"][0]["sha256"] = mod.digest(self.input)
        return self.cycle(2, previousOrderId="test-1", previousPacketSha256=mod.digest(packet_path),
                          decision={"path": str(decision), "sha256": mod.digest(decision)})

    def finish_cycle_fixture(self, job, run):
        folder = self.root / "runtime/runs" / run
        archive = folder / "test-profile"
        (archive / "saves").mkdir(parents=True)
        (archive / "saves/fixture.ess").write_bytes(b"fake save")
        mod.write(folder / "state.json", {"order": {"id": job}, "done": True, "restored": True,
                  "profileArchive": str(archive), "testProfile": str(self.root / "profiles" / ("Autotest-" + run))})
        mod.write(folder / "result.json", {"restored": True, "result": "failed", "restoreErrors": []})
        self.p.finish(job, "failed", "Prescribed assertion mismatch", folder, True)

    def ticket(self, slot, cycle, order, iteration=1, chat="fixture", thread="thread-1"):
        path = self.root / (slot + ".json")
        mod.write(path, {"schemaVersion": 1, "id": slot, "cycleId": cycle, "iteration": iteration,
                        "orderId": order, "sourceChat": chat, "sourceThreadId": thread, "writePaths": [str(self.input)]})
        return path

    def clearance(self, slot=None, hold=None):
        value = mod.read(self.approval(False, deadlineUtc=None))
        value.update(slotId=slot, holdId=hold, installationSettled=True)
        path = self.root / "clearance.json"
        mod.write(path, value)
        return path

    def test_three_cycles_fifo_fairness_and_independent_cancellation(self):
        self.completed_cycle_iteration()  # A1 finished; A may request A2.
        self.p.register_cycle(self.approval(id="cycle-b", sourceChat="fixture-b", sourceThreadId="thread-b", subject="Fixture B"))
        self.p.register_cycle(self.approval(id="cycle-c", sourceChat="fixture-c", sourceThreadId="thread-c", subject="Fixture C"))
        b = self.ticket("slot-b1", "cycle-b", "test-b1", chat="fixture-b", thread="thread-b")
        self.p.request_slot(b)
        self.assertTrue(self.p.request_slot(b)["duplicate"])
        self.p.request_slot(self.ticket("slot-c1", "cycle-c", "test-c1", chat="fixture-c", thread="thread-c"))
        self.p.request_slot(self.ticket("slot-a2", "cycle-1", "test-2", iteration=2))
        self.assertEqual(self.p.grant_slot()["id"], "slot-b1")
        other = mod.Polygon(self.root)
        self.assertEqual(other.grant_slot()["id"], "slot-b1")
        self.p.slot_notified("slot-b1", "App receipt thread-b/slot-b1")
        self.assertTrue(self.p.slot_notified("slot-b1", "Duplicate app receipt")["duplicate"])
        self.p.stop_cycle("cycle-b", "cancelled", "Owner cancelled B only")
        self.assertEqual(self.p.grant_slot()["status"], "blocked")
        self.p.clear_slot("slot-b1", self.clearance(slot="slot-b1"))
        self.assertEqual(self.p.grant_slot()["id"], "slot-c1")
        self.assertEqual(self.p.cycle_state("cycle-1")["status"], "active")
        self.assertEqual(self.p.cycle_state("cycle-c")["status"], "active")

    def test_install_slot_excludes_other_game_orders_and_never_expires_open(self):
        self.automatic_submit()
        self.p.register_cycle(self.approval())
        self.p.request_slot(self.ticket("slot-first", "cycle-1", "test-cycle"))
        self.assertEqual(self.p.grant_slot()["id"], "slot-first")
        self.p.release_batch(self.approval(False))
        self.assertIsNone(self.p.claim())
        with self.assertRaisesRegex(ValueError, "installation/run slot"):
            self.p.check_launch_authorization(self.order)
        with patch.object(mod.time, "time", return_value=time.time() + 7200):
            self.assertEqual(self.p.grant_slot()["status"], "blocked")
        self.assertEqual(self.p.pipeline_status()["slots"][0]["status"], "blocked")

    def test_shared_tooling_hold_stops_all_dispatch_but_not_result_delivery(self):
        self.completed_cycle_iteration()
        self.p.hold_pipeline("observer-fault", "Observer schema/provenance is uncertain")
        self.assertIsNone(self.p.claim())
        self.assertEqual(self.p.grant_slot()["status"], "pipeline_held")
        self.p.clear_pipeline("observer-fault", self.clearance(hold="observer-fault"))
        self.assertFalse(self.p.pipeline_status()["holds"])

    def test_slot_origin_and_receipt_required_before_order_admission(self):
        self.p.register_cycle(self.approval())
        with self.assertRaisesRegex(ValueError, "origin mismatch"):
            self.p.request_slot(self.ticket("slot-bad", "cycle-1", "test-1", thread="wrong-thread"))
        self.p.request_slot(self.ticket("slot-real", "cycle-1", "test-1"))
        self.p.grant_slot()
        order = dict(self.order, mode="automatic", cycle=dict(self.cycle(), slotId="slot-real"))
        with self.p.connect() as con:
            with self.assertRaisesRegex(ValueError, "delivery receipt"):
                self.p.validate_cycle(con, order)

    def test_manual_released_batch_precedes_new_install_reservations(self):
        self.automatic_submit()
        self.p.release_batch(self.approval(False))
        self.p.register_cycle(self.approval())
        self.p.request_slot(self.ticket("slot-later", "cycle-1", "test-cycle"))
        self.assertEqual(self.p.grant_slot()["status"], "manual_batch_pending")

    def test_external_manual_game_refuses_preparation_grant(self):
        self.p.register_cycle(self.approval())
        self.p.request_slot(self.ticket("slot-later", "cycle-1", "test-cycle"))
        with patch.object(self.p, "environment_idle", return_value=False):
            self.assertEqual(self.p.grant_slot()["status"], "external_game_or_vr_busy")
        self.assertEqual(self.p.slots()[0]["status"], "waiting")

    def test_uncertain_restoration_retains_global_install_barrier(self):
        self.p.register_cycle(self.approval())
        self.automatic_submit(self.cycle())
        self.p.claim()
        self.p.finish("test-1", "failed", "Restore failed", restored=False)
        status = self.p.pipeline_status()
        self.assertTrue(status["holds"])
        self.assertEqual(status["slots"][0]["status"], "blocked")

    def test_standard_submit_waits_for_owner_batch_and_future_orders_wait(self):
        self.automatic_submit()
        self.assertIsNone(self.p.claim())
        self.assertTrue(self.p.board()[0]["awaitingOwnerStart"])
        with self.assertRaisesRegex(ValueError, "manual batch start"):
            self.p.check_launch_authorization(self.order)
        approval = self.approval(cycle=False)
        self.p.release_batch(approval)
        self.assertTrue(self.p.release_batch(approval)["duplicate"])
        self.order["id"] = "test-2"
        self.automatic_submit()
        self.assertEqual(self.p.claim()["id"], "test-1")
        self.p.finish("test-1", "blocked", "Offline prelaunch fixture")
        self.assertIsNone(self.p.claim())
        self.assertEqual(self.p.get("test-2")["status"], "queued")

    def test_manual_batch_provenance_expiry_and_atomic_validation(self):
        self.automatic_submit()
        with self.assertRaises(ValueError):
            self.p.release_batch(self.approval(False, orderIds=["test-1", "unknown"]))
        self.assertIsNone(self.p.claim())
        self.p.release_batch(self.approval(False))
        with patch.object(mod.time, "time", return_value=time.time() + 7200), patch.object(mod.subprocess, "run", side_effect=AssertionError("Must not launch")):
            self.assertEqual(self.p.execute_next()["executionOutcome"], "blocked")

    def test_standard_finite_batch_needs_no_cycle_time_budget(self):
        self.automatic_submit()
        self.p.release_batch(self.approval(False, deadlineUtc=None))
        with patch.object(mod.time, "time", return_value=time.time() + 7200):
            self.p.check_launch_authorization(self.order)

    def test_order_cannot_self_authorize_cycle(self):
        cycle = self.cycle()
        cycle["ownerAuthorization"] = {"quote": "I approve myself"}
        with self.assertRaisesRegex(ValueError, "separately authorized"):
            self.automatic_submit(cycle)
        self.assertFalse(self.p.board())

    def test_registration_requires_pinned_owner_evidence_and_finite_limits(self):
        with self.assertRaises(ValueError): self.p.register_cycle(self.approval(maxIterations=0))
        with self.assertRaises(ValueError): self.p.register_cycle(self.approval(deadlineUtc=float("inf")))
        path = self.approval()
        (self.root / "owner-start.txt").write_text("Changed")
        with self.assertRaises(ValueError): self.p.register_cycle(path)

    def test_cycle_does_not_release_unrelated_standard_order(self):
        self.automatic_submit()
        self.p.register_cycle(self.approval())
        self.order["id"] = "test-cycle"
        self.automatic_submit(self.cycle())
        self.assertEqual(self.p.claim()["id"], "test-cycle")
        self.assertEqual(self.p.get("test-1")["status"], "queued")

    def test_cycle_scope_iteration_and_cancellation_guards(self):
        path = self.approval()
        self.p.register_cycle(path)
        self.assertTrue(self.p.register_cycle(path)["duplicate"])
        with self.assertRaises(ValueError): self.automatic_submit(self.cycle(4))
        self.order["sourceThreadId"] = "wrong-origin"
        with self.assertRaises(ValueError): self.automatic_submit(self.cycle())
        self.order["sourceThreadId"] = "thread-1"
        self.automatic_submit(self.cycle())
        self.p.stop_cycle("cycle-1", "cancelled", "Owner cancelled")
        self.assertTrue(self.p.register_cycle(path)["duplicate"])
        self.assertEqual(self.p.cycle_state("cycle-1")["status"], "cancelled")
        with patch.object(mod.subprocess, "run", side_effect=AssertionError("Must not launch")):
            self.assertEqual(self.p.execute_next()["executionOutcome"], "blocked")

    def test_cycle_linear_continuation_and_duplicate_notification_cannot_branch(self):
        cycle = self.completed_cycle_iteration()
        self.automatic_submit(cycle)
        self.assertTrue(self.automatic_submit(cycle)["duplicate"])
        self.order["id"] = "test-branch"
        with self.assertRaisesRegex(ValueError, "nonbranching|slot"):
            self.automatic_submit(cycle)

    def test_cycle_changed_packet_decision_or_archive_stops_continuation(self):
        cycle = self.completed_cycle_iteration()
        packet = Path(self.p.get("test-1")["packet"])
        packet.write_text(packet.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "packet provenance"):
            self.automatic_submit(cycle)
        cycle["previousPacketSha256"] = mod.digest(packet)
        decision = mod.read(cycle["decision"]["path"])
        decision["previousPacketSha256"] = cycle["previousPacketSha256"]
        mod.write(cycle["decision"]["path"], decision)
        cycle["decision"]["sha256"] = mod.digest(cycle["decision"]["path"])
        (self.root / "runtime/runs/run-1/test-profile/saves/fixture.ess").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "profile/save evidence"):
            self.automatic_submit(cycle)

    def test_cycle_requires_fresh_build_and_healthy_analysis(self):
        cycle = self.completed_cycle_iteration()
        self.input.write_bytes(b"test build")
        self.order["inputs"][0]["sha256"] = mod.digest(self.input)
        with self.assertRaisesRegex(ValueError, "new build"):
            self.automatic_submit(cycle)
        self.input.write_bytes(b"fixed")
        self.order["inputs"][0]["sha256"] = mod.digest(self.input)
        decision = mod.read(cycle["decision"]["path"])
        decision["toolingHealthy"] = False
        mod.write(cycle["decision"]["path"], decision)
        cycle["decision"]["sha256"] = mod.digest(cycle["decision"]["path"])
        with self.assertRaisesRegex(ValueError, "Uncertain"):
            self.automatic_submit(cycle)

    def test_cycle_unverified_restoration_blocks_registration(self):
        self.p.register_cycle(self.approval())
        self.automatic_submit(self.cycle())
        self.p.claim()
        self.p.finish("test-1", "failed", "Restoration unknown", restored=False)
        self.assertEqual(self.p.cycle_state("cycle-1")["status"], "blocked")

    def test_cycle_cancellation_keeps_running_session_barrier(self):
        self.p.register_cycle(self.approval())
        self.automatic_submit(self.cycle())
        self.p.claim()
        self.p.stop_cycle("cycle-1", "cancelled", "Owner cancelled")
        self.assertEqual(self.p.get("test-1")["status"], "running")
        self.assertIsNone(self.p.claim())

    def test_active_profile_is_verified_without_creating_or_switching_one(self):
        self.automatic_submit()
        ini = self.root / "MO2/ModOrganizer.ini"
        ini.parent.mkdir()
        ini.write_text("[General]\nselected_profile=@ByteArray(Test)\n", encoding="utf-8")
        runner = types.SimpleNamespace(P=types.SimpleNamespace(mo2_ini=ini),
                                      native=types.SimpleNamespace(processes=lambda: []))
        before = ini.read_bytes()
        self.assertEqual(self.p.source_profile(self.order, runner), "Test")
        self.assertEqual(ini.read_bytes(), before)
        self.assertFalse((ini.parent / "profiles").exists())
        ini.write_text("selected_profile=@ByteArray(Changed)\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "differs from order"):
            self.p.source_profile(self.order, runner)

    def test_active_profile_reads_live_bridge_when_mo2_is_running(self):
        self.automatic_submit()
        token = self.root / "token.txt"
        token.write_text("offline-fixture-token")
        runner = types.SimpleNamespace(P=types.SimpleNamespace(bridge_token=token, bridge_port=1),
                    native=types.SimpleNamespace(processes=lambda: [{"name": "ModOrganizer.exe"}]),
                    request=lambda port, route, token: {"profile": "Test"})
        self.assertEqual(self.p.source_profile(self.order, runner), "Test")

    def test_exclusive_profile_is_owner_or_active_cycle_decision_only(self):
        self.order["profileSelection"] = {"mode": "exclusive", "authority": "cycle-origin", "reason": "Clean mod set required"}
        with self.assertRaisesRegex(ValueError, "authorized full cycle"):
            self.automatic_submit()
        self.p.register_cycle(self.approval())
        self.order["profile"] = "CleanFixture"
        self.automatic_submit(self.cycle())
        runner = types.SimpleNamespace()  # Exclusive source does not read or alter the active profile.
        self.assertEqual(self.p.source_profile(self.order, runner), "CleanFixture")

    def test_exclusive_standard_profile_requires_pinned_owner_instruction(self):
        self.order["profileSelection"] = {"mode": "exclusive", "authority": "owner", "reason": "Owner requests a clean game"}
        with self.assertRaisesRegex(ValueError, "direct owner evidence"):
            self.automatic_submit()
        approval = mod.read(self.approval(False))
        self.order["profileSelection"]["ownerAuthorization"] = approval["ownerAuthorization"]
        self.automatic_submit()
        self.p.release_batch(self.approval(False))
        self.p.check_launch_authorization(self.order)

    def test_cycle_deadline_or_changed_owner_provenance_refuses_launch(self):
        self.p.register_cycle(self.approval())
        self.automatic_submit(self.cycle())
        with patch.object(mod.time, "time", return_value=time.time() + 7200):
            with self.assertRaisesRegex(ValueError, "deadline"):
                self.p.check_launch_authorization(self.order)
        (self.root / "owner-start.txt").write_text("Changed")
        with self.assertRaisesRegex(ValueError, "provenance changed"):
            self.p.check_launch_authorization(self.order)

    def test_delivery_preserves_first_receipt_and_refuses_wrong_origin(self):
        self.submit()
        self.p.assisted_start("test-1")
        self.p.finish("test-1", "collected", "Offline collection")
        path = Path(self.p.get("test-1")["packet"])
        packet = mod.read(path)
        packet["sourceThreadId"] = "wrong-thread"
        mod.write(path, packet)
        with self.assertRaisesRegex(ValueError, "origin/order mismatch"): self.p.pending()
        packet["sourceThreadId"] = "thread-1"
        mod.write(path, packet)
        self.assertEqual(self.p.pending()[0]["packetSha256"], mod.digest(path))
        with self.assertRaises(ValueError): self.p.delivered("test-1", " ")
        self.p.delivered("test-1", "First verified receipt")
        self.assertTrue(self.p.delivered("test-1", "Repeated receipt")["duplicate"])
        self.assertEqual(self.p.get("test-1")["delivery"], "First verified receipt")

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

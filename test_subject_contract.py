"""Offline subject/platform separation, provenance, compatibility and launch gates."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import polygon as mod
import subject_contract as contract


class SeparationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.p = mod.Polygon(self.root)
        self.subject = self.root / "mod.dll"
        self.subject.write_bytes(b"subject")
        self.provider = self.root / "provider.dll"
        self.provider.write_bytes(b"provider1")
        self.executor = self.root / "executor"
        (self.executor / "skyrim_autotest").mkdir(parents=True)
        (self.executor / "skyrim_autotest/runner.py").write_text("# offline executor")
        (self.executor / "run.py").write_text("# offline entrypoint")
        self.config = self.root / "runner-config.json"
        mod.write(self.config, {"runtime": str(self.root / "runtime")})
        self.operations = {"state.read": {"tool": "inspect", "args": {"kind": "state"},
                                         "fields": {"world.ready": "playerLoaded"}}}
        self.evidence = self.root / "qualification-results.json"
        mod.write(self.evidence, {"offlineFixture": True, "check": "mapping qualified in isolated fixture"})
        self.manifest = self.root / "platform.json"
        self.qualification = self.root / "qualification.json"
        self.order = {"schemaVersion": 2, "id": "mod-test-1", "mode": "automatic",
                      "subject": "Fixture mod", "sourceChat": "fixture", "sourceThreadId": "thread-1",
                      "profile": "Test", "purpose": "Check actual response", "collect": ["state"],
                      "inputs": [{"path": str(self.subject), "sha256": mod.digest(self.subject), "role": "subject"}],
                      "subjectPlan": {"interface": contract.INTERFACE, "fixture": {"cell": "QASmoke"},
                                      "steps": [{"name": "subject-response", "operation": "state.read", "timeout": 10,
                                                 "assert": [{"field": "world.ready", "equals": True}]}]},
                      "testing": {"start": {"kind": "check", "name": "subject-response"},
                                  "checks": [{"name": "subject-response", "role": "subject"}]}}
        self.path = self.root / "order.json"
        self.qualify()
        self.config_module = types.ModuleType("skyrim_autotest.config")
        self.config_module.load = mod.read
        for p in (patch.object(self.p, "executor", return_value=(self.executor, lambda s: None)),
                  patch.dict(mod.sys.modules, {"skyrim_autotest.config": self.config_module})):
            p.start()
            self.addCleanup(p.stop)

    def qualify(self):
        pins = [{"path": str(p), "sha256": mod.digest(p)} for p in
                (self.provider, self.executor / "run.py", self.executor / "skyrim_autotest/runner.py")]
        mod.write(self.qualification, {"qualified": True, "interface": contract.INTERFACE,
                  "verifiedBy": "offline-test", "reason": "Isolated qualification fixture, no game",
                  "pins": pins, "operations": self.operations,
                  "configurationSha256": contract.identity(mod.read(self.config)),
                  "evidence": [{"path": str(self.evidence), "sha256": mod.digest(self.evidence)}]})
        mod.write(self.manifest, {"schemaVersion": 1, "interface": contract.INTERFACE,
                  "config": str(self.config), "operations": self.operations,
                  "inputs": [{"path": str(self.provider), "sha256": mod.digest(self.provider)}],
                  "qualification": {"path": str(self.qualification), "sha256": mod.digest(self.qualification)}})
        mod.write(self.p.local / "config.json", {"executor": str(self.executor), "platformManifest": str(self.manifest)})

    def submit(self):
        mod.write(self.path, self.order)
        self.p.submit(self.path)
        return json.loads(self.p.get(self.order["id"])["request"])

    def claimed(self):
        order = self.submit()
        with self.p.connect() as con:
            con.execute("UPDATE jobs SET status='running' WHERE id=?", (order["id"],))
        return order

    def test_queued_subject_survives_tool_update_without_new_order_or_executor(self):
        with patch.object(self.p, "executor", side_effect=AssertionError("Origin must not use executor")):
            order = self.submit()
        before = self.p.get(order["id"])["request"]
        self.provider.write_bytes(b"provider2")
        self.qualify()
        self.submit()
        self.assertEqual(before, self.p.get(order["id"])["request"])
        self.assertNotIn("resolvedConfig", order)
        self.assertNotIn("config", order)
        with self.p.connect() as con:
            con.execute("UPDATE jobs SET status='running'")
        plan = self.p.prepare_platform(order)
        self.assertEqual(plan["scenario"]["steps"][0]["assert"], [{"path": "playerLoaded", "equals": True}])
        self.assertIn({"path": str(self.provider), "sha256": mod.digest(self.provider)}, plan["pins"])

    def test_unqualified_tool_replacement_refuses_same_subject(self):
        order = self.claimed()
        self.provider.write_bytes(b"unqualified")
        with self.assertRaisesRegex(ValueError, "qualification pin mismatch"):
            self.p.prepare_platform(order)
        self.assertFalse(self.p.pending())
        self.assertIsNone(self.p.board()[0]["testOutcome"])

    def test_subject_update_still_invalidates_subject_pins(self):
        order = self.submit()
        self.subject.write_bytes(b"changed mod")
        with self.assertRaisesRegex(ValueError, "Pinned input changed"):
            self.p.verify_inputs(order)

    def test_frozen_platform_cannot_be_replaced_or_reprepared(self):
        order = self.claimed()
        plan = self.p.prepare_platform(order)
        self.provider.write_bytes(b"provider2")
        self.qualify()
        with self.assertRaisesRegex(ValueError, "changed after preparation"):
            self.p.prepare_platform(order)
        self.assertEqual(self.p.attempt_plan(order), plan)

    def test_added_executor_code_and_changed_selection_refuse_dispatch(self):
        order = self.claimed()
        self.p.prepare_platform(order)
        (self.executor / "skyrim_autotest/new.py").write_text("# unqualified")
        with self.assertRaisesRegex(ValueError, "inventory changed"):
            self.p.verify_platform(order)
        host = mod.read(self.p.local / "config.json")
        host["executor"] = str(self.root / "other")
        mod.write(self.p.local / "config.json", host)
        with self.assertRaisesRegex(ValueError, "selection changed"):
            self.p.verify_platform(order)

    def test_platform_plan_file_tampering_is_not_retained_as_valid_provenance(self):
        order = self.claimed()
        self.p.prepare_platform(order)
        mod.write(self.p.evidence_dir(order["id"]) / "platform-plan.json", {"altered": True})
        with self.assertRaisesRegex(ValueError, "plan file changed"):
            self.p.verify_platform(order)

    def test_semantics_or_evidence_change_requires_new_qualification(self):
        order = self.claimed()
        manifest = mod.read(self.manifest)
        manifest["operations"]["state.read"]["fields"]["world.ready"] = "other"
        mod.write(self.manifest, manifest)
        with self.assertRaisesRegex(ValueError, "semantics"):
            self.p.prepare_platform(order)
        self.qualify()
        self.evidence.write_text("changed evidence")
        with self.assertRaisesRegex(ValueError, "pin mismatch"):
            self.p.prepare_platform(order)

    def test_missing_capability_is_platform_refusal_not_mod_success(self):
        order = self.claimed()
        self.operations = {}
        self.qualify()
        with self.assertRaisesRegex(ValueError, "Unavailable platform operation"):
            self.p.prepare_platform(order)
        self.assertEqual(self.p.get(order["id"])["status"], "running")
        self.assertFalse(self.p.pending())

    def test_subject_cannot_pin_provider_or_specify_transport(self):
        self.order["config"] = str(self.config)
        with self.assertRaisesRegex(ValueError, "configuration belongs"):
            self.submit()
        self.order.pop("config")
        self.order["inputs"].append({"path": str(self.provider), "sha256": mod.digest(self.provider), "role": "dependency"})
        order = self.claimed()
        with self.assertRaisesRegex(ValueError, "overlap platform tools"):
            self.p.prepare_platform(order)

    def test_tool_changes_do_not_create_subject_progress_or_reset_authority(self):
        order = self.submit()
        fingerprint = contract.subject_identity(order)
        other = copy.deepcopy(order)
        other["id"] = "new-attempt"
        other["cycle"] = {"iteration": 2, "buildId": "unchanged"}
        self.provider.write_bytes(b"provider2")
        self.assertEqual(contract.subject_identity(other), fingerprint)
        self.assertNotEqual(contract.identity(other), contract.identity(order))
        self.assertIsNone(self.p.claim())  # No batch/cycle authority was created.

    def test_dependency_or_fixture_change_is_not_a_changed_subject_build(self):
        order = self.submit()
        changed = copy.deepcopy(order)
        changed["inputs"].append({"path": "dependency", "sha256": "a" * 64, "role": "dependency"})
        self.assertEqual(contract.build_hashes(order), contract.build_hashes(changed))
        changed["inputs"][0]["sha256"] = "b" * 64
        self.assertNotEqual(contract.build_hashes(order), contract.build_hashes(changed))

    def test_worker_refuses_unqualified_platform_before_any_child_or_notification(self):
        self.submit()
        with self.p.connect() as con:
            # Fixture for an already owner-released standard ticket, not live authority.
            con.execute("INSERT INTO released_orders VALUES(?,?)", (self.order["id"], "offline-batch"))
        self.provider.write_bytes(b"unqualified")
        with patch.object(self.p, "check_launch_authorization"), patch.object(mod.subprocess, "run", side_effect=AssertionError("No child may launch")):
            packet = self.p.execute_next()
        self.assertEqual(packet["executionOutcome"], "blocked")
        self.assertIsNone(packet["platformPlanSha256"])
        self.assertFalse(self.p.pending())
        self.assertIsNone(self.p.board()[0]["testOutcome"])

    def test_packet_retains_both_identities_and_pretest_is_not_notified(self):
        order = self.claimed()
        plan = self.p.prepare_platform(order)
        packet = self.p.finish(order["id"], "blocked", "Offline pretest refusal")
        self.assertEqual(packet["subjectOrderSha256"], contract.identity(order))
        self.assertEqual(packet["platformPlanSha256"], contract.identity(plan))
        self.assertIn("platform-plan.json", {Path(p["path"]).name for p in packet["files"]})
        self.assertFalse(self.p.pending())
        self.assertIsNone(self.p.board()[0]["testOutcome"])

    def test_schema1_retains_its_original_provider_pin_enforcement(self):
        self.order.update(schemaVersion=1, mode="assisted", playerSteps=["Observe"],
                          observations=[{"tool": "inspect", "args": {"kind": "state"}}])
        self.order["inputs"] = [{"path": str(self.provider), "sha256": mod.digest(self.provider)}]
        order = self.submit()
        retained = self.p.get(order["id"])["request"]
        self.provider.write_bytes(b"provider2")
        with self.assertRaisesRegex(ValueError, "Pinned input changed"):
            self.p.verify_inputs(order)
        self.assertEqual(retained, self.p.get(order["id"])["request"])

    def test_finite_semantic_steps_reject_raw_commands_and_mutating_poll(self):
        plan = copy.deepcopy(self.order["subjectPlan"])
        step = plan["steps"][0]
        step.update(operation="object.perform", parameters={"request": {"command": "raw backend call"}})
        with self.assertRaisesRegex(ValueError, "Provider command"):
            contract.validate(plan)
        step["parameters"] = {"request": {"object": "subject object", "action": "acquire"}}
        step["poll"] = True
        with self.assertRaisesRegex(ValueError, "read operation"):
            contract.validate(plan)


if __name__ == "__main__":
    unittest.main()

"""Isolated native-session composition, attribution and recovery regression tests."""
import copy
import json
from pathlib import Path
import types
import unittest
from unittest.mock import patch

import polygon as mod
import test_subject_contract as fixtures


class SharedSessionTests(unittest.TestCase):
    setUp = fixtures.SeparationTests.setUp
    qualify = fixtures.SeparationTests.qualify

    def orders(self, count=2, release=True):
        result = []
        for i in range(count):
            order = copy.deepcopy(self.order)
            order['id'] = 'subject-' + str(i)
            order['sourceChat'] = 'origin-' + str(i)
            order['sourceThreadId'] = 'thread-' + str(i)
            path = self.root / (order['id'] + '.json')
            mod.write(path, order)
            self.p.submit(path)
            result.append(json.loads(self.p.get(order['id'])['request']))
        if release:
            quote = 'Run the prepared tests'
            evidence = self.root / 'owner.txt'
            evidence.write_text(quote)
            request = {'schemaVersion': 1, 'id': 'batch-1', 'orderIds': [o['id'] for o in result],
                       'ownerAuthorization': {'threadId': 'owner', 'messageId': 'turn-1', 'quote': quote,
                         'verifiedBy': 'offline-test', 'path': str(evidence), 'sha256': mod.digest(evidence)}}
            path = self.root / 'release.json'
            mod.write(path, request)
            self.p.release_batch(path)
        return result

    def group(self, orders):
        path = self.root / 'session-request.json'
        mod.write(path, {'schemaVersion': 1, 'id': 'session-1', 'orderIds': [o['id'] for o in orders],
                         'compatibility': {'stateIndependent': True, 'verifiedBy': 'offline-test',
                                           'reason': 'Same fixture; read-only independent checks'}})
        return self.p.register_session(path)

    def prepared(self):
        orders = self.orders()
        self.group(orders)
        claimed = self.p.claim_shared()
        self.assertEqual(claimed['orderIds'], [o['id'] for o in orders])
        return orders, self.p.prepare_shared('session-1')

    def native_run(self, plan, checks=None, done=True, restored=True, reason='completed', outcome='passed'):
        run = self.root / 'runtime/runs/shared-run'
        run.mkdir(parents=True, exist_ok=True)
        state = {'id': 'shared-run', 'order': {'id': plan['anchorOrderId']},
                 'scenarioHash': mod.digest(self.p.local / 'sessions/session-1/scenario.json'),
                 'done': done, 'restored': restored, 'restoreErrors': [], 'reason': reason,
                 'result': outcome}
        checks = checks if checks is not None else [{'name': name, 'result': 'passed'} for member in plan['members'] for name in member['checkNames']]
        mod.write(run / 'state.json', state)
        mod.write(run / 'result.json', {**state, 'checks': checks})
        (run / 'steps.jsonl').write_text('')
        return run

    def finalize(self, order):
        packet = mod.read(self.p.get(order['id'])['packet'])
        evidence = next(p for p in packet['files'] if Path(p['path']).name == 'result.json')
        path = self.root / ('report-' + order['id'] + '.json')
        mod.write(path, {'schemaVersion': 1, 'id': 'report-' + order['id'], 'orderIds': [order['id']],
                         'summary': 'Complete verified member evidence', 'collectionFinished': True,
                         'dataCoverage': {order['id']: [{'name': 'state', 'status': 'collected', 'evidence': [evidence]}]}})
        return self.p.report_ready(path)

    def test_two_origins_one_native_call_with_namespaced_scenario_and_replay_refusal(self):
        orders, plan = self.prepared()
        calls = []
        runner = types.ModuleType('skyrim_autotest.runner')
        runner.configure = lambda config: None
        runner.run = lambda profile, scenario, **kw: calls.append((profile, mod.read(scenario), kw)) or 0
        with patch.dict(mod.sys.modules, {'skyrim_autotest': types.ModuleType('skyrim_autotest'), 'skyrim_autotest.runner': runner}), patch.object(self.p, 'source_profile', return_value='Test'):
            self.assertEqual(self.p.child_shared('session-1'), 0)
            with self.assertRaises(Exception):
                self.p.child_shared('session-1')
        self.assertEqual(len(calls), 1)
        self.assertEqual([s['name'] for s in calls[0][1]['steps']], ['m0-0', 'm1-0'])
        with self.p.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 2)
        self.assertEqual(orders[0]['testing']['start']['name'], 'subject-response')

    def test_successful_members_finalize_independently_with_exact_origins(self):
        orders, plan = self.prepared()
        self.native_run(plan)
        self.assertEqual(self.p.reconcile(), [o['id'] for o in orders])
        first = self.finalize(orders[0])
        pending = self.p.pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['threadId'], 'thread-0')
        self.assertEqual(pending[0]['testOutcome'], 'tested_successfully')
        self.p.delivered(orders[0]['id'], 'verified app receipt thread-0')
        self.assertEqual(self.p.get(orders[1]['id'])['status'], 'recorded')
        self.finalize(orders[1])
        self.assertEqual(self.p.pending()[0]['threadId'], 'thread-1')
        self.assertEqual(self.p.reconcile(), [])

    def test_shared_collection_fault_interrupts_started_members_only(self):
        orders, plan = self.prepared()
        checks = [{'name': name, 'result': 'passed'} for name in plan['members'][0]['checkNames']]
        run = self.native_run(plan, checks=checks)
        result = mod.read(run / 'result.json')
        result.update(collectionComplete=False, collectionErrors=[
            {'path': 'SteamVR/vrserver.txt', 'error': 'copy failed', 'segment': 'restart-1'}])
        mod.write(run / 'result.json', result)
        self.p.reconcile()
        for order in orders:
            self.finalize(order)
            findings = mod.read(self.p.evidence_dir(order['id']) / 'self-checks.json')['findings']
            self.assertEqual(findings[0]['kind'], 'evidence_collection_incomplete')
        pending = self.p.pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['threadId'], 'thread-0')
        self.assertEqual(pending[0]['testOutcome'], 'interrupted_external')
        second = next(b for b in self.p.board() if b['id'] == orders[1]['id'])
        self.assertEqual(second['testOutcome'], 'not_started')
        self.assertEqual(second['notificationEligibility'], 'suppressed')

    def test_shared_bootstrap_is_auxiliary_for_each_member_and_unknown_checks_survive(self):
        orders, plan = self.prepared()
        run = self.native_run(plan)
        check = {'name': 'executor bootstrap', 'result': 'passed', 'provenance': {
            'schemaVersion': 1, 'component': 'skyrim-autotest', 'stage': 'bootstrap',
            'role': 'tooling', 'runId': 'shared-run', 'checkId': 'bootstrap-1'}}
        result = mod.read(run / 'result.json')
        result['checks'].append(check)
        result['checks'].append({'name': 'unproven extra check', 'result': 'passed'})
        mod.write(run / 'result.json', result)
        state = mod.read(run / 'state.json')
        state['checks'] = result['checks']
        mod.write(run / 'state.json', state)
        (run / 'steps.jsonl').write_text(mod.json.dumps({'kind': 'executor-check', **check}) + '\n')
        self.p.reconcile()
        for order in orders:
            self.finalize(order)
        for row in self.p.board():
            self.assertEqual(row['testOutcome'], 'incomplete')
            self.assertEqual(row['coverage']['required'], 1)
            self.assertEqual(row['auxiliaryCoverage']['passed'], 1)
            self.assertEqual(row['coverage']['checks'][-1]['role'], 'unknown')

    def test_failure_in_first_member_never_starts_second(self):
        orders, plan = self.prepared()
        self.native_run(plan, [{'name': 'm0-0', 'result': 'failed'}], reason='Assertion failed: m0-0', outcome='failed')
        self.p.reconcile()
        self.finalize(orders[0])
        self.finalize(orders[1])
        self.assertEqual(self.p.pending()[0]['testOutcome'], 'tested_with_errors')
        other = self.p.board()[0]
        self.assertEqual(other['id'], orders[1]['id'])
        self.assertEqual(other['testOutcome'], 'not_started')
        self.assertEqual(other['notificationEligibility'], 'suppressed')

    def test_later_crash_preserves_completed_first_coverage(self):
        orders, plan = self.prepared()
        self.native_run(plan, [{'name': 'm0-0', 'result': 'passed'}, {'name': 'm1-0', 'result': 'failed'}], reason='Game exited unexpectedly', outcome='failed')
        self.p.reconcile()
        self.finalize(orders[0])
        self.finalize(orders[1])
        outcomes = {entry['threadId']: entry['testOutcome'] for entry in self.p.pending()}
        self.assertEqual(outcomes['thread-0'], 'tested_successfully')
        # Failed subject rules remain observations, not a diagnosis of the crash.
        self.assertIn(outcomes['thread-1'], ('tested_with_errors', 'interrupted_external'))

    def test_unrestored_or_running_session_keeps_all_barriers(self):
        orders, plan = self.prepared()
        run = self.native_run(plan, restored=False)
        self.assertEqual(self.p.reconcile(), [])
        self.assertIsNone(self.p.claim())
        self.assertEqual(self.p.get(orders[1]['id'])['status'], 'session_waiting')
        self.assertEqual(self.p.grant_slot()['status'], 'pipeline_held')
        with self.assertRaisesRegex(ValueError, 'Shared members'):
            self.p.finish(orders[0]['id'], 'passed', 'false finish', run, True)
        with self.assertRaisesRegex(ValueError, 'completion'):
            self.p.finish_shared('session-1', run)
        self.assertFalse(self.p.pending())

    def test_registration_does_not_authorize_launch_and_can_be_dissolved(self):
        orders = self.orders(release=False)
        self.group(orders)
        self.assertIsNone(self.p.claim_shared())
        self.assertIsNone(self.p.claim())
        self.assertTrue(self.p.register_session(self.root / 'session-request.json')['duplicate'])
        self.p.cancel_session('session-1')
        self.assertIsNone(self.p.member_session(orders[0]['id']))
        self.assertEqual(self.p.get(orders[0]['id'])['status'], 'queued')

    def test_fifo_intervening_order_is_not_skipped(self):
        orders = self.orders(3)
        self.group([orders[0], orders[2]])
        self.assertEqual(self.p.claim_shared()['status'], 'awaiting_members_or_fifo')
        self.assertIsNone(self.p.claim())
        self.p.cancel_session('session-1')
        self.assertEqual(self.p.claim()['id'], orders[0]['id'])

    def test_pin_fixture_and_manifest_tamper_refuse_before_dispatch(self):
        orders, plan = self.prepared()
        self.subject.write_bytes(b'drift')
        with self.assertRaisesRegex(ValueError, 'Pinned input changed'):
            self.p.verify_shared('session-1')
        self.subject.write_bytes(b'subject')
        mod.write(self.p.local / 'sessions/session-1/session-plan.json', {})
        with self.assertRaisesRegex(ValueError, 'plan changed'):
            self.p.verify_shared('session-1')
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.p.finish_shared('session-1', self.native_run(plan))

    def test_incompatible_profile_rejected_without_claim(self):
        orders = self.orders()
        # Simulate a second separately submitted profile, not a mutation of a live order.
        order = copy.deepcopy(self.order)
        order['id'], order['profile'] = 'different-profile', 'Exclusive'
        path = self.root / 'different-profile.json'
        mod.write(path, order)
        self.p.submit(path)
        with self.assertRaisesRegex(ValueError, 'profile'):
            self.group([orders[0], json.loads(self.p.get(order['id'])['request'])])
        self.assertEqual(self.p.get(orders[0]['id'])['status'], 'queued')

    def test_incompatible_fixture_refuses_whole_session_without_start(self):
        orders = self.orders()
        order = copy.deepcopy(self.order)
        order['id'] = 'different-fixture'
        order['subjectPlan']['fixture']['cell'] = 'OtherCell'
        path = self.root / 'different-fixture.json'
        mod.write(path, order)
        self.p.submit(path)
        # Existing owner batch cannot authorize a later order; use a separately verified release.
        with self.p.connect() as con:
            con.execute('INSERT INTO released_orders VALUES(?,?)', (order['id'], 'batch-1'))
        other = json.loads(self.p.get(order['id'])['request'])
        self.group([orders[0], orders[1], other])
        claimed = self.p.claim_shared()
        with self.assertRaisesRegex(ValueError, 'fixture'):
            self.p.prepare_shared(claimed['id'])
        self.p.finish_shared(claimed['id'], reason='Incompatible fixture')
        self.assertFalse(self.p.pending())
        self.assertTrue(all(self.p.get(o['id'])['status'] == 'blocked' for o in [*orders, other]))

    def test_shared_postcompletion_tamper_blocks_report_and_delivery(self):
        orders, plan = self.prepared()
        run = self.native_run(plan)
        self.p.reconcile()
        self.finalize(orders[0])
        (run / 'result.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'manifest mismatch'):
            self.p.pending()

    def test_child_rechecks_authority_for_every_member(self):
        orders, plan = self.prepared()
        (self.root / 'owner.txt').write_text('authority changed')
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.p.child_shared('session-1')
        with self.p.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 0)

    def test_normal_next_uses_one_shared_child_and_retains_two_packets(self):
        orders = self.orders()
        self.group(orders)
        def child(*args, **kw):
            plan = self.p.verify_shared('session-1')
            self.native_run(plan)
            return types.SimpleNamespace(returncode=0)
        with patch('shared_sessions.subprocess.run', side_effect=child) as call:
            result = self.p.execute_next()
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result['status'], 'complete')
        self.assertTrue(all(self.p.get(o['id'])['packet'] for o in orders))
        self.assertFalse(self.p.pending())
        self.assertEqual(self.p.execute_next()['status'], 'idle_or_busy')

    def test_partial_finalization_resumes_without_launch_or_packet_rewrite(self):
        orders, plan = self.prepared()
        self.native_run(plan)
        original = self.p.finish
        def interrupted(job, *args, **kw):
            if job == orders[0]['id']:
                raise OSError('simulated collection crash')
            return original(job, *args, **kw)
        with patch.object(self.p, 'finish', side_effect=interrupted):
            with self.assertRaises(OSError):
                self.p.reconcile()
        packet = Path(self.p.get(orders[1]['id'])['packet'])
        pin = mod.digest(packet)
        self.assertIsNone(self.p.claim())
        self.p.reconcile()
        self.assertEqual(pin, mod.digest(packet))
        self.assertEqual(self.p.session_show('session-1')['status'], 'complete')


    def test_interrupted_preparation_recovers_without_frozen_platform_or_runner(self):
        orders = self.orders()
        self.group(orders)
        self.p.claim_shared()
        result = self.p.recover_active()
        self.assertEqual(result['status'], 'complete')
        self.assertFalse(self.p.pending())

    def test_finalizing_barrier_blocks_install_without_running_anchor(self):
        orders, plan = self.prepared()
        with self.p.connect() as con:
            con.execute("UPDATE game_sessions SET status='finalizing'")
            con.execute("UPDATE jobs SET status='recorded' WHERE status='running'")
        self.assertEqual(self.p.grant_slot()['status'], 'game_busy')
        self.assertIsNone(self.p.claim())

    def test_legacy_generic_sessions_preserve_requests(self):
        self.orders()
        scenario = {'schemaVersion': 1, 'cell': 'QASmoke', 'steps': [
            {'name': 'response', 'tool': 'inspect', 'args': {'kind': 'state'}, 'assert': [{'path': 'ready', 'equals': True}]}]}
        legacy = []
        for index in range(2):
            order = {'schemaVersion': 1, 'id': 'legacy-' + str(index), 'mode': 'automatic',
                     'sourceChat': 'legacy-' + str(index), 'sourceThreadId': 'legacy-thread-' + str(index),
                     'profile': 'Test', 'subject': 'Legacy subject', 'purpose': 'Check', 'collect': ['state'],
                     'inputs': [{'path': str(self.subject), 'sha256': mod.digest(self.subject)}],
                     'config': str(self.config), 'scenario': str(self.root / 'legacy-scenario.json'),
                     'testing': {'start': {'kind': 'check', 'name': 'response'}, 'checks': [{'name': 'response', 'role': 'subject'}]}}
            mod.write(self.root / 'legacy-scenario.json', scenario)
            path = self.root / ('legacy-' + str(index) + '.json')
            mod.write(path, order)
            self.p.submit(path)
            legacy.append(json.loads(self.p.get(order['id'])['request']))
        with self.p.connect() as con:
            con.execute("DELETE FROM jobs WHERE id LIKE 'subject-%'")
            for order in legacy:
                con.execute('INSERT INTO released_orders VALUES(?,?)', (order['id'], 'batch-1'))
        self.group(legacy)
        self.p.claim_shared()
        before = [self.p.get(o['id'])['request'] for o in legacy]
        plan = self.p.prepare_shared('session-1')
        self.native_run(plan)
        self.p.reconcile()
        self.assertEqual(before, [self.p.get(o['id'])['request'] for o in legacy])
        self.finalize(legacy[1])
        self.assertEqual(self.p.pending()[0]['threadId'], 'legacy-thread-1')


if __name__ == '__main__':
    unittest.main()

"""Tool-only retry regression checks; no live queue/game is used."""
import copy
import json
from pathlib import Path
import types
import unittest
from unittest.mock import patch

import polygon as mod
import test_subject_contract as fixtures
import test_shared_sessions as shared_fixtures


class ToolingRetryTests(unittest.TestCase):
    setUp = fixtures.SeparationTests.setUp
    qualify = fixtures.SeparationTests.qualify

    def predecessor(self, checks=None, restored=True):
        mod.write(self.path, self.order)
        self.p.submit(self.path)
        with self.p.connect() as con:
            con.execute("UPDATE jobs SET status='running'")
        order = json.loads(self.p.get(self.order['id'])['request'])
        plan = self.p.prepare_platform(order)
        folder = self.p.evidence_dir(order['id'])
        mod.write(folder / 'config.json', plan['configuration'])
        mod.write(folder / 'scenario.json', plan['scenario'])
        run = self.root / 'runtime/runs/previous'
        run.mkdir(parents=True)
        state = {'id': 'previous', 'order': {'id': order['id']}, 'done': True, 'restored': restored,
                 'restoreErrors': [], 'result': 'failed', 'reason': 'Tool setup failed before subject',
                 'scenarioHash': mod.digest(folder / 'scenario.json')}
        mod.write(run / 'state.json', state)
        mod.write(run / 'result.json', {**state, 'checks': checks or []})
        (run / 'steps.jsonl').write_text('')
        self.p.finish(order['id'], 'failed', state['reason'], run, restored)
        self.original = {str(p): mod.digest(p) for p in folder.iterdir() if p.is_file()}
        return order, run

    def ticket(self, checks=None, restored=True):
        order, run = self.predecessor(checks, restored)
        return self.ticket_for(order, run, restored)

    def ticket_for(self, order, run, restored=True):
        packet = Path(self.p.get(order['id'])['packet'])
        abort_path = self.root / 'abort.json'
        mod.write(abort_path, {'orderId': order['id'], 'classification': 'confirmed-tooling-pretest-abort',
                              'subjectStarted': False, 'done': True, 'restored': restored, 'restoreErrors': [],
                              'packetSha256': mod.digest(packet), 'reason': 'Verified tooling setup issue', 'run': str(run)})
        quote = 'Continue the current subject after repairing tools'
        evidence = self.root / 'owner.txt'
        evidence.write_text(quote)
        authority_path = self.root / 'authority.json'
        mod.write(authority_path, {'schemaVersion': 1, 'state': 'active', 'orderIds': [order['id']],
            'ownerAuthorization': {'threadId': 'owner', 'messageId': 'turn-1', 'quote': quote,
              'path': str(evidence), 'sha256': mod.digest(evidence), 'verifiedBy': 'offline-test'}})
        # Fresh exact qualification while retaining the original per-order plan/packet.
        self.provider.write_bytes(b'provider-repaired')
        self.qualify()
        ticket = {'schemaVersion': 1, 'id': 'retry-1', 'orderId': order['id'],
                  'previousPacketSha256': mod.digest(packet),
                  'technicalAbort': {'path': str(abort_path), 'sha256': mod.digest(abort_path)},
                  'ownerAuthority': {'path': str(authority_path), 'sha256': mod.digest(authority_path)},
                  'platform': {'path': str(self.manifest), 'sha256': mod.digest(self.manifest)},
                  'authorityReview': {'verifiedBy': 'offline-test', 'reason': 'One scoped existing-owner-authorized tooling retry',
                                      'retryPermitted': True, 'maxAdditionalAttempts': 1, 'cumulativeActualLaunchesBefore': 34}}
        path = self.root / 'retry.json'
        mod.write(path, ticket)
        return order, ticket, path

    def claimed(self):
        order, ticket, path = self.ticket()
        self.p.register_retry(path)
        self.p.claim_retry()
        plan = self.p.prepare_platform(order, attempt_id=ticket['id'])
        folder = self.p.local / 'retry-attempts' / ticket['id']
        mod.write(folder / 'attempt-request.json', ticket)
        mod.write(folder / 'config.json', plan['configuration'])
        mod.write(folder / 'scenario.json', plan['scenario'])
        return order, ticket, plan

    def native(self, ticket, checks=None, restored=True):
        folder = self.p.local / 'retry-attempts' / ticket['id']
        run = self.root / 'runtime/runs/new-retry'
        run.mkdir(parents=True)
        state = {'id': 'new-retry', 'order': {'id': ticket['id'], 'subjectOrderId': ticket['orderId']},
                 'done': True, 'restored': restored, 'restoreErrors': [], 'result': 'passed', 'reason': 'completed',
                 'scenarioHash': mod.digest(folder / 'scenario.json')}
        mod.write(run / 'state.json', state)
        mod.write(run / 'result.json', {**state, 'checks': checks if checks is not None else [{'name': 'subject-response', 'result': 'passed'}]})
        (run / 'steps.jsonl').write_text('')
        return run

    def final(self, ticket, include_data=True):
        row = self.p.retry_show(ticket['id'])
        packet = mod.read(row['packet'])
        ref = next(p for p in packet['files'] if Path(p['path']).name == 'result.json')
        request = {'schemaVersion': 1, 'id': 'retry-final', 'attemptId': ticket['id'],
                   'summary': 'Verified completed attempt', 'collectionFinished': True}
        if include_data:
            request['dataCoverage'] = [{'name': 'state', 'status': 'collected', 'evidence': [ref]}]
        path = self.root / 'report.json'
        mod.write(path, request)
        return self.p.report_ready(path)

    def test_register_dedup_preserves_subject_and_all_old_evidence(self):
        order, ticket, path = self.ticket()
        before = self.p.get(order['id'])['request']
        self.p.register_retry(path)
        self.assertTrue(self.p.register_retry(path)['duplicate'])
        self.assertEqual(self.p.get(order['id'])['request'], before)
        self.assertEqual(self.original, {p: mod.digest(p) for p in self.original})
        self.assertEqual(self.p.get(order['id'])['status'], 'recorded')
        with self.p.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)

    def test_started_subject_or_unrestored_failure_is_not_tooling_retry(self):
        order, ticket, path = self.ticket(checks=[{'name': 'subject-response', 'result': 'failed'}])
        with self.assertRaisesRegex(ValueError, 'pre-subject'):
            self.p.register_retry(path)

    def test_unrestored_predecessor_refuses(self):
        order, ticket, path = self.ticket(restored=False)
        with self.assertRaisesRegex(ValueError, 'restoration'):
            self.p.register_retry(path)

    def test_owner_permission_scope_and_proof_drift_refuse(self):
        order, ticket, path = self.ticket()
        ticket['authorityReview']['retryPermitted'] = False
        mod.write(path, ticket)
        with self.assertRaisesRegex(ValueError, 'permission'):
            self.p.register_retry(path)
        ticket['authorityReview']['retryPermitted'] = True
        mod.write(path, ticket)
        (self.root / 'owner.txt').write_text('revoked evidence')
        with self.assertRaisesRegex(ValueError, 'evidence'):
            self.p.register_retry(path)

    def test_second_ticket_cannot_branch_or_reopen_old_attempt(self):
        order, ticket, path = self.ticket()
        self.p.register_retry(path)
        ticket['id'] = 'retry-2'
        mod.write(path, ticket)
        with self.assertRaisesRegex(ValueError, 'nonbranching'):
            self.p.register_retry(path)
        self.assertEqual(self.p.get(order['id'])['status'], 'recorded')

    def test_native_once_replay_refuses_and_old_files_unchanged(self):
        order, ticket, plan = self.claimed()
        runner = types.ModuleType('skyrim_autotest.runner')
        runner.configure = lambda config: None
        calls = []
        runner.run = lambda *args, **kw: calls.append((args, kw)) or 0
        with patch.dict(mod.sys.modules, {'skyrim_autotest': types.ModuleType('skyrim_autotest'), 'skyrim_autotest.runner': runner}), patch.object(self.p, 'source_profile', return_value='Test') as profile:
            self.assertEqual(self.p.child_retry(ticket['id']), 0)
            with self.assertRaises(Exception):
                self.p.child_retry(ticket['id'])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]['order']['id'], ticket['id'])
        self.assertEqual(calls[0][1]['order']['subjectOrderId'], order['id'])
        self.assertEqual(profile.call_args.kwargs['output_dir'], self.p.local / 'retry-attempts' / ticket['id'])
        self.assertEqual(self.original, {p: mod.digest(p) for p in self.original})

    def test_retry_result_routes_exact_origin_and_retains_original_packet(self):
        order, ticket, plan = self.claimed()
        self.native(ticket)
        self.p.reconcile()
        result = self.final(ticket)
        self.assertEqual(result['eligibility'], 'eligible')
        pending = self.p.pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual((pending[0]['orderId'], pending[0]['attemptId'], pending[0]['threadId']), (order['id'], ticket['id'], order['sourceThreadId']))
        self.assertEqual(pending[0]['testOutcome'], 'tested_successfully')
        self.p.delivered(ticket['id'], 'verified exact-origin app receipt')
        self.assertFalse(self.p.pending())
        self.assertTrue(self.p.delivered(ticket['id'], 'second receipt')['duplicate'])
        self.assertEqual(self.original, {p: mod.digest(p) for p in self.original})

    def test_retry_pretest_abort_suppresses_origin_and_cannot_be_delivered(self):
        order, ticket, plan = self.claimed()
        run = self.native(ticket, checks=[])
        state = mod.read(run / 'state.json')
        state['result'], state['reason'] = 'failed', 'tooling abort'
        mod.write(run / 'state.json', state)
        self.p.reconcile()
        self.assertEqual(self.final(ticket)['eligibility'], 'suppressed')
        self.assertFalse(self.p.pending())
        with self.assertRaisesRegex(ValueError, 'cannot notify'):
            self.p.delivered(ticket['id'], 'false receipt')

    def test_input_platform_or_materialized_drift_refuses_child(self):
        order, ticket, plan = self.claimed()
        mod.write(self.p.local / 'retry-attempts' / ticket['id'] / 'scenario.json', {})
        with self.assertRaisesRegex(ValueError, 'Materialized'):
            self.p.child_retry(ticket['id'])
        mod.write(self.p.local / 'retry-attempts' / ticket['id'] / 'scenario.json', plan['scenario'])
        self.subject.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Pinned input'):
            self.p.child_retry(ticket['id'])

    def test_active_retry_blocks_ordinary_shared_and_install_dispatch(self):
        order, ticket, plan = self.claimed()
        self.assertIsNone(self.p.claim())
        self.assertTrue(self.p.claim_shared()['busy'])
        self.assertEqual(self.p.grant_slot()['status'], 'game_busy')
        self.assertFalse(self.p.pending())

    def test_normal_next_dispatches_retry_once_with_fresh_platform(self):
        order, ticket, path = self.ticket()
        self.p.register_retry(path)
        def child(*args, **kw):
            self.native(ticket)
            return types.SimpleNamespace(returncode=0)
        with patch('tooling_retries.subprocess.run', side_effect=child) as native:
            packet = self.p.execute_next()
        self.assertEqual(native.call_count, 1)
        self.assertEqual(packet['attemptId'], ticket['id'])
        self.assertEqual(self.p.execute_next()['status'], 'idle_or_busy')
        self.assertEqual(self.original, {p: mod.digest(p) for p in self.original})

    def test_unproven_worker_cannot_release_retry_barrier(self):
        order, ticket, plan = self.claimed()
        with self.p.connect() as con:
            con.execute('INSERT INTO attempts VALUES(?,?)', (ticket['id'], 1))
        self.assertEqual(self.p.recover_active()['status'], 'worker_completion_unproven')
        self.assertEqual(self.p.retry_show(ticket['id'])['status'], 'running')

    def test_interrupted_preparation_is_closed_without_dispatch(self):
        order, ticket, path = self.ticket()
        self.p.register_retry(path)
        self.p.claim_retry()
        packet = self.p.recover_active()
        self.assertEqual(packet['executionOutcome'], 'blocked')
        self.assertEqual(self.p.retry_show(ticket['id'])['status'], 'blocked')


    def test_unstarted_shared_member_retries_without_replaying_other_members(self):
        members = shared_fixtures.SharedSessionTests.orders(self)
        shared_fixtures.SharedSessionTests.group(self, members)
        self.p.claim_shared()
        plan = self.p.prepare_shared('session-1')
        run = shared_fixtures.SharedSessionTests.native_run(self, plan, checks=[{'name': 'm0-0', 'result': 'failed'}],
                                                         reason='Tool request failed before member2', outcome='failed')
        self.p.reconcile()
        order, ticket, path = self.ticket_for(members[1], run)
        first_packet = self.p.get(members[0]['id'])['packet']
        first_sha = mod.digest(first_packet)
        self.p.register_retry(path)
        self.assertEqual(self.p.claim_retry()['order_id'], members[1]['id'])
        self.assertEqual(first_sha, mod.digest(first_packet))
        self.assertEqual(self.p.session_show('session-1')['status'], 'complete')
        self.assertEqual(self.p.get(members[0]['id'])['status'], 'recorded')

    def test_unqualified_repair_and_late_platform_drift_refuse(self):
        order, ticket, path = self.ticket()
        self.p.register_retry(path)
        row = self.p.claim_retry()
        self.provider.write_bytes(b'unqualified-late-drift')
        packet = self.p.execute_retry(row)
        self.assertEqual(packet['executionOutcome'], 'blocked')
        self.assertFalse(self.p.pending())
        self.assertEqual(self.p.get(order['id'])['status'], 'recorded')


if __name__ == '__main__':
    unittest.main()

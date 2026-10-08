"""Reviewed post-start replays preserve immutable subjects, prior results and launch counts."""
import copy
import json
from pathlib import Path
import time
import types
import unittest
from unittest.mock import patch

import polygon as mod
import test_tooling_retries as fixtures


class PostStartTests(unittest.TestCase):
    setUp = fixtures.ToolingRetryTests.setUp
    qualify = fixtures.ToolingRetryTests.qualify

    def games(self, run, count=6):
        state = mod.read(run / 'state.json')
        identities = [{'pid': 100 + i, 'birth': 1000 + i, 'path': 'C:/Game/SkyrimVR.exe'} for i in range(count)]
        state.update(owned=[{'role': 'game', 'identity': g} for g in identities],
                     game=identities[-1], ownedGameRestartCount=count - 1)
        mod.write(run / 'state.json', state)

    def ticket(self):
        first = copy.deepcopy(self.order['subjectPlan']['steps'][0])
        first['name'] = 'late-check'
        self.order['subjectPlan']['steps'].append(first)
        self.order['testing']['checks'].append({'name': 'late-check', 'role': 'subject'})
        reason = 'Tool request failed: Timed publication exceeded motion budget'
        checks = [{'name': 'subject-response', 'result': 'passed'},
                  {'name': 'late-check', 'result': 'failed', 'observation': None, 'reason': reason}]
        original_finish = self.p.finish
        def finish(job, outcome, note, run, restored):
            self.games(run)
            return original_finish(job, outcome, note, run, restored)
        with patch.object(self.p, 'finish', side_effect=finish):
            order, run = fixtures.ToolingRetryTests.predecessor(self, checks)
        report_request = self.root / 'predecessor-report.json'
        mod.write(report_request, {'schemaVersion': 1, 'id': 'predecessor-final', 'orderIds': [order['id']],
                                  'summary': 'Ended, restored, evidence reviewed', 'collectionFinished': True})
        report = self.p.report_ready(report_request)
        self.p.delivered(order['id'], 'Actual exact-origin fixture receipt')
        self.old_report = Path(report['report'])
        self.old_report_sha = mod.digest(self.old_report)
        order, ticket, path = fixtures.ToolingRetryTests.ticket_for(self, order, run)
        ticket.pop('technicalAbort')
        ticket.update(kind='post-start-tooling', restartMode='initial-fixture', id='continuation-1',
                      previousReport={'path': str(self.old_report), 'sha256': self.old_report_sha})
        ticket['authorityReview'].update(cumulativeActualLaunchesBefore=161,
            postStartContinuationPermitted=True, fullReplayReviewed=True, preservePriorCoverage=True)
        failure_path = self.root / 'failure.json'
        mod.write(failure_path, {'schemaVersion': 1, 'classification': 'confirmed-tooling-post-start-failure',
            'orderId': order['id'], 'subjectStarted': True, 'done': True, 'restored': True, 'restoreErrors': [],
            'collectionFinished': True, 'packetSha256': ticket['previousPacketSha256'],
            'reportSha256': ticket['previousReport']['sha256'], 'run': str(run),
            'reason': 'Reviewed confirmed executor request failure; no mod reauthoring', 'verifiedBy': 'offline-test',
            'failedCheck': {'name': 'late-check', 'reason': reason},
            'evidence': [{'path': str(run / name), 'sha256': mod.digest(run / name)} for name in ('state.json', 'result.json')]})
        ticket['technicalFailure'] = {'path': str(failure_path), 'sha256': mod.digest(failure_path)}
        accounting = self.root / 'launch-accounting.json'
        mod.write(accounting, {'schemaVersion': 1, 'orderId': order['id'],
            'previousPacketSha256': ticket['previousPacketSha256'], 'previousAttemptActualLaunches': 6,
            'cumulativeActualLaunches': 161, 'verifiedBy': 'offline-test',
            'reason': 'Reviewed cumulative actual starts, including prior initial run and five restarts'})
        ticket['launchAccounting'] = {'path': str(accounting), 'sha256': mod.digest(accounting)}
        mod.write(path, ticket)
        return order, ticket, path

    def claimed(self):
        order, ticket, path = self.ticket()
        self.p.register_continuation(path)
        self.p.claim_retry()
        plan = self.p.prepare_platform(order, attempt_id=ticket['id'])
        folder = self.p.local / 'retry-attempts' / ticket['id']
        mod.write(folder / 'attempt-request.json', ticket)
        mod.write(folder / 'config.json', plan['configuration'])
        mod.write(folder / 'scenario.json', plan['scenario'])
        self.p.freeze_continuation_review(ticket, folder)
        return order, ticket, plan

    def native(self, ticket, complete=True):
        checks = [{'name': 'subject-response', 'result': 'passed'}]
        if complete:
            checks.append({'name': 'late-check', 'result': 'passed'})
        run = fixtures.ToolingRetryTests.native(self, ticket, checks)
        self.games(run, count=2)
        return run

    final = fixtures.ToolingRetryTests.final

    def test_delivered_started_predecessor_registers_separate_attempt_without_reopening(self):
        order, ticket, path = self.ticket()
        original = self.p.get(order['id'])
        self.p.register_continuation(path)
        self.assertTrue(self.p.register_continuation(path)['duplicate'])
        self.assertEqual(self.p.get(order['id']), original)
        self.assertEqual(mod.digest(self.old_report), self.old_report_sha)
        self.assertEqual(self.original, {p: mod.digest(p) for p in self.original})
        with self.p.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)
        self.assertEqual(self.p.retry_show(ticket['id'])['status'], 'queued')

    def test_old_pretest_command_cannot_accept_poststart_ticket(self):
        _, _, path = self.ticket()
        with self.assertRaisesRegex(ValueError, 'Invalid tooling continuation'):
            self.p.register_retry(path)

    def test_full_replay_preserves_every_step_fixture_and_current_attempt_only_success(self):
        order, ticket, plan = self.claimed()
        self.assertEqual([s['name'] for s in plan['scenario']['steps']], [s['name'] for s in order['subjectPlan']['steps']])
        self.assertEqual(plan['scenario']['cell'], order['subjectPlan']['fixture']['cell'])
        self.assertFalse(self.p.pending_retries())
        run = self.native(ticket)
        packet = self.p.finish_retry(ticket['id'], run)
        self.assertEqual(packet['launchAccounting']['attemptActualLaunches'], 2)
        self.assertEqual(packet['launchAccounting']['cumulativeActualLaunchesBefore'], 161)
        self.assertEqual(packet['launchAccounting']['cumulativeActualLaunchesAfter'], 163)
        self.final(ticket)
        final = mod.read(self.p.retry_show(ticket['id'])['report'])
        self.assertEqual(final['launchAccounting'], packet['launchAccounting'])
        board = self.p.retry_board()[0]
        self.assertEqual(board['attemptKind'], 'post_start_tooling')
        self.assertEqual(board['launchAccounting']['cumulativeActualLaunchesAfter'], 163)
        message, = self.p.pending_retries()
        self.assertEqual(message['threadId'], order['sourceThreadId'])
        self.assertEqual(message['testOutcome'], 'tested_successfully')
        self.assertEqual(self.original, {p: mod.digest(p) for p in self.original})
        self.assertEqual(mod.digest(self.old_report), self.old_report_sha)

    def test_earlier_pass_cannot_fill_missing_checks_in_later_attempt(self):
        _, ticket, _ = self.claimed()
        run = self.native(ticket, complete=False)
        self.p.finish_retry(ticket['id'], run)
        self.final(ticket)
        report = mod.read(self.p.retry_show(ticket['id'])['report'])
        self.assertEqual(report['testResult']['outcome'], 'incomplete')
        self.assertEqual(report['testResult']['coverage']['not_run'], 1)

    def test_subject_failure_or_unrelated_proof_alone_cannot_qualify(self):
        _, ticket, path = self.ticket()
        proof = mod.read(ticket['technicalFailure']['path'])
        for failure in (None, {'name': 'late-check', 'reason': 'Assertion failed: late-check'},
                        {'name': 'foreign-check', 'reason': proof['failedCheck']['reason']}):
            proof['failedCheck'] = failure
            mod.write(ticket['technicalFailure']['path'], proof)
            ticket['technicalFailure']['sha256'] = mod.digest(ticket['technicalFailure']['path'])
            mod.write(path, ticket)
            with self.subTest(failure=failure), self.assertRaisesRegex(ValueError, 'No corroborated'):
                self.p.register_continuation(path)

    def test_review_must_explicitly_allow_poststart_full_replay_and_preserve_coverage(self):
        _, ticket, path = self.ticket()
        for key in ('postStartContinuationPermitted', 'fullReplayReviewed', 'preservePriorCoverage'):
            invalid = copy.deepcopy(ticket)
            invalid['authorityReview'][key] = False
            mod.write(path, invalid)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'reviewed full post-start'):
                self.p.register_continuation(path)
        ticket['restartMode'] = 'skip-passed-checks'
        mod.write(path, ticket)
        with self.assertRaisesRegex(ValueError, 'initial fixture'):
            self.p.register_continuation(path)

    def test_wrong_report_native_pins_or_accounting_refuses(self):
        _, ticket, path = self.ticket()
        for key in ('previousReport', 'technicalFailure', 'launchAccounting'):
            invalid = copy.deepcopy(ticket)
            invalid[key]['sha256'] = '0' * 64
            mod.write(path, invalid)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'pin changed'):
                self.p.register_continuation(path)
        ticket['authorityReview']['cumulativeActualLaunchesBefore'] = 0
        mod.write(path, ticket)
        with self.assertRaisesRegex(ValueError, 'cumulative physical'):
            self.p.register_continuation(path)

    def test_missing_current_owner_or_expired_authority_refuses(self):
        _, ticket, path = self.ticket()
        authority_path = Path(ticket['ownerAuthority']['path'])
        original = mod.read(authority_path)
        for change in ({'state': 'cancelled'}, {'deadlineUtc': time.time() - 1}, {'ownerAuthorization': {}}):
            mod.write(authority_path, {**original, **change})
            ticket['ownerAuthority']['sha256'] = mod.digest(authority_path)
            mod.write(path, ticket)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.p.register_continuation(path)

    def test_hold_is_not_cleared_and_pending_attempt_cannot_branch(self):
        _, ticket, path = self.ticket()
        self.p.hold_pipeline('shared-tool-fault', 'Owner-reviewed qualification pending')
        self.p.register_continuation(path)
        self.assertIsNone(self.p.claim_retry())
        self.assertTrue(self.p.pipeline_status()['holds'])
        ticket['id'] = 'continuation-2'
        mod.write(path, ticket)
        with self.assertRaisesRegex(ValueError, 'nonbranching chain'):
            self.p.register_continuation(path)

    def test_child_admitted_once_and_revalidates_immutable_full_plan(self):
        order, ticket, plan = self.claimed()
        runner = types.ModuleType('skyrim_autotest.runner')
        runner.configure = lambda config: None
        calls = []
        runner.run = lambda *a, **kw: calls.append(kw) or 0
        with patch.dict(mod.sys.modules, {'skyrim_autotest': types.ModuleType('skyrim_autotest'), 'skyrim_autotest.runner': runner}), \
             patch.object(self.p, 'source_profile', return_value='Test'):
            self.assertEqual(self.p.child_retry(ticket['id']), 0)
            with self.assertRaises(Exception):
                self.p.child_retry(ticket['id'])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['order']['id'], ticket['id'])
        self.assertEqual(calls[0]['order']['subjectOrderId'], order['id'])
        with self.p.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 1)

    def test_unknown_actual_launches_or_pending_restoration_retains_barrier(self):
        _, ticket, _ = self.claimed()
        run = self.native(ticket)
        state = mod.read(run / 'state.json')
        state['owned'] = []
        mod.write(run / 'state.json', state)
        with self.assertRaisesRegex(ValueError, 'accounting is unproven'):
            self.p.finish_retry(ticket['id'], run)
        self.assertEqual(self.p.retry_show(ticket['id'])['status'], 'running')
        self.games(run, 2)
        state = mod.read(run / 'state.json')
        state['restored'] = False
        mod.write(run / 'state.json', state)
        self.assertFalse(self.p.reconcile_retries())
        self.assertEqual(self.p.retry_show(ticket['id'])['status'], 'running')
        self.assertTrue(self.p.pipeline_status()['holds'])

    def test_preparation_without_dispatch_preserves_baseline_and_zero_starts(self):
        _, ticket, path = self.ticket()
        self.p.register_continuation(path)
        self.p.claim_retry()
        packet = self.p.recover_active()
        self.assertEqual(packet['launchAccounting']['attemptActualLaunches'], 0)
        self.assertEqual(packet['launchAccounting']['cumulativeActualLaunchesAfter'], 161)
        self.assertFalse(self.p.pending_retries())

    def test_factual_start_and_proof_fields_are_not_inferred_from_review_labels(self):
        _, ticket, path = self.ticket()
        original = mod.read(ticket['technicalFailure']['path'])
        for change in ({'subjectStarted': False}, {'done': False}, {'restored': False},
                       {'restoreErrors': ['pending recovery']}, {'packetSha256': '0' * 64},
                       {'reportSha256': '0' * 64}, {'evidence': original['evidence'][:1]}):
            mod.write(ticket['technicalFailure']['path'], {**original, **change})
            ticket['technicalFailure']['sha256'] = mod.digest(ticket['technicalFailure']['path'])
            mod.write(path, ticket)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.p.register_continuation(path)

    def test_repair_platform_drift_refuses_without_launching_or_resetting_counts(self):
        _, ticket, path = self.ticket()
        self.p.register_continuation(path)
        row = self.p.claim_retry()
        self.provider.write_bytes(b'unqualified repair bytes')
        packet = self.p.execute_retry(row)
        self.assertEqual(packet['executionOutcome'], 'blocked')
        self.assertEqual(packet['launchAccounting']['cumulativeActualLaunchesAfter'], 161)
        with self.p.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 0)

    def test_cancellation_at_final_dispatch_gate_prevents_admission(self):
        _, ticket, _ = self.claimed()
        runner = types.ModuleType('skyrim_autotest.runner')
        runner.configure = lambda config: None
        runner.run = lambda *a, **kw: self.fail('Cancelled authority cannot launch')
        def cancel(*args, **kwargs):
            authority = Path(ticket['ownerAuthority']['path'])
            value = mod.read(authority)
            value['state'] = 'cancelled'
            mod.write(authority, value)
            return 'Test'
        with patch.dict(mod.sys.modules, {'skyrim_autotest': types.ModuleType('skyrim_autotest'), 'skyrim_autotest.runner': runner}), \
             patch.object(self.p, 'source_profile', side_effect=cancel):
            with self.assertRaisesRegex(ValueError, 'pin changed'):
                self.p.child_retry(ticket['id'])
        with self.p.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 0)

    def test_frozen_review_corruption_refuses_even_before_packet_creation(self):
        _, ticket, _ = self.claimed()
        run = self.native(ticket)
        path = self.p.local / 'retry-attempts' / ticket['id'] / 'review-ownerAuthority.json'
        value = mod.read(path)
        value['documentText'] = '{}'
        mod.write(path, value)
        with self.assertRaisesRegex(ValueError, 'review bytes'):
            self.p.finish_retry(ticket['id'], run)
        self.assertIsNone(self.p.retry_show(ticket['id'])['packet'])

    def test_dispatch_without_native_evidence_cannot_be_accounted_as_zero(self):
        _, ticket, _ = self.claimed()
        with self.p.connect() as con:
            con.execute('INSERT INTO attempts VALUES(?,?)', (ticket['id'], time.time()))
        with self.assertRaisesRegex(ValueError, 'accounting is unproven'):
            self.p.finish_retry(ticket['id'], reason='Missing native lifecycle')
        self.assertEqual(self.p.retry_show(ticket['id'])['status'], 'running')

    def test_late_scenario_truncation_cannot_skip_the_original_prefix(self):
        _, ticket, _ = self.claimed()
        runner = types.ModuleType('skyrim_autotest.runner')
        runner.configure = lambda config: None
        runner.run = lambda *a, **kw: self.fail('Truncated scenario cannot launch')
        def truncate(*args, **kwargs):
            path = self.p.local / 'retry-attempts' / ticket['id'] / 'scenario.json'
            scenario = mod.read(path)
            scenario['steps'] = scenario['steps'][1:]
            mod.write(path, scenario)
            return 'Test'
        with patch.dict(mod.sys.modules, {'skyrim_autotest': types.ModuleType('skyrim_autotest'), 'skyrim_autotest.runner': runner}), \
             patch.object(self.p, 'source_profile', side_effect=truncate):
            with self.assertRaisesRegex(ValueError, 'Full continuation plan changed'):
                self.p.child_retry(ticket['id'])
        with self.p.connect() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 0)

    def test_chained_poststart_attempt_cannot_reset_prior_actual_starts(self):
        order, ticket, _ = self.claimed()
        run = self.native(ticket)
        result = mod.read(run / 'result.json')
        reason = 'Tool request failed: another proven tooling request failure'
        result['checks'][-1].update(result='failed', reason=reason, observation=None)
        result['result'] = 'failed'
        mod.write(run / 'result.json', result)
        state = mod.read(run / 'state.json')
        state.update(result='failed', reason=reason)
        mod.write(run / 'state.json', state)
        packet = self.p.finish_retry(ticket['id'], run)
        self.final(ticket)
        previous = self.p.retry_show(ticket['id'])
        successor = copy.deepcopy(ticket)
        successor.update(id='continuation-2', previousAttemptId=ticket['id'],
            previousPacketSha256=mod.digest(previous['packet']),
            previousReport={'path': previous['report'], 'sha256': previous['report_sha']})
        proof = mod.read(ticket['technicalFailure']['path'])
        proof.update(attemptId=ticket['id'], packetSha256=successor['previousPacketSha256'],
            reportSha256=successor['previousReport']['sha256'], run=str(run),
            failedCheck={'name': 'late-check', 'reason': reason},
            evidence=[{'path': str(run / name), 'sha256': mod.digest(run / name)} for name in ('state.json', 'result.json')])
        proof_path = self.root / 'successor-failure.json'
        mod.write(proof_path, proof)
        successor['technicalFailure'] = {'path': str(proof_path), 'sha256': mod.digest(proof_path)}
        accounting = mod.read(ticket['launchAccounting']['path'])
        accounting.update(previousAttemptId=ticket['id'], previousPacketSha256=successor['previousPacketSha256'],
                          previousAttemptActualLaunches=2)
        accounting_path = self.root / 'successor-accounting.json'
        path = self.root / 'successor-ticket.json'
        mod.write(accounting_path, accounting)
        successor['launchAccounting'] = {'path': str(accounting_path), 'sha256': mod.digest(accounting_path)}
        mod.write(path, successor)
        with self.assertRaisesRegex(ValueError, 'counter cannot reset'):
            self.p.register_continuation(path)
        accounting['cumulativeActualLaunches'] = 163
        successor['authorityReview']['cumulativeActualLaunchesBefore'] = 163
        mod.write(accounting_path, accounting)
        successor['launchAccounting']['sha256'] = mod.digest(accounting_path)
        mod.write(path, successor)
        self.p.register_continuation(path)
        self.assertEqual(self.p.retry_show(successor['id'])['status'], 'queued')
        self.assertEqual(packet['launchAccounting']['cumulativeActualLaunchesAfter'], 163)


if __name__ == '__main__':
    unittest.main()

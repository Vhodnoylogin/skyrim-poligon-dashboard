"""One-shot report routing, final-only notices and independent exact-target receipts."""
import json
import unittest
from pathlib import Path

import test_polygon

mod = test_polygon.mod


class AutotestWorkflowTests(unittest.TestCase):
    def fixture(self, release=True):
        f = test_polygon.Tests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.automatic_submit()
        evidence = f.root / 'autotest-owner.txt'
        evidence.write_text('Conduct an autotest of this mod')
        request = {'schemaVersion': 1, 'id': 'autotest-1', 'workflow': 'autotest',
                   'orderIds': ['test-1'], 'toolThreadId': 'tool-thread',
                   'ownerAuthorization': {'threadId': 'thread-1', 'messageId': 'owner-turn',
                       'quote': 'Conduct an autotest of this mod', 'verifiedBy': 'offline-test',
                       'path': str(evidence), 'sha256': mod.digest(evidence)}}
        path = f.root / 'autotest.json'
        mod.write(path, request)
        if release:
            f.p.release_batch(path)
        return f, request, path

    def finish(self, f, check='passed', technical=False, ready=True, data=True):
        run = f.root / 'runtime/runs/autotest'
        state = {'id': 'autotest-run', 'order': {'id': 'test-1'}, 'done': True,
                 'restored': True, 'restoreErrors': []}
        if technical:
            state.update(collectionComplete=False, collectionErrors=[
                {'path': 'vrserver.txt', 'error': 'copy failed', 'segment': 'restart-1'}])
        mod.write(run / 'state.json', state)
        mod.write(run / 'result.json', {**state, 'checks': [] if check is None else [
            {'name': 'subject-check', 'result': check}]})
        packet = f.p.finish('test-1', 'passed' if check == 'passed' and not technical else 'failed',
                            'evidence collection incomplete' if technical else '', run, True)
        if ready:
            ref = next(e for e in packet['files'] if Path(e['path']).name == 'result.json')
            request = {'schemaVersion': 1, 'id': 'final-autotest', 'orderIds': ['test-1'],
                       'summary': 'Ended and restored; final evidence assessed', 'collectionFinished': True}
            if data:
                request['dataCoverage'] = {'test-1': [{'name': 'state', 'status': 'collected', 'evidence': [ref]}]}
            path = f.root / 'complete.json'
            mod.write(path, request)
            f.p.report_ready(path)
        return packet

    def receipt(self, message, **changes):
        return json.dumps({'messageId': 'real-app-message', **{k: message[k] for k in
                           ('notificationId', 'threadId', 'reportSha256')}, **changes})

    def test_success_requires_end_and_report_then_requests_origin_analysis(self):
        f, _, _ = self.fixture()
        self.assertFalse(f.p.pending())
        self.finish(f, ready=False)
        self.assertFalse(f.p.pending())
        f.ready('test-1')
        # Unassessed requested data cannot be upgraded to success by the workflow.
        messages = f.p.pending()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['action'], 'analyze_incomplete_report')
        self.assertFalse(messages[0]['attemptSuccessful'])

    def test_success_is_analyzed_by_exact_origin_and_not_tooling(self):
        f, _, _ = self.fixture()
        self.finish(f)
        message, = f.p.pending()
        self.assertEqual(message['threadId'], 'thread-1')
        self.assertEqual(message['action'], 'analyze_successful_report')
        self.assertTrue(message['attemptSuccessful'])
        self.assertIn('tell the owner', message['text'])
        self.assertEqual(f.p.board()[0]['workflow'], 'autotest')

    def test_subject_errors_request_analysis_without_tool_repair(self):
        f, _, _ = self.fixture()
        self.finish(f, check='failed')
        message, = f.p.pending()
        self.assertEqual(message['action'], 'analyze_subject_errors')
        self.assertEqual(message['testOutcome'], 'tested_with_errors')

    def test_tool_failure_has_two_independent_final_reports_to_correct_targets(self):
        f, _, _ = self.fixture()
        self.finish(f, technical=True)
        messages = f.p.pending()
        self.assertEqual([(m['recipient'], m['threadId'], m['action']) for m in messages],
                         [('origin', 'thread-1', 'review_failed_attempt'), ('tooling', 'tool-thread', 'test_tooling')])
        self.assertEqual(messages[0]['reportSha256'], messages[1]['reportSha256'])
        self.assertTrue(all(m['testOutcome'] == 'interrupted_external' for m in messages))

    def test_pretest_tool_failure_suppresses_both_targets_and_never_marks_tested(self):
        f, _, _ = self.fixture()
        self.finish(f, check=None, technical=True)
        self.assertFalse(f.p.pending())
        for recipient in ('origin', 'tooling'):
            message = {'notificationId': f'autotest:test-1:{recipient}', 'threadId': 'thread-1', 'reportSha256': '0' * 64}
            with self.subTest(recipient=recipient), self.assertRaisesRegex(ValueError, 'No finalized autotest notification'):
                f.p.delivered(message['notificationId'], self.receipt(message))
        self.assertEqual(f.p.get('test-1')['status'], 'recorded')
        self.assertIsNone(f.p.get('test-1')['delivery'])
        board = f.p.board()[0]
        self.assertEqual(board['testingLifecycle'], 'not_started')
        self.assertEqual(board['notificationEligibility'], 'suppressed')

    def test_mixed_faults_preserve_subject_analysis_and_tool_repair(self):
        f, _, _ = self.fixture()
        self.finish(f, check='failed', technical=True)
        messages = f.p.pending()
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]['testOutcome'], 'tested_with_errors')
        self.assertIn('independently recorded subject mismatches', messages[0]['text'])

    def test_origin_receipt_does_not_suppress_tooling_and_duplicates_do_not_resend(self):
        f, _, _ = self.fixture()
        self.finish(f, technical=True)
        origin, tooling = f.p.pending()
        f.p.delivered(origin['notificationId'], self.receipt(origin))
        self.assertEqual(f.p.get('test-1')['status'], 'delivered')
        self.assertEqual(f.p.pending()[0]['notificationId'], tooling['notificationId'])
        self.assertTrue(f.p.delivered(origin['notificationId'], self.receipt(origin))['duplicate'])
        f.p.delivered(tooling['notificationId'], self.receipt(tooling))
        self.assertFalse(f.p.pending())

    def test_wrong_target_hash_or_unstructured_receipt_refused(self):
        f, _, _ = self.fixture()
        self.finish(f, technical=True)
        origin, tooling = f.p.pending()
        for receipt in ('claimed sent', self.receipt(origin, threadId='tool-thread'),
                        self.receipt(origin, reportSha256='0' * 64), self.receipt(origin, messageId='')):
            with self.subTest(receipt=receipt), self.assertRaises(ValueError):
                f.p.delivered(origin['notificationId'], receipt)
        with self.assertRaisesRegex(ValueError, 'notificationId'):
            f.p.delivered('test-1', 'old generic acknowledgement')
        self.assertEqual(len(f.p.pending()), 2)

    def test_tampered_raw_data_blocks_both_recipients_even_after_origin_receipt(self):
        f, _, _ = self.fixture()
        packet = self.finish(f, technical=True)
        origin, tooling = f.p.pending()
        f.p.delivered(origin['notificationId'], self.receipt(origin))
        Path(packet['runDirectory'], 'result.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'manifest mismatch'):
            f.p.pending()
        with self.assertRaisesRegex(ValueError, 'manifest mismatch'):
            f.p.delivered(tooling['notificationId'], self.receipt(tooling))

    def test_registration_is_immutable_and_subject_order_does_not_acquire_workflow(self):
        f, request, path = self.fixture(release=False)
        original = f.p.get('test-1')['request']
        f.p.release_batch(path)
        self.assertTrue(f.p.release_batch(path)['duplicate'])
        request['toolThreadId'] = 'different-tool-thread'
        mod.write(path, request)
        with self.assertRaisesRegex(ValueError, 'different approval'):
            f.p.release_batch(path)
        self.assertEqual(f.p.get('test-1')['request'], original)
        self.assertNotIn('workflow', json.loads(original))

    def test_explicit_workflow_requires_owner_and_distinct_tool_recipient(self):
        f, request, path = self.fixture(release=False)
        for key, value in (('toolThreadId', ''), ('toolThreadId', 'thread-1'), ('workflow', 'full-cycle'),
                           ('ownerAuthorization', {})):
            invalid = {**request, key: value}
            mod.write(path, invalid)
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                f.p.release_batch(path)
        self.assertIsNone(f.p.claim())


if __name__ == '__main__':
    unittest.main()

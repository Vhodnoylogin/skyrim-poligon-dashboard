"""Zero-native continuation proofs against isolated queue fixtures only."""
import copy
import json
from pathlib import Path
import time
import unittest
from unittest.mock import Mock, patch

import companion_pretest_resume as resume
import polygon as m
import subject_companion_route as route
import test_subject_companion_route as fixtures


class CompanionPretestTests(unittest.TestCase):
    pin = fixtures.CompanionRouteTests.pin
    bind = fixtures.CompanionRouteTests.bind
    admission_fixture = fixtures.CompanionRouteTests.admission_fixture

    def setUp(self):
        fixtures.CompanionRouteTests.setUp(self)
        self.admission_fixture()
        self.deadline = time.time() + 600
        with self.p.connect() as con:
            con.execute('UPDATE releases SET authorization=?', (json.dumps({'ownerAuthorization': self.auth,
                'deadlineUtc': self.deadline}),))
        folder = self.p.evidence_dir(self.order['id'])
        m.write(folder / 'request.json', self.order)
        with patch.object(self.p, 'execute_claimed', side_effect=lambda row:
                self.p.finish(self.order['id'], 'blocked', 'Tool classifier refused before platform freeze')):
            route.execute(self.p, self.reviewfile)
        self.original = {str(path): m.digest(path) for path in folder.iterdir() if path.is_file()}
        self.previous_packet = Path(self.p.get(self.order['id'])['packet'])
        self.refusal = self.root / 'refusal.json'
        m.write(self.refusal, {'actualGameStarts': 0, 'subjectStarted': False,
                              'platformPlanCreated': False, 'historyPreserved': True})
        self.restoration = self.root / 'manager-restored.json'
        m.write(self.restoration, {'gameVRIdle': True, 'gameStartsThisAttempt': 0, 'procs': {'running': 0},
            'identity': {'pid': 700, 'birth': 7000, 'path': str(self.root / 'MO2.exe')}})
        self.abort = self.root / 'pre-session-review.json'
        m.write(self.abort, {'classification': 'confirmed-tooling-pre-session-refusal', 'orderId': self.order['id'],
            'packetSha256': m.digest(self.previous_packet), 'subjectStarted': False, 'actualGameStarts': 0,
            'platformPlanCreated': False, 'preSessionUntouched': True, 'refusal': self.pin(self.refusal),
            'managerRestoration': self.pin(self.restoration), 'verifiedBy': 'offline independent review',
            'reason': 'Zero native dispatcher and unchanged source inputs'})
        self.authority_file = self.root / 'authority.json'
        m.write(self.authority_file, {'state': 'active', 'orderIds': [self.order['id']], 'ownerAuthorization': self.auth})
        evidence = self.root / 'repair-tests.log'; evidence.write_text('Retained offline fixture test evidence, no game')
        self.repair_file = self.root / 'repair.json'
        m.write(self.repair_file, {'schemaVersion': 1, 'kind': 'companion-pre-session-tooling-repair',
            'orderId': self.order['id'], 'previousPacketSha256': m.digest(self.previous_packet),
            'operatorFiles': [self.pin(path) for path in m.HERE.glob('*.py')], 'testEvidence': [self.pin(evidence)],
            'verifiedBy': 'offline independent reviewer', 'reason': 'Only operator classifier repaired'})
        self.ticket = {'schemaVersion': 1, 'kind': resume.KIND, 'id': 'companion-pretest-1', 'orderId': self.order['id'],
            'previousPacketSha256': m.digest(self.previous_packet), 'technicalAbort': self.pin(self.abort),
            'ownerAuthority': self.pin(self.authority_file), 'companionSelection': self.pin(self.requestfile),
            'previousAdmission': self.pin(self.reviewfile), 'repair': self.pin(self.repair_file),
            'authorityReview': {'verifiedBy': 'offline operator', 'reason': 'Original unused first subject launch only',
                'retryPermitted': True, 'maxAdditionalAttempts': 1, 'subjectActualLaunchesBefore': 0,
                'maximumSubjectActualLaunches': 1, 'originalDeadlineUtc': self.deadline}}
        self.ticket_file = self.root / 'ticket.json'; m.write(self.ticket_file, self.ticket)
        self.admit_file = self.root / 'pretest-admission.json'
        m.write(self.admit_file, {'schemaVersion': 1, 'kind': 'operator-companion-pre-session-admission',
            'attemptId': self.ticket['id'], 'ticket': self.pin(self.ticket_file), 'ownerAuthorization': self.auth,
            'verifiedBy': 'offline independent operator', 'reason': 'Review exact unused first launch',
            'zeroNativeReviewed': True, 'preSessionUntouchedReviewed': True, 'restorationReviewed': True,
            'repairReviewed': True, 'unusedStartReviewed': True})
        import order_platform
        runner = order_platform.activate(self.executor)
        runner.GAME_NAMES, runner.VR_NAMES = {'skyrimse.exe', 'skse64_loader.exe'}, {'vrserver.exe', 'vrcompositor.exe'}

    def assert_original_preserved(self):
        self.assertEqual(self.p.get(self.order['id'])['status'], 'blocked')
        self.assertEqual(self.original, {path: m.digest(path) for path in self.original})
        self.assertIsNone(m.read(self.previous_packet)['restored'])

    def register(self):
        return self.p.register_retry(self.ticket_file)

    def admitted(self):
        self.register()
        resume.admit(self.p, self.admit_file)

    def test_register_uses_actual_companion_not_global_vr_and_retains_hold_and_packet(self):
        with patch.object(self.p, 'executor', side_effect=AssertionError('No global VR executor')):
            result = self.register()
        self.assertFalse(result['launch'])
        self.assertTrue(self.register()['duplicate'])
        self.assertEqual(self.p.retry_show(self.ticket['id'])['status'], 'queued')
        self.assertEqual([x['id'] for x in self.p.pipeline_status()['holds']], [self.order['id']])
        self.assertIsNone(self.p.claim_retry())
        self.assert_original_preserved()

    def test_admit_atomically_transfers_hold_to_running_not_old_global_queue(self):
        self.register(); seen = []; original = self.p.check_launch_authorization
        def check(order, connection=None):
            with self.p.connect() as con:
                seen.append(([r[0] for r in con.execute('SELECT id FROM pipeline_holds')],
                             con.execute('SELECT status FROM retry_attempts WHERE id=?', (self.ticket['id'],)).fetchone()[0]))
            return original(order, connection=connection)
        with patch.object(self.p, 'check_launch_authorization', side_effect=check):
            result = resume.admit(self.p, self.admit_file)
        self.assertEqual(seen, [([self.order['id']], 'queued')])
        self.assertEqual(result['status'], 'running')
        self.assertFalse(result['launch'])
        self.assertEqual(self.p.pipeline_status()['holds'], [])
        self.assertIsNone(self.p.claim_retry())  # An unchanged legacy dispatcher sees no queued ticket.
        self.assertEqual(resume.admit(self.p, self.admit_file)['status'], 'already_admitted')
        self.assert_original_preserved()

    def test_dedicated_dispatch_is_once_and_does_not_requeue_original(self):
        self.admitted()
        with patch.object(self.p, 'execute_retry', return_value={'mock': 'no launch'}) as execute:
            self.assertEqual(resume.run(self.p, self.ticket['id']), {'mock': 'no launch'})
            with self.assertRaisesRegex(ValueError, 'already dispatched'):
                resume.run(self.p, self.ticket['id'])
        execute.assert_called_once()
        self.assert_original_preserved()

    def test_original_attempt_platform_or_matching_run_refuses_registration(self):
        for kind in ('attempt', 'platform', 'run'):
            with self.subTest(kind=kind):
                if kind == 'run':
                    path = Path(self.cfg['runtime']) / 'runs' / 'foreign' / 'state.json'
                    m.write(path, {'order': {'id': self.order['id']}})
                else:
                    with self.p.connect() as con:
                        if kind == 'attempt': con.execute('INSERT INTO attempts VALUES(?,?)', (self.order['id'], 1))
                        else: con.execute('INSERT INTO platform_attempts VALUES(?,?,?)', (self.order['id'], '{}', '0' * 64))
                with self.assertRaises(ValueError): self.register()
                if kind == 'run': path.unlink()
                else:
                    with self.p.connect() as con:
                        con.execute('DELETE FROM ' + ('attempts' if kind == 'attempt' else 'platform_attempts') + ' WHERE id=?', (self.order['id'],))
        self.assert_original_preserved()

    def test_expired_or_extended_original_deadline_refuses_without_clearing_hold(self):
        for changed in ('expire', 'extend'):
            with self.subTest(changed=changed):
                if changed == 'expire':
                    with patch.object(resume.time, 'time', return_value=self.deadline + 1), self.assertRaisesRegex(ValueError, 'expired'):
                        self.register()
                else:
                    ticket = copy.deepcopy(self.ticket); ticket['authorityReview']['originalDeadlineUtc'] += 1
                    m.write(self.ticket_file, ticket)
                    with self.assertRaisesRegex(ValueError, 'extended'): self.register()
                    m.write(self.ticket_file, self.ticket)
        self.assertEqual([x['id'] for x in self.p.pipeline_status()['holds']], [self.order['id']])

    def test_changed_subject_input_and_changed_owner_scope_are_refused(self):
        self.subject.write_bytes(b'changed mod')
        with self.assertRaises(ValueError): self.register()
        self.subject.write_bytes(b'subject-under-test')
        value = m.read(self.authority_file); value['ownerAuthorization']['messageId'] = 'another-message'
        m.write(self.authority_file, value); ticket = copy.deepcopy(self.ticket); ticket['ownerAuthority'] = self.pin(self.authority_file)
        m.write(self.ticket_file, ticket)
        with self.assertRaisesRegex(ValueError, 'scope'): self.register()

    def test_context_accepts_its_later_native_run_after_deadline_but_not_foreign_attempt(self):
        self.admitted()
        path = Path(self.cfg['runtime']) / 'runs' / 'new-native' / 'state.json'
        state = {'order': {'id': self.order['id'], 'attemptId': self.ticket['id'], 'subjectOrderId': self.order['id']}}
        m.write(path, state)
        with patch.object(resume.time, 'time', return_value=self.deadline + 1):
            value = resume.context(self.p, self.order, self.ticket['id'])
        self.assertEqual(value['folder'], self.p.local / 'retry-attempts' / self.ticket['id'])
        with self.assertRaises(ValueError): resume.before_dispatch(self.p, self.ticket)
        state['order']['attemptId'] = 'another-attempt'; m.write(path, state)
        with self.assertRaisesRegex(ValueError, 'foreign'): resume.context(self.p, self.order, self.ticket['id'])

    def test_registration_requires_untouched_zero_native_not_only_review_flags(self):
        abort = m.read(self.abort); abort['actualGameStarts'] = 1; m.write(self.abort, abort)
        ticket = copy.deepcopy(self.ticket); ticket['technicalAbort'] = self.pin(self.abort); m.write(self.ticket_file, ticket)
        with self.assertRaisesRegex(ValueError, 'zero-native'): self.register()

    def test_direct_retry_execute_cannot_bypass_supported_dispatch_marker(self):
        self.admitted()
        with self.assertRaisesRegex(ValueError, 'dispatch claim'):
            self.p.execute_retry(self.p.retry_show(self.ticket['id']))

    def test_historical_context_accepts_one_exact_successor_without_reauthorizing_old_dispatch(self):
        self.admitted()
        with self.p.connect() as con:
            con.execute("UPDATE retry_attempts SET status='recorded' WHERE id=?", (self.ticket['id'],))
            descendant = {'kind': 'companion-post-start-tooling', 'id': 'reviewed-next-attempt',
                          'orderId': self.order['id'], 'previousAttemptId': self.ticket['id']}
            con.execute("INSERT INTO retry_attempts(id,order_id,request,created,status) VALUES(?,?,?,2,'queued')",
                        (descendant['id'], self.order['id'], json.dumps(descendant)))
        self.assertEqual(resume.context(self.p, self.order, self.ticket['id'])['attemptId'], self.ticket['id'])
        with self.assertRaisesRegex(ValueError, 'cannot branch'):
            resume.predecessor(self.p, self.ticket, allow_current=False)
        with self.p.connect() as con:
            descendant['previousAttemptId'] = 'unrelated-ended-attempt'
            con.execute('UPDATE retry_attempts SET request=? WHERE id=?', (json.dumps(descendant), descendant['id']))
        with self.assertRaisesRegex(ValueError, 'cannot branch'):
            resume.context(self.p, self.order, self.ticket['id'])

    def test_other_queued_work_or_prepared_qualification_retains_hold(self):
        self.register()
        with self.p.connect() as con:
            con.execute("INSERT INTO qualifications(id,request,status) VALUES('other-prepared','{}','prepared')")
        with self.assertRaisesRegex(ValueError, 'qualification'): resume.admit(self.p, self.admit_file)
        self.assertEqual([x['id'] for x in self.p.pipeline_status()['holds']], [self.order['id']])

    def test_archive_inventory_rejects_empty_changed_and_extra_files(self):
        run = self.root / 'collected-run'; archive = run / 'test-profile'; archive.mkdir(parents=True)
        m.write(run / 'state.json', {'profileArchive': str(archive), 'testProfile': str(self.root / 'removed-copy')})
        with self.assertRaisesRegex(ValueError, 'nonempty'): resume.archive_record(run)
        original = archive / 'modlist.txt'; original.write_text('original profile')
        folder = self.root / 'attempt-evidence'; folder.mkdir()
        record = resume.freeze_archive(folder, run)
        packet = {'runDirectory': str(run), 'files': [{**self.pin(record), 'bytes': record.stat().st_size}]}
        resume.verify_archive(packet)
        original.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'archive changed'): resume.verify_archive(packet)
        original.write_text('original profile'); (archive / 'extra.ini').write_text('extra')
        with self.assertRaisesRegex(ValueError, 'archive changed'): resume.verify_archive(packet)


if __name__ == '__main__':
    unittest.main()

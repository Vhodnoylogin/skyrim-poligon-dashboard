"""Queue/plan/result plumbing with mocked native outcomes, never a game launch."""
import json
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import polygon as m
import companion_pretest_resume as resume
import test_companion_pretest_resume as fixtures


class PreSessionIntegrationTests(unittest.TestCase):
    setUp = fixtures.CompanionPretestTests.setUp
    pin = fixtures.CompanionPretestTests.pin
    bind = fixtures.CompanionPretestTests.bind
    admission_fixture = fixtures.CompanionPretestTests.admission_fixture
    register = fixtures.CompanionPretestTests.register
    admitted = fixtures.CompanionPretestTests.admitted
    assert_original_preserved = fixtures.CompanionPretestTests.assert_original_preserved

    def freeze(self):
        self.admitted()
        with patch.object(self.p, 'execute_retry', return_value={'fixture': 'no native launch'}):
            resume.run(self.p, self.ticket['id'])
        plan = self.p.prepare_platform(self.order, attempt_id=self.ticket['id'])
        folder = self.p.local / 'retry-attempts' / self.ticket['id']
        m.write(folder / 'config.json', plan['configuration'])
        m.write(folder / 'scenario.json', plan['scenario'])
        return plan, folder

    def test_registered_admitted_proof_freezes_actual_retry_context_without_global_vr(self):
        with patch.object(self.p, 'executor', side_effect=AssertionError('No global VR fallback')):
            plan, folder = self.freeze()
            self.assertEqual(self.p.verify_platform(self.order, attempt_id=self.ticket['id']), plan)
        self.assertEqual(plan['companionAttemptId'], self.ticket['id'])
        self.assertEqual(plan['subjectOrderSha256'], m.subject_contract.identity(self.order))
        self.assertTrue((folder / 'platform-plan.json').is_file())
        self.assert_original_preserved()

    def test_final_packet_preserves_original_and_verifies_actual_new_archive_inventory(self):
        plan, folder = self.freeze()
        run = Path(self.cfg['runtime']) / 'runs' / 'mocked-native-result'
        archive = run / 'test-profile'; archive.mkdir(parents=True)
        saved_profile = archive / 'modlist.txt'; saved_profile.write_text('actual archived fixture bytes')
        state = {'id': run.name, 'order': {'id': self.order['id'], 'attemptId': self.ticket['id'],
                   'subjectOrderId': self.order['id'], 'owner': self.order['sourceChat']},
                 'done': True, 'restored': True, 'restoreErrors': [], 'result': 'passed',
                 'scenarioHash': m.digest(folder / 'scenario.json'), 'profileArchive': str(archive),
                 'testProfile': str(self.root / 'removed-new-profile')}
        m.write(run / 'state.json', state); m.write(run / 'result.json', state)
        summary = {'completed': True, 'uncertain': False, 'subjectStarted': False, 'pins': [],
                   'checks': [{'name': name, 'result': 'not_run'} for name in self.order['subjectPlan']['checks']]}
        with patch('companion_evidence.collect', return_value=summary):
            packet = self.p.finish_retry(self.ticket['id'], run)
        self.assertEqual(packet['orderId'], self.order['id'])
        self.assertEqual(packet['attemptId'], self.ticket['id'])
        self.assertEqual(packet['launchAccounting']['subjectActualLaunchesAfter'], 1)
        self.assertEqual(packet['subjectCompanion']['checks'], summary['checks'])
        self.assertTrue((folder / 'profile-archive.json').is_file())
        self.assert_original_preserved()
        row = self.p.retry_show(self.ticket['id'])
        self.p.verify_retry_packet(row)
        saved_profile.write_text('changed after collection')
        with self.assertRaisesRegex(ValueError, 'archive'):
            self.p.verify_retry_packet(row)

    def test_valid_partial_transport_failure_still_collects_archive_and_retains_truthful_cases(self):
        _, folder = self.freeze()
        run = Path(self.cfg['runtime']) / 'runs' / 'mocked-partial-transport'
        archive = run / 'test-profile'; archive.mkdir(parents=True)
        (archive / 'modlist.txt').write_text('restored failed-session profile')
        reason = 'Interactive session ended: Unique declared native function metadata is unavailable'
        state = {'id': run.name, 'order': {'id': self.order['id'], 'attemptId': self.ticket['id'],
                   'subjectOrderId': self.order['id']}, 'done': True, 'restored': True, 'restoreErrors': [],
                 'result': 'failed', 'reason': reason, 'scenarioHash': m.digest(folder / 'scenario.json'),
                 'profileArchive': str(archive), 'testProfile': str(self.root / 'removed-failed-profile')}
        m.write(run / 'state.json', state); m.write(run / 'result.json', state)
        names = self.order['subjectPlan']['checks']
        summary = {'completed': False, 'uncertain': True, 'subjectStarted': True, 'pins': [],
                   'checks': [{'name': name, 'result': ('passed' if i == 0 else 'unavailable' if i == 1 else 'not_run')}
                              for i, name in enumerate(names)]}
        with patch('companion_evidence.collect', return_value=summary):
            packet = self.p.finish_retry(self.ticket['id'], run)
        self.assertTrue((folder / 'profile-archive.json').is_file())
        self.assertEqual(packet['subjectCompanion'], summary)
        self.assertEqual(packet['executionOutcome'], 'failed'); self.assertEqual(packet['reason'], reason)
        findings = m.read(folder / 'self-checks.json')['findings']
        self.assertIn('companion_transport_interrupted', [x['kind'] for x in findings])
        self.assertNotIn('companion_evidence_unverified', [x['kind'] for x in findings])
        self.assertIn(self.ticket['id'], [x['id'] for x in self.p.pipeline_status()['holds']])
        self.p.verify_retry_packet(self.p.retry_show(self.ticket['id']))
        self.assert_original_preserved()


class HistoricalRepairHookTests(unittest.TestCase):
    def test_verified_historical_view_does_not_reenter_live_context_or_profile_absence_gate(self):
        order = {'id': 'original-subject'}
        raw = {'attemptId': 'ended-attempt', 'subjectOrderSha256': m.subject_contract.identity(order),
               'previousPacketSha256': 'a' * 64, 'runDirectory': 'closed-owned-run', 'files': []}
        derived = dict(raw, collectionRepair={'path': 'frozen-supplement', 'sha256': 'b' * 64},
                       originalPacket={'path': 'old-packet', 'sha256': 'c' * 64})
        row = {'id': 'ended-attempt', 'packet': 'old-packet',
               'request': json.dumps({'kind': 'companion-pre-session', 'previousPacketSha256': 'a' * 64})}
        p = SimpleNamespace(retry_order=lambda _: order, verify_packet=lambda _: (order, raw))
        with (patch('companion_collection_repair.apply', return_value=derived) as applied,
              patch('companion_pretest_resume.context', side_effect=AssertionError('Current owner is irrelevant to closed proof')),
              patch('companion_pretest_resume.verify_archive', side_effect=AssertionError('Repair already verifies immutable archive')),
              patch('companion_pretest_resume.packet_metadata', return_value={})):
            self.assertEqual(m.Polygon.verify_retry_packet(p, row), derived)
        applied.assert_called_once_with(p, row, raw)
        self.assertNotIn('collectionRepair', raw)


if __name__ == '__main__': unittest.main()

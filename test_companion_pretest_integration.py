"""Queue/plan/result plumbing with mocked native outcomes, never a game launch."""
import json
from pathlib import Path
import unittest
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


if __name__ == '__main__': unittest.main()

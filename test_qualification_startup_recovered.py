"""Recovered pre-client startup retains unknown exit and never invents a client."""
import copy
import unittest

import polygon as m
import qualification_preclient as d
import test_qualification_startup_native as fixture


class RecoveredStartupTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture.NativeStartupTests(); self.base.setUp(); self.addCleanup(self.base.doCleanups)
        f = self.f = self.base.f
        f.state['guardianRecovery'] = {'trigger': 'Owner unavailable during native cleanup',
            'prior': {'phase': 'stop-and-restore', 'result': 'failed'},
            'decision': {'id': f.state['id'], 'runner': f.worker, 'game': f.game,
                'done': False, 'ownerAlive': False, 'action': 'claim-recovery-mutex'}}
        f.state['gameProcessObservations'] = [{'status': 'unavailable', 'identityVerified': False,
            'identity': None, 'expectedIdentity': f.game, 'exitCodeAvailable': False,
            'exitCode': None, 'exitCodeHex': None}]
        f.write(f.run / 'state.json', f.state)

    def technical_review(self):
        f = self.f; path = self.base.technical_review(); value = m.read(path)
        value.pop('gameExit')
        value.update(gameProcessObservations=f.state['gameProcessObservations'],
            guardianRecovery=f.state['guardianRecovery'], allExactOwnedProcessesDeadIncludingDebugger=True,
            freshNoGameCDBWerFault=True, supportedRecoveryAfterActualGameAndCDBEnded=True)
        for pin in value['rawPins']: pin['bytes'] = __import__('pathlib').Path(pin['path']).stat().st_size
        f.write(path, value); return path

    def review(self):
        f = self.f; path = self.base.base.review(); value = m.read(path)
        value['dispatch'] = f.pin(f.comp / 'dispatch.json')
        value['endedTechnicalReview'] = f.pin(self.technical_review())
        f.write(path, value); return path

    def record(self): return d.record(self.f.p, 'q-one', self.review(), startup=True)

    def test_recovered_prefix_records_not_run_and_unknown_game_exit(self):
        f = self.f; packet = self.record()
        self.assertEqual(packet['startupFailureMode'], 'native-recovered-before-client')
        self.assertFalse(packet['gameExitCodeAvailable']); self.assertIsNone(packet['gameExitCode'])
        self.assertEqual(packet['qualificationOutcome'], 'not_conducted')
        self.assertTrue(all(x['result'] == 'not_run' for x in packet['componentCoverage']))
        self.assertFalse((f.comp / 'report.json').exists())
        self.assertEqual(len(f.p.pipeline_status()['holds']), 1)
        self.assertFalse(f.p.qualification_successful_result(f.plan, packet))
        self.assertIsNone(packet['cumulativeActualGameStartsAfter'])
        self.assertEqual(f.p.qualification_collect('q-one'), packet)

    def test_mismatched_recovery_or_exit_observations_refuse(self):
        f = self.f; original = copy.deepcopy(f.state)
        changes = [dict(ownerAlive=True), dict(game=f.client), dict(runner=f.client), dict(action='other')]
        for change in changes:
            with self.subTest(change=change):
                f.state = copy.deepcopy(original); f.state['guardianRecovery']['decision'].update(change)
                f.write(f.run / 'state.json', f.state)
                with self.assertRaisesRegex(ValueError, 'recovery required'): self.record()
        for change in [dict(exitCode=0), dict(exitCodeAvailable=True), dict(expectedIdentity=f.client), dict(status='running')]:
            with self.subTest(change=change):
                f.state = copy.deepcopy(original); f.state['gameProcessObservations'][0].update(change)
                f.write(f.run / 'state.json', f.state)
                with self.assertRaisesRegex(ValueError, 'unavailable game exit'): self.record()

    def test_client_or_completed_world_cannot_be_finalized_as_unstarted(self):
        f = self.f
        f.write(f.comp / 'report.json', {'status': 'unknown'})
        with self.assertRaisesRegex(ValueError, 'client output'): self.record()
        (f.comp / 'report.json').unlink()
        f.state['gameplayBootstrap'] = {'completed': True}; f.write(f.run / 'state.json', f.state)
        with self.assertRaisesRegex(ValueError, 'ownership was reached'): self.record()

    def test_technical_review_cannot_invent_game_exit_or_omit_death(self):
        f = self.f
        for change in [dict(gameExit=0), dict(freshNoGameCDBWerFault=False), dict(supportedRecoveryAfterActualGameAndCDBEnded=False)]:
            with self.subTest(change=change):
                path = self.review(); value = m.read(path); technical = m.read(value['endedTechnicalReview']['path'])
                technical.update(change); f.write(value['endedTechnicalReview']['path'], technical)
                value['endedTechnicalReview'] = f.pin(value['endedTechnicalReview']['path']); f.write(path, value)
                with self.assertRaisesRegex(ValueError, 'recovery/death'): d.record(f.p, 'q-one', path, startup=True)

    def test_uncertain_actual_death_and_unrestored_files_remain_blocked(self):
        f = self.f; f.dead.side_effect = ValueError('actual owner death unproven')
        with self.assertRaisesRegex(ValueError, 'death unproven'): self.record()
        f.dead.side_effect = None; f.target.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'hash differs'): self.record()
        self.assertFalse((f.folder / 'startup-diagnostic').exists())

    def test_cached_packet_cannot_change_unknown_exit_to_success(self):
        f = self.f; packet = self.record(); changed = copy.deepcopy(packet)
        changed.update(gameExitCodeAvailable=True, gameExitCode=0)
        with self.assertRaisesRegex(ValueError, 'unavailable game exit'): d.verify_packet(f.p, f.plan, changed)


if __name__ == '__main__': unittest.main()

"""Exit observations outrank raw pass and cleanup, without changing subject checks."""
import json
from pathlib import Path
import tempfile
import unittest

import polygon


class ExecutionExitProjectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.run = Path(temporary.name)
        self.game = {'pid': 123, 'birth': 456, 'path': str(self.run / 'SkyrimSE.exe')}
        self.state = {'id': 'native', 'game': self.game, 'done': True, 'restored': True,
                      'phase': 'stop-and-restore', 'restoreErrors': []}
        self.result = {'result': 'passed', 'checks': [{'name': 'actual-load', 'result': 'passed'}]}
        self.events = [{'kind': 'tool', 'tool': 'console', 'args': {'action': 'exec', 'command': 'qqq'},
                        'result': {'queued': True}}]

    def observation(self, code):
        return {'status': 'exited', 'identityVerified': True, 'identity': self.game,
                'expectedIdentity': self.game, 'exitCodeAvailable': True,
                'exitCode': code, 'exitCodeHex': f'0x{code:08X}'}

    def project(self, pinned=None):
        polygon.write(self.run / 'state.json', self.state)
        polygon.write(self.run / 'result.json', self.result)
        (self.run / 'steps.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in self.events), encoding='utf-8')
        before = {path.name: path.read_bytes() for path in self.run.iterdir()}
        summary = polygon.Polygon.execution_summary({'id': 'order'}, self.run, 'passed', None, pinned)
        self.assertEqual({path.name: path.read_bytes() for path in self.run.iterdir()}, before)
        self.assertEqual(self.result['checks'], [{'name': 'actual-load', 'result': 'passed'}])
        self.assertEqual(summary['rawOutcome'], 'passed')
        return summary

    def test_nonzero_in_state_or_result_dominates_passed_cleanup_and_request(self):
        for source in ('state', 'result'):
            with self.subTest(source=source):
                target = self.state if source == 'state' else self.result
                target['gameProcessObservations'] = [self.observation(0xC0000409)]
                summary = self.project()
                self.assertEqual(summary['terminationCause'], 'unexpected_process_exit')
                self.assertEqual(summary['gameExitEvidence']['exitCodes'], [0xC0000409])
                target.pop('gameProcessObservations')

    def test_actual_zero_and_logged_request_prove_normal_close(self):
        self.state['gameProcessObservations'] = [self.observation(0)]
        self.assertEqual(self.project()['terminationCause'], 'normal_close')
        self.events = []
        self.assertEqual(self.project()['terminationCause'], 'unknown')

    def test_exact_durable_quit_attempt_works_without_legacy_tool_log_but_intent_alone_does_not(self):
        self.state['gameProcessObservations'] = [self.observation(0)]
        self.events = []
        self.state['gracefulGameExit'] = {'game': self.game, 'command': 'qqq', 'requestAttempted': True}
        self.assertEqual(self.project()['terminationCause'], 'normal_close')
        self.state['gracefulGameExit']['requestAttempted'] = False
        self.events = [dict(self.state['gracefulGameExit'], kind='graceful-game-exit-request')]
        self.assertEqual(self.project()['terminationCause'], 'unknown')

    def test_absent_unavailable_malformed_or_foreign_observer_never_invents_zero(self):
        missing = self.observation(0)
        cases = [[], [dict(missing, status='unavailable', exitCode=None, exitCodeHex=None, exitCodeAvailable=False)],
                 [dict(missing, identityVerified=False)], [dict(missing, exitCodeAvailable=False)],
                 [dict(missing, exitCode=False)], [dict(missing, exitCodeHex=None)],
                 [dict(missing, identity=dict(self.game, birth=999))],
                 [dict(missing, expectedIdentity=dict(self.game, pid=999))]]
        for observations in cases:
            with self.subTest(observations=observations):
                self.state['gameProcessObservations'] = observations
                self.assertEqual(self.project()['terminationCause'], 'unknown')

    def test_forced_game_stop_even_observed_zero_is_operational(self):
        self.state['gameProcessObservations'] = [self.observation(0)]
        for source in ('state', 'result', 'log'):
            with self.subTest(source=source):
                if source == 'log': self.events.append({'kind': 'forced-stop', 'role': 'game', 'pid': 123})
                else: (self.state if source == 'state' else self.result)['forcedGameStop'] = True
                summary = self.project()
                self.assertEqual(summary['terminationCause'], 'operational_interruption')
                self.assertTrue(summary['gameExitEvidence']['forcedStopObserved'])
                self.state.pop('forcedGameStop', None); self.result.pop('forcedGameStop', None)

    def test_previous_owned_game_zero_cannot_stand_in_for_current_game_exit(self):
        previous = dict(self.game, pid=122, birth=455)
        self.state['owned'] = [{'role': 'game', 'identity': previous}, {'role': 'game', 'identity': self.game}]
        self.state['gameProcessObservations'] = [dict(self.observation(0), identity=previous, expectedIdentity=previous)]
        self.state['gracefulGameExit'] = {'game': self.game, 'command': 'qqq', 'requestAttempted': True}
        self.assertEqual(self.project()['terminationCause'], 'unknown')

    def test_unpinned_telemetry_or_request_cannot_prove_exit(self):
        self.result['gameProcessObservations'] = [self.observation(0)]
        pinned = {(self.run / name).resolve() for name in ('state.json', 'steps.jsonl')}
        self.assertEqual(self.project(pinned)['terminationCause'], 'unknown')
        pinned = {(self.run / name).resolve() for name in ('state.json', 'result.json')}
        self.assertEqual(self.project(pinned)['terminationCause'], 'unknown')

    def test_nonzero_remains_an_observation_not_a_claimed_crash_cause(self):
        self.state['gameProcessObservations'] = [self.observation(0xC0000409)]
        self.events.append({'kind': 'forced-stop', 'role': 'game', 'pid': 123})
        summary = self.project()
        self.assertEqual(summary['terminationCause'], 'unexpected_process_exit')
        self.assertNotIn('crash', summary['terminationCause'])
        self.assertTrue(summary['gameExitEvidence']['forcedStopObserved'])

    def test_failed_exit_preserves_passed_checks_and_raw_outcome_separately(self):
        import test_polygon
        fixture = test_polygon.Tests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        checks = [{'name': name, 'result': 'passed'} for name in ('subject-check', 'later-check')]
        packet = fixture.final_fixture(checks, outcome='passed', native_proof={
            'state': {'game': self.game, 'gameProcessObservations': [self.observation(0xC0000409)]},
            'events': self.events})
        order, verified = fixture.p.verify_packet(fixture.p.get('final-fixture'))
        result = fixture.p.test_projection(order, verified)
        self.assertEqual(packet['executionOutcome'], 'passed')
        self.assertEqual(result['execution']['terminationCause'], 'unexpected_process_exit')
        self.assertEqual(result['outcome'], 'interrupted_external')
        self.assertEqual(result['coverage']['passed'], 2)
        self.assertEqual(result['coverage']['failed'], 0)
        self.assertFalse(result['subjectMismatchObserved'])


if __name__ == '__main__': unittest.main()

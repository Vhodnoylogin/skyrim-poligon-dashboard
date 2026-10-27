"""Collection-only prebinding prefix; temporary queue/files and no game or HTTP."""
import copy
import json
import unittest

import polygon as m
import qualification_preclient as d
import test_qualification_preclient as fixture


class PrebindingTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.PreclientTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        f = self.f
        self.binding = {'provider': 'skyrim-autotest', 'conversationId': 'run-one', 'agentId': 'owned-game-executor'}
        self.recovery = {'trigger': 'Runner exceeded its phase deadline or heartbeat limit',
            'prior': {'phase': 'interactive-session'}, 'decision': {'id': 'run-one', 'runner': f.worker,
                'game': f.game, 'done': False, 'expired': True, 'ownerAlive': False, 'gameAlive': True,
                'action': 'claim-recovery-mutex', 'reasons': ['runner-heartbeat-expired'], 'at': 1040,
                'health': {'ok': True, 'pid': f.game['pid'], 'frame': 500},
                'timing': {'phase': 'interactive-session', 'pulse': None, 'reasons': ['runner-heartbeat-expired'],
                           'at': 1040, 'deadline': 1600}}}
        f.state.update(result='failed', phase='stop-and-restore', reason=self.recovery['trigger'],
            guardianRecovery=copy.deepcopy(self.recovery),
            interactiveSession={'ready': True, 'sessionId': 'game-run-one', 'binding': self.binding},
            gameProcessObservations=[{'status': 'exited', 'identityVerified': True, 'identity': f.game,
                'expectedIdentity': f.game, 'exitCodeAvailable': True, 'exitCode': 125, 'exitCodeHex': '0x0000007D'}])
        f.write(f.run / 'state.json', f.state)
        f.write(f.run / 'result.json', {'id': 'run-one', 'restored': True, 'restoreErrors': [], 'result': 'failed'})
        f.write(f.run / 'heartbeat.json', {'schemaVersion': 1, 'id': 'run-one', 'runner': f.worker,
            'at': 1038, 'healthy': True, 'error': None, 'recovery': {'owned': f.state['owned']}})
        f.write(f.folder / 'child-exit.json', {'returncode': 125})
        self.ready = {'kind': 'interactive-ready', 'at': 1002, 'sessionId': 'game-run-one', 'binding': self.binding}
        (f.run / 'steps.jsonl').write_text(json.dumps(self.ready)+'\n')
        f.report.update(errorType='CompanionError', reason='Exact worker heartbeat is unavailable/stale',
                        gameLifecycleOwned=False, startedAt=1005)
        f.dispatch['nativeRun']['interactiveDeadline'] = 1600
        (f.comp / 'evidence').mkdir()
        (f.comp / 'client.log').write_text('Actual stopped prefix retained\n')
        f.save()

    def technical(self):
        f = self.f
        value = {'schemaVersion': 1, 'qualificationId': 'q-one', 'nativeRun': str(f.run),
            'nativeDoneRestoredCollected': True, 'nativeResult': 'failed', 'componentActions': 0,
            'componentChecksNotRun': 2, 'workerExit': {'returncode': 125}, 'gameExit': 125,
            'dispatch': f.dispatch, 'clientFailure': {k: f.report.get(k) for k in
                ('done', 'completed', 'status', 'reason', 'uncertain', 'runId', 'binding', 'sessionId', 'cases')},
            'operatorFinishSubmitted': False, 'guardianRecovery': f.state['guardianRecovery'],
            'allExactOwnedProcessesDeadIncludingDebugger': True}
        paths = [f.folder / p for p in ('plan.json', 'worker.json', 'child-exit.json',
            'subject-companion/dispatch.json', 'subject-companion/executor-manifest.json',
            'subject-companion/report.json', 'subject-companion/events.jsonl', 'subject-companion/client.log')]
        paths += [f.run / p for p in ('state.json', 'result.json', 'steps.jsonl', 'heartbeat.json')]
        value['rawPins'] = [{**f.pin(path), 'bytes': path.stat().st_size} for path in paths]
        path = f.root / 'technical-review.json'; f.write(path, value); return path

    def review(self):
        f = self.f; path = f.review(); value = m.read(path)
        value.update(kind='qualification-prebinding-review', prebindingFailureReviewed=True,
                     endedTechnicalReview=f.pin(self.technical()))
        f.write(path, value); return path

    def record(self):
        return d.record(self.f.p, 'q-one', self.review(), prebinding=True)

    def test_records_actual_prefix_without_fabricating_binding_finish_or_release(self):
        f = self.f; packet = self.record()
        self.assertEqual(packet['kind'], d.PREBINDING_KIND)
        self.assertEqual(packet['actualGameStarts'], 1)
        self.assertIsNone(packet['cumulativeActualGameStartsAfter'])
        self.assertTrue(packet['retainHold']); self.assertFalse(packet['testingStarted'])
        self.assertIsNone(packet['ownerFinishCommandId'])
        self.assertFalse(packet['clientRunIdentityAvailable'])
        self.assertEqual(packet['executionOutcome'], 'failed')
        self.assertTrue(all(row['result'] == 'not_run' for row in packet['componentCoverage']))
        self.assertEqual(packet['endedTechnicalReview']['path'], str(f.root / 'technical-review.json'))
        self.assertFalse(f.p.qualification_successful_result(f.plan, packet))
        f.installed.write_bytes(b'legitimate rollback after collection')
        self.assertEqual(f.p.qualification_collect('q-one'), packet)
        self.assertEqual(len(f.p.pipeline_status()['holds']), 1)
        self.assertNotIn('runId', m.read(f.comp / 'report.json'))
        self.assertEqual(f.dead.call_args.args[1], [f.worker, f.client, f.game])

    def test_old_modes_keep_their_original_conditions(self):
        f = self.f
        with self.assertRaises(ValueError): d.verify_prefix(f.plan, f.folder, f.run / 'state.json')
        with self.assertRaises(ValueError): d.verify_startup_prefix(f.plan, f.folder, f.run / 'state.json')
        with self.assertRaisesRegex(ValueError, 'operator review'):
            d.record(f.p, 'q-one', f.review(), prebinding=True)

    def test_binding_inner_origin_actions_or_uncertainty_cannot_be_reclassified(self):
        f = self.f
        for key, value in (('binding', None), ('runId', 'run-one'), ('sequencerProcess', {}), ('readyState', {}),
                           ('actions', [{'commandId': 'a'*32}]), ('uncertain', True), ('subjectStarted', True)):
            with self.subTest(key=key):
                old = copy.deepcopy(f.report); f.report[key] = value; f.save()
                with self.assertRaises(ValueError): self.record()
                f.report = old; f.save()
        (f.run / 'subject-companion.claim.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'claim'): self.record()

    def test_even_a_finish_or_evidence_record_refuses_zero_action_projection(self):
        f = self.f
        with (f.run / 'steps.jsonl').open('a') as stream:
            stream.write(json.dumps({'kind': 'interactive-action-delivered', 'commandId': 'a'*32,
                                     'request': {'operation': 'finish'}})+'\n')
        with self.assertRaisesRegex(ValueError, 'component action'): self.record()
        (f.run / 'steps.jsonl').write_text(json.dumps(self.ready)+'\n')
        (f.comp / 'evidence/unexpected.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'unexpected artifacts'): self.record()

    def test_wrong_guardian_identity_exit_or_chronology_cannot_finalize(self):
        f = self.f; initial = copy.deepcopy(f.state)
        for change in ('identity', 'exit', 'deadline', 'reason'):
            with self.subTest(change=change):
                f.state = copy.deepcopy(initial)
                if change == 'identity': f.state['guardianRecovery']['decision']['game']['pid'] = 999
                if change == 'exit': f.state['gameProcessObservations'][0]['exitCode'] = 0
                if change == 'deadline': f.state['guardianRecovery']['decision']['timing']['deadline'] = 1020
                if change == 'reason': f.state['guardianRecovery']['decision']['reasons'] = ['other']
                f.write(f.run / 'state.json', f.state)
                with self.assertRaises(ValueError): self.record()
        f.state = initial; f.write(f.run / 'state.json', f.state)
        f.write(f.folder / 'child-exit.json', {'returncode': 0})
        with self.assertRaisesRegex(ValueError, 'worker exit125'): self.record()

    def test_fresh_heartbeat_required_and_dead_process_uncertainty_retains_hold(self):
        f = self.f; pulse = m.read(f.run / 'heartbeat.json'); pulse['at'] = 1000
        f.write(f.run / 'heartbeat.json', pulse)
        with self.assertRaisesRegex(ValueError, 'retained heartbeat'): self.record()
        pulse['at'] = 1038; f.write(f.run / 'heartbeat.json', pulse)
        f.dead.side_effect = ValueError('unknown debugger death')
        with self.assertRaisesRegex(ValueError, 'unknown debugger death'): self.record()
        self.assertEqual(f.p.qualification_show('q-one')['status'], 'running')
        self.assertFalse((f.folder / 'prebinding-diagnostic').exists())

    def test_independent_review_raw_inventory_and_counts_are_mandatory(self):
        f = self.f; path = self.review(); review = m.read(path); technical = m.read(f.root / 'technical-review.json')
        technical['rawPins'] = [x for x in technical['rawPins'] if not x['path'].endswith('heartbeat.json')]
        f.write(f.root / 'technical-review.json', technical)
        review['endedTechnicalReview'] = f.pin(f.root / 'technical-review.json'); f.write(path, review)
        with self.assertRaisesRegex(ValueError, 'incomplete reviewed raw'):
            d.record(f.p, 'q-one', path, prebinding=True)


if __name__ == '__main__': unittest.main()

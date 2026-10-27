"""Guardian-ended pre-client collection uses only synthetic external evidence."""
import json
import unittest

import polygon as m
import qualification_preclient as d
import test_qualification_preclient as fixture


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.PreclientTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        f = self.f
        for p in f.comp.iterdir():
            if p.name != 'executor-manifest.json': p.unlink()
        f.state.pop('interactiveSession'); f.state.pop('gameplayBootstrap')
        f.state.update(result='failed', reason='guardian recovered startup', phase='stop-and-restore',
            guardianRecovery={'trigger': 'guardian recovered startup', 'prior': {'phase': 'wait-task-queue'}})
        f.write(f.run / 'state.json', f.state)
        f.write(f.run / 'result.json', {'id': 'run-one', 'restored': True, 'restoreErrors': [], 'result': 'failed'})
        f.write(f.folder / 'child-exit.json', {'returncode': 125})
        (f.run / 'steps.jsonl').write_text(json.dumps({'kind': 'phase', 'name': 'wait-task-queue'})+'\n'+
            json.dumps({'kind': 'phase', 'name': 'stop-and-restore'})+'\n')

    def review(self):
        f = self.f
        value = {'schemaVersion': 1, 'kind': 'qualification-startup-review', 'qualificationId': 'q-one',
            'verifiedBy': 'offline operator', 'summary': 'No client was admitted; retain failed startup and count',
            'nativeCompletionReviewed': True, 'restorationReviewed': True, 'archiveReviewed': True,
            'startupFailureReviewed': True, 'retainHold': True, 'implementationPins': d.implementation_pins()}
        for key, path in {'plan': f.folder / 'plan.json', 'state': f.run / 'state.json', 'result': f.run / 'result.json',
            'childExit': f.folder / 'child-exit.json', 'worker': f.folder / 'worker.json'}.items(): value[key] = f.pin(path)
        value['profileArchivePins'], value['profileArchiveDirectories'] = d.archive_inventory(f.profile)
        path = f.root / 'startup-review.json'; f.write(path, value); return path

    def record(self): return d.record(self.f.p, 'q-one', self.review(), startup=True)

    def test_records_no_report_without_fabricating_identity_or_completion(self):
        f = self.f; packet = self.record()
        self.assertEqual(packet['kind'], d.STARTUP_KIND); self.assertEqual(packet['executionOutcome'], 'failed')
        self.assertEqual(packet['actualGameStarts'], 1); self.assertIsNone(packet['cumulativeActualGameStartsAfter'])
        self.assertFalse(packet['testingStarted']); self.assertIsNone(packet['ownerFinishCommandId'])
        self.assertFalse((f.comp / 'report.json').exists()); self.assertFalse((f.comp / 'dispatch.json').exists())
        self.assertTrue(all(x['result'] == 'not_run' for x in packet['componentCoverage']))
        self.assertFalse(f.p.qualification_successful_result(f.plan, packet))
        f.installed.write_bytes(b'legitimate rollback')
        self.assertEqual(f.p.qualification_collect('q-one'), packet)
        self.assertEqual(len(f.p.pipeline_status()['holds']), 1)
        self.assertEqual(f.dead.call_args.args[1], [f.worker, f.game])

    def test_partial_client_or_any_ready_evidence_cannot_use_startup_path(self):
        f = self.f; f.write(f.comp / 'dispatch.json', {'unknown': True})
        with self.assertRaisesRegex(ValueError, 'client output'): self.record()
        (f.comp / 'dispatch.json').unlink()
        f.state['gameplayBootstrap'] = {'completed': True}; f.write(f.run / 'state.json', f.state)
        with self.assertRaisesRegex(ValueError, 'ownership was reached'): self.record()
        self.assertEqual(f.p.qualification_show('q-one')['status'], 'running')

    def test_delivered_action_or_later_world_phase_refuses(self):
        f = self.f
        with (f.run / 'steps.jsonl').open('a') as out: out.write(json.dumps({'kind': 'interactive-action-delivered', 'commandId': 'a'*32})+'\n')
        with self.assertRaisesRegex(ValueError, 'action'): self.record()
        (f.run / 'steps.jsonl').write_text(json.dumps({'kind': 'phase', 'name': 'interactive-session'})+'\n')
        with self.assertRaisesRegex(ValueError, 'progressed'): self.record()

    def test_wrong_exit_and_unrestored_or_unknown_native_cannot_be_finalized(self):
        f = self.f; f.write(f.folder / 'child-exit.json', {'returncode': 0})
        with self.assertRaisesRegex(ValueError, 'exit125'): self.record()
        f.write(f.folder / 'child-exit.json', {'returncode': 125}); f.state['restored'] = False; f.write(f.run / 'state.json', f.state)
        with self.assertRaisesRegex(ValueError, 'restoration'): self.record()
        f.state['restored'] = True; f.write(f.run / 'state.json', f.state); f.dead.side_effect = ValueError('unknown native owner')
        with self.assertRaisesRegex(ValueError, 'unknown native owner'): self.record()
        self.assertFalse((f.folder / 'startup-diagnostic').exists())

    def test_transport_review_cannot_authorize_different_failure_shape(self):
        f = self.f; path = self.review(); r = m.read(path); r['kind'] = 'qualification-preclient-review'; f.write(path, r)
        with self.assertRaisesRegex(ValueError, 'operator review'): d.record(f.p, 'q-one', path, startup=True)


if __name__ == '__main__': unittest.main()

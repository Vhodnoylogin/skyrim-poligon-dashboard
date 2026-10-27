"""Ended native bootstrap failure is distinct from any admitted/missing client."""
import copy
import json
import unittest

import polygon as m
import qualification_preclient as d
import test_qualification_startup as fixture


class NativeStartupTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture.StartupTests(); self.base.setUp(); self.addCleanup(self.base.doCleanups)
        f = self.f = self.base.f
        f.state.pop('guardianRecovery')
        f.state['initialWorldTransition'] = {'completed': False, 'beforeGame': f.game}
        f.state['gameProcessObservations'] = [{'status': 'exited', 'identityVerified': True,
            'identity': f.game, 'expectedIdentity': f.game, 'exitCodeAvailable': True,
            'exitCode': 0xC0000005, 'exitCodeHex': '0xC0000005'}]
        f.state['reason'] = 'ConnectionResetError during common world preparation'
        f.write(f.run / 'state.json', f.state)
        f.write(f.folder / 'child-exit.json', {'returncode': 1})
        (f.run / 'steps.jsonl').write_text('\n'.join(json.dumps({'kind': 'phase', 'name': name}) for name in
            ('snapshot', 'start-mo2', 'start-skse', 'wait-devbench', 'se-native-startup-events',
             'gameplay-new-game-menu', 'gameplay-new-game-load', 'wait-task-queue',
             'gameplay-new-game-initial-world', 'gameplay-world-ready', 'stop-and-restore'))+'\n')
        self.dispatch = {'schemaVersion': 1, 'orderId': 'qualification-q-one', 'qualificationId': 'q-one', 'worker': f.worker}
        f.write(f.comp / 'dispatch.json', self.dispatch)

    def technical_review(self):
        f = self.f
        value = {'schemaVersion': 1, 'qualificationId': 'q-one', 'nativeRun': str(f.run),
            'nativeDoneRestoredCollected': True, 'nativeResult': 'failed', 'noClientReport': True,
            'componentActions': 0, 'componentChecksNotRun': 2, 'workerExit': {'returncode': 1},
            'gameExit': 0xC0000005,
            'dispatch': m.read(f.comp / 'dispatch.json'), 'rawPins': []}
        for directory in (f.folder, f.run):
            value['rawPins'].extend(f.pin(p) for p in sorted(directory.rglob('*')) if p.is_file())
        path = f.root / 'ended-technical-review.json'; f.write(path, value); return path

    def review(self):
        f = self.f; path = self.base.review(); value = m.read(path)
        value['dispatch'] = f.pin(f.comp / 'dispatch.json')
        value['endedTechnicalReview'] = f.pin(self.technical_review())
        f.write(path, value); return path

    def record(self): return d.record(self.f.p, 'q-one', self.review(), startup=True)

    def test_native_exit1_initial_dispatch_records_not_run_without_fabricating_client(self):
        f = self.f; packet = self.record()
        self.assertEqual(packet['kind'], d.STARTUP_KIND)
        self.assertEqual(packet['startupFailureMode'], 'native-failed-before-client')
        self.assertEqual(packet['actualGameStarts'], 1)
        self.assertIsNone(packet['cumulativeActualGameStartsBefore'])
        self.assertIsNone(packet['cumulativeActualGameStartsAfter'])
        self.assertTrue(packet['retainHold']); self.assertFalse(packet['testingStarted'])
        self.assertFalse(packet['clientRunIdentityAvailable']); self.assertIsNone(packet['ownerFinishCommandId'])
        self.assertTrue(all(row['result'] == 'not_run' for row in packet['componentCoverage']))
        self.assertEqual(m.read(f.comp / 'dispatch.json'), self.dispatch)
        self.assertEqual({p.name for p in f.comp.iterdir()}, {'dispatch.json', 'executor-manifest.json'})
        self.assertEqual(len(f.p.pipeline_status()['holds']), 1)
        self.assertFalse(f.p.qualification_successful_result(f.plan, packet))
        self.assertEqual(f.dead.call_args.args[1], [f.worker, f.game])
        f.installed.write_bytes(b'legitimate rollback after recorded collection')
        self.assertEqual(f.p.qualification_collect('q-one'), packet)
        release = {'schemaVersion': 1, 'kind': 'tool-qualification-release', 'qualificationId': 'q-one',
            'verifiedBy': 'offline operator', 'summary': 'This failed startup must remain held',
            **{key: True for key in ('successfulResultReviewed', 'collectionReviewed', 'nativeCompletionReviewed',
                                     'restorationReviewed', 'archiveReviewed')},
            'packetSha256': json.loads(f.p.qualification_show('q-one')['packet'])['sha256']}
        path = f.root / 'release-review.json'; f.write(path, release)
        with self.assertRaisesRegex(ValueError, 'Only factually successful'):
            f.p.child_qualification_release('q-one', path)
        self.assertEqual(len(f.p.pipeline_status()['holds']), 1)

    def test_any_client_intent_identity_pid_or_completion_in_dispatch_refuses(self):
        f = self.f
        for change in ({'client': {}}, {'client': {'identity': f.client}}, {'pid': 12},
                       {'nativeRun': {'runId': 'run-one'}}, {'returncode': 2}, {'error': 'unknown'}):
            with self.subTest(change=change):
                f.write(f.comp / 'dispatch.json', dict(self.dispatch, **change))
                with self.assertRaisesRegex(ValueError, 'dispatcher prefix'): self.record()
        self.assertEqual(f.p.qualification_show('q-one')['status'], 'running')

    def test_missing_client_report_after_possible_start_is_never_inferred_not_run(self):
        f = self.f
        for name in ('report.json', 'events.jsonl', 'client.log', 'inner-identity.json'):
            with self.subTest(name=name):
                path = f.comp / name; path.write_text('{}')
                with self.assertRaisesRegex(ValueError, 'client output'): self.record()
                path.unlink()
        for event in ({'kind': 'interactive-ready'}, {'kind': 'interactive-action-delivered'},
                      {'kind': 'tool', 'commandId': 'a'*32}, {'kind': 'interactive-stopped'}):
            original = (f.run / 'steps.jsonl').read_text()
            with self.subTest(event=event):
                (f.run / 'steps.jsonl').write_text(original+json.dumps(event)+'\n')
                with self.assertRaisesRegex(ValueError, 'action or readiness'): self.record()
                (f.run / 'steps.jsonl').write_text(original)

    def test_completed_world_or_interactive_state_and_wrong_owned_exit_refuse(self):
        f = self.f; original = copy.deepcopy(f.state)
        for change in ({'initialWorldTransition': {'completed': True}}, {'ownedWorldGeneration': 1},
                       {'fixtureAnchor': {'status': 'intent'}}, {'interactiveSession': {'ready': False}},
                       {'gameProcessObservations': []},
                       {'gameProcessObservations': [dict(original['gameProcessObservations'][0], identity=f.client)]}):
            with self.subTest(change=change):
                f.write(f.run / 'state.json', dict(original, **change))
                with self.assertRaises(ValueError): self.record()
        f.write(f.run / 'state.json', original)
        f.write(f.folder / 'child-exit.json', {'returncode': 2})
        with self.assertRaisesRegex(ValueError, 'exit125.*exit1'): self.record()

    def test_technical_review_and_every_raw_pin_are_mandatory_and_rechecked(self):
        f = self.f; review = self.review(); value = m.read(review)
        value.pop('endedTechnicalReview'); f.write(review, value)
        with self.assertRaisesRegex(ValueError, 'evidence pin'): d.record(f.p, 'q-one', review, startup=True)
        review = self.review(); technical = m.read(m.read(review)['endedTechnicalReview']['path'])
        technical['rawPins'][0]['sha256'] = '0'*64
        technical_path = f.root / 'ended-technical-review.json'; f.write(technical_path, technical)
        value = m.read(review); value['endedTechnicalReview'] = f.pin(technical_path); f.write(review, value)
        with self.assertRaisesRegex(ValueError, 'pin mismatch'): d.record(f.p, 'q-one', review, startup=True)

    def test_wrong_worker_unknown_death_or_unrestored_files_cannot_record(self):
        f = self.f
        f.state['runner'] = f.client; f.write(f.run / 'state.json', f.state)
        with self.assertRaisesRegex(ValueError, 'attribution'): self.record()
        f.state['runner'] = f.worker; f.write(f.run / 'state.json', f.state)
        f.target.write_text('modified')
        with self.assertRaisesRegex(ValueError, 'hash'): self.record()
        f.target.write_text('original'); f.dead.side_effect = ValueError('unknown native owner')
        with self.assertRaisesRegex(ValueError, 'unknown native owner'): self.record()
        self.assertFalse((f.folder / 'startup-diagnostic').exists())

    def test_optional_capture_phase_is_supported_only_by_native_exit1_prefix(self):
        f = self.f; steps = f.run / 'steps.jsonl'
        original = steps.read_text()
        steps.write_text(json.dumps({'kind': 'phase', 'name': 'startup-crash-capture'})+'\n'+original)
        checked = d.verify_startup_prefix(f.plan, f.folder, f.run / 'state.json')
        self.assertEqual(checked['failureMode'], 'native-failed-before-client')
        f.write(f.folder / 'child-exit.json', {'returncode': 125})
        f.state['guardianRecovery'] = {'trigger': 'guardian recovered', 'prior': {'phase': 'wait-task-queue'}}
        f.write(f.run / 'state.json', f.state); (f.comp / 'dispatch.json').unlink()
        with self.assertRaisesRegex(ValueError, 'progressed'):
            d.verify_startup_prefix(f.plan, f.folder, f.run / 'state.json')

    def test_review_raw_inventory_cannot_omit_critical_paths_or_duplicate_pins(self):
        f = self.f
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                path = self.review(); review = m.read(path)
                technical_path = f.root / 'ended-technical-review.json'; technical = m.read(technical_path)
                if duplicate: technical['rawPins'].append(technical['rawPins'][-1])
                else: technical['rawPins'] = [p for p in technical['rawPins'] if p['path'] != str(f.run / 'steps.jsonl')]
                f.write(technical_path, technical); review['endedTechnicalReview'] = f.pin(technical_path); f.write(path, review)
                with self.assertRaisesRegex(ValueError, 'duplicate or incomplete'):
                    d.record(f.p, 'q-one', path, startup=True)


if __name__ == '__main__': unittest.main()

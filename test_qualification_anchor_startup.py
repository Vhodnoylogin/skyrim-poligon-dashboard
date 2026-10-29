"""Offline synthetic evidence only; no live queue, process observer or game."""
import contextlib
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import polygon as m
import qualification_anchor_startup as d
import qualification_preclient
from qualification import inventory
import test_qualification_startup_native as fixture


class AnchorStartupTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture.NativeStartupTests(); self.base.setUp(); self.addCleanup(self.base.doCleanups)
        self.f = f = self.base.f
        f.write(f.p.local / 'config.json', {})
        executor = Path(f.plan['executor']) / 'skyrim_autotest'; executor.mkdir(parents=True)
        for name in ('runner.py', 'bootstrap.py', 'fixture_anchor.py'):
            (executor / name).write_text('# immutable offline executor source ' + name)
        f.plan['executorPins'] = inventory(f.plan['executor'])
        f.plan['configuration'].update(game_edition='se', se_fixture_anchor='qasmoke-west-navmesh-v1')
        dashboard = f.root / 'original-dashboard'; dashboard.mkdir()
        exported = f.root / 'exported-dashboard'; exported.mkdir()
        self.export_rows = []
        for name in ('polygon.py', 'qualification_companion.py'):
            original = dashboard / name; original.write_text('# immutable original ' + name)
            export = exported / name; export.write_bytes(original.read_bytes())
            f.plan['pins'].append(f.pin(original))
            self.export_rows.append({'originalPath': str(original), 'exportPath': str(export), 'sha256': m.digest(original)})
        f.state.update(ownedWorldGeneration=1, initialWorldTransition={'completed': True, 'mode': 'new-game',
            'beforeGame': f.game, 'afterGame': f.game, 'worldGeneration': 1},
            executorHashes={Path(pin['path']).name: pin['sha256'] for pin in f.plan['executorPins']})
        samples = [{'atMonotonic': 10.0, 'position': [1., 2., 3.], 'headingDegrees': 90.,
                    'positionErrorGameUnits': 12., 'headingErrorDegrees': 0.},
                   {'atMonotonic': 11.0, 'position': [2., 3., 4.], 'headingDegrees': 91.,
                    'positionErrorGameUnits': 14., 'headingErrorDegrees': 1.}]
        f.state['reason'] = d.REASON_PREFIX + repr(samples[-1])
        f.state['fixtureAnchor'] = {'recipe': 'qasmoke-west-navmesh-v1', 'status': 'uncertain',
            'preparationId': 'a' * 32, 'runId': 'run-one', 'game': f.game, 'worldGeneration': 1,
            'steps': {'MoveTo': 'returned', 'SetAngle': 'returned'}, 'samples': samples,
            'toleranceGameUnits': 4., 'toleranceDegrees': 1., 'reason': f.state['reason'],
            'provenance': {'subjectStarted': False}}
        trace = 'Traceback (most recent call last):\n' + ''.join(
            '  File "' + str(executor / name) + '", line 10, in ' + function + '\n'
            for name, function in (('runner.py', 'run'), ('bootstrap.py', 'prepare_gameplay'), ('fixture_anchor.py', 'prepare_anchor')))
        trace += 'skyrim_autotest.interactive_bindings.BindingError: ' + f.state['reason'] + '\n'
        self.steps = [{'kind': 'phase', 'name': 'snapshot'}, {'kind': 'initial-world-completed'},
                      {'kind': 'phase', 'name': 'gameplay-fixture-anchor'},
                      *[{'kind': 'fixture-anchor-readback', **sample} for sample in samples],
                      {'kind': 'exception', 'trace': trace}, {'kind': 'phase', 'name': 'stop-and-restore'}]
        self.save()
        with f.p.connect() as con:
            con.execute('UPDATE qualifications SET request=? WHERE id=?', (json.dumps(f.plan), 'q-one'))
        observer = MagicMock(); observer.SessionMutex.side_effect = contextlib.nullcontext
        self.observer_patch = patch.object(d, '_observer', return_value=observer); self.observer_patch.start(); self.addCleanup(self.observer_patch.stop)
        self.native_patch = patch.object(d, '_native', return_value={'workerAndOwnedIdentitiesVerifiedDead': True, 'processCount': 5})
        self.native = self.native_patch.start(); self.addCleanup(self.native_patch.stop)

    def save(self):
        f = self.f
        f.write(f.folder / 'plan.json', f.plan); f.write(f.run / 'state.json', f.state)
        f.write(f.run / 'result.json', {'id': f.state['id'], 'result': 'failed', 'reason': f.state['reason'],
                                      'restored': True, 'restoreErrors': []})
        f.write(f.comp / 'executor-manifest.json', {'schemaVersion': 1, 'files': f.plan['executorPins']})
        (f.run / 'steps.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in self.steps))

    def review(self):
        f = self.f
        export = f.root / 'original-export.json'
        f.write(export, {'schemaVersion': 1, 'kind': 'original-dashboard-source-export',
            'qualificationId': 'q-one', 'planSha256': m.digest(f.folder / 'plan.json'), 'files': self.export_rows})
        path = self.base.review(); value = m.read(path)
        technical_path = Path(value['endedTechnicalReview']['path'])
        technical = m.read(technical_path)
        technical['gameExit'] = next(row['exitCode'] for row in f.state['gameProcessObservations'] if row.get('status') == 'exited')
        f.write(technical_path, technical)
        value['endedTechnicalReview'] = f.pin(technical_path)
        value.update(kind='qualification-anchor-startup-review', anchorInterruptionReviewed=True,
            noClientAdmissionReviewed=True, exactSingleStartReviewed=True,
            implementationPins=d.implementation_pins(), originalDashboardExport=f.pin(export),
            observer={'path': str(f.root / 'observer.py'), 'sha256': 'e' * 64})
        # The trusted observer is mocked in these offline tests; pin checking of
        # its source occurs in _observer in production, never by importing a runner.
        observer = f.root / 'observer.py'; observer.write_text('# strict observer test placeholder')
        value['observer'] = f.pin(observer)
        f.write(path, value)
        return path

    def record(self):
        return d.record(self.f.p, 'q-one', self.review())

    def test_records_failed_anchor_without_client_or_acceptance_and_keeps_hold(self):
        f = self.f; packet = self.record()
        self.assertEqual(packet['kind'], d.KIND)
        self.assertEqual(packet['startupFailureMode'], d.MODE)
        self.assertEqual(packet['qualificationOutcome'], 'not_conducted')
        self.assertEqual(packet['actualGameStarts'], 1)
        self.assertIsNone(packet['cumulativeActualGameStartsBefore'])
        self.assertIsNone(packet['cumulativeActualGameStartsAfter'])
        self.assertEqual(packet['gameExitCode'], 0xC0000005)
        self.assertFalse(packet['causeEstablishedByCollector'])
        self.assertTrue(packet['retainHold']); self.assertFalse(packet['testingStarted'])
        self.assertFalse(packet['subjectModAccepted']); self.assertFalse(packet['globalProviderQualified'])
        self.assertFalse(packet['clientRunIdentityAvailable']); self.assertIsNone(packet['ownerFinishCommandId'])
        self.assertTrue(all(row['result'] == 'not_run' for row in packet['componentCoverage']))
        self.assertEqual({path.name for path in f.comp.iterdir()}, {'dispatch.json', 'executor-manifest.json'})
        self.assertEqual(len(f.p.pipeline_status()['holds']), 1)
        self.assertEqual(f.p.qualification_show('q-one')['status'], 'recorded')
        self.assertFalse(f.p.qualification_successful_result(f.plan, packet))
        self.assertEqual(self.native.call_args.args[1], [f.worker, f.game])
        f.installed.write_bytes(b'legitimate later installation change')
        d.verify_packet(f.p, f.plan, packet)

    def test_old_startup_prefix_stays_narrow(self):
        with self.assertRaisesRegex(ValueError, 'before world completion'):
            qualification_preclient.verify_startup_prefix(self.f.plan, self.f.folder, self.f.run / 'state.json')
        self.assertEqual(d.verify_prefix(self.f.plan, self.f.folder, self.f.run / 'state.json')['failureMode'], d.MODE)

    def test_normal_collect_verifies_diagnostic_without_demanding_a_client_report(self):
        packet = self.record()
        with patch.object(d, 'verify_packet', wraps=d.verify_packet) as verify, \
                patch('qualification_companion.verify_packet', side_effect=AssertionError('No client was started')):
            actual = self.f.p.qualification_collect('q-one')
        self.assertEqual(actual, packet)
        verify.assert_called_once()
        self.assertFalse(self.f.p.qualification_successful_result(self.f.plan, actual))
        self.assertEqual(len(self.f.p.pipeline_status()['holds']), 1)

    def test_normal_known_exit_is_separate_from_anchor_interruption(self):
        for row in self.f.state['gameProcessObservations']:
            row.update(exitCode=0, exitCodeHex='0x00000000')
        self.save(); packet = self.record()
        self.assertEqual(packet['gameExitCode'], 0)
        self.assertEqual(packet['executionOutcome'], 'failed')
        self.assertFalse(packet['qualificationPassed'])

    def test_unavailable_or_conflicting_native_exit_is_never_inferred(self):
        original = copy.deepcopy(self.f.state['gameProcessObservations'])
        for change in ({'exitCodeAvailable': False, 'exitCode': None, 'exitCodeHex': None},
                       {'identityVerified': False}, {'expectedIdentity': self.f.worker},
                       {'exitCode': True}, {'exitCodeHex': '0x00000000'}):
            with self.subTest(change=change):
                self.f.state['gameProcessObservations'] = [dict(original[0], **change)]; self.save()
                with self.assertRaisesRegex(ValueError, 'known native exit'):
                    self.record()
        self.assertEqual(self.f.p.qualification_show('q-one')['status'], 'running')

    def test_partial_client_artifacts_and_any_dispatch_intent_refuse(self):
        f = self.f
        for name in ('report.json', 'events.jsonl', 'client.log', 'inner-identity.json'):
            with self.subTest(name=name):
                path = f.comp / name; path.write_text('{}')
                with self.assertRaisesRegex(ValueError, 'client intent/output'):
                    self.record()
                path.unlink()
        initial = m.read(f.comp / 'dispatch.json')
        for key in ('client', 'nativeRun', 'returncode', 'ownedMO2Admission'):
            with self.subTest(key=key):
                f.write(f.comp / 'dispatch.json', {**initial, key: {}})
                with self.assertRaisesRegex(ValueError, 'client intent/output'):
                    self.record()
        f.write(f.comp / 'dispatch.json', initial)

    def test_readiness_registry_claim_or_component_delivery_refuses(self):
        f = self.f
        for field in ('gameplayBootstrap', 'interactiveSession', 'interactiveActorFixtures', 'interactiveArtifacts', 'morphSession'):
            with self.subTest(field=field):
                f.state[field] = {'completed': True}; self.save()
                with self.assertRaisesRegex(ValueError, 'ownership'):
                    self.record()
                del f.state[field]
        self.save(); claim = f.run / 'subject-companion.claim.json'; claim.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'ownership'):
            self.record()
        claim.unlink()
        for event in ({'kind': 'interactive-ready'}, {'kind': 'interactive-action-delivered', 'commandId': 'x'},
                      {'kind': 'gameplay-ready'}, {'kind': 'bootstrap-completed'}, {'kind': 'fixture-anchor-ready'}):
            self.steps.insert(-1, event); self.save()
            with self.assertRaises(ValueError):
                self.record()
            self.steps.pop(-2)

    def test_missing_or_reordered_anchor_raw_evidence_refuses(self):
        original = copy.deepcopy(self.steps)
        for kind in ('initial-world-completed', 'fixture-anchor-readback', 'exception'):
            with self.subTest(kind=kind):
                self.steps = [row for row in original if row['kind'] != kind]; self.save()
                with self.assertRaises(ValueError):
                    self.record()
        self.steps = copy.deepcopy(original)
        self.steps[3]['positionErrorGameUnits'] = 99; self.save()
        with self.assertRaisesRegex(ValueError, 'chronology'):
            self.record()

    def test_changed_original_executor_or_dashboard_export_refuses(self):
        executor = Path(self.f.plan['executorPins'][0]['path']); original = executor.read_bytes()
        executor.write_bytes(b'changed after original run')
        with self.assertRaises(ValueError):
            self.record()
        executor.write_bytes(original)
        exported = Path(self.export_rows[0]['exportPath']); exported.write_text('changed export')
        with self.assertRaises(ValueError):
            self.record()

    def test_restore_backup_archive_and_missing_hold_fail_closed(self):
        f = self.f; f.target.write_text('unrestored')
        with self.assertRaisesRegex(ValueError, 'restored target'):
            self.record()
        f.target.write_text('original'); (f.run / 'backups/0').write_text('wrong original')
        with self.assertRaisesRegex(ValueError, 'original backup'):
            self.record()
        (f.run / 'backups/0').write_text('original'); (f.profile / 'settings.ini').unlink()
        with self.assertRaisesRegex(ValueError, 'nonempty archived'):
            self.record()
        (f.profile / 'settings.ini').write_text('archived')
        with f.p.connect() as con:
            con.execute('DELETE FROM pipeline_holds')
        with self.assertRaisesRegex(ValueError, 'original hold'):
            self.record()

    def test_fresh_death_failure_prevents_recording(self):
        self.native.side_effect = ValueError('current process present')
        with self.assertRaisesRegex(ValueError, 'current process present'):
            self.record()
        self.assertEqual(self.f.p.qualification_show('q-one')['status'], 'running')
        self.assertFalse((self.f.folder / 'anchor-startup-diagnostic').exists())

    def test_second_start_or_unknown_exact_accounting_refuses(self):
        self.f.state['ownedGameRestartCount'] = 1; self.save()
        with self.assertRaisesRegex(ValueError, 'one consumed|accounting is unproven'):
            self.record()
        self.assertEqual(len(self.f.p.pipeline_status()['holds']), 1)

    def test_operator_reported_external_context_stays_separate_and_pinned(self):
        path = self.review(); review = m.read(path)
        evidence = self.f.root / 'owner-context.txt'; evidence.write_text('Owner reports moving the character before handoff')
        review['operatorReportedContext'] = {'summary': 'Owner-reported input before handoff; no collector cause inference', 'evidence': self.f.pin(evidence)}
        self.f.write(path, review)
        packet = d.record(self.f.p, 'q-one', path)
        self.assertEqual(packet['operatorReportedContext'], review['operatorReportedContext'])
        self.assertFalse(packet['causeEstablishedByCollector'])
        self.assertEqual(packet['gameExitCode'], 0xC0000005)
        d.verify_packet(self.f.p, self.f.plan, packet)

    def test_cached_evidence_or_archive_tampering_refuses(self):
        packet = self.record()
        changed = copy.deepcopy(packet); changed['gameExitCode'] = 0
        with self.assertRaisesRegex(ValueError, 'observed exit'):
            d.verify_packet(self.f.p, self.f.plan, changed)
        changed = copy.deepcopy(packet); changed['componentCoverage'][0]['result'] = 'passed'
        with self.assertRaisesRegex(ValueError, 'coverage'):
            d.verify_packet(self.f.p, self.f.plan, changed)
        (self.f.profile / 'added.ini').write_text('changed archive membership')
        with self.assertRaisesRegex(ValueError, 'archive'):
            d.verify_packet(self.f.p, self.f.plan, packet)


if __name__ == '__main__':
    unittest.main()

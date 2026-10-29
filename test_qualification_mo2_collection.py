"""Isolated failed-run lifecycle proof; all native observations are mocked."""
from contextlib import nullcontext
import copy
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import polygon as m
import qualification_diagnostic as diagnostic
import qualification_mo2_boundary as boundary
import qualification_mo2_collection as collection
import test_qualification as fixtures


class ManagedMo2CollectionTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.QualificationTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.p, self.root = self.f.p, self.f.root
        self.identity = 'candidate-one'
        self.original = b'[General]\nselected_profile=Core\n[Geometry]\nMainWindow_geometry=old\n'
        self.native_ini = self.original.replace(b'=old', b'=new')
        self.f.ini.write_bytes(self.original)
        self.f.config.update(game_edition='se', mo2_ini=str(self.f.ini), mo2_exe=str(self.root / 'ModOrganizer.exe'))
        self.f.order['inputs'] = [self.pin(self.f.ini)]
        m.write(self.root / 'config.json', self.f.config)
        m.write(self.root / 'order.json', self.f.order)
        self.f.unknown_accounting_fixture()
        self.f.register()
        self.plan = json.loads(self.p.qualification_show(self.identity)['request'])
        self.folder = self.p.local / 'qualifications' / self.identity
        self.folder.mkdir(parents=True)
        self.run = Path(self.f.config['runtime']) / 'runs/actual'
        self.archive = self.run / 'test-profile'
        self.archive.mkdir(parents=True)
        (self.archive / 'settings.ini').write_text('Preserved archive')
        self.backup = self.run / 'backups/0'
        self.backup.parent.mkdir()
        self.backup.write_bytes(self.native_ini)
        self.f.ini.write_bytes(self.native_ini)
        self.origin = self.root / 'origin/backups/0'
        self.origin.parent.mkdir(parents=True)
        self.origin.write_bytes(self.original)
        m.write(self.origin.parent.parent / 'state.json', {'snapshots': [
            {'path': str(self.f.ini), 'exists': True, 'backup': str(self.origin), 'sha256': self.pin(self.origin)['sha256']}]})
        self.worker = {'pid': 111, 'birth': 2, 'path': str(self.root / 'python.exe')}
        self.game = {'pid': 222, 'birth': 3, 'path': str(self.root / 'SkyrimSE.exe')}
        self.manager = {'pid': 333, 'birth': 4, 'path': self.f.config['mo2_exe']}
        self.runner = self.f.candidate / 'skyrim_autotest/runner.py'
        self.runner_sha = m.digest(self.runner)
        self.state = {'id': 'actual', 'order': {'id': 'qualification-' + self.identity}, 'runner': self.worker,
            'configuration': self.plan['configuration'], 'result': 'failed', 'done': True, 'restored': True,
            'restoreErrors': [], 'collectionComplete': True, 'collectionErrors': [],
            'owned': [{'role': 'game', 'identity': self.game}], 'game': self.game,
            'profileArchive': str(self.archive), 'testProfile': str(self.run / 'removed'),
            'preflight': {'idleMO2': self.manager}, 'executorHashes': {'runner.py': self.runner_sha},
            'snapshots': [{'path': str(self.f.ini), 'exists': True, 'backup': str(self.backup), 'sha256': m.digest(self.backup)}],
            'gameTermination': {'kind': 'abnormal_exit', 'game': self.game, 'identityVerified': True,
                'ownQuitRequest': True, 'forcedGameStop': False, 'exitCode': 0xC0000005}}
        self.result = {'id': 'actual', 'result': 'failed', 'restored': True, 'restoreErrors': [],
                       'checks': [{'name': 'tool-check', 'result': 'passed'}], 'reason': 'Owned shutdown AV'}
        m.write(self.folder / 'plan.json', self.plan)
        m.write(self.folder / 'worker.json', {'identity': self.worker})
        m.write(self.folder / 'child-exit.json', {'returncode': 1})
        self.steps = [{'kind': 'idle-mo2-graceful-close', 'identity': self.manager,
                       'request': {'requested': True, 'systemCommand': True, 'windows': [{'accepted': True}]}}]
        self.steps_path = self.run / 'steps.jsonl'
        self.steps_path.write_text('\n'.join(json.dumps(x) for x in self.steps), encoding='utf-8')
        with self.p.connect() as con:
            con.execute("UPDATE qualifications SET status='running',expires=100 WHERE id=?", (self.identity,))
            con.execute('INSERT INTO attempts VALUES(?,1)', ('qualification-' + self.identity,))
        export = self.root / 'export'
        export.mkdir()
        exported = []
        for pin in self.plan['pins']:
            source = Path(pin['path'])
            if source.parent == m.HERE and source.suffix == '.py':
                target = export / source.name
                shutil.copyfile(source, target)
                exported.append({'originalPath': str(source), 'exportPath': str(target), 'sha256': pin['sha256']})
        self.export = self.root / 'export.json'
        m.write(self.export, {'schemaVersion': 1, 'kind': 'original-dashboard-source-export', 'qualificationId': self.identity,
                             'planSha256': m.digest(self.folder / 'plan.json'), 'files': exported})
        self.proof_path = self.root / 'boundary.json'
        self.observer_path = self.root / 'observer.py'
        self.observer_path.write_text('# Never imported; native observations mocked')
        self.review_path = self.root / 'collection-review.json'
        self.sync()
        self.review = {'schemaVersion': 1, 'kind': 'qualification-managed-mo2-collection-review',
            'qualificationId': self.identity, 'verifiedBy': 'Independent synthetic reviewer', 'summary': 'Failed native exit',
            **{key: True for key in collection.FLAGS}, 'managedMo2IniBoundary': self.pin(self.proof_path),
            'originalDashboardExport': self.pin(self.export), 'implementationPins': diagnostic.implementation_pins(),
            'state': self.pin(self.run / 'state.json'), 'result': self.pin(self.run / 'result.json'),
            'worker': self.pin(self.folder / 'worker.json'), 'childExit': self.pin(self.folder / 'child-exit.json'),
            'managerCloseSteps': self.pin(self.steps_path),
            'observer': self.pin(self.observer_path), 'profileArchivePins': [self.pin(self.archive / 'settings.ini')],
            'profileArchiveDirectories': []}
        self.rows = [{'pid': 999, 'name': 'python.exe'}]
        self.native = SimpleNamespace(SessionMutex=nullcontext, processes=lambda: self.rows,
                                     alive=lambda ident: False, identity=lambda pid: None)
        for mock in (patch.object(boundary, 'RUNNER_SHA256', self.runner_sha),
                     patch.object(collection, '_observer', return_value=self.native)):
            mock.start()
            self.addCleanup(mock.stop)

    def pin(self, path):
        return {'path': str(path), 'sha256': m.digest(path)}

    def sync(self):
        m.write(self.run / 'state.json', self.state)
        m.write(self.run / 'result.json', self.result)
        snapshot = self.state['snapshots'][0]
        self.proof = {'schemaVersion': 1, 'kind': 'read-only-pre-dispatch-versus-native-INI-baseline-review',
            'qualificationId': self.identity, 'runId': 'actual',
            'artifacts': [self.pin(path) for path in (self.folder / 'plan.json', self.run / 'state.json',
                         self.run / 'result.json', self.folder / 'worker.json', self.folder / 'child-exit.json',
                         self.origin.parent.parent / 'state.json')],
            'baselineBoundaries': {'immutableQualificationPin': dict(self.pin(self.f.ini),
                sha256=m.digest(self.origin), originalByteCopyAvailable=self.pin(self.origin)),
                'nativeSnapshotAfterIdleManagerClose': {'snapshot': copy.deepcopy(snapshot), 'backup': self.pin(self.backup)},
                'currentINI': self.pin(self.f.ini)}, 'nativeCompletion': {'snapshotCountRehashed': len(self.state['snapshots'])},
            'safeINIComparison': {'changedKeysOnlyValuesRedacted': [{'section': 'Geometry', 'key': 'MainWindow_geometry'}]}}
        m.write(self.proof_path, self.proof)
        if hasattr(self, 'review'):
            self.review.update(managedMo2IniBoundary=self.pin(self.proof_path), state=self.pin(self.run / 'state.json'),
                               result=self.pin(self.run / 'result.json'))

    def record(self):
        m.write(self.review_path, self.review)
        return collection.record(self.p, self.identity, self.review_path)

    def refuses(self):
        before = self.p.db.read_bytes()
        with self.assertRaises(ValueError):
            self.record()
        self.assertEqual(self.p.db.read_bytes(), before)
        self.assertEqual(self.p.qualification_show(self.identity)['status'], 'running')
        self.assertFalse((self.folder / collection.POINTER).exists())

    def test_failed_normal_packet_keeps_exact_start_null_cumulative_hold_and_originals(self):
        originals = {path: path.read_bytes() for path in (self.folder / 'plan.json', self.run / 'state.json',
                                                        self.run / 'result.json', self.f.ini)}
        request = self.p.qualification_show(self.identity)['request']
        packet = self.record()
        self.assertEqual(packet['kind'], 'tool-qualification-result')
        self.assertEqual(packet['executionOutcome'], 'failed')
        self.assertEqual(packet['actualGameStarts'], 1)
        self.assertIsNone(packet['cumulativeActualGameStartsAfter'])
        self.assertFalse(packet['qualificationPassed'])
        self.assertFalse(self.p.qualification_successful_result(self.plan, packet))
        self.assertEqual(len(self.p.pipeline_status()['holds']), 1)
        self.assertEqual(self.p.qualification_show(self.identity)['request'], request)
        for path, raw in originals.items():
            self.assertEqual(path.read_bytes(), raw)
        frozen = self.folder / collection.SNAPSHOTS
        self.assertEqual((frozen / 'registration-ModOrganizer.ini').read_bytes(), self.original)
        self.assertEqual((frozen / 'native-ModOrganizer.ini').read_bytes(), self.native_ini)
        self.assertNotIn(str(self.f.ini), {item['path'] for item in packet['files']})

    def test_cache_survives_later_gui_input_and_executor_changes_but_checks_archive(self):
        packet = self.record()
        self.f.ini.write_bytes(self.native_ini.replace(b'=new', b'=later'))
        self.runner.write_text('# Later independently authorized candidate')
        self.assertEqual(self.p.qualification_collect(self.identity), packet)
        self.assertEqual(collection.record(self.p, self.identity, self.review_path), packet)
        (self.archive / 'unexpected').write_text('Extra archived file')
        with self.assertRaisesRegex(ValueError, 'archive membership'):
            self.p.qualification_collect(self.identity)

    def test_generic_verification_still_refuses_original_pin_and_failed_release_refuses(self):
        packet = self.record()
        for authority in (True, False):
            with self.assertRaisesRegex(ValueError, 'Qualification pin changed'):
                self.p.qualification_verify(self.p.qualification_show(self.identity), authority=authority)
        self.f.ini.write_bytes(self.original)  # Isolated adversary tries to appease generic pin validation.
        release = {'schemaVersion': 1, 'kind': 'tool-qualification-release', 'qualificationId': self.identity,
            'verifiedBy': 'Synthetic operator', 'summary': 'Cannot qualify failed exit',
            **{key: True for key in ('successfulResultReviewed', 'collectionReviewed', 'nativeCompletionReviewed', 'restorationReviewed', 'archiveReviewed')},
            'packetSha256': json.loads(self.p.qualification_show(self.identity)['packet'])['sha256']}
        path = self.root / 'release.json'
        m.write(path, release)
        with self.assertRaisesRegex(ValueError, 'Only factually successful'):
            self.p.child_qualification_release(self.identity, path)

    def test_non_gui_change_rehashed_into_native_proof_is_not_accepted(self):
        raw = self.native_ini.replace(b'selected_profile=Core', b'selected_profile=Other')
        self.backup.write_bytes(raw)
        self.f.ini.write_bytes(raw)
        self.state['snapshots'][0]['sha256'] = m.digest(self.backup)
        self.sync()
        self.refuses()

    def test_duplicate_and_unparsed_ini_records_are_not_gui_normalization(self):
        for raw in (self.native_ini + b'MainWindow_geometry=duplicate\n', self.native_ini + b'not-an-ini-record\n'):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    boundary.gui_delta(self.original, raw)

    def test_original_copy_source_close_or_native_snapshot_mismatch_refuses(self):
        self.origin.write_bytes(b'Unproven original bytes')
        self.sync()
        self.refuses()

    def test_wrong_manager_close_or_candidate_source_refuses(self):
        self.steps[0]['identity'] = dict(self.manager, birth=999)
        self.steps_path.write_text(json.dumps(self.steps[0]), encoding='utf-8')
        self.review['managerCloseSteps'] = self.pin(self.steps_path)
        self.refuses()

    def test_changed_candidate_source_is_not_the_reviewed_close_control_flow(self):
        self.runner.write_text('# Changed original executed runner')
        self.refuses()

    def test_review_swap_before_lock_cannot_create_pointer_or_snapshot(self):
        def changing_observer(pin):
            m.write(self.review_path, dict(self.review, summary='Different bytes after initial read'))
            return self.native
        with patch.object(collection, '_observer', side_effect=changing_observer):
            self.refuses()
        self.assertFalse((self.folder / collection.SNAPSHOTS).exists())

    def swap_after_verify(self, target):
        original_verify = collection.verify
        def swapping_verify(*args, **kwargs):
            captured = original_verify(*args, **kwargs)
            if target == 'pointer':
                replacement = self.root / 'replacement-review.json'
                m.write(replacement, dict(self.review, summary='Unverified replacement review'))
                m.write(self.folder / collection.POINTER, self.pin(replacement))
            else:
                m.write(self.run / 'result.json', dict(self.result, reason='Replaced after verification'))
            return captured
        with patch.object(collection, 'verify', side_effect=swapping_verify):
            with self.assertRaisesRegex(ValueError, 'pin mismatch'):
                self.record()
        row = self.p.qualification_show(self.identity)
        self.assertEqual(row['status'], 'running')
        self.assertIsNone(row['packet'])
        self.assertFalse((self.folder / 'packet.json').exists())
        self.assertEqual(len(self.p.pipeline_status()['holds']), 1)

    def test_pointer_swap_after_verify_before_packet_assembly_is_not_adopted(self):
        self.swap_after_verify('pointer')

    def test_evidence_swap_after_verify_before_packet_write_is_not_adopted(self):
        self.swap_after_verify('result')

    def test_another_original_input_drift_is_not_waived(self):
        (self.root / 'scenario.json').write_text('{"changed":true}')
        self.refuses()

    def test_passed_unrestored_or_second_game_native_result_is_not_supported(self):
        for key, value in (('result', 'passed'), ('restored', False)):
            with self.subTest(key=key):
                original = self.state[key]
                self.state[key] = value
                self.sync()
                self.refuses()
                self.state[key] = original
        self.state['owned'].append({'role': 'game', 'identity': dict(self.game, pid=444)})
        self.sync()
        self.refuses()

    def test_live_worker_unknown_inventory_or_foreign_game_refuses(self):
        for rows in ([], [{'pid': 5555, 'name': 'SkyrimSE.exe'}], [{'pid': self.worker['pid'], 'name': 'python.exe'}]):
            with self.subTest(rows=rows):
                self.rows = rows
                self.refuses()

    def test_changed_archive_or_own_reservation_never_yields_packet(self):
        (self.archive / 'extra').write_text('Archive changed')
        self.refuses()

    def test_interrupted_snapshot_artifact_is_never_overwritten_or_adopted(self):
        snapshots = self.folder / collection.SNAPSHOTS
        snapshots.mkdir()
        (snapshots / 'orphan').write_text('Preserve for review')
        self.refuses()
        self.assertEqual((snapshots / 'orphan').read_text(), 'Preserve for review')


if __name__ == '__main__':
    unittest.main()

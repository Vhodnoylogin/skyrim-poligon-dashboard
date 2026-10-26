"""Ended-attempt additive repair uses only temporary files and mocked observers."""
import copy
from contextlib import contextmanager, nullcontext
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import companion_collection_repair as repair


class CompanionCollectionRepairTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.local = self.root / 'local'; self.attempt = 'ended-retry-1'
        self.folder = self.local / 'retry-attempts' / self.attempt; self.folder.mkdir(parents=True)
        self.run = self.root / 'runtime/runs/native-run'; self.run.mkdir(parents=True)
        self.archive = self.run / 'test-profile'; self.archive.mkdir(); (self.archive / 'empty-directory').mkdir()
        self.write(self.archive / 'modlist.txt', 'exact archived profile')
        self.target = self.root / 'live/manager.ini'; self.target.parent.mkdir(); self.write(self.target, 'restored bytes')
        self.source = self.root / 'reviewed-implementation'; self.source.mkdir()
        self.write(self.source / 'collector.py', '# reviewed additive collector')
        self.write(self.source / 'projection.py', '# reviewed projection hook')
        source_patch = patch.object(repair, 'api', return_value=SimpleNamespace(HERE=self.source))
        source_patch.start(); self.addCleanup(source_patch.stop)
        self.scope_impl = repair.native_scope
        scope_patch = patch.object(repair, 'native_scope', side_effect=lambda *args: nullcontext())
        scope_patch.start(); self.addCleanup(scope_patch.stop)
        self.order = {'schemaVersion': 2, 'id': 'original-subject', 'sourceChat': 'origin', 'sourceThreadId': 'real-origin',
            'subjectPlan': {'interface': 'polygon-file-plan/1'}}
        self.configuration = {'runtime': str(self.root / 'runtime')}
        self.provider = self.root / 'original-provider.dll'; self.write(self.provider, 'original frozen provider')
        self.platform = {'executor': str(self.root / 'frozen-executor'), 'configuration': self.configuration, 'pins': [repair.pin(self.provider)]}
        self.write(self.folder / 'platform-plan.json', self.platform)
        self.write(self.folder / 'scenario.json', {'cell': 'QASmoke', 'steps': []})
        self.worker = {'pid': 101, 'birth': 111, 'path': str(self.root / 'python.exe')}
        self.game = {'pid': 202, 'birth': 222, 'path': str(self.root / 'SkyrimSE.exe')}
        self.reason = 'Interactive session ended: Unique declared native function metadata is unavailable'
        self.state = {'id': self.run.name, 'order': {'id': self.order['id'], 'attemptId': self.attempt,
            'subjectOrderId': self.order['id'], 'owner': 'origin'}, 'configuration': self.configuration,
            'scenarioHash': repair.pin(self.folder / 'scenario.json')['sha256'], 'done': True, 'restored': True,
            'restoreErrors': [], 'result': 'failed', 'reason': self.reason, 'collectionComplete': True, 'collectionErrors': [],
            'runner': self.worker, 'game': self.game, 'owned': [{'role': 'game', 'identity': self.game}],
            'snapshots': [{'path': str(self.target), 'exists': True, 'sha256': repair.pin(self.target)['sha256']},
                {'path': str(self.root / 'live/absent.dll'), 'exists': False}],
            'profileArchive': str(self.archive), 'testProfile': str(self.root / 'removed-profile'),
            'gameProcessObservations': [{'status': 'exited', 'exitCode': 3221225477, 'exitCodeHex': '0xC0000005'}]}
        self.write(self.run / 'state.json', self.state)
        self.result = {key: self.state[key] for key in ('id', 'result', 'reason', 'restored', 'restoreErrors', 'collectionComplete', 'collectionErrors')}
        self.write(self.run / 'result.json', self.result)
        self.report_path = self.folder / 'subject-companion/report.json'
        self.write(self.report_path, {'schemaVersion': 1, 'orderId': self.order['id'], 'attemptId': self.attempt,
            'runId': self.run.name, 'done': True, 'subjectStarted': True, 'uncertain': True, 'completed': False,
            'cases': [{'id': 'catalog', 'status': 'passed'}, {'id': 'human-preset', 'status': 'unavailable'}]})
        self.write(self.folder / 'child-exit.json', {'returncode': 1})
        self.companion = {'reportPin': repair.pin(self.report_path), 'pins': [repair.pin(self.report_path)],
            'checks': [{'name': 'catalog', 'result': 'passed'}, {'name': 'human-preset', 'result': 'unavailable'}],
            'subjectStarted': True, 'uncertain': True, 'completed': False}
        self.raw = {'schemaVersion': 1, 'attemptId': self.attempt, 'orderId': self.order['id'], 'sourceChat': 'origin',
            'sourceThreadId': 'real-origin', 'executionOutcome': 'failed', 'reason': self.reason, 'runDirectory': str(self.run),
            'restored': True, 'subjectCompanion': self.companion, 'launchAccounting': {'subjectActualLaunchesBefore': 0,
                'thisAttemptActualGameStarts': 1, 'subjectActualLaunchesAfter': 1, 'maximumSubjectActualLaunches': 1},
            'subjectOrderSha256': hashlib.sha256(repair.encoded(self.order)).hexdigest(),
            'files': [repair.pin(path) for path in (self.run / 'state.json', self.run / 'result.json', self.report_path,
                self.folder / 'child-exit.json', self.folder / 'scenario.json', self.folder / 'platform-plan.json')]}
        self.packet = self.folder / 'packet.json'; self.write(self.packet, self.raw)
        self.original_bytes = self.packet.read_bytes()
        self.database = self.root / 'db.sqlite3'
        with self.connect() as con:
            con.executescript('''CREATE TABLE retry_attempts(id TEXT,status TEXT,packet TEXT,request TEXT,report TEXT);
              CREATE TABLE pipeline_holds(id TEXT,reason TEXT); CREATE TABLE jobs(id TEXT,status TEXT);
              CREATE TABLE qualifications(id TEXT,status TEXT); CREATE TABLE game_sessions(id TEXT,status TEXT);''')
            con.execute('INSERT INTO retry_attempts VALUES(?,?,?,?,NULL)', (self.attempt, 'recorded', str(self.packet),
                json.dumps({'kind': 'companion-pre-session', 'id': self.attempt, 'orderId': self.order['id']})))
            con.execute('INSERT INTO pipeline_holds VALUES(?,?)', (self.attempt, 'Uncertain technical outcome; retain'))
        self.p = SimpleNamespace(local=self.local, connect=self.connect, retry_show=self.retry_show,
            retry_order=lambda _: copy.deepcopy(self.order), verify_packet=self.verify_packet,
            verify_platform=Mock(side_effect=self.verify_platform), native_game_starts=Mock(return_value=1),
            verify_companion_processes_dead=Mock(return_value=True), host=lambda: {})
        collect_patch = patch.object(repair, 'collect', return_value=self.companion)
        collect_patch.start(); self.addCleanup(collect_patch.stop)
        self.review = {'schemaVersion': 1, 'kind': 'companion-ended-collection-repair', 'attemptId': self.attempt,
            'packet': repair.pin(self.packet), 'platformPlan': repair.pin(self.folder / 'platform-plan.json'),
            'state': repair.pin(self.run / 'state.json'), 'result': repair.pin(self.run / 'result.json'),
            'childExit': repair.pin(self.folder / 'child-exit.json'), 'companionReport': repair.pin(self.report_path),
            'profileArchive': repair._archive(self.run)[0], 'implementationPins': repair.implementations(),
            'verifiedBy': 'independent offline fixture', 'reason': 'Only missing archive manifest; uncertain native result unchanged',
            **{flag: True for flag in repair.FLAGS}}
        self.review_path = self.root / 'review.json'; self.write(self.review_path, self.review)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value.encode() if isinstance(value, str) else repair.encoded(value))

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.database); con.row_factory = sqlite3.Row
        try:
            with con: yield con
        finally: con.close()

    def retry_show(self, attempt):
        with self.connect() as con: return dict(con.execute('SELECT * FROM retry_attempts WHERE id=?', (attempt,)).fetchone())

    def verify_packet(self, row):
        packet = repair.read(row['packet'])
        for item in packet['files']: repair.checked(item)
        return self.order, packet

    def verify_platform(self, order, attempt_id=None):
        self.assertEqual(attempt_id, self.attempt)
        for item in self.platform['pins']: repair.checked(item)
        return self.platform

    def record(self): return repair.record(self.p, self.attempt, self.review_path)

    def test_additive_view_preserves_old_packet_uncertainty_and_hold(self):
        original_row = self.retry_show(self.attempt)
        receipt = self.record()
        self.assertFalse(receipt['duplicate']); self.assertTrue(receipt['holdRetained'])
        self.assertEqual(self.packet.read_bytes(), self.original_bytes)
        self.assertEqual(self.retry_show(self.attempt), original_row)
        with self.connect() as con: self.assertEqual(con.execute('SELECT COUNT(*) FROM pipeline_holds').fetchone()[0], 1)
        view = repair.apply(self.p, original_row, self.raw)
        self.assertEqual({key: view[key] for key in self.raw if key != 'files'}, {key: self.raw[key] for key in self.raw if key != 'files'})
        self.assertTrue(view['subjectCompanion']['uncertain']); self.assertFalse(view['subjectCompanion']['completed'])
        self.assertTrue(any(Path(item['path']).name == 'profile-archive.json' for item in view['files']))
        self.assertEqual(repair.read(receipt['collectionRepair']['path'])['archiveEvidence'], {
            'originalFilePinCount': 0, 'inventoryBasis': 'reviewed-current-ended-owned-profile',
            'historicalFileContinuityEstablished': False})
        self.assertEqual(self.state['gameProcessObservations'][0]['exitCodeHex'], '0xC0000005')
        self.assertEqual(self.record()['duplicate'], True)

    def test_no_supplement_returns_original_view(self):
        self.assertIs(repair.apply(self.p, self.retry_show(self.attempt), self.raw), self.raw)

    def test_changed_original_pin_archive_or_empty_directory_refuses(self):
        self.record()
        for target in (self.archive / 'modlist.txt', self.folder / 'scenario.json'):
            data = target.read_bytes(); target.write_bytes(b'changed')
            with self.subTest(target=target), self.assertRaises(ValueError): repair.apply(self.p, self.retry_show(self.attempt), self.raw)
            target.write_bytes(data)
        (self.archive / 'new-empty-directory').mkdir()
        with self.assertRaisesRegex(ValueError, 'membership'): repair.apply(self.p, self.retry_show(self.attempt), self.raw)

    def test_wrong_run_and_live_process_or_missing_hold_refuse(self):
        self.review['state'] = self.review['result']; self.write(self.review_path, self.review)
        with self.assertRaisesRegex(ValueError, 'path/hash'): self.record()
        self.review['state'] = repair.pin(self.run / 'state.json'); self.write(self.review_path, self.review)
        self.p.verify_companion_processes_dead.return_value = False
        with self.assertRaisesRegex(ValueError, 'process death'): self.record()
        self.p.verify_companion_processes_dead.return_value = True
        with self.connect() as con: con.execute('DELETE FROM pipeline_holds')
        with self.assertRaisesRegex(ValueError, 'fault hold'): self.record()

    def test_restored_target_and_second_start_cannot_be_attested(self):
        self.target.write_bytes(b'foreign changed configuration')
        with self.assertRaisesRegex(ValueError, 'restored target'): self.record()
        self.target.write_bytes(b'restored bytes'); self.p.native_game_starts.return_value = 2
        with self.assertRaisesRegex(ValueError, 'single-start'): self.record()

    def test_implementation_drift_or_pointer_review_change_refuses(self):
        self.record()
        self.write(self.source / 'collector.py', '# unreviewed implementation')
        with self.assertRaisesRegex(ValueError, 'path/hash'): repair.apply(self.p, self.retry_show(self.attempt), self.raw)
        self.write(self.source / 'collector.py', '# reviewed additive collector')
        other = self.root / 'other-review.json'; other.write_bytes(self.review_path.read_bytes())
        with self.assertRaisesRegex(ValueError, 'immutable'): repair.record(self.p, self.attempt, other)

    def test_partial_archive_subset_cannot_silently_adopt_new_files(self):
        self.raw['files'].append(repair.pin(self.archive / 'modlist.txt'))
        self.write(self.packet, self.raw); self.review['packet'] = repair.pin(self.packet)
        self.write(self.archive / 'unpublished.ess', 'unknown later save')
        self.review['profileArchive'] = repair._archive(self.run)[0]; self.write(self.review_path, self.review)
        with self.assertRaisesRegex(ValueError, 'retained original file inventory'): self.record()

    def test_complete_retained_file_inventory_is_marked_without_directory_history_claim(self):
        self.raw['files'].append(repair.pin(self.archive / 'modlist.txt'))
        self.write(self.packet, self.raw); self.review['packet'] = repair.pin(self.packet); self.write(self.review_path, self.review)
        receipt = self.record()
        self.assertEqual(repair.read(receipt['collectionRepair']['path'])['archiveEvidence'], {
            'originalFilePinCount': 1, 'inventoryBasis': 'retained-original-file-pins',
            'historicalFileContinuityEstablished': True})

    def test_late_proof_failure_does_not_publish_partial_repair(self):
        self.p.verify_companion_processes_dead.side_effect = [True, ValueError('Native inventory became unavailable')]
        with self.assertRaisesRegex(ValueError, 'inventory became unavailable'): self.record()
        self.assertFalse((self.folder / 'collection-repair').exists())
        self.assertFalse(list(self.folder.glob('.collection-repair-*')))
        self.assertEqual(self.packet.read_bytes(), self.original_bytes)

    def test_registered_final_report_or_active_owner_refuses_new_repair(self):
        with self.connect() as con: con.execute('UPDATE retry_attempts SET report=?', ('retained-final-report',))
        with self.assertRaisesRegex(ValueError, 'final report'): self.record()
        with self.connect() as con:
            con.execute('UPDATE retry_attempts SET report=NULL')
            con.execute('INSERT INTO jobs VALUES(?,?)', ('foreign-job', 'running'))
        with self.assertRaisesRegex(ValueError, 'unfinished owner'): self.record()

    def test_selected_native_scope_refuses_foreign_game_vr_or_unknown_inventory(self):
        observer = SimpleNamespace(SessionMutex=nullcontext, processes=Mock(return_value=[{'pid': 909, 'name': 'explorer.exe'}]))
        runner = SimpleNamespace(native=observer, GAME_NAMES={'skyrimse.exe'}, VR_NAMES={'vrserver.exe'})
        with patch('order_platform.activate', return_value=runner) as activate:
            with self.scope_impl(self.p, self.order, self.attempt): pass
            activate.assert_called_with(self.platform['executor'])
            for rows in ([], [{'pid': 1, 'name': 'SkyrimSE.exe'}], [{'pid': 2, 'name': 'vrserver.exe'}], [{'name': 'unknown.exe'}]):
                observer.processes.return_value = rows
                with self.subTest(rows=rows), self.assertRaises(ValueError):
                    with self.scope_impl(self.p, self.order, self.attempt): pass

    def test_history_survives_new_export_owner_and_legitimate_live_target_changes(self):
        import companion_evidence
        self.record()
        view = repair.apply(self.p, self.retry_show(self.attempt), self.raw)
        self.write(self.source / 'new-current-module.py', '# later unrelated addition')
        self.target.write_bytes(b'legitimate later session configuration')
        Path(self.state['testProfile']).mkdir()
        with self.connect() as con:
            con.execute('DELETE FROM pipeline_holds')
            con.execute('INSERT INTO pipeline_holds VALUES(?,?)', ('new-owner', 'Legitimate later owner'))
            con.execute('INSERT INTO jobs VALUES(?,?)', ('new-owner', 'running'))
        self.p.verify_platform.side_effect = AssertionError('History must not re-admit old platform')
        self.p.verify_companion_processes_dead.side_effect = AssertionError('History must not inspect current OS')
        self.p.native_game_starts.side_effect = AssertionError('History uses closed start evidence')
        with patch.object(repair, 'collect', side_effect=AssertionError('History must not recollect current runtime')):
            self.assertEqual(repair.apply(self.p, self.retry_show(self.attempt), self.raw), view)
            new_export = self.root / 'new-current-export'; new_export.mkdir()
            self.write(new_export / 'different-module.py', '# legitimate current implementation')
            with patch.object(repair, 'api', return_value=SimpleNamespace(HERE=new_export)):
                self.assertEqual(repair.projection(self.p, self.order, view), self.companion)
                self.assertEqual(companion_evidence.projection(self.p, self.order, view), self.companion)

    def test_history_rejects_old_implementation_snapshot_or_verification_proof_tampering(self):
        receipt = self.record(); root = self.folder / 'collection-repair'
        for path in (root / 'implementation/collector.py', root / 'verification-proof.json'):
            data = path.read_bytes(); path.write_bytes(b'changed old proof')
            with self.subTest(path=path), self.assertRaises(ValueError):
                repair.projection(self.p, self.order, repair.apply(self.p, self.retry_show(self.attempt), self.raw))
            path.write_bytes(data)
        supplement = repair.read(receipt['collectionRepair']['path'])
        self.assertEqual(supplement['verificationProof']['path'], str(root / 'verification-proof.json'))

    def test_unregistered_reserved_repair_tags_cannot_skip_initial_gates(self):
        for key in ('collectionRepair', 'originalPacket'):
            forged = dict(self.raw, **{key: {'path': 'forged', 'sha256': '0' * 64}})
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'reserved repair tags'):
                repair.apply(self.p, self.retry_show(self.attempt), forged)


if __name__ == '__main__': unittest.main()

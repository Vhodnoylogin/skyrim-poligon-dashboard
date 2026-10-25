import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
import polygon as m
import qualification_collection_repair as repair


class PatchTests(unittest.TestCase):
    def test_exact_single_line_only(self):
        original = 'before\n' + repair.ANCHOR + 'after\n'
        current = original.replace(repair.ANCHOR, repair.ANCHOR + repair.LINE)
        repair.validate_patch(original, current)
        for changed in (original, current + '# extra\n', current.replace('after', 'changed'), current + repair.LINE):
            with self.subTest(changed=changed), self.assertRaises(ValueError): repair.validate_patch(original, changed)
        with self.assertRaises(ValueError): repair.validate_patch(current, current)


class ProofGuardTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup); self.root = Path(tmp.name)
        self.folder = self.root / 'qualifications/q'; self.folder.mkdir(parents=True)
        self.run = self.root / 'runtime/runs/run'; self.run.mkdir(parents=True)
        archive = self.run / 'test-profile'; archive.mkdir(); (archive / 'settings.ini').write_text('preserved')
        self.worker = {'pid': 10, 'birth': 11, 'path': str(self.root / 'python.exe')}
        self.game = {'pid': 20, 'birth': 21, 'path': str(self.root / 'SkyrimSE.exe')}
        self.state = {'id': 'run', 'runner': self.worker, 'order': {'id': 'qualification-q'},
                      'done': True, 'restored': True, 'restoreErrors': [], 'result': 'passed', 'reason': None,
                      'profileArchive': str(archive), 'testProfile': str(self.root / 'removed-profile'),
                      'game': self.game, 'owned': [{'role': 'game', 'identity': self.game}]}
        self.result = {'id': 'run', 'result': 'passed', 'reason': None, 'restored': True, 'restoreErrors': []}
        self.plan = {'id': 'q', 'configuration': {'runtime': str(self.root / 'runtime')}}
        self.row = {'request': json.dumps(self.plan)}
        self.con = sqlite3.connect(':memory:'); self.con.row_factory = sqlite3.Row; self.addCleanup(self.con.close)
        self.con.execute('CREATE TABLE qualifications(id TEXT,request TEXT,status TEXT)')
        self.con.execute('CREATE TABLE attempts(id TEXT)')
        self.con.execute("INSERT INTO qualifications VALUES('q',?,'running')", (self.row['request'],))
        self.con.execute("INSERT INTO attempts VALUES('qualification-q')")
        self.p = SimpleNamespace(local=self.root, qualification_guard=Mock(), host=lambda: {}, native_game_starts=lambda state: 1)
        m.write(self.folder / 'plan.json', self.plan)
        m.write(self.folder / 'worker.json', {'identity': self.worker}); m.write(self.folder / 'child-exit.json', {'returncode': 0})
        self.original = self.root / 'original-polygon.py'; self.original.write_text('original source')
        self.export = self.root / 'export.json'; m.write(self.export, {'files': [{'originalPath': str(self.root / 'polygon.py'), 'exportPath': str(self.original)}]})
        self.review_path = self.root / 'review.json'
        self.review = {'schemaVersion': 1, 'kind': 'qualification-collection-repair-review', 'qualificationId': 'q',
                       'verifiedBy': 'offline', 'summary': 'Exact narrow collection repair', **{k: True for k in repair.FLAGS}}
        self.refresh()

    def refresh(self):
        m.write(self.run / 'state.json', self.state); m.write(self.run / 'result.json', self.result)
        pin = lambda p: {'path': str(p), 'sha256': m.digest(p)}
        self.review.update(originalDashboardExport=pin(self.export), childExit=pin(self.folder / 'child-exit.json'),
                           worker=pin(self.folder / 'worker.json'), state=pin(self.run / 'state.json'), result=pin(self.run / 'result.json'))
        self.review['profileArchivePins'], self.review['profileArchiveDirectories'] = repair.archive_inventory(self.run / 'test-profile')
        m.write(self.review_path, self.review)

    def check(self):
        with patch.object(repair, '_sources', return_value=[]), patch.object(repair, 'validate_patch'), patch.object(m, 'raw_evidence_pins', return_value=[]):
            return repair._checked(self.p, self.row, self.plan, self.review_path, self.con)

    def test_exact_ended_success_passes_without_rewriting_raw_evidence(self):
        before = (self.run / 'state.json').read_bytes(); review, ids, paths = self.check()
        self.assertEqual(ids, [self.worker, self.game]); self.assertIn(self.run / 'result.json', paths)
        self.assertEqual((self.run / 'state.json').read_bytes(), before); self.p.qualification_guard.assert_called_once()

    def test_failed_nonnullable_and_unrestored_states_refuse(self):
        for changes in ({'result': 'failed'}, {'reason': ''}, {'done': False}, {'restored': False}, {'runner': self.game}):
            original = dict(self.state); self.state.update(changes); self.refresh()
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.check()
            self.state = original
        self.state.pop('reason'); self.refresh()
        self.check()  # Real successful state omits reason; raw result has explicit null.
        self.result.pop('reason'); self.refresh()
        with self.assertRaises(ValueError): self.check()

    def test_nonzero_exit_added_archive_and_owner_change_refuse(self):
        m.write(self.folder / 'child-exit.json', {'returncode': 1}); self.refresh()
        with self.assertRaisesRegex(ValueError, 'exit zero'): self.check()
        m.write(self.folder / 'child-exit.json', {'returncode': 0}); self.refresh()
        (self.run / 'test-profile/extra').mkdir()
        with self.assertRaisesRegex(ValueError, 'archive inventory'): self.check()
        (self.run / 'test-profile/extra').rmdir(); self.p.qualification_guard.side_effect = ValueError('foreign owner')
        with self.assertRaisesRegex(ValueError, 'foreign owner'): self.check()

    def test_second_start_or_changed_plan_refuse(self):
        self.p.native_game_starts = lambda state: 2
        with self.assertRaisesRegex(ValueError, 'one successful'): self.check()
        self.p.native_game_starts = lambda state: 1
        m.write(self.folder / 'plan.json', dict(self.plan, changed=True))
        with self.assertRaisesRegex(ValueError, 'original frozen'): self.check()

    def test_cached_packet_archive_detects_extra_member(self):
        packet = {'id': 'q', 'runDirectory': str(self.run),
                  'profileArchivePins': self.review['profileArchivePins'],
                  'collectionRepair': {'path': str(self.review_path), 'sha256': m.digest(self.review_path)}}
        repair.verify_packet_archive(packet)
        (self.run / 'test-profile/new-empty-directory').mkdir()
        with self.assertRaisesRegex(ValueError, 'archive membership'):
            repair.verify_packet_archive(packet)


if __name__ == '__main__': unittest.main()

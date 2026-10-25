"""Synthetic native observations; no game/candidate runner is imported or run."""
from contextlib import nullcontext
import copy
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import polygon as m
import qualification_diagnostic as q
import test_qualification as fixtures


class HeldDiagnosticTests(unittest.TestCase):
    def setUp(self):
        fixtures.QualificationTests.setUp(self)
        fixtures.QualificationTests.register(self)
        self.identity = 'candidate-one'
        self.plan = json.loads(self.p.qualification_show(self.identity)['request'])
        self.folder = self.p.local / 'qualifications' / self.identity
        self.folder.mkdir(parents=True)
        self.worker = {'pid': 444, 'birth': 2, 'path': str(self.root / 'python.exe')}
        self.game = {'pid': 555, 'birth': 3, 'path': str(self.root / 'SkyrimVR.exe')}
        self.second = {'pid': 556, 'birth': 4, 'path': self.game['path']}
        with self.p.connect() as con:
            con.execute("UPDATE qualifications SET status='running' WHERE id=?", (self.identity,))
            con.execute('INSERT INTO attempts VALUES(?,?)', ('qualification-' + self.identity, 1))
        m.write(self.folder / 'plan.json', self.plan)
        m.write(self.folder / 'worker.json', {'identity': self.worker})
        m.write(self.folder / 'child-exit.json', {'returncode': 1})
        self.run = Path(self.config['runtime']) / 'runs' / 'actual'
        self.archive = self.run / 'test-profile'
        self.archive.mkdir(parents=True)
        (self.archive / 'settings.ini').write_text('preserved')
        self.state = {'id': 'actual', 'order': {'id': 'qualification-' + self.identity},
                      'runner': self.worker, 'done': True, 'restored': True, 'restoreErrors': [],
                      'owned': [{'role': 'game', 'identity': self.game}], 'game': None,
                      'profileArchive': str(self.archive), 'testProfile': str(self.run / 'removed')}
        m.write(self.run / 'state.json', self.state)
        m.write(self.run / 'result.json', {'id': 'actual', 'restored': True,
                                          'restoreErrors': [], 'result': 'failed', 'checks': []})
        export = self.root / 'export'
        export.mkdir()
        rows = []
        for pin in self.plan['pins']:
            path = Path(pin['path'])
            if path.parent == m.HERE and path.suffix == '.py':
                target = export / path.name
                shutil.copyfile(path, target)
                rows.append({'originalPath': str(path), 'exportPath': str(target), 'sha256': pin['sha256']})
        receipt = self.root / 'export.json'
        m.write(receipt, {'schemaVersion': 1, 'kind': 'original-dashboard-source-export',
                         'qualificationId': self.identity, 'planSha256': m.digest(self.folder / 'plan.json'), 'files': rows})
        evidence = self.root / 'accounting-evidence.json'
        m.write(evidence, {'observedGameIdentities': [self.game, self.second], 'exhaustive': False})
        observer = self.root / 'observer.py'
        observer.write_text('# Fixture observer; real import is mocked, never run\n')
        self.review_path = self.root / 'review.json'
        self.review = {'schemaVersion': 1, 'kind': 'qualification-held-diagnostic-review',
                       'qualificationId': self.identity, 'verifiedBy': 'synthetic independent reviewer',
                       'summary': 'Observed two game identities, exhaustive count unknown',
                       **{k: True for k in ('nativeCompletionReviewed', 'trackedRestorationReviewed',
                          'archiveReviewed', 'uncertainAccountingReviewed', 'retainHold')},
                       'originalDashboardExport': self.pin(receipt), 'implementationPins': q.implementation_pins(),
                       'worker': self.pin(self.folder / 'worker.json'), 'childExit': self.pin(self.folder / 'child-exit.json'),
                       'state': self.pin(self.run / 'state.json'), 'result': self.pin(self.run / 'result.json'),
                       'observer': self.pin(observer), 'profileArchivePins': [self.pin(self.archive / 'settings.ini')],
                       'profileArchiveDirectories': [],
                       'observedGameIdentities': [self.game, self.second], 'accountingEvidence': [self.pin(evidence)],
                       'observedGamesReviewed': True, 'observedMinimumActualGameStarts': 2,
                       'observedIdentityEvidence': [{'identity': x, 'evidence': self.pin(evidence),
                                                   'locator': 'observedGameIdentities fixture'}
                                                  for x in (self.game, self.second)]}
        self.rows = [{'pid': 77, 'name': 'python.exe'}]
        self.native = SimpleNamespace(processes=lambda: copy.deepcopy(self.rows),
                                     alive=lambda ident: False, identity=lambda pid: None,
                                     SessionMutex=nullcontext)
        self.real_observer_loader = q._observer
        mocked = patch.object(q, '_observer', return_value=self.native)
        mocked.start()
        self.addCleanup(mocked.stop)

    def pin(self, path):
        return {'path': str(path), 'sha256': m.digest(path)}

    def save(self):
        m.write(self.review_path, self.review)

    def record(self):
        self.save()
        return q.record(self.p, self.identity, self.review_path)

    def test_unknown_count_recorded_without_release_or_fake_coverage(self):
        packet = self.record()
        self.assertIsNone(packet['actualGameStarts'])
        self.assertIsNone(packet['cumulativeActualGameStartsAfter'])
        self.assertEqual(packet['observedMinimumActualGameStarts'], 2)
        self.assertEqual(packet['restorationScope'], 'tracked_executor_domains_only')
        self.assertEqual(packet['unownedWriteDomains'], 'unresolved')
        self.assertEqual(packet['testResult']['coverage']['performed'], 0)
        self.assertFalse(packet['testingStarted'])
        self.assertFalse(packet['globalProviderQualified'])
        self.assertFalse(packet['qualificationPassed'])
        self.assertEqual(packet['executionOutcome'], 'failed')
        self.assertEqual(self.p.qualification_show(self.identity)['status'], 'recorded')
        self.assertEqual(len(self.p.pipeline_status()['holds']), 1)
        self.assertIsNone(self.p.claim())
        self.assertFalse(self.p.qualification_successful_result(self.plan, packet))
        self.assertEqual(q.record(self.p, self.identity, self.review_path), packet)

    def test_changed_review_or_retained_evidence_refuses_idempotence(self):
        self.record()
        self.review['summary'] = 'altered'
        self.save()
        with self.assertRaises(ValueError):
            q.record(self.p, self.identity, self.review_path)

    def test_missing_or_changed_original_export_refused(self):
        receipt = m.read(self.review['originalDashboardExport']['path'])
        Path(receipt['files'][0]['exportPath']).write_text('altered')
        with self.assertRaisesRegex(ValueError, 'pin mismatch'):
            self.record()

    def test_incomplete_original_export_refused(self):
        path = Path(self.review['originalDashboardExport']['path'])
        receipt = m.read(path)
        receipt['files'].pop()
        m.write(path, receipt)
        self.review['originalDashboardExport'] = self.pin(path)
        with self.assertRaisesRegex(ValueError, 'inventory required'):
            self.record()

    def test_live_or_unknown_worker_and_foreign_game_refused(self):
        self.native.alive = lambda ident: True
        with self.assertRaisesRegex(ValueError, 'remains alive'):
            self.record()
        self.native.alive = lambda ident: False
        self.rows = [{'pid': self.worker['pid'], 'name': 'python.exe'}]
        with self.assertRaisesRegex(ValueError, 'identity unknown'):
            self.record()
        self.rows = [{'pid': 99, 'name': 'SkyrimSE.exe'}]
        with self.assertRaisesRegex(ValueError, 'game/loader'):
            self.record()

    def test_empty_inventory_refused(self):
        self.rows = []
        with self.assertRaisesRegex(ValueError, 'inventory unavailable'):
            self.record()

    def test_restoration_and_archive_failures_refused(self):
        self.state['restored'] = False
        m.write(self.run / 'state.json', self.state)
        self.review['state'] = self.pin(self.run / 'state.json')
        with self.assertRaisesRegex(ValueError, 'tracked restoration'):
            self.record()
        self.state['restored'] = True
        m.write(self.run / 'state.json', self.state)
        self.review['state'] = self.pin(self.run / 'state.json')
        (self.archive / 'settings.ini').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'archive inventory'):
            self.record()

    def test_missing_native_state_is_not_pre_native_zero(self):
        (self.run / 'state.json').unlink()
        with self.assertRaisesRegex(ValueError, 'native state required'):
            self.record()

    def test_unregistered_packet_is_not_overwritten(self):
        path = self.folder / 'held-diagnostic.json'
        path.write_text('crash artifact')
        with self.assertRaisesRegex(ValueError, 'Unregistered diagnostic'):
            self.record()
        self.assertEqual(path.read_text(), 'crash artifact')

    def test_observed_foreign_identity_must_be_dead(self):
        self.native.alive = lambda ident: ident == self.second
        with self.assertRaisesRegex(ValueError, 'remains alive'):
            self.record()

    def test_lower_bound_and_identity_evidence_mapping_review_required(self):
        self.review['observedMinimumActualGameStarts'] = 1
        with self.assertRaisesRegex(ValueError, 'lower bound differs'):
            self.record()
        self.review['observedMinimumActualGameStarts'] = 2
        self.review['observedIdentityEvidence'].pop()
        with self.assertRaisesRegex(ValueError, 'identity/evidence mapping'):
            self.record()

    def test_recorded_diagnostic_cannot_claim_hold_after_clearance(self):
        self.record()
        with self.p.connect() as con:
            con.execute('DELETE FROM pipeline_holds')
        with self.assertRaisesRegex(ValueError, 'immutable'):
            q.record(self.p, self.identity, self.review_path)

    def test_factual_start_uses_original_boundary_and_keeps_checks_not_run(self):
        # Change only the synthetic fixture before registering a fresh qualification.
        self.plan['orderData']['testing']['start'] = {'kind': 'event', 'event': 'phase', 'name': 'start-skse'}
        with self.p.connect() as con:
            con.execute('UPDATE qualifications SET request=? WHERE id=?', (json.dumps(self.plan, sort_keys=True), self.identity))
        m.write(self.folder / 'plan.json', self.plan)
        receipt_path = Path(self.review['originalDashboardExport']['path'])
        receipt = m.read(receipt_path)
        receipt['planSha256'] = m.digest(self.folder / 'plan.json')
        m.write(receipt_path, receipt)
        self.review['originalDashboardExport'] = self.pin(receipt_path)
        (self.run / 'steps.jsonl').write_text(json.dumps({'kind': 'phase', 'name': 'start-skse'}) + '\n')
        packet = self.record()
        self.assertTrue(packet['testingStarted'])
        self.assertEqual(packet['testResult']['coverage']['performed'], 0)

    def test_archive_directory_membership_is_not_ignored(self):
        (self.archive / 'unexpected-empty-directory').mkdir()
        with self.assertRaisesRegex(ValueError, 'archive inventory'):
            self.record()

    def test_wrong_observer_hash_is_rejected_before_import(self):
        with self.assertRaisesRegex(ValueError, 'strict read-only native observer'):
            self.real_observer_loader(self.review['observer'])

    def test_diagnostic_never_satisfies_successful_release_predicate(self):
        packet = self.record()
        # Even artificially populated success-looking fields never qualify its kind.
        packet['executionOutcome'] = 'passed'
        packet['testResult']['testingStarted'] = True
        self.assertFalse(self.p.qualification_successful_result(self.plan, packet))

    def test_code_snapshots_replace_mutable_source_evidence(self):
        packet = self.record()
        retained_paths = {pin['path'] for pin in packet['files']}
        self.assertFalse(any(str(path) in retained_paths for path in m.HERE.glob('*.py')))
        self.assertNotIn(self.review['observer']['path'], retained_paths)
        self.assertTrue(packet['implementationSnapshotPins'])
        self.assertNotIn(str(self.p.local / 'config.json'), retained_paths)
        self.assertTrue(packet['originalInputSnapshots'])
        # Historical collection remains valid after a legitimate host-only update.
        m.write(self.p.local / 'config.json', {'executor': 'new-host-only-value'})
        self.assertEqual(self.p.qualification_collect(self.identity), packet)

    def test_windows_path_spelling_does_not_double_count_pid_birth(self):
        alias = {**self.second, 'path': self.second['path'].replace('\\', '/')}
        self.review['observedGameIdentities'].append(alias)
        self.review['observedIdentityEvidence'].append({
            'identity': alias, 'evidence': self.review['accountingEvidence'][0],
            'locator': 'same exact PID/birth with alternate Windows path spelling'})
        self.assertEqual(self.record()['observedMinimumActualGameStarts'], 2)

    def test_original_qualification_source_export_can_precede_refusal_guard(self):
        receipt_path = Path(self.review['originalDashboardExport']['path'])
        receipt = m.read(receipt_path)
        row = next(x for x in receipt['files'] if Path(x['originalPath']).name == 'qualification.py')
        exported = Path(row['exportPath'])
        current = exported.read_text(encoding='utf-8')
        original = current.replace("        if packet.get('kind') == 'qualification-held-diagnostic':\n            return False\n", '')
        self.assertNotEqual(current, original)
        exported.write_text(original, encoding='utf-8', newline='')
        old_hash = m.digest(exported)
        row['sha256'] = old_hash
        next(x for x in self.plan['pins'] if x['path'] == row['originalPath'])['sha256'] = old_hash
        m.write(self.folder / 'plan.json', self.plan)
        with self.p.connect() as con:
            con.execute('UPDATE qualifications SET request=? WHERE id=?', (json.dumps(self.plan, sort_keys=True), self.identity))
        receipt['planSha256'] = m.digest(self.folder / 'plan.json')
        m.write(receipt_path, receipt)
        self.review['originalDashboardExport'] = self.pin(receipt_path)
        self.assertIsNone(self.record()['actualGameStarts'])

    def test_frozen_scenario_keeps_original_evidence_pin(self):
        packet = self.record()
        self.assertIn(self.plan['scenarioPath'], {pin['path'] for pin in packet['files']})
        Path(self.plan['scenarioPath']).write_text('changed')
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            self.p.qualification_collect(self.identity)

    def test_added_archive_file_is_detected_on_direct_collection(self):
        self.record()
        (self.archive / 'added.ini').write_text('new')
        with self.assertRaisesRegex(ValueError, 'archive membership'):
            self.p.qualification_collect(self.identity)


if __name__ == '__main__':
    unittest.main()

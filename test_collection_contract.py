"""Explicit collector failure is technical evidence, never inferred mod failure."""
import copy
import unittest
from pathlib import Path

import test_polygon

mod = test_polygon.mod
ERROR = {'path': 'SteamVR/vrserver.txt', 'error': 'copy failed', 'segment': 'restart-1'}


class CollectionContract(unittest.TestCase):
    def report(self, fields, checks=None, outcome='passed'):
        fixture = test_polygon.Tests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        checks = checks if checks is not None else [
            {'name': name, 'result': 'passed'} for name in ('subject-check', 'later-check')]
        packet = fixture.final_fixture(checks, outcome=outcome, native_proof=fields)
        pin = next(e for e in packet['files'] if Path(e['path']).name == 'result.json')
        path = fixture.root / 'complete-collection.json'
        mod.write(path, {'schemaVersion': 1, 'id': 'collection-final', 'orderIds': ['final-fixture'],
                        'summary': 'Collection phase ended; available evidence assessed', 'collectionFinished': True,
                        'dataCoverage': {'final-fixture': [{'name': 'state', 'status': 'collected', 'evidence': [pin]}]}})
        fixture.p.report_ready(path)
        entry = mod.read(fixture.p.local / 'final-reports/collection-final/report.json')['orders'][0]
        return fixture, packet, entry

    def test_explicit_fault_in_either_source_holds_and_interrupts_even_raw_pass(self):
        for source in ('state', 'result'):
            for fields in ({'collectionComplete': False}, {'collectionErrors': [ERROR]},
                           {'collectionComplete': True, 'collectionErrors': [ERROR]}):
                with self.subTest(source=source, fields=fields):
                    fixture, packet, entry = self.report({source: fields})
                    result = entry['testResult']
                    self.assertEqual(result['outcome'], 'interrupted_external')
                    self.assertTrue(result['interruptionObserved'])
                    self.assertFalse(result['subjectMismatchObserved'])
                    self.assertEqual(result['coverage']['failed'], 0)
                    self.assertEqual(result['execution']['terminationCause'], 'evidence_collection_failure')
                    self.assertEqual(result['execution']['rawOutcome'], 'passed')
                    findings = mod.read(fixture.p.evidence_dir('final-fixture') / 'self-checks.json')['findings']
                    self.assertEqual(findings[0]['kind'], 'evidence_collection_incomplete')
                    self.assertEqual(findings[0]['details']['collectionErrors'], fields.get('collectionErrors'))
                    with fixture.p.connect() as con:
                        self.assertIsNotNone(con.execute('SELECT * FROM pipeline_holds WHERE id=?', ('final-fixture',)).fetchone())
                    self.assertEqual(fixture.p.pending()[0]['testOutcome'], 'interrupted_external')
                    self.assertTrue(packet['restored'])

    def test_pretest_collection_fault_stays_unnotified(self):
        fixture, _, entry = self.report({'result': {'collectionComplete': False, 'collectionErrors': [ERROR]}}, checks=[])
        self.assertEqual(entry['testResult']['outcome'], 'not_started')
        self.assertEqual(entry['eligibility'], 'suppressed')
        self.assertFalse(fixture.p.pending())
        with self.assertRaisesRegex(ValueError, 'notification prohibited'):
            fixture.p.delivered('final-fixture', 'No fabricated delivery')

    def test_real_subject_mismatch_survives_independent_collection_fault(self):
        _, _, entry = self.report({'state': {'collectionComplete': False}},
                                  checks=[{'name': 'subject-check', 'result': 'failed'}], outcome='failed')
        result = entry['testResult']
        self.assertEqual(result['outcome'], 'tested_with_errors')
        self.assertTrue(result['subjectMismatchObserved'])
        self.assertTrue(result['interruptionObserved'])
        self.assertEqual(result['coverage']['failed'], 1)

    def test_healthy_absent_and_null_fields_keep_legacy_behavior(self):
        for fields in ({}, {'collectionComplete': None, 'collectionErrors': None},
                       {'collectionComplete': True, 'collectionErrors': []}):
            with self.subTest(fields=fields):
                fixture, packet, entry = self.report({'state': fields, 'result': fields})
                self.assertEqual(entry['testResult']['outcome'], 'tested_successfully')
                self.assertEqual(entry['testResult']['execution']['terminationCause'], 'normal_close')
                self.assertFalse(mod.read(fixture.p.evidence_dir('final-fixture') / 'self-checks.json')['findings'])
                order, verified = fixture.p.verify_packet(fixture.p.get('final-fixture'))
                legacy_failed = copy.deepcopy(verified)
                legacy_failed['executionOutcome'] = 'failed'
                self.assertEqual(fixture.p.test_projection(order, legacy_failed)['outcome'], 'incomplete')

    def test_unpinned_result_cannot_classify_collection_fault(self):
        fixture, packet, _ = self.report({'result': {'collectionComplete': False}})
        order, packet = fixture.p.verify_packet(fixture.p.get('final-fixture'))
        packet['files'] = [e for e in packet['files'] if Path(e['path']).name != 'result.json']
        result = fixture.p.test_projection(order, packet)
        self.assertEqual(result['outcome'], 'not_started')
        self.assertFalse(result['execution']['collectionFindings'])

    def test_malformed_nonnull_contract_never_proves_success(self):
        for fields in ({'collectionComplete': 0}, {'collectionComplete': 'false'}, {'collectionErrors': {}},
                       {'collectionErrors': 'copy failed'}):
            with self.subTest(fields=fields):
                _, _, entry = self.report({'result': fields})
                self.assertEqual(entry['testResult']['outcome'], 'interrupted_external')


if __name__ == '__main__':
    unittest.main()

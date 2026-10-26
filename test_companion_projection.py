"""Ordinary result semantics over actual verified companion fixtures."""
import polygon as m
import test_companion_evidence as fixture
import unittest


class CompanionProjectionTests(unittest.TestCase):
    def setUp(self):
        fixture.CompanionEvidenceTests.setUp(self)
        self.order['collect'] = ['Actual subject case outcomes']
        self.p.executor_auxiliary_checks = lambda *args: []
        self.p.execution_summary = lambda *args: {'terminationCause': 'normal_close'}
        self.result = self.write(self.run / 'result.json', {'checks': [
            {'name': 'companion-core-preparation', 'result': 'passed', 'observation': {'world': {'ready': True}}}]})

    write = fixture.CompanionEvidenceTests.write
    lines = fixture.CompanionEvidenceTests.lines
    action = fixture.CompanionEvidenceTests.action
    save = fixture.CompanionEvidenceTests.save
    collect = fixture.CompanionEvidenceTests.collect
    dispatch_record = fixture.CompanionEvidenceTests.dispatch_record

    def projection(self):
        summary = self.collect()
        packet = {'runDirectory': str(self.run), 'subjectCompanion': summary,
                  'files': summary['pins'] + [self.result], 'executionOutcome': 'passed', 'reason': ''}
        return m.Polygon.test_projection(self.p, self.order, packet)

    def test_separate_cases_pass_without_promoting_core_readiness_into_subject_coverage(self):
        result = self.projection()
        self.assertEqual(result['outcome'], 'tested_successfully')
        self.assertEqual(result['coverage']['required'], len(self.names))
        self.assertEqual(result['coverage']['passed'], len(self.names))
        self.assertEqual(result['auxiliaryCoverage']['checks'][0]['name'], 'companion-core-preparation')

    def test_subject_mismatch_with_normal_helper_and_game_end_is_a_mod_failure(self):
        name = self.names[-1]
        self.report['cases'][-1]['status'] = 'failed'; self.report['status'] = 'stopped'
        for row in self.events:
            record = row.get('record', {})
            if record.get('caseId') == name and record.get('kind') in ('assertion', 'check-result'):
                record['outcome'] = 'mismatch'
        self.save()
        result = self.projection()
        self.assertEqual(result['outcome'], 'tested_with_errors')
        self.assertTrue(result['subjectMismatchObserved']); self.assertFalse(result['interruptionObserved'])
        self.assertEqual(result['coverage']['failed'], 1)

    def test_nonzero_helper_is_a_tool_fault_even_if_report_contains_passed_cases(self):
        self.write(self.folder / 'dispatch.json', self.dispatch_record(7))
        result = self.projection()
        self.assertEqual(result['outcome'], 'interrupted_external')
        self.assertTrue(result['interruptionObserved'])

    def test_core_readiness_and_unverified_companion_cannot_establish_subject_start(self):
        packet = {'runDirectory': str(self.run), 'files': [self.result], 'executionOutcome': 'passed', 'reason': ''}
        result = m.Polygon.test_projection(self.p, self.order, packet)
        self.assertEqual(result['outcome'], 'not_started'); self.assertFalse(result['testingStarted'])
        self.assertEqual(result['coverage']['not_run'], len(self.names))


if __name__ == '__main__': unittest.main()

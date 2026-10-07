"""Typed same-run technical checks never create subject progress."""
import copy
import unittest
from pathlib import Path
import test_polygon

mod = test_polygon.mod


class ExecutorChecks(unittest.TestCase):
    def report(self, mutate=None, status='passed', subject=True):
        fixture = test_polygon.Tests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        check = {'name': 'arbitrary executor bootstrap checkpoint', 'result': status,
                 'provenance': {'schemaVersion': 1, 'component': 'skyrim-autotest',
                                'stage': 'bootstrap', 'role': 'tooling', 'runId': 'run-fixture',
                                'checkId': 'bootstrap-transition-1'}}
        checks = ([{'name': n, 'result': 'passed'} for n in ('subject-check', 'later-check')] if subject else []) + [check]
        proof = {'state': {'checks': copy.deepcopy(checks)}, 'result': {'id': 'run-fixture'},
                 'events': [{'kind': 'executor-check', **copy.deepcopy(check)}]}
        if mutate:
            mutate(checks, proof)
        packet = fixture.final_fixture(checks, outcome='passed', native_proof=proof)
        pin = next(p for p in packet['files'] if Path(p['path']).name == 'result.json')
        request = fixture.root / 'complete.json'
        mod.write(request, {'schemaVersion': 1, 'id': 'complete', 'orderIds': ['final-fixture'],
                           'summary': 'Verified raw checks and collected state', 'collectionFinished': True,
                           'dataCoverage': {'final-fixture': [{'name': 'state', 'status': 'collected', 'evidence': [pin]}]}})
        fixture.p.report_ready(request)
        report = mod.read(fixture.p.local / 'final-reports/complete/report.json')['orders'][0]['testResult']
        return fixture, report

    def test_typed_bootstrap_pass_keeps_required_counts_and_board_separate(self):
        fixture, report = self.report()
        self.assertEqual(report['outcome'], 'tested_successfully')
        self.assertEqual(report['coverage']['required'], 2)
        self.assertEqual(report['coverage']['performed'], 2)
        self.assertEqual(report['coverage']['passed'], 2)
        self.assertEqual(report['auxiliaryCoverage']['passed'], 1)
        board = next(r for r in fixture.p.board() if r['id'] == 'final-fixture')
        self.assertEqual(board['auxiliaryCoverage'], report['auxiliaryCoverage'])
        self.assertEqual(fixture.p.pending()[0]['testOutcome'], 'tested_successfully')

    def test_bootstrap_alone_never_proves_subject_start_or_notifies(self):
        fixture, report = self.report(subject=False)
        self.assertEqual(report['outcome'], 'not_started')
        self.assertFalse(report['testingStarted'])
        self.assertEqual(report['coverage']['not_run'], 2)
        self.assertFalse(fixture.p.pending())

    def test_failed_bootstrap_is_external_interruption_after_subject_start(self):
        _, report = self.report(status='failed')
        self.assertEqual(report['outcome'], 'interrupted_external')
        self.assertTrue(report['interruptionObserved'])
        self.assertFalse(report['subjectMismatchObserved'])
        self.assertEqual(report['coverage']['failed'], 0)
        self.assertEqual(report['auxiliaryCoverage']['failed'], 1)

    def test_unavailable_and_not_run_auxiliary_never_prove_success(self):
        for status in ('unavailable', 'not_run'):
            with self.subTest(status=status):
                _, report = self.report(status=status)
                self.assertEqual(report['outcome'], 'incomplete')
                self.assertEqual(report['auxiliaryCoverage'][status], 1)

    def test_missing_or_mismatched_attestation_remains_unknown(self):
        mutations = [
            lambda c, p: c[-1].pop('provenance'),
            lambda c, p: p.update(events=[]),
            lambda c, p: p['state'].update(checks=[]),
            lambda c, p: p['result'].update(id='foreign-run'),
            lambda c, p: p['events'][0].update(result='failed'),
            lambda c, p: p['state']['checks'][-1].update(result='failed'),
            lambda c, p: p['events'].append(copy.deepcopy(p['events'][0])),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                _, report = self.report(mutate)
                self.assertEqual(report['outcome'], 'incomplete')
                self.assertEqual(report['auxiliaryCoverage']['checks'], [])
                self.assertEqual(report['coverage']['checks'][-1]['role'], 'unknown')

    def test_foreign_native_owner_refuses_finalization(self):
        with self.assertRaisesRegex(ValueError, 'Execution completion/identity not proven'):
            self.report(lambda c, p: p['state'].update(order={'id': 'foreign-order'}))

    def test_unsupported_provenance_never_gets_blanket_exclusion(self):
        for key, value in [('component', 'mod'), ('stage', 'scenario'), ('role', 'subject'),
                           ('schemaVersion', 2), ('schemaVersion', True), ('runId', 'foreign'),
                           ('checkId', '../bad'), ('extra', 'not accepted')]:
            with self.subTest(key=key, value=value):
                def mutate(checks, proof):
                    for check in (checks[-1], proof['state']['checks'][-1], proof['events'][0]):
                        check['provenance'][key] = value
                _, report = self.report(mutate)
                self.assertEqual(report['outcome'], 'incomplete')
                self.assertFalse(report['auxiliaryCoverage']['checks'])

    def test_name_only_bootstrap_trust_is_refused(self):
        def mutate(checks, proof):
            checks[-1] = {'name': 'new game world transition observed', 'result': 'passed'}
        _, report = self.report(mutate)
        self.assertEqual(report['outcome'], 'incomplete')
        self.assertEqual(report['coverage']['checks'][-1]['role'], 'unknown')

    def test_duplicate_names_or_executor_ids_fail_closed(self):
        for same_name in (True, False):
            with self.subTest(same_name=same_name):
                def mutate(checks, proof):
                    other = copy.deepcopy(checks[-1])
                    if not same_name:
                        other['name'] = 'another bootstrap check'
                    checks.append(other)
                _, report = self.report(mutate)
                self.assertEqual(report['outcome'], 'incomplete')
                self.assertFalse(report['auxiliaryCoverage']['checks'])

    def test_executor_type_cannot_satisfy_declared_subject_start(self):
        def mutate(checks, proof):
            checks.pop(0)
            for check in (checks[-1], proof['state']['checks'][-1], proof['events'][0]):
                check['name'] = 'subject-check'
        fixture, report = self.report(mutate)
        self.assertEqual(report['outcome'], 'not_started')
        self.assertEqual(report['coverage']['checks'][0]['status'], 'unavailable')
        self.assertFalse(fixture.p.pending())

    def test_existing_final_report_is_not_recomputed_or_resent(self):
        fixture, report = self.report()
        path = fixture.p.local / 'final-reports/complete/report.json'
        # Model a retained report authored before the additive auxiliaryCoverage field.
        legacy = mod.read(path)
        legacy['orders'][0]['testResult'].pop('auxiliaryCoverage')
        mod.write(path, legacy)
        with fixture.p.connect() as con:
            con.execute('UPDATE final_reports SET sha256=? WHERE id=?', (mod.digest(path), 'complete'))
        original = path.read_bytes()
        with unittest.mock.patch.object(fixture.p, 'test_projection', side_effect=AssertionError('Must not reproject history')):
            fixture.p.pending()
            fixture.p.board()
        self.assertEqual(path.read_bytes(), original)

    def test_unpinned_log_cannot_attest_auxiliary_check(self):
        fixture, report = self.report()
        order, packet = fixture.p.verify_packet(fixture.p.get('final-fixture'))
        packet = copy.deepcopy(packet)
        packet['files'] = [p for p in packet['files'] if Path(p['path']).name != 'steps.jsonl']
        projection = fixture.p.test_projection(order, packet)
        self.assertEqual(projection['outcome'], 'incomplete')
        self.assertFalse(projection['auxiliaryCoverage']['checks'])

    def test_executor_log_event_never_establishes_subject_start(self):
        fixture, report = self.report()
        order, packet = fixture.p.verify_packet(fixture.p.get('final-fixture'))
        order = copy.deepcopy(order)
        order['testing']['start'] = {'kind': 'event', 'event': 'executor-check',
                                    'name': 'arbitrary executor bootstrap checkpoint'}
        self.assertFalse(fixture.p.test_projection(order, packet)['testingStarted'])

    def test_tampered_pinned_log_blocks_delivery(self):
        fixture, report = self.report()
        packet = mod.read(fixture.p.get('final-fixture')['packet'])
        log = Path(packet['runDirectory']) / 'steps.jsonl'
        log.write_text('{}\n')
        with self.assertRaisesRegex(ValueError, 'manifest mismatch'):
            fixture.p.pending()


if __name__ == '__main__':
    unittest.main()

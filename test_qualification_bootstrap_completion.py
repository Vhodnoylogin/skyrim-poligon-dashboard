"""Completion-only compatibility; no launch and no rewritten raw qualification."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from qualification import Qualifications


class NewGamePrefixCompletionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.run = Path(temp.name) / 'actual-owned-run'
        self.run.mkdir()
        prefix = [
            {'name': 'journal', 'tool': 'menu', 'args': {'action': 'close', 'name': 'Journal Menu'}, 'observe': True},
            {'name': 'tutorial', 'tool': 'menu', 'args': {'action': 'close', 'name': 'Tutorial Menu'}, 'observe': True},
            {'name': 'ready', 'tool': 'platform', 'args': {'operation': 'state.read'},
             'assert': [{'path': 'world.ready', 'equals': True}]},
        ]
        suffix = [{'name': name, 'tool': 'platform',
                   'args': {'operation': 'world.read', 'request': {'domain': domain}},
                   'assert': [{'path': 'ready', 'equals': True}]}
                  for name, domain in [('catalog', 'human-preset-catalog'), ('config', 'human-provider-config')]]
        self.plan = {'configuration': {'game_edition': 'se', 'se_new_game_ui': True},
                     'scenario': {'schemaVersion': 1, 'cell': 'QASmoke', 'startMode': 'new-game', 'steps': prefix + suffix},
                     'orderData': {'testing': {'start': {'kind': 'check', 'name': 'catalog'},
                                  'checks': [{'name': n, 'role': 'tooling'} for n in ('catalog', 'config')]}}}
        provenance = {'schemaVersion': 1, 'component': 'skyrim-autotest', 'stage': 'bootstrap',
                      'role': 'tooling', 'runId': self.run.name, 'checkId': 'new-game-world-transition'}
        auxiliary = {'name': 'new game world transition observed', 'role': 'tooling', 'status': 'passed', 'provenance': provenance}
        self.packet = {'kind': 'tool-qualification-result', 'runDirectory': str(self.run), 'executionOutcome': 'passed',
                       'testResult': {'outcome': 'incomplete', 'testingStarted': True, 'interruptionObserved': False,
                                      'subjectMismatchObserved': False,
                                      'coverage': {'checks': [{'name': n, 'role': 'tooling', 'status': 'passed'} for n in ('catalog', 'config')] +
                                                  [{'name': n, 'role': 'unknown', 'status': r}
                                                   for n, r in [('journal', 'observed'), ('tutorial', 'observed'), ('ready', 'passed')]]},
                                      'auxiliaryCoverage': {'checks': [auxiliary]}}}
        self.actual = [{'name': auxiliary['name'], 'result': 'passed', 'provenance': provenance},
                       {'name': 'journal', 'result': 'observed', 'observation': {'action': 'close', 'name': 'Journal Menu', 'queued': True}},
                       {'name': 'tutorial', 'result': 'observed', 'observation': {'action': 'close', 'name': 'Tutorial Menu', 'queued': True}},
                       {'name': 'ready', 'result': 'passed', 'observation': {'world': {'ready': True}}},
                       {'name': 'catalog', 'result': 'passed'}, {'name': 'config', 'result': 'passed'}]

    def classify(self, plan=None, packet=None, actual=None):
        self.result_path = self.run / 'result.json'
        self.result_path.write_text(json.dumps({'checks': self.actual if actual is None else actual}), encoding='utf-8')
        return Qualifications.qualification_successful_result(self.plan if plan is None else plan,
                                                             self.packet if packet is None else packet)

    def test_exact_declared_scope_finishes_without_rewriting_incomplete_projection(self):
        before_plan = copy.deepcopy(self.plan)
        before_packet = copy.deepcopy(self.packet)
        self.assertTrue(self.classify())
        self.assertEqual(self.plan, before_plan)
        self.assertEqual(self.packet, before_packet)
        self.assertEqual(self.packet['testResult']['outcome'], 'incomplete')
        self.assertEqual([c['role'] for c in self.packet['testResult']['coverage']['checks']][2:], ['unknown'] * 3)
        self.assertEqual(json.loads(self.result_path.read_text())['checks'], self.actual)

    def test_only_explicit_se_new_game_five_step_scenario_is_recognized(self):
        variants = []
        for change in ({'game_edition': 'vr'}, {'se_new_game_ui': False}):
            p = copy.deepcopy(self.plan); p['configuration'].update(change); variants.append(p)
        for change in ({'cell': 'OtherCell'}, {'startMode': 'save'}, {'fixture': {'saveStem': 'Other'}}, {'kind': 'probe'}, {'postSteps': [{}]}):
            p = copy.deepcopy(self.plan); p['scenario'].update(change); variants.append(p)
        p = copy.deepcopy(self.plan); p['scenario']['steps'].append(copy.deepcopy(p['scenario']['steps'][-1])); variants.append(p)
        for p in variants:
            with self.subTest(plan=p): self.assertFalse(self.classify(plan=p))

    def test_prefix_operations_and_assertions_cannot_be_substituted(self):
        for index, change in [(0, {'args': {'action': 'open', 'name': 'Journal Menu'}}),
                              (1, {'args': {'action': 'close', 'name': 'Other Menu'}}),
                              (0, {'assert': [{'path': 'queued', 'equals': True}]}), (1, {'observe': False}),
                              (2, {'args': {'operation': 'world.read'}}),
                              (2, {'assert': [{'path': 'world.ready', 'equals': False}]}),
                              (2, {'assert': [{'path': 'world.ready', 'equals': 1}]})]:
            p = copy.deepcopy(self.plan); p['scenario']['steps'][index].update(change)
            with self.subTest(index=index, change=change): self.assertFalse(self.classify(plan=p))

    def test_required_two_tooling_suffix_and_start_boundary_stay_exact(self):
        for index, value in [(0, 'subject'), (1, 'unknown')]:
            p = copy.deepcopy(self.plan); p['orderData']['testing']['checks'][index]['role'] = value
            self.assertFalse(self.classify(plan=p))
        for start in ('ready', 'config'):
            p = copy.deepcopy(self.plan); p['orderData']['testing']['start']['name'] = start
            self.assertFalse(self.classify(plan=p))
        p = copy.deepcopy(self.plan); p['orderData']['testing']['checks'].reverse(); self.assertFalse(self.classify(plan=p))
        p = copy.deepcopy(self.plan); p['scenario']['steps'][3]['args']['request']['domain'] = 'actor-fixture'
        self.assertFalse(self.classify(plan=p))

    def test_missing_extra_duplicate_failed_or_wrong_role_projected_check_rejected(self):
        for mutation in ('missing', 'extra', 'duplicate', 'failed', 'unavailable', 'role'):
            p = copy.deepcopy(self.packet); rows = p['testResult']['coverage']['checks']
            if mutation == 'missing': rows.pop()
            elif mutation == 'extra': rows.append({'name': 'other', 'role': 'unknown', 'status': 'passed'})
            elif mutation == 'duplicate': rows[2] = copy.deepcopy(rows[3])
            elif mutation == 'role': rows[2]['role'] = 'tooling'
            else: rows[0]['status'] = mutation
            with self.subTest(mutation=mutation): self.assertFalse(self.classify(packet=p))

    def test_raw_sequence_status_prefix_observation_and_required_checks_are_all_required(self):
        for mutation in ('missing', 'extra', 'duplicate', 'failed_required', 'failed_prefix', 'missing_observation', 'world_false', 'late_prefix', 'numeric_queued'):
            rows = copy.deepcopy(self.actual)
            if mutation == 'missing': rows.pop()
            elif mutation == 'extra': rows.append({'name': 'other', 'result': 'passed'})
            elif mutation == 'duplicate': rows[4] = copy.deepcopy(rows[5])
            elif mutation == 'failed_required': rows[4]['result'] = 'failed'
            elif mutation == 'failed_prefix': rows[1]['result'] = 'failed'
            elif mutation == 'missing_observation': rows[1].pop('observation')
            elif mutation == 'world_false': rows[3]['observation']['world']['ready'] = False
            elif mutation == 'late_prefix': rows[1], rows[4] = rows[4], rows[1]
            elif mutation == 'numeric_queued': rows[1]['observation']['queued'] = 1
            with self.subTest(mutation=mutation): self.assertFalse(self.classify(actual=rows))

    def test_actual_bootstrap_provenance_and_auxiliary_projection_are_exact(self):
        for value in ({}, {'runId': 'other'}, {'role': 'subject'}, {'checkId': 'other'}, {'schemaVersion': True}):
            rows = copy.deepcopy(self.actual); rows[0]['provenance'].update(value)
            if not value: rows[0]['provenance'] = {}
            self.assertFalse(self.classify(actual=rows))
        p = copy.deepcopy(self.packet); p['testResult']['auxiliaryCoverage']['checks'] = []
        self.assertFalse(self.classify(packet=p))

    def test_failed_interrupted_subject_mismatch_or_diagnostic_is_never_completed(self):
        for key in ('interruptionObserved', 'subjectMismatchObserved'):
            p = copy.deepcopy(self.packet); p['testResult'][key] = True; self.assertFalse(self.classify(packet=p))
        p = copy.deepcopy(self.packet); p['executionOutcome'] = 'failed'; self.assertFalse(self.classify(packet=p))
        p = copy.deepcopy(self.packet); p['kind'] = 'qualification-held-diagnostic'; self.assertFalse(self.classify(packet=p))

    def test_missing_subject_or_fixture_check_cannot_be_covered_by_bootstrap(self):
        for role in ('subject', 'fixture'):
            p = copy.deepcopy(self.plan)
            p['orderData']['testing']['checks'].append({'name': 'required-missing', 'role': role})
            with self.subTest(role=role):
                self.assertFalse(self.classify(plan=p))

    def test_undeclared_subject_action_cannot_be_omitted_from_native_results(self):
        p = copy.deepcopy(self.plan)
        p['scenario']['steps'].append({'name': 'subject-action', 'tool': 'platform',
                                     'args': {'operation': 'object.perform', 'request': {'action': 'activate'}},
                                     'assert': [{'path': 'activated', 'equals': True}]})
        self.assertFalse(self.classify(plan=p))

    def test_unknown_startup_check_cannot_hide_an_additional_subject_assertion(self):
        p = copy.deepcopy(self.plan)
        p['scenario']['steps'][2]['assert'].append({'path': 'subject.response', 'equals': True})
        self.assertFalse(self.classify(plan=p))

    def test_auxiliary_bootstrap_name_cannot_collide_with_any_scenario_step(self):
        # A duplicate name cannot receive authentic auxiliary classification;
        # reject it here even if a contradictory retained projection is supplied.
        auxiliary_name = self.actual[0]['name']
        for index in range(5):
            p, packet, actual = copy.deepcopy(self.plan), copy.deepcopy(self.packet), copy.deepcopy(self.actual)
            old = p['scenario']['steps'][index]['name']
            p['scenario']['steps'][index]['name'] = auxiliary_name
            actual[index + 1]['name'] = auxiliary_name
            for check in packet['testResult']['coverage']['checks']:
                if check['name'] == old:
                    check['name'] = auxiliary_name
            for check in p['orderData']['testing']['checks']:
                if check['name'] == old:
                    check['name'] = auxiliary_name
            if p['orderData']['testing']['start']['name'] == old:
                p['orderData']['testing']['start']['name'] = auxiliary_name
            with self.subTest(index=index):
                self.assertFalse(self.classify(plan=p, packet=packet, actual=actual))

    def test_bootstrap_compatibility_does_not_change_ordinary_subject_acceptance(self):
        p, packet = copy.deepcopy(self.plan), copy.deepcopy(self.packet)
        p['orderData']['testing']['checks'] = [{'name': 'subject-check', 'role': 'subject'}]
        p['orderData']['testing']['start'] = {'kind': 'check', 'name': 'subject-check'}
        p['scenario']['steps'] = [{'name': 'subject-check', 'tool': 'platform',
                                  'args': {'operation': 'state.read'},
                                  'assert': [{'path': 'subject.response', 'equals': True}]}]
        packet['testResult']['coverage']['checks'] = [{'name': 'subject-check', 'role': 'subject', 'status': 'passed'}]
        packet['testResult']['auxiliaryCoverage']['checks'] = []
        actual = [{'name': 'subject-check', 'result': 'passed'}]
        self.assertTrue(self.classify(plan=p, packet=packet, actual=actual))
        packet['testResult']['coverage']['checks'][0]['status'] = 'not_run'
        self.assertFalse(self.classify(plan=p, packet=packet, actual=[]))


if __name__ == '__main__': unittest.main()

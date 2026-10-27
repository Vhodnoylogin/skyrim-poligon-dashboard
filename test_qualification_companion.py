"""Offline qualification/companion admission and independently checked evidence."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import polygon as m
import qualification_companion as route
from qualification import inventory
import test_qualification as qualification_fixture
import test_companion_evidence as evidence_fixture


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = qualification_fixture.QualificationTests(); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.plan = f.root / 'component-plan.json'; self.transport = f.root / 'client.py'; self.sequencer = f.root / 'sequencer.py'
        m.write(self.plan, {'checks': [{'name': 'case-one', 'role': 'subject'}, {'name': 'case-two', 'role': 'subject'}],
            'fixture': {'cell': 'QASmoke'}, 'bounds': {'maximumSeconds': 600, 'maximumCommands': 256}})
        self.transport.write_text('# separately pinned data client\n'); self.sequencer.write_text('def run(exchange,emit): return {}\n')
        self.spec = {'maximumSeconds': 600, **{name: {'path': str(path), 'sha256': m.digest(path)} for name, path in
            (('transport', self.transport), ('plan', self.plan), ('sequencer', self.sequencer))}}
        f.request['companion'] = self.spec
        f.scenario.update(cell='QASmoke', startMode='new-game')
        f.config.update(game_edition='se', se_new_game_ui=True, allow_owned_save_load=True,
            interactive_session={'maximumSeconds': 600, 'channelConfig': str(f.root / 'channel.json'), 'sourceId': 'operator.actions',
                'allowedTools': ['platform', 'papyrus', 'inspect'], 'npcPersistence': True,
                'morphSession': {'new': 'provider under qualification'}, 'nativeBindings': {'bindings': ['explicit new provider declarations']}})
        m.write(f.root / 'config.json', f.config); m.write(f.root / 'scenario.json', f.scenario)

    def test_explicit_recipe_pins_new_tools_without_any_ordinary_baseline(self):
        f = self.fixture; f.register()
        frozen = f.p.qualification_verify(f.p.qualification_show('candidate-one'))
        self.assertEqual(frozen['companion'], self.spec)
        self.assertEqual(frozen['maximumWallSeconds'], 900)
        self.assertEqual(frozen['configuration'], f.config)
        pins = {row['path']: row['sha256'] for row in frozen['pins']}
        for path in (self.transport, self.plan, self.sequencer): self.assertEqual(pins[str(path)], m.digest(path))
        self.assertTrue(f.p.qualification_check('candidate-one')['validated'])
        self.assertEqual(len(f.p.pipeline_status()['holds']), 1)

    def test_changed_source_cannot_dispatch(self):
        f = self.fixture; f.register(); self.sequencer.write_text('# changed after immutable registration')
        with self.assertRaisesRegex(ValueError, 'pin changed'): f.p.qualification_run('candidate-one')
        self.assertEqual(f.p.qualification_show('candidate-one')['status'], 'prepared')

    def test_window_fixture_and_config_mismatches_fail_before_registration(self):
        f = self.fixture
        for field, value in [('maximumSeconds', 1200), ('extra', True)]:
            original = copy.deepcopy(f.request['companion']); f.request['companion'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): f.register()
            f.request['companion'] = original
        for key, value in [('game_edition', 'vr'), ('se_new_game_ui', False), ('reuse_test_profile', {'enabled': True})]:
            original = copy.deepcopy(f.config); f.config[key] = value; m.write(f.root / 'config.json', f.config)
            with self.subTest(key=key), self.assertRaises(ValueError): f.register()
            f.config = original
        f.config['interactive_session']['maximumSeconds'] = 599; m.write(f.root / 'config.json', f.config)
        with self.assertRaisesRegex(ValueError, 'interactive owner'): f.register()

    def test_release_predicate_requires_every_actual_component_case(self):
        f = self.fixture; f.register(); plan = f.p.qualification_verify(f.p.qualification_show('candidate-one'))
        run = f.root / 'native-run'; m.write(run / 'result.json', {'checks': [{'name': 'tool-check', 'result': 'passed'}]})
        packet = {'kind': 'tool-qualification-result', 'executionOutcome': 'passed', 'testResult': {'testingStarted': True,
            'coverage': {'checks': [{'name': 'tool-check', 'status': 'passed'}]}, 'auxiliaryCoverage': {'checks': []}}, 'runDirectory': str(run)}
        self.assertFalse(f.p.qualification_successful_result(plan, packet))
        packet['toolCompanion'] = {'completed': True, 'uncertain': False, 'subjectStarted': True, 'scope': 'tool-qualification-only',
            'subjectModAccepted': False, 'checks': [{'name': name, 'result': 'passed'} for name in ('case-one', 'case-two')]}
        self.assertTrue(f.p.qualification_successful_result(plan, packet))
        for field, bad in [('completed', False), ('uncertain', True), ('subjectStarted', False)]:
            original = packet['toolCompanion'][field]; packet['toolCompanion'][field] = bad
            with self.subTest(field=field): self.assertFalse(f.p.qualification_successful_result(plan, packet))
            packet['toolCompanion'][field] = original
        packet['toolCompanion']['checks'][1]['result'] = 'not_run'
        self.assertFalse(f.p.qualification_successful_result(plan, packet))


class DispatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup); self.root = Path(temporary.name)
        self.folder = self.root / 'qualification'; self.folder.mkdir()
        self.worker = {'pid': os.getpid(), 'birth': 123, 'path': str(Path(sys.executable).resolve())}
        self.game = {'pid': 4242, 'birth': 12345, 'path': str(self.root / 'SkyrimSE.exe')}
        self.config = {'runtime': str(self.root / 'runtime'), 'game_edition': 'se', 'interactive_session': {'maximumSeconds': 600,
            'sourceId': 'operator.actions', 'channelConfig': str(self.root / 'channel.json')}}
        m.write(self.folder / 'config.json', self.config); m.write(self.folder / 'worker.json', {'identity': self.worker})
        self.component_plan = self.root / 'plan.json'
        m.write(self.component_plan, {'checks': [{'name': 'case-one', 'role': 'subject'}], 'bounds': {'maximumSeconds': 600, 'maximumCommands': 256}})
        self.plan = {'id': 'one', 'executor': str(self.root / 'executor'), 'executorPins': [], 'configuration': self.config,
            'companion': {'maximumSeconds': 600, 'plan': {'path': str(self.component_plan), 'sha256': m.digest(self.component_plan)},
                'sequencer': {'path': str(self.root / 'sequencer.py'), 'sha256': 'a' * 64}, 'transport': {'path': str(self.root / 'transport.py'), 'sha256': 'b' * 64}}}
        self.manager = {'pid': 4243, 'birth': 12346, 'path': str(self.root / 'ModOrganizer.exe')}
        owned_ini, backup = self.root / 'owned.ini', self.root / 'original.ini'
        owned_ini.write_text('owned selection'); backup.write_text('original selection')
        self.owned_witness = {'scope': 'offline-owned-MO2-witness', 'manager': self.manager,
                              'path': str(owned_ini), 'liveSha256': m.digest(owned_ini),
                              'backup': {'path': str(backup)}, 'originalSha256': m.digest(backup)}
        self.p = SimpleNamespace(qualification_show=lambda _: {'status': 'running'}, qualification_verify=Mock(return_value=self.plan),
                                 qualification_verify_owned_mo2=Mock(return_value=self.owned_witness))
        identities = {row['pid']: row for row in (self.worker, self.game, self.manager)}
        self.runner = SimpleNamespace(native=SimpleNamespace(identity=lambda pid: identities.get(pid)))
        config_module = ModuleType('skyrim_autotest.config'); config_module.load = lambda path: m.read(path)
        package = ModuleType('skyrim_autotest'); package.config = config_module
        self.modules = patch.dict(sys.modules, {'skyrim_autotest': package, 'skyrim_autotest.config': config_module}); self.modules.start(); self.addCleanup(self.modules.stop)
        self.spawned = threading.Event(); self.native_calls = 0

    def state(self):
        return {'id': 'fresh-run', 'order': {'id': 'qualification-one'}, 'runner': self.worker, 'game': self.game,
            'owned': [{'role': 'game', 'identity': self.game}], 'configuration': self.config, 'phase': 'interactive-session',
            'deadline': time.time() + 605, 'gameplayBootstrap': {'completed': True},
            'interactiveSession': {'sessionId': 'game-fresh-run', 'ready': True, 'maximumSeconds': 600,
                'binding': {'provider': 'skyrim-autotest', 'conversationId': 'fresh-run', 'agentId': 'owned-game-executor'}}}

    def native(self):
        self.native_calls += 1
        m.write(Path(self.config['runtime']) / 'runs/fresh-run/state.json', self.state())
        self.assertTrue(self.spawned.wait(3), 'Client hook never observed the exact held run')
        return 0

    def test_actual_native_plus_five_deadline_and_single_retained_client(self):
        identity = dict(self.worker, pid=5555, birth=55555)
        class Child:
            pid = 5555; returncode = 0
            def poll(self): return self.returncode
            def terminate(self): raise AssertionError('Already-ended retained client must not be terminated')
            def wait(self, timeout=None): return 0
        tracker = SimpleNamespace(snapshot=lambda: {'schemaVersion': 1, 'status': 'exited', 'identityVerified': True,
            'identity': identity, 'exitCodeAvailable': True, 'exitCode': 0, 'exitCodeHex': '0x00000000'}, close=lambda: {'closed': True})
        def spawn(argv, **kwargs): self.argv = argv; self.spawned.set(); return Child()
        with patch.object(route.subprocess, 'Popen', side_effect=spawn) as popen, patch.object(route, '_retain_client', return_value=(identity, tracker)):
            result = route.run(self.p, self.plan, {'expires': time.time() + 900}, self.folder, self.runner, self.native)
        self.assertEqual(result, 0); self.assertEqual(self.native_calls, 1); self.assertEqual(popen.call_count, 1)
        flags = dict(zip(self.argv[2::2], self.argv[3::2]))
        self.assertEqual(flags['--order-id'], 'qualification-one'); self.assertEqual(flags['--attempt-id'], 'qualification-one')
        self.assertEqual(json.loads(flags['--worker-identity']), self.worker); self.assertEqual(json.loads(flags['--game-identity']), self.game)
        self.assertEqual(flags['--maximum-seconds'], '600')
        dispatch = m.read(self.folder / 'subject-companion/dispatch.json')
        self.assertEqual(dispatch['client']['identity'], identity); self.assertEqual(dispatch['client']['exit']['exitCode'], 0)
        self.assertFalse(dispatch['client']['terminatedOwnedClient'])
        self.p.qualification_verify.assert_called_once()
        self.p.qualification_verify_owned_mo2.assert_called_once()
        self.assertEqual(dispatch['ownedMO2Admission'], self.owned_witness)

    def test_insufficient_original_outer_budget_refuses_before_native_or_client(self):
        with patch.object(route.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ValueError, 'before native start'):
                route.run(self.p, self.plan, {'expires': time.time() + 650}, self.folder, self.runner, self.native)
        self.assertEqual(self.native_calls, 0); popen.assert_not_called()

    def test_post_admission_game_identity_loss_refuses_the_single_client_spawn(self):
        original = self.runner.native.identity
        def admitted(*args):
            def changed(pid):
                if pid == self.game['pid']:
                    self.spawned.set()  # Release the synthetic native wait; no process was started.
                    return None
                return original(pid)
            self.runner.native.identity = changed
            return self.owned_witness
        self.p.qualification_verify_owned_mo2.side_effect = admitted
        with patch.object(route.subprocess, 'Popen') as popen:
            self.assertEqual(route.run(self.p, self.plan, {'expires': time.time() + 900},
                                       self.folder, self.runner, self.native), 0)
        popen.assert_not_called()
        dispatch = m.read(self.folder / 'subject-companion/dispatch.json')
        self.assertIn('identity changed before client spawn', dispatch['error'])

    def test_changed_original_pre_native_pin_refuses_before_any_native_start(self):
        self.p.qualification_verify.side_effect = ValueError('changed original pre-native pin')
        with patch.object(route.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ValueError, 'changed original pre-native pin'):
                route.run(self.p, self.plan, {'expires': time.time() + 900}, self.folder, self.runner, self.native)
        self.assertEqual(self.native_calls, 0)
        popen.assert_not_called()

    def test_deadline_extension_and_wrong_worker_refuse(self):
        state = self.state(); state['deadline'] += 30
        with self.assertRaisesRegex(ValueError, 'extended'): route._ready(state, self.worker, self.config, 600)
        state = self.state(); state['runner'] = dict(self.worker, birth=999)
        with self.assertRaisesRegex(ValueError, 'worker changed'): route._ready(state, self.worker, self.config, 600)


class CollectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup); self.root = Path(temporary.name)
        self.e = evidence_fixture.CompanionEvidenceTests()
        with patch('test_companion_evidence.tempfile.TemporaryDirectory', return_value=SimpleNamespace(name=str(self.root / 'qualifications'), cleanup=lambda: None)):
            self.e.setUp()
        self.addCleanup(self.e.doCleanups)
        e = self.e
        e.order['id'] = 'qualification-order'; e.state['order']['id'] = e.order['id']
        e.state.update(done=True, restored=True, restoreErrors=[])
        e.order['subjectPlan']['maximumSeconds'] = 600
        e.plan_pin = e.write(Path(e.plan_pin['path']), {'checks': [{'name': name, 'role': 'subject'} for name in e.names],
            'bounds': {'maximumSeconds': 600, 'maximumCommands': 256}, 'fixture': {'cell': 'QASmoke'}})
        e.order['subjectPlan']['plan'] = e.plan_pin
        e.steps, e.events, e.actions, e.cases = [], [], [], []
        for number, name in enumerate(e.names, 1):
            action, raw = e.action(number, name); e.actions.append(action)
            e.cases.append({'id': name, 'status': 'passed', 'commandIds': [action['commandId']], 'evidence': [raw]})
        e.actions.append(e.action(len(e.names) + 1, None)[0])
        e.report.update(orderId=e.order['id'], attemptId=e.order['id'], plan=e.plan_pin, cases=e.cases, actions=e.actions,
            subjectStart={'caseId': e.names[0], 'commandId': e.actions[0]['commandId'], 'sourceEventId': e.actions[0]['sourceEventId'], 'deliveredEvidence': e.actions[0]['deliveredEvidence']})
        e.dispatch = e.dispatch_record(); e.write(e.folder / 'dispatch.json', e.dispatch); e.write(e.run / 'state.json', e.state); e.save()
        self.p = SimpleNamespace(local=self.root)
        self.plan = {'id': 'order', 'executor': e.frozen['executor'], 'configuration': e.frozen['configuration'], 'executorPins': [],
            'companion': {'maximumSeconds': 600, 'transport': e.transport, 'plan': e.plan_pin, 'sequencer': e.sequencer_pin}}
        self.death = patch.object(route, 'verify_processes_dead', return_value=True); self.dead = self.death.start(); self.addCleanup(self.death.stop)

    def test_all_actual_delivered_case_proof_and_full_packet_pins(self):
        result = route.collect(self.p, self.plan, self.e.run)
        self.assertTrue(result['completed']); self.assertFalse(result['uncertain']); self.assertFalse(result['subjectModAccepted'])
        self.assertEqual(len(result['checks']), 17)
        self.assertEqual(result['scope'], 'tool-qualification-only')
        self.assertEqual(self.dead.call_args.args[1], [self.e.client_identity, self.e.child_identity])
        packet = {'runDirectory': str(self.e.run), 'toolCompanion': result, 'files': result['pins']}
        route.verify_packet(self.p, self.plan, packet)
        packet['files'] = packet['files'][1:]
        with self.assertRaisesRegex(ValueError, 'absent'): route.verify_packet(self.p, self.plan, packet)

    def test_missing_native_delivery_wrong_identity_and_inner_exit_never_pass(self):
        e = self.e
        e.steps.pop(0); e.save()
        with self.assertRaisesRegex(ValueError, 'delivery'): route.collect(self.p, self.plan, e.run)
        e.steps.insert(0, m.read(e.actions[0]['deliveredEvidence']['path'])); e.save()
        e.report['game'] = dict(e.game, birth=999); e.save()
        with self.assertRaisesRegex(ValueError, 'identity'): route.collect(self.p, self.plan, e.run)
        e.report['game'] = e.game; e.report['sequencerProcess']['returnCode'] = 1; e.save()
        stopped = route.collect(self.p, self.plan, e.run)
        self.assertFalse(stopped['completed']); self.assertTrue(stopped['uncertain'])
        self.assertFalse(route.successful(self.plan, {'toolCompanion': stopped}))

    def test_unknown_process_death_or_unrestored_native_run_stays_uncollectable(self):
        self.dead.return_value = False
        with self.assertRaisesRegex(ValueError, 'death verification'): route.collect(self.p, self.plan, self.e.run)
        self.dead.return_value = True; self.e.state['restored'] = False; self.e.write(self.e.run / 'state.json', self.e.state)
        with self.assertRaisesRegex(ValueError, 'restoration'): route.collect(self.p, self.plan, self.e.run)


class ProcessDeathTests(unittest.TestCase):
    def test_fresh_isolated_observer_checks_birth_and_refuses_unknown_same_pid(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); package = root / 'executor/skyrim_autotest'; package.mkdir(parents=True)
            (package / '__init__.py').write_text('')
            native = package / 'native.py'
            expected = {'pid': 111, 'birth': 222, 'path': str(root / 'old-client.exe')}
            for birth, accepted in ((333, True), (222, False), (None, False)):
                native.write_text('def processes(): return [{"pid":111,"name":"offline-client"}]\n' +
                    ('def identity(pid): return None\n' if birth is None else f'def identity(pid): return {{"pid":pid,"birth":{birth},"path":"offline"}}\n'))
                plan = {'executor': str(package.parent), 'executorPins': [{'path': str(native), 'sha256': m.digest(native)}]}
                if accepted: self.assertTrue(route.verify_processes_dead(plan, [expected]))
                else:
                    with self.assertRaisesRegex(ValueError, 'death unproven'): route.verify_processes_dead(plan, [expected])
            native.write_text('# source changed before independent import\n')
            with self.assertRaisesRegex(ValueError, 'pinned native'): route.verify_processes_dead(plan, [expected])


if __name__ == '__main__': unittest.main()

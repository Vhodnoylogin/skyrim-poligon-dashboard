"""Offline candidate leases; fake native evidence never launches an application."""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import polygon as m


FAKE_RUNNER = '''
import json, os
from pathlib import Path
from types import SimpleNamespace
native=SimpleNamespace(processes=lambda: [], identity=lambda pid: {'pid':pid,'birth':1,'path':'offline-worker'}, alive=lambda ident:False)
P=SimpleNamespace()
def configure(config):
 global C
 C=config
 P.mo2_ini=Path(config['ini'])
def request(*args,**kwargs): return {}
def recover(): pass
def run(profile,scenario_file,**kwargs):
 scenario=json.loads(Path(scenario_file).read_text())
 request(1,'run')
 if scenario.get('secondLaunch'): request(1,'run')
 run=Path(C['runtime'])/'runs'/'offline'
 run.mkdir(parents=True)
 archive=run/'test-profile'
 archive.mkdir()
 (archive/'settings.ini').write_text('preserved')
 game={'pid':42,'birth':43,'path':'offline-game'}
 state={'order':kwargs['order'],'done':True,'restored':True,'restoreErrors':[],
  'profileArchive':str(archive),'testProfile':str(run/'removed-profile'),
  'owned':[{'role':'game','identity':game}],'game':game,'ownedGameRestartCount':0}
 (run/'state.json').write_text(json.dumps(state))
 (run/'result.json').write_text(json.dumps({'restored':True,'restoreErrors':[],'result':'passed'}))
 return 0
'''


class QualificationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.p = m.Polygon(self.root)
        self.candidate = self.root / 'candidate'
        pkg = self.candidate / 'skyrim_autotest'
        pkg.mkdir(parents=True)
        (pkg / '__init__.py').write_text('')
        (pkg / 'runner.py').write_text(FAKE_RUNNER)
        (pkg / 'config.py').write_text('import json\nfrom pathlib import Path\ndef load(p): return json.loads(Path(p).read_text())\n')
        (pkg / 'scenarios.py').write_text('def validate(s): return None\n')
        (pkg / 'restart_budget.py').write_text("def plan(s): return {'maximum':0}\n")
        self.ini = self.root / 'mo2.ini'
        self.ini.write_text('selected_profile=Core\n')
        self.host = {'executor': str(self.root / 'old-executor'), 'other': 'preserved'}
        m.write(self.p.local / 'config.json', self.host)
        self.config = {'runtime': str(self.root / 'runtime'), 'ini': str(self.ini)}
        self.scenario = {'schemaVersion': 1, 'steps': [{'name': 'tool-check', 'tool': 'inspect',
                          'args': {'kind': 'state'}, 'assert': [{'path': 'ready', 'equals': True}]}]}
        m.write(self.root / 'config.json', self.config)
        m.write(self.root / 'scenario.json', self.scenario)
        self.order = {'schemaVersion': 1, 'id': 'tool-order', 'mode': 'automatic', 'sourceThreadId': 'root',
                      'sourceChat': 'autotest', 'subject': 'Executor qualification', 'purpose': 'Tool checks',
                      'profile': 'Core', 'config': 'config.json', 'scenario': 'scenario.json', 'inputs': [],
                      'collect': ['tool evidence'], 'testing': {'start': {'kind': 'check', 'name': 'tool-check'},
                                  'checks': [{'name': 'tool-check', 'role': 'subject'}]}}
        m.write(self.root / 'order.json', self.order)
        self.owner = self.root / 'owner.txt'
        self.owner.write_text('One tool qualification start only')
        m.write(self.root / 'accounting.json', {'cumulativeActualGameStarts': 10, 'verifiedBy': 'offline', 'reason': 'Offline fixture'})
        self.request = {'schemaVersion': 1, 'kind': 'tool-qualification', 'id': 'candidate-one',
                        'order': 'order.json', 'executor': str(self.candidate), 'maximumActualGameStarts': 1,
                        'maximumWallSeconds': 900, 'deadlineUtc': time.time()+1800,
                        'cumulativeActualGameStartsBefore': 10, 'verifiedBy': 'offline', 'reason': 'Offline only',
                        'launchAccounting': {'path': 'accounting.json', 'sha256': m.digest(self.root/'accounting.json')},
                        'ownerAuthorization': {'threadId': 'root', 'messageId': 'human',
                         'path': str(self.owner), 'sha256': m.digest(self.owner), 'verifiedBy': 'offline',
                         'quote': self.owner.read_text()}}
        self.path = self.root / 'qualification.json'

    def register(self):
        m.write(self.path, self.request)
        return self.p.register_qualification(self.path)

    def test_single_candidate_execution_preserves_host_and_retains_old_queue_barrier(self):
        self.register()
        self.assertTrue(self.p.qualification_check('candidate-one')['validated'])
        packet = self.p.qualification_run('candidate-one')
        self.assertEqual(packet['actualGameStarts'], 1)
        self.assertEqual(packet['cumulativeActualGameStartsAfter'], 11)
        self.assertFalse(packet['globalProviderQualified'])
        self.assertEqual(m.read(self.p.local/'config.json'), self.host)
        self.assertEqual(len(self.p.pipeline_status()['holds']), 1)
        self.assertIsNone(self.p.claim())
        self.assertFalse(self.p.pending())
        with self.assertRaisesRegex(ValueError, 'only once'):
            self.p.qualification_run('candidate-one')

    def test_existing_hold_survives_registration_and_blocks_dispatch(self):
        self.p.hold_pipeline('old', 'Recovery review')
        self.register()
        with self.assertRaisesRegex(ValueError, 'no other holds'):
            self.p.qualification_run('candidate-one')
        self.assertEqual(self.p.qualification_show('candidate-one')['status'], 'prepared')
        self.assertEqual(len(self.p.pipeline_status()['holds']), 2)

    def test_immutable_candidate_config_scenario_owner_and_host_pins(self):
        for index, file in enumerate(['candidate/skyrim_autotest/runner.py', 'config.json', 'scenario.json', 'owner.txt', 'local/skyrim-polygon/config.json']):
            with self.subTest(file=file):
                if index == 0:
                    self.register()
                path = self.root / file
                before = path.read_bytes()
                path.write_bytes(before+b' ')
                with self.assertRaises(ValueError):
                    self.p.qualification_run('candidate-one')
                path.write_bytes(before)
        (self.candidate / 'new.py').write_text('# inventory drift')
        with self.assertRaisesRegex(ValueError, 'inventory changed'):
            self.p.qualification_run('candidate-one')

    def test_registration_is_idempotent_and_rejects_changed_request(self):
        self.register()
        self.assertTrue(self.p.register_qualification(self.path)['duplicate'])
        self.request['reason'] = 'Changed'
        with self.assertRaisesRegex(ValueError, 'immutable'):
            self.register()

    def test_live_owner_blocks_registration(self):
        with self.p.connect() as con:
            con.execute("INSERT INTO jobs(id,mode,subject,origin,status,submitted,request) VALUES('live','automatic','s','o','running',1,'{}')")
        with self.assertRaisesRegex(ValueError, 'Recover existing owner'):
            self.register()

    def test_restarts_and_mod_workflows_are_not_accepted(self):
        self.scenario['steps'][0]['args'] = {'operation': 'input.perform', 'request': {'action': 'restart_game'}}
        m.write(self.root/'scenario.json', self.scenario)
        with self.assertRaisesRegex(ValueError, 'forbids restarts'):
            self.register()
        self.order['schemaVersion'] = 2
        m.write(self.root/'order.json', self.order)
        with self.assertRaisesRegex(ValueError, 'Dedicated schema1'):
            self.register()

    def test_expired_authority_does_not_claim(self):
        self.register()
        with patch('time.time', return_value=self.request['deadlineUtc']+1):
            with self.assertRaisesRegex(ValueError, 'deadline'):
                self.p.qualification_run('candidate-one')

    def test_child_crash_without_native_evidence_retains_uncertainty(self):
        self.register()
        with self.p.connect() as con:
            con.execute("UPDATE qualifications SET status='running',expires=?", (time.time()+900,))
            con.execute("INSERT INTO attempts VALUES('qualification-candidate-one',1)")
        folder = self.p.local/'qualifications/candidate-one'
        m.write(folder/'child-exit.json', {'returncode': 2})
        self.assertEqual(self.p.qualification_collect('candidate-one')['status'], 'running')
        self.assertEqual(self.p.qualification_show('candidate-one')['status'], 'running')
        self.assertEqual(len(self.p.pipeline_status()['holds']), 1)

    def test_parent_timeout_does_not_dispatch_a_second_attempt(self):
        self.register()
        with patch('qualification.subprocess.run', side_effect=subprocess.TimeoutExpired('child', 900)):
            packet = self.p.qualification_run('candidate-one')
        self.assertEqual(packet['actualGameStarts'], 0)  # no child/native admission in fixture
        self.assertFalse(packet['testingStarted'])
        with self.assertRaisesRegex(ValueError, 'only once'):
            self.p.qualification_run('candidate-one')

    def test_bridge_launch_guard_blocks_a_second_launch(self):
        self.scenario['secondLaunch'] = True
        m.write(self.root/'scenario.json', self.scenario)
        self.register()
        packet = self.p.qualification_run('candidate-one')
        self.assertEqual(packet['status'], 'running')  # failed child; never invent zero/coverage
        log = self.p.local/'qualifications/candidate-one/executor.log'
        self.assertIn('launch budget exhausted', log.read_text())

    def test_lease_cannot_be_cleared_before_final_collection(self):
        self.register()
        clearance = {'holdId': 'qualification-candidate-one', 'installationSettled': True,
                     'ownerAuthorization': self.request['ownerAuthorization']}
        m.write(self.root/'clearance.json', clearance)
        with self.assertRaisesRegex(ValueError, 'proven completion'):
            self.p.clear_pipeline('qualification-candidate-one', self.root/'clearance.json')

    def test_clearing_old_hold_keeps_released_old_jobs_behind_qualification_lease(self):
        with self.p.connect() as con:
            con.execute("INSERT INTO jobs(id,mode,subject,origin,status,submitted,request) VALUES('old','automatic','old','other','queued',1,'{}')")
            con.execute("INSERT INTO released_orders VALUES('old','old-release')")
        self.p.hold_pipeline('old-hold', 'False prelaunch hold')
        self.register()
        m.write(self.root/'clear.json', {'holdId': 'old-hold', 'installationSettled': True,
                    'ownerAuthorization': self.request['ownerAuthorization']})
        self.p.clear_pipeline('old-hold', self.root/'clear.json')
        self.assertIsNone(self.p.claim())
        self.p.qualification_run('candidate-one')
        self.assertIsNone(self.p.claim())
        self.assertEqual(self.p.get('old')['status'], 'queued')

    def test_collection_verifies_retained_result_and_manifest(self):
        self.register()
        original = self.p.qualification_run('candidate-one')
        self.assertEqual(self.p.qualification_collect('candidate-one'), original)
        Path(original['runDirectory'], 'result.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            self.p.qualification_collect('candidate-one')

    def test_recovery_retains_unknown_worker_and_live_restoration(self):
        self.register()
        with self.p.connect() as con:
            con.execute("UPDATE qualifications SET status='running',expires=?", (time.time()+900,))
        result = self.p.qualification_recover('candidate-one')
        self.assertEqual(result['status'], 'running')
        self.assertIn('Unproven worker completion', result['reason'])

    def test_unrestored_native_run_cannot_release_lease(self):
        self.register()
        packet = self.p.qualification_run('candidate-one')
        state_file = Path(packet['runDirectory'])/'state.json'
        state = m.read(state_file)
        state['restored'] = False
        m.write(state_file, state)
        with self.p.connect() as con:
            con.execute("UPDATE qualifications SET status='running',packet=NULL")
        self.assertIn('restoration unproven', self.p.qualification_collect('candidate-one')['reason'])
        self.assertIsNone(self.p.claim())


if __name__ == '__main__':
    unittest.main()

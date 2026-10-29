"""Offline first-client admission; no live queue, game or process access."""
import copy
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace, ModuleType
import unittest
from unittest.mock import MagicMock, patch

import polygon as m
import qualification_companion as route
import qualification_manual_client as target
import test_qualification_startup_native as fixture


class ManualClientTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture.NativeStartupTests(); self.base.setUp(); self.addCleanup(self.base.doCleanups)
        self.f = f = self.base.f
        f.plan['configuration'].update(game_edition='se', interactive_session={'channelConfig': str(f.root / 'channel.json')})
        f.plan['deadlineUtc'] = time.time() + 9000
        f.write(f.plan['companion']['plan']['path'], {'checks': [{'name': 'owner-controlled-manual-scene', 'role': 'subject'}],
            'scope': 'Owner-controlled scene and observed actions; no whole-mod acceptance'})
        f.plan['companion']['plan']['sha256'] = m.digest(f.plan['companion']['plan']['path'])
        f.state.update(done=False, restored=False, phase='interactive-session', deadline=time.time() + 600,
            configuration=copy.deepcopy(f.plan['configuration']), gameplayBootstrap={'completed': True})
        f.state.pop('guardianRecovery', None)
        f.state['interactiveSession'] = {'ready': True, 'sessionId': 'game-' + f.state['id'],
            'maximumSeconds': f.plan['companion']['maximumSeconds'],
            'binding': {'provider': 'skyrim-autotest', 'conversationId': f.state['id'], 'agentId': 'owned-game-executor'}}
        self.dispatch = {'schemaVersion': 1, 'orderId': 'qualification-q-one', 'qualificationId': 'q-one', 'worker': f.worker,
            'error': target.ERROR, 'errorDetails': {'operation': 'qualification-companion', 'traceback': 'trace\n' + target.ERROR}}
        f.write(f.comp / 'dispatch.json', self.dispatch)
        f.write(f.comp / 'executor-manifest.json', {'schemaVersion': 1, 'files': f.plan['executorPins']})
        f.write(f.folder / 'plan.json', f.plan); f.write(f.folder / 'config.json', f.plan['configuration'])
        f.write(f.run / 'state.json', f.state)
        (f.run / 'steps.jsonl').write_text(json.dumps({'kind': 'phase', 'name': 'interactive-session', 'deadline': f.state['deadline']})+'\n')
        with f.p.connect() as con:
            con.execute('UPDATE qualifications SET request=?,expires=? WHERE id=?', (json.dumps(f.plan), time.time()+1200, 'q-one'))
        self.runner = SimpleNamespace(native=SimpleNamespace(identity=lambda pid: {f.worker['pid']: f.worker, f.game['pid']: f.game}[pid]))
        self.review = {'schemaVersion': 1, 'kind': 'qualification-first-manual-client-admission', 'qualificationId': 'q-one',
            'verifiedBy': 'Offline operator', 'summary': 'Same owned session, no prior client', 'implementationPins': target.implementation_pins(),
            'plan': f.pin(f.folder / 'plan.json'), 'previousDispatch': f.pin(f.comp / 'dispatch.json'),
            'ownerEvidence': f.pin(f.folder / 'worker.json'), 'worker': f.worker, 'game': f.game, 'statePath': str(f.run / 'state.json')}
        for key in ('manualOnlyReviewed','sameOwnedSessionReviewed','noPriorClientReviewed','originalDeadlineReviewed',
                    'currentOwnerAuthorityReviewed','originalPinsReviewed'):self.review[key]=True
        self.review_path=f.root/'manual-review.json';f.write(self.review_path,self.review)

    def fresh(self):
        fake_config = ModuleType('skyrim_autotest.config');fake_config.load=lambda path:self.f.plan['configuration']
        package = ModuleType('skyrim_autotest');package.config=fake_config
        with patch.dict('sys.modules',{'skyrim_autotest':package,'skyrim_autotest.config':fake_config}):
            return target.fresh(self.f.plan,self.f.folder,self.f.run/'state.json',self.f.worker,self.f.game,self.runner)

    def test_fresh_original_native_ready_and_deadline_are_required(self):
        self.assertEqual(self.fresh()['game'],self.f.game)
        self.f.state['deadline'] += 1;self.f.write(self.f.run/'state.json',self.f.state)
        with self.assertRaisesRegex(ValueError,'original phase'):self.fresh()

    def test_no_prior_claim_registry_or_action_can_be_replayed(self):
        for key in ('interactiveActorFixtures','morphSession','interactiveArtifacts'):
            self.f.state[key]={'prior':True};self.f.write(self.f.run/'state.json',self.f.state)
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'prior client'):self.fresh()
            self.f.state.pop(key)
        self.f.write(self.f.run/'state.json',self.f.state)
        (self.f.run/'steps.jsonl').write_text(json.dumps({'kind':'interactive-action-delivered'})+'\n')
        with self.assertRaisesRegex(ValueError,'prior native action'):self.fresh()

    def test_prior_error_is_exact_and_client_intent_is_terminal(self):
        self.assertEqual(target.prior(self.f.plan,self.f.folder),self.f.comp/'dispatch.json')
        changed={**self.dispatch,'client':{}}
        self.f.write(self.f.comp/'dispatch.json',changed)
        with self.assertRaisesRegex(ValueError,'terminal pre-client'):target.prior(self.f.plan,self.f.folder)
        self.f.write(self.f.comp/'dispatch.json',self.dispatch)
        (self.f.comp/'report.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'prior client output'):target.prior(self.f.plan,self.f.folder)

    def test_one_original_client_only_additive_dispatch_and_no_native_relaunch(self):
        f=self.f;original=(f.comp/'dispatch.json').read_bytes()
        child=MagicMock();child.poll.return_value=0;child.returncode=0
        tracker=MagicMock();tracker.snapshot.return_value={'identityVerified':True,'exitCode':0};tracker.close.return_value={'closed':True}
        client={'pid':555,'birth':1234,'path':str(Path(__import__('sys').executable))}
        with patch.object(target,'_runner',return_value=self.runner),patch.object(target,'fresh',return_value=f.state), \
                patch.object(f.p,'qualification_verify_owned_mo2',return_value={'liveSha256':'a'*64}), \
                patch.object(target.subprocess,'Popen',return_value=child) as spawn, \
                patch.object(target,'_retain_client',return_value=(client,tracker)):
            result=target.admit(f.p,'q-one',self.review_path)
            self.assertEqual(result['returncode'],0)
            self.assertEqual(spawn.call_count,1)
            argv=spawn.call_args.args[0]
            self.assertEqual(argv[1],f.plan['companion']['transport']['path'])
            self.assertEqual(argv[argv.index('--output')+1],str(f.folder/target.DIRECTORY/'subject-companion/report.json'))
            with self.assertRaisesRegex(ValueError,'already attempted'):target.admit(f.p,'q-one',self.review_path)
            self.assertEqual(spawn.call_count,1)
        self.assertEqual((f.comp/'dispatch.json').read_bytes(),original)
        self.assertEqual(f.p.qualification_show('q-one')['status'],'running')
        self.assertEqual(len(f.p.pipeline_status()['holds']),1)
        admission=m.read(f.folder/target.DIRECTORY/'admission.json')
        self.assertEqual(admission['physicalGameStartsAdded'],0)
        self.assertFalse(admission['nativeOwnerReplaced'])

    def test_expiry_during_last_witness_never_spawns_a_client(self):
        f=self.f;wall=[time.time()];calls=[]
        def witness(*args):
            calls.append(True)
            if len(calls)==2:wall[0]=f.state['deadline']+1
            return {'liveSha256':'a'*64}
        with patch.object(target,'_runner',return_value=self.runner),patch.object(target,'fresh',return_value=f.state), \
                patch.object(f.p,'qualification_verify_owned_mo2',side_effect=witness), \
                patch.object(target.time,'time',side_effect=lambda:wall[0]),patch.object(target.subprocess,'Popen') as spawn:
            with self.assertRaisesRegex(ValueError,'expired before client spawn'):target.admit(f.p,'q-one',self.review_path)
        spawn.assert_not_called()

    def test_collection_uses_explicit_additive_context_and_keeps_original_refusal(self):
        f=self.f;f.state.update(done=True,restored=True,restoreErrors=[]);f.write(f.run/'state.json',f.state)
        output=f.folder/target.DIRECTORY;output.mkdir()
        admission={'kind':'same-native-first-manual-client','qualificationId':'q-one','physicalGameStartsAdded':0,
            'nativeOwnerReplaced':False,'plan':self.review['plan'],'previousDispatch':self.review['previousDispatch'],
            'review':f.pin(self.review_path),'statePath':str(f.run/'state.json'),'maximumSeconds':f.plan['companion']['maximumSeconds'],
            'worker':f.worker,'game':f.game,'at':time.time(),'nativeDeadline':f.state['deadline'],'outerExpires':time.time()+1200}
        retained=[];(output/'implementation').mkdir()
        for source in self.review['implementationPins']:
            dest=output/'implementation'/Path(source['path']).name;dest.write_bytes(Path(source['path']).read_bytes())
            retained.append({'originalPath':source['path'],'path':str(dest),'sha256':source['sha256']})
        admission['implementation']=retained
        f.write(output/'admission.json',admission)
        with patch.object(route.companion_evidence,'collect',return_value={'pins':[]}) as collect:
            summary=route.collect(f.p,f.plan,f.run)
        self.assertEqual(collect.call_args.args[0].folder,output)
        self.assertTrue(summary['firstManualClientAdmission'])
        self.assertEqual(m.read(f.comp/'dispatch.json'),self.dispatch)
        self.assertTrue(summary['pins'])
        Path(retained[0]['path']).write_bytes(b'changed retained source')
        with self.assertRaises(ValueError):target.collection_context(f.p,f.plan,f.folder,f.run)


if __name__=='__main__':unittest.main()

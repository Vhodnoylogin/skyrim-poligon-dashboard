"""Offline held selection/projection; no real executor, queue or game is used."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch,Mock

import polygon as m
import held_semantic as route
import held_semantic_evidence as evidence
from test_subject_companion_route import CompanionRouteTests
from test_companion_evidence import CompanionEvidenceTests


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.f=CompanionRouteTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        f=self.f;self.p=f.p
        self.order=copy.deepcopy(f.order);self.order['id']='held-original'
        self.order['inputs']=[self.order['inputs'][0]]
        names=['step-'+str(index) for index in range(17)]
        self.order['subjectPlan']={'interface':'polygon-actions/1','fixture':{'cell':'QASmoke','startMode':'new-game'},'steps':[
            {'name':name,'operation':'world.read','parameters':{'request':{}},'timeout':5,'assert':[{'field':'actual','equals':True}]} for name in names]}
        self.order['testing']={'start':{'kind':'check','name':names[12]},'checks':[{'name':name,'role':'fixture' if i<12 else 'subject'} for i,name in enumerate(names)]}
        self.file=f.root/'semantic-order.json';m.write(self.file,self.order);self.p.submit(self.file)
        self.order=json.loads(self.p.get(self.order['id'])['request']);m.write(self.file,self.order)
        cfg=copy.deepcopy(f.cfg);old=copy.deepcopy(cfg);old['runtime']=str(f.root/'baseline-runtime');m.write(f.baseline_config,old)
        f.qplan.update(configuration=old,companion={'transport':f.pin(f.transport)})
        f.qplan['pins']=[f.pin(f.provider),f.pin(f.baseline_config)]
        f.packet['toolCompanion']={'scope':'tool-qualification-only','completed':True,'uncertain':False,'subjectStarted':True,
            'checks':[{'name':'native-'+str(i),'result':'passed'} for i in range(9)]}
        m.write(f.packetfile,f.packet)
        with self.p.connect() as con:
            con.execute('UPDATE qualifications SET request=?,packet=? WHERE id=?',(json.dumps(f.qplan),json.dumps(f.pin(f.packetfile)),f.qid))
        self.operations={'world.read':{'tool':'inspect','args':{'kind':'state'},'fields':{'actual':'actual'}}}
        proof={'qualified':True,'interface':'polygon-actions/1','operations':self.operations,'evidence':[f.pin(f.packetfile)],
            'configurationSha256':m.subject_contract.identity(old),'pins':f.qplan['executorPins']}
        self.proof=f.root/'mapping-proof.json';m.write(self.proof,proof)
        self.mapping=f.root/'mapping.json';m.write(self.mapping,{'schemaVersion':1,'interface':'polygon-actions/1','operations':self.operations,'qualification':f.pin(self.proof)})
        self.program=f.root/'compiled.json';scenario=m.subject_contract.compile_plan(self.order['subjectPlan'],self.operations);m.write(self.program,scenario)
        self.module=f.root/'generic-module.py';self.module.write_text('import json\ndef render(spec):\n return "# standalone pinned source\\nSPEC="+json.dumps(spec,sort_keys=True)+"\\n"\n')
        self.spec={'schemaVersion':1,'interface':'held-semantic-plan/1','subjectOrderSha256':m.subject_contract.identity(self.order),
            'originalTesting':self.order['testing'],'scenario':scenario,'bounds':{'maximumSeconds':30,'maximumCommands':2048},
            'provenance':{'order':f.pin(self.file),'mappingManifest':f.pin(self.mapping),'compiledScenario':f.pin(self.program),
                          'sourcePlanSha256':m.subject_contract.identity(self.order['subjectPlan'])}}
        self.execution=f.root/'execution.json';m.write(self.execution,{'checks':[{'name':name,'role':'subject'} for name in names],
            'fixture':self.order['subjectPlan']['fixture'],'bounds':self.spec['bounds'],'semantic':self.spec})
        self.seq=f.root/'generated.py';self.seq.write_bytes(('# standalone pinned source\nSPEC='+json.dumps(self.spec,sort_keys=True)+'\n').encode('utf-8'))
        self.request={'schemaVersion':1,'kind':'operator-held-semantic','orderId':self.order['id'],
            'subjectOrderSha256':m.subject_contract.identity(self.order),'executor':str(f.executor),'configuration':f.pin(f.config),
            'transport':f.pin(f.transport),'qualificationId':f.qid,'baselinePacket':f.pin(f.packetfile),'holdId':f.hold,
            'ownerAuthorization':f.auth,'verifiedBy':'offline','reason':'One unchanged semantic plan','subjectCapabilitiesUnderTest':True,
            'mappingManifest':f.pin(self.mapping),'compiledProgram':f.pin(self.program),'sequencerModule':f.pin(self.module),
            'sequencer':f.pin(self.seq),'executionPlan':f.pin(self.execution),'maximumSeconds':30}
        self.selection=f.root/'held-selection.json';m.write(self.selection,self.request)

    def bind(self):return route.register(self.p,self.selection)

    def review(self,release=True):
        self.bind();f=self.f
        if release:
            with self.p.connect() as con:
                con.execute('INSERT INTO releases VALUES(?,?)',('held-release',json.dumps({'ownerAuthorization':f.auth})))
                con.execute('INSERT INTO released_orders VALUES(?,?)',(self.order['id'],'held-release'))
        review={'schemaVersion':1,'kind':'operator-held-semantic-admission','orderId':self.order['id'],'binding':f.pin(self.selection),
            'baselinePacket':f.pin(f.packetfile),'ownerAuthorization':f.auth,'verifiedBy':'offline','reason':'Same current human only',
            'preparationReviewed':True,'restorationReviewed':True,'archiveReviewed':True,'exactOnlySubjectReviewed':True,'subjectCapabilitiesUnderTest':True}
        file=f.root/'held-admission.json';m.write(file,review);return file

    def test_bind_pins_unchanged_order_without_claim_or_global_host_change(self):
        before=self.p.get(self.order['id'])['request'];source=self.file.read_bytes()
        self.assertFalse(self.bind()['launch']);self.assertTrue(self.bind()['duplicate'])
        self.assertEqual(self.p.get(self.order['id'])['request'],before)
        self.assertEqual(self.file.read_bytes(),source)
        self.assertEqual((self.p.local/'config.json').read_bytes(),self.f.host_bytes)
        self.assertEqual(self.p.get(self.order['id'])['status'],'queued')

    def test_actual_new_component_qualification_required_without_loosening_old_route(self):
        self.f.packet.pop('toolCompanion');m.write(self.f.packetfile,self.f.packet)
        self.request['baselinePacket']=self.f.pin(self.f.packetfile);m.write(self.selection,self.request)
        with self.p.connect() as con:con.execute('UPDATE qualifications SET packet=? WHERE id=?',(json.dumps(self.f.pin(self.f.packetfile)),self.f.qid))
        with self.assertRaisesRegex(ValueError,'component qualification'):self.bind()

    def test_altered_mapping_compiled_program_code_and_original_order_refuse(self):
        self.bind()
        for file in (self.mapping,self.program,self.seq,self.module,self.execution):
            before=file.read_bytes();file.write_bytes(before+b' ')
            with self.subTest(file=file),self.assertRaises(ValueError):route.find(self.p,self.order)
            file.write_bytes(before)
        changed=copy.deepcopy(self.order);changed['testing']['start']['name']='step-0'
        with self.assertRaises(ValueError):route.find(self.p,changed)

    def test_no_release_cannot_consume_hold_or_claim(self):
        review=self.review(False)
        with self.assertRaisesRegex(ValueError,'currently released'):route.execute(self.p,review)
        self.assertEqual(self.p.get(self.order['id'])['status'],'queued')
        self.assertEqual([row['id'] for row in self.p.pipeline_status()['holds']],[self.f.hold])

    def test_exact_release_claim_freezes_only_preparation_scenario_and_original_compiled_plan(self):
        review=self.review();captured=[]
        def claimed(row):captured.append(route.freeze(self.p,self.order));return {'offline':True}
        with patch.object(self.p,'execute_claimed',side_effect=claimed):self.assertTrue(route.execute(self.p,review)['offline'])
        plan=captured[0]
        self.assertEqual(plan['originalTesting'],self.order['testing'])
        self.assertEqual(plan['subjectOrderSha256'],m.subject_contract.identity(self.order))
        self.assertEqual(plan['scenario']['steps'][0]['name'],'held-semantic-core-preparation')
        self.assertEqual(len(plan['scenario']['steps']),1)
        self.assertEqual(len(plan['compiledProgram']['steps']),17)
        self.assertFalse(route.execute(self.p,review)['rerun'])


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.e=CompanionEvidenceTests();self.e.setUp();self.addCleanup(self.e.doCleanups);e=self.e
        self.order={'schemaVersion':2,'id':e.order['id'],'subjectPlan':{'interface':'polygon-actions/1','fixture':{'cell':'QASmoke','startMode':'new-game'},
            'steps':[]},'inputs':[],'collect':['Independent raw results'],'testing':{'start':{'kind':'check','name':e.names[12]},
            'checks':[{'name':name,'role':'fixture' if index<12 else 'subject'} for index,name in enumerate(e.names)]}}
        scenario={'schemaVersion':1,'cell':'QASmoke','startMode':'new-game','steps':[]}
        for index,name in enumerate(e.names):
            rules=[] if index in (0,13) else [{'path':'actual','equals':True}]
            scenario['steps'].append({'name':name,'tool':'inspect','args':{'kind':'state'},'timeout':5,'assert':rules,**({'observe':True} if not rules else {})})
            self.order['subjectPlan']['steps'].append({'name':name,'operation':'world.read','parameters':{'request':{}},
                'timeout':5,**({'assert':[{'field':'actual','equals':True}]} if rules else {'observe':True})})
            assertion=e.events[index*4+2]['record'];result=e.events[index*4+3]['record']
            if rules:
                assertion.update(check=name+'/assert-0',assertionRole='semantic',rule=rules[0],available=True)
            else:assertion.update(check='transport.receipt-recorded',assertionRole='transport')
            result.update(semanticResult='passed' if rules else 'observed',semanticRole='fixture' if index<12 else 'subject',stepIndex=index)
        self.plan={**e.frozen,'compiledProgram':scenario,'transportPlan':e.plan_pin,'executorPins':[],'pins':[],
            'heldSemanticSelection':{'sequencer':e.sequencer_pin,'maximumSeconds':1200},'subjectOrderSha256':m.subject_contract.identity(self.order)}
        self.p=e.p
        e.state.update(done=True,restored=True,restoreErrors=[]);e.write(e.run/'state.json',e.state);e.save()
        verify=patch.object(route,'verify',return_value=self.plan);verify.start();self.addCleanup(verify.stop)
        death=patch('qualification_companion.verify_processes_dead',return_value=True);death.start();self.addCleanup(death.stop)

    def collect(self):return evidence.collect(self.p,self.order,self.e.run)

    def public_projection(self,summary):
        p=m.Polygon(self.e.root/'projection-host')
        with p.connect() as con:con.execute('INSERT INTO held_semantic_bindings VALUES(?,?,?,?)',(self.order['id'],'{}','unused','unused'))
        packet={'runDirectory':str(self.e.run),'heldSemantic':summary,'files':summary['pins'],'executionOutcome':'passed','reason':''}
        with patch.object(p,'evidence_dir',return_value=self.e.folder.parent),patch.object(p,'executor_auxiliary_checks',return_value=[]),\
             patch.object(p,'execution_summary',return_value={'terminationCause':'normal'}):
            return p.test_projection(self.order,packet)

    def test_step13_actual_delivery_sets_mod_boundary_and_preserves_observed_roles(self):
        summary=self.collect()
        self.assertTrue(summary['subjectStarted']);self.assertEqual(summary['actualSubjectBoundary']['caseId'],self.e.names[12])
        self.assertEqual(summary['transportBoundary']['caseId'],self.e.names[0])
        self.assertEqual(summary['observedStepCount'],2)
        self.assertEqual(summary['checks'][13]['result'],'observed')
        self.assertEqual(summary['checks'][13]['role'],'subject')
        result={'outcome':'incomplete','coverage':{'checks':[{'name':row['name'],'role':row['role'],'status':'unavailable'} for row in self.order['testing']['checks']]},'auxiliaryCoverage':{'checks':[]}}
        result=evidence.complete_projection(result,self.order,{'executionOutcome':'passed'},summary)
        self.assertEqual(result['outcome'],'tested_successfully')
        self.assertEqual(result['coverage']['observed'],2)
        self.assertEqual(result['assertionCoverage']['required'],4)
        self.assertEqual(result['coverage']['checks'][13]['status'],'observed')
        public=self.public_projection(summary)
        self.assertEqual(public['outcome'],'tested_successfully')
        self.assertEqual(public['actualSubjectBoundary']['caseId'],self.e.names[12])
        self.assertEqual(public['coverage']['executed'],17)
        self.assertEqual(public['coverage']['observed'],2)
        interrupted={'outcome':'interrupted_external','interruptionObserved':True,
            'coverage':{'checks':copy.deepcopy(public['coverage']['checks'])},'auxiliaryCoverage':{'checks':[]}}
        self.assertEqual(evidence.complete_projection(interrupted,self.order,{'executionOutcome':'passed'},summary)['outcome'],'interrupted_external')

    def test_first12_fixture_failure_keeps_mod_unstarted_despite_protocol_start(self):
        e=self.e;index=11
        e.actions=e.actions[:12];e.events=e.events[:48];e.steps=e.steps[:12]
        failed=e.actions[index];raw=e.write(Path(failed['rawResult']['path']),{'actual':False});failed['rawResult']=raw
        completion=m.read(failed['completion']['path']);completion['data']['result']={'actual':False};failed['completion']=e.write(Path(failed['completion']['path']),completion)
        e.events[index*4+2]['record'].update(actual=False,outcome='mismatch')
        e.events[index*4+3]['record'].update(outcome='mismatch',semanticResult='failed')
        e.cases[index].update(status='failed',evidence=[raw])
        finish=e.action(13,None)[0];e.actions.append(finish)
        e.report['actions']=e.actions;e.report['cases']=e.cases[:12]+[{'id':name,'status':'not_run','commandIds':[],'evidence':[]} for name in e.names[12:]]
        e.save();summary=self.collect()
        self.assertTrue(summary['transportStarted']);self.assertFalse(summary['subjectStarted'])
        self.assertIsNone(summary['actualSubjectBoundary'])
        self.assertEqual([row['result'] for row in summary['checks'][12:]],['not_run']*5)
        public=self.public_projection(summary)
        self.assertFalse(public['testingStarted'])
        self.assertEqual(public['outcome'],'not_started')

    def test_claimed_pass_with_false_actual_raw_is_rejected_independently(self):
        e=self.e;action=e.actions[12]
        raw=e.write(Path(action['rawResult']['path']),{'actual':False});action['rawResult']=raw;e.cases[12]['evidence']=[raw]
        completion=m.read(action['completion']['path']);completion['data']['result']={'actual':False};action['completion']=e.write(Path(action['completion']['path']),completion)
        e.save()
        with self.assertRaisesRegex(ValueError,'independently evaluated'):self.collect()

    def test_unrestored_owner_and_incomplete_packet_cannot_project(self):
        summary=self.collect();packet={'runDirectory':str(self.e.run),'heldSemantic':summary,'files':summary['pins']}
        self.assertEqual(evidence.projection(self.p,self.order,packet),summary)
        packet['files']=packet['files'][1:]
        with self.assertRaisesRegex(ValueError,'absent'):evidence.projection(self.p,self.order,packet)
        self.e.state['restored']=False;self.e.write(self.e.run/'state.json',self.e.state)
        with self.assertRaisesRegex(ValueError,'restored'):self.collect()

    def test_original_roles_cannot_be_replaced_with_helper_all_subject_inventory(self):
        self.e.events[3]['record']['semanticRole']='subject';self.e.save()
        with self.assertRaisesRegex(ValueError,'role/index'):self.collect()

    def test_actual_native_delivery_order_is_independently_required(self):
        self.e.steps[0],self.e.steps[1]=self.e.steps[1],self.e.steps[0];self.e.save()
        with self.assertRaisesRegex(ValueError,'delivery order'):self.collect()

    def test_unknown_delivered_mutation_is_uncertain_without_finish_or_replay_authority(self):
        e=self.e;e.stop('unavailable',True)
        action=e.report['actions'][0];action['status']='uncertain'
        e.report['cases'][0].update(verdictSource='transport',reason='Lost actual mutation completion')
        e.events=e.events[:2]
        envelope={'schemaVersion':1,'operation':'tool','tool':'platform','timeoutSeconds':5,
            'args':{'operation':'object.perform','request':{'domain':'actor-fixture','action':'create'}}}
        action['envelope']=envelope
        req=m.read(action['request']['path']);req['text']=json.dumps(envelope);action['request']=e.write(Path(action['request']['path']),req)
        ack=m.read(action['ack']['path']);ack['command']['text']=req['text'];action['ack']=e.write(Path(action['ack']['path']),ack)
        native=m.read(action['deliveredEvidence']['path']);native['request']=envelope
        action['deliveredEvidence']=e.write(Path(action['deliveredEvidence']['path']),native)
        e.steps=[native];e.events[1].update(executorLog=native,evidence=action['deliveredEvidence'])
        e.report['subjectStart']['deliveredEvidence']=action['deliveredEvidence']
        self.plan['compiledProgram']['steps'][0].update(tool='platform',args=envelope['args'])
        e.save();summary=self.collect()
        self.assertTrue(summary['uncertain']);self.assertFalse(summary['completed']);self.assertFalse(summary['planCompleted'])
        self.assertFalse(summary['subjectStarted']);self.assertEqual(summary['executedStepCount'],1)
        self.assertEqual(summary['checks'][0]['attempts'],1)
        self.assertEqual(len(e.report['actions']),1)


if __name__=='__main__':unittest.main()

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from contextlib import nullcontext
import unittest
from unittest.mock import Mock, patch
import polygon as m
import order_platform as b
import test_subject_contract as fixture


class OperatorBindingTests(unittest.TestCase):
    qualify=fixture.SeparationTests.qualify
    submit=fixture.SeparationTests.submit
    claimed=fixture.SeparationTests.claimed

    def setUp(self):
        fixture.SeparationTests.setUp(self)
        self.owner=self.root/'owner.txt';self.owner.write_text('Conduct the exact SE test')
        self.auth={'threadId':'owner','messageId':'human','quote':'Conduct the exact SE test',
                   'verifiedBy':'offline independent fixture','path':str(self.owner),'sha256':m.digest(self.owner)}
        package=self.executor/'skyrim_autotest'
        (package/'__init__.py').write_text('')
        (package/'config.py').write_text('import json\ndef load(p):\n x=json.loads(open(p).read());x["selected"]="SE";return x\n')
        (package/'scenarios.py').write_text('def validate(s):\n assert s["steps"] and s["cell"]=="QASmoke"\n')
        self.orderdata=self.submit()
        self.configdata={**m.read(self.config),'selected':'SE'}
        self.packetfile=self.root/'tool-packet.json';m.write(self.packetfile,{'fixture':'tool-only proof'})
        self.packetpin={'path':str(self.packetfile),'sha256':m.digest(self.packetfile)}
        q=m.read(self.qualification);q['configurationSha256']=m.subject_contract.identity(self.configdata)
        q['pins']=[{'path':str(p),'sha256':m.digest(p)} for p in [self.provider,self.executor/'run.py',*sorted(package.glob('*.py'))]]
        q['evidence'].append(self.packetpin);m.write(self.qualification,q)
        manifest=m.read(self.manifest);manifest['qualification']['sha256']=m.digest(self.qualification);m.write(self.manifest,manifest)
        self.qid='composition';self.hold='qualification-'+self.qid
        self.qplan={'id':self.qid,'executor':str(self.executor),'configuration':self.configdata,'ownerAuthorization':self.auth}
        with self.p.connect() as con:
            con.execute("INSERT INTO qualifications(id,request,status,packet) VALUES(?,?,'recorded',?)",(self.qid,json.dumps(self.qplan),json.dumps(self.packetpin)))
        self.p.hold_pipeline(self.hold,'Exact reviewed successful fixture completion')
        self.request={'schemaVersion':1,'kind':'operator-order-platform','orderId':self.orderdata['id'],
                      'subjectOrderSha256':m.subject_contract.identity(self.orderdata),'executor':str(self.executor),
                      'platformManifest':{'path':str(self.manifest),'sha256':m.digest(self.manifest)},
                      'qualificationId':self.qid,'holdId':self.hold,'verifiedBy':'offline fixture',
                      'reason':'Exact target, no live game','ownerAuthorization':self.auth}
        self.requestfile=self.root/'selection.json';m.write(self.requestfile,self.request)
        # Deliberately unsuitable global VR values remain byte-identical.
        m.write(self.p.local/'config.json',{'executor':'missing-global-vr','platformManifest':'missing-global-vr-manifest'})
        self.hostbytes=(self.p.local/'config.json').read_bytes()

    def bind(self):return b.register(self.p,self.requestfile)

    def test_frozen_selection_uses_real_selected_subprocess_not_parent_cache(self):
        self.bind();self.assertEqual((self.p.local/'config.json').read_bytes(),self.hostbytes)
        with self.p.connect() as con:con.execute("UPDATE jobs SET status='running' WHERE id=?",(self.orderdata['id'],))
        plan=self.p.prepare_platform(self.orderdata)
        self.assertEqual(plan['configuration']['selected'],'SE')
        self.assertEqual(plan['executor'],str(self.executor));self.assertIn('operatorSelection',plan)
        self.assertTrue(any(Path(x['path']).name=='order_platform.py' for x in plan['pins']))
        m.write(self.p.local/'config.json',{'executor':'another-global-vr','platformManifest':'another-vr'})
        self.assertEqual(self.p.verify_platform(self.orderdata),plan)
        with self.assertRaises(ValueError):b.find(self.p,self.orderdata,'new-retry')

    def test_binding_immutable_idempotent_and_cannot_rebind_prepared_order(self):
        self.bind();self.assertTrue(self.bind()['duplicate'])
        request=copy.deepcopy(self.request);request['reason']='changed';m.write(self.requestfile,request)
        with self.assertRaises(ValueError):self.bind()

    def test_wrong_owner_hold_order_or_unqualified_data_is_refused(self):
        for field,value in [('subjectOrderSha256','f'*64),('holdId','other')]:
            r=copy.deepcopy(self.request);r[field]=value;m.write(self.requestfile,r)
            with self.assertRaises(ValueError):self.bind()
        r=copy.deepcopy(self.request);r['ownerAuthorization']['messageId']='other-human';m.write(self.requestfile,r)
        with self.assertRaises(ValueError):self.bind()
        m.write(self.requestfile,self.request);self.p.hold_pipeline('other','foreign barrier')
        with self.assertRaises(ValueError):self.bind()

    def test_drift_and_unsupported_sharing_rejected(self):
        self.bind();m.write(self.requestfile,{**self.request,'reason':'drift'})
        with self.assertRaises(ValueError):b.find(self.p,self.orderdata)

    def test_normal_claim_cannot_dispatch_bound_order_after_hold_removal(self):
        self.bind()
        with self.p.connect() as con:
            con.execute('DELETE FROM pipeline_holds')
            con.execute('INSERT INTO releases VALUES(?,?)',('release','{}'))
            con.execute('INSERT INTO released_orders VALUES(?,?)',(self.orderdata['id'],'release'))
        self.assertIsNone(self.p.claim())
        self.assertEqual(self.p.get(self.orderdata['id'])['status'],'queued')

    def admission_fixture(self):
        self.bind();self.run=self.root/'native';archive=self.run/'test-profile';archive.mkdir(parents=True)
        (archive/'modlist.txt').write_text('fixture')
        self.worker={'pid':100,'birth':101,'path':'offline-worker'}
        state={'runner':self.worker,'order':{'id':'qualification-'+self.qid},'done':True,'restored':True,
               'testProfile':str(self.root/'removed-profile'),'profileArchive':str(archive),'owned':[]}
        m.write(self.run/'state.json',state)
        folder=self.p.local/'qualifications'/self.qid;folder.mkdir(parents=True)
        m.write(folder/'worker.json',{'identity':self.worker});m.write(folder/'child-exit.json',{'returncode':0})
        self.packet={'runDirectory':str(self.run),'restored':True,'actualGameStarts':1,'collectionFinished':True,
                     'profileArchivePins':[{'path':str(archive/'modlist.txt'),'sha256':m.digest(archive/'modlist.txt')}]}
        m.write(self.packetfile,self.packet);self.packetpin={'path':str(self.packetfile),'sha256':m.digest(self.packetfile)}
        with self.p.connect() as con:
            con.execute('UPDATE qualifications SET packet=? WHERE id=?',(json.dumps(self.packetpin),self.qid))
            con.execute('INSERT INTO releases VALUES(?,?)',('release',json.dumps({'ownerAuthorization':self.auth})))
            con.execute('INSERT INTO released_orders VALUES(?,?)',(self.orderdata['id'],'release'))
        self.review={'schemaVersion':1,'kind':'operator-bound-subject-admission','orderId':self.orderdata['id'],
                     'binding':{'path':str(self.requestfile),'sha256':m.digest(self.requestfile)},'packet':self.packetpin,
                     'ownerAuthorization':self.auth,'successfulQualificationReviewed':True,'restorationReviewed':True,
                     'archiveReviewed':True,'exactOnlySubjectReviewed':True,'verifiedBy':'offline','reason':'Exact transfer, no game'}
        self.reviewfile=self.root/'admission.json';m.write(self.reviewfile,self.review)
        self.native=SimpleNamespace(SessionMutex=nullcontext,processes=lambda:[{'pid':999,'name':'explorer.exe'}],alive=lambda x:False,identity=lambda x:None)
        changes=[patch.object(self.p,'qualification_collect',return_value=self.packet),patch.object(self.p,'qualification_verify',return_value=self.qplan),
                 patch.object(self.p,'qualification_successful_result',return_value=True),patch.object(self.p,'native_game_starts',return_value=1),
                 patch.object(self.p,'check_launch_authorization'),patch.object(self.p,'execute_claimed',return_value={'fixture':'admitted, no native launch'}),
                 patch.object(b,'activate',return_value=SimpleNamespace(native=self.native))]
        for item in changes:item.start();self.addCleanup(item.stop)

    def test_atomic_exact_subject_transfer_no_old_global_dispatch_or_rerun(self):
        self.admission_fixture();out=b.execute(self.p,self.reviewfile)
        self.assertEqual(out,{'fixture':'admitted, no native launch'})
        self.assertEqual(self.p.get(self.orderdata['id'])['status'],'running')
        self.assertEqual(self.p.pipeline_status()['holds'],[])
        self.assertEqual(self.p.qualification_show(self.qid)['status'],'recorded')
        self.assertEqual((self.p.local/'config.json').read_bytes(),self.hostbytes)
        self.assertFalse(b.execute(self.p,self.reviewfile)['rerun'])
        self.p.execute_claimed.assert_called_once()

    def test_admission_refuses_other_released_work_or_live_game(self):
        self.admission_fixture();self.native.processes=lambda:[{'pid':999,'name':'SkyrimSE.exe'}]
        with self.assertRaises(ValueError):b.execute(self.p,self.reviewfile)
        self.assertEqual(self.p.get(self.orderdata['id'])['status'],'queued')
        self.assertEqual(len(self.p.pipeline_status()['holds']),1)
        self.native.processes=lambda:[{'pid':999,'name':'explorer.exe'}]
        with self.p.connect() as con:
            con.execute('INSERT INTO jobs(id,mode,subject,origin,status,submitted,request) VALUES(?,?,?,?,?,?,?)',('other','automatic','other','other','queued',0,'{}'))
            con.execute('INSERT INTO released_orders VALUES(?,?)',('other','release'))
        with self.assertRaises(ValueError):b.execute(self.p,self.reviewfile)
        self.p.execute_claimed.assert_not_called()

    def test_admission_refuses_bad_exit_identity_archive_owner_or_packet(self):
        self.admission_fixture();folder=self.p.local/'qualifications'/self.qid
        m.write(folder/'child-exit.json',{'returncode':False})
        with self.assertRaises(ValueError):b.execute(self.p,self.reviewfile)
        m.write(folder/'child-exit.json',{'returncode':0})
        (self.run/'test-profile'/'extra.txt').write_text('not retained')
        with self.assertRaises(ValueError):b.execute(self.p,self.reviewfile)
        self.p.execute_claimed.assert_not_called()

    def test_admission_retains_barrier_for_unfinished_native_runtime(self):
        self.admission_fixture();runtime=self.root/'runtime'
        self.qplan['configuration']={'runtime':str(runtime)}
        m.write(runtime/'runs'/'old'/'state.json',{'done':False})
        with self.assertRaisesRegex(ValueError,'Unfinished native'):b.execute(self.p,self.reviewfile)
        self.assertEqual(self.p.get(self.orderdata['id'])['status'],'queued')
        self.assertEqual(len(self.p.pipeline_status()['holds']),1)
        self.p.execute_claimed.assert_not_called()

    def test_activate_refuses_cached_foreign_package(self):
        # setUp deliberately supplied a parent module from another location.
        with self.assertRaisesRegex(ValueError,'Mixed cached'):b.activate(self.executor)


if __name__=='__main__':unittest.main()

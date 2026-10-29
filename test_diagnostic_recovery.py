"""Offline composed recovery; all native observations and installed files are fixtures."""
import copy
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
import unittest
from unittest.mock import patch

import diagnostic_admission as d
import diagnostic_recovery as r
import polygon as m
import test_diagnostic_admission as fixture


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture.DiagnosticTests(); self.base.setUp(); self.addCleanup(self.base.doCleanups)
        self.root, self.p = self.base.root, self.base.p
        for item,name in zip(self.base.installation,('claw-build.json','README.md','README.ru.md')):
            old=Path(item['target']);new=old.with_name(name);old.rename(new);item['target']=str(new)
        intent_path=Path(self.base.request['installationPlan']['path']);intent=m.read(intent_path)
        for item,payload in zip(self.base.installation,intent['archiveInspection']['payloadFiles']):payload['destination']=Path(item['target']).name
        m.write(intent_path,intent);self.base.request['installationPlan']=d.file_pin(intent_path)
        d.APPROVED_INSTALLATION_PLAN_SHA256=m.digest(intent_path)
        case_path=Path(self.base.request['caseReview']['path']);case=m.read(case_path)
        case['authoritativeStagingAnchors']['installation-plan.json']=d.file_pin(intent_path);m.write(case_path,case)
        self.base.request['caseReview']=d.file_pin(case_path);d.APPROVED_CASE_REVIEW_SHA256=m.digest(case_path)
        self.original_providers=[];old_mod=self.root/'original-mod';old_mod.mkdir()
        for i,item in enumerate(self.base.installation):
            if i<3:self.original_providers.append(None);continue
            path=old_mod/Path(item['target']).name;path.write_bytes(('old provider '+str(i)).encode())
            self.original_providers.append(d.file_pin(path))
        original_template=self.base.order_template
        def template():
            order=original_template();order['inputs'].extend([{**x,'role':'dependency'} for x in self.original_providers if x]);return order
        self.base.order_template=template
        draft_path=Path(self.base.request['prospectiveSubject']['path']);m.write(draft_path,template())
        self.base.request['prospectiveSubject']=d.file_pin(draft_path)
        d.APPROVED_SUBJECT_DRAFT_SHA256=m.digest(draft_path);d.APPROVED_SUBJECT_SPECIFICATION_SHA256=m.subject_contract.subject_identity(template())
        for item in self.base.installation:
            item['beforeSha256'] = None
            Path(item['target']).unlink()
        (self.root/'installed').rmdir()
        m.write(self.base.prepare_path, self.base.request)
        self.base.prepare(); (self.root/'installed').mkdir(); self.base.install_submit()
        with patch.object(d, 'freeze', return_value={}):
            self.base.freeze()  # Produce only the normal immutable installation receipt.
        self.base.ini.write_text('[Settings]\nselected_profile=Core\n[Geometry]\nMainWindow_geometry=before\n')
        for i in range(7):
            (self.base.profile / ('profile-'+str(i)+'.txt')).write_text('unchanged profile '+str(i))
        self.backups = self.root/'fresh-backups'; self.backups.mkdir()
        preimages = []
        paths = [self.base.ini, *sorted(self.base.profile.glob('*'))]
        self.assertEqual(len(paths), 11)
        for i, path in enumerate(paths):
            raw = b'+original\n' if path.name == 'modlist.txt' else path.read_bytes()
            backup = self.backups/str(i); backup.write_bytes(raw)
            preimages.append({'path': str(path), 'backup': str(backup), 'sha256': m.digest(backup),
                              'currentSha256': m.digest(path), 'currentlyByteIdentical': raw == path.read_bytes()})
        (self.backups/'index.jsonl').write_text(''.join(json.dumps({k: x[k] for k in ('path','backup','sha256')})+'\n' for x in preimages))
        downloads = self.root/'downloads'; downloads.mkdir()
        archive = downloads/'published.7z'; archive.write_bytes((self.root/'published.7z').read_bytes())
        sidecar = downloads/'published.7z.meta'; sidecar.write_bytes(b'original sidecar fixture')
        self.assessment = {'schemaVersion': 1, 'kind': 'read-only-minimal-unstarted-preparation-restoration-assessment',
            'rootMod': str(self.root/'installed'), 'modFiles': [d.file_pin(x) for x in sorted((self.root/'installed').rglob('*')) if x.is_file()],
            'newDownloadFiles': [{**d.file_pin(x), 'beforeAbsentProvenBy': 'Executed fixture absence preflight'} for x in (archive,sidecar)],
            'freshPreimages': preimages, 'noRestorationPerformed': True,
            'diagnosticEvidencePathFacts': [{'path': str(self.root/x), 'exists': False} for x in ('never-runtime','never-freeze','never-execution')]}
        self.assessment_path = self.root/'assessment.json'; m.write(self.assessment_path, self.assessment)
        old = r.ASSESSMENT_SHA256; r.ASSESSMENT_SHA256 = m.digest(self.assessment_path); self.addCleanup(setattr, r, 'ASSESSMENT_SHA256', old)
        helper = self.root/'owned-install-helper.py'; helper.write_text('# fixture executed absence preflight\n')
        old = r.INSTALL_HELPER_SHA256; r.INSTALL_HELPER_SHA256 = m.digest(helper); self.addCleanup(setattr, r, 'INSTALL_HELPER_SHA256', old)
        # Separate old source copies let the test prove new code does not repin or
        # need to execute/retain the old live implementation forever.
        self.legacy_source = self.root/'legacy-source'; self.legacy_source.mkdir()
        with self.p.connect() as con:
            old_row = dict(con.execute("SELECT * FROM diagnostic_admissions WHERE id='diag'").fetchone())
            original_request = json.loads(old_row['request'])
            pins = []
            for value in original_request['dashboardPins']:
                target = self.legacy_source/Path(value['path']).name
                target.write_bytes(Path(value['path']).read_bytes()); pins.append(d.file_pin(target))
            original_request['dashboardPins'] = sorted(pins, key=lambda x:x['path'])
            raw_request=json.dumps(original_request,sort_keys=True)
            con.execute('UPDATE diagnostic_admissions SET request=? WHERE id=?', (raw_request,'diag'))
            con.execute("UPDATE events SET note=? WHERE id='slot' AND status='diagnostic_slot_granted'",(raw_request,))
        known=patch.object(r,'_known_source',return_value={Path(x['path']).name:x['sha256'] for x in pins})
        known.start();self.addCleanup(known.stop)
        self.manager={'pid':77,'birth':778899,'path':str(self.root/'ModOrganizer.exe')}
        runner=r.order_platform.activate(str(self.base.executor));identity=runner.native.identity;processes=runner.native.processes
        observed_identity=patch.object(runner.native,'identity',side_effect=lambda pid:self.manager if pid==77 else identity(pid))
        observed_rows=patch.object(runner.native,'processes',side_effect=lambda:[*processes(),{'name':'ModOrganizer.exe','pid':77}])
        observed_identity.start();observed_rows.start();self.addCleanup(observed_identity.stop);self.addCleanup(observed_rows.stop)
        info = r.inspect(self.p,'diag')
        started = self.root/'installation-started.json'; ready = self.root/'native-ui-ready.json'
        m.write(started, {'slotId':'slot','grantSha256':info['slotGrantSha256'],'gameStarted':False,'nativeMutexHeld':True})
        m.write(ready, {'slotId':'slot','archive':str(archive),'sha256':m.digest(archive),'gameStarted':False,'nativeMutexHeld':True})
        self.review = {'schemaVersion':1,'kind':'diagnostic-preexecution-recovery-reserve','id':'recovery','diagnosticId':'diag',
            'preparedRequestSha256':info['preparedRequestSha256'],'subjectOrderSha256':info['subjectOrderSha256'],
            'slotGrantSha256':info['slotGrantSha256'],'assessment':d.file_pin(self.assessment_path),
            'installationReceipt':d.file_pin(self.root/'receipt.json'),'installHelper':d.file_pin(helper),
            'installationStarted':d.file_pin(started),'nativeUiReady':d.file_pin(ready),'ownerAuthorization':self.base.auth,
            'noLaunchAuthority':True,'verifiedBy':'offline reviewer','reason':'Exact owned cleanup only'}
        self.path = self.root/'recovery-review.json'; m.write(self.path,self.review)
        self.original_job = self.p.get('subject')
        with self.p.connect() as con:
            self.original_events = r._events(con,'subject')
            self.original_cycle = dict(con.execute("SELECT * FROM cycles WHERE id='cycle'").fetchone())

    def reserve(self):
        return r.reserve(self.p,self.path)

    def restore_fixture(self, gui=False):
        archive_root = self.p.local/'diagnostic-recoveries'/'recovery'/'archive'; archive_root.mkdir(parents=True)
        files = []
        for i, item in enumerate([*self.assessment['modFiles'],*self.assessment['newDownloadFiles']]):
            archived = archive_root/str(i); shutil.copyfile(item['path'],archived)
            files.append({'original':d._short_pin(item),'archived':d.file_pin(archived)})
        manifest = archive_root.parent/'manifest.json'; m.write(manifest,{'schemaVersion':1,'kind':'diagnostic-preexecution-recovery-archive','recoveryId':'recovery','files':files})
        mod_root = Path(self.assessment['rootMod']).resolve()
        self.assertTrue(mod_root.is_relative_to(self.root.resolve()))
        shutil.rmtree(mod_root)
        for item in self.assessment['newDownloadFiles']:
            target = Path(item['path']).resolve(); self.assertTrue(target.is_relative_to(self.root.resolve())); target.unlink()
        modlist = next(x for x in self.assessment['freshPreimages'] if Path(x['path']).name=='modlist.txt')
        shutil.copyfile(modlist['backup'],modlist['path'])
        if gui:
            self.base.ini.write_text(self.base.ini.read_text().replace('geometry=before','geometry=after'))
        after = archive_root.parent/'managed-ini-after.txt'; after.write_bytes(self.base.ini.read_bytes())
        readback=archive_root.parent/'native-readback.json'
        virtual=[str(Path(x['target']).relative_to(Path(self.assessment['rootMod']))) for x in self.base.installation]
        m.write(readback,{'managerIdentity':self.manager,'profile':'Core','busyKnown':True,'busy':None,'managerRefreshed':True,
            'newModAbsent':True,'downloadsAbsent':[True,True],
            'vfsWinners':[{'virtualPath':name,'provider':provider} for name,provider in zip(virtual,self.original_providers)]})
        actor=archive_root.parent/'approved-native-restorer.py';actor.write_text('# fixture reviewed native UI actor\n')
        receipt=archive_root.parent/'restoration-receipt.json'
        m.write(receipt,{'schemaVersion':1,'kind':'diagnostic-preexecution-native-restoration-receipt','recoveryId':'recovery',
            'reservedReviewPin':d.file_pin(self.path),'sourceChat':'mod','sourceThreadId':'origin','instance':str(self.root),'profile':'Core',
            'managerIdentity':self.manager,'noGameStarted':True,'archive':d.file_pin(manifest),
            'rollbackTargets':[x['path'] for x in [*self.assessment['modFiles'],*self.assessment['newDownloadFiles']]]+[modlist['path']],
            'nativeUiActor':{'helper':d.file_pin(actor),'evidence':[d.file_pin(self.base.evidence)]},'readback':d.file_pin(readback),
            'verifiedBy':'offline fixture reviewer','reason':'Pinned native actor/readback fixture'})
        self.completion = {'schemaVersion':1,'kind':'diagnostic-preexecution-recovery-complete','id':'recovery',
                         'archive':d.file_pin(manifest),'managedIniAfter':d.file_pin(after),'restorationReceipt':d.file_pin(receipt),
                         'verifiedBy':'offline','reason':'Exact fixture rollback archived'}
        self.completion_path = self.root/'completion.json'; m.write(self.completion_path,self.completion)

    def assert_subject_untouched(self):
        self.assertEqual(self.p.get('subject'),self.original_job)
        with self.p.connect() as con:
            self.assertEqual(r._events(con,'subject'),self.original_events)
            self.assertEqual(dict(con.execute("SELECT * FROM cycles WHERE id='cycle'").fetchone()),self.original_cycle)
            self.assertIsNone(con.execute("SELECT actual_starts FROM diagnostic_admissions WHERE id='diag'").fetchone()[0])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM attempts WHERE id='subject'").fetchone()[0],0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM notification_results').fetchone()[0],0)
        self.assertEqual(self.p.pending(),[])

    def test_two_phase_preserves_queued_subject_blocks_old_actions_and_historical_provider_changes(self):
        self.assertEqual(self.reserve()['status'],'restoring'); self.assert_subject_untouched()
        spec = importlib.util.spec_from_file_location('isolated_legacy_diagnostic',self.legacy_source/'diagnostic_admission.py')
        legacy = importlib.util.module_from_spec(spec); spec.loader.exec_module(legacy)
        with self.assertRaisesRegex(ValueError,'unconsumed preparation'): legacy.freeze(self.p,self.base.freeze_path)
        execute = self.root/'execute.json'; m.write(execute,{'schemaVersion':1,'kind':'one-shot-diagnostic-execution','id':'diag',
            'platformPlanSha256':'0'*64,'verifiedBy':'offline','reason':'Must refuse'})
        with patch.object(self.p,'execute_claimed') as launch:
            with self.assertRaisesRegex(ValueError,'frozen diagnostic'): legacy.execute(self.p,execute)
            launch.assert_not_called()
        self.restore_fixture(gui=True)
        self.assertEqual(r.complete(self.p,self.completion_path)['actualStartsThisPreparation'],0)
        self.assert_subject_untouched(); self.assertTrue(r.settled(self.p,'recovery'))
        self.assertEqual(self.p.slots()[0]['status'],'released'); self.assertIsNone(self.p.claim())
        self.base.provider.write_bytes(b'legitimate later provider build')
        (self.legacy_source/'diagnostic_admission.py').write_text('# legitimate later source checkout change')
        self.base.ini.write_text('[Later]\nnewConfiguration=true\n')
        self.assertTrue(r.settled(self.p,'recovery'))
        self.assertTrue(r.complete(self.p,self.completion_path)['duplicate'])
        self.assertFalse(self.reserve()['newCleanupGranted'])
        with self.p.connect() as con:
            con.execute("UPDATE jobs SET status='running' WHERE id='subject'")
            self.p.event(con,'subject','later-generation-progress','Synthetic later work; no new permission from historical recovery')
        self.assertTrue(r.settled(self.p,'recovery'))
        self.assertTrue(r.complete(self.p,self.completion_path)['duplicate'])

    def test_frozen_attempt_or_foreign_hold_cannot_enter_recovery(self):
        for mutation in ('frozen','attempt','foreign'):
            with self.p.connect() as con:
                if mutation=='frozen':con.execute("UPDATE diagnostic_admissions SET status='frozen'")
                if mutation=='attempt':con.execute("INSERT INTO attempts VALUES('subject',1)")
            if mutation=='foreign':self.p.hold_pipeline('foreign','Other owner')
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.reserve()
            with self.p.connect() as con:
                con.execute("UPDATE diagnostic_admissions SET status='preparing'")
                con.execute("DELETE FROM attempts WHERE id='subject'");con.execute("DELETE FROM pipeline_holds WHERE id='foreign'")
        self.assert_subject_untouched()

    def test_recovery_audit_cannot_use_subject_identity(self):
        self.review['id']='subject';m.write(self.path,self.review)
        with self.assertRaisesRegex(ValueError,'audit identity'):self.reserve()
        self.assert_subject_untouched()

    def test_changed_owned_file_or_extra_file_prevents_reservation(self):
        target=self.root/'installed'/'foreign.bin';target.write_bytes(b'foreign')
        with self.assertRaisesRegex(ValueError,'Changed/extra'):self.reserve()
        self.assert_subject_untouched()

    def test_partial_restore_bad_archive_and_non_gui_changes_retain_lease(self):
        self.reserve()
        with self.assertRaises(ValueError):r.complete(self.p,self.path)
        self.restore_fixture()
        manifest=m.read(self.completion['archive']['path']);archive_path=Path(manifest['files'][0]['archived']['path'])
        old=archive_path.read_bytes();archive_path.write_bytes(b'bad archive')
        with self.assertRaises(ValueError):r.complete(self.p,self.completion_path)
        archive_path.write_bytes(old)
        self.base.ini.write_text('[Settings]\nselected_profile=Foreign\n')
        with self.assertRaises(ValueError):r.complete(self.p,self.completion_path)
        self.assertEqual(r.show(self.p,'recovery')['status'],'restoring');self.assert_subject_untouched()
        self.assertEqual(self.p.slots()[0]['status'],'reserved')

    def test_terminal_label_without_complete_audit_is_not_historical_recovery(self):
        self.reserve()
        with self.p.connect() as con:
            con.execute("UPDATE diagnostic_admissions SET status='recovered-unstarted'")
            con.execute("UPDATE diagnostic_recoveries SET status='completed',completion='{}'")
        self.assertFalse(r.settled(self.p,'recovery'));self.assert_subject_untouched()

    def test_changed_legacy_source_is_refused_before_observer_activation(self):
        (self.legacy_source/'diagnostic_admission.py').write_text('# changed old producer')
        with patch.object(r.order_platform,'activate') as activate:
            with self.assertRaises(ValueError):self.reserve()
            activate.assert_not_called()
        self.assert_subject_untouched()

    def test_file_ack_hash_and_cycle_audit_identity_are_enforced(self):
        ack=self.root/'ack.json';original=ack.read_bytes();ack.write_text('{}')
        with self.assertRaises(ValueError):self.reserve()
        ack.write_bytes(original);self.review['id']='cycle';m.write(self.path,self.review)
        with self.assertRaisesRegex(ValueError,'audit identity'):self.reserve()
        self.assert_subject_untouched()

    def test_index_swap_during_native_observation_cannot_grant_cleanup(self):
        actual=d._native_closed
        def swapped(*args,**kwargs):
            result=actual(*args,**kwargs);path=self.backups/'index.jsonl';path.write_bytes(path.read_bytes()+b'\n');return result
        with patch.object(d,'_native_closed',side_effect=swapped):
            with self.assertRaises(ValueError):self.reserve()
        self.assertEqual(r.inspect(self.p,'diag')['status'],'preparing');self.assert_subject_untouched()

    def test_nested_installation_evidence_swap_during_native_probe_refuses_reservation(self):
        evidence=self.root/'only-installation-evidence.txt';evidence.write_text('immutable native installation observation')
        receipt_path=Path(self.review['installationReceipt']['path']);receipt=m.read(receipt_path)
        receipt['evidence']=[d.file_pin(evidence)];m.write(receipt_path,receipt)
        self.review['installationReceipt']=d.file_pin(receipt_path);m.write(self.path,self.review)
        actual=d._native_closed
        def swapped(*args,**kwargs):
            result=actual(*args,**kwargs);evidence.write_text('changed after receipt validation');return result
        with patch.object(d,'_native_closed',side_effect=swapped):
            with self.assertRaises(ValueError):self.reserve()
        self.assertEqual(r.inspect(self.p,'diag')['status'],'preparing');self.assert_subject_untouched()

    def test_other_profile_reference_and_extra_empty_directory_refuse_cleanup(self):
        other=self.base.profile.parent/'Other';other.mkdir();(other/'modlist.txt').write_text('-installed\n')
        with self.assertRaisesRegex(ValueError,'Another profile'):self.reserve()
        (other/'modlist.txt').write_text('+original\n');(self.root/'installed'/'unexpected-empty').mkdir()
        with self.assertRaisesRegex(ValueError,'Changed/extra'):self.reserve()
        self.assert_subject_untouched()

    def test_reparse_directory_is_rejected_without_removing_its_target(self):
        target=self.root/'outside-owned-mod';target.mkdir();marker=target/'keep.txt';marker.write_text('preserved')
        link=self.root/'installed'/'unreviewed-link'
        try:
            os.symlink(target,link,target_is_directory=True)
        except OSError:
            if os.name!='nt':raise
            quote=lambda value:"'"+str(value).replace("'","''")+"'"
            result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',
                'New-Item -ItemType Junction -Path '+quote(link)+' -Target '+quote(target)+' | Out-Null'],capture_output=True)
            if result.returncode:self.skipTest('OS does not permit symlink or junction fixture')
        try:
            with self.assertRaises(ValueError):self.reserve()
            self.assertEqual(marker.read_text(),'preserved');self.assert_subject_untouched()
        finally:
            self.assertTrue(link.absolute().is_relative_to(self.root.resolve()))
            if os.name=='nt':os.rmdir(link)
            else:link.unlink()

    def test_live_ini_snapshot_or_stale_manager_cannot_complete(self):
        self.reserve();self.restore_fixture();original=copy.deepcopy(self.completion)
        self.completion['managedIniAfter']=d.file_pin(self.base.ini);m.write(self.completion_path,self.completion)
        with self.assertRaisesRegex(ValueError,'immutable scoped'):r.complete(self.p,self.completion_path)
        self.completion=original;m.write(self.completion_path,self.completion)
        self.manager['birth']+=1
        with self.assertRaisesRegex(ValueError,'identity is stale'):r.complete(self.p,self.completion_path)
        self.assertEqual(r.show(self.p,'recovery')['status'],'restoring');self.assert_subject_untouched()

    def test_receipt_swap_after_restoration_read_cannot_release_lease(self):
        self.reserve();self.restore_fixture();actual=r._current;calls=0
        def swapped(*args,**kwargs):
            nonlocal calls
            result=actual(*args,**kwargs)
            if args[2]:
                calls+=1
                if calls==3:
                    receipt=m.read(self.completion['restorationReceipt']['path']);path=Path(receipt['readback']['path'])
                    path.write_bytes(path.read_bytes()+b' ')
            return result
        with patch.object(r,'_current',side_effect=swapped):
            with self.assertRaises(ValueError):r.complete(self.p,self.completion_path)
        self.assertEqual(r.show(self.p,'recovery')['status'],'restoring');self.assertEqual(self.p.slots()[0]['status'],'reserved')
        self.assert_subject_untouched()

    def test_metadata_other_provider_is_observation_but_game_provider_cannot_be_replaced(self):
        self.reserve();self.restore_fixture()
        receipt_path=Path(self.completion['restorationReceipt']['path']);receipt=m.read(receipt_path)
        readback_path=Path(receipt['readback']['path']);readback=m.read(readback_path)
        extra=self.root/'unrelated-mod';extra.mkdir();metadata=extra/'README.md';metadata.write_text('other metadata')
        readback['vfsWinners'][1]['provider']=d.file_pin(metadata)
        wrong=extra/'f3.bin';wrong.write_bytes(Path(self.original_providers[3]['path']).read_bytes())
        readback['vfsWinners'][3]['provider']=d.file_pin(wrong)
        def save():
            m.write(readback_path,readback);receipt['readback']=d.file_pin(readback_path);m.write(receipt_path,receipt)
            self.completion['restorationReceipt']=d.file_pin(receipt_path);m.write(self.completion_path,self.completion)
        save()
        with self.assertRaisesRegex(ValueError,'Seven game'):r.complete(self.p,self.completion_path)
        readback['vfsWinners'][3]['provider']=self.original_providers[3];save()
        self.assertEqual(r.complete(self.p,self.completion_path)['status'],'completed');self.assert_subject_untouched()

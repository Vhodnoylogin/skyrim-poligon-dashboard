"""Guard exercises use only the existing fake native/installation fixture."""
from contextlib import redirect_stdout
import copy
import io
import json
import sqlite3
from pathlib import Path
import unittest
from unittest.mock import patch

import diagnostic_admission as d
import diagnostic_recovery as r
import polygon as m
import test_diagnostic_recovery as fixture


class RestoringGuardTests(unittest.TestCase):
    def setUp(self):
        self.base=fixture.RecoveryTests();self.base.setUp();self.addCleanup(self.base.doCleanups)
        self.root,self.p=self.base.root,self.base.p
        self.base.reserve()
        self.query={'schemaVersion':1,'kind':'diagnostic-preexecution-restoring-guard','id':'recovery',
                    'reservedReviewPin':d.file_pin(self.base.path),'stage':'pre-archive'}
        self.path=self.root/'guard-query.json';m.write(self.path,self.query)

    def call(self):
        return r.guard(self.root,self.path)

    def archive(self):
        root=self.p.local/'diagnostic-recoveries'/'recovery'/'archive';root.mkdir(parents=True)
        files=[]
        for i,item in enumerate([*self.base.assessment['modFiles'],*self.base.assessment['newDownloadFiles']]):
            path=root/str(i);path.write_bytes(Path(item['path']).read_bytes())
            files.append({'original':d._short_pin(item),'archived':d.file_pin(path)})
        manifest=root.parent/'manifest.json';m.write(manifest,{'schemaVersion':1,'kind':'diagnostic-preexecution-recovery-archive','recoveryId':'recovery','files':files})
        self.query.update(stage='partial',archive=d.file_pin(manifest));m.write(self.path,self.query)
        return files

    def test_cli_uses_readonly_existing_db_no_constructor_or_mutex_and_no_mutations(self):
        before=self.p.db.read_bytes();runner=r.order_platform.activate(str(self.base.base.executor))
        with patch.object(m.Polygon,'__init__',side_effect=AssertionError('RW constructor forbidden')),\
             patch.object(runner.native,'SessionMutex',side_effect=AssertionError('Caller already holds native mutex')),\
             redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(m.main(['--root',str(self.root),'diagnostic-recovery-guard',str(self.path)]),0)
        result=json.loads(stdout.getvalue());self.assertTrue(result['copyOnly']);self.assertFalse(result['archiveVerified'])
        self.assertFalse(result['newCleanupGranted']);self.assertFalse(result['launchGranted'])
        self.assertFalse(result['mutexOwnershipProvedByGuard']);self.assertEqual(len(result['allowedPostimages']),13)
        self.assertEqual(self.p.db.read_bytes(),before);self.base.assert_subject_untouched()
        missing=self.root/'missing-runtime'
        with self.assertRaises(ValueError):r.guard(missing,self.path)
        self.assertFalse(missing.exists())
        unknown=self.root/'unknown-schema';database=unknown/'local/skyrim-polygon/queue.sqlite3'
        database.parent.mkdir(parents=True);sqlite3.connect(database).close();empty=database.read_bytes()
        with self.assertRaises(ValueError):r.guard(unknown,self.path)
        self.assertEqual(database.read_bytes(),empty)

    def test_partial_requires_full_archive_before_any_missing_source(self):
        owned=Path(self.base.assessment['modFiles'][0]['path']);original=owned.read_bytes();owned.unlink()
        with self.assertRaises((ValueError,OSError)):self.call()
        self.query['stage']='partial';m.write(self.path,self.query)
        with self.assertRaisesRegex(ValueError,'two-stage'):self.call()
        owned.write_bytes(original);files=self.archive();Path(files[0]['archived']['path']).unlink()
        owned.unlink()
        with self.assertRaises((ValueError,OSError)):self.call()
        self.base.assert_subject_untouched()

    def test_known_partial_and_exact_toggle_then_preimage_are_readonly_scopes(self):
        self.archive();owned=Path(self.base.assessment['modFiles'][0]['path']);owned.unlink()
        modlist=self.base.base.profile/'modlist.txt';raw=modlist.read_bytes();modlist.write_bytes(raw.replace(b'+installed',b'-installed',1))
        before=self.p.db.read_bytes();result=self.call()
        self.assertEqual(result['stageProof']['modlistState'],'disabled-new-mod')
        self.assertEqual(len(result['stageProof']['absent']),1);self.assertTrue(result['archiveVerified']);self.assertFalse(result['copyOnly'])
        self.assertEqual(self.p.db.read_bytes(),before)
        fresh=next(x for x in self.base.assessment['freshPreimages'] if Path(x['path'])==modlist)
        modlist.write_bytes(Path(fresh['backup']).read_bytes());self.assertEqual(self.call()['stageProof']['modlistState'],'preimage')
        modlist.write_bytes(b'+different-other-mod\n')
        with self.assertRaisesRegex(ValueError,'Only exact'):self.call()

    def test_foreign_hold_wrong_source_ack_record_and_completed_state_refuse(self):
        self.p.hold_pipeline('foreign','Different owner')
        with self.assertRaises(ValueError):self.call()
        with self.p.connect() as con:con.execute("DELETE FROM pipeline_holds WHERE id='foreign'")
        old=self.query['reservedReviewPin'];self.query['reservedReviewPin']={'path':str(self.path),'sha256':'0'*64};m.write(self.path,self.query)
        with self.assertRaisesRegex(ValueError,'reserved review'):self.call()
        self.query['reservedReviewPin']=old;m.write(self.path,self.query)
        ack=self.root/'ack.json';raw=ack.read_bytes();ack.write_text('{}')
        with self.assertRaises(ValueError):self.call()
        ack.write_bytes(raw)
        with self.p.connect() as con:
            record=json.loads(con.execute("SELECT request FROM diagnostic_recoveries WHERE id='recovery'").fetchone()[0])
            changed=copy.deepcopy(record);changed['implementationPins']=[]
            con.execute("UPDATE diagnostic_recoveries SET request=? WHERE id='recovery'",(json.dumps(changed,sort_keys=True),))
        with patch.object(r.order_platform,'activate') as activate:
            with self.assertRaisesRegex(ValueError,'implementation'):self.call()
            activate.assert_not_called()
        with self.p.connect() as con:
            con.execute("UPDATE diagnostic_recoveries SET request=?,status='completed' WHERE id='recovery'",(json.dumps(record,sort_keys=True),))
        with self.assertRaisesRegex(ValueError,'Current restoring'):self.call()

    def test_changed_owned_partial_or_other_profile_refuses(self):
        self.archive();owned=Path(self.base.assessment['modFiles'][0]['path']);raw=owned.read_bytes();owned.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.call()
        owned.write_bytes(raw);other=self.base.base.profile.parent/'Other';other.mkdir();(other/'modlist.txt').write_text('-installed\n')
        with self.assertRaises(ValueError):self.call()

    def test_native_probe_late_proof_change_refuses_without_writing(self):
        actual=d._native_closed;index=self.base.backups/'index.jsonl';before=self.p.db.read_bytes()
        def swapped(*args,**kwargs):
            value=actual(*args,**kwargs);index.write_bytes(index.read_bytes()+b'\n');return value
        with patch.object(d,'_native_closed',side_effect=swapped):
            with self.assertRaises(ValueError):self.call()
        self.assertEqual(self.p.db.read_bytes(),before);self.base.assert_subject_untouched()

    def test_owned_or_profile_state_changing_during_final_pins_refuses(self):
        self.archive();owned=Path(self.base.assessment['modFiles'][0]['path']);owned.unlink()
        modlist=self.base.base.profile/'modlist.txt';before=self.p.db.read_bytes();actual=d.pin
        for mutation in ('reappeared','extra-directory','foreign-profile'):
            extra=Path(self.base.assessment['rootMod'])/'unknown-directory'
            other=self.base.base.profile.parent/'LateOther'
            def swapped(value):
                result=actual(value)
                if Path(value['path'])==modlist:
                    if mutation=='reappeared':owned.write_bytes(b'unreviewed new bytes')
                    elif mutation=='extra-directory':extra.mkdir(exist_ok=True)
                    else:other.mkdir(exist_ok=True);(other/'modlist.txt').write_text('-installed\n')
                return result
            with self.subTest(mutation=mutation),patch.object(d,'pin',side_effect=swapped):
                with self.assertRaises(ValueError):self.call()
            if owned.exists():owned.unlink()
            if extra.exists():extra.rmdir()
            if other.exists():(other/'modlist.txt').unlink();other.rmdir()
            self.assertEqual(self.p.db.read_bytes(),before)
        self.base.assert_subject_untouched()

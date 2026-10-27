"""No native run is inferred from a refused, never-dispatched reservation."""
import hashlib
import json
from contextlib import nullcontext
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import polygon as m
import test_qualification as fixture


class PreparedAbandonTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture.QualificationTests(); self.base.setUp(); self.addCleanup(self.base.doCleanups)
        self.base.register(); self.p = self.base.p
        self.review = {'schemaVersion': 1, 'kind': 'qualification-prepared-abandon-review',
            'qualificationId': 'candidate-one', 'verifiedBy': 'offline operator', 'reason': 'Refused before dispatch',
            'noDispatchReviewed': True, 'zeroStartsReviewed': True, 'installationSettled': True,
            'ownerAuthorization': dict(self.base.request['ownerAuthorization']),
            'preparedRequestSha256': hashlib.sha256(self.p.qualification_show('candidate-one')['request'].encode()).hexdigest()}
        self.path = self.base.root / 'abandon-review.json'
        self.rows = [{'name': 'python.exe', 'pid': 1}]
        runner = SimpleNamespace(native=SimpleNamespace(SessionMutex=nullcontext, processes=lambda: self.rows),
            GAME_NAMES={'skyrimse.exe', 'skyrimvr.exe', 'skse64_loader.exe', 'sksevr_loader.exe'})
        self.activate = patch('order_platform.activate', return_value=runner); self.activate.start(); self.addCleanup(self.activate.stop)

    def abandon(self):
        m.write(self.path, self.review)
        return self.p.qualification_abandon_prepared('candidate-one', self.path)

    def test_changed_profile_input_can_retire_only_unstarted_reservation_without_packet(self):
        original = self.p.qualification_show('candidate-one')['request']
        self.base.ini.write_text('MO2 normalized source settings')
        self.p.hold_pipeline('unrelated-hold', 'Preserve this hold')
        result = self.abandon()
        self.assertEqual(result['actualGameStarts'], 0)
        self.assertEqual(result['cumulativeActualGameStartsAfter'], 10)
        row = self.p.qualification_show('candidate-one')
        self.assertEqual(row['status'], 'abandoned'); self.assertIsNone(row['expires']); self.assertIsNone(row['packet'])
        self.assertEqual(row['request'], original)
        with self.p.connect() as con:
            self.assertIsNone(con.execute('SELECT id FROM attempts').fetchone())
            self.assertEqual([x['id'] for x in con.execute('SELECT id FROM pipeline_holds')], ['unrelated-hold'])
        self.assertFalse((self.p.local / 'qualifications/candidate-one').exists())
        with self.assertRaisesRegex(ValueError, 'unstarted prepared'): self.abandon()
        self.base.ini.write_text('selected_profile=Core\n')
        self.base.request['id'] = 'fresh-reservation'
        self.assertEqual(self.base.register()['status'], 'prepared')

    def test_status_expiry_packet_or_any_attempt_refuses(self):
        for field, value in (('status', 'running'), ('expires', 1), ('packet', '{}')):
            with self.subTest(field=field):
                with self.p.connect() as con: con.execute('UPDATE qualifications SET ' + field + '=?', (value,))
                with self.assertRaisesRegex(ValueError, 'unstarted prepared'): self.abandon()
                with self.p.connect() as con: con.execute("UPDATE qualifications SET status='prepared',expires=NULL,packet=NULL")
        with self.p.connect() as con: con.execute("INSERT INTO attempts VALUES('qualification-candidate-one',1)")
        with self.assertRaisesRegex(ValueError, 'unstarted prepared'): self.abandon()
        self.assertEqual(self.p.qualification_show('candidate-one')['status'], 'prepared')

    def test_unknown_cumulative_baseline_stays_unknown(self):
        row = self.p.qualification_show('candidate-one'); plan = json.loads(row['request'])
        plan['cumulativeActualGameStartsBefore'] = None
        request = json.dumps(plan, sort_keys=True)
        with self.p.connect() as con: con.execute('UPDATE qualifications SET request=?', (request,))
        self.review['preparedRequestSha256'] = hashlib.sha256(request.encode()).hexdigest()
        result = self.abandon()
        self.assertIsNone(result['cumulativeActualGameStartsBefore'])
        self.assertIsNone(result['cumulativeActualGameStartsAfter'])
        self.assertEqual(result['actualGameStarts'], 0)

    def test_any_dispatch_or_runtime_artifact_refuses(self):
        for path in (self.p.local / 'qualifications/candidate-one/dispatch-intent.json',
                     self.base.root / 'runtime/runs/native/state.json'):
            with self.subTest(path=path):
                m.write(path, {})
                with self.assertRaisesRegex(ValueError, 'artifacts exist'): self.abandon()
                path.unlink()
                for parent in path.parents:
                    if parent == self.base.root or parent == self.p.local: break
                    try: parent.rmdir()
                    except OSError: break

    def test_foreign_game_unknown_inventory_and_wrong_review_refuse(self):
        for rows in ([], None, [{'name': 'SkyrimSE.exe', 'pid': 22}], [{'name': 'python.exe'}]):
            with self.subTest(rows=rows):
                self.rows = rows
                with self.assertRaisesRegex(ValueError, 'native idle inventory'): self.abandon()
        self.rows = [{'name': 'python.exe', 'pid': 1}]
        self.review['preparedRequestSha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'prepared request'): self.abandon()

    def test_previously_released_queue_is_not_unblocked(self):
        with self.p.connect() as con:
            con.execute("INSERT INTO jobs(id,mode,subject,origin,status,submitted,request) VALUES('old','automatic','old','origin','queued',1,'{}')")
            con.execute("INSERT INTO released_orders VALUES('old','owner-batch')")
        with self.assertRaisesRegex(ValueError, 'released work'): self.abandon()
        self.assertEqual(len(self.p.pipeline_status()['holds']), 1)


if __name__ == '__main__': unittest.main()

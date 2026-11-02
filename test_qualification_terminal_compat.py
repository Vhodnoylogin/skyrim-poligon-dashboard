"""Supported terminal history is recognized without inventing a new result."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import polygon as m
import qualification_terminal as q
import hashlib
import test_qualification as fixture


class TerminalQualificationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.QualificationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.register()
        self.p = self.fixture.p
        self.identity = 'candidate-one'
        self.old_owner = self.fixture.root / 'settlement-owner.txt'
        self.old_owner.write_bytes(self.fixture.owner.read_bytes())
        # Seed the published producer's exact terminal audit in an isolated test
        # database. Recognition adds no abandonment command or live mutation.
        row = self.p.qualification_show(self.identity)
        review = {'schemaVersion': 1, 'kind': 'qualification-prepared-abandon-review',
            'qualificationId': self.identity, 'verifiedBy': 'offline operator',
            'reason': 'Refused before dispatch', 'noDispatchReviewed': True,
            'zeroStartsReviewed': True, 'installationSettled': True,
            'ownerAuthorization': dict(self.fixture.request['ownerAuthorization']),
            'preparedRequestSha256': hashlib.sha256(row['request'].encode()).hexdigest()}
        review['ownerAuthorization']['path'] = str(self.old_owner)
        self.review_path = self.fixture.root / 'abandon-review.json'
        m.write(self.review_path, review)
        event = {'id': self.identity, 'status': 'abandoned', 'actualGameStarts': 0,
            'cumulativeActualGameStartsBefore': 10, 'cumulativeActualGameStartsAfter': 10,
            'review': {'path': str(self.review_path), 'sha256': m.digest(self.review_path)},
            'globalProviderQualified': False, 'launchAuthorityGranted': False, 'reviewed': review}
        with self.p.connect() as con:
            con.execute("UPDATE qualifications SET status='abandoned' WHERE id=?", (self.identity,))
            con.execute('DELETE FROM pipeline_holds WHERE id=?', ('qualification-' + self.identity,))
            self.p.event(con, self.identity, 'qualification_prepared_abandoned', json.dumps(event, sort_keys=True))
        self.old = self.p.qualification_show(self.identity)
        self.event = self.history()[-1]

    def history(self):
        with self.p.connect() as con:
            return [dict(r) for r in con.execute('SELECT * FROM events WHERE id=? ORDER BY seq', (self.identity,))]

    def fresh(self):
        self.fixture.request['id'] = 'fresh-reservation'
        self.fixture.path = self.fixture.root / 'fresh-qualification.json'
        return self.fixture.register()

    def refuses(self):
        original = self.p.db.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Recover existing owner or qualification'):
            self.fresh()
        self.assertEqual(self.p.db.read_bytes(), original)

    def rewrite_event(self, value):
        note = json.dumps(value, sort_keys=True) if isinstance(value, dict) else value
        with self.p.connect() as con:
            con.execute('UPDATE events SET note=? WHERE seq=?', (note, self.event['seq']))

    def test_supported_terminal_allows_fresh_registration_with_old_history_unchanged(self):
        old_history = self.history()
        review_bytes = self.review_path.read_bytes()
        self.assertEqual(self.fresh()['status'], 'prepared')
        self.assertEqual(self.p.qualification_show(self.identity), self.old)
        self.assertEqual(self.history(), old_history)
        self.assertEqual(self.review_path.read_bytes(), review_bytes)
        self.assertIsNone(self.old['packet'])
        self.assertIsNone(self.old['expires'])
        self.assertFalse((self.p.local / 'qualifications' / self.identity).exists())
        with self.assertRaisesRegex(ValueError, 'only once'):
            self.p.qualification_run(self.identity)

    def test_bare_abandoned_label_or_missing_prepared_history_is_not_settled(self):
        for missing in ('qualification_prepared_abandoned', 'qualification_prepared'):
            with self.subTest(missing=missing):
                history = self.history()
                with self.p.connect() as con:
                    con.execute('DELETE FROM events WHERE id=? AND status=?', (self.identity, missing))
                self.refuses()
                with self.p.connect() as con:
                    con.execute('DELETE FROM events WHERE id=?', (self.identity,))
                    for row in history:
                        con.execute('INSERT INTO events VALUES(?,?,?,?,?)', tuple(row.values()))

    def test_terminal_packet_expiry_hold_or_admission_contradictions_block(self):
        mutations = [
            ("UPDATE qualifications SET expires=1 WHERE id='candidate-one'", "UPDATE qualifications SET expires=NULL WHERE id='candidate-one'"),
            ("UPDATE qualifications SET packet='{}' WHERE id='candidate-one'", "UPDATE qualifications SET packet=NULL WHERE id='candidate-one'"),
            ("INSERT INTO pipeline_holds VALUES('qualification-candidate-one','Retain')", "DELETE FROM pipeline_holds"),
            ("INSERT INTO attempts VALUES('qualification-candidate-one',1)", "DELETE FROM attempts"),
            ("INSERT INTO platform_attempts VALUES('qualification-candidate-one','{}','hash')", "DELETE FROM platform_attempts"),
        ]
        for mutation, undo in mutations:
            with self.subTest(mutation=mutation):
                with self.p.connect() as con:
                    con.execute(mutation)
                self.refuses()
                with self.p.connect() as con:
                    con.execute(undo)

    def test_malformed_or_contradictory_terminal_events_are_not_skipped(self):
        original = json.loads(self.event['note'])
        variants = ['{bad-json', dict(original, actualGameStarts=1), dict(original, actualGameStarts=False),
                    dict(original, cumulativeActualGameStartsAfter=None),
                    dict(original, globalProviderQualified=True), dict(original, launchAuthorityGranted=True)]
        for value in variants:
            with self.subTest(value=value):
                self.rewrite_event(value)
                self.refuses()
        self.rewrite_event(original)
        with self.p.connect() as con:
            plan = json.loads(self.old['request'])
            plan['reason'] = 'Changed frozen historical request'
            con.execute('UPDATE qualifications SET request=? WHERE id=?', (json.dumps(plan), self.identity))
        self.refuses()

    def test_changed_historical_review_or_owner_bytes_are_not_current_authority(self):
        original = self.review_path.read_bytes()
        self.review_path.write_bytes(original + b' ')
        self.refuses()
        self.review_path.write_bytes(original)
        self.old_owner.write_text('Changed old settlement authority', encoding='utf-8')
        self.refuses()

    def test_rehashed_false_review_is_still_rejected(self):
        original = json.loads(self.event['note'])
        review = m.read(self.review_path)
        review['zeroStartsReviewed'] = False
        m.write(self.review_path, review)
        value = copy.deepcopy(original)
        value['review']['sha256'] = m.digest(self.review_path)
        value['reviewed'] = review
        self.rewrite_event(value)
        self.refuses()

    def test_later_unrelated_runtime_and_input_reuse_preserve_settlement(self):
        self.fixture.ini.write_text('MO2 later normalized source files')
        (self.fixture.candidate / 'skyrim_autotest/runner.py').write_text('# Later independently reviewed source')
        m.write(self.fixture.root / 'runtime/runs/later/state.json',
                {'order': {'id': 'other-independent-order'}, 'done': True, 'restored': True})
        self.assertEqual(self.fresh()['status'], 'prepared')
        self.assertEqual(self.p.qualification_show(self.identity), self.old)

    def test_own_dispatch_files_native_state_or_later_event_still_block(self):
        paths = [self.p.local / 'qualifications' / self.identity / 'dispatch-intent.json',
                 self.fixture.root / 'runtime/runs/old/state.json']
        for path in paths:
            with self.subTest(path=path):
                m.write(path, {'order': {'id': 'qualification-' + self.identity}, 'done': True})
                self.refuses()
                path.unlink()
        with self.p.connect() as con:
            self.p.event(con, self.identity, 'qualification_recorded', 'Later contradictory lifecycle')
        self.refuses()

    def test_unknown_baseline_remains_null_when_terminal_audit_is_recognized(self):
        # A supported producer already has its own unknown-baseline coverage;
        # retain the exact same accounting in both the stored plan and event.
        plan = json.loads(self.old['request'])
        plan['cumulativeActualGameStartsBefore'] = None
        raw = json.dumps(plan, sort_keys=True)
        review = m.read(self.review_path)
        import hashlib
        review['preparedRequestSha256'] = hashlib.sha256(raw.encode()).hexdigest()
        m.write(self.review_path, review)
        value = json.loads(self.event['note'])
        value.update(cumulativeActualGameStartsBefore=None, cumulativeActualGameStartsAfter=None,
                     reviewed=review, review={'path': str(self.review_path), 'sha256': m.digest(self.review_path)})
        self.rewrite_event(value)
        with self.p.connect() as con:
            con.execute('UPDATE qualifications SET request=? WHERE id=?', (raw, self.identity))
        before = self.p.qualification_show(self.identity)
        with self.p.connect() as con:
            self.assertFalse(self.p.qualification_unsettled(con))
        self.assertEqual(self.p.qualification_show(self.identity), before)
        self.assertIsNone(json.loads(before['request'])['cumulativeActualGameStartsBefore'])

    def test_current_active_owners_still_block_with_valid_old_terminal_audit(self):
        mutations = [
            ("INSERT INTO qualifications VALUES('current','{}','prepared',NULL,NULL)", "DELETE FROM qualifications WHERE id='current'"),
            ("INSERT INTO qualifications VALUES('current','{}','running',1,NULL)", "DELETE FROM qualifications WHERE id='current'"),
            ("INSERT INTO jobs(id,mode,subject,origin,status,submitted,request) VALUES('current','automatic','x','x','running',1,'{}')", "DELETE FROM jobs"),
            ("INSERT INTO game_sessions(id,request,status) VALUES('current','{}','preparing')", "DELETE FROM game_sessions"),
            ("INSERT INTO retry_attempts VALUES('current','x','{}',1,'collecting',NULL,NULL,NULL,NULL,NULL)", "DELETE FROM retry_attempts"),
            ("INSERT INTO cycle_slots(id,cycle_id,iteration,order_id,request,status) VALUES('current','x',1,'x','{}','reserved')", "DELETE FROM cycle_slots"),
        ]
        for mutation, undo in mutations:
            with self.subTest(mutation=mutation):
                with self.p.connect() as con:
                    con.execute(mutation)
                self.refuses()
                with self.p.connect() as con:
                    con.execute(undo)


if __name__ == '__main__':
    unittest.main()

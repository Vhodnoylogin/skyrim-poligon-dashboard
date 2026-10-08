"""A reviewed replay preserves closed cycle ownership and refuses drift/cancellation."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

import polygon as mod
import test_subject_contract as subject_fixtures
import test_post_start_continuations as continuation_fixtures


class CycleReplayTests(unittest.TestCase):
    setUp = subject_fixtures.SeparationTests.setUp
    qualify = subject_fixtures.SeparationTests.qualify
    games = continuation_fixtures.PostStartTests.games

    def fixture(self):
        order = copy.deepcopy(self.order)
        order['cycle'] = {'id': 'cycle-1', 'iteration': 1, 'slotId': 'slot-1'}
        auth = json.dumps({'sourceChat': order['sourceChat'], 'sourceThreadId': order['sourceThreadId'],
                           'maxIterations': 1, 'deadlineUtc': 1})  # Expired origin is never revived.
        ack = self.root / 'ack.json'
        mod.write(ack, {'slotId': 'slot-1', 'sourceThreadId': order['sourceThreadId']})
        receipt = json.dumps({'path': str(ack), 'sha256': mod.digest(ack)})
        with self.p.connect() as con:
            con.execute("INSERT INTO cycles VALUES(?,?,'blocked','tool failure')", ('cycle-1', auth))
            con.execute("INSERT INTO cycle_slots(id,cycle_id,iteration,order_id,request,status,receipt) VALUES(?,?,1,?,?,'released',?)",
                        ('slot-1', 'cycle-1', order['id'], '{}', receipt))
            row = con.execute('SELECT * FROM cycle_slots WHERE id=?', ('slot-1',)).fetchone()
        ticket = {'kind': 'post-start-tooling', 'authorityReview': {
            'cycleSubjectReplayPermitted': True, 'preserveCycleState': True,
            'cycleReplay': {'cycleId': 'cycle-1', 'slotId': 'slot-1', 'iteration': 1,
                'authorizationSha256': hashlib.sha256(auth.encode()).hexdigest(),
                'grantSha256': self.p.slot_view(row)['grantSha256'],
                'receiptSha256': hashlib.sha256(receipt.encode()).hexdigest()}}}
        return order, ticket, ack

    def snapshot(self):
        with self.p.connect() as con:
            return [dict(r) for r in con.execute('SELECT * FROM cycles')], [dict(r) for r in con.execute('SELECT * FROM cycle_slots')]

    def test_expired_blocked_cycle_stays_closed_and_immutable(self):
        order, ticket, _ = self.fixture()
        before = self.snapshot()
        self.p.continuation_cycle_review(ticket, order)
        self.p.continuation_cycle_review(ticket, order)
        self.assertEqual(self.snapshot(), before)

    def test_pretest_and_missing_explicit_review_are_refused(self):
        order, ticket, _ = self.fixture()
        for key in ('cycleSubjectReplayPermitted', 'preserveCycleState', 'cycleReplay'):
            altered = copy.deepcopy(ticket)
            del altered['authorityReview'][key]
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'explicit operator review'):
                self.p.continuation_cycle_review(altered, order)
        ticket['kind'] = 'pretest-tooling'
        with self.assertRaisesRegex(ValueError, 'explicit operator review'):
            self.p.continuation_cycle_review(ticket, order)

    def test_cancellation_or_unreleased_slot_refuses_later_dispatch_review(self):
        order, ticket, _ = self.fixture()
        self.p.continuation_cycle_review(ticket, order)
        with self.p.connect() as con:
            con.execute("UPDATE cycles SET status='cancelled'")
        with self.assertRaisesRegex(ValueError, 'blocked original'):
            self.p.continuation_cycle_review(ticket, order)
        with self.p.connect() as con:
            con.execute("UPDATE cycles SET status='blocked'")
            con.execute("UPDATE cycle_slots SET status='reserved'")
        with self.assertRaisesRegex(ValueError, 'restored released slot'):
            self.p.continuation_cycle_review(ticket, order)

    def test_changed_grant_authority_or_ack_file_are_refused(self):
        order, ticket, ack = self.fixture()
        for field in ('authorizationSha256', 'grantSha256', 'receiptSha256', 'iteration'):
            altered = copy.deepcopy(ticket)
            altered['authorityReview']['cycleReplay'][field] = 'changed'
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'provenance changed'):
                self.p.continuation_cycle_review(altered, order)
        ack.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'pin changed'):
            self.p.continuation_cycle_review(ticket, order)

    def test_register_claim_and_freeze_preserve_cycle_subject_and_prior_report(self):
        order, review, _ = self.fixture()
        self.order = order
        # The historical predecessor fixture is fabricated offline; current
        # replay admission, authority, packet/report and ownership remain real.
        with patch.object(self.p, 'validate_cycle'):
            order, ticket, path = continuation_fixtures.PostStartTests.ticket(self)
        ticket['authorityReview'].update(review['authorityReview'])
        mod.write(path, ticket)
        before, original = self.snapshot(), self.p.get(order['id'])
        self.p.register_continuation(path)
        self.assertIsNone(self.p.claim_retry())  # Registration never clears the fixture's hold.
        clearance = mod.read(ticket['ownerAuthority']['path'])
        clearance.update(holdId=order['id'], installationSettled=True)
        clearance_path = self.root / 'clearance.json'
        mod.write(clearance_path, clearance)
        self.p.clear_pipeline(order['id'], clearance_path)
        self.assertEqual(self.p.claim_retry()['id'], ticket['id'])
        plan = self.p.prepare_platform(order, attempt_id=ticket['id'])
        self.assertEqual(plan['subjectOrderSha256'], mod.subject_contract.identity(order))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.p.get(order['id']), original)
        self.assertEqual(mod.digest(self.old_report), self.old_report_sha)
        self.assertIsNone(self.p.claim())
        with self.p.connect() as con:
            con.execute("UPDATE cycles SET status='cancelled'")
        with self.assertRaisesRegex(ValueError, 'blocked original'):
            self.p.retry_authority(ticket)

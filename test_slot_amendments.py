"""Preparation metadata amendments in isolated databases; no native calls/games."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import polygon as m
from slot_amendments import text_sha


class SlotAmendmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.p = m.Polygon(self.root)
        evidence = self.root / 'owner.txt'
        evidence.write_text('Owner: fix this mod in the bounded cycle.', encoding='utf-8')
        self.owner = dict(threadId='owner-thread', messageId='owner-turn', quote='Owner: fix this mod',
                          path=str(evidence), sha256=m.digest(evidence), verifiedBy='human instruction checked')
        approval = dict(schemaVersion=1, id='cycle-a', sourceChat='mod-a', sourceThreadId='origin-a',
                        subject='Mod A', profile='Profile', scopeId='mod-a-scope', task='Fix Mod A',
                        stopCriteria='One bounded acceptance', allowedChanges=['Mod A installation/profile configuration'],
                        maxIterations=3, deadlineUtc=time.time()+3600, ownerAuthorization=self.owner)
        m.write(self.root / 'cycle.json', approval)
        self.p.register_cycle(self.root / 'cycle.json')
        self.request = dict(schemaVersion=1, id='slot-a', cycleId='cycle-a', iteration=1, orderId='order-a',
                            sourceChat='mod-a', sourceThreadId='origin-a', writePaths=[str(self.root / 'mod.dll')],
                            installationIntent='Only Mod A and its selected profile')
        m.write(self.root / 'slot.json', self.request)
        self.p.request_slot(self.root / 'slot.json')
        self.witness = self.root / 'zero-effects.json'
        m.write(self.witness, {'liveWrites': False, 'physicalGameStarts': 0, 'reviewed': 'exact draft stayed waiting'})

    def row(self):
        return self.p.slots()[0]

    def amendment(self, name='amend-a', clearance=None, addition='profile.ini'):
        original = self.row()
        replacement = json.loads(original['request'])
        replacement['writePaths'].append(str(self.root / addition))
        replacement_path = self.root / (name+'-replacement.json')
        m.write(replacement_path, replacement)
        identity = dict(slotId='slot-a', cycleId='cycle-a', iteration=1, orderId='order-a',
                        sourceChat='mod-a', sourceThreadId='origin-a', previousRequestSha256=text_sha(original['request']))
        review = dict(schemaVersion=1, **identity, replacementRequestSha256=m.digest(replacement_path),
                      neverGranted=True, neverAcknowledged=True, noSubmittedOrder=True, liveWrites=False,
                      physicalGameStarts=0, withinOriginalAllowedChanges=True,
                      allowedWritePaths=replacement['writePaths'], reviewerThreadId='independent-tool-reviewer',
                      reason='Correct missing profile write declaration before effects', verifiedBy='independent review',
                      evidence=[{'path': str(self.witness), 'sha256': m.digest(self.witness)}])
        review_path = self.root / (name+'-review.json')
        m.write(review_path, review)
        value = dict(schemaVersion=1, id=name, **identity, ownerAuthorization=self.owner,
                     replacementRequest={'path': str(replacement_path), 'sha256': m.digest(replacement_path)},
                     review={'path': str(review_path), 'sha256': m.digest(review_path)})
        if clearance:
            value['originalClearance'] = {'path': str(clearance), 'sha256': m.digest(clearance)}
        path = self.root / (name+'.json')
        m.write(path, value)
        return path

    def edit_review(self, path, **changes):
        value = m.read(path)
        review_path = Path(value['review']['path'])
        review = m.read(review_path)
        review.update(changes)
        m.write(review_path, review)
        value['review']['sha256'] = m.digest(review_path)
        m.write(path, value)

    def clear(self):
        path = self.root / 'clearance.json'
        m.write(path, dict(schemaVersion=1, slotId='slot-a', installationSettled=True,
                           ownerAuthorization=self.owner, review={'oldTicketStatus': 'waiting', 'liveWrites': False}))
        self.p.clear_slot('slot-a', path)
        return path

    def events(self):
        with self.p.connect() as con:
            return [dict(row) for row in con.execute("SELECT * FROM events WHERE id='slot-a' ORDER BY seq")]

    def test_waiting_amendment_preserves_fifo_cycle_hold_and_original_snapshot(self):
        before = self.row()
        cycle = self.p.cycle_state('cycle-a')
        self.p.hold_pipeline('manual6', 'Unrelated retained recovery barrier')
        path = self.amendment()
        with patch.object(self.p, 'environment_idle', side_effect=AssertionError('No native work')):
            result = self.p.amend_slot('slot-a', path)
        after = self.row()
        self.assertEqual(result['status'], 'waiting')
        for key in ('id', 'seq', 'cycle_id', 'iteration', 'order_id', 'receipt'):
            self.assertEqual(after[key], before[key])
        self.assertEqual(self.p.cycle_state('cycle-a'), cycle)
        self.assertEqual(self.p.pipeline_status()['holds'][0]['id'], 'manual6')
        self.assertNotEqual(after['grantSha256'], before['grantSha256'])
        snapshot = json.loads(self.events()[-1]['note'])
        self.assertEqual(snapshot['originalSlot'], {k: v for k, v in before.items() if k != 'grantSha256'})
        self.assertEqual(snapshot['replacementRequest']['writePaths'][-1], str(self.root / 'profile.ini'))
        self.assertEqual(self.p.board(), [])

    def test_exact_duplicate_before_or_after_grant_never_reopens_or_renews(self):
        path = self.amendment()
        self.p.amend_slot('slot-a', path)
        count = len(self.events())
        self.assertTrue(self.p.amend_slot('slot-a', path)['duplicate'])
        self.assertEqual(len(self.events()), count)
        with patch.object(self.p, 'environment_idle', return_value=True):
            self.p.grant_slot()
        reserved = self.row()
        self.assertTrue(self.p.amend_slot('slot-a', path)['duplicate'])
        self.assertEqual(self.row(), reserved)

    def test_released_legacy_needs_exact_original_clearance_and_keeps_it(self):
        clearance = self.clear()
        # Retained pre-feature database: only our isolated fixture drops audit.
        with self.p.connect() as con:
            con.execute("DELETE FROM events WHERE id='slot-a'")
        before = self.row()
        path = self.amendment(clearance=clearance)
        self.assertEqual(self.p.amend_slot('slot-a', path)['status'], 'waiting')
        snapshot = json.loads(self.events()[-1]['note'])
        self.assertEqual(snapshot['originalSlot']['note'], before['note'])
        self.assertEqual(snapshot['originalClearance'], m.read(clearance))
        self.assertTrue(self.p.amend_slot('slot-a', path)['duplicate'])

    def test_released_receipt_null_alone_is_insufficient(self):
        self.clear()
        before = self.row()
        with self.assertRaisesRegex(ValueError, 'original waiting-state clearance'):
            self.p.amend_slot('slot-a', self.amendment())
        self.assertEqual(self.row(), before)

    def test_relative_clearance_pin_is_idempotent_after_revision(self):
        clearance = self.clear()
        path = self.amendment(clearance=clearance)
        value = m.read(path)
        value['originalClearance']['path'] = clearance.name
        m.write(path, value)
        self.p.amend_slot('slot-a', path)
        self.assertTrue(self.p.amend_slot('slot-a', path)['duplicate'])

    def test_stale_pre_amendment_grant_hash_cannot_ack_new_grant(self):
        before = self.row()
        self.p.amend_slot('slot-a', self.amendment())
        with patch.object(self.p, 'environment_idle', return_value=True): self.p.grant_slot()
        ack = self.root / 'old-ack.json'
        m.write(ack, dict(schemaVersion=1, slotId='slot-a', cycleId='cycle-a', iteration=1,
                          orderId='order-a', sourceChat='mod-a', sourceThreadId='origin-a', grantSha256=before['grantSha256']))
        with self.assertRaisesRegex(ValueError, 'reserved grant'): self.p.acknowledge_slot('slot-a', ack)
        self.assertIsNone(self.row()['receipt'])

    def test_new_grant_history_survives_clear_and_refuses_forged_never_granted_review(self):
        with patch.object(self.p, 'environment_idle', return_value=True):
            self.p.grant_slot()
        clearance = self.clear()
        self.assertIsNone(self.row()['receipt'])
        with self.assertRaisesRegex(ValueError, 'grant/ack/unknown'):
            self.p.amend_slot('slot-a', self.amendment(clearance=clearance))

    def test_real_preclear_reserved_snapshot_refuses_even_if_grant_event_absent(self):
        with patch.object(self.p, 'environment_idle', return_value=True):
            self.p.grant_slot()
        clearance = self.clear()
        with self.p.connect() as con:
            con.execute("DELETE FROM events WHERE id='slot-a' AND status IN ('slot_granted','slot_ever_granted')")
        with self.assertRaisesRegex(ValueError, 'clearance history'):
            self.p.amend_slot('slot-a', self.amendment(clearance=clearance))

    def test_any_subject_or_attempt_trace_refuses(self):
        path = self.amendment()
        mutations = [
            ("INSERT INTO attempts VALUES('order-a',1)", "DELETE FROM attempts"),
            ("INSERT INTO platform_attempts VALUES('order-a','{}','hash')", "DELETE FROM platform_attempts"),
            ("INSERT INTO session_members VALUES('order-a','session',0)", "DELETE FROM session_members"),
            ("INSERT INTO jobs(id,mode,subject,origin,status,submitted,request) VALUES('order-a','automatic','Mod A','mod-a','blocked',1,'{}')", "DELETE FROM jobs"),
        ]
        for mutation, undo in mutations:
            with self.subTest(mutation=mutation):
                with self.p.connect() as con: con.execute(mutation)
                with self.assertRaises(ValueError): self.p.amend_slot('slot-a', path)
                with self.p.connect() as con: con.execute(undo)

    def test_older_writer_grant_clear_cannot_hide_ever_granted_history(self):
        # Simulate an older supported writer, which knows no new Python audit.
        clearance = self.root / 'legacy-clearance.json'
        data = dict(schemaVersion=1, slotId='slot-a', installationSettled=True,
                    ownerAuthorization=self.owner, review={'oldTicketStatus': 'waiting', 'liveWrites': False})
        m.write(clearance, data)
        with self.p.connect() as con:
            con.execute("UPDATE cycle_slots SET status='reserved' WHERE id='slot-a'")
            con.execute("UPDATE cycle_slots SET status='released',note=? WHERE id='slot-a'", (json.dumps(data, sort_keys=True),))
        self.assertTrue(any(e['status'] == 'slot_ever_granted' for e in self.events()))
        self.assertFalse(any(e['status'] in ('slot_granted', 'slot_cleared') for e in self.events()))
        with self.assertRaisesRegex(ValueError, 'grant/ack/unknown'):
            self.p.amend_slot('slot-a', self.amendment(clearance=clearance))

    def test_present_acknowledgment_refuses_before_history_review(self):
        path = self.amendment()
        with self.p.connect() as con:
            con.execute("UPDATE cycle_slots SET receipt='retained-ack' WHERE id='slot-a'")
        with self.assertRaisesRegex(ValueError, 'unacknowledged preparation'):
            self.p.amend_slot('slot-a', path)

    def test_old_writer_receipt_then_null_still_retains_database_witness(self):
        with self.p.connect() as con:
            con.execute("UPDATE cycle_slots SET receipt='old-ack' WHERE id='slot-a'")
            con.execute("UPDATE cycle_slots SET receipt=NULL WHERE id='slot-a'")
        with self.assertRaisesRegex(ValueError, 'grant/ack/unknown'):
            self.p.amend_slot('slot-a', self.amendment())

    def test_witness_installation_seeds_retained_reserved_state_once(self):
        # Isolated fixture only: recreate the pre-feature grant without triggers.
        with self.p.connect() as con:
            con.execute('DROP TRIGGER slot_grant_witness_insert')
            con.execute('DROP TRIGGER slot_grant_witness_update')
            con.execute("UPDATE cycle_slots SET status='reserved' WHERE id='slot-a'")
        m.Polygon(self.root)
        count = len([e for e in self.events() if e['status'] == 'slot_ever_granted'])
        self.assertEqual(count, 1)
        m.Polygon(self.root)
        self.assertEqual(len([e for e in self.events() if e['status'] == 'slot_ever_granted']), count)

    def test_changed_origin_iteration_order_or_intent_refuses(self):
        for key, value in [('sourceThreadId', 'other-origin'), ('iteration', 2), ('orderId', 'new-order'),
                           ('id', 'new-slot'), ('installationIntent', 'Also replace third-party mods')]:
            with self.subTest(key=key):
                path = self.amendment(name='amend-'+key.lower())
                ticket = m.read(path)
                replacement_path = Path(ticket['replacementRequest']['path'])
                replacement = m.read(replacement_path); replacement[key] = value
                m.write(replacement_path, replacement)
                ticket['replacementRequest']['sha256'] = m.digest(replacement_path); m.write(path, ticket)
                self.edit_review(path, replacementRequestSha256=m.digest(replacement_path))
                with self.assertRaisesRegex(ValueError, 'only writePaths'):
                    self.p.amend_slot('slot-a', path)

    def test_independent_exact_zero_effect_review_and_pins_are_required(self):
        for change in [dict(reviewerThreadId='origin-a'), dict(liveWrites=True), dict(neverGranted=False),
                       dict(physicalGameStarts=False), dict(withinOriginalAllowedChanges=False),
                       dict(allowedWritePaths=[str(self.root / 'other.dll')])]:
            with self.subTest(change=change):
                path = self.amendment()
                self.edit_review(path, **change)
                with self.assertRaises(ValueError): self.p.amend_slot('slot-a', path)
        path = self.amendment()
        self.witness.write_text('changed', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'pin changed'): self.p.amend_slot('slot-a', path)

    def test_expired_or_stopped_or_changed_owner_refuses_without_budget_reset(self):
        path = self.amendment()
        cycle = self.p.cycle_state('cycle-a')
        before = self.row()
        with patch('slot_amendments.time.time', return_value=time.time()+7200):
            with self.assertRaisesRegex(ValueError, 'deadline'): self.p.amend_slot('slot-a', path)
        self.assertEqual(self.p.cycle_state('cycle-a'), cycle)
        self.p.stop_cycle('cycle-a', 'blocked', 'Independent reason')
        with self.assertRaisesRegex(ValueError, 'active owner cycle'): self.p.amend_slot('slot-a', path)
        self.assertEqual(self.row(), before)

    def test_deadline_is_rechecked_after_review_before_any_revision_event(self):
        path = self.amendment()
        before, events = self.row(), self.events()
        deadline = json.loads(self.p.cycle_state('cycle-a')['authorization'])['deadlineUtc']
        with patch('slot_amendments.time.time', side_effect=[deadline-1, deadline+1]):
            with self.assertRaisesRegex(ValueError, 'elapsed during amendment'):
                self.p.amend_slot('slot-a', path)
        self.assertEqual(self.row(), before)
        self.assertEqual(self.events(), events)

    def test_repeated_draft_revisions_keep_lineage_and_reuse_id_conflicts_refuse(self):
        one = self.amendment(); self.p.amend_slot('slot-a', one)
        first = self.row()
        two = self.amendment(name='amend-b', addition='manager.ini'); self.p.amend_slot('slot-a', two)
        events = [e for e in self.events() if e['status'] == 'slot_draft_amended']
        self.assertEqual(len(events), 2)
        self.assertEqual(json.loads(events[-1]['note'])['originalSlot']['note'], first['note'])
        old_duplicate = self.p.amend_slot('slot-a', one)
        self.assertTrue(old_duplicate['duplicate'])
        self.assertFalse(old_duplicate['currentlyApplied'])
        changed = m.read(two); changed['id'] = 'amend-a'; m.write(two, changed)
        with self.assertRaisesRegex(ValueError, 'already used'): self.p.amend_slot('slot-a', two)

    def test_audit_and_revision_are_atomic_on_write_failure(self):
        path = self.amendment()
        before, events = self.row(), self.events()
        original = self.p.event
        def fail(con, *args):
            original(con, *args)
            raise OSError('simulated audit/transaction interruption')
        with patch.object(self.p, 'event', side_effect=fail):
            with self.assertRaises(OSError): self.p.amend_slot('slot-a', path)
        self.assertEqual(self.row(), before)
        self.assertEqual(self.events(), events)

    def test_document_changed_between_hash_and_read_refuses(self):
        path = self.amendment()
        original_digest = m.digest
        replacement = Path(m.read(path)['replacementRequest']['path'])
        def raced_digest(target):
            value = original_digest(target)
            if Path(target) == replacement:
                data = m.read(replacement); data['writePaths'].append(str(self.root / 'unreviewed'))
                m.write(replacement, data)
            return value
        with patch.object(m, 'digest', side_effect=raced_digest):
            with self.assertRaisesRegex(ValueError, 'changed while reading'):
                self.p.amend_slot('slot-a', path)


if __name__ == '__main__':
    unittest.main()

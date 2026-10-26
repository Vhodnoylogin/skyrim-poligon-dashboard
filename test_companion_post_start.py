"""Prospective selector replay proofs in isolated queues; no game or live database."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import polygon as m
import companion_post_start as replay
import companion_pretest_resume as pretest
import subject_companion_route as route
import test_companion_pretest_resume as fixtures
from qualification import inventory


class CompanionPostStartTests(unittest.TestCase):
    pin = fixtures.CompanionPretestTests.pin
    admission_fixture = fixtures.CompanionPretestTests.admission_fixture

    def bind(self):
        self.cfg['interactive_session']['nativeBindings'] = {'schemaVersion': 1,
            'fixtureActorBases': ['0x00013475'], 'allowedRaceForms': ['0x00013746'], 'bindings': [{
                'id': 'morph_keys', 'script': 'NiOverride', 'function': 'GetBodyMorphKeys', 'scope': 'global',
                'params': ['ObjectReference', 'String'], 'returnType': 'String[]', 'effect': 'read',
                'actorSelf': False, 'actorArgs': [0], 'raceArgs': [], 'completion': 'native-return'}]}
        m.write(self.config, self.cfg); self.request['configuration'] = self.pin(self.config)
        m.write(self.requestfile, self.request)
        # The selected frozen package is deliberately small, and never contacts a game.
        package = self.executor / 'skyrim_autotest'
        (package / 'interactive_bindings.py').write_text('''class BindingError(Exception): pass
def validate(p): return p
def _metadata(b,e):
 d=b.call('papyrus',{'action':'describe','script':e['script']})
 rows=[r for r in d.get('globalFunctions',[]) if r['name']==e['function']]
 if len(rows)!=1 or rows[0].get('native') is not True: raise BindingError('signature')
 r=rows[0]
 if [v['type'].lower() for v in r['params']]!=[v.lower() for v in e['params']] or r['returnType'].lower()!=e['returnType'].lower(): raise BindingError('types')
 return r
''')
        self.qplan['executorPins'] = inventory(self.executor)
        with self.p.connect() as con:
            con.execute('UPDATE qualifications SET request=? WHERE id=?', (json.dumps(self.qplan), self.qid))
        return fixtures.CompanionPretestTests.bind(self)

    def setUp(self):
        fixtures.CompanionPretestTests.setUp(self)
        self.old_ticket = copy.deepcopy(self.ticket)
        pretest.register(self.p, self.ticket_file); pretest.admit(self.p, self.admit_file)
        self.old_id = self.old_ticket['id']
        self.old_run = Path(self.cfg['runtime']) / 'runs' / 'old-ended-native'
        archive = self.old_run / 'test-profile'; archive.mkdir(parents=True)
        (archive / 'modlist.txt').write_text('old restored archived profile')
        self.old_state = {'id': self.old_run.name, 'order': {'id': self.order['id'], 'attemptId': self.old_id,
            'subjectOrderId': self.order['id']}, 'done': True, 'restored': True, 'restoreErrors': [],
            'runner': {'pid': 21, 'birth': 210, 'path': 'mock-old-worker'},
            'game': {'pid': 22, 'birth': 220, 'path': 'mock-old-game'},
            'profileArchive': str(archive), 'testProfile': str(self.root / 'removed-old-profile')}
        m.write(self.old_run / 'state.json', self.old_state)
        m.write(self.old_run / 'result.json', {'result': 'failed', 'reason': 'Interactive session ended: Unique declared native function metadata is unavailable'})
        self.description = {'name': 'NiOverride', 'globalFunctions': [{'name': 'GetMorphKeys', 'native': True,
            'params': [{'name': 'ref', 'type': 'ObjectReference'}, {'name': 'morphName', 'type': 'string'}], 'returnType': 'string[]'}], 'memberFunctions': []}
        self.steps = self.old_run / 'steps.jsonl'
        self.step_rows = [{'kind': 'interactive-action-delivered', 'commandId': 'getter-14',
            'request': {'operation': 'binding', 'bindingId': 'morph_keys', 'args': []}},
            {'kind': 'tool', 'tool': 'papyrus', 'args': {'action': 'describe', 'script': 'NiOverride'}, 'result': self.description},
            {'kind': 'interactive-stopped', 'commandId': 'getter-14', 'reason': 'Unique declared native function metadata is unavailable', 'replayed': False}]
        self.write_steps()
        self.old_packet_file = self.p.local / 'retry-attempts' / self.old_id / 'packet.json'
        process_folder = self.old_packet_file.parent / 'subject-companion'
        m.write(process_folder / 'dispatch.json', {'client': {'identity': {'pid': 23, 'birth': 230, 'path': 'mock-old-client'}}})
        m.write(process_folder / 'report.json', {'sequencerProcess': {'identity': {'pid': 24, 'birth': 240, 'path': 'mock-old-sequencer'}}})
        self.old_packet = {'schemaVersion': 1, 'orderId': self.order['id'], 'attemptId': self.old_id,
            'subjectOrderSha256': m.subject_contract.identity(self.order), 'executionOutcome': 'failed', 'restored': True,
            'runDirectory': str(self.old_run), 'files': [self.pin(process_folder / x) for x in ('dispatch.json', 'report.json')] +
                [self.pin(self.old_run / x) for x in ('state.json', 'result.json', 'steps.jsonl')]}
        m.write(self.old_packet_file, self.old_packet)
        self.supplement = self.root / 'old-additive-supplement.json'; m.write(self.supplement, {'keepsRawPacket': self.pin(self.old_packet_file)})
        self.old_packet['collectionRepair'] = dict(self.pin(self.supplement), bytes=self.supplement.stat().st_size)
        self.old_packet['originalPacket'] = self.pin(self.old_packet_file)
        self.old_report_file = self.root / 'registered-ended-report.json'
        self.old_report = {'collectionFinished': True, 'packetSha256': m.digest(self.old_packet_file),
                          'testResult': {'testingStarted': True, 'coverage': {'passed': 1, 'unavailable': 1, 'not_run': 2}}}
        m.write(self.old_report_file, self.old_report)
        with self.p.connect() as con:
            con.execute("UPDATE retry_attempts SET status='recorded',packet=?,report=?,report_sha=? WHERE id=?",
                        (str(self.old_packet_file), str(self.old_report_file), m.digest(self.old_report_file), self.old_id))
        self.p.hold_pipeline(self.old_id, 'Confirmed getter selector tooling fault; collection ended')
        real_packet, real_report, real_projection = self.p.verify_retry_packet, self.p.verify_retry_report, self.p.test_projection
        self.packet_mock = patch.object(self.p, 'verify_retry_packet', side_effect=lambda row:
            self.old_packet if row['id'] == self.old_id else real_packet(row)).start(); self.addCleanup(patch.stopall)
        patch.object(self.p, 'verify_retry_report', side_effect=lambda row:
            self.old_report if row['id'] == self.old_id else real_report(row)).start()
        patch.object(self.p, 'test_projection', side_effect=lambda order, packet:
            {'testingStarted': True, 'interruptionObserved': True, 'subjectMismatchObserved': False}
            if packet.get('attemptId') == self.old_id else real_projection(order, packet)).start()
        patch.object(self.p, 'verify_companion_processes_dead', return_value=True).start()
        self.candidate = self.root / 'corrected-config.json'; self.new_cfg = copy.deepcopy(self.cfg)
        self.new_cfg['runtime'] = str(self.root / 'separate-replay-runtime')
        self.new_cfg['interactive_session']['nativeBindings']['bindings'][0]['function'] = 'GetMorphKeys'
        m.write(self.candidate, self.new_cfg)
        self.new_authority = self.root / 'prospective-authority.json'
        m.write(self.new_authority, {'schemaVersion': 1, 'state': 'active', 'orderIds': [self.order['id']],
            'ownerAuthorization': self.auth, 'deadlineUtc': time.time() + 900})
        self.failure = self.root / 'post-start-failure.json'
        m.write(self.failure, {'schemaVersion': 1, 'classification': 'confirmed-tooling-post-start-failure',
            'orderId': self.order['id'], 'attemptId': self.old_id, 'packetSha256': m.digest(self.old_packet_file),
            'reportSha256': m.digest(self.old_report_file), 'run': str(self.old_run), 'subjectStarted': True,
            'done': True, 'restored': True, 'restoreErrors': [], 'collectionFinished': True,
            'evidence': self.old_packet['files'], 'verifiedBy': 'independent offline proof', 'reason': 'Actual metadata excludes failed selector'})
        self.accounting = self.root / 'subject-accounting.json'
        m.write(self.accounting, {'schemaVersion': 1, 'scope': 'same-immutable-order', 'orderId': self.order['id'],
            'previousAttemptId': self.old_id, 'previousPacketSha256': m.digest(self.old_packet_file),
            'previousAttemptActualLaunches': 1, 'subjectActualLaunchesBefore': 1, 'historicalGlobalActualLaunches': None,
            'verifiedBy': 'independent offline operator', 'reason': 'Subject one, historical global remains unknown'})
        self.repair = self.root / 'selector-repair.json'
        self.repair_value = {'schemaVersion': 1, 'kind': 'companion-native-selector-repair', 'orderId': self.order['id'],
            'previousAttemptId': self.old_id, 'previousPacketSha256': m.digest(self.old_packet_file),
            'originalConfiguration': self.pin(self.config), 'configuration': self.pin(self.candidate),
            'recordedSteps': self.pin(self.steps), 'metadataStep': 2, 'operatorFiles': [self.pin(path) for path in m.HERE.glob('*.py')],
            'testEvidence': [self.pin(self.owner)], 'verifiedBy': 'independent offline reviewer', 'reason': 'Only runtime and getter selector corrected'}
        m.write(self.repair, self.repair_value)
        self.ticket = {'schemaVersion': 1, 'kind': replay.KIND, 'restartMode': 'initial-fixture', 'id': 'companion-post-start-1',
            'orderId': self.order['id'], 'previousAttemptId': self.old_id, 'previousPacketSha256': m.digest(self.old_packet_file),
            'previousReport': self.pin(self.old_report_file), 'technicalFailure': self.pin(self.failure),
            'launchAccounting': self.pin(self.accounting), 'ownerAuthority': self.pin(self.new_authority),
            'companionSelection': self.pin(self.requestfile), 'configuration': self.pin(self.candidate), 'repair': self.pin(self.repair),
            'authorityReview': {'verifiedBy': 'independent offline operator', 'reason': 'Separate bounded additional tooling verification',
                'retryPermitted': True, 'postStartContinuationPermitted': True, 'fullReplayReviewed': True,
                'preservePriorCoverage': True, 'previousAttemptBudgetConsumed': True, 'maxAdditionalAttempts': 1,
                'subjectActualLaunchesBefore': 1, 'maximumSubjectActualLaunches': 2, 'historicalGlobalActualLaunches': None}}
        self.ticket_file = self.root / 'post-start-ticket.json'; m.write(self.ticket_file, self.ticket)
        self.admit_file = self.root / 'post-start-admit.json'
        m.write(self.admit_file, {'schemaVersion': 1, 'kind': 'operator-companion-post-start-admission',
            'attemptId': self.ticket['id'], 'ticket': self.pin(self.ticket_file), 'ownerAuthorization': self.auth,
            'verifiedBy': 'offline independent operator', 'reason': 'One full replay with separately reviewed additional start',
            **{key: True for key in ('predecessorFinalReportReviewed', 'restorationReviewed', 'archiveReviewed',
                                     'repairReviewed', 'fullReplayReviewed', 'additionalStartReviewed')}})
        self.historical = {str(path): path.read_bytes() for path in (self.previous_packet, self.old_packet_file,
            self.old_report_file, self.config, self.requestfile, self.ticket_file.parent / 'ticket.json') if path.exists()}

    def write_steps(self):
        self.steps.write_text(''.join(json.dumps(row) + '\n' for row in self.step_rows), encoding='utf-8')

    def register(self): return replay.register(self.p, self.ticket_file)

    def save_ticket(self): m.write(self.ticket_file, self.ticket)

    def assert_history(self):
        self.assertEqual(self.p.get(self.order['id'])['status'], 'blocked')
        self.assertEqual({path: Path(path).read_bytes() for path in self.historical}, self.historical)
        self.assertEqual(self.old_report['testResult']['coverage']['passed'], 1)
        self.assertEqual((self.p.local / 'config.json').read_bytes(), self.host_bytes)

    def test_registration_retains_old_partial_and_hold_no_global_or_launch(self):
        with patch.object(self.p, 'executor', side_effect=AssertionError('No global fallback')):
            result = self.register()
        self.assertTrue(result['holdRetained']); self.assertFalse(result['launch']); self.assertTrue(self.register()['duplicate'])
        self.assertEqual(self.p.retry_show(self.ticket['id'])['status'], 'queued')
        self.assertIsNone(self.p.claim_retry()); self.assert_history()

    def test_legacy_dispatcher_cannot_claim_new_kind_even_without_predecessor_hold(self):
        self.register()
        with self.p.connect() as con: con.execute('DELETE FROM pipeline_holds')
        self.assertIsNone(self.p.claim_retry())
        self.assertEqual(self.p.retry_show(self.ticket['id'])['status'], 'queued')
        with self.assertRaisesRegex(ValueError, 'supported dispatch claim'):
            self.p.execute_retry(self.p.retry_show(self.ticket['id']))

    def test_preparation_refusal_records_zero_new_starts_and_retains_new_attempt_hold(self):
        self.p.register_continuation(self.ticket_file); replay.admit(self.p, self.admit_file)
        real_run = subprocess.run
        def no_native_child(args, *positional, **kwargs):
            self.assertNotIn('_execute-retry', args)
            return real_run(args, *positional, **kwargs)
        with patch.object(self.p, 'prepare_platform', side_effect=ValueError('Offline selected platform preparation refused')), \
                patch('tooling_retries.subprocess.run', side_effect=no_native_child):
            packet = replay.run(self.p, self.ticket['id'])
        self.assertIsNone(packet['runDirectory']); self.assertEqual(packet['executionOutcome'], 'blocked')
        self.assertEqual(packet['launchAccounting']['thisAttemptActualGameStarts'], 0)
        self.assertEqual(packet['launchAccounting']['subjectActualLaunchesAfter'], 1)
        self.assertEqual([x['id'] for x in self.p.pipeline_status()['holds']], [self.ticket['id']])
        self.assertIsNone(self.p.retry_show(self.ticket['id'])['report'])
        self.assert_history()

    def test_final_report_and_verified_collection_supplement_are_hard_gates(self):
        with self.p.connect() as con: con.execute('UPDATE retry_attempts SET report=NULL WHERE id=?', (self.old_id,))
        with self.assertRaisesRegex(ValueError, 'final report'): self.register()
        with self.p.connect() as con: con.execute('UPDATE retry_attempts SET report=? WHERE id=?', (str(self.old_report_file), self.old_id))
        saved = self.old_packet.pop('collectionRepair')
        with self.assertRaisesRegex(ValueError, 'collection repair'): self.register()
        self.old_packet['collectionRepair'] = saved; self.assert_history()

    def test_generated_packet_pins_with_byte_counts_keep_strict_ticket_pin_contract(self):
        self.old_packet['files'] = [dict(item, bytes=Path(item['path']).stat().st_size) for item in self.old_packet['files']]
        self.assertIn('bytes', self.old_packet['collectionRepair'])
        self.register(); replay.admit(self.p, self.admit_file)
        self.assertEqual(replay.context(self.p, self.order, self.ticket['id'])['attemptId'], self.ticket['id'])
        bad = copy.deepcopy(self.ticket); bad['configuration']['bytes'] = self.candidate.stat().st_size
        m.write(self.ticket_file, bad)
        with self.assertRaisesRegex(ValueError, 'exact pinned configuration'): replay.normalize(self.ticket_file)

    def test_actual_native_attribution_restoration_and_tooling_classification_required(self):
        for key, value in [('order', {'id': self.old_id}), ('restored', False), ('restoreErrors', ['not-restored'])]:
            state = copy.deepcopy(self.old_state); state[key] = value; m.write(self.old_run / 'state.json', state)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'native identity'): self.register()
        m.write(self.old_run / 'state.json', self.old_state)
        with patch.object(self.p, 'test_projection', return_value={'testingStarted': True, 'interruptionObserved': True, 'subjectMismatchObserved': True}):
            with self.assertRaisesRegex(ValueError, 'subject mismatch'): self.register()

    def test_only_two_configuration_deltas_are_accepted(self):
        for change in ('game', 'source', 'binding', 'reuse-runtime'):
            altered = copy.deepcopy(self.new_cfg)
            if change == 'game': altered['game'] = 'other-game'
            if change == 'source': altered['interactive_session']['sourceId'] = 'other-source'
            if change == 'binding': altered['interactive_session']['nativeBindings']['bindings'][0]['params'] = ['Actor', 'String']
            if change == 'reuse-runtime': altered['runtime'] = self.cfg['runtime']
            m.write(self.candidate, altered); self.ticket['configuration'] = self.pin(self.candidate)
            self.repair_value['configuration'] = self.pin(self.candidate); m.write(self.repair, self.repair_value)
            self.ticket['repair'] = self.pin(self.repair); self.save_ticket()
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'only fresh runtime|fresh distinct'): self.register()

    def test_spent_authority_expiry_accounting_reset_and_global_invention_refuse(self):
        original = copy.deepcopy(self.ticket)
        for change in ('old-authority', 'counter-reset', 'extra-starts', 'global-invention'):
            self.ticket = copy.deepcopy(original)
            if change == 'old-authority': self.ticket['ownerAuthority'] = self.old_ticket['ownerAuthority']
            if change == 'counter-reset': self.ticket['authorityReview']['subjectActualLaunchesBefore'] = 0
            if change == 'extra-starts': self.ticket['authorityReview']['maxAdditionalAttempts'] = 2
            if change == 'global-invention': self.ticket['authorityReview']['historicalGlobalActualLaunches'] = 1
            self.save_ticket()
            with self.subTest(change=change), self.assertRaises(ValueError): self.register()
        self.ticket = original; self.save_ticket()
        with patch.object(replay.time, 'time', return_value=time.time() + 1800), self.assertRaisesRegex(ValueError, 'deadline'):
            self.register()

    def test_recorded_native_signature_and_exact_failed_command_are_required(self):
        for change in ('not-native', 'wrong-return', 'old-exists', 'wrong-command'):
            rows = copy.deepcopy(self.step_rows)
            if change == 'not-native': rows[1]['result']['globalFunctions'][0]['native'] = False
            if change == 'wrong-return': rows[1]['result']['globalFunctions'][0]['returnType'] = 'Bool'
            if change == 'old-exists': rows[1]['result']['globalFunctions'].append(dict(rows[1]['result']['globalFunctions'][0], name='GetBodyMorphKeys'))
            if change == 'wrong-command': rows[2]['commandId'] = 'foreign'
            self.steps.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
            self.old_packet['files'][-1] = self.pin(self.steps); self.repair_value['recordedSteps'] = self.pin(self.steps)
            proof = m.read(self.failure); proof['evidence'] = self.old_packet['files']; m.write(self.failure, proof)
            self.ticket['technicalFailure'] = self.pin(self.failure)
            m.write(self.repair, self.repair_value); self.ticket['repair'] = self.pin(self.repair); self.save_ticket()
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'metadata correction|exact delivered selector'): self.register()

    def test_atomic_admission_is_running_and_dispatch_marker_prevents_second_call(self):
        self.register(); result = replay.admit(self.p, self.admit_file)
        self.assertEqual(result['status'], 'running'); self.assertFalse(result['launch'])
        self.assertEqual(self.p.pipeline_status()['holds'], []); self.assertIsNone(self.p.claim_retry())
        self.assertEqual(replay.admit(self.p, self.admit_file)['status'], 'already_admitted')
        with patch.object(self.p, 'execute_retry', return_value={'offline': True}) as execute:
            self.assertEqual(replay.run(self.p, self.ticket['id']), {'offline': True})
            with self.assertRaisesRegex(ValueError, 'already dispatched'): replay.run(self.p, self.ticket['id'])
        execute.assert_called_once(); self.assert_history()

    def test_other_queue_or_live_identity_retains_hold_and_rolls_back_admission(self):
        self.register()
        for change in ('queued-retry', 'live-predecessor', 'unfinished-runtime'):
            if change == 'queued-retry':
                with self.p.connect() as con: con.execute("INSERT INTO retry_attempts(id,order_id,request,created,status) VALUES('other','other','{}',1,'queued')")
            elif change == 'live-predecessor': self.native.alive = lambda ident: ident['pid'] == 22
            else: m.write(Path(self.new_cfg['runtime']) / 'runs' / 'unknown' / 'state.json', {'done': False})
            with self.subTest(change=change), self.assertRaises(ValueError): replay.admit(self.p, self.admit_file)
            self.assertEqual(self.p.retry_show(self.ticket['id'])['status'], 'queued')
            self.assertEqual([x['id'] for x in self.p.pipeline_status()['holds']], [self.old_id])
            if change == 'queued-retry':
                with self.p.connect() as con: con.execute("DELETE FROM retry_attempts WHERE id='other'")
            elif change == 'live-predecessor': self.native.alive = lambda ident: False

    def test_attempt_overlay_preserves_original_selection_and_all_checks(self):
        self.register(); replay.admit(self.p, self.admit_file)
        original = route.find(self.p, self.order)
        effective = replay.effective_selection(self.p, self.order, self.ticket['id'], original)
        self.assertEqual(effective, dict(original, configuration=self.ticket['configuration']))
        self.assertEqual(route.find(self.p, self.order), original)
        self.assertEqual(replay.context(self.p, self.order, self.ticket['id'])['folder'], self.p.local / 'retry-attempts' / self.ticket['id'])
        self.assertEqual(route.scenario(self.order)['cell'], 'QASmoke'); self.assert_history()

    def test_independent_death_verifier_false_or_unavailable_does_not_release_hold(self):
        self.register()
        for value in (False, None):
            with self.subTest(value=value), patch.object(self.p, 'verify_companion_processes_dead', return_value=value):
                with self.assertRaisesRegex(ValueError, 'independent predecessor'): replay.admit(self.p, self.admit_file)
            self.assertEqual([x['id'] for x in self.p.pipeline_status()['holds']], [self.old_id])

    def test_cancellation_after_admission_blocks_dispatch_without_using_old_release(self):
        self.register(); replay.admit(self.p, self.admit_file)
        value = m.read(self.new_authority); value['state'] = 'cancelled'; m.write(self.new_authority, value)
        with patch.object(self.p, 'execute_retry') as execute, self.assertRaises(ValueError):
            replay.run(self.p, self.ticket['id'])
        execute.assert_not_called()
        with self.p.connect() as con:
            self.assertIsNone(con.execute('SELECT id FROM companion_poststart_dispatches').fetchone())

    def test_original_withdrawal_after_admission_blocks_dispatch(self):
        self.register(); replay.admit(self.p, self.admit_file)
        with self.p.connect() as con: con.execute("UPDATE jobs SET status='withdrawn' WHERE id=?", (self.order['id'],))
        with patch.object(self.p, 'execute_retry') as execute, self.assertRaisesRegex(ValueError, 'blocked solo immutable'):
            replay.run(self.p, self.ticket['id'])
        execute.assert_not_called()

    def test_historical_context_survives_later_source_additions_but_dispatch_refuses_drift(self):
        self.register(); replay.admit(self.p, self.admit_file)
        expected = replay.context(self.p, self.order, self.ticket['id'])
        later = self.root / 'later-operator-source'; later.mkdir()
        (later / 'another_module.py').write_text('# later development, not this approved source closure')
        with patch.object(m, 'HERE', later):
            self.assertEqual(replay.context(self.p, self.order, self.ticket['id']), expected)
            with patch.object(self.p, 'execute_retry') as execute, self.assertRaisesRegex(ValueError, 'source inventory'):
                replay.run(self.p, self.ticket['id'])
            execute.assert_not_called()

    def test_unverified_registered_report_never_substitutes_for_finished_collection(self):
        with patch.object(self.p, 'verify_retry_report', side_effect=ValueError('registered report hash mismatch')):
            with self.assertRaisesRegex(ValueError, 'report hash'): self.register()
        self.old_report['collectionFinished'] = False
        with self.assertRaisesRegex(ValueError, 'ended collection'): self.register()
        self.assertEqual([x['id'] for x in self.p.pipeline_status()['holds']], [self.old_id])

    def test_changed_or_extra_old_archive_evidence_is_not_adopted(self):
        with patch.object(self.p, 'verify_retry_packet', side_effect=ValueError('profile archive changed')):
            with self.assertRaisesRegex(ValueError, 'archive changed'): self.register()
        self.assertEqual([x['id'] for x in self.p.pipeline_status()['holds']], [self.old_id])

    def test_scoped_accounting_is_one_to_two_and_unknown_native_is_not_zero(self):
        self.register()
        run = Path(self.new_cfg['runtime']) / 'runs' / 'fresh'
        m.write(run / 'state.json', {'order': {'id': self.order['id'], 'attemptId': self.ticket['id'], 'subjectOrderId': self.order['id']}})
        accounting = replay.packet_metadata(self.p, self.ticket, run)['launchAccounting']
        self.assertEqual(accounting['subjectActualLaunchesBefore'], 1); self.assertEqual(accounting['subjectActualLaunchesAfter'], 2)
        self.assertIsNone(accounting['historicalGlobalActualLaunches'])
        with self.p.connect() as con: con.execute('INSERT INTO attempts VALUES(?,1)', (self.ticket['id'],))
        with self.assertRaisesRegex(ValueError, 'not zero'): replay.packet_metadata(self.p, self.ticket, None)
        with patch.object(self.p, 'native_game_starts', return_value=2), self.assertRaisesRegex(ValueError, 'budget'): replay.packet_metadata(self.p, self.ticket, run)

    def test_new_kind_real_hooks_execute_collect_and_report_do_not_reuse_old_release_or_coverage(self):
        # Native execution and companion business outcomes are explicit fixtures;
        # new registration, plan/child attribution, packets and reports are real.
        self.p.register_continuation(self.ticket_file)
        replay.admit(self.p, self.admit_file)
        worker = {'pid': os.getpid(), 'birth': 9001, 'path': 'mock-new-owned-worker'}
        self.native.identity = lambda pid: worker if pid == os.getpid() else None
        import order_platform
        runner = order_platform.activate(self.executor); runner.configure = Mock()
        run = Path(self.new_cfg['runtime']) / 'runs' / 'mock-new-native'
        folder = self.p.local / 'retry-attempts' / self.ticket['id']
        def native_run(profile, scenario, **kwargs):
            self.assertEqual(kwargs['order'], {'id': self.order['id'], 'attemptId': self.ticket['id'],
                'subjectOrderId': self.order['id'], 'owner': self.order['sourceChat']})
            archive = run / 'test-profile'; archive.mkdir(parents=True)
            (archive / 'modlist.txt').write_text('newly archived distinct copied profile')
            state = {'id': run.name, 'order': kwargs['order'], 'runner': worker,
                'game': {'pid': 802, 'birth': 8020, 'path': 'mock-new-game'}, 'owned': [],
                'done': True, 'restored': True, 'restoreErrors': [], 'result': 'passed',
                'scenarioHash': m.digest(scenario), 'profileArchive': str(archive),
                'testProfile': str(self.root / 'removed-new-profile')}
            m.write(run / 'state.json', state); m.write(run / 'result.json', dict(state, checks=[]))
            return run
        runner.run = native_run
        real_subprocess_run = subprocess.run
        def child(args, *positional, **kwargs):
            if '_execute-retry' in args:
                self.assertEqual(args[-1], self.ticket['id'])
                self.p.child_retry(self.ticket['id'])
                return SimpleNamespace(returncode=0)
            return real_subprocess_run(args, *positional, **kwargs)
        summary = {'completed': True, 'uncertain': False, 'subjectStarted': True, 'pins': [],
            'checks': [{'name': name, 'result': 'not_run'} for name in self.order['subjectPlan']['checks']]}
        config_module = ModuleType('skyrim_autotest.config'); config_module.load = lambda path: copy.deepcopy(self.new_cfg)
        with patch.object(self.p, 'check_launch_authorization', side_effect=AssertionError('Spent old batch release must never authorize replay')), \
                patch.object(self.p, 'source_profile', return_value=self.order['profile']) as source_profile, \
                patch('tooling_retries.subprocess.run', side_effect=child), patch('companion_evidence.collect', return_value=summary), \
                patch.dict(sys.modules, {'skyrim_autotest': ModuleType('skyrim_autotest'), 'skyrim_autotest.config': config_module}):
            packet = replay.run(self.p, self.ticket['id'])
            plan = self.p.verify_platform(self.order, attempt_id=self.ticket['id'])
            self.assertEqual(plan['configuration'], self.new_cfg)
            self.assertEqual(plan['companionSelection'], route.find(self.p, self.order))
            retained = {(str(Path(item['path']).resolve()), item['sha256']) for item in plan['pins']}
            for item in [self.pin(self.ticket_file), self.pin(self.config)] + [self.ticket[key] for key in replay.PINS]:
                self.assertIn((str(Path(item['path']).resolve()), item['sha256']), retained)
            self.assertEqual(packet['attemptKind'], 'companion_post_start_tooling')
            self.assertEqual(packet['launchAccounting']['subjectActualLaunchesAfter'], 2)
            self.assertIsNone(packet['launchAccounting']['historicalGlobalActualLaunches'])
            source_profile.assert_called_once_with(self.order, runner, output_dir=folder)
            request = self.root / 'new-final-request.json'
            m.write(request, {'schemaVersion': 1, 'id': 'separate-new-final', 'attemptId': self.ticket['id'],
                'summary': 'Offline wiring only; mocked native/companion; no subject pass', 'collectionFinished': True})
            self.p.retry_report_ready(request)
            report = self.p.verify_retry_report(self.p.retry_show(self.ticket['id']))
        self.assertEqual(report['testResult']['coverage']['passed'], 0)
        self.assertEqual(report['testResult']['coverage']['not_run'], len(self.checks))
        self.assertEqual(report['launchAccounting'], packet['launchAccounting'])
        self.assert_history()


if __name__ == '__main__': unittest.main()

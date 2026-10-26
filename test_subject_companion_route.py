"""Offline first-attempt file plans: authority, immutable pins and owned dispatch."""
import copy
from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import polygon as m
import subject_contract as contract
import subject_companion_route as route
from qualification import inventory


class CompanionRouteTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name); self.p = m.Polygon(self.root)
        self.owner = self.root / 'current-human.txt'; self.owner.write_text('Conduct this exact bounded SE subject')
        self.auth = {'threadId': 'operator', 'messageId': 'actual-current-human', 'quote': self.owner.read_text(),
                     'path': str(self.owner), 'sha256': m.digest(self.owner), 'verifiedBy': 'independent offline test'}
        self.executor = self.root / 'frozen-rc6'; package = self.executor / 'skyrim_autotest'; package.mkdir(parents=True)
        (self.executor / 'run.py').write_text('# frozen runtime')
        (package / '__init__.py').write_text('')
        (package / 'runner.py').write_text('# frozen owned runner')
        (package / 'config.py').write_text('import json\ndef load(p): return json.load(open(p))\n')
        (package / 'scenarios.py').write_text('def validate(s):\n assert s["cell"]=="QASmoke" and s["startMode"]=="new-game"\n')
        self.provider = self.root / 'provider.dll'; self.provider.write_bytes(b'baseline-provider')
        self.subject = self.root / 'claw.dll'; self.subject.write_bytes(b'subject-under-test')
        self.origin = self.root / 'origin-plan.json'; self.sequencer = self.root / 'origin-sequencer.py'
        self.checks = ['catalogs', 'male-transform', 'female-transform', 'clear-resume']
        m.write(self.origin, {'cases': [{'id': x} for x in self.checks], 'bounds': {'maximumSeconds': 30}})
        self.sequencer.write_text('def run(exchange, emit): pass\n')
        self.transport = self.root / 'transport.py'; self.transport.write_text('# separately pinned reusable client')
        self.config = self.root / 'companion-config.json'
        self.cfg = {'runtime': str(self.root / 'fresh-runtime'), 'game_edition': 'se', 'game': str(self.root / 'game'),
                    'mo2': str(self.root / 'mo2'), 'mo2_exe': str(self.root / 'mo2/ModOrganizer.exe'),
                    'mo2_ini': str(self.root / 'mo2/ModOrganizer.ini'), 'bridge_port': 12345,
                    'bridge_token': str(self.root / 'mo2/token'), 'skse_logs': str(self.root / 'logs'),
                    'se_new_game_ui': True, 'staged_plugins': [],
                    'interactive_session': {'channelConfig': str(self.root / 'channel.json'), 'maximumSeconds': 30,
                        'sourceId': 'operator.actions', 'allowedTools': ['inspect', 'menu', 'papyrus', 'platform'],
                        'nativeBindings': {'fixtureActorBases': ['new-female'], 'bindings': ['under-test']}}}
        m.write(self.config, self.cfg)
        self.order = {'schemaVersion': 2, 'id': 'claw-core-1', 'mode': 'automatic', 'subject': 'CLAW exact build',
            'sourceChat': 'skyrimvr-claw', 'sourceThreadId': 'actual-origin', 'profile': 'SE-Testing',
            'purpose': 'Actual human preset transformation checks', 'collect': ['Mechanical outcomes and raw evidence'],
            'inputs': [{**self.pin(self.subject), 'role': 'subject'}, {**self.pin(self.origin), 'role': 'fixture'},
                       {**self.pin(self.sequencer), 'role': 'fixture'}],
            'subjectPlan': {'interface': contract.FILE_INTERFACE, 'fixture': {'cell': 'QASmoke', 'startMode': 'new-game'},
                'plan': self.pin(self.origin), 'sequencer': self.pin(self.sequencer), 'checks': self.checks, 'maximumSeconds': 30},
            'testing': {'start': {'kind': 'check', 'name': self.checks[0]},
                        'checks': [{'name': x, 'role': 'subject'} for x in self.checks]}}
        self.orderfile = self.root / 'order.json'; m.write(self.orderfile, self.order); self.p.submit(self.orderfile)
        self.order = json.loads(self.p.get(self.order['id'])['request'])
        self.qid = 'se-core-4'; self.hold = 'se-claw-priority'
        self.run = self.root / 'old-qualified-run'; archive = self.run / 'test-profile'; archive.mkdir(parents=True)
        (archive / 'modlist.txt').write_text('archived')
        self.worker = {'pid': 11, 'birth': 111, 'path': 'offline-baseline-worker'}
        self.state = {'id': 'baseline-run', 'runner': self.worker, 'order': {'id': 'qualification-' + self.qid},
                      'owned': [], 'done': True, 'restored': True, 'restoreErrors': [],
                      'testProfile': str(self.root / 'removed-copy'), 'profileArchive': str(archive)}
        m.write(self.run / 'state.json', self.state)
        self.packetfile = self.root / 'baseline-packet.json'
        self.packet = {'executionOutcome': 'passed', 'actualGameStarts': 1, 'restored': True, 'collectionFinished': True,
                       'runDirectory': str(self.run), 'files': [self.pin(self.run / 'state.json')],
                       'profileArchivePins': [self.pin(archive / 'modlist.txt')]}
        m.write(self.packetfile, self.packet)
        old_cfg = copy.deepcopy(self.cfg); old_cfg['runtime'] = str(self.root / 'baseline-runtime')
        old_cfg['interactive_session']['nativeBindings'] = {'fixtureActorBases': ['old-alvor'], 'bindings': ['race']}
        self.baseline_config = self.root / 'baseline' / 'runner-config.json'; m.write(self.baseline_config, old_cfg)
        self.qplan = {'executor': str(self.executor), 'executorPins': inventory(self.executor), 'configuration': old_cfg,
                      'configPath': str(self.baseline_config), 'pins': [self.pin(self.provider), self.pin(self.baseline_config)],
                      'ownerAuthorization': {**self.auth, 'messageId': 'older-baseline-human'}}
        qfolder = self.p.local / 'qualifications' / self.qid
        m.write(qfolder / 'worker.json', {'identity': self.worker}); m.write(qfolder / 'child-exit.json', {'returncode': 0})
        with self.p.connect() as con:
            con.execute("INSERT INTO qualifications(id,request,status,packet) VALUES(?,?,'released',?)",
                        (self.qid, json.dumps(self.qplan), json.dumps(self.pin(self.packetfile))))
        self.p.hold_pipeline(self.hold, 'Current independently reviewed SE preparation')
        self.request = {'schemaVersion': 1, 'kind': 'operator-subject-companion', 'orderId': self.order['id'],
            'subjectOrderSha256': contract.identity(self.order), 'executor': str(self.executor), 'configuration': self.pin(self.config),
            'transport': self.pin(self.transport), 'qualificationId': self.qid, 'baselinePacket': self.pin(self.packetfile),
            'holdId': self.hold, 'ownerAuthorization': self.auth, 'subjectCapabilitiesUnderTest': True,
            'verifiedBy': 'offline operator', 'reason': 'Core baseline retained; new subject API remains under test'}
        self.requestfile = self.root / 'selection.json'; m.write(self.requestfile, self.request)
        m.write(self.p.local / 'config.json', {'executor': 'old-global-vr', 'platformManifest': 'old-vr-manifest'})
        self.host_bytes = (self.p.local / 'config.json').read_bytes()
        self.native = SimpleNamespace(SessionMutex=nullcontext, processes=lambda: [{'pid': 999, 'name': 'explorer.exe'}],
                                      alive=lambda ident: False, identity=lambda pid: None)
        for item in (patch.object(self.p, 'qualification_verify', return_value=self.qplan),
                     patch.object(self.p, 'qualification_successful_result', return_value=True),
                     patch.object(self.p, 'native_game_starts', return_value=1),
                     patch('order_platform.activate', return_value=SimpleNamespace(native=self.native))):
            item.start(); self.addCleanup(item.stop)

    def pin(self, path): return {'path': str(path), 'sha256': m.digest(path)}
    def bind(self): return route.register(self.p, self.requestfile)

    def admission_fixture(self):
        self.bind()
        with self.p.connect() as con:
            con.execute('INSERT INTO releases VALUES(?,?)', ('one-current-release', json.dumps({'ownerAuthorization': self.auth})))
            con.execute('INSERT INTO released_orders VALUES(?,?)', (self.order['id'], 'one-current-release'))
        review = {'schemaVersion': 1, 'kind': 'operator-subject-companion-admission', 'orderId': self.order['id'],
                  'binding': self.pin(self.requestfile), 'baselinePacket': self.pin(self.packetfile), 'ownerAuthorization': self.auth,
                  'verifiedBy': 'offline independent operator', 'reason': 'One exact subject; no replay',
                  'preparationReviewed': True, 'restorationReviewed': True, 'archiveReviewed': True,
                  'exactOnlySubjectReviewed': True, 'subjectCapabilitiesUnderTest': True}
        self.reviewfile = self.root / 'admission.json'; m.write(self.reviewfile, review)
        return review

    def test_standalone_file_plan_needs_no_executor_to_submit_but_all_fixture_pins(self):
        with patch.object(self.p, 'executor', side_effect=AssertionError('No global executor on subject submit')):
            self.assertEqual(self.p.submit(self.orderfile)['id'], self.order['id'])
        altered = copy.deepcopy(self.order); altered['id'] = 'no-sequencer-pin'; altered['inputs'] = altered['inputs'][:-1]
        m.write(self.orderfile, altered)
        with self.assertRaisesRegex(ValueError, 'fixture inputs'): self.p.submit(self.orderfile)

    def test_exact_checklist_and_real_first_boundary_and_bounds_are_required(self):
        for change in ('duplicate', 'boundary', 'cases', 'window', 'reserved'):
            order = copy.deepcopy(self.order); order['id'] = 'bad-' + change
            if change == 'duplicate': order['subjectPlan']['checks'].append(self.checks[0])
            if change == 'boundary': order['testing']['start']['name'] = self.checks[1]
            if change == 'cases': order['subjectPlan']['checks'] = ['not-in-origin']
            if change == 'window': order['subjectPlan']['maximumSeconds'] = 1201
            if change == 'reserved': order['subjectPlan']['checks'][0] = 'companion-core-preparation'
            m.write(self.orderfile, order)
            with self.subTest(change=change), self.assertRaises(ValueError): self.p.submit(self.orderfile)

    def test_compact_origin_check_names_are_supported_without_rewriting_source(self):
        m.write(self.origin, {'checks': [{'name': x, 'role': 'subject', 'maximumSeconds': 20} for x in self.checks],
                              'bounds': {'maximumSeconds': 30}})
        order = copy.deepcopy(self.order); order['id'] = 'compact-origin'
        order['subjectPlan']['plan'] = self.pin(self.origin)
        order['inputs'][1] = {**self.pin(self.origin), 'role': 'fixture'}
        m.write(self.orderfile, order); before = self.origin.read_bytes()
        self.assertEqual(self.p.submit(self.orderfile)['id'], 'compact-origin')
        self.assertEqual(self.origin.read_bytes(), before)

    def test_binding_is_idempotent_pinned_and_does_not_claim_or_change_global_host(self):
        self.assertFalse(self.bind()['subjectCapabilitiesQualified']); self.assertTrue(self.bind()['duplicate'])
        self.assertEqual(self.p.get(self.order['id'])['status'], 'queued')
        self.assertEqual((self.p.local / 'config.json').read_bytes(), self.host_bytes)
        self.transport.write_text('changed')
        with self.assertRaises(ValueError): route.find(self.p, self.order)

    def test_new_subject_policy_is_under_test_but_core_game_or_provider_cannot_drift(self):
        self.assertFalse(self.bind()['launch'])  # Expanded policy is not called qualified.
        with self.p.connect() as con: con.execute('DELETE FROM companion_bindings')
        changed = copy.deepcopy(self.cfg); changed['game'] = 'foreign-game'; m.write(self.config, changed)
        request = {**self.request, 'configuration': self.pin(self.config)}; m.write(self.requestfile, request)
        with self.assertRaisesRegex(ValueError, 'Core baseline'): self.bind()

    def test_only_runtime_window_and_binding_data_may_differ_from_baseline(self):
        changes = [dict(self.cfg, allow_steam_client_restart=True), dict(self.cfg, extra_files=['new']),
                   dict(self.cfg, staged_plugins=[{'destination': 'SKSE/Plugins/foreign.dll', 'sha256': 'f' * 64}])]
        for field, value in (('channelConfig', 'new-channel'), ('sourceId', 'other-source'), ('allowedTools', ['console'])):
            changed = copy.deepcopy(self.cfg); changed['interactive_session'][field] = value; changes.append(changed)
        for changed in changes:
            m.write(self.config, changed); request = {**self.request, 'configuration': self.pin(self.config)}
            m.write(self.requestfile, request)
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, 'baseline|Baseline'):
                self.bind()

    def test_both_raw_inputs_use_same_frozen_loader_defaults_and_original_path_base(self):
        loader = self.executor / 'skyrim_autotest/config.py'
        loader.write_text('import json\nfrom pathlib import Path\ndef load(p):\n'
            ' p=Path(p).resolve();v=json.loads(p.read_text(encoding="utf-8-sig"))\n'
            ' for k,d in [("extra_files",[]),("collected_files",[]),("subject_state_bindings",{}),("fixture_dir",None)]: v.setdefault(k,d)\n'
            ' v["game"]=str((p.parent/v["game"]).resolve())\n'
            ' return v\n')
        original = copy.deepcopy(self.qplan['configuration'])
        original['game'] = '../game'
        m.write(self.baseline_config, original)
        self.qplan.update(configuration=original, pins=[self.pin(self.provider), self.pin(self.baseline_config)])
        proposed = copy.deepcopy(self.cfg)
        proposed.update(extra_files=[], collected_files=[], subject_state_bindings={}, fixture_dir=None)
        m.write(self.config, proposed)
        selection = {**self.request, 'configuration': self.pin(self.config)}
        before = self.baseline_config.read_bytes()
        normalized = route.configuration(None, self.order, selection, self.qplan)
        self.assertEqual(normalized, proposed)
        self.assertEqual(self.baseline_config.read_bytes(), before)
        self.assertEqual(self.qplan['configuration'], original)
        # Default insertion cannot hide a real extra snapshot or core flag.
        for changed in (dict(proposed, extra_files=['new-file']), dict(proposed, allow_owned_save_load=True)):
            m.write(self.config, changed); selection['configuration'] = self.pin(self.config)
            with self.assertRaisesRegex(ValueError, 'Core baseline'):
                route.configuration(None, self.order, selection, self.qplan)

    def test_baseline_normalization_requires_exact_raw_file_and_qualification_pin(self):
        for changed in ('missing-pin', 'changed-pin', 'raw-snapshot-mismatch'):
            q = copy.deepcopy(self.qplan)
            if changed == 'missing-pin': q['pins'] = [self.pin(self.provider)]
            if changed == 'changed-pin': q['pins'][-1]['sha256'] = '0' * 64
            if changed == 'raw-snapshot-mismatch': q['configuration']['extra_files'] = []
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                route.configuration(None, self.order, self.request, q)

    def test_unreleased_baseline_changed_executor_and_foreign_hold_refuse(self):
        with self.p.connect() as con: con.execute("UPDATE qualifications SET status='recorded'")
        with self.assertRaisesRegex(ValueError, 'released'): self.bind()
        with self.p.connect() as con: con.execute("UPDATE qualifications SET status='released'")
        (self.executor / 'run.py').write_text('new runtime')
        with self.assertRaisesRegex(ValueError, 'byte-identical'): self.bind()
        (self.executor / 'run.py').write_text('# frozen runtime')
        self.p.hold_pipeline('foreign-hold', 'foreign')
        with self.assertRaisesRegex(ValueError, 'sole'): self.bind()

    def test_global_next_cannot_claim_even_released_file_plan_without_explicit_admission(self):
        self.admission_fixture()
        with self.p.connect() as con: con.execute('DELETE FROM pipeline_holds')
        self.assertIsNone(self.p.claim()); self.assertEqual(self.p.get(self.order['id'])['status'], 'queued')

    def test_atomic_current_owner_hold_transfer_and_no_repeat_dispatch(self):
        self.admission_fixture(); seen = []; original = self.p.check_launch_authorization
        def check(order, *, connection=None):
            self.assertIsNotNone(connection)
            with self.p.connect() as other:
                seen.append(([x['id'] for x in other.execute('SELECT id FROM pipeline_holds')],
                             other.execute('SELECT status FROM jobs WHERE id=?', (order['id'],)).fetchone()[0]))
            return original(order, connection=connection)
        with (patch.object(self.p, 'execute_claimed', return_value={'fixture': 'no actual launch'}) as dispatched,
              patch.object(self.p, 'check_launch_authorization', side_effect=check)):
            self.assertEqual(route.execute(self.p, self.reviewfile), {'fixture': 'no actual launch'})
            self.assertFalse(route.execute(self.p, self.reviewfile)['rerun']); dispatched.assert_called_once()
        self.assertEqual(seen, [([self.hold], 'queued')]); self.assertEqual(self.p.pipeline_status()['holds'], [])
        self.assertEqual(self.p.qualification_show(self.qid)['status'], 'released')
        self.assertEqual((self.p.local / 'config.json').read_bytes(), self.host_bytes)

    def test_expired_release_rolls_back_hold_and_claim(self):
        self.admission_fixture()
        with self.p.connect() as con:
            con.execute('UPDATE releases SET authorization=?', (json.dumps({'ownerAuthorization': self.auth, 'deadlineUtc': 0}),))
        with patch.object(self.p, 'execute_claimed') as dispatched, self.assertRaisesRegex(ValueError, 'expired'):
            route.execute(self.p, self.reviewfile)
        self.assertEqual(self.p.get(self.order['id'])['status'], 'queued')
        self.assertEqual([x['id'] for x in self.p.pipeline_status()['holds']], [self.hold])
        self.assertIsNone(route.admission(self.p, self.order['id'])); dispatched.assert_not_called()

    def test_foreign_game_own_unfinished_runtime_and_additional_released_work_refuse(self):
        self.admission_fixture(); self.native.processes = lambda: [{'pid': 99, 'name': 'SkyrimSE.exe'}]
        with self.assertRaisesRegex(ValueError, 'game/VR'): route.execute(self.p, self.reviewfile)
        self.native.processes = lambda: [{'pid': 999, 'name': 'explorer.exe'}]
        m.write(Path(self.cfg['runtime']) / 'runs/unknown/state.json', {'done': False})
        with self.assertRaisesRegex(ValueError, 'Unfinished'): route.execute(self.p, self.reviewfile)

    def test_foreign_hold_or_old_human_release_never_receives_transfer_exception(self):
        self.admission_fixture(); self.p.hold_pipeline('foreign', 'Other task')
        with self.assertRaisesRegex(ValueError, 'sole'): route.execute(self.p, self.reviewfile)
        with self.p.connect() as con:
            con.execute("DELETE FROM pipeline_holds WHERE id='foreign'")
            con.execute('UPDATE releases SET authorization=?', (json.dumps({'ownerAuthorization': dict(self.auth, messageId='old-human')}),))
        with self.assertRaisesRegex(ValueError, 'Current one-shot'): route.execute(self.p, self.reviewfile)
        self.assertEqual(self.p.get(self.order['id'])['status'], 'queued')
        self.assertIsNone(route.admission(self.p, self.order['id']))

    def test_other_released_order_blocks_exact_transfer(self):
        self.admission_fixture()
        with self.p.connect() as con:
            con.execute("INSERT INTO jobs(id,mode,subject,origin,status,submitted,request) VALUES('other','automatic','other','other','queued',0,'{}')")
            con.execute("INSERT INTO released_orders VALUES('other','one-current-release')")
        with self.assertRaisesRegex(ValueError, 'exact released queued'): route.execute(self.p, self.reviewfile)
        self.assertEqual([x['id'] for x in self.p.pipeline_status()['holds']], [self.hold])

    def test_freeze_uses_selected_runtime_and_rechecks_all_pin_inventory(self):
        self.admission_fixture()
        with patch.object(self.p, 'execute_claimed', return_value=None): route.execute(self.p, self.reviewfile)
        plan = self.p.prepare_platform(self.order)
        self.assertEqual(plan['executor'], str(self.executor)); self.assertTrue(plan['baselineCoreOnly'])
        self.assertFalse(plan['subjectCapabilitiesQualified']); self.assertEqual(self.p.verify_platform(self.order), plan)
        self.assertEqual(plan['scenario']['steps'][0]['name'], 'companion-core-preparation')
        with self.assertRaisesRegex(ValueError, 'retry'): self.p.verify_platform(self.order, attempt_id='new-attempt')
        (self.executor / 'new-unpinned.txt').write_text('must refuse all frozen runtime changes')
        with self.assertRaisesRegex(ValueError, 'inventory'): self.p.verify_platform(self.order)

    def test_baseline_gameplay_subject_and_profile_fixture_overlap_is_not_provider_identity(self):
        self.admission_fixture()
        with patch.object(self.p, 'execute_claimed', return_value=None): route.execute(self.p, self.reviewfile)
        # Like the real refusal: the old tool qualification also pinned the
        # installed mod and source-profile files as composition evidence.
        self.qplan['pins'].extend(self.pin(Path(x['path'])) for x in self.order['inputs'])
        plan = self.p.prepare_platform(self.order)
        self.assertEqual(plan['subjectOrderSha256'], contract.identity(self.order))
        for entry in self.order['inputs']:
            self.assertIn({'path': entry['path'], 'sha256': entry['sha256']}, plan['pins'])
        self.subject.write_bytes(b'changed subject bytes')
        with self.assertRaisesRegex(ValueError, 'pin changed'): self.p.verify_platform(self.order)

    def test_true_executor_and_staged_provider_source_or_installed_destination_collisions_refuse(self):
        source = self.pin(self.provider)
        installed = self.root / 'mods' / 'explicit-provider' / 'SKSE/Plugins/provider.dll'
        installed.parent.mkdir(parents=True); installed.write_bytes(b'qualified installed copy')
        installed_pin = self.pin(installed)
        cfg = {'overwrite': str(self.root / 'overwrite'), 'staged_plugins': [
            {'source': source['path'], 'sha256': source['sha256'], 'destination': 'SKSE/Plugins/provider.dll'}]}
        q = {'executorPins': inventory(self.executor), 'pins': [source, installed_pin, self.pin(self.subject)]}
        operator = self.pin(self.transport)
        protected = [source, installed_pin, q['executorPins'][0], operator]
        for target in protected:
            for role, expected in [('subject', target['sha256']), ('fixture', target['sha256']), ('dependency', 'f' * 64)]:
                with self.subTest(target=target['path'], role=role), self.assertRaisesRegex(ValueError, 'core baseline'):
                    route.validate_core_overlaps({'inputs': [{**target, 'role': role, 'sha256': expected}]}, q, cfg, [operator])
            route.validate_core_overlaps({'inputs': [{**target, 'role': 'dependency'}]}, q, cfg, [operator])
        # Full component suffix matching, not "provider" in a subject's filename.
        similarly_named = self.root / 'mods' / 'subject' / 'provider.dll'
        similarly_named.parent.mkdir(parents=True); similarly_named.write_bytes(b'gameplay subject')
        route.validate_core_overlaps({'inputs': [{**self.pin(similarly_named), 'role': 'subject'}]}, q, cfg, [operator])

    def test_supported_retry_freezes_separate_plan_and_preserves_blocked_original_packet(self):
        self.admission_fixture()
        with patch.object(self.p, 'execute_claimed', return_value=None): route.execute(self.p, self.reviewfile)
        original_packet = self.p.evidence_dir(self.order['id']) / 'packet.json'
        m.write(original_packet, {'runDirectory': None, 'classification': 'zero-native-refusal'})
        old_bytes = original_packet.read_bytes()
        attempt = 'same-subject-pre-session-1'
        review = self.root / 'pre-session-review.json'; m.write(review, {'review': 'zero native, explicit same-subject attempt'})
        context = {'attemptId': attempt, 'folder': self.p.local / 'retry-attempts' / attempt, 'reviewPin': self.pin(review)}
        with self.p.connect() as con:
            con.execute("UPDATE jobs SET status='blocked',packet=? WHERE id=?", (str(original_packet), self.order['id']))
            con.execute("INSERT INTO retry_attempts(id,order_id,request,created,status) VALUES(?,?,?,0,'running')",
                        (attempt, self.order['id'], json.dumps({'kind': 'companion-pre-session'})))
        with patch.object(route, 'attempt_context', return_value=context):
            plan = self.p.prepare_platform(self.order, attempt_id=attempt)
            self.assertEqual(self.p.verify_platform(self.order, attempt_id=attempt), plan)
        self.assertEqual(plan['companionAttemptId'], attempt)
        self.assertEqual(plan['companionPretestReview'], self.pin(review))
        self.assertEqual(self.p.get(self.order['id'])['status'], 'blocked')
        self.assertEqual(original_packet.read_bytes(), old_bytes)
        self.assertTrue((context['folder'] / 'platform-plan.json').is_file())
        self.assertFalse((self.p.evidence_dir(self.order['id']) / 'platform-plan.json').exists())
        with self.assertRaisesRegex(ValueError, 'No frozen platform'): self.p.attempt_plan(self.order)

    def test_retry_companion_uses_separate_output_and_exact_native_attempt_attribution(self):
        attempt = 'same-subject-pre-session-1'
        folder = self.p.local / 'retry-attempts' / attempt; folder.mkdir(parents=True)
        review = self.root / 'pre-session-review.json'; m.write(review, {})
        context = {'attemptId': attempt, 'folder': folder, 'reviewPin': self.pin(review)}
        worker = {'pid': 888, 'birth': 999, 'path': 'offline-worker'}
        game = {'pid': 222, 'birth': 333, 'path': 'offline-game'}
        finished = threading.Event()
        plan = {'executor': str(self.executor), 'configuration': self.cfg, 'pins': inventory(self.executor),
                'companionSelection': {'transport': self.pin(self.transport)}}
        def owned_run(profile, scenario_path, **kwargs):
            native_order = {'id': self.order['id'], 'owner': self.order['sourceChat'],
                            'attemptId': attempt, 'subjectOrderId': self.order['id']}
            self.assertEqual(kwargs['order'], native_order); self.assertEqual(scenario_path, folder / 'scenario.json')
            m.write(Path(self.cfg['runtime']) / 'runs/fresh/state.json', {'id': 'fresh', 'runner': worker,
                'game': game, 'order': native_order, 'interactiveSession': {'ready': True}})
            self.assertTrue(finished.wait(3)); return 0
        def client(args, **kwargs):
            self.assertEqual(args[args.index('--attempt-id') + 1], attempt)
            self.assertEqual(args[args.index('--order-id') + 1], self.order['id'])
            self.assertEqual(args[args.index('--output') + 1], str(folder / 'subject-companion/report.json'))
            child = Mock(pid=500, returncode=None)
            def wait(**kwargs): child.returncode = 0; finished.set(); return 0
            child.wait.side_effect = wait; child.poll.side_effect = lambda: child.returncode
            return child
        runner = SimpleNamespace(native=SimpleNamespace(identity=lambda pid: worker), run=owned_run)
        tracker = SimpleNamespace(snapshot=lambda: {'identityVerified': True, 'status': 'exited', 'exitCode': 0}, close=lambda: {'closeConfirmed': True})
        with (patch.object(route, 'attempt_context', return_value=context),
              patch.object(self.p, 'source_profile', return_value=self.order['profile']) as selected_profile,
              patch.object(route.subprocess, 'Popen', side_effect=client),
              patch.object(route, '_retain_client', return_value=({'pid': 500, 'birth': 501, 'path': 'own-client'}, tracker))):
            self.assertEqual(route.run(self.p, self.order, plan, runner, attempt_id=attempt), 0)
        selected_profile.assert_called_once_with(self.order, runner, output_dir=folder)
        self.assertFalse((self.p.evidence_dir(self.order['id']) / 'subject-companion').exists())

    def test_bounded_companion_waits_for_exact_ready_run_while_runner_stays_on_main_thread(self):
        worker = {'pid': 888, 'birth': 999, 'path': 'offline-current-worker'}
        game = {'pid': 222, 'birth': 333, 'path': 'offline-current-game'}
        ready, exchanged = threading.Event(), threading.Event()
        state = {'id': 'fresh', 'runner': worker, 'game': game, 'interactiveSession': {'ready': True}}
        plan = {'executor': str(self.executor), 'configuration': self.cfg, 'pins': inventory(self.executor),
                'companionSelection': {'transport': self.pin(self.transport)}}
        native = SimpleNamespace(identity=lambda pid: worker)
        main_thread = threading.get_ident()
        def owned_run(profile, scenario_path, **kwargs):
            self.assertEqual(threading.get_ident(), main_thread)
            self.assertEqual(profile, self.order['profile']); self.assertTrue(kwargs['restart_idle_mo2'])
            ready.set(); self.assertTrue(exchanged.wait(3)); return 0
        runner = SimpleNamespace(native=native, run=owned_run)
        def client(args, **kwargs):
            self.assertTrue(ready.is_set()); self.assertFalse(kwargs['shell'])
            self.assertEqual(args[args.index('--order-id') + 1], self.order['id'])
            self.assertEqual(json.loads(args[args.index('--game-identity') + 1]), game)
            self.assertEqual(json.loads(args[args.index('--worker-identity') + 1]), worker)
            manifest = Path(args[args.index('--executor-manifest') + 1])
            self.assertEqual(m.read(manifest)['files'], inventory(self.executor))
            exchanged.set()
            child = Mock(pid=500, returncode=None)
            def wait(**kwargs): child.returncode = 0; return 0
            child.wait.side_effect = wait; child.poll.side_effect = lambda: child.returncode
            return child
        tracker = SimpleNamespace(snapshot=lambda: {'identityVerified': True, 'status': 'exited', 'exitCode': 0}, close=lambda: {'closeConfirmed': True})
        folder = self.p.evidence_dir(self.order['id']); folder.mkdir(parents=True)
        with (patch.object(self.p, 'matching_runs', side_effect=lambda _: [(self.root / 'state.json', state)] if ready.is_set() else []),
              patch.object(self.p, 'source_profile', return_value=self.order['profile']),
              patch.object(route.subprocess, 'Popen', side_effect=client),
              patch.object(route, '_retain_client', return_value=({'pid': 500, 'birth': 501, 'path': 'own-client'}, tracker))):
            self.assertEqual(route.run(self.p, self.order, plan, runner), 0)
        dispatch = m.read(folder / 'subject-companion/dispatch.json')
        self.assertEqual(dispatch['returncode'], 0)
        self.assertEqual(dispatch['client']['source'], self.pin(self.transport))
        self.assertFalse(dispatch['client']['terminatedOwnedClient'])
        with self.assertRaisesRegex(ValueError, 'reconnect/replay'): route.run(self.p, self.order, plan, runner)

    def test_independent_death_verifier_accepts_absence_or_reuse_but_refuses_unknown_or_same_birth(self):
        native_file = self.executor / 'skyrim_autotest/native.py'
        owner = {'pid': 771, 'birth': 100, 'path': 'owned-client'}
        plan = {'executor': str(self.executor)}
        for rows, actual, allowed in [([{'pid': 9}], None, True), ([{'pid': 771}], dict(owner, birth=101), True),
                                      ([{'pid': 771}], None, False), ([{'pid': 771}], dict(owner, path='changed-path'), False)]:
            native_file.write_text('def processes(): return ' + repr(rows) + '\ndef identity(pid): return ' + repr(actual) + '\n')
            with patch.object(route, 'verify', return_value=plan):
                if allowed: self.assertTrue(route.verify_processes_dead(self.p, self.order, [owner]))
                else:
                    with self.assertRaisesRegex(ValueError, 'death unavailable'):
                        route.verify_processes_dead(self.p, self.order, [owner])

    def test_timeout_terminates_only_once_through_retained_own_client_and_records_actual_exit(self):
        worker = {'pid': 888, 'birth': 999, 'path': 'offline-worker'}
        game = {'pid': 222, 'birth': 333, 'path': 'offline-game'}
        client_ident = {'pid': 500, 'birth': 501, 'path': 'offline-client'}
        state = {'id': 'fresh', 'runner': worker, 'game': game, 'interactiveSession': {'ready': True}}
        plan = {'executor': str(self.executor), 'configuration': self.cfg, 'pins': inventory(self.executor),
                'companionSelection': {'transport': self.pin(self.transport)}}
        finished = threading.Event(); child = Mock(pid=500, returncode=None)
        def wait(**kwargs):
            if not child.terminate.called: raise route.subprocess.TimeoutExpired('owned-client', 1)
            child.returncode = 7; finished.set(); return 7
        child.wait.side_effect = wait; child.poll.side_effect = lambda: child.returncode
        tracker = Mock()
        tracker.snapshot.return_value = {'identityVerified': True, 'identity': client_ident, 'status': 'exited', 'exitCode': 7, 'exitCodeHex': '0x00000007'}
        tracker.close.return_value = {'closeConfirmed': True}
        runner = SimpleNamespace(native=SimpleNamespace(identity=lambda pid: worker),
                                 run=lambda *args, **kwargs: 0 if finished.wait(3) else self.fail('No bounded client finish'))
        folder = self.p.evidence_dir(self.order['id']); folder.mkdir(parents=True)
        with (patch.object(self.p, 'matching_runs', return_value=[(self.root / 'state.json', state)]),
              patch.object(self.p, 'source_profile', return_value=self.order['profile']),
              patch.object(route.subprocess, 'Popen', return_value=child),
              patch.object(route, '_retain_client', return_value=(client_ident, tracker))):
            self.assertEqual(route.run(self.p, self.order, plan, runner), 0)
        child.terminate.assert_called_once(); tracker.close.assert_called_once()
        dispatch = m.read(folder / 'subject-companion/dispatch.json')
        self.assertTrue(dispatch['client']['timedOut']); self.assertTrue(dispatch['client']['terminatedOwnedClient'])
        self.assertEqual(dispatch['returncode'], 7); self.assertEqual(dispatch['client']['exit']['exitCode'], 7)


if __name__ == '__main__': unittest.main()

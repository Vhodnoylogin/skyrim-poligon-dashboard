"""Adversarial isolated fixtures; never import a real native observer or launch."""
import copy
import contextlib
from contextlib import nullcontext
import json
import io
import os
from pathlib import Path
import shutil
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import polygon as m
import qualification_pre_native as q
import test_qualification as fixtures


class PreNativeTests(unittest.TestCase):
    def setUp(self):
        fixtures.QualificationTests.setUp(self)
        self.identity = 'candidate-one'
        self.profile = self.root / 'profiles/Core'
        self.profile.mkdir(parents=True)
        (self.profile / 'settings.ini').write_text('unchanged')
        self.game = self.root / 'game'
        self.game.mkdir()
        (self.game / 'SkyrimVR.exe').write_bytes(b'synthetic installation')
        self.overwrite = self.root / 'overwrite'
        self.overwrite.mkdir()
        self.saves = self.root / 'original-saves'
        self.saves.mkdir()
        (self.saves / 'original.ess').write_bytes(b'original save bytes')
        self.host_config = self.root / 'host-config.json'
        self.host_runtime = self.root / 'host-runtime'
        m.write(self.host_config, {'runtime': str(self.host_runtime)})
        self.host['runnerConfig'] = str(self.host_config)
        m.write(self.p.local / 'config.json', self.host)
        self.token = self.root / 'bridge-token.txt'
        self.token.write_text('synthetic token only')
        self.root_cache = self.root / 'root-cache'
        self.root_cache.mkdir()
        (self.root / 'mods').mkdir()
        (self.candidate / 'skyrim_autotest/cli.py').write_text('# Synthetic CLI identity; never executed\n')
        self.config.update(game_edition='vr', game=str(self.game), profiles=str(self.root / 'profiles'),
                           mo2_ini=str(self.ini), overwrite=str(self.overwrite),
                           mo2_exe=str(self.root / 'ModOrganizer.exe'), bridge_port=12345,
                           bridge_token=str(self.token), root_builder_data=str(self.root_cache), mods=str(self.root / 'mods'))
        m.write(self.root / 'config.json', self.config)
        fixtures.QualificationTests.register(self)
        self.row = self.p.qualification_show(self.identity)
        self.plan = json.loads(self.row['request'])
        self.folder = self.p.local / 'qualifications' / self.identity
        self.folder.mkdir(parents=True)
        self.started = time.time()
        self.admission = {'id': 'qualification-' + self.identity, 'started': self.started}
        with self.p.connect() as con:
            con.execute("UPDATE qualifications SET status='running',expires=? WHERE id=?", (self.started + 900, self.identity))
            con.execute('INSERT INTO attempts VALUES(?,?)', tuple(self.admission.values()))
        m.write(self.folder / 'plan.json', self.plan)
        self.worker = {'pid': 44444, 'birth': 123, 'path': str(self.root / 'python.exe')}
        m.write(self.folder / 'worker.json', {'identity': self.worker})
        m.write(self.folder / 'child-exit.json', {'returncode': 2})
        m.write(self.folder / 'dispatch-intent.json', {'id': self.identity, 'at': self.started, 'expires': self.started + 900})
        m.write(self.folder / 'profile-selection.json', {'sourceProfile': 'Core', 'selection': {'mode': 'active'},
                'copyOwner': 'skyrim-autotest', 'originalProfilePreserved': True})
        m.write(self.folder / 'executor.log', {'error': 'Missing required file: ' + str(self.game / 'sksevr_loader.exe')})
        export = self.root / 'original-dashboard'
        export.mkdir()
        files = []
        for pin in self.plan['pins']:
            source = Path(pin['path'])
            if source.parent == m.HERE and source.suffix == '.py':
                target = export / source.name
                shutil.copyfile(source, target)
                files.append({'originalPath': str(source), 'exportPath': str(target), 'sha256': pin['sha256']})
        self.export_receipt = self.root / 'original-source.json'
        m.write(self.export_receipt, {'schemaVersion': 1, 'kind': 'original-dashboard-source-export',
                'qualificationId': self.identity, 'planSha256': m.digest(self.folder / 'plan.json'), 'files': files})
        self.baseline = self.root / 'protected-before.json'
        scopes = q.protected_scopes(self.config, 'Core', str(self.saves))
        scopes['hostRunnerConfig'] = str(self.host_config)
        m.write(self.baseline, {'schemaVersion': 1, 'kind': 'qualification-pre-native-baseline',
                'qualificationId': self.identity, 'capturedAt': self.started - 1,
                'originalSavesRoot': str(self.saves),
                'snapshots': {key: q.protected_inventory(path) for key, path in scopes.items()}})
        self.runner_hash = m.digest(self.candidate / 'skyrim_autotest/runner.py')
        self.review_path = self.root / 'pre-native-review.json'
        self.review = {'schemaVersion': 1, 'kind': 'qualification-pre-native-review', 'qualificationId': self.identity,
                'verifiedBy': 'independent synthetic operator', 'summary': 'Fixture-only reviewed pre-native refusal',
                'sourceFlowReviewed': True, 'zeroStartsReviewed': True, 'noMutationReviewed': True,
                'protectedStateReviewed': True, 'originalAuthorityReviewed': True,
                'uncertaintyResolved': True, 'reservationIsOwnRoutine': True,
                'ownerAuthorization': copy.deepcopy(self.request['ownerAuthorization']),
                'admission': self.admission, 'plan': self.pin(self.folder / 'plan.json'),
                'originalDashboardExport': self.pin(self.export_receipt),
                'implementationPins': q.implementation_pins(), 'protectedBaseline': self.pin(self.baseline),
                'sourceFlow': {'runnerSha256': self.runner_hash, 'case': 'missing-sksevr-loader-before-native-state-and-setup'},
                'evidence': {name: self.pin(self.folder / (name + ('.log' if name == 'executor' else '.json')))
                             for name in ('worker', 'child-exit', 'dispatch-intent', 'executor', 'profile-selection')}}
        self.save_review()
        self.process_rows = [{'pid': 77, 'name': 'python.exe'}]
        self.native = SimpleNamespace(SessionMutex=Mock(side_effect=lambda: nullcontext()),
                processes=lambda: copy.deepcopy(self.process_rows), alive=Mock(return_value=False),
                identity=Mock(return_value=None))
        self.observer = SimpleNamespace(native=self.native, GAME_NAMES={'skyrimvr.exe', 'sksevr_loader.exe'},
                request=Mock(return_value={'profile': 'Core'}))
        for item in (patch.object(q, 'SUPPORTED_RUNNER_SHA256', self.runner_hash),
                     patch.object(q, 'SUPPORTED_DASHBOARD', {name: m.digest(m.HERE / name) for name in ('polygon.py', 'qualification.py')}),
                     patch.object(q, '_runner', return_value=self.observer)):
            item.start()
            self.addCleanup(item.stop)

    def pin(self, path):
        return {'path': str(path), 'sha256': m.digest(path)}

    def save_review(self):
        m.write(self.review_path, self.review)

    def prefix_mode(self):
        self.review.pop('protectedBaseline')
        self.review.update(proofMode='executed-source-prefix', freshSafetyScopeReviewed=True,
                           freshSafety={'originalSavesRoot': str(self.saves)})
        dashboard_pins = [pin for pin in self.plan['pins'] if Path(pin['path']).parent == m.HERE and Path(pin['path']).suffix == '.py']
        candidate_digest = q.source_inventory_digest(self.plan['executorPins'], self.candidate)
        dashboard_digest = q.source_inventory_digest(dashboard_pins, m.HERE)
        cli_digest = m.digest(self.candidate / 'skyrim_autotest/cli.py')
        for item in (patch.object(q, 'SUPPORTED_CANDIDATE_INVENTORY', candidate_digest),
                     patch.object(q, 'SUPPORTED_DASHBOARD_INVENTORY', dashboard_digest),
                     patch.object(q, 'SUPPORTED_CLI_SHA256', cli_digest)):
            item.start()
            self.addCleanup(item.stop)
        prep = self.root / 'original-operator-preparation.json'
        m.write(prep, {'schemaVersion': 1, 'kind': 'operator-preparation', 'id': self.identity,
                'testingStarted': False, 'actualGameStarts': None, 'executorExit': {'returncode': 2},
                'finding': {'workerReceipt': {'identity': self.worker}, 'nativeRunStates': [], 'launchIntentExists': False},
                'evidence': list(self.review['evidence'].values())})
        self.review['operatorExecutionReceipt'] = self.pin(prep)
        self.audit_path = self.root / 'executed-prefix-audit.json'
        self.audit = {'schemaVersion': 1, 'kind': 'qualification-write-free-prefix-audit',
                'qualificationId': self.identity, 'verifiedBy': 'independent synthetic source reviewer',
                'analysis': 'Synthetic exact prefix: no protected mutation, runtime work or alternate action',
                'sourcePrefixReviewedWriteFree': True, 'noAlternateActionPath': True,
                'preExistingRecoveryWorkAbsent': True, 'noProtectedEnvironmentMutation': True,
                'candidateRuntimePreviouslyUnused': True, 'candidateRuntime': self.config['runtime'],
                'recoveryReasoning': 'distinct_unused_candidate_runtime_and_recover_preserves_run_state_traces',
                'planSha256': self.review['plan']['sha256'], 'worker': self.worker, 'admission': self.admission,
                'executedCommand': [self.worker['path'], str(m.HERE / 'polygon.py'), '--root', str(self.root),
                                    '_execute-qualification', self.identity],
                'commandEvidenceBasis': 'pinned_dispatch_subprocess_argv_and_exact_child_exit',
                'controlFlow': q.SOURCE_PREFIX, 'runnerSha256': self.runner_hash,
                'candidateCliSha256': cli_digest, 'candidateInventorySha256': candidate_digest,
                'originalDashboardInventorySha256': dashboard_digest,
                'evidenceSha256': {key: pin['sha256'] for key, pin in self.review['evidence'].items()}}
        self.save_audit()

    def save_audit(self):
        m.write(self.audit_path, self.audit)
        self.review['executedControlFlowAudit'] = self.pin(self.audit_path)
        self.save_review()

    def reconcile(self):
        return q.reconcile(self.p, self.identity, self.review_path)

    def refuse(self, message=None):
        before = self.p.qualification_show(self.identity)
        with self.assertRaisesRegex(ValueError, message or '.'):
            self.reconcile()
        self.assertEqual(self.p.qualification_show(self.identity), before)
        self.assertEqual([row['id'] for row in self.p.pipeline_status()['holds']], ['qualification-' + self.identity])
        self.assertFalse((self.folder / 'pre-native-packet.json').exists())

    def finish_review(self, packet):
        path = self.root / 'finish.json'
        m.write(path, {'schemaVersion': 1, 'kind': 'qualification-pre-native-finish',
                'qualificationId': self.identity, 'verifiedBy': 'independent operator',
                'summary': 'Finish only the reviewed synthetic reservation',
                'reconciliationReviewed': True, 'zeroStartsReviewed': True,
                'noMutationReviewed': True, 'finishOwnReservation': True,
                'packetSha256': m.digest(self.folder / 'pre-native-packet.json'),
                'reconciliationReviewSha256': m.digest(self.review_path)})
        return path

    def test_reconcile_and_separate_finish_preserve_admission_unknown_record_and_host(self):
        unknown = self.root / 'original-unknown.json'
        m.write(unknown, {'actualGameStarts': None})
        unknown_bytes = unknown.read_bytes()
        before_host = (self.p.local / 'config.json').read_bytes()
        packet = self.reconcile()
        self.assertEqual(packet['actualGameStarts'], 0)
        self.assertEqual(packet['cumulativeActualGameStartsAfter'], 10)
        self.assertIsNone(packet['restored'])
        self.assertEqual(packet['restorationBasis'], 'not_required_no_mutation')
        self.assertEqual(self.p.qualification_show(self.identity)['status'], 'recorded')
        self.assertEqual(len(self.p.pipeline_status()['holds']), 1)
        result = q.finish(self.p, self.identity, self.finish_review(packet))
        self.assertEqual(result['status'], 'released')
        self.assertEqual(self.p.pipeline_status()['holds'], [])
        self.assertEqual(unknown.read_bytes(), unknown_bytes)
        self.assertEqual((self.p.local / 'config.json').read_bytes(), before_host)
        with self.p.connect() as con:
            self.assertEqual(dict(con.execute('SELECT * FROM attempts').fetchone()), self.admission)
        self.assertTrue(q.finish(self.p, self.identity, self.root / 'finish.json')['duplicate'])
        with self.assertRaisesRegex(ValueError, 'only once'):
            self.p.qualification_run(self.identity)

    def test_missing_operator_review_never_infers_zero(self):
        self.review['zeroStartsReviewed'] = False
        self.save_review()
        self.refuse('Explicit')

    def test_existing_unknown_packet_is_never_replaced(self):
        original = self.folder / 'original-unknown-packet.json'
        m.write(original, {'actualGameStarts': None, 'reason': 'Original uncertainty preserved'})
        before = original.read_bytes()
        with self.p.connect() as con:
            con.execute('UPDATE qualifications SET packet=? WHERE id=?',
                        (json.dumps(self.pin(original)), self.identity))
        self.refuse('Existing qualification packet')
        self.assertEqual(original.read_bytes(), before)

    def test_timeout_even_with_rehashed_exit_is_not_supported(self):
        m.write(self.folder / 'child-exit.json', {'returncode': 2, 'timeout': True})
        self.review['evidence']['child-exit'] = self.pin(self.folder / 'child-exit.json')
        self.save_review()
        self.refuse('non-timeout')

    def test_missing_or_forged_evidence_is_refused(self):
        for key in ('worker', 'child-exit', 'executor', 'profile-selection', 'dispatch-intent'):
            with self.subTest(key=key):
                original = self.review['evidence'][key]
                self.review['evidence'][key] = {**original, 'sha256': '0' * 64}
                self.save_review()
                self.refuse('pin mismatch')
                self.review['evidence'][key] = original
        self.save_review()

    def test_even_rehashed_arbitrary_error_or_extra_log_is_refused(self):
        log = self.folder / 'executor.log'
        log.write_text('{"error":"Something else"}\n{"later":"exit"}')
        self.review['evidence']['executor'] = self.pin(log)
        self.save_review()
        self.refuse('exact known')

    def test_wrong_loader_refusal_is_not_the_supported_case(self):
        log = self.folder / 'executor.log'
        m.write(log, {'error': 'Missing required file: another-loader.exe'})
        self.review['evidence']['executor'] = self.pin(log)
        self.save_review()
        self.refuse('exact missing-loader')

    def test_launch_intent_or_any_native_trace_prevents_zero(self):
        m.write(self.folder / 'launch-intent.json', {'at': 1})
        self.refuse('launch intent')
        (self.folder / 'launch-intent.json').unlink()
        trace = Path(self.config['runtime']) / 'runs/unknown'
        trace.mkdir(parents=True)
        self.refuse('native run trace')

    def test_original_source_export_corruption_and_new_code_badpin_are_refused(self):
        receipt = m.read(self.export_receipt)
        exported = Path(receipt['files'][0]['exportPath'])
        old = exported.read_bytes()
        exported.write_bytes(b'forged old implementation')
        self.refuse('source export changed')
        exported.write_bytes(old)
        self.review['implementationPins'][0]['sha256'] = '0' * 64
        self.save_review()
        self.refuse('implementation provenance')

    def test_current_original_guard_and_mixin_drift_cannot_use_export_substitution(self):
        original = q._hash
        for name in ('qualification.py', 'shared_sessions.py', 'tooling_retries.py'):
            target = m.HERE / name
            def changed(path):
                return '0' * 64 if Path(path) == target else original(path)
            with self.subTest(current_source=name), patch.object(q, '_hash', side_effect=changed):
                self.refuse('pin mismatch')

    def test_changed_candidate_or_plan_cannot_be_blessed_by_review(self):
        source = self.candidate / 'skyrim_autotest/runner.py'
        source.write_text(source.read_text() + '\n# changed')
        self.refuse('candidate executor changed')

    def test_unknown_source_flow_hash_fails_even_when_other_pins_match(self):
        with patch.object(q, 'SUPPORTED_RUNNER_SHA256', '0' * 64):
            self.refuse('exact missing-loader candidate source')

    def test_missing_late_incomplete_or_changed_baseline_is_refused(self):
        original = m.read(self.baseline)
        for mutation in (lambda row: row.update(capturedAt=self.started + 1),
                         lambda row: row['snapshots'].pop('installation')):
            row = copy.deepcopy(original)
            mutation(row)
            m.write(self.baseline, row)
            self.review['protectedBaseline'] = self.pin(self.baseline)
            self.save_review()
            self.refuse()

    def test_changes_to_settings_saves_installation_or_profile_refuse(self):
        for path in (self.ini, self.saves / 'original.ess', self.game / 'SkyrimVR.exe', self.profile / 'settings.ini'):
            before = path.read_bytes()
            path.write_bytes(before + b'changed')
            self.refuse('baseline changed')
            path.write_bytes(before)

    def test_added_installation_file_is_also_detected(self):
        (self.game / 'new.dll').write_bytes(b'new installation')
        self.refuse('baseline changed')

    def test_added_empty_directory_is_detected(self):
        (self.overwrite / 'partial-setup').mkdir()
        self.refuse('baseline changed')

    def test_inventory_bound_includes_empty_directories(self):
        (self.overwrite / 'empty-a').mkdir()
        (self.overwrite / 'empty-b').mkdir()
        with patch.object(q, 'MAX_FILES', 1):
            with self.assertRaisesRegex(ValueError, 'bounded entry count'):
                q.protected_inventory(self.overwrite)

    def test_dangling_reparse_point_is_not_an_absent_protected_root(self):
        missing = self.root / 'dangling-junction'
        original = Path.lstat
        def metadata(path):
            if path == missing:
                return SimpleNamespace(st_mode=0, st_file_attributes=0x400)
            return original(path)
        with patch.object(Path, 'lstat', metadata):
            with self.assertRaisesRegex(ValueError, 'links/reparse'):
                q.protected_inventory(missing)

    def test_original_bytearray_profile_format_is_supported(self):
        self.ini.write_text('selected_profile=@ByteArray(Core)\n')
        baseline = m.read(self.baseline)
        baseline['snapshots']['mo2Settings'] = q.protected_inventory(self.ini)
        m.write(self.baseline, baseline)
        self.review['protectedBaseline'] = self.pin(self.baseline)
        self.save_review()
        self.assertEqual(self.reconcile()['actualGameStarts'], 0)

    def test_unknown_original_dispatch_source_is_refused(self):
        with patch.object(q, 'SUPPORTED_DASHBOARD', {'polygon.py': '0' * 64}):
            self.refuse('Original dispatch/control-flow')

    def test_reservation_reclassified_as_uncertainty_cannot_finish(self):
        with self.p.connect() as con:
            con.execute("UPDATE pipeline_holds SET note='Uncertain restoration; manual review required'")
        self.refuse('unchanged routine')

    def test_changed_host_pin_is_refused(self):
        m.write(self.p.local / 'config.json', {'executor': 'changed-host'})
        self.refuse('pin mismatch')

    def test_changed_host_runner_config_is_caught_by_protected_baseline(self):
        m.write(self.host_config, {'runtime': str(self.root / 'substitute-runtime')})
        self.refuse('baseline changed')

    def test_host_unfinished_native_state_retains_reservation(self):
        m.write(self.host_runtime / 'runs/foreign/state.json', {'done': False})
        self.refuse('Host native session')

    def test_live_mo2_profile_is_checked_without_changing_selection(self):
        manager = {'pid': 55, 'birth': 66, 'path': self.config['mo2_exe']}
        self.process_rows.append({'pid': 55, 'name': 'ModOrganizer.exe'})
        self.native.identity.return_value = manager
        session = {'mo2Pid': 55, 'serverBootId': 'boot', 'instanceId': 'instance', 'profilesPath': self.config['profiles']}
        self.observer.request.side_effect = lambda port, route, **kwargs: session if route == 'session' else {
            'profile': 'ChangedByOwner', 'ok': True, 'busyKnown': True, 'mainThread': 'ok', 'busy': None}
        self.refuse('Live active profile changed')
        self.assertEqual([call.args[1] for call in self.observer.request.call_args_list], ['session', 'ping'])

    def test_live_mo2_bridge_binds_pid_boot_instance_profiles_game_and_mods(self):
        manager = {'pid': 55, 'birth': 66, 'path': self.config['mo2_exe']}
        self.process_rows.append({'pid': 55, 'name': 'ModOrganizer.exe'})
        self.native.identity.return_value = manager
        session = {'mo2Pid': 55, 'serverBootId': 'boot', 'instanceId': 'instance', 'profilesPath': self.config['profiles']}
        ping = {'profile': 'Core', 'game': 'SkyrimVR', 'modsPath': self.config['mods'],
                'ok': True, 'busyKnown': True, 'mainThread': 'ok', 'busy': None}
        procs = {'busy': None, 'running': 0, 'launchedByMO2': [], 'serverBootId': 'boot'}
        for wrong in ({**session, 'mo2Pid': 999}, {**session, 'profilesPath': str(self.root)},
                      {**session, 'serverBootId': ''}, {**session, 'instanceId': ''}):
            self.observer.request.side_effect = lambda port, route, **kwargs: wrong if route == 'session' else ping
            self.refuse()
        self.observer.request.side_effect = lambda port, route, **kwargs: session if route == 'session' else {**ping, 'modsPath': str(self.root)}
        self.refuse('game/mods path differs')
        self.observer.request.side_effect = [session, ping, procs, {**session, 'serverBootId': 'restarted'}]
        self.refuse('session changed')
        self.observer.request.side_effect = lambda port, route, **kwargs: session if route == 'session' else procs if route == 'procs' else ping
        packet = self.reconcile()
        self.assertEqual(packet['nativeEvidence']['mo2Bridge']['before'], session)

    def test_live_mo2_unknown_or_busy_writer_and_unhealthy_ping_are_refused(self):
        manager = {'pid': 55, 'birth': 66, 'path': self.config['mo2_exe']}
        self.process_rows.append({'pid': 55, 'name': 'ModOrganizer.exe'})
        self.native.identity.return_value = manager
        session = {'mo2Pid': 55, 'serverBootId': 'boot', 'instanceId': 'instance', 'profilesPath': self.config['profiles']}
        ping = {'profile': 'Core', 'game': 'SkyrimVR', 'modsPath': self.config['mods'],
                'ok': True, 'busyKnown': True, 'mainThread': 'ok', 'busy': False}
        procs = {'busy': False, 'running': 0, 'launchedByMO2': [], 'serverBootId': 'boot'}
        for change in ({'busy': True}, {'busy': {'app': 'xEdit.exe'}}, {'running': True}, {'running': 1},
                       {'launchedByMO2': ['xEdit.exe']}, {'serverBootId': 'different-boot'}):
            wrong = {**procs, **change}
            self.observer.request.side_effect = lambda port, route, **kwargs: session if route == 'session' else wrong if route == 'procs' else ping
            self.refuse('active/unknown writer')
        for missing in ('busy', 'running', 'launchedByMO2', 'serverBootId'):
            wrong = {key: value for key, value in procs.items() if key != missing}
            self.observer.request.side_effect = lambda port, route, **kwargs: session if route == 'session' else wrong if route == 'procs' else ping
            self.refuse('active/unknown writer')
        for change in ({'ok': False}, {'busyKnown': False}, {'mainThread': 'timeout'}, {'busy': True}):
            wrong_ping = {**ping, **change}
            self.observer.request.side_effect = lambda port, route, **kwargs: session if route == 'session' else procs if route == 'procs' else wrong_ping
            self.refuse('health/idleness')

    def test_installed_bridge_231_unadvertised_busy_known_is_recorded_and_accepted(self):
        manager = {'pid': 55, 'birth': 66, 'path': self.config['mo2_exe']}
        self.process_rows.append({'pid': 55, 'name': 'ModOrganizer.exe'})
        self.native.identity.return_value = manager
        session = {'mo2Pid': 55, 'serverBootId': 'boot', 'instanceId': 'instance', 'profilesPath': self.config['profiles']}
        ping = {'profile': 'Core', 'game': 'SkyrimVR', 'modsPath': self.config['mods'],
                'ok': True, 'busyKnown': False, 'mainThread': 'ok', 'busy': None}
        procs = {'busy': None, 'running': 0, 'launchedByMO2': [], 'serverBootId': 'boot'}
        self.observer.request.side_effect = lambda port, route, **kwargs: session if route == 'session' else procs if route == 'procs' else ping
        self.refuse('health/idleness')
        ping.pop('busyKnown')
        packet = self.reconcile()
        evidence = packet['nativeEvidence']['mo2Bridge']
        self.assertEqual(evidence['busyKnownAvailability'], 'not_advertised')
        self.assertIsNone(evidence['ping']['busyKnown'])
        self.assertEqual(evidence['procs']['running'], 0)

    def test_native_game_appearing_during_safety_observation_keeps_hold(self):
        initial = copy.deepcopy(self.process_rows)
        self.native.processes = Mock(side_effect=[initial, [*initial, {'pid': 999, 'name': 'SkyrimVR.exe'}]])
        self.refuse('appeared during native observation')

    def test_live_worker_unknown_identity_and_foreign_native_are_refused(self):
        self.native.alive.return_value = True
        self.refuse('worker remains alive')
        self.native.alive.return_value = False
        self.process_rows.append({'pid': self.worker['pid'], 'name': 'python.exe'})
        self.refuse('identity is unknown')
        self.process_rows.pop()
        self.process_rows.append({'pid': 10, 'name': 'SkyrimVR.exe'})
        self.refuse('Current game')

    def test_unavailable_process_inventory_is_uncertain(self):
        self.process_rows.clear()
        self.refuse('inventory unavailable')

    def test_missing_or_altered_admission_cannot_manufacture_zero(self):
        with self.p.connect() as con:
            con.execute('DELETE FROM attempts')
        self.refuse('original admission')

    def test_other_hold_prevents_reconcile_without_removing_either(self):
        self.p.hold_pipeline('foreign', 'Uncertain unrelated installation')
        with self.assertRaisesRegex(ValueError, 'exclusive lease'):
            self.reconcile()
        self.assertEqual(len(self.p.pipeline_status()['holds']), 2)

    def test_finish_refuses_eligible_old_work_and_leaves_all_queue_rows_unchanged(self):
        packet = self.reconcile()
        review = self.finish_review(packet)
        with self.p.connect() as con:
            con.execute("INSERT INTO jobs VALUES('old','automatic','old','old','queued',0,'{}',NULL,'',NULL,NULL)")
            con.execute("INSERT INTO released_orders VALUES('old','old-release')")
        with self.assertRaisesRegex(ValueError, 'old work'):
            q.finish(self.p, self.identity, review)
        self.assertEqual(self.p.get('old')['status'], 'queued')
        self.assertEqual(len(self.p.pipeline_status()['holds']), 1)

    def test_finish_requires_exact_immutable_packet_and_review(self):
        packet = self.reconcile()
        path = self.finish_review(packet)
        review = m.read(path)
        review['packetSha256'] = '0' * 64
        m.write(path, review)
        with self.assertRaisesRegex(ValueError, 'exact authoritative packet'):
            q.finish(self.p, self.identity, path)
        self.assertEqual(len(self.p.pipeline_status()['holds']), 1)

    def test_finish_refreshes_native_and_protected_environment(self):
        packet = self.reconcile()
        path = self.finish_review(packet)
        self.native.alive.return_value = True
        with self.assertRaisesRegex(ValueError, 'worker remains alive'):
            q.finish(self.p, self.identity, path)
        self.assertEqual(len(self.p.pipeline_status()['holds']), 1)

    def test_finish_refuses_changed_protected_saves_and_new_recovery_code(self):
        packet = self.reconcile()
        path = self.finish_review(packet)
        original = self.saves / 'original.ess'
        data = original.read_bytes()
        original.write_bytes(b'changed after reconciliation')
        with self.assertRaisesRegex(ValueError, 'baseline changed'):
            q.finish(self.p, self.identity, path)
        original.write_bytes(data)
        with patch.object(q, 'implementation_pins', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'implementation provenance'):
                q.finish(self.p, self.identity, path)
        self.assertEqual(len(self.p.pipeline_status()['holds']), 1)

    def test_no_runner_launch_recovery_or_profile_mutation_is_used(self):
        self.observer.run = Mock(side_effect=AssertionError('never launch'))
        self.observer.recover = Mock(side_effect=AssertionError('never recover'))
        self.observer.configure = Mock(side_effect=AssertionError('never configure native state'))
        packet = self.reconcile()
        q.finish(self.p, self.identity, self.finish_review(packet))
        self.observer.run.assert_not_called()
        self.observer.recover.assert_not_called()
        self.observer.configure.assert_not_called()
        self.observer.request.assert_not_called()

    def test_cli_routes_only_the_explicit_review_command(self):
        for name, function in (('qualification-reconcile-pre-native', 'reconcile'),
                               ('qualification-finish-pre-native', 'finish')):
            with patch.object(q, function, return_value={'id': self.identity, 'fact': 'fixture'}) as operation:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(m.main(['--root', str(self.root), name, self.identity, str(self.review_path)]), 0)
                self.assertEqual(operation.call_args.args[0].root, self.root)
                self.assertEqual(operation.call_args.args[1:], (self.identity, self.review_path))

    def test_source_prefix_reconciles_without_historical_baseline_and_preserves_unknown(self):
        self.prefix_mode()
        prep = Path(self.review['operatorExecutionReceipt']['path'])
        original = prep.read_bytes()
        self.baseline.unlink()  # There is no historical snapshot available in this mode.
        packet = self.reconcile()
        self.assertEqual(packet['actualGameStarts'], 0)
        self.assertEqual(packet['noMutationProof'], 'no_mutation_by_this_attempt_proven_by_executed_source')
        self.assertEqual(packet['originalGlobalStateComparison'], 'not_attested')
        self.assertEqual(packet['restoration'], 'not_required_no_mutation')
        self.assertNotIn('installation', packet['runtimeEvidence']['stateProof']['freshSafetyInventory'])
        result = q.finish(self.p, self.identity, self.finish_review(packet))
        self.assertEqual(result['status'], 'released')
        self.assertEqual(prep.read_bytes(), original)

    def test_source_prefix_accepts_readonly_hardlinked_game_exe_and_never_hashes_data_bsa(self):
        self.prefix_mode()
        os.link(self.game / 'SkyrimVR.exe', self.root / 'other-game-exe-link')
        data = self.game / 'Data'
        data.mkdir()
        (data / 'bulk.bsa').write_bytes(b'synthetic bulk file; must not be opened')
        (self.root_cache / 'cached.bsa').write_bytes(b'synthetic cached bulk file; metadata only')
        original_hash = q._hash
        def no_bulk_hash(path):
            self.assertNotEqual(Path(path).suffix.lower(), '.bsa')
            return original_hash(path)
        with patch.object(q, '_hash', side_effect=no_bulk_hash):
            packet = self.reconcile()
        scopes = packet['runtimeEvidence']['stateProof']['freshSafetyInventory']
        self.assertGreaterEqual(scopes['gameExecutable']['files'][0]['identity']['hardlinks'], 2)
        self.assertIsNone(scopes['root_builder_data']['files'][0]['sha256'])

    def test_source_prefix_does_not_mislabel_current_save_inventory_as_global_comparison(self):
        self.prefix_mode()
        (self.saves / 'original.ess').write_bytes(b'Current safety observation, no historical comparison claim')
        packet = self.reconcile()
        self.assertEqual(packet['originalGlobalStateComparison'], 'not_attested')
        current = packet['runtimeEvidence']['stateProof']['freshSafetyInventory']['originalSaves']['files'][0]
        self.assertEqual(current['sha256'], m.digest(self.saves / 'original.ess'))

    def test_source_prefix_cannot_use_only_error_text_or_empty_runs(self):
        self.prefix_mode()
        del self.review['executedControlFlowAudit']
        self.save_review()
        self.refuse('Complete source-prefix')

    def test_source_prefix_requires_entire_candidate_cli_and_dashboard(self):
        self.prefix_mode()
        for name in ('SUPPORTED_CANDIDATE_INVENTORY', 'SUPPORTED_DASHBOARD_INVENTORY', 'SUPPORTED_CLI_SHA256'):
            with self.subTest(source=name), patch.object(q, name, '0' * 64):
                self.refuse('Entire candidate/CLI/original Dashboard')

    def test_source_prefix_rejects_forged_command_or_alternate_action_path(self):
        self.prefix_mode()
        original = copy.deepcopy(self.audit)
        for mutation in (lambda row: row['executedCommand'].append('--different-action'),
                         lambda row: row.update(noAlternateActionPath=False),
                         lambda row: row.update(controlFlow=['failure text only'])):
            self.audit = copy.deepcopy(original)
            mutation(self.audit)
            self.save_audit()
            self.refuse('executed source/command/control-flow')

    def test_source_prefix_keeps_original_unknown_receipt_immutable(self):
        self.prefix_mode()
        prep = Path(self.review['operatorExecutionReceipt']['path'])
        changed = m.read(prep)
        changed['actualGameStarts'] = 0
        m.write(prep, changed)
        self.review['operatorExecutionReceipt'] = self.pin(prep)
        self.save_review()
        self.refuse('Original unknown operator execution receipt')

    def test_source_prefix_rejects_baseline_relabeling_and_active_worker(self):
        self.prefix_mode()
        self.review['protectedBaseline'] = self.pin(self.baseline)
        self.save_review()
        self.refuse('do not relabel')
        self.review.pop('protectedBaseline')
        self.save_review()
        self.native.alive.return_value = True
        self.refuse('worker remains alive')

    def test_source_prefix_requires_distinct_unused_runtime_and_reviewed_recover_reasoning(self):
        self.prefix_mode()
        self.audit['recoveryReasoning'] = 'empty runs means zero'
        self.save_audit()
        self.refuse('executed source/command/control-flow')
        self.audit['recoveryReasoning'] = 'distinct_unused_candidate_runtime_and_recover_preserves_run_state_traces'
        self.save_audit()
        # The configured-host runtime is already a protected pinned file; a
        # source-prefix audit must additionally establish actual distinctness.
        m.write(self.host_config, {'runtime': self.config['runtime']})
        self.refuse('distinct previously unused')

    def test_source_prefix_finish_refreshes_safety_scope_without_claiming_historical_equality(self):
        self.prefix_mode()
        packet = self.reconcile()
        finish = self.finish_review(packet)
        (self.overwrite / 'new-uncertain-file').write_text('changed after reviewed safety observation')
        with self.assertRaisesRegex(ValueError, 'Reconciled evidence changed'):
            q.finish(self.p, self.identity, finish)
        self.assertEqual(len(self.p.pipeline_status()['holds']), 1)

    def test_fresh_scopes_resolve_implicit_rootbuilder_and_actual_steamvr_settings(self):
        config = dict(self.config)
        config.pop('root_builder_data')
        config['mo2'] = str(self.root)
        rootbuilder = self.root / 'plugins/data/RootBuilder'
        rootbuilder.mkdir(parents=True)
        m.write(rootbuilder / 'cache.json', {'readOnly': True})
        steam = self.root / 'steam-config'
        steam.mkdir()
        m.write(steam / 'steamvr.vrsettings', {'steamvr': {}})
        pointer = self.root / 'openvrpaths.vrpath'
        m.write(pointer, {'config': [str(steam)]})
        config['openvr_paths'] = str(pointer)
        scopes = q.fresh_safety_scopes(config, 'Core', str(self.saves))
        self.assertEqual(scopes['root_builder_data'], str(rootbuilder))
        self.assertEqual(scopes['openvr_paths'], str(pointer))
        self.assertEqual(scopes['steamvrSettings'], str(steam / 'steamvr.vrsettings'))
        self.assertNotIn('installation', scopes)

    def test_openvr_pointer_and_resolved_settings_use_bounded_strict_json(self):
        pointer = self.root / 'openvrpaths.vrpath'
        config = dict(self.config, openvr_paths=str(pointer))
        for data in ('{"config":["relative"]}', '{"config":[]}', '{"config":[1]}',
                     '{"config":[],"config":[]}', '{"config":NaN}', '[]'):
            pointer.write_text(data)
            with self.subTest(pointer=data), self.assertRaises(ValueError):
                q.fresh_safety_scopes(config, 'Core', str(self.saves))
        pointer.write_bytes(b' ' * 65)
        with patch.object(q, 'MAX_SETTINGS_JSON', 64), self.assertRaisesRegex(ValueError, 'bounded read size'):
            q.fresh_safety_scopes(config, 'Core', str(self.saves))
        steam = self.root / 'resolved-steam-config'
        steam.mkdir()
        m.write(pointer, {'config': [str(steam)]})
        (steam / 'steamvr.vrsettings').write_text('{"steamvr":{},"steamvr":{}}')
        with self.assertRaisesRegex(ValueError, 'Duplicate settings JSON'):
            q.fresh_safety_scopes(config, 'Core', str(self.saves))


if __name__ == '__main__':
    unittest.main()

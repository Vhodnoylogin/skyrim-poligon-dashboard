"""Offline copied-profile admission; only synthetic temporary files/processes."""
import copy
import json
from pathlib import Path
import time
from types import SimpleNamespace
import unittest

import polygon as m
import qualification_owned_mo2 as owned_mo2
import test_qualification as fixtures


class OwnedMO2Tests(unittest.TestCase):
    def setUp(self):
        f = self.f = fixtures.QualificationTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        root = f.root
        mo2 = root / 'mo2'
        mo2.mkdir()
        paths = {key: str(root / key) for key in ('mods', 'profiles', 'runtime', 'game')}
        for path in paths.values():
            Path(path).mkdir(exist_ok=True)
        paths.update(mo2=str(mo2), mo2_exe=str(mo2 / 'ModOrganizer.exe'),
                     mo2_ini=str(f.ini), bridge_token=str(mo2 / 'token.txt'))
        self.secret = 'never-retain-this-synthetic-bridge-credential'
        Path(paths['mo2_exe']).write_bytes(b'offline executable identity only')
        Path(paths['bridge_token']).write_text(self.secret, encoding='utf-8')
        self.original = b'[General]\nselected_profile=@ByteArray(Core)\notherSetting=preserve\n'
        f.ini.write_bytes(self.original)
        f.config.update(paths, game_edition='se', bridge_port=18936)
        subject = root / 'subject-input.bin'
        subject.write_bytes(b'immutable subject input')
        f.order['inputs'] = [{'path': str(f.ini), 'sha256': m.digest(f.ini)},
                             {'path': str(subject), 'sha256': m.digest(subject)}]
        m.write(root / 'config.json', f.config)
        m.write(root / 'order.json', f.order)
        f.register()
        with f.p.connect() as con:
            con.execute("UPDATE qualifications SET status='running',expires=? WHERE id=?",
                        (time.time() + 600, 'candidate-one'))
        self.row = f.p.qualification_show('candidate-one')
        self.plan = json.loads(self.row['request'])
        self.run_id = 'offline-owned-one'
        self.run = Path(paths['runtime']) / 'runs' / self.run_id
        (self.run / 'backups').mkdir(parents=True)
        self.backup = self.run / 'backups' / '0'
        self.backup.write_bytes(self.original)
        self.profile_name = 'Autotest-' + self.run_id
        self.profile = Path(paths['profiles']) / self.profile_name
        self.profile.mkdir()
        now = time.time()
        birth = int((now + 11644473600) * 10000000)
        self.worker = {'pid': 301, 'birth': birth - 30000000, 'path': str(root / 'python.exe')}
        self.manager = {'pid': 302, 'birth': birth - 10000000, 'path': paths['mo2_exe']}
        self.game = {'pid': 303, 'birth': birth, 'path': str(Path(paths['game']) / 'SkyrimSE.exe')}
        self.identities = {identity['pid']: copy.deepcopy(identity)
                           for identity in (self.worker, self.manager, self.game)}
        self.state = {'id': self.run_id, 'order': {'id': 'qualification-candidate-one'},
                      'phase': 'interactive-session', 'done': False,
                      'gameplayBootstrap': {'completed': True, 'cell': 'QASmoke'},
                      'ownedWorldGeneration': 1, 'deadline': now + 500,
                      'configuration': copy.deepcopy(f.config), 'runner': self.worker, 'game': self.game,
                      'owned': [{'role': 'mo2', 'identity': self.manager}, {'role': 'game', 'identity': self.game}],
                      'testProfileName': self.profile_name, 'testProfile': str(self.profile),
                      'preflight': {'profile': 'Core'},
                      'snapshots': [{'path': str(f.ini), 'exists': True, 'backup': str(self.backup),
                                     'sha256': m.digest(self.backup)}],
                      'launchIntents': {'mo2': {'at': now - 2, 'directory': paths['mo2']}}}
        self.state_path = self.run / 'state.json'
        m.write(self.state_path, self.state)
        self.expected = ('[General]\nselected_profile=@ByteArray(' + self.profile_name +
                         ')\notherSetting=preserve\n').encode('utf-8')
        f.ini.write_bytes(self.expected)
        self.session = {'mo2Pid': self.manager['pid'], 'profilesPath': paths['profiles'],
                        'serverBootId': 'offline-boot', 'instanceId': 'offline-instance'}
        self.ping = {'ok': True, 'mainThread': 'ok', 'profile': self.profile_name,
                     'game': 'SkyrimSE', 'modsPath': paths['mods']}
        self.calls = []
        self.on_request = None

        def request(port, route, **kwargs):
            self.assertEqual(port, 18936)
            self.assertEqual(kwargs.get('token'), self.secret)
            self.assertEqual(kwargs.get('timeout'), 3)
            self.calls.append(route)
            if self.on_request is not None:
                self.on_request(route)
            return copy.deepcopy(self.session if route == 'session' else self.ping)

        self.runner = SimpleNamespace(native=SimpleNamespace(
            identity=lambda pid: copy.deepcopy(self.identities.get(pid))), request=request)

    def verify(self, state=None):
        if state is not None:
            m.write(self.state_path, state)
        return self.f.p.qualification_verify_owned_mo2(
            self.row, self.state_path, self.state if state is None else state, self.runner)

    def test_bridge_error_metadata_does_not_prove_readiness(self):
        self.ping['ok'] = False
        with self.assertRaisesRegex(ValueError, 'Bridge copied-profile/instance mismatch'):
            self.verify()

    def test_bridge_main_thread_error_does_not_prove_readiness(self):
        self.ping['mainThread'] = 'timeout'
        with self.assertRaisesRegex(ValueError, 'Bridge copied-profile/instance mismatch'):
            self.verify()

    def test_exact_owned_selection_accepted_but_pre_native_verifier_stays_strict(self):
        with self.assertRaisesRegex(ValueError, 'Qualification pin changed'):
            self.f.p.qualification_verify(self.row)
        witness = self.verify()
        self.assertEqual(witness['scope'], 'exact-owned-selected-profile-write-only')
        self.assertEqual(witness['originalSha256'], m.digest(self.backup))
        self.assertEqual(witness['liveSha256'], m.digest(self.f.ini))
        self.assertEqual(witness['liveSha256'], witness['expectedSha256'])
        self.assertEqual(witness['manager'], self.manager)
        self.assertEqual(witness['profileName'], self.profile_name)
        self.assertEqual(self.calls, ['session', 'ping', 'session'])
        self.assertNotIn(self.secret, json.dumps(witness))

    def test_other_ini_change_or_original_selected_profile_refuses(self):
        for contents in (self.expected.replace(b'preserve', b'changed'), self.original):
            with self.subTest(contents=contents):
                self.f.ini.write_bytes(contents)
                with self.assertRaisesRegex(ValueError, 'selected_profile write'):
                    self.verify()
                self.assertEqual(self.calls, [])

    def test_selected_profile_preserves_exact_line_endings_and_unrelated_bytes(self):
        originals = (
            b'[General]\nselected_profile=@ByteArray(Core)\notherSetting=preserve\n',
            b'[General]\r\nselected_profile=@ByteArray(Core)\r\notherSetting=preserve\r\n',
            b'[General]\nselected_profile=@ByteArray(Core)\r\notherSetting=preserve\n',
            b'[General]\r\nselected_profile=@ByteArray(Core)\notherSetting=preserve\r\n',
            b'[General]\r\nselected_profile=@ByteArray(Core)\r\notherSetting=preserve',
            b'[General]\notherSetting=preserve\nselected_profile=@ByteArray(Core)',
            b'\xef\xbb\xbf[General]\r\nselected_profile=@ByteArray(Core)\r\notherSetting=\xc5\xbe\r\n',
        )
        for original in originals:
            with self.subTest(original=original):
                replacement = b'selected_profile=@ByteArray(' + self.profile_name.encode('ascii') + b')'
                expected = original.replace(b'selected_profile=@ByteArray(Core)', replacement)
                self.assertEqual(owned_mo2._selected_profile_bytes(original, self.profile_name), expected)

    def test_crlf_witness_accepts_only_the_profile_value_change(self):
        original = self.original.replace(b'\n', b'\r\n')
        self.backup.write_bytes(original)
        original_sha = m.digest(self.backup)
        plan = copy.deepcopy(self.plan)
        for pin in plan['pins']:
            if Path(pin['path']) == self.f.ini:
                pin['sha256'] = original_sha
        self.state['snapshots'][0]['sha256'] = original_sha
        m.write(self.state_path, self.state)
        expected = original.replace(b'selected_profile=@ByteArray(Core)',
            b'selected_profile=@ByteArray(' + self.profile_name.encode('ascii') + b')')
        self.f.ini.write_bytes(expected)
        witness = owned_mo2.witness(plan, self.state_path, self.state, self.runner)
        self.assertEqual(witness['liveSha256'], m.digest(self.f.ini))
        self.assertEqual(self.f.ini.read_bytes(), expected)
        for changed in (expected.replace(b'otherSetting=preserve', b'otherSetting=changed'),
                        expected.replace(b'\r\n', b'\n', 1), expected[:-2]):
            with self.subTest(changed=changed):
                self.calls.clear()
                self.f.ini.write_bytes(changed)
                with self.assertRaisesRegex(ValueError, 'selected_profile write'):
                    owned_mo2.witness(plan, self.state_path, self.state, self.runner)
                self.assertEqual(self.calls, [])

    def test_missing_or_duplicate_selected_profile_refuses_for_all_line_endings(self):
        for original in (b'[General]\r\notherSetting=preserve\r\n',
                         b'selected_profile=a\nselected_profile=b\n',
                         b'selected_profile=a\r\nselected_profile=b\r\n',
                         b'selected_profile=a\r\nselected_profile=b',
                         b'selected_profile=a\nselected_profile=b\r\n'):
            with self.subTest(original=original):
                with self.assertRaisesRegex(ValueError, 'one original selected_profile'):
                    owned_mo2._selected_profile_bytes(original, self.profile_name)

    def test_backup_change_or_snapshot_hash_change_refuses(self):
        self.backup.write_bytes(b'changed backup')
        with self.assertRaisesRegex(ValueError, 'backup hash changed'):
            self.verify()
        self.backup.write_bytes(self.original)
        self.state['snapshots'][0]['sha256'] = '0' * 64
        m.write(self.state_path, self.state)
        with self.assertRaisesRegex(ValueError, 'original settings snapshot'):
            self.verify()

    def test_other_immutable_input_change_still_refuses(self):
        (self.f.root / 'subject-input.bin').write_bytes(b'changed subject input')
        with self.assertRaisesRegex(ValueError, 'Qualification pin changed'):
            self.verify()

    def test_borrowed_profile_and_changed_name_or_source_profile_refuse(self):
        for field, value in (('borrowedMO2', self.manager), ('testProfileName', 'Core'),
                             ('testProfile', str(self.f.root / 'foreign-profile'))):
            with self.subTest(field=field):
                state = copy.deepcopy(self.state)
                state[field] = value
                with self.assertRaisesRegex(ValueError, 'copied profile'):
                    self.verify(state)
        state = copy.deepcopy(self.state)
        state['preflight']['profile'] = 'other-source'
        with self.assertRaisesRegex(ValueError, 'copied profile'):
            self.verify(state)

    def test_manager_pid_birth_reuse_refuses(self):
        self.identities[self.manager['pid']]['birth'] += 1
        with self.assertRaisesRegex(ValueError, 'manager identity changed'):
            self.verify()
        self.assertEqual(self.calls, [])

    def test_missing_worker_or_changed_game_identity_refuses(self):
        for identity in (self.worker, self.game):
            with self.subTest(identity=identity['pid']):
                original = self.identities.pop(identity['pid'])
                with self.assertRaisesRegex(ValueError, 'identity changed'):
                    self.verify()
                self.identities[identity['pid']] = original

    def test_foreign_bridge_pid_profiles_or_missing_boot_refuse(self):
        for field, value in (('mo2Pid', 999), ('profilesPath', str(self.f.root / 'foreign-profiles')),
                             ('serverBootId', ''), ('instanceId', '')):
            with self.subTest(field=field):
                original = self.session[field]
                self.session[field] = value
                with self.assertRaisesRegex(ValueError, 'Bridge session'):
                    self.verify()
                self.session[field] = original

    def test_bridge_boot_change_between_reads_refuses(self):
        def change(route):
            if self.calls == ['session', 'ping', 'session']:
                self.session['serverBootId'] = 'changed-boot'
        self.on_request = change
        with self.assertRaisesRegex(ValueError, 'changed during admission'):
            self.verify()

    def test_bridge_profile_game_or_mods_mismatch_refuses(self):
        for field, value in (('profile', 'Core'), ('game', 'SkyrimVR'),
                             ('modsPath', str(self.f.root / 'foreign-mods'))):
            with self.subTest(field=field):
                original = self.ping[field]
                self.ping[field] = value
                with self.assertRaisesRegex(ValueError, 'Bridge copied-profile/instance mismatch'):
                    self.verify()
                self.ping[field] = original

    def test_ini_change_during_bridge_reads_refuses(self):
        self.on_request = lambda route: self.f.ini.write_bytes(b'changed') if route == 'ping' else None
        with self.assertRaisesRegex(ValueError, 'changed during admission'):
            self.verify()

    def test_wrong_run_state_path_or_native_configuration_refuses(self):
        with self.assertRaisesRegex(ValueError, 'current native run'):
            self.f.p.qualification_verify_owned_mo2(self.row, self.run / 'foreign-state.json',
                                                   self.state, self.runner)
        state = copy.deepcopy(self.state)
        state['configuration']['mods'] = str(self.f.root / 'foreign-mods')
        with self.assertRaisesRegex(ValueError, 'native configuration path changed'):
            self.verify(state)

    def test_nonrunning_qualification_refuses_before_bridge(self):
        self.row['status'] = 'prepared'
        with self.assertRaisesRegex(ValueError, 'Running native qualification'):
            self.verify()
        self.assertEqual(self.calls, [])

    def test_actual_current_state_ended_after_supplied_snapshot_refuses(self):
        current = copy.deepcopy(self.state)
        current.update(done=True, phase='stop-and-restore')
        m.write(self.state_path, current)
        with self.assertRaises(ValueError):
            self.verify()

    def test_game_identity_change_during_bridge_reads_refuses(self):
        def change(route):
            if route == 'ping':
                self.identities[self.game['pid']]['birth'] += 1
        self.on_request = change
        with self.assertRaises(ValueError):
            self.verify()

    def test_current_native_state_ends_during_bridge_reads_refuses(self):
        def change(route):
            if route == 'ping':
                current = copy.deepcopy(self.state)
                current.update(done=True, phase='stop-and-restore')
                m.write(self.state_path, current)
        self.on_request = change
        with self.assertRaises(ValueError):
            self.verify()

    def test_manager_predating_the_owned_launch_intent_refuses(self):
        current = copy.deepcopy(self.state)
        current['launchIntents']['mo2']['at'] = time.time() - .01
        current['owned'][0]['identity']['birth'] -= 300000000
        self.identities[self.manager['pid']]['birth'] = current['owned'][0]['identity']['birth']
        with self.assertRaisesRegex(ValueError, 'launch intent'):
            self.verify(current)


if __name__ == '__main__':
    unittest.main()

"""Read-only witness for one native-owned SE copied-profile selection.

Original pins remain strict before native startup. Only the exact deterministic
selected_profile write has a separately witnessed post-start representation.
"""
from pathlib import Path
import hashlib
import math
import re
import threading
import time


def _require(value, message):
    if not value:
        raise ValueError('Owned MO2 admission: ' + message)


def _path(value):
    _require(isinstance(value, str) and Path(value).is_absolute(), 'absolute path required')
    path = Path(value)
    for item in (path, *path.parents):
        if item.exists():
            _require(not item.is_symlink() and not getattr(item.lstat(), 'st_file_attributes', 0) & 0x400,
                     'linked/reparse path refused')
    return path.resolve()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _selected_profile_bytes(original, profile_name):
    # Match only the value bytes. In multiline mode a dot also consumes CR,
    # which would turn this one CRLF into LF and corrupt the exact witness.
    expected, count = re.subn(rb'(?m)^selected_profile=[^\r\n]*',
        lambda _: b'selected_profile=@ByteArray(' + profile_name.encode('ascii') + b')', original)
    _require(count == 1, 'one original selected_profile setting required')
    return expected


def witness(plan, state_path, state, runner):
    config = plan['configuration']
    _require(config.get('game_edition') == 'se', 'SE copied-profile route required')
    run_id = state.get('id')
    _require(isinstance(run_id, str) and run_id not in ('.', '..')
             and re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', run_id), 'native run identity required')
    run = _path(str(_path(config['runtime']) / 'runs' / run_id))
    _require(_path(str(state_path)) == run / 'state.json' and state.get('order', {}).get('id') == 'qualification-' + plan['id']
             and state.get('done') is not True and state.get('phase') == 'interactive-session'
             and state.get('gameplayBootstrap', {}).get('completed') is True,
             'exact initialized current native run required')
    from subject_companion_route import _read_live_state
    deadline = state.get('deadline')
    _require(type(deadline) in (int, float) and math.isfinite(deadline) and deadline > time.time(),
             'original native deadline required')
    critical = ('id', 'order', 'runner', 'game', 'configuration', 'phase', 'done', 'gameplayBootstrap',
                'interactiveSession', 'deadline', 'testProfileName', 'testProfile', 'snapshots',
                'owned', 'launchIntents', 'preflight', 'borrowedMO2')
    def current_state():
        remaining = deadline - time.time()
        _require(remaining > 0, 'original native deadline expired during admission')
        value = _read_live_state(run / 'state.json', run.parent, threading.Event(),
                                 time.monotonic() + min(.75, remaining))
        _require(all(value.get(key) == state.get(key) for key in critical), 'native state changed during admission')
    current_state()
    actual_config = state.get('configuration', {})
    for key in ('mo2_ini', 'mo2_exe', 'mo2', 'mods', 'profiles', 'runtime', 'game', 'bridge_token'):
        _require(_path(actual_config.get(key)) == _path(config.get(key)), 'native configuration path changed: ' + key)
    _require(actual_config.get('game_edition') == 'se' and actual_config.get('bridge_port') == config.get('bridge_port'),
             'native edition/Bridge changed')
    ini = _path(config['mo2_ini'])
    originals = [pin for pin in plan['pins'] if _path(pin['path']) == ini]
    _require(originals and len({pin['sha256'] for pin in originals}) == 1, 'original settings pin required')
    original_sha = originals[0]['sha256']
    profile_name = 'Autotest-' + run_id
    profile = _path(str(_path(config['profiles']) / profile_name))
    _require(not state.get('borrowedMO2') and state.get('testProfileName') == profile_name
             and _path(state.get('testProfile')) == profile and profile.is_dir()
             and state.get('preflight', {}).get('profile') == plan['orderData']['profile'],
             'exact newly owned copied profile required')
    snapshots = [item for item in state.get('snapshots', []) if _path(item.get('path')) == ini]
    _require(len(snapshots) == 1 and snapshots[0].get('exists') is True
             and snapshots[0].get('sha256') == original_sha, 'original settings snapshot required')
    backup = _path(snapshots[0].get('backup'))
    _require(backup.parent == run / 'backups' and re.fullmatch(r'[0-9]+', backup.name), 'same-run settings backup required')
    original = backup.read_bytes()
    _require(_sha(original) == original_sha, 'original settings backup hash changed')
    expected = _selected_profile_bytes(original, profile_name)
    live = ini.read_bytes()
    _require(live == expected, 'settings differ beyond the owned selected_profile write')
    managers = [row.get('identity') for row in state.get('owned', []) if row.get('role') == 'mo2']
    _require(len(managers) == 1 and isinstance(managers[0], dict), 'one owned manager required')
    manager = managers[0]
    _require(_path(manager.get('path')) == _path(config['mo2_exe'])
             and runner.native.identity(manager.get('pid')) == manager, 'owned manager identity changed')
    intent = state.get('launchIntents', {}).get('mo2', {})
    _require(_path(intent.get('directory')) == _path(config['mo2'])
             and type(intent.get('at')) in (int, float) and math.isfinite(intent['at'])
             and 0 < intent['at'] <= time.time(), 'owned manager launch intent required')
    birth = manager.get('birth')
    _require(type(birth) is int and birth > 0
             and intent['at'] - 1 <= birth / 10000000 - 11644473600 <= time.time() + 1,
             'manager creation does not follow its owned launch intent')
    for role in ('runner', 'game'):
        identity = state.get(role)
        _require(isinstance(identity, dict) and runner.native.identity(identity.get('pid')) == identity,
                 'current native ' + role + ' identity changed')
    token = _path(config['bridge_token']).read_text(encoding='utf-8-sig').strip()
    _require(token, 'Bridge token unavailable')
    port = config['bridge_port']
    _require(type(port) is int and 0 < port < 65536, 'configured Bridge port required')
    def session():
        value = runner.request(port, 'session', token=token, timeout=3)
        _require(isinstance(value, dict) and value.get('mo2Pid') == manager['pid']
                 and _path(value.get('profilesPath')) == _path(config['profiles'])
                 and isinstance(value.get('serverBootId'), str) and value['serverBootId']
                 and isinstance(value.get('instanceId'), str) and value['instanceId'], 'foreign/unavailable Bridge session')
        return {key: value[key] for key in ('mo2Pid', 'profilesPath', 'serverBootId', 'instanceId')}
    before = session()
    ping = runner.request(port, 'ping', token=token, timeout=3)
    _require(isinstance(ping, dict) and ping.get('ok') is True and ping.get('mainThread') == 'ok'
             and ping.get('profile') == profile_name and ping.get('game') == 'SkyrimSE'
             and _path(ping.get('modsPath')) == _path(config['mods']), 'Bridge copied-profile/instance mismatch')
    after = session()
    _require(before == after and runner.native.identity(manager['pid']) == manager
             and ini.read_bytes() == expected and _sha(backup.read_bytes()) == original_sha,
             'owned manager/settings changed during admission')
    for role in ('runner', 'game'):
        identity = state[role]
        _require(runner.native.identity(identity['pid']) == identity,
                 'native ' + role + ' identity changed during admission')
    current_state()
    return {'path': str(ini), 'originalSha256': original_sha, 'liveSha256': _sha(live),
            'expectedSha256': _sha(expected), 'backup': {'path': str(backup), 'sha256': original_sha},
            'manager': manager, 'profile': str(profile), 'profileName': profile_name,
            'bridgeSession': after, 'bridgePing': {key: ping[key] for key in ('profile', 'game', 'modsPath')},
            'verifiedAt': time.time(), 'scope': 'exact-owned-selected-profile-write-only'}

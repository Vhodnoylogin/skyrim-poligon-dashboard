"""Read-only proof of the reviewed managed-MO2 GUI boundary for failed collection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from qualification_pre_native import _absolute, _hash, _identity

RUNNER_SHA256 = '9433d4e8cfe6a578236c5a7aab5a50c0c30f46ef4a337e0965f04b6ed35f8e00'
GUI_KEYS = {('Geometry', key) for key in ('MainWindow_downloadView_state', 'MainWindow_espList_state',
            'MainWindow_geometry', 'MainWindow_modList_state', 'MainWindow_state')}
GUI_KEYS |= {('Widgets', 'MainWindow_modList_index'), ('Widgets', 'MainWindow_tabWidget_index'),
             ('recentDirectories', '1\\directory'), ('recentDirectories', '1\\name'), ('recentDirectories', 'size')}
MAX_BYTES = 8 * 1024 * 1024


def read_pin(pin):
    import polygon as m
    if (not isinstance(pin, dict) or not {'path', 'sha256'} <= set(pin)
            or set(pin) - {'path', 'sha256', 'bytes'} or not isinstance(pin['path'], str)
            or not Path(pin['path']).is_absolute() or not isinstance(pin['sha256'], str)
            or not m.SHA.fullmatch(pin['sha256'])):
        raise ValueError('Exact absolute managed-MO2 evidence pin required')
    path = _absolute(pin['path'])
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if (len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != pin['sha256']
            or 'bytes' in pin and (type(pin['bytes']) is not int or pin['bytes'] != len(raw))):
        raise ValueError('Managed-MO2 evidence bytes/pin changed')
    return path, raw


def document(raw):
    from qualification_terminal import _json
    return _json(raw)


def ini_values(raw):
    """Strict literal Qt INI subset: no duplicate/ambiguous records or interpolation."""
    section, sections, values = None, set(), {}
    for line in raw.decode('utf-8-sig').splitlines():
        if not line.strip() or line.lstrip().startswith((';', '#')):
            continue
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
            if not section or section in sections:
                raise ValueError('Duplicate/empty managed-MO2 INI section')
            sections.add(section)
            continue
        if section is None or '=' not in line:
            raise ValueError('Unparsed managed-MO2 INI record')
        key, value = line.split('=', 1)
        if not key or key != key.strip() or (section, key) in values:
            raise ValueError('Duplicate/ambiguous managed-MO2 INI key')
        values[(section, key)] = value
    return values


def gui_delta(before, after):
    original, native = ini_values(before), ini_values(after)
    changed = {key for key in original.keys() | native.keys() if original.get(key) != native.get(key)}
    if not changed <= GUI_KEYS:
        raise ValueError('Non-GUI managed-MO2 INI value changed')
    return sorted(changed)


def validate(plan, review, plan_path):
    """Return historical byte evidence; never grant execution or restore a file."""
    import polygon as m
    proof_path, proof_raw = read_pin(review['managedMo2IniBoundary'])
    proof = document(proof_raw)
    state_path, state_raw = read_pin(review['state'])
    state = document(state_raw)
    result_path, result_raw = read_pin(review['result'])
    result = document(result_raw)
    run = state_path.parent
    if (proof.get('schemaVersion') != 1 or proof.get('kind') != 'read-only-pre-dispatch-versus-native-INI-baseline-review'
            or proof.get('qualificationId') != plan['id'] or proof.get('runId') != run.name
            or state.get('id') != run.name or result_path != run / 'result.json'
            or state.get('order', {}).get('id') != 'qualification-' + plan['id']
            or any(state.get('configuration', {}).get(key) != value for key, value in plan['configuration'].items())
            or set(state.get('configuration', {})) - set(plan['configuration']) - {'fixture_dir', 'collected_files', 'subject_state_bindings'}
            or plan['configuration'].get('game_edition') != 'se'
            or state.get('result') != 'failed' or result.get('result') != 'failed'
            or state.get('done') is not True or state.get('restored') is not True or state.get('restoreErrors')
            or result.get('restored') is not True or result.get('restoreErrors')
            or state.get('collectionComplete') is not True or state.get('collectionErrors')
            or m.Polygon.native_game_starts(state) != 1):
        raise ValueError('Exact ended failed single-start SE managed-MO2 boundary required')
    termination = state.get('gameTermination', {})
    if (termination.get('kind') != 'abnormal_exit' or termination.get('game') != state.get('game')
            or termination.get('identityVerified') is not True or termination.get('ownQuitRequest') is not True
            or termination.get('forcedGameStop') is not False or termination.get('exitCode') != 0xC0000005):
        raise ValueError('Original owned abnormal-exit failure must remain intact')
    artifacts = {}
    for item in proof.get('artifacts', []):
        path = _absolute(item['path'])
        if path in artifacts:
            raise ValueError('Duplicate managed-MO2 proof artifact')
        artifacts[path] = item
    for path in (Path(plan_path), state_path, result_path, Path(review['worker']['path']), Path(review['childExit']['path'])):
        if path not in artifacts:
            raise ValueError('Managed-MO2 proof omits exact original artifacts')
        read_pin(artifacts[path])
    ini = _absolute(plan['configuration']['mo2_ini'])
    originals = [pin for pin in plan['pins'] if Path(pin['path']) == ini]
    if len(originals) != 1:
        raise ValueError('Exactly one original configured MO2 INI pin required')
    original = originals[0]
    boundaries = proof['baselineBoundaries']
    declared = boundaries['immutableQualificationPin']
    if Path(declared['path']) != ini or declared['sha256'] != original['sha256']:
        raise ValueError('Managed-MO2 proof must retain original registration pin')
    original_path, original_raw = read_pin(declared['originalByteCopyAvailable'])
    if hashlib.sha256(original_raw).hexdigest() != original['sha256']:
        raise ValueError('Original registration INI copy differs')
    origin_state_path = original_path.parent.parent / 'state.json'
    if origin_state_path not in artifacts:
        raise ValueError('Retained original-copy snapshot provenance required')
    _, origin_raw = read_pin(artifacts[origin_state_path])
    origin_state = document(origin_raw)
    if len([s for s in origin_state.get('snapshots', []) if Path(s['path']) == ini
            and s.get('exists') is True and Path(s['backup']) == original_path and s['sha256'] == original['sha256']]) != 1:
        raise ValueError('Original byte-copy provenance differs from retained snapshot')
    snapshots = state.get('snapshots', [])
    if not 1 <= len(snapshots) <= 4096 or proof['nativeCompletion'].get('snapshotCountRehashed') != len(snapshots):
        raise ValueError('Complete finite native restoration inventory required')
    seen, ini_snapshot = set(), []
    for index, snapshot in enumerate(snapshots):
        path = _absolute(snapshot['path'])
        if path in seen or type(snapshot.get('exists')) is not bool:
            raise ValueError('Ambiguous native restoration snapshot')
        seen.add(path)
        if snapshot['exists']:
            backup = _absolute(snapshot['backup'])
            if (backup != run / 'backups' / str(index) or _hash(backup) != snapshot['sha256']
                    or _hash(path) != snapshot['sha256']):
                raise ValueError('Native snapshot backup/current restoration differs')
        elif path.exists():
            raise ValueError('Native missing-file restoration differs')
        if path == ini:
            ini_snapshot.append(snapshot)
    if len(ini_snapshot) != 1 or ini_snapshot[0].get('exists') is not True:
        raise ValueError('Exact configured INI native snapshot required')
    snapshot = ini_snapshot[0]
    native = boundaries['nativeSnapshotAfterIdleManagerClose']
    if native.get('snapshot') != snapshot or Path(native['backup']['path']) != Path(snapshot['backup']):
        raise ValueError('Managed-MO2 native boundary differs from original snapshot')
    native_path, native_raw = read_pin(native['backup'])
    if native['backup']['sha256'] != snapshot['sha256'] or snapshot['sha256'] == original['sha256']:
        raise ValueError('Distinct registered/native INI boundaries required')
    current_path, current_raw = read_pin(boundaries['currentINI'])
    if current_path != ini or current_raw != native_raw:
        raise ValueError('Restored configured INI differs from exact native baseline')
    changed = gui_delta(original_raw, native_raw)
    declared_changes = proof['safeINIComparison']['changedKeysOnlyValuesRedacted']
    if sorted((entry['section'], entry['key']) for entry in declared_changes) != changed:
        raise ValueError('Reviewed GUI-key delta differs from exact INI bytes')
    runner = Path(plan['executor']) / 'skyrim_autotest/runner.py'
    runner_pins = [pin for pin in plan['executorPins'] if Path(pin['path']) == runner]
    if len(runner_pins) != 1 or runner_pins[0]['sha256'] != RUNNER_SHA256 or state['executorHashes'].get('runner.py') != RUNNER_SHA256:
        raise ValueError('Only reviewed managed-close-before-snapshot runner is supported')
    runner_path, runner_raw = read_pin(runner_pins[0])
    idle = _identity(state['preflight']['idleMO2'])
    if Path(idle['path']) != Path(plan['configuration']['mo2_exe']) or state.get('borrowedMO2'):
        raise ValueError('Exact owned idle-manager close required')
    steps_path, steps_raw = read_pin(review['managerCloseSteps'])
    if steps_path != run / 'steps.jsonl':
        raise ValueError('Exact original manager-close steps evidence required')
    steps = [document(line) for line in steps_raw.splitlines() if line.strip()]
    closes = [step for step in steps if step.get('kind') == 'idle-mo2-graceful-close']
    if (len(closes) != 1 or closes[0].get('identity') != idle
            or closes[0].get('request', {}).get('requested') is not True
            or closes[0]['request'].get('systemCommand') is not True
            or not closes[0]['request'].get('windows')
            or any(window.get('accepted') is not True for window in closes[0]['request']['windows'])):
        raise ValueError('Matching original graceful-manager-close receipt required')
    return {'ini': ini, 'original': original, 'native': {'path': str(ini), 'sha256': snapshot['sha256']},
            'changedGuiKeys': [{'section': section, 'key': key} for section, key in changed],
            'proofPath': proof_path, 'paths': [proof_path, steps_path],
            'frozen': {'registration-ModOrganizer.ini': original_raw, 'native-ModOrganizer.ini': native_raw,
                       'registration-ini-origin-state.json': origin_raw, 'executed-runner.py': runner_raw},
            'writerAttribution': 'individual_key_writer_and_time_not_attested',
            'globalWriteFreeClaim': False, 'snapshotCount': len(snapshots)}

"""Explicit reconciliation of one known, pinned missing-loader preflight refusal.

No runner recovery, launch, queue dispatch or notification is called here. Empty
run directories alone are never evidence of zero starts or unchanged installation.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import stat
import sys

from qualification import inventory


# The reviewed 0.3.1 candidate: missing-loader check precedes run-state creation
# and setup. Changing this allowlist is a separate source/control-flow review.
SUPPORTED_RUNNER_SHA256 = '36605b612f5de4f94546b691818e6e8cadf9638bdebd013af320110a48a803ab'
SUPPORTED_DASHBOARD = {'polygon.py': 'a0e7f8fb2da8140cebef4bb33f3c5ea68273891f85f3d123562566123cb2c551',
                       'qualification.py': 'c9251b27a33f1d2cf8c5e36ea9573dcc41f07729eba55713f7b6efcf1470006f'}
SUPPORTED_CANDIDATE_INVENTORY = 'da99b03e94b26020057236fb13e15aac1b7417b6e6070a5eb5d991a274a73b62'
SUPPORTED_DASHBOARD_INVENTORY = 'e7921ba1fa723353acffde0dc5bd9d3956b2875e3ee097ea84521c914a168e23'
SUPPORTED_CLI_SHA256 = 'f390ada90b67fa1b9e8ace9f966b5c5ab0dac5d70984cbe15ecba4291d3cb78e'
SOURCE_PREFIX = [
    'original polygon.main dispatches _execute-qualification',
    'original child_qualification verifies pins, records worker and reads source profile',
    'original child_qualification records admission and invokes pinned runner.run',
    'pinned runner.run validates and recover has no native work',
    'pinned runner.run acquires native mutex and calls preflight before run-state creation',
    'pinned preflight required-file loop raises missing sksevr_loader.exe before setup',
    'original polygon.main emits only the refusal JSON and child exits 2',
]
MAX_FILES = 100000
MAX_SETTINGS_JSON = 1024 * 1024


def _api():
    import polygon
    return polygon


def _absolute(value):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError('Explicit absolute evidence/scope path required')
    path = Path(os.path.abspath(value))
    for item in (path, *path.parents):
        try:
            metadata = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Evidence and protected scopes cannot contain links/reparse points')
    return path


def _hash(path):
    path = _absolute(str(path))
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = os.fstat(stream.fileno())
    stamp = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if stamp(before) != stamp(after) or stamp(after) != stamp(path.stat()):
        raise ValueError('Evidence changed while hashing')
    return digest


def _pin(value, expected=None):
    m = _api()
    if type(value) is not dict or set(value) != {'path', 'sha256'}:
        raise ValueError('Exact path/SHA256 evidence pin required')
    path = _absolute(value['path'])
    if expected is not None and path != Path(expected).absolute():
        raise ValueError('Evidence pin points outside the exact qualification artifact')
    if not m.SHA.fullmatch(value.get('sha256', '')) or _hash(path) != value['sha256']:
        raise ValueError('Evidence pin mismatch: ' + str(path))
    return path


def protected_inventory(path, *, fresh=False):
    """Read-only full inventory; operators must retain a real pre-dispatch baseline."""
    path = _absolute(str(path))
    if not path.exists():
        return {'path': str(path), 'kind': 'missing', 'files': [], 'directories': []}
    paths = []
    for item in ([path] if path.is_file() else path.rglob('*')):
        _absolute(str(item))
        if len(paths) >= MAX_FILES:
            raise ValueError('Protected inventory exceeds bounded entry count')
        paths.append(item)
    paths.sort()
    files = []
    directories = []
    for item in paths:
        _absolute(str(item))
        if item.is_file():
            if len(files) >= MAX_FILES:
                raise ValueError('Protected inventory exceeds bounded file count')
            metadata = item.stat()
            row = {'path': '.' if item == path else item.relative_to(path).as_posix(),
                   'size': metadata.st_size}
            if fresh and item.suffix.lower() in ('.bsa', '.ba2'):
                row.update(sha256=None, hashBasis='bulk_archive_metadata_only_fresh_safety')
            else:
                row['sha256'] = _hash(item)
            if fresh:
                row['identity'] = {'device': metadata.st_dev, 'inode': metadata.st_ino,
                                   'hardlinks': metadata.st_nlink}
                row['observedMetadata'] = {'mtimeNs': metadata.st_mtime_ns, 'ctimeNs': metadata.st_ctime_ns}
            files.append(row)
        elif item.is_dir():
            directories.append(item.relative_to(path).as_posix())
        else:
            raise ValueError('Unsupported protected filesystem object')
    return {'path': str(path), 'kind': 'file' if path.is_file() else 'directory',
            'files': files, 'directories': directories}


def protected_scopes(config, profile, original_saves):
    """Complete declared installation/profile/settings/overwrite/save roots."""
    result = {'profile': str(_absolute(config['profiles']) / profile),
              'mo2Settings': str(_absolute(config['mo2_ini'])),
              'installation': str(_absolute(config['game'])),
              'overwrite': str(_absolute(config['overwrite'])),
              'originalSaves': str(_absolute(original_saves))}
    for key in ('openvr_paths', 'root_builder_data', 'bridge_token'):
        if config.get(key):
            result[key] = str(_absolute(config[key]))
    for index, path in enumerate(config.get('extra_files', [])):
        result['extraFile' + str(index)] = str(_absolute(path))
    return result


def implementation_pins():
    """The new recovery logic and its CLI integration are pinned separately."""
    m = _api()
    return [{'path': str(path), 'sha256': _hash(path)}
            for path in sorted((Path(__file__).resolve(), Path(m.__file__).resolve()))]


def source_inventory_digest(pins, root):
    rows = sorted([{'path': Path(pin['path']).relative_to(root).as_posix(), 'sha256': pin['sha256']}
                   for pin in pins], key=lambda row: row['path'])
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def fresh_safety_scopes(config, profile, original_saves):
    """Read-only relevant scopes; never walk/hash the bulk game Data tree."""
    scopes = protected_scopes(config, profile, original_saves)
    scopes.pop('installation')
    if not config.get('root_builder_data'):
        mo2 = _absolute(config.get('mo2') or str(_absolute(config['mo2_exe']).parent))
        scopes['root_builder_data'] = str(mo2 / 'plugins/data/RootBuilder')
    if config.get('openvr_paths'):
        pointer = _bounded_settings_json(_absolute(config['openvr_paths']))
        paths = pointer.get('config')
        if type(paths) is not list or not 1 <= len(paths) <= 16:
            raise ValueError('OpenVR pointer requires bounded config directory list')
        for directory in paths:
            if type(directory) is not str or not 1 <= len(directory) <= 32767:
                raise ValueError('Invalid OpenVR config directory')
            _absolute(directory)
        settings = _absolute(str(_absolute(paths[0]) / 'steamvr.vrsettings'))
        if settings.exists():
            _bounded_settings_json(settings)
        scopes['steamvrSettings'] = str(settings)
    game = _absolute(config['game'])
    scopes.update(gameExecutable=str(game / 'SkyrimVR.exe'), loader=str(game / 'sksevr_loader.exe'))
    overwrite = _absolute(config['overwrite'])
    for index, plugin in enumerate(config.get('staged_plugins', [])):
        destination = _absolute(str(overwrite / plugin['destination']))
        if not destination.is_relative_to(overwrite):
            raise ValueError('Staged safety target escapes overwrite')
        scopes['stagedSource' + str(index)] = str(_absolute(plugin['source']))
        scopes['stagedTarget' + str(index)] = str(destination)
    return scopes


def _bounded_settings_json(path):
    """Strict bounded read only; pointer resolution never writes settings."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate settings JSON key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('Nonfinite settings JSON constant: ' + value)
    with _absolute(str(path)).open('rb') as stream:
        data = stream.read(MAX_SETTINGS_JSON + 1)
    if len(data) > MAX_SETTINGS_JSON:
        raise ValueError('Settings JSON exceeds bounded read size')
    try:
        value = json.loads(data.decode('utf-8-sig'), object_pairs_hook=unique, parse_constant=constant)
    except RecursionError:
        raise ValueError('Settings JSON nesting exceeds parser limit') from None
    if type(value) is not dict:
        raise ValueError('Settings JSON must be an object')
    return value


def _original_sources(plan, review, plan_path):
    m = _api()
    receipt_path = _pin(review['originalDashboardExport'])
    receipt = m.read(receipt_path)
    if (receipt.get('schemaVersion') != 1 or receipt.get('kind') != 'original-dashboard-source-export'
            or receipt.get('qualificationId') != plan['id'] or receipt.get('planSha256') != _hash(plan_path)):
        raise ValueError('Original Dashboard export must bind this exact frozen plan')
    originals = [pin for pin in plan['pins'] if Path(pin['path']).name == 'polygon.py']
    if len(originals) != 1:
        raise ValueError('Unique original Dashboard entrypoint pin required')
    original_root = Path(originals[0]['path']).parent
    expected = {pin['path']: pin['sha256'] for pin in plan['pins']
                if Path(pin['path']).parent == original_root and Path(pin['path']).suffix == '.py'}
    if any(expected.get(str(original_root / name)) != digest for name, digest in SUPPORTED_DASHBOARD.items()):
        raise ValueError('Original dispatch/control-flow source is not the exact reviewed implementation')
    rows = receipt.get('files', [])
    if (not rows or len(rows) != len(expected) or
            {row.get('originalPath'): row.get('sha256') for row in rows} != expected or
            len({row.get('exportPath') for row in rows}) != len(rows)):
        raise ValueError('Original Dashboard export inventory differs from original plan pins')
    for row in rows:
        if _hash(row['exportPath']) != row['sha256']:
            raise ValueError('Original Dashboard source export changed')
    # Only the reviewed CLI-routing file changed. Runtime helpers/mixins still
    # execute CURRENT files and must match every original current source pin.
    substituted = str(original_root / 'polygon.py')
    for pin in plan['pins']:
        if pin['path'] != substituted:
            _pin(pin)
    if inventory(plan['executor']) != plan['executorPins']:
        raise ValueError('Pinned candidate executor changed')
    if review.get('implementationPins') != implementation_pins():
        raise ValueError('New recovery implementation provenance mismatch')
    return [receipt_path, *[Path(row['exportPath']) for row in rows],
            *[Path(pin['path']) for pin in plan['pins'] if pin['path'] != substituted],
            *[Path(pin['path']) for pin in plan['executorPins']]]


def _prefix_proof(p, plan, review, worker, folder):
    """Source/command/receipt proof; current inventory never claims old equality."""
    m = _api()
    if (not {'executedControlFlowAudit', 'operatorExecutionReceipt', 'freshSafety'} <= set(review)
            or type(review.get('freshSafety')) is not dict or set(review['freshSafety']) != {'originalSavesRoot'}):
        raise ValueError('Complete source-prefix audit/receipt and explicit fresh safety scope required')
    if review.get('freshSafetyScopeReviewed') is not True or 'protectedBaseline' in review:
        raise ValueError('Explicit fresh-safety review required; do not relabel a current inventory as a baseline')
    candidate_digest = source_inventory_digest(plan['executorPins'], Path(plan['executor']))
    original_root = Path(next(pin['path'] for pin in plan['pins'] if Path(pin['path']).name == 'polygon.py')).parent
    dashboard_pins = [pin for pin in plan['pins'] if Path(pin['path']).parent == original_root and Path(pin['path']).suffix == '.py']
    dashboard_digest = source_inventory_digest(dashboard_pins, original_root)
    cli_digest = _hash(Path(plan['executor']) / 'skyrim_autotest/cli.py')
    if (candidate_digest != SUPPORTED_CANDIDATE_INVENTORY or dashboard_digest != SUPPORTED_DASHBOARD_INVENTORY
            or cli_digest != SUPPORTED_CLI_SHA256):
        raise ValueError('Entire candidate/CLI/original Dashboard is not the exact audited prefix implementation')
    audit_path = _pin(review['executedControlFlowAudit'])
    audit = m.read(audit_path)
    expected_command = [worker['path'], str(original_root / 'polygon.py'), '--root', str(p.root),
                        '_execute-qualification', plan['id']]
    flags = ('sourcePrefixReviewedWriteFree', 'noAlternateActionPath',
             'preExistingRecoveryWorkAbsent', 'noProtectedEnvironmentMutation', 'candidateRuntimePreviouslyUnused')
    host = p.host()
    if not host.get('runnerConfig'):
        raise ValueError('Known configured-host runtime required for the distinct unused-runtime proof')
    host_runtime = _absolute(m.read(_absolute(host['runnerConfig']))['runtime'])
    if _absolute(plan['configuration']['runtime']) == host_runtime:
        raise ValueError('Source-prefix proof requires a distinct previously unused candidate runtime')
    if (audit.get('schemaVersion') != 1 or audit.get('kind') != 'qualification-write-free-prefix-audit'
            or audit.get('qualificationId') != plan['id'] or any(audit.get(key) is not True for key in flags)
            or audit.get('planSha256') != review['plan']['sha256'] or audit.get('worker') != worker
            or audit.get('admission') != review['admission'] or audit.get('executedCommand') != expected_command
            or audit.get('commandEvidenceBasis') != 'pinned_dispatch_subprocess_argv_and_exact_child_exit'
            or audit.get('controlFlow') != SOURCE_PREFIX or audit.get('runnerSha256') != SUPPORTED_RUNNER_SHA256
            or audit.get('candidateCliSha256') != cli_digest or audit.get('candidateInventorySha256') != candidate_digest
            or audit.get('originalDashboardInventorySha256') != dashboard_digest
            or audit.get('candidateRuntime') != plan['configuration']['runtime']
            or audit.get('recoveryReasoning') != 'distinct_unused_candidate_runtime_and_recover_preserves_run_state_traces'
            or audit.get('evidenceSha256') != {key: pin['sha256'] for key, pin in review['evidence'].items()}):
        raise ValueError('Exact independently reviewed executed source/command/control-flow audit required')
    for key in ('verifiedBy', 'analysis'):
        m.required_string(audit, key)
    prep_path = _pin(review['operatorExecutionReceipt'])
    prep = m.read(prep_path)
    if (prep.get('schemaVersion') != 1 or prep.get('kind') != 'operator-preparation'
            or prep.get('id') != plan['id'] or prep.get('testingStarted') is not False
            or prep.get('actualGameStarts', 'missing') is not None or prep.get('executorExit') != {'returncode': 2}
            or prep.get('finding', {}).get('workerReceipt', {}).get('identity') != worker
            or prep.get('finding', {}).get('nativeRunStates') != []
            or prep.get('finding', {}).get('launchIntentExists') is not False):
        raise ValueError('Original unknown operator execution receipt must bind this worker/refusal, without rewriting its accounting')
    prep_pins = prep.get('evidence', [])
    for pin in prep_pins:
        _pin(pin)
    originals = {pin['path']: pin['sha256'] for pin in prep_pins}
    if any(originals.get(review['evidence'][name]['path']) != review['evidence'][name]['sha256']
           for name in ('worker', 'child-exit', 'executor', 'profile-selection')):
        raise ValueError('Original operator receipt does not bind complete child/worker/log/profile artifacts')
    scopes = fresh_safety_scopes(plan['configuration'], plan['orderData']['profile'], review['freshSafety']['originalSavesRoot'])
    if p.host().get('runnerConfig'):
        scopes['hostRunnerConfig'] = str(_absolute(p.host()['runnerConfig']))
    state = {'proofMode': 'executed-source-prefix',
             'noMutationProof': 'no_mutation_by_this_attempt_proven_by_executed_source',
             'originalGlobalStateComparison': 'not_attested',
             'commandEvidenceBasis': audit['commandEvidenceBasis'], 'executedCommand': expected_command,
             'freshSafetyInventory': {key: protected_inventory(path, fresh=True) for key, path in scopes.items()}}
    return state, [audit_path, prep_path, *[Path(pin['path']) for pin in prep_pins]]


def _guard_db(p, con, identity, admission):
    p.qualification_guard(con, identity)
    hold = con.execute('SELECT note FROM pipeline_holds WHERE id=?', ('qualification-' + identity,)).fetchone()
    if not hold or hold['note'] != 'Exclusive qualification lease; retain after completion until owner-reviewed clearance':
        raise ValueError('Only this unchanged routine qualification reservation can finish')
    if con.execute("SELECT id FROM qualifications WHERE id != ? AND status IN ('prepared','running')", (identity,)).fetchone():
        raise ValueError('Another qualification remains active')
    actual = con.execute('SELECT id,started FROM attempts WHERE id=?', ('qualification-' + identity,)).fetchone()
    if not actual or dict(actual) != admission:
        raise ValueError('Exact original admission required; do not delete or fabricate accounting')
    if (con.execute("SELECT j.id FROM jobs j JOIN released_orders r ON r.id=j.id WHERE j.status IN ('queued','running','waiting_player','session_waiting')").fetchone()
            or con.execute("SELECT id FROM jobs WHERE status IN ('queued','session_waiting') AND json_extract(request,'$.cycle') IS NOT NULL").fetchone()
            or con.execute("SELECT id FROM retry_attempts WHERE status='queued'").fetchone()
            or con.execute("SELECT id FROM game_sessions WHERE status='queued'").fetchone()):
        raise ValueError('Eligible/released old work would become runnable; retain own reservation')


def _runner(plan):
    sys.path.insert(0, plan['executor'])
    runner = importlib.import_module('skyrim_autotest.runner')
    if Path(runner.__file__).resolve() != Path(plan['executor']) / 'skyrim_autotest/runner.py':
        raise ValueError('Wrong candidate native observer imported')
    return runner


def _identity(value):
    if (type(value) is not dict or set(value) != {'pid', 'birth', 'path'}
            or type(value['pid']) is not int or value['pid'] <= 0
            or type(value['birth']) is not int or value['birth'] <= 0):
        raise ValueError('Exact worker PID/birth/path identity required')
    _absolute(value['path'])
    return value


def _fresh_native(runner, worker, config, profile):
    rows = runner.native.processes()
    if not isinstance(rows, list) or not rows:
        raise ValueError('Fresh native process inventory unavailable')
    if runner.native.alive(worker):
        raise ValueError('Exact qualification worker remains alive')
    if any(row.get('pid') == worker['pid'] for row in rows):
        actual = runner.native.identity(worker['pid'])
        if actual is None or actual == worker:
            raise ValueError('Worker identity is unknown or still present')
    if any(row.get('name', '').lower() in runner.GAME_NAMES | getattr(runner, 'VR_NAMES', set()) for row in rows):
        raise ValueError('Current game/loader/VR process retains reservation')
    managers = [row for row in rows if row.get('name', '').lower() == 'modorganizer.exe']
    if managers:
        if len(managers) != 1 or runner.native.identity(managers[0]['pid']) is None:
            raise ValueError('Active MO2 identity is unavailable or ambiguous')
        manager = runner.native.identity(managers[0]['pid'])
        if _absolute(manager['path']) != _absolute(config['mo2_exe']):
            raise ValueError('Active MO2 belongs to another installation')
        token = _absolute(config['bridge_token']).read_text().strip()
        session = runner.request(config['bridge_port'], 'session', token=token, timeout=3)
        session_keys = ('mo2Pid', 'serverBootId', 'instanceId', 'profilesPath')
        if (type(session.get('mo2Pid')) is not int or session['mo2Pid'] != manager['pid']
                or not isinstance(session.get('serverBootId'), str) or not session['serverBootId']
                or not isinstance(session.get('instanceId'), str) or not session['instanceId']
                or _absolute(session.get('profilesPath')) != _absolute(config['profiles'])):
            raise ValueError('Live MO2 bridge session PID/boot/instance/profiles path differs')
        ping = runner.request(config['bridge_port'], 'ping', token=token, timeout=3)
        if (ping.get('ok') is not True or ('busyKnown' in ping and ping['busyKnown'] is not True) or ping.get('mainThread') != 'ok'
                or 'busy' not in ping or not (ping['busy'] is None or ping['busy'] is False)):
            raise ValueError('Live MO2 bridge health/idleness is unavailable')
        if ping.get('profile') != profile:
            raise ValueError('Live active profile changed')
        if ping.get('game') != 'SkyrimVR' or _absolute(ping.get('modsPath')) != _absolute(config['mods']):
            raise ValueError('Live MO2 bridge game/mods path differs')
        procs = runner.request(config['bridge_port'], 'procs', token=token, timeout=3)
        if (type(procs) is not dict or 'busy' not in procs
                or not (procs['busy'] is None or procs['busy'] is False)
                or type(procs.get('running')) is not int or procs['running'] != 0
                or type(procs.get('launchedByMO2')) is not list or procs['launchedByMO2'] != []
                or procs.get('serverBootId') != session['serverBootId']):
            raise ValueError('Live MO2 has active/unknown writer processes or changed boot')
        after = runner.request(config['bridge_port'], 'session', token=token, timeout=3)
        if any(after.get(key) != session.get(key) for key in session_keys):
            raise ValueError('Live MO2 bridge session changed during observation')
        if runner.native.identity(managers[0]['pid']) != manager:
            raise ValueError('Active MO2 identity changed during observation')
    final_rows = runner.native.processes()
    if not isinstance(final_rows, list) or not final_rows or runner.native.alive(worker):
        raise ValueError('Final native inventory/worker safety is unavailable')
    if any(row.get('name', '').lower() in runner.GAME_NAMES | getattr(runner, 'VR_NAMES', set()) for row in final_rows):
        raise ValueError('A game/loader/VR process appeared during native observation')
    if any(row.get('pid') == worker['pid'] for row in final_rows):
        actual = runner.native.identity(worker['pid'])
        if actual is None or actual == worker:
            raise ValueError('Final worker identity is unknown or present')
    if [row.get('pid') for row in final_rows if row.get('name', '').lower() == 'modorganizer.exe'] != [row['pid'] for row in managers]:
        raise ValueError('MO2 process ownership changed during observation')
    if managers and runner.native.identity(manager['pid']) != manager:
        raise ValueError('Final MO2 identity changed')
    result = {'worker': worker, 'exactWorkerAlive': False, 'processes': final_rows, 'processesBefore': rows,
              'profile': profile, 'profileSource': 'live-bridge' if managers else 'pinned-saved-settings'}
    if managers:
        result['mo2Bridge'] = {'manager': manager, 'before': {key: session[key] for key in session_keys},
                              'after': {key: after[key] for key in session_keys},
                              'ping': {key: ping.get(key) for key in ('profile', 'game', 'modsPath', 'ok', 'busyKnown', 'mainThread', 'busy')},
                              'busyKnownAvailability': 'advertised' if 'busyKnown' in ping else 'not_advertised',
                              'procs': procs}
    return result


def _runtime_checks(plan, host):
    m = _api()
    candidate = _absolute(plan['configuration']['runtime'])
    runs = candidate / 'runs'
    _absolute(str(runs))
    if runs.exists() and any(runs.iterdir()):
        raise ValueError('Any candidate native run trace requires ordinary recovery/review')
    result = {'candidateRuntime': str(candidate), 'candidateRunsDirectoryExists': runs.exists(), 'hostStates': []}
    if host.get('runnerConfig'):
        config_path = _absolute(host['runnerConfig'])
        host_runtime = _absolute(m.read(config_path)['runtime'])
        for state_path in sorted((host_runtime / 'runs').glob('*/state.json')):
            _absolute(str(state_path))
            state = m.read(state_path)
            if state.get('done') is not True or state.get('restored') is not True or state.get('restoreErrors'):
                raise ValueError('Host native session/restoration is unfinished or uncertain')
            result['hostStates'].append({'path': str(state_path), 'sha256': _hash(state_path)})
    return result


def _checked(p, identity, review_path, con, allowed_status):
    m = _api()
    review_path = _absolute(str(review_path))
    review = m.read(review_path)
    required = ('sourceFlowReviewed', 'zeroStartsReviewed', 'noMutationReviewed', 'protectedStateReviewed',
                'originalAuthorityReviewed', 'uncertaintyResolved', 'reservationIsOwnRoutine')
    if (review.get('schemaVersion') != 1 or review.get('kind') != 'qualification-pre-native-review'
            or review.get('qualificationId') != identity or any(review.get(key) is not True for key in required)):
        raise ValueError('Explicit exact pre-native operator review required')
    for key in ('verifiedBy', 'summary'):
        m.required_string(review, key)
    m.owner_evidence(review, review_path, require_deadline=False)
    row = dict(con.execute('SELECT * FROM qualifications WHERE id=?', (identity,)).fetchone() or {})
    if row.get('status') not in allowed_status:
        raise ValueError('Qualification status cannot be reconciled/finished')
    if row['status'] == 'running' and row.get('packet') is not None:
        raise ValueError('Existing qualification packet cannot be replaced by pre-native reconciliation')
    plan = json.loads(row['request'])
    folder = p.local / 'qualifications' / identity
    plan_path = _pin(review['plan'], folder / 'plan.json')
    if m.read(plan_path) != plan:
        raise ValueError('Frozen plan and durable request differ')
    retained = _original_sources(plan, review, plan_path)
    runner_path = Path(plan['executor']) / 'skyrim_autotest/runner.py'
    if (_hash(runner_path) != SUPPORTED_RUNNER_SHA256 or
            review.get('sourceFlow') != {'runnerSha256': SUPPORTED_RUNNER_SHA256,
                'case': 'missing-sksevr-loader-before-native-state-and-setup'}):
        raise ValueError('Only the reviewed exact missing-loader candidate source is supported')
    config = plan['configuration']
    if config.get('game_edition', 'vr') != 'vr':
        raise ValueError('Only the known VR loader refusal is supported')
    artifact_names = {'worker', 'child-exit', 'dispatch-intent', 'executor', 'profile-selection'}
    if set(review.get('evidence', {})) != artifact_names:
        raise ValueError('Complete original refusal evidence required')
    for name in artifact_names:
        path = folder / (name + ('.log' if name == 'executor' else '.json'))
        _pin(review['evidence'][name], path)
    if m.read(folder / 'child-exit.json') != {'returncode': 2}:
        raise ValueError('Exact non-timeout preflight refusal exit required')
    loader = _absolute(config['game']) / 'sksevr_loader.exe'
    try:
        error = json.loads((folder / 'executor.log').read_text(encoding='utf-8').strip())
    except ValueError:
        raise ValueError('Complete log is not the exact known preflight refusal') from None
    if error != {'error': 'Missing required file: ' + str(loader)}:
        raise ValueError('Only the exact missing-loader preflight error is supported')
    if (folder / 'launch-intent.json').exists():
        raise ValueError('A launch intent prevents pre-native reconciliation')
    dispatch = m.read(folder / 'dispatch-intent.json')
    if (dispatch.get('id') != identity or type(dispatch.get('at')) not in (float, int)
            or not math.isfinite(dispatch['at']) or type(dispatch.get('expires')) not in (float, int)
            or not math.isfinite(dispatch['expires']) or dispatch['expires'] != row['expires']):
        raise ValueError('Exact dispatch intent required')
    _guard_db(p, con, identity, review.get('admission'))
    if type(review['admission']['started']) not in (float, int) or review['admission']['started'] < dispatch['at']:
        raise ValueError('Admission chronology differs')
    worker = _identity(m.read(folder / 'worker.json').get('identity'))
    selection = m.read(folder / 'profile-selection.json')
    if selection != {'sourceProfile': plan['orderData']['profile'], 'selection': {'mode': 'active'},
                      'copyOwner': 'skyrim-autotest', 'originalProfilePreserved': True}:
        raise ValueError('Original active profile provenance differs')
    proof_mode = review.get('proofMode', 'historical-protected-baseline')
    if proof_mode == 'executed-source-prefix':
        state_proof, proof_files = _prefix_proof(p, plan, review, worker, folder)
    elif proof_mode == 'historical-protected-baseline':
        baseline_path = _pin(review['protectedBaseline'])
        baseline = m.read(baseline_path)
        captured = baseline.get('capturedAt')
        if (baseline.get('schemaVersion') != 1 or baseline.get('kind') != 'qualification-pre-native-baseline'
                or baseline.get('qualificationId') != identity or type(captured) not in (float, int)
                or not math.isfinite(captured) or captured > min(dispatch['at'], review['admission']['started'])):
            raise ValueError('A real independently reviewed pre-dispatch protected baseline is required')
        scopes = protected_scopes(config, plan['orderData']['profile'], baseline.get('originalSavesRoot'))
        if p.host().get('runnerConfig'):
            scopes['hostRunnerConfig'] = str(_absolute(p.host()['runnerConfig']))
        current = {key: protected_inventory(path) for key, path in scopes.items()}
        if baseline.get('snapshots') != current:
            raise ValueError('Protected profile/settings/saves/installation baseline changed or incomplete')
        state_proof = {'proofMode': proof_mode, 'noMutationProof': 'reviewed_source_and_historical_protected_baseline',
                       'originalGlobalStateComparison': 'attested_against_predispatch_protected_baseline'}
        proof_files = [baseline_path]
    else:
        raise ValueError('Unsupported pre-native proof mode')
    # Check saved selection here; the mutex-held native guard also checks the
    # live bridge when MO2 is open. Neither read changes the active profile.
    import re
    selections = re.findall(r'(?m)^selected_profile=(.*?)\r?$', Path(config['mo2_ini']).read_text(encoding='utf-8-sig'))
    selected = selections[0] if len(selections) == 1 else ''
    if selected.startswith('@ByteArray(') and selected.endswith(')'):
        selected = selected[len('@ByteArray('):-1]
    if selected.startswith('@') or '\\' in selected or selected != plan['orderData']['profile']:
        raise ValueError('Saved active profile is unavailable or changed')
    runtimes = _runtime_checks(plan, p.host())
    runtimes['stateProof'] = state_proof
    evidence = [plan_path, review_path, *proof_files, Path(review['ownerAuthorization']['path']), *retained]
    evidence += [Path(pin['path']) for pin in review['evidence'].values()]
    evidence += [Path(pin['path']) for pin in review['implementationPins']]
    pins = [{'path': str(path), 'sha256': _hash(path)} for path in sorted(set(evidence))]
    return row, plan, review, worker, runtimes, pins


def _table(con):
    con.execute('CREATE TABLE IF NOT EXISTS qualification_pre_native (id TEXT PRIMARY KEY, review TEXT NOT NULL, packet TEXT NOT NULL, finish TEXT)')


def reconcile(p, identity, review_path):
    """Record reviewed zero-start evidence; keep the exclusive reservation held."""
    m = _api()
    review_path = Path(review_path).absolute()
    # Preliminary verification pins the candidate before importing its observer.
    with p.connect() as con:
        row, plan, review, worker, _, _ = _checked(p, identity, review_path, con, {'running'})
    runner = _runner(plan)
    with runner.native.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        row, plan, review, worker, runtimes, pins = _checked(p, identity, review_path, con, {'running'})
        native = _fresh_native(runner, worker, plan['configuration'], plan['orderData']['profile'])
        _table(con)
        packet = {'schemaVersion': 1, 'kind': 'qualification-pre-native-result', 'id': identity,
                  'orderId': plan['orderData']['id'], 'executionOutcome': 'preflight_refused',
                  'testingStarted': False, 'actualGameStarts': 0, 'runDirectory': None, 'restored': None,
                  'restorationBasis': 'not_required_no_mutation', 'collectionFinished': True,
                  'restoration': 'not_required_no_mutation',
                  'noMutationProof': runtimes['stateProof']['noMutationProof'],
                  'originalGlobalStateComparison': runtimes['stateProof']['originalGlobalStateComparison'],
                  'globalProviderQualified': False, 'reviewSha256': _hash(review_path),
                  'cumulativeActualGameStartsBefore': plan['cumulativeActualGameStartsBefore'],
                  'cumulativeActualGameStartsAfter': plan['cumulativeActualGameStartsBefore'],
                  'runtimeEvidence': runtimes, 'nativeEvidence': native, 'files': pins}
        target = p.local / 'qualifications' / identity / 'pre-native-packet.json'
        if target.exists():
            raise ValueError('Unregistered prior reconciliation artifact requires review')
        packet['nativeEvidence'] = _fresh_native(runner, worker, plan['configuration'], plan['orderData']['profile'])
        m.write(target, packet)
        reference = json.dumps({'path': str(target), 'sha256': _hash(target)}, sort_keys=True)
        con.execute('INSERT INTO qualification_pre_native VALUES(?,?,?,NULL)',
                    (identity, json.dumps({'path': str(Path(review_path).absolute()), 'sha256': _hash(review_path)}, sort_keys=True), reference))
        con.execute("UPDATE qualifications SET status='recorded',packet=? WHERE id=?", (reference, identity))
        p.event(con, identity, 'qualification_pre_native_recorded', 'Reviewed zero; own reservation remains held; original admission retained')
    return packet


def finish(p, identity, finish_path):
    """Explicitly finish only the reviewed zero-start reservation; never run work."""
    m = _api()
    finish_path = _absolute(str(Path(finish_path).absolute()))
    review = m.read(finish_path)
    if (review.get('schemaVersion') != 1 or review.get('kind') != 'qualification-pre-native-finish'
            or review.get('qualificationId') != identity or
            any(review.get(key) is not True for key in ('reconciliationReviewed', 'zeroStartsReviewed', 'noMutationReviewed', 'finishOwnReservation'))):
        raise ValueError('Explicit exact pre-native reservation finish review required')
    for key in ('verifiedBy', 'summary'):
        m.required_string(review, key)
    canonical = json.dumps({'path': str(finish_path), 'sha256': _hash(finish_path)}, sort_keys=True)
    with p.connect() as con:
        if not con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='qualification_pre_native'").fetchone():
            raise ValueError('No authoritative pre-native reconciliation exists')
        prior = con.execute('SELECT * FROM qualification_pre_native WHERE id=?', (identity,)).fetchone()
        if not prior:
            raise ValueError('No authoritative pre-native reconciliation exists')
        prior = dict(prior)
        if prior['finish']:
            completed = json.loads(prior['finish'])
            if completed['review'] != json.loads(canonical):
                raise ValueError('Pre-native finish review is immutable')
            _pin(completed['receipt'])
            _pin(json.loads(prior['review']))
            retained_packet = m.read(_pin(json.loads(prior['packet'])))
            for pin in retained_packet['files']:
                _pin(pin)
            return {'id': identity, 'status': 'released', 'duplicate': True, 'actualGameStarts': 0}
    reference = json.loads(prior['packet'])
    packet_path = _pin(reference)
    packet = m.read(packet_path)
    if review.get('packetSha256') != reference['sha256'] or review.get('reconciliationReviewSha256') != json.loads(prior['review'])['sha256']:
        raise ValueError('Finish must bind the exact authoritative packet and reconciliation review')
    original_review_path = _pin(json.loads(prior['review']))
    with p.connect() as con:
        _, plan, _, worker, _, _ = _checked(p, identity, original_review_path, con, {'recorded'})
    runner = _runner(plan)
    with runner.native.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        row, _, _, worker, runtimes, pins = _checked(p, identity, original_review_path, con, {'recorded'})
        if row['packet'] != prior['packet'] or _hash(packet_path) != reference['sha256']:
            raise ValueError('Authoritative reconciliation changed')
        if (packet.get('actualGameStarts') != 0 or packet.get('testingStarted') is not False
                or packet.get('restorationBasis') != 'not_required_no_mutation' or packet.get('restored') is not None
                or packet.get('files') != pins or packet.get('runtimeEvidence') != runtimes):
            raise ValueError('Reconciled evidence changed or contains uncertain/native execution')
        if _hash(finish_path) != json.loads(canonical)['sha256']:
            raise ValueError('Finish review changed')
        native = _fresh_native(runner, worker, plan['configuration'], plan['orderData']['profile'])
        receipt_path = p.local / 'qualifications' / identity / 'pre-native-finish.json'
        if receipt_path.exists():
            raise ValueError('Unregistered prior finish artifact requires review')
        receipt = {'schemaVersion': 1, 'kind': 'qualification-pre-native-finish-receipt',
                   'qualificationId': identity, 'review': json.loads(canonical), 'packet': reference,
                   'actualGameStarts': 0, 'restorationBasis': 'not_required_no_mutation',
                   'restoration': 'not_required_no_mutation',
                   'noMutationProof': runtimes['stateProof']['noMutationProof'],
                   'originalGlobalStateComparison': runtimes['stateProof']['originalGlobalStateComparison'],
                   'nativeEvidence': native, 'runtimeEvidence': runtimes, 'evidence': pins,
                   'releasedHold': 'qualification-' + identity, 'originalAdmissionRetained': True}
        m.write(receipt_path, receipt)
        retained_finish = json.dumps({'review': json.loads(canonical),
            'receipt': {'path': str(receipt_path), 'sha256': _hash(receipt_path)}}, sort_keys=True)
        con.execute('DELETE FROM pipeline_holds WHERE id=?', ('qualification-' + identity,))
        con.execute("UPDATE qualifications SET status='released' WHERE id=?", (identity,))
        con.execute('UPDATE qualification_pre_native SET finish=? WHERE id=? AND finish IS NULL', (retained_finish, identity))
        p.event(con, identity, 'qualification_pre_native_released', canonical)
    return {'id': identity, 'status': 'released', 'actualGameStarts': 0, 'testingStarted': False,
            'restorationBasis': 'not_required_no_mutation', 'globalProviderQualified': False}

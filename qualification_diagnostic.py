"""Record ended, restored, uncertain qualification evidence; never clear its hold."""
from __future__ import annotations

import importlib.util
import json
import ntpath
from pathlib import Path
import re
import stat

from qualification import inventory
from qualification_pre_native import _absolute, _hash, _identity, _pin


# Strict full-snapshot enumeration fixed in executor 0.3.5/0.3.6. Import only this
# stdlib observer, never the original candidate runner or its recovery/setup.
OBSERVER_SHA256 = 'ce57c40710921be46901daf19aa58f75c5f3990e24bc7899797ac9aa07182da6'
GAME_NAMES = {'skyrimvr.exe', 'skyrimse.exe', 'sksevr_loader.exe', 'skse64_loader.exe'}


def _api():
    import polygon
    return polygon


def implementation_pins():
    return [{'path': str(p), 'sha256': _hash(p)}
            for p in sorted(_api().HERE.glob('*.py'))]


def _sources(plan, review, plan_path):
    m = _api()
    receipt_path = _pin(review['originalDashboardExport'])
    receipt = m.read(receipt_path)
    if (receipt.get('schemaVersion') != 1 or receipt.get('kind') != 'original-dashboard-source-export'
            or receipt.get('qualificationId') != plan['id']
            or receipt.get('planSha256') != _hash(plan_path)):
        raise ValueError('Original source export must bind the exact frozen plan')
    entrypoints = [p for p in plan['pins'] if Path(p['path']).name == 'polygon.py']
    execution_evidence = None
    if len(entrypoints) == 1:
        root = Path(entrypoints[0]['path']).parent
    else:
        # A plan can retain earlier Dashboard exports as accounting evidence.
        # Select the actually executed root only from the exact original late
        # companion-gate traceback, never merely from a reviewer's path choice.
        root = _absolute(receipt.get('executedDashboardRoot', ''))
        execution_evidence = _pin(receipt.get('executionEvidence'), plan_path.parent / 'subject-companion' / 'dispatch.json')
        dispatch = m.read(execution_evidence)
        worker = m.read(plan_path.parent / 'worker.json').get('identity')
        message = 'Qualification pin changed: ' + plan['configuration']['mo2_ini']
        details = dispatch.get('errorDetails', {})
        frames = re.findall(r'File "([^"]+)", line [0-9]+, in ([^\r\n]+)', details.get('traceback', ''))
        expected_frames = [(str(root / 'qualification_companion.py'), 'companion'),
                           (str(root / 'qualification.py'), 'qualification_verify')]
        if (len(entrypoints) < 2 or not any(Path(pin['path']).parent == root for pin in entrypoints)
                or set(dispatch) != {'schemaVersion', 'orderId', 'qualificationId', 'worker', 'error', 'errorDetails'}
                or dispatch.get('schemaVersion') != 1 or dispatch.get('qualificationId') != plan['id']
                or dispatch.get('orderId') != 'qualification-' + plan['id'] or dispatch.get('worker') != worker
                or dispatch.get('error') != 'ValueError: ' + message
                or details.get('operation') != 'qualification-companion'
                or [(ntpath.normcase(ntpath.normpath(path)), function) for path, function in frames]
                   != [(ntpath.normcase(ntpath.normpath(path)), function) for path, function in expected_frames]
                or not details.get('traceback', '').rstrip().endswith('ValueError: ' + message)):
            raise ValueError('Exact executed late companion-gate source evidence required')
    expected = {p['path']: p['sha256'] for p in plan['pins']
                if Path(p['path']).parent == root and Path(p['path']).suffix == '.py'}
    rows = receipt.get('files', [])
    if (not rows or len(rows) != len(expected)
            or {r.get('originalPath'): r.get('sha256') for r in rows} != expected
            or len({r.get('exportPath') for r in rows}) != len(rows)):
        raise ValueError('Complete original source export inventory required')
    retained = [receipt_path]
    if execution_evidence is not None:
        retained.append(execution_evidence)
    for row in rows:
        exported = _pin({'path': row['exportPath'], 'sha256': row['sha256']})
        retained.append(exported)
    # Only CLI integration and the explicit diagnostic-release refusal changed.
    # Every original source remains independently preserved in the export above.
    for pin in plan['pins']:
        source = Path(pin['path'])
        is_source = source.parent == root and source.suffix == '.py'
        if not (is_source and source.name in ('polygon.py', 'qualification.py')):
            _pin(pin)
        if not is_source:
            retained.append(source)
    if inventory(plan['executor']) != plan['executorPins']:
        raise ValueError('Original candidate inventory changed')
    if review.get('implementationPins') != implementation_pins():
        raise ValueError('Current diagnostic implementation closure differs')
    retained.extend(Path(p['path']) for p in plan['executorPins'])
    return retained


def _observer(pin):
    path = _pin(pin)
    if pin['sha256'] != OBSERVER_SHA256:
        raise ValueError('Exact reviewed strict read-only native observer required')
    spec = importlib.util.spec_from_file_location('_polygon_diagnostic_native', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _native(observer, identities):
    rows = observer.processes()
    if type(rows) is not list or not rows:
        raise ValueError('Complete native process inventory unavailable')
    if any(type(r) is not dict or type(r.get('pid')) is not int
           or not isinstance(r.get('name'), str) for r in rows):
        raise ValueError('Malformed native process inventory')
    if any(r['name'].lower() in GAME_NAMES for r in rows):
        raise ValueError('Current game/loader blocks diagnostic finalization')
    for ident in identities:
        if observer.alive(ident):
            raise ValueError('Worker/owned process remains alive')
        if any(r['pid'] == ident['pid'] for r in rows):
            actual = observer.identity(ident['pid'])
            if actual is None or actual == ident:
                raise ValueError('Worker/owned process identity unknown or still present')
    return {'processCount': len(rows), 'workerAndOwnedIdentitiesVerifiedDead': True}


def archive_inventory(archive):
    archive = _absolute(str(archive))
    if not archive.is_dir():
        raise ValueError('Profile archive missing')
    files, directories = [], []
    for path in sorted(archive.rglob('*')):
        _absolute(str(path))
        mode = path.lstat().st_mode
        if stat.S_ISREG(mode):
            files.append({'path': str(path), 'sha256': _hash(path)})
        elif stat.S_ISDIR(mode):
            directories.append(str(path))
        else:
            raise ValueError('Unsupported profile archive object')
    return files, directories


def verify_archive(packet):
    actual = archive_inventory(Path(packet['runDirectory']) / 'test-profile')
    if actual != (packet['profileArchivePins'], packet['profileArchiveDirectories']):
        raise ValueError('Diagnostic profile archive membership or bytes changed')


def _checked(p, identity, review_path, con):
    m = _api()
    row = con.execute('SELECT * FROM qualifications WHERE id=?', (identity,)).fetchone()
    if not row or row['status'] != 'running' or row['packet']:
        raise ValueError('Uncollected running qualification required')
    plan = json.loads(row['request'])
    folder = p.local / 'qualifications' / identity
    plan_path = folder / 'plan.json'
    if m.read(plan_path) != plan:
        raise ValueError('Original frozen plan differs')
    review = m.read(review_path)
    if (review.get('schemaVersion') != 1 or review.get('kind') != 'qualification-held-diagnostic-review'
            or review.get('qualificationId') != identity
            or any(review.get(k) is not True for k in ('nativeCompletionReviewed', 'trackedRestorationReviewed',
                      'archiveReviewed', 'uncertainAccountingReviewed', 'retainHold'))):
        raise ValueError('Explicit ended/restored/uncertain diagnostic review required')
    for key in ('verifiedBy', 'summary'):
        m.required_string(review, key)
    if not con.execute('SELECT id FROM pipeline_holds WHERE id=?', ('qualification-' + identity,)).fetchone():
        raise ValueError('Original qualification hold must remain')
    if p.qualification_busy(con) or con.execute(
            "SELECT id FROM qualifications WHERE id!=? AND status IN ('prepared','running')", (identity,)).fetchone():
        raise ValueError('Another active owner blocks diagnostic finalization')
    if not con.execute('SELECT id FROM attempts WHERE id=?', ('qualification-' + identity,)).fetchone():
        raise ValueError('Original native admission required')
    paths = _sources(plan, review, plan_path)
    child = _pin(review['childExit'], folder / 'child-exit.json')
    exit_record = m.read(child)
    if (type(exit_record.get('returncode')) is not int
            and exit_record.get('timeout') is not True and not exit_record.get('verifiedDeadWorker')):
        raise ValueError('Exact child completion evidence required')
    worker_path = _pin(review['worker'], folder / 'worker.json')
    worker = _identity(m.read(worker_path).get('identity'))
    runs = []
    runtimes = {Path(plan['configuration']['runtime'])}
    host = p.host()
    if host.get('runnerConfig'):
        runtimes.add(Path(m.read(host['runnerConfig'])['runtime']))
    state_paths = {x for runtime in runtimes for x in (runtime / 'runs').glob('*/state.json')}
    for state_path in sorted(state_paths):
        state = m.read(state_path)
        if state.get('done') is not True:
            raise ValueError('Unfinished native session blocks diagnostic finalization')
        if (state.get('order', {}).get('id') == 'qualification-' + identity
                and state_path.is_relative_to(Path(plan['configuration']['runtime']))):
            runs.append((state_path, state))
    if len(runs) != 1:
        raise ValueError('One exact admitted native state required')
    state_path, state = runs[0]
    _pin(review['state'], state_path)
    result_path = _pin(review['result'], state_path.parent / 'result.json')
    result = m.read(result_path)
    if (state.get('runner') != worker or state.get('done') is not True
            or state.get('restored') is not True or state.get('restoreErrors')
            or result.get('restored') is not True or result.get('restoreErrors')
            or result.get('id') != state.get('id') or state.get('id') != state_path.parent.name):
        raise ValueError('Exact native completion and tracked restoration required')
    archive = state_path.parent / 'test-profile'
    if (Path(state.get('profileArchive', '')).resolve() != archive.resolve() or not archive.is_dir()
            or not state.get('testProfile') or Path(state['testProfile']).exists()):
        raise ValueError('Tracked profile archive/removal unproven')
    archived, directories = archive_inventory(archive)
    if (not archived or review.get('profileArchivePins') != archived
            or review.get('profileArchiveDirectories') != directories):
        raise ValueError('Exact nonempty profile archive inventory required')
    observed = review.get('observedGameIdentities')
    if (type(observed) is not list or not observed or not review.get('accountingEvidence')
            or review.get('observedGamesReviewed') is not True):
        raise ValueError('Distinct observed game identities with pinned evidence required')
    games = [_identity(x) for x in observed]
    identities = [worker]
    for item in state.get('owned', []):
        ident = _identity(item.get('identity'))
        identities.append(ident)
        if item.get('role') == 'game':
            games.append(ident)
    if any(Path(x['path']).name.lower() not in {'skyrimvr.exe', 'skyrimse.exe'} for x in games):
        raise ValueError('Observed identity is not a game executable')
    unique = {}
    for game in games:
        key = (game['pid'], game['birth'])
        if (key in unique and ntpath.normcase(ntpath.normpath(unique[key]['path']))
                != ntpath.normcase(ntpath.normpath(game['path']))):
            raise ValueError('One physical PID/birth has conflicting executable paths')
        unique.setdefault(key, game)
    if len(unique) < 1:
        raise ValueError('Observed lower bound is not proven')
    if (type(review.get('observedMinimumActualGameStarts')) is not int
            or review['observedMinimumActualGameStarts'] != len(unique)):
        raise ValueError('Reviewed observed lower bound differs from distinct identities')
    evidence = [_pin(x) for x in review['accountingEvidence']]
    mapped = review.get('observedIdentityEvidence', [])
    if (type(mapped) is not list or len(mapped) != len(observed)
            or {json.dumps(x.get('identity'), sort_keys=True) for x in mapped}
               != {json.dumps(x, sort_keys=True) for x in observed}):
        raise ValueError('Exact independently reviewed identity/evidence mapping required')
    for row in mapped:
        if _pin(row.get('evidence')) not in evidence:
            raise ValueError('Identity evidence must be in pinned accounting evidence')
        m.required_string(row, 'locator')
    identities.extend(unique.values())
    if review.get('exactSingleStartReviewed') is not None:
        if (review['exactSingleStartReviewed'] is not True or len(unique) != 1
                or state.get('game') != next(iter(unique.values()))
                or p.native_game_starts(state) != 1
                or state.get('result') != 'failed' or result.get('result') != 'failed'
                or exit_record != {'returncode': 1}):
            raise ValueError('Exact single failed native start review differs')
    additional = review.get('additionalEvidencePins', [])
    if (type(additional) is not list or len(additional) > 100000
            or len({json.dumps(pin, sort_keys=True) for pin in additional}) != len(additional)):
        raise ValueError('Bounded unique supplemental raw evidence required')
    paths.extend(_pin(pin) for pin in additional)
    extra_identities = review.get('additionalDeadIdentities', [])
    if type(extra_identities) is not list or len(extra_identities) > 16:
        raise ValueError('Bounded additional exact process identities required')
    identities.extend(_identity(ident) for ident in extra_identities)
    paths.extend([plan_path, review_path, child, worker_path, state_path, result_path,
                  *evidence, *(Path(x['path']) for x in archived)])
    _pin(review['observer'])
    for directory in (folder, state_path.parent):
        paths.extend(x for x in directory.iterdir() if x.is_file()
                     and x.suffix in ('.json', '.jsonl', '.log')
                     and x.name not in ('packet.json', 'held-diagnostic.json'))
    paths.extend(Path(x['path']) for x in m.raw_evidence_pins(state_path.parent))
    files = [{'path': str(x), 'sha256': _hash(x)} for x in sorted(set(paths))]
    original_pins = {str(_absolute(pin['path'])): pin['sha256'] for pin in plan['pins']}
    if any(pin['path'] in original_pins and pin['sha256'] != original_pins[pin['path']] for pin in files):
        raise ValueError('Original diagnostic input changed during review')
    return plan, review, worker, identities, state_path, archived, list(unique.values()), files, directories


def record(p, identity, review_path):
    m = _api()
    review_path = _absolute(str(Path(review_path).absolute()))
    row = p.qualification_show(identity)
    if row['packet']:
        packet = p.qualification_collect(identity)  # rechecks packet/evidence hashes
        with p.connect() as con:
            held = con.execute('SELECT id FROM pipeline_holds WHERE id=?', ('qualification-' + identity,)).fetchone()
        if (packet.get('kind') != 'qualification-held-diagnostic'
                or row['status'] != 'recorded' or not held
                or packet.get('reviewPath') != str(review_path)
                or packet.get('reviewSha256') != _hash(review_path)):
            raise ValueError('Existing diagnostic review is immutable')
        return packet
    with p.connect() as con:
        checked = _checked(p, identity, review_path, con)
    observer = _observer(checked[1]['observer'])
    with observer.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        plan, review, worker, identities, state_path, archived, games, files, directories = _checked(p, identity, review_path, con)
        native = _native(observer, identities)
        packet = {'schemaVersion': 1, 'kind': 'qualification-held-diagnostic', 'id': identity,
                  'orderId': plan['orderData']['id'], 'sourceThreadId': plan['orderData']['sourceThreadId'],
                  'runDirectory': str(state_path.parent),
                  'executionOutcome': m.read(state_path.parent / 'result.json').get('result'),
                  'qualificationOutcome': 'unqualified', 'qualificationPassed': False,
                  'executionEnded': True, 'collectionFinished': True,
                  'restored': True, 'restorationScope': 'tracked_executor_domains_only',
                  'unownedWriteDomains': 'unresolved', 'actualGameStarts': None,
                  'cumulativeActualGameStartsBefore': plan['cumulativeActualGameStartsBefore'],
                  'cumulativeActualGameStartsAfter': None,
                  'observedMinimumActualGameStarts': len(games), 'observedGameIdentities': games,
                  'globalProviderQualified': False, 'holdRetained': True,
                  'reviewPath': str(review_path), 'reviewSha256': _hash(review_path),
                  'profileArchivePins': archived, 'profileArchiveDirectories': directories,
                  'nativeEvidence': native, 'files': files,
                  'observer': review['observer'], 'observerRole': 'current_read_only_observer_not_run_executor',
                  'reason': review['summary']}
        packet['testResult'] = p.test_projection(plan['orderData'], packet)
        packet['testingStarted'] = packet['testResult']['testingStarted']
        if review.get('exactSingleStartReviewed') is True:
            packet.update(actualGameStarts=1,
                cumulativeActualGameStartsAfter=(None if plan['cumulativeActualGameStartsBefore'] is None
                                                else plan['cumulativeActualGameStartsBefore'] + 1),
                accountingBasis='reviewed_exact_single_native_start')
        if review.get('additionalEvidencePins'):
            packet['supplementalEvidenceRole'] = 'raw_only_not_official_companion_or_qualification_coverage'
        # An interrupted write is retained for review, never overwritten/adopted.
        target = p.local / 'qualifications' / identity / 'held-diagnostic.json'
        snapshots = target.parent / 'diagnostic-implementation'
        if target.exists() or snapshots.exists():
            raise ValueError('Unregistered diagnostic artifact requires explicit review')
        for pin in files:
            _pin(pin)
        # Freeze code separately, so later legitimate repository updates cannot
        # invalidate this historical diagnostic. Never execute these copies.
        snapshots.mkdir()
        code_pins = []
        # Frozen attempt request/order/config/scenario remain original evidence.
        # Snapshot only live host settings and installed input roots which future
        # authorized SE/VR preparation can legitimately update.
        protected = {str(_absolute(plan[key])) for key in ('requestPath', 'order', 'configPath', 'scenarioPath')}
        protected.add(str(_absolute(plan['ownerAuthorization']['path'])))
        accounting = Path(plan['launchAccounting']['path'])
        if not accounting.is_absolute():
            accounting = Path(plan['requestPath']).parent / accounting
        protected.add(str(_absolute(str(accounting))))
        live_roots = [Path(plan['configuration'][key]).resolve()
                      for key in ('game', 'mods', 'profiles', 'overwrite') if plan['configuration'].get(key)]
        live_settings = ({Path(plan['configuration']['mo2_ini']).resolve()}
                         if plan['configuration'].get('mo2_ini') else set())
        original_pins = {pin['path']: pin for pin in plan['pins']}
        mutable_inputs = [original_pins[pin['path']] for pin in files if pin['path'] in original_pins
                          and pin['path'] not in protected
                          and (Path(pin['path']) == p.local / 'config.json'
                               or Path(pin['path']).resolve() in live_settings
                               or any(Path(pin['path']).is_relative_to(root) for root in live_roots))]
        mutable_paths = {pin['path'] for pin in mutable_inputs}
        files[:] = [pin for pin in files if pin['path'] not in mutable_paths]
        original_snapshots = []
        for index, source in enumerate(review['implementationPins'] + [review['observer']] + mutable_inputs):
            path = _pin(source)
            if source in mutable_inputs:
                name = f'input-{index:04d}-' + path.name
            else:
                name = 'observer-native.py' if source == review['observer'] else path.name
            destination = snapshots / name
            if destination.exists():
                raise ValueError('Diagnostic implementation snapshot name collision')
            destination.write_bytes(path.read_bytes())
            if _hash(destination) != source['sha256']:
                raise ValueError('Diagnostic implementation snapshot differs')
            snapshot_pin = {'path': str(destination), 'sha256': source['sha256']}
            code_pins.append(snapshot_pin)
            if source in mutable_inputs:
                original_snapshots.append({'original': source, 'snapshot': snapshot_pin})
            if source == review['observer']:
                packet['observer'] = snapshot_pin
        packet['files'].extend(code_pins)
        packet['implementationSnapshotPins'] = code_pins
        packet['originalInputSnapshots'] = original_snapshots
        # Recheck raw/snapshot bytes after copying, immediately before fresh native
        # observation and the terminal record. Code/input origin paths are provenance
        # only after their exact verified copies have been frozen above.
        for pin in packet['files']:
            _pin(pin)
        verify_archive(packet)
        packet['nativeEvidence'] = _native(observer, identities)
        m.write(target, packet)
        reference = json.dumps({'path': str(target), 'sha256': _hash(target)}, sort_keys=True)
        con.execute("UPDATE qualifications SET status='recorded',packet=? WHERE id=?", (reference, identity))
        p.event(con, identity, 'qualification_diagnostic_recorded',
                'Ended diagnostic only; accounting unknown and genuine hold retained')
    return packet

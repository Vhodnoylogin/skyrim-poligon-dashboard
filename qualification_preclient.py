"""Explicit collection of one ended pre-client transport refusal; never launch."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys

from qualification_diagnostic import archive_inventory, verify_archive
from qualification_pre_native import _identity, _pin

KIND = 'qualification-preclient-diagnostic'
STARTUP_KIND = 'qualification-startup-diagnostic'


def api():
    import polygon
    return polygon


def require(value, message):
    if not value: raise ValueError('Pre-client collection: ' + message)


def implementation_pins():
    m = api()
    return [{'path': str(p), 'sha256': m.digest(p)} for p in sorted(m.HERE.glob('*.py'))]


def _native_dead(plan, identities):
    from qualification_companion import verify_processes_dead
    verify_processes_dead(plan, identities)
    native = Path(plan['executor']) / 'skyrim_autotest/native.py'
    expected = next(p['sha256'] for p in plan['executorPins'] if Path(p['path']) == native)
    code = """import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]);p=root/'skyrim_autotest/native.py'
assert hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[2]
sys.path.insert(0,str(root));from skyrim_autotest import native
rows=native.processes();assert isinstance(rows,list) and rows
assert not any(r['name'].lower() in {'skyrimse.exe','skyrimvr.exe','skse64_loader.exe','sksevr_loader.exe'} for r in rows)
print(json.dumps({'noGame':True}))
"""
    r = subprocess.run([sys.executable, '-B', '-c', code, plan['executor'], expected],
                       capture_output=True, text=True, timeout=30, shell=False)
    require(r.returncode == 0 and r.stdout.strip() == '{"noGame": true}', 'fresh complete idle inventory required')


def verify_prefix(plan, folder, state_path):
    """Reject an initialized client, lost action ACK or any component delivery."""
    m = api(); folder, state_path = Path(folder), Path(state_path)
    state, result = m.read(state_path), m.read(state_path.parent / 'result.json')
    worker = m.read(folder / 'worker.json').get('identity')
    expected = 'qualification-' + plan['id']; root = folder / 'subject-companion'
    report, dispatch = m.read(root / 'report.json'), m.read(root / 'dispatch.json')
    require(state_path == Path(plan['configuration']['runtime']) / 'runs' / state['id'] / 'state.json' and
            state['order']['id'] == expected and state['runner'] == _identity(worker), 'native attribution differs')
    game = _identity(state.get('game'))
    require(any(row.get('role') == 'game' and row.get('identity') == game for row in state.get('owned', [])),
            'exact game must belong to this native owner')
    require(state.get('done') is True and state.get('restored') is True and not state.get('restoreErrors') and
            state.get('collectionComplete') is True and not state.get('collectionErrors') and
            result.get('id') == state['id'] and result.get('result') == state.get('result') == 'passed' and
            result.get('restored') is True and not result.get('restoreErrors'), 'ended collected native restoration required')
    require(state.get('gameplayBootstrap', {}).get('completed') is True and
            state.get('interactiveSession', {}).get('ready') is False and
            state['interactiveSession'].get('reason') == 'owner-finished', 'known common bootstrap and owner finish required')
    require(m.read(folder / 'child-exit.json') == {'returncode': 0}, 'normal native child exit required')
    require(report.get('schemaVersion') == 1 and report.get('kind') == 'subject-companion-report' and
            report.get('done') is True and report.get('status') == 'stopped' and report.get('completed') is False and
            report.get('uncertain') is False and report.get('subjectStarted') is False and report.get('subjectStart') is None and
            report.get('actions') == [] and report.get('evidence') == [] and report.get('actionsRetried') is False and
            report.get('audioOpened') is False and report.get('errorType') == 'ConnectionRefusedError' and
            isinstance(report.get('reason'), str) and report['reason'] and
            not any(key in report for key in ('runId', 'sessionId', 'binding', 'sequencerProcess')),
            'only the genuine pre-ready connection refusal with no action/inner process is supported')
    require(report.get('orderId') == report.get('attemptId') == expected and report.get('worker') == worker and
            report.get('game') == state['game'], 'retained report argv identities differ')
    names = [r['name'] for r in m.read(plan['companion']['plan']['path'])['checks']]
    require(report.get('caseIds') == names and report.get('cases') == [
        {'id': name, 'status': 'not_run', 'commandIds': [], 'evidence': []} for name in names], 'all original cases must remain not_run')
    for key in ('plan', 'sequencer', 'transport'):
        require(report.get(key) == plan['companion'][key], 'report source pin differs')
        _pin(report[key])
    events = root / 'events.jsonl'
    require(report.get('events') == {'path': str(events), 'sha256': m.digest(events), 'bytes': 0} and
            events.read_bytes() == b'', 'client has origin/delivery events')
    manifest = root / 'executor-manifest.json'
    require(report.get('executorManifest') == {'path': str(manifest), 'sha256': m.digest(manifest)} and
            m.read(manifest) == {'schemaVersion': 1, 'files': plan['executorPins']}, 'executor inventory differs')
    require(dispatch.get('schemaVersion') == 1 and dispatch.get('orderId') == expected and
            dispatch.get('qualificationId') == plan['id'] and dispatch.get('worker') == worker and
            dispatch.get('returncode') == 2 and 'error' not in dispatch, 'dispatch attribution/exit differs')
    client = dispatch['client']; ident = _identity(client.get('identity')); exit_ = client['exit']
    require(client.get('source') == report['transport'] and client.get('timedOut') is False and
            client.get('terminatedOwnedClient') is False and client.get('returncode') == 2 and
            exit_.get('schemaVersion') == 1 and exit_.get('status') == 'exited' and exit_.get('identityVerified') is True and
            exit_.get('identity') == ident and exit_.get('exitCodeAvailable') is True and type(exit_.get('exitCode')) is int and
            exit_['exitCode'] == 2 and exit_.get('exitCodeHex') == '0x00000002', 'retained exact client exit required')
    argv = client['argv']; require(isinstance(argv, list) and len(argv) % 2 == 0 and len(argv) >= 2 and
                                 Path(argv[0]) == Path(ident['path']) and argv[1] == report['transport']['path'], 'client executable/source differs')
    args = dict(zip(argv[2::2], argv[3::2])); require(len(args) == (len(argv)-2)//2, 'duplicate client flag')
    exact = {'--executor': plan['executor'], '--executor-manifest': str(manifest), '--executor-manifest-sha256': m.digest(manifest),
        '--runtime': plan['configuration']['runtime'], '--channel-config': plan['configuration']['interactive_session']['channelConfig'],
        '--order-id': expected, '--attempt-id': expected, '--output': str(root / 'report.json'),
        '--maximum-seconds': str(plan['companion']['maximumSeconds']),
        **{flag: plan['companion'][key][field] for key in ('plan', 'sequencer') for flag, field in
           (('--'+key, 'path'), ('--'+key+'-sha256', 'sha256'))}}
    require(set(args) == set(exact) | {'--worker-identity', '--game-identity'} and
            all(args[k] == v for k, v in exact.items()) and json.loads(args['--worker-identity']) == worker and
            json.loads(args['--game-identity']) == state['game'], 'exact target flags differ')
    native = dispatch['nativeRun']
    require(native.get('path') == str(state_path) and native.get('runId') == state['id'] and native.get('game') == state['game'],
            'dispatcher native readiness observation differs')
    steps = [json.loads(line) for line in (state_path.parent / 'steps.jsonl').read_text(encoding='utf-8').splitlines()]
    delivered = [r for r in steps if r.get('kind') == 'interactive-action-delivered']
    require(len(delivered) == 1 and delivered[0].get('request') == {'schemaVersion': 1, 'operation': 'finish'},
            'component action exists or known single owner finish missing')
    require(isinstance(delivered[0].get('commandId'), str) and re.fullmatch('[0-9a-f]{32}', delivered[0]['commandId']),
            'known owner finish command UUID required')
    return {'report': report, 'reason': report['reason'], 'state': state, 'client': ident, 'names': names, 'finish': delivered[0]['commandId']}


def verify_startup_prefix(plan, folder, state_path):
    """Ended native startup before the source-defined client admission gate."""
    m = api(); folder, state_path = Path(folder), Path(state_path)
    state, result = m.read(state_path), m.read(state_path.parent / 'result.json')
    expected = 'qualification-' + plan['id']; worker = _identity(m.read(folder / 'worker.json').get('identity'))
    game = _identity(state.get('game'))
    require(state_path == Path(plan['configuration']['runtime']) / 'runs' / state['id'] / 'state.json' and
            state.get('order', {}).get('id') == expected and state.get('runner') == worker and
            any(x.get('role') == 'game' and x.get('identity') == game for x in state.get('owned', [])), 'native startup attribution differs')
    require(state.get('done') is True and state.get('restored') is True and not state.get('restoreErrors') and
            state.get('collectionComplete') is True and not state.get('collectionErrors') and
            result.get('id') == state['id'] and result.get('restored') is True and not result.get('restoreErrors') and
            result.get('result') == state.get('result') == 'failed', 'ended failed startup and completed restoration required')
    recovery = state.get('guardianRecovery', {})
    child = m.read(folder / 'child-exit.json')
    require(set(child) == {'returncode'} and type(child['returncode']) is int and child['returncode'] in (1, 125),
            'exact native termination exit125 or failed-before-client exit1 required')
    native_failure = child['returncode'] == 1
    allowed_phases = {'snapshot', 'start-mo2', 'start-skse', 'wait-devbench',
                      'se-native-startup-events', 'wait-task-queue', 'stop-and-restore'}
    if native_failure:
        require(not recovery and state.get('phase') == 'stop-and-restore' and not state.get('fixtureAnchor') and
                not state.get('ownedWorldGeneration') and not state.get('initialWorldTransition', {}).get('completed'),
                'only failed native bootstrap before world completion/client admission is supported')
        allowed_phases.update({'startup-crash-capture', 'gameplay-startup-screen', 'gameplay-new-game-menu', 'gameplay-new-game-load',
                               'gameplay-new-game-initial-world', 'gameplay-world-ready'})
        exits = [row for row in state.get('gameProcessObservations', []) if row.get('status') == 'exited']
        require(exits and all(row.get('identityVerified') is True and row.get('identity') == game and
                row.get('expectedIdentity') == game and row.get('exitCodeAvailable') is True and
                type(row.get('exitCode')) is int and 0 < row['exitCode'] < 2**32 and
                row.get('exitCodeHex') == f"0x{row['exitCode']:08X}" for row in exits) and
                len({row['exitCode'] for row in exits}) == 1, 'exact observed nonzero owned game exit required')
    else:
        require(isinstance(recovery.get('trigger'), str) and recovery['trigger'] and
                recovery.get('prior', {}).get('phase') in {'wait-devbench', 'se-native-startup-events', 'wait-task-queue'} and
                state.get('phase') == 'stop-and-restore', 'only the reviewed guardian-ended pre-world startup is supported')
    require(not state.get('interactiveSession') and not state.get('gameplayBootstrap') and
            not state.get('interactiveArtifacts') and not state.get('interactiveActorFixtures'), 'interactive or world-ready ownership was reached')
    root = folder / 'subject-companion'; manifest = root / 'executor-manifest.json'
    names_expected = {'executor-manifest.json', 'dispatch.json'} if native_failure else {'executor-manifest.json'}
    require(root.is_dir() and {x.name for x in root.iterdir()} == names_expected and
            m.read(manifest) == {'schemaVersion': 1, 'files': plan['executorPins']},
            'client output or unexpected helper artifacts exist; never infer a missing client identity')
    if native_failure:
        require(m.read(root / 'dispatch.json') == {'schemaVersion': 1, 'orderId': expected,
                'qualificationId': plan['id'], 'worker': worker},
                'only the initial exact dispatcher prefix without client intent/identity is supported')
    steps = [json.loads(line) for line in (state_path.parent / 'steps.jsonl').read_text(encoding='utf-8').splitlines()]
    forbidden = {'interactive-ready', 'interactive-action-delivered', 'gameplay-ready', 'bootstrap-completed'}
    require(not any(x.get('kind') in forbidden or x.get('commandId') or
            (native_failure and str(x.get('kind', '')).startswith('interactive-')) for x in steps),
            'subject/client action or readiness evidence exists')
    phases = [x.get('name') for x in steps if x.get('kind') == 'phase']
    require(phases and phases[-1] == 'stop-and-restore' and all(x in allowed_phases for x in phases),
        'native progressed beyond the source-defined startup gate')
    names = [x['name'] for x in m.read(plan['companion']['plan']['path'])['checks']]
    for name in ('plan', 'sequencer', 'transport'): _pin(plan['companion'][name])
    return {'report': None, 'reason': state.get('reason') or recovery.get('trigger'), 'state': state, 'client': None,
            'names': names, 'finish': None,
            'failureMode': 'native-failed-before-client' if native_failure else 'guardian-ended-pre-world'}


def verify_ended_technical_review(plan, folder, state_path, pin, checked):
    """Pin the independent operator's raw inventory; it never replaces native proof."""
    m = api(); path = _pin(pin); review = m.read(path)
    require(review.get('schemaVersion') == 1 and review.get('qualificationId') == plan['id'] and
            Path(review.get('nativeRun', '')).resolve() == Path(state_path).parent.resolve() and
            review.get('nativeDoneRestoredCollected') is True and review.get('nativeResult') == 'failed' and
            review.get('noClientReport') is True and review.get('componentActions') == 0 and
            type(review.get('componentActions')) is int and type(review.get('componentChecksNotRun')) is int and
            review['componentChecksNotRun'] == len(checked['names']) and
            review.get('workerExit') == {'returncode': 1} and
            type(review.get('gameExit')) is int and review['gameExit'] ==
                next(row['exitCode'] for row in checked['state']['gameProcessObservations'] if row.get('status') == 'exited') and
            review.get('dispatch') == m.read(Path(folder) / 'subject-companion/dispatch.json'),
            'ended technical review attribution or no-client/no-action facts differ')
    raw = review.get('rawPins')
    require(isinstance(raw, list) and raw and len(raw) <= 100000, 'bounded reviewed raw inventory required')
    paths = []
    for item in raw: paths.append(str(_pin(item)))
    critical = {str(Path(folder) / name) for name in ('plan.json', 'worker.json', 'child-exit.json',
                'subject-companion/dispatch.json', 'subject-companion/executor-manifest.json')}
    critical.update(str(Path(state_path).parent / name) for name in ('state.json', 'result.json', 'steps.jsonl'))
    require(len(paths) == len(set(paths)) and critical <= set(paths), 'duplicate or incomplete reviewed raw inventory')
    return {'path': str(path), 'sha256': m.digest(path)}


def record(p, identity, review_path, *, startup=False):
    m = api(); review_path = Path(review_path).resolve(); review_hash = m.digest(review_path); review = m.read(review_path)
    require(review.get('schemaVersion') == 1 and review.get('kind') == ('qualification-startup-review' if startup else 'qualification-preclient-review') and
            review.get('qualificationId') == identity and all(review.get(k) is True for k in
             ('nativeCompletionReviewed', 'restorationReviewed', 'archiveReviewed', 'startupFailureReviewed' if startup else 'preclientFailureReviewed', 'retainHold')),
            'explicit collection-only operator review required')
    for k in ('verifiedBy', 'summary'): m.required_string(review, k)
    require(review.get('implementationPins') == implementation_pins(), 'current reviewed implementation differs')
    with p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute('SELECT * FROM qualifications WHERE id=?', (identity,)).fetchone()
        require(row is not None and row['status'] == 'running' and not row['packet'], 'uncollected ended qualification required')
        require(con.execute('SELECT id FROM pipeline_holds WHERE id=?', ('qualification-' + identity,)).fetchone(), 'retain original qualification hold')
        require(not p.qualification_busy(con) and not con.execute("SELECT id FROM qualifications WHERE id!=? AND status IN ('prepared','running')", (identity,)).fetchone(), 'another owner blocks recording')
        require(con.execute('SELECT id FROM attempts WHERE id=?', ('qualification-' + identity,)).fetchone(), 'actual native admission required')
        plan = p.qualification_verify(dict(row), authority=False)
        require('companion' in plan, 'explicit companion qualification required')
        folder = p.local / 'qualifications' / identity
        require(m.read(folder / 'plan.json') == plan, 'retained plan differs')
        runs = [s for s in (Path(plan['configuration']['runtime']) / 'runs').glob('*/state.json')
                if m.read(s).get('order', {}).get('id') == 'qualification-' + identity]
        require(len(runs) == 1, 'one exact native run required')
        state_path = runs[0]
        checked = (verify_startup_prefix if startup else verify_prefix)(plan, folder, state_path); state = checked['state']
        technical_review = None
        if checked.get('failureMode') == 'native-failed-before-client':
            technical_review = verify_ended_technical_review(plan, folder, state_path, review.get('endedTechnicalReview'), checked)
        exact_paths = {'plan': folder / 'plan.json', 'state': state_path, 'result': state_path.parent / 'result.json',
            'childExit': folder / 'child-exit.json', 'worker': folder / 'worker.json'}
        if not startup:
            exact_paths.update(report=folder / 'subject-companion/report.json', dispatch=folder / 'subject-companion/dispatch.json')
        elif technical_review:
            exact_paths['dispatch'] = folder / 'subject-companion/dispatch.json'
        for key, path in exact_paths.items(): _pin(review[key], path)
        require(p.native_game_starts(state) == 1, 'exactly one consumed physical start required')
        archive = state_path.parent / 'test-profile'; archived, directories = archive_inventory(archive)
        require(archived and Path(state.get('profileArchive', '')).resolve() == archive.resolve() and
                state.get('testProfile') and not Path(state['testProfile']).exists() and
                review.get('profileArchivePins') == archived and review.get('profileArchiveDirectories') == directories,
                'nonempty archived and removed profile inventory differs')
        restoration = []
        for snapshot in state.get('snapshots', []):
            from companion_evidence import _path
            path = _path(snapshot['path'])
            require(path.is_file() if snapshot['exists'] else not path.exists(), 'restoration existence differs')
            if snapshot['exists']:
                require(m.digest(path) == snapshot['sha256'] and Path(snapshot['backup']).is_relative_to(state_path.parent / 'backups') and
                        m.digest(snapshot['backup']) == snapshot['sha256'], 'restored target or original backup hash differs')
            restoration.append({'path': str(path), 'exists': snapshot['exists'], 'sha256': snapshot.get('sha256')})
        require(restoration, 'tracked restoration inventory required')
        identities = [state['runner']] + ([checked['client']] if checked['client'] is not None else []) + [state['game']] + [x['identity'] for x in state['owned']]
        identities = list({json.dumps(value, sort_keys=True): value for value in identities}.values())
        _native_dead(plan, identities)
        output = folder / ('startup-diagnostic' if startup else 'preclient-diagnostic'); require(not output.exists(), 'diagnostic is immutable')
        files = []
        for directory in (folder, state_path.parent):
            for path in sorted(directory.rglob('*')):
                from companion_evidence import _path
                _path(path)
                if path.is_file() and path.name != 'packet.json': files.append({'path': str(path), 'sha256': m.digest(path)})
        # Installed inputs may legitimately be rolled back after collection.
        # Retain their exact reviewed bytes instead of freezing the live setup forever.
        require(m.digest(review_path) == review_hash, 'review changed during recording')
        output.mkdir(); retained_originals = []
        for number, original in enumerate(plan['pins']):
            source = _pin(original); destination = output / 'original-inputs' / str(number)
            raw = source.read_bytes()
            require(hashlib.sha256(raw).hexdigest() == original['sha256'], 'original input changed while copying')
            destination.parent.mkdir(exist_ok=True); destination.write_bytes(raw)
            files.append({'path': str(destination), 'sha256': m.digest(destination)})
            retained_originals.append({'originalPath': str(source), 'retainedPath': str(destination), 'sha256': original['sha256']})
        files.extend(plan['executorPins']); files.extend(review['implementationPins'])
        files.append({'path': str(review_path), 'sha256': m.digest(review_path)})
        if technical_review: files.append(technical_review)
        files = sorted({x['path']: x for x in files}.values(), key=lambda x: x['path'])
        packet = {'schemaVersion': 1, 'kind': STARTUP_KIND if startup else KIND, 'id': identity, 'orderId': plan['orderData']['id'],
            'sourceThreadId': plan['orderData']['sourceThreadId'], 'runDirectory': str(state_path.parent),
            'attemptId': 'qualification-' + identity, 'actualGameStarts': 1,
            'cumulativeActualGameStartsBefore': plan['cumulativeActualGameStartsBefore'],
            'cumulativeActualGameStartsAfter': None if plan['cumulativeActualGameStartsBefore'] is None else plan['cumulativeActualGameStartsBefore']+1,
            'restored': True, 'collectionFinished': True, 'testingStarted': False, 'executionOutcome': state['result'],
            'qualificationOutcome': 'not_conducted', 'reason': checked['reason'], 'retainHold': True,
            'globalProviderQualified': False, 'subjectModAccepted': False, 'physicsQualified': False,
            'componentCoverage': [{'name': name, 'result': 'not_run'} for name in checked['names']],
            'clientRunIdentityAvailable': False, 'nativeAttributionBasis': ('native startup state, phase log and unchanged source-defined admission gate; no client report or identity fabricated'
                if startup else 'native state and retained client argv; report identity fields remain absent'),
            'ownerFinishCommandId': checked['finish'], 'recordedRestoration': restoration,
            'retainedOriginalPins': retained_originals,
            'profileArchivePins': archived, 'profileArchiveDirectories': directories, 'files': files}
        if startup:
            packet['startupFailureMode'] = checked['failureMode']
            if technical_review: packet['endedTechnicalReview'] = technical_review
        m.write(output / 'packet.json', packet)
        con.execute("UPDATE qualifications SET status='recorded',packet=? WHERE id=?", (json.dumps({'path': str(output / 'packet.json'), 'sha256': m.digest(output / 'packet.json')}), identity))
        p.event(con, identity, 'startup_diagnostic_recorded' if startup else 'preclient_diagnostic_recorded',
                'No components tested; original hold and physical count retained')
        return packet


def verify_packet(p, plan, packet):
    require(packet.get('kind') in (KIND, STARTUP_KIND) and packet.get('id') == plan['id'] and packet.get('retainHold') is True and
            packet.get('qualificationOutcome') == 'not_conducted' and packet.get('testingStarted') is False and
            packet.get('actualGameStarts') == 1 and packet.get('globalProviderQualified') is False, 'diagnostic claims changed')
    folder = p.local / 'qualifications' / plan['id']; run = Path(packet['runDirectory'])
    startup = packet['kind'] == STARTUP_KIND
    checked = (verify_startup_prefix if startup else verify_prefix)(plan, folder, run / 'state.json')
    if checked.get('failureMode') == 'native-failed-before-client':
        require(packet.get('startupFailureMode') == checked['failureMode'], 'startup failure mode changed')
        verify_ended_technical_review(plan, folder, run / 'state.json', packet.get('endedTechnicalReview'), checked)
    require(packet.get('componentCoverage') == [{'name': n, 'result': 'not_run'} for n in checked['names']] and
            packet.get('ownerFinishCommandId') == checked['finish'], 'diagnostic coverage changed')
    originals = packet.get('retainedOriginalPins', [])
    require([(x['originalPath'], x['sha256']) for x in originals] == [(x['path'], x['sha256']) for x in plan['pins']], 'retained original inventory differs')
    for row in originals:
        file = Path(row['retainedPath'])
        require(file.is_relative_to(folder / ('startup-diagnostic' if startup else 'preclient-diagnostic') / 'original-inputs') and
                api().digest(file) == row['sha256'], 'retained original bytes differ')
    verify_archive(packet)

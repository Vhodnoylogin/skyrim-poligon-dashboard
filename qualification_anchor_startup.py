"""Append-only collection of a proved interrupted anchor before client admission.

No game/client execution, recovery, report synthesis, release or hold clearance.
The observed exit is retained independently of the anchor interruption. Position
readbacks do not establish its cause or a subject defect.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

from qualification_diagnostic import (_native, _observer, _sources, archive_inventory,
                                      implementation_pins, verify_archive)
from qualification_pre_native import _identity, _pin
from qualification_preclient import verify_ended_technical_review


KIND = 'qualification-anchor-startup-diagnostic'
MODE = 'anchor-interrupted-before-client'
REASON_PREFIX = 'QA anchor readback exceeded its settling deadline: '
PHASES = {'snapshot', 'start-mo2', 'start-skse', 'wait-devbench', 'se-native-startup-events',
          'wait-task-queue', 'gameplay-startup-screen', 'gameplay-new-game-menu',
          'gameplay-new-game-load', 'gameplay-new-game-initial-world', 'gameplay-world-ready',
          'gameplay-native-fixture-transfer', 'gameplay-native-fixture-destination',
          'gameplay-native-fixture-stabilization', 'gameplay-fixture-anchor', 'stop-and-restore'}


def api():
    import polygon
    return polygon


def require(value, message):
    if not value:
        raise ValueError('Anchor startup collection: ' + message)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def verify_prefix(plan, folder, state_path):
    """Verify original native evidence only; absence of a report is insufficient."""
    m = api(); folder, state_path = Path(folder), Path(state_path)
    state, result = m.read(state_path), m.read(state_path.parent / 'result.json')
    worker = _identity(m.read(folder / 'worker.json').get('identity'))
    game = _identity(state.get('game'))
    require(state_path == Path(plan['configuration']['runtime']) / 'runs' / state['id'] / 'state.json' and
            state['id'] == state_path.parent.name and state.get('order', {}).get('id') == 'qualification-' + plan['id'] and
            state.get('runner') == worker and any(row.get('role') == 'game' and row.get('identity') == game
                                                 for row in state.get('owned', [])), 'native attribution differs')
    require(state.get('done') is True and state.get('restored') is True and state.get('restoreErrors') == [] and
            state.get('collectionComplete') is True and state.get('collectionErrors') == [] and
            result.get('id') == state['id'] and result.get('restored') is True and result.get('restoreErrors') == [] and
            result.get('result') == state.get('result') == 'failed' and state.get('phase') == 'stop-and-restore' and
            m.read(folder / 'child-exit.json') == {'returncode': 1}, 'ended failed native execution/restoration required')
    require(not state.get('guardianRecovery') and not any(state.get(key) for key in
            ('gameplayBootstrap', 'interactiveSession', 'interactiveArtifacts', 'interactiveActorFixtures',
             'morphSession', 'npcPersistence')) and not (state_path.parent / 'subject-companion.claim.json').exists(),
            'client/world readiness, component ownership or recovery exists')
    initial = state.get('initialWorldTransition', {})
    generation = state.get('ownedWorldGeneration')
    require(plan['configuration'].get('game_edition') == 'se' and
            plan['configuration'].get('se_fixture_anchor') == 'qasmoke-west-navmesh-v1' and
            initial.get('completed') is True and initial.get('mode') == 'new-game' and
            initial.get('beforeGame') == initial.get('afterGame') == game and
            type(generation) is int and generation > 0 and initial.get('worldGeneration') == generation,
            'exact completed initial world before the configured anchor required')
    root = folder / 'subject-companion'
    require(root.is_dir() and {path.name for path in root.iterdir()} == {'dispatch.json', 'executor-manifest.json'} and
            m.read(root / 'executor-manifest.json') == {'schemaVersion': 1, 'files': plan['executorPins']} and
            m.read(root / 'dispatch.json') == {'schemaVersion': 1, 'orderId': 'qualification-' + plan['id'],
                'qualificationId': plan['id'], 'worker': worker},
            'only the exact initial dispatch and executor manifest may exist; no client intent/output')
    anchor = state.get('fixtureAnchor', {})
    reason = state.get('reason')
    require(anchor.get('recipe') == plan['configuration']['se_fixture_anchor'] and anchor.get('status') == 'uncertain' and
            anchor.get('runId') == state['id'] and anchor.get('game') == game and anchor.get('worldGeneration') == generation and
            isinstance(anchor.get('preparationId'), str) and re.fullmatch('[0-9a-f]{32}', anchor['preparationId']) and
            anchor.get('steps') == {'MoveTo': 'returned', 'SetAngle': 'returned'} and
            anchor.get('provenance', {}).get('subjectStarted') is False and
            isinstance(reason, str) and reason.startswith(REASON_PREFIX) and
            reason == anchor.get('reason') == result.get('reason'), 'exact uncertain anchor interruption required')
    samples = anchor.get('samples')
    sample_keys = {'atMonotonic', 'position', 'headingDegrees', 'positionErrorGameUnits', 'headingErrorDegrees'}
    require(type(samples) is list and 1 <= len(samples) <= 64, 'bounded actual anchor readbacks required')
    previous = None
    for sample in samples:
        require(type(sample) is dict and set(sample) == sample_keys and type(sample['position']) is list and
                len(sample['position']) == 3 and all(_number(value) for value in sample['position']) and
                all(_number(sample[key]) for key in sample_keys - {'position'}) and
                sample['positionErrorGameUnits'] >= 0 and sample['headingErrorDegrees'] >= 0 and
                (previous is None or sample['atMonotonic'] > previous), 'finite chronological anchor samples required')
        previous = sample['atMonotonic']
    require(all(_number(anchor.get(key)) and anchor[key] >= 0 for key in ('toleranceGameUnits', 'toleranceDegrees')) and
            (samples[-1]['positionErrorGameUnits'] > anchor['toleranceGameUnits'] or
             samples[-1]['headingErrorDegrees'] > anchor['toleranceDegrees']), 'actual unsettled final readback required')
    steps = [json.loads(line) for line in (state_path.parent / 'steps.jsonl').read_text(encoding='utf-8').splitlines()]
    require(steps and all(type(row) is dict for row in steps) and
            not any(str(row.get('kind', '')).startswith('interactive-') or row.get('commandId') or row.get('kind') in
                    {'gameplay-ready', 'bootstrap-completed', 'fixture-anchor-ready', 'scenario-started', 'scenario-step'}
                    for row in steps), 'readiness or component delivery exists')
    phases = [(index, row['name']) for index, row in enumerate(steps) if row.get('kind') == 'phase']
    require(phases and phases[-1][1] == 'stop-and-restore' and all(name in PHASES for _, name in phases) and
            [name for _, name in phases].count('gameplay-fixture-anchor') == 1 and
            [name for _, name in phases].count('stop-and-restore') == 1,
            'native progressed outside the supported anchor prefix')
    entered = next(index for index, name in phases if name == 'gameplay-fixture-anchor')
    completed = [(index, row) for index, row in enumerate(steps) if row.get('kind') == 'initial-world-completed']
    readbacks = [(index, row) for index, row in enumerate(steps) if row.get('kind') == 'fixture-anchor-readback']
    errors = [(index, row) for index, row in enumerate(steps) if row.get('kind') == 'exception']
    require(len(completed) == len(errors) == 1 and completed[0][0] < entered and readbacks and
            entered < readbacks[0][0] <= readbacks[-1][0] < errors[0][0] < phases[-1][0] and
            [{key: row.get(key) for key in sample_keys} for _, row in readbacks] == samples,
            'original initial-world/anchor/readback/exception/cleanup chronology differs')
    trace = errors[0][1].get('trace', '')
    frames = re.findall(r'File "([^"]+)", line [0-9]+, in ([^\r\n]+)', trace)
    expected_frames = [(str(Path(plan['executor']) / 'skyrim_autotest' / name), function) for name, function in
                       (('runner.py', 'run'), ('bootstrap.py', 'prepare_gameplay'), ('fixture_anchor.py', 'prepare_anchor'))]
    require([(Path(path), function) for path, function in frames] == [(Path(path), function) for path, function in expected_frames] and
            trace.rstrip().endswith('skyrim_autotest.interactive_bindings.BindingError: ' + reason),
            'exact pinned executor anchor exception required')
    for name in ('runner.py', 'bootstrap.py', 'fixture_anchor.py'):
        path = Path(plan['executor']) / 'skyrim_autotest' / name
        pins = [pin for pin in plan['executorPins'] if Path(pin['path']) == path]
        require(len(pins) == 1 and state.get('executorHashes', {}).get(name) == pins[0]['sha256'],
                'actual native executor source identity differs')
        _pin(pins[0])
    exits = [row for row in state.get('gameProcessObservations', []) if row.get('status') == 'exited']
    require(exits and all(row.get('identityVerified') is True and row.get('identity') == row.get('expectedIdentity') == game and
            row.get('exitCodeAvailable') is True and type(row.get('exitCode')) is int and 0 <= row['exitCode'] < 2**32 and
            row.get('exitCodeHex') == f"0x{row['exitCode']:08X}" for row in exits) and
            len({row['exitCode'] for row in exits}) == 1, 'exact known native exit required; no inference from process absence')
    names = [row['name'] for row in m.read(plan['companion']['plan']['path'])['checks']]
    require(names and len(names) == len(set(names)), 'original component inventory required')
    for key in ('plan', 'sequencer', 'transport'):
        _pin(plan['companion'][key])
    return {'state': state, 'reason': reason, 'names': names, 'finish': None, 'client': None,
            'report': None, 'failureMode': MODE, 'gameExitCode': exits[0]['exitCode']}


def _checked(p, identity, review_path, con):
    m = api(); row = con.execute('SELECT * FROM qualifications WHERE id=?', (identity,)).fetchone()
    require(row is not None and row['status'] == 'running' and not row['packet'], 'uncollected running qualification required')
    plan = json.loads(row['request']); folder = p.local / 'qualifications' / identity
    require(m.read(folder / 'plan.json') == plan and 'companion' in plan, 'original companion plan differs')
    review = m.read(review_path)
    require(review.get('schemaVersion') == 1 and review.get('kind') == 'qualification-anchor-startup-review' and
            review.get('qualificationId') == identity and all(review.get(key) is True for key in
            ('nativeCompletionReviewed', 'restorationReviewed', 'archiveReviewed', 'anchorInterruptionReviewed',
             'noClientAdmissionReviewed', 'exactSingleStartReviewed', 'retainHold')), 'explicit collection-only review required')
    for key in ('verifiedBy', 'summary'):
        m.required_string(review, key)
    require(con.execute('SELECT id FROM pipeline_holds WHERE id=?', ('qualification-' + identity,)).fetchone(), 'genuine original hold required')
    require(not p.qualification_busy(con) and not con.execute(
        "SELECT id FROM qualifications WHERE id!=? AND status IN ('prepared','running')", (identity,)).fetchone(), 'another active owner blocks recording')
    require(con.execute('SELECT id FROM attempts WHERE id=?', ('qualification-' + identity,)).fetchone(), 'original native admission required')
    sources = _sources(plan, review, folder / 'plan.json')
    runtimes = {Path(plan['configuration']['runtime'])}
    if p.host().get('runnerConfig'):
        runtimes.add(Path(m.read(p.host()['runnerConfig'])['runtime']))
    runs = []
    for runtime in runtimes:
        for state_path in (runtime / 'runs').glob('*/state.json'):
            state = m.read(state_path)
            require(state.get('done') is True, 'unfinished native session blocks recording')
            if state.get('order', {}).get('id') == 'qualification-' + identity:
                require(state_path.is_relative_to(Path(plan['configuration']['runtime'])), 'foreign runtime attribution')
                runs.append(state_path)
    require(len(runs) == 1, 'one exact admitted native run required')
    state_path = runs[0]; checked = verify_prefix(plan, folder, state_path); state = checked['state']
    for key, path in {'plan': folder / 'plan.json', 'state': state_path, 'result': state_path.parent / 'result.json',
                      'worker': folder / 'worker.json', 'childExit': folder / 'child-exit.json',
                      'dispatch': folder / 'subject-companion/dispatch.json'}.items():
        _pin(review[key], path)
    technical = verify_ended_technical_review(plan, folder, state_path, review.get('endedTechnicalReview'), checked)
    require(p.native_game_starts(state) == 1, 'exactly one consumed physical start required')
    before = plan['cumulativeActualGameStartsBefore']
    require(before is None or type(before) is int and before >= 0, 'known or explicitly unknown cumulative baseline required')
    archive = state_path.parent / 'test-profile'; archived, directories = archive_inventory(archive)
    require(archived and Path(state.get('profileArchive', '')).resolve() == archive.resolve() and
            state.get('testProfile') and not Path(state['testProfile']).exists() and
            review.get('profileArchivePins') == archived and review.get('profileArchiveDirectories') == directories,
            'exact nonempty archived and removed profile inventory required')
    restoration = []
    for snapshot in state.get('snapshots', []):
        from companion_evidence import _path
        path = _path(snapshot['path'])
        require(type(snapshot.get('exists')) is bool and (path.is_file() if snapshot['exists'] else not path.exists()), 'restored target existence differs')
        if snapshot['exists']:
            require(m.digest(path) == snapshot['sha256'] and Path(snapshot['backup']).is_relative_to(state_path.parent / 'backups') and
                    m.digest(snapshot['backup']) == snapshot['sha256'], 'restored target or original backup differs')
        restoration.append({'path': str(path), 'exists': snapshot['exists'], 'sha256': snapshot.get('sha256')})
    require(restoration, 'tracked restoration inventory required')
    context = review.get('operatorReportedContext')
    if context is not None:
        require(type(context) is dict and set(context) == {'summary', 'evidence'}, 'reported context requires separate pinned provenance')
        m.required_string(context, 'summary'); sources.append(_pin(context['evidence']))
    identities = [_identity(state['runner']), _identity(state['game'])] + [_identity(row['identity']) for row in state['owned']]
    identities = list({json.dumps(value, sort_keys=True): value for value in identities}.values())
    return plan, review, state_path, checked, archived, directories, restoration, identities, sources, technical


def record(p, identity, review_path):
    """Supported collection API; caller must separately expose this exact kind."""
    m = api(); review_path = Path(review_path).resolve(); review_hash = m.digest(review_path)
    with p.connect() as con:
        checked = _checked(p, identity, review_path, con)
    observer = _observer(checked[1]['observer'])
    with observer.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        plan, review, state_path, checked, archived, directories, restoration, identities, sources, technical = _checked(p, identity, review_path, con)
        native = _native(observer, identities)
        require(m.digest(review_path) == review_hash, 'review changed during recording')
        folder = p.local / 'qualifications' / identity; output = folder / 'anchor-startup-diagnostic'
        require(not output.exists(), 'unregistered diagnostic artifact is immutable; explicit review required')
        from companion_evidence import _path
        files = {str(path): m.digest(path) for directory in (folder, state_path.parent) for path in directory.rglob('*')
                 if _path(path).is_file()}
        files.update({str(path): m.digest(path) for path in sources})
        files[str(review_path)] = review_hash; files[technical['path']] = technical['sha256']
        files[review['observer']['path']] = review['observer']['sha256']
        files.update({pin['path']: pin['sha256'] for pin in plan['executorPins']})
        output.mkdir(); originals, code = [], []
        for index, original in enumerate(plan['pins']):
            source = _pin(original); destination = output / 'original-inputs' / str(index)
            raw = source.read_bytes(); require(hashlib.sha256(raw).hexdigest() == original['sha256'], 'original input changed while freezing')
            destination.parent.mkdir(exist_ok=True); destination.write_bytes(raw)
            files.pop(str(source), None); files[str(destination)] = original['sha256']
            originals.append({'originalPath': str(source), 'retainedPath': str(destination), 'sha256': original['sha256']})
        for original in review['implementationPins']:
            source = _pin(original); destination = output / 'implementation' / source.name
            raw = source.read_bytes(); require(hashlib.sha256(raw).hexdigest() == original['sha256'], 'implementation changed while freezing')
            destination.parent.mkdir(exist_ok=True); destination.write_bytes(raw); files[str(destination)] = original['sha256']
            code.append({'originalPath': str(source), 'retainedPath': str(destination), 'sha256': original['sha256']})
        before = plan['cumulativeActualGameStartsBefore']
        packet = {'schemaVersion': 1, 'kind': KIND, 'id': identity, 'orderId': plan['orderData']['id'],
            'sourceThreadId': plan['orderData']['sourceThreadId'], 'attemptId': 'qualification-' + identity,
            'runDirectory': str(state_path.parent), 'executionOutcome': 'failed', 'executionEnded': True,
            'qualificationOutcome': 'not_conducted', 'qualificationPassed': False, 'collectionFinished': True,
            'restored': True, 'restorationScope': 'tracked_executor_domains_only', 'recordedRestoration': restoration,
            'testingStarted': False, 'subjectModAccepted': False, 'globalProviderQualified': False, 'physicsQualified': False,
            'actualGameStarts': 1, 'cumulativeActualGameStartsBefore': before,
            'cumulativeActualGameStartsAfter': None if before is None else before + 1,
            'retainHold': True, 'clientRunIdentityAvailable': False, 'ownerFinishCommandId': None,
            'startupFailureMode': MODE, 'reason': checked['reason'], 'causeEstablishedByCollector': False,
            'gameExitCodeAvailable': True, 'gameExitCode': checked['gameExitCode'],
            'componentCoverage': [{'name': name, 'result': 'not_run'} for name in checked['names']],
            'profileArchivePins': archived, 'profileArchiveDirectories': directories,
            'retainedOriginalPins': originals, 'retainedImplementationPins': code,
            'review': {'path': str(review_path), 'sha256': review_hash}, 'endedTechnicalReview': technical,
            'nativeEvidence': native, 'files': [{'path': path, 'sha256': digest} for path, digest in sorted(files.items())]}
        if review.get('operatorReportedContext') is not None:
            packet['operatorReportedContext'] = review['operatorReportedContext']
        for pin in packet['files']:
            _pin(pin)
        m.write(output / 'packet.json', packet)
        con.execute("UPDATE qualifications SET status='recorded',packet=? WHERE id=?",
                    (json.dumps({'path': str(output / 'packet.json'), 'sha256': m.digest(output / 'packet.json')}), identity))
        p.event(con, identity, 'anchor_startup_diagnostic_recorded', 'Interrupted before client; all components not_run; original hold/count retained')
        return packet


def verify_packet(p, plan, packet):
    """Cached evidence verification; no current restoration or process mutation."""
    m = api(); folder = p.local / 'qualifications' / plan['id']; run = Path(packet['runDirectory'])
    require(packet.get('kind') == KIND and packet.get('id') == plan['id'] and packet.get('attemptId') == 'qualification-' + plan['id'] and
            packet.get('startupFailureMode') == MODE and packet.get('executionOutcome') == 'failed' and
            packet.get('qualificationOutcome') == 'not_conducted' and packet.get('qualificationPassed') is False and
            packet.get('retainHold') is True and packet.get('testingStarted') is False and
            packet.get('clientRunIdentityAvailable') is False and packet.get('ownerFinishCommandId') is None and
            packet.get('subjectModAccepted') is False and packet.get('globalProviderQualified') is False and
            packet.get('physicsQualified') is False and packet.get('causeEstablishedByCollector') is False and
            type(packet.get('actualGameStarts')) is int and packet['actualGameStarts'] == 1, 'diagnostic claims changed')
    for pin in packet['files']:
        _pin(pin)
    checked = verify_prefix(plan, folder, run / 'state.json')
    require(packet.get('componentCoverage') == [{'name': name, 'result': 'not_run'} for name in checked['names']] and
            packet.get('reason') == checked['reason'] and packet.get('gameExitCodeAvailable') is True and
            type(packet.get('gameExitCode')) is int and packet['gameExitCode'] == checked['gameExitCode'], 'coverage or observed exit changed')
    before = plan['cumulativeActualGameStartsBefore']
    require(packet.get('cumulativeActualGameStartsBefore') == before and
            packet.get('cumulativeActualGameStartsAfter') == (None if before is None else before + 1), 'cumulative accounting changed')
    originals = packet.get('retainedOriginalPins', [])
    require([(row['originalPath'], row['sha256']) for row in originals] == [(pin['path'], pin['sha256']) for pin in plan['pins']],
            'retained original inventory differs')
    for row in originals:
        require(Path(row['retainedPath']).is_relative_to(folder / 'anchor-startup-diagnostic/original-inputs'), 'retained input escaped its diagnostic')
        _pin({'path': row['retainedPath'], 'sha256': row['sha256']})
    review_path = _pin(packet['review']); review = m.read(review_path)
    require(packet.get('operatorReportedContext') == review.get('operatorReportedContext'), 'reported context changed')
    verify_ended_technical_review(plan, folder, run / 'state.json', packet['endedTechnicalReview'], checked)
    verify_archive(packet)

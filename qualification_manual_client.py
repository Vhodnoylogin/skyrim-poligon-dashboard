"""One first manual client after the known owned-INI pre-client refusal.

Never launches/restarts/adopts a game, changes a frozen input, renews a deadline,
replays a client or clears a hold. The existing native worker remains the owner.
"""
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from qualification_companion import _ready, _Context, order_view
from qualification_diagnostic import implementation_pins
from qualification_pre_native import _pin
from subject_companion_route import _read_live_state, _retain_client

ERROR = 'ValueError: Owned MO2 admission: settings differ beyond the owned selected_profile write'
DIRECTORY = 'first-manual-client'


def api():
    import polygon
    return polygon


def require(value, message):
    if not value: raise ValueError('First manual client: ' + message)


def prior(plan, folder):
    """The old watcher reached a terminal exception before any client intent."""
    m = api(); root = Path(folder) / 'subject-companion'
    require({p.name for p in root.iterdir()} == {'dispatch.json', 'executor-manifest.json'},
            'prior client output/intent exists')
    dispatch = m.read(root / 'dispatch.json')
    require(set(dispatch) == {'schemaVersion', 'orderId', 'qualificationId', 'worker', 'error', 'errorDetails'} and
            dispatch['schemaVersion'] == 1 and dispatch['orderId'] == 'qualification-' + plan['id'] and
            dispatch['qualificationId'] == plan['id'] and dispatch['error'] == ERROR and
            dispatch['worker'] == m.read(Path(folder) / 'worker.json')['identity'] and
            dispatch['errorDetails'].get('operation') == 'qualification-companion' and
            dispatch['errorDetails'].get('traceback', '').rstrip().endswith(ERROR), 'not the exact terminal pre-client INI refusal')
    require(m.read(root / 'executor-manifest.json') == {'schemaVersion': 1, 'files': plan['executorPins']},
            'original native manifest changed')
    declared = m.read(plan['companion']['plan']['path'])
    require(declared.get('checks') == [{'name': 'owner-controlled-manual-scene', 'role': 'subject'}] and
            declared.get('scope') == 'Owner-controlled scene and observed actions; no whole-mod acceptance',
            'only the original owner-controlled manual scene is supported')
    return root / 'dispatch.json'


def _runner(plan):
    sys.path.insert(0, plan['executor'])
    from skyrim_autotest import runner
    require(Path(runner.__file__).resolve() == Path(plan['executor']) / 'skyrim_autotest/runner.py',
            'wrong native observer package')
    return runner


def fresh(plan, folder, state_path, worker, game, runner):
    m = api(); runtime = Path(plan['configuration']['runtime'])
    require(state_path.parent.parent == runtime / 'runs' and state_path.name == 'state.json', 'foreign native state path')
    state = _read_live_state(state_path, runtime / 'runs', threading.Event(), time.monotonic() + .75)
    from skyrim_autotest.config import load
    _ready(state, worker, load(Path(folder) / 'config.json'), plan['companion']['maximumSeconds'])
    require(state.get('game') == game and state.get('order', {}).get('id') == 'qualification-' + plan['id'] and
            not any(state.get(k) for k in ('interactiveActorFixtures', 'morphSession', 'npcPersistence', 'interactiveArtifacts')) and
            not (state_path.parent / 'subject-companion.claim.json').exists(), 'prior client/fixture/claim or foreign game')
    for identity in (worker, game):
        require(runner.native.identity(identity['pid']) == identity, 'native owner identity changed')
    log = state_path.parent / 'steps.jsonl'
    require(log.stat().st_size <= 128 * 1024 * 1024, 'oversized native evidence')
    phases = []
    for line in log.read_text(encoding='utf-8-sig').splitlines():
        event = json.loads(line); kind = event.get('kind', '')
        if kind == 'phase' and event.get('name') == 'interactive-session': phases.append(event)
        require(not kind.startswith(('interactive-action-', 'interactive-fixture-', 'morph-session-')),
                'a prior native action exists')
    require(len(phases) == 1 and phases[0].get('deadline') == state.get('deadline'),
            'native interactive deadline differs from its original phase event')
    return state


def admit(p, identity, review_path):
    """Synchronous supervisor of only one data client; operator may run hidden."""
    m = api(); review_path = Path(review_path).resolve(); review_hash = m.digest(review_path); review = m.read(review_path)
    require(m.digest(review_path) == review_hash, 'review changed while reading')
    require(review.get('schemaVersion') == 1 and review.get('kind') == 'qualification-first-manual-client-admission' and
            review.get('qualificationId') == identity and all(review.get(k) is True for k in
            ('manualOnlyReviewed', 'sameOwnedSessionReviewed', 'noPriorClientReviewed', 'originalDeadlineReviewed',
             'currentOwnerAuthorityReviewed', 'originalPinsReviewed')), 'explicit reviewed manual-only admission required')
    for key in ('verifiedBy', 'summary'): m.required_string(review, key)
    require(review.get('implementationPins') == implementation_pins(), 'new admission implementation changed')
    _pin(review['ownerEvidence']); _pin(review['plan']); _pin(review['previousDispatch'])
    folder = p.local / 'qualifications' / identity
    require(Path(review['plan']['path']) == folder / 'plan.json', 'wrong original plan')
    row = p.qualification_show(identity); plan = json.loads(row['request'])
    require(row['status'] == 'running' and not row['packet'] and m.read(folder / 'plan.json') == plan and
            time.time() < min(row['expires'], plan['deadlineUtc']) and 'companion' in plan, 'original live qualification required')
    original = prior(plan, folder)
    require(Path(review['previousDispatch']['path']) == original, 'wrong previous dispatch')
    worker, game = review['worker'], review['game']; state_path = Path(review['statePath'])
    require(worker == m.read(folder / 'worker.json')['identity'], 'original worker differs')
    runner = _runner(plan)
    state = fresh(plan, folder, state_path, worker, game, runner)
    owned = p.qualification_verify_owned_mo2(row, state_path, state, runner)
    output = folder / DIRECTORY
    with p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        require(not p.qualification_busy(con) and not con.execute(
            "SELECT id FROM qualifications WHERE id!=? AND status IN ('prepared','running')", (identity,)).fetchone(),
            'another owner blocks first-client admission')
        holds = [r['id'] for r in con.execute('SELECT id FROM pipeline_holds')]
        require(holds == ['qualification-' + identity], 'exact original hold alone required')
        prior(plan, folder); fresh(plan, folder, state_path, worker, game, runner)
        require(not output.exists(), 'admission already attempted; never replay')
        output.mkdir()
        retained = []; (output / 'implementation').mkdir()
        for source_pin in review['implementationPins']:
            source = _pin(source_pin); raw = source.read_bytes()
            require(m.digest(source) == source_pin['sha256'], 'admission source changed while retaining')
            destination = output / 'implementation' / source.name
            require(not destination.exists(), 'duplicate implementation source name')
            destination.write_bytes(raw)
            require(m.digest(destination) == source_pin['sha256'], 'retained source differs')
            retained.append({'originalPath': str(source), 'path': str(destination), 'sha256': source_pin['sha256']})
        admission = {'schemaVersion': 1, 'kind': 'same-native-first-manual-client', 'qualificationId': identity,
            'plan': review['plan'], 'previousDispatch': review['previousDispatch'],
            'review': {'path': str(review_path), 'sha256': review_hash},
            'worker': worker, 'game': game, 'statePath': str(state_path), 'nativeDeadline': state['deadline'],
            'outerExpires': row['expires'], 'maximumSeconds': plan['companion']['maximumSeconds'],
            'ownedMO2Admission': owned, 'physicalGameStartsAdded': 0, 'nativeOwnerReplaced': False,
            'implementation': retained, 'at': time.time()}
        m.write(output / 'admission.json', admission)
        p.event(con, identity, 'first_manual_client_intent', 'Same live native owner; zero prior client; no new game/deadline')
    root = output / 'subject-companion'; root.mkdir()
    manifest = root / 'executor-manifest.json'; m.write(manifest, {'schemaVersion': 1, 'files': plan['executorPins']})
    spec = plan['companion']; order = order_view(plan)
    args = [sys.executable, spec['transport']['path'], '--executor', plan['executor'],
        '--executor-manifest', str(manifest), '--executor-manifest-sha256', m.digest(manifest),
        '--plan', spec['plan']['path'], '--plan-sha256', spec['plan']['sha256'],
        '--sequencer', spec['sequencer']['path'], '--sequencer-sha256', spec['sequencer']['sha256'],
        '--runtime', plan['configuration']['runtime'], '--channel-config', plan['configuration']['interactive_session']['channelConfig'],
        '--order-id', order['id'], '--attempt-id', order['id'], '--worker-identity', json.dumps(worker),
        '--game-identity', json.dumps(game), '--output', str(root / 'report.json'), '--maximum-seconds', str(spec['maximumSeconds'])]
    record = {'argv': args, 'source': spec['transport'], 'identity': None, 'timedOut': False,
              'terminatedOwnedClient': False, 'returncode': None, 'exit': None}
    dispatch = {'schemaVersion': 1, 'orderId': order['id'], 'qualificationId': identity, 'worker': worker,
        'ownedMO2Admission': owned, 'nativeRun': {'path': str(state_path), 'runId': state['id'], 'game': game,
        'interactiveDeadline': state['deadline'], 'outerExpires': row['expires']}, 'client': record}
    m.write(root / 'dispatch.json', dispatch)  # Durable once intent before CreateProcess.
    child = tracker = None
    try:
        prior(plan, folder); current = fresh(plan, folder, state_path, worker, game, runner)
        require(current['deadline'] == admission['nativeDeadline'], 'original native deadline changed')
        require(p.qualification_verify_owned_mo2(row, state_path, current, runner)['liveSha256'] == owned['liveSha256'],
                'owned MO2 changed before client spawn')
        end = min(admission['nativeDeadline'], admission['outerExpires'] - 60, plan['deadlineUtc'])
        latest = p.qualification_show(identity)
        require(latest['status'] == 'running' and latest['request'] == row['request'] and
                latest['expires'] == row['expires'] and not latest['packet'], 'qualification changed before client spawn')
        require(m.digest(review_path) == review_hash and review['implementationPins'] == implementation_pins(),
                'review or admission source changed before client spawn')
        with (root / 'client.log').open('x', encoding='utf-8') as log:
            require(time.time() < end, 'original native/outer deadline expired before client spawn')
            child = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), shell=False)
            record['identity'], tracker = _retain_client(child)
            m.write(root / 'dispatch.json', dispatch)
            while child.poll() is None:
                if time.time() >= end:
                    record.update(timedOut=True, terminatedOwnedClient=True)
                    child.terminate(); child.wait(timeout=5)  # Only this retained client handle.
                    break
                try: child.wait(timeout=min(.2, max(.001, end - time.time())))
                except subprocess.TimeoutExpired: pass
            record['returncode'] = dispatch['returncode'] = child.returncode
    except BaseException as error:
        dispatch['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        if child is not None:
            if child.poll() is None:
                record['terminatedOwnedClient'] = True; child.terminate(); child.wait(timeout=5)
            record['returncode'] = dispatch['returncode'] = child.returncode
        if tracker is not None:
            try: record['exit'] = tracker.snapshot()
            finally: record['handleClose'] = tracker.close()
        m.write(root / 'dispatch.json', dispatch)
    return dispatch


def collection_context(p, plan, folder, run):
    """Select only the explicitly admitted additive client evidence for collection."""
    m = api(); folder, run = Path(folder), Path(run); output = folder / DIRECTORY
    admission = m.read(output / 'admission.json')
    _pin(admission['plan'], folder / 'plan.json'); _pin(admission['previousDispatch'], prior(plan, folder))
    review_path = _pin(admission['review']); review = m.read(review_path); _pin(review['ownerEvidence'])
    require(admission.get('kind') == 'same-native-first-manual-client' and admission.get('qualificationId') == plan['id'] and
            admission.get('physicalGameStartsAdded') == 0 and admission.get('nativeOwnerReplaced') is False and
            review.get('qualificationId') == plan['id'] and review.get('manualOnlyReviewed') is True and
            admission['statePath'] == str(run / 'state.json') and
            admission['maximumSeconds'] == plan['companion']['maximumSeconds'], 'additive manual admission differs')
    state = m.read(run / 'state.json')
    require(state['runner'] == admission['worker'] and state['game'] == admission['game'] and
            admission['nativeDeadline'] <= admission['at'] + plan['companion']['maximumSeconds'] + 5 and
            admission['at'] < admission['nativeDeadline'] <= admission['outerExpires'] and
            admission['outerExpires'] <= plan['deadlineUtc'], 'original owned identities/deadlines differ')
    retained = admission.get('implementation', [])
    require([(item['originalPath'], item['sha256']) for item in retained] ==
            [(item['path'], item['sha256']) for item in review['implementationPins']], 'retained admission source inventory differs')
    code_pins = []
    for item in retained:
        require(Path(item['path']).parent == output / 'implementation', 'retained admission source escaped')
        code_pin = {'path': item['path'], 'sha256': item['sha256']}; _pin(code_pin); code_pins.append(code_pin)
    pins = [admission['plan'], admission['previousDispatch'], admission['review'], review['ownerEvidence'],
            {'path': str(output / 'admission.json'), 'sha256': m.digest(output / 'admission.json')}, *code_pins]
    return _Context(plan, output), pins

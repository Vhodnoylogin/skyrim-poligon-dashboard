"""Optional finite companion for a new operator tool qualification only.

No baseline admission is reused or relaxed. The qualification's original child
owns the ordinary runner; one pinned data client shares its exact held session.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback

import companion_evidence
from subject_companion_route import _PollingStopped, _matching_live_runs, _retain_client

MAXIMUM_SECONDS = 14100
STARTUP_RESERVE_SECONDS = 240
RESTORATION_RESERVE_SECONDS = 60


def _api():
    import polygon
    return polygon


def _require(condition, message):
    if not condition: raise ValueError('Qualification companion: ' + message)


def _checked_pin(value, base):
    m = _api()
    _require(type(value) is dict and set(value) == {'path', 'sha256'}, 'exact path/SHA256 pin required')
    path = Path(value['path'])
    path = (base / path).resolve() if not path.is_absolute() else path.resolve()
    companion_evidence._path(path)  # Reject linked/reparse-point inputs.
    _require(isinstance(value['sha256'], str) and m.SHA.fullmatch(value['sha256']) and
             path.is_file() and m.digest(path) == value['sha256'], 'input pin differs')
    return {'path': str(path), 'sha256': value['sha256']}


def validate(request, config, scenario, base):
    """Normalize one explicit optional recipe before its immutable registration."""
    if 'companion' not in request: return None
    spec = request['companion']
    _require(type(spec) is dict and set(spec) == {'transport', 'plan', 'sequencer', 'maximumSeconds'},
             'transport, plan, sequencer and maximumSeconds are required')
    maximum = spec['maximumSeconds']
    wall = request.get('maximumWallSeconds')
    _require(type(wall) is int and 900 <= wall <= 14400 and type(maximum) is int and
             1 <= maximum <= min(MAXIMUM_SECONDS, wall - STARTUP_RESERVE_SECONDS - RESTORATION_RESERVE_SECONDS),
             'window must fit the explicit outer wall minus240second startup and60second restoration reserves')
    selected = {name: _checked_pin(spec[name], Path(base)) for name in ('transport', 'plan', 'sequencer')}
    selected['maximumSeconds'] = maximum
    plan = companion_evidence._json(Path(selected['plan']['path']).read_bytes())
    checks = plan.get('checks') if type(plan) is dict else None
    _require(type(checks) is list and 1 <= len(checks) <= 64 and all(type(row) is dict and set(row) == {'name', 'role'} and
             row['role'] == 'subject' and isinstance(row['name'], str) and _api().SAFE_ID.fullmatch(row['name']) for row in checks),
             'plan requires a bounded ordered check inventory')
    names = [row['name'] for row in checks]
    _require(len(set(names)) == len(names), 'duplicate companion check')
    bounds = plan.get('bounds', {})
    _require(bounds.get('maximumSeconds') == maximum and type(bounds.get('maximumCommands')) is int and
             1 <= bounds['maximumCommands'] <= 256, 'pinned plan window/command bound differs')
    _require(config.get('game_edition') == 'se' and config.get('se_new_game_ui') is True and
             not config.get('root_builder') and not config.get('reuse_test_profile'), 'cold-owned SE native startup required')
    settings = config.get('interactive_session', {})
    _require(type(settings) is dict and settings.get('maximumSeconds') == maximum and settings.get('sourceId') == 'operator.actions' and
             isinstance(settings.get('channelConfig'), str) and Path(settings['channelConfig']).is_absolute() and
             {'platform', 'papyrus', 'inspect'} <= set(settings.get('allowedTools', [])) and
             type(settings.get('nativeBindings')) is dict and settings['nativeBindings'], 'exact bounded typed interactive owner configuration required')
    _require(type(plan.get('fixture')) is dict and isinstance(plan['fixture'].get('cell'), str) and
             plan['fixture']['cell'] == scenario.get('cell') and scenario.get('startMode') == 'new-game',
             'companion and common native startup cell/new-game fixture differ')
    # The candidate's own config/scenario validators run in qualification-check.
    # No alternate owner, launch or legacy baseline qualification is admitted here.
    return selected


def order_view(plan):
    """Qualification-only view consumed by the existing strict evidence parser."""
    spec = plan['companion']; declared = _api().read(spec['plan']['path'])
    names = [row['name'] for row in declared['checks']]
    identity = 'qualification-' + plan['id']
    return {'id': identity, 'subjectPlan': {'interface': companion_evidence.INTERFACE,
        'plan': spec['plan'], 'sequencer': spec['sequencer'], 'checks': names, 'maximumSeconds': spec['maximumSeconds']},
        'inputs': [dict(spec[name], role='fixture') for name in ('plan', 'sequencer')],
        'testing': {'start': {'kind': 'check', 'name': names[0]}, 'checks': declared['checks']}}


def _ready(state, worker, expected_config, maximum):
    _require(state.get('runner') == worker, 'native worker changed')
    _require(companion_evidence._identity(state.get('game')) and
             any(row.get('role') == 'game' and row.get('identity') == state['game'] for row in state.get('owned', [])),
             'actual owned game identity unavailable')
    metadata = state.get('interactiveSession', {})
    binding = {'provider': 'skyrim-autotest', 'conversationId': state['id'], 'agentId': 'owned-game-executor'}
    _require(state.get('phase') == 'interactive-session' and state.get('gameplayBootstrap', {}).get('completed') is True and
             state.get('configuration') == expected_config and metadata.get('ready') is True and
             metadata.get('sessionId') == 'game-' + state['id'] and metadata.get('binding') == binding and
             metadata.get('maximumSeconds') == maximum and state.get('done') is not True,
             'exact fresh initialized interactive owner unavailable')
    deadline = state.get('deadline')
    # interactive.run owns maximumSeconds+5 for completion/cleanup bookkeeping;
    # the client independently clamps its work to maximumSeconds and the
    # original native deadline minus that fixed five-second allowance.
    _require(type(deadline) in (int, float) and math.isfinite(deadline) and time.time() < deadline <= time.time() + maximum + 5,
             'original native interactive deadline unavailable/extended')


def run(p, plan, row, folder, runner, run_native):
    """Call the ordinary runner exactly once; own only the separate client handle."""
    m = _api(); spec = plan['companion']; order = order_view(plan)
    output = Path(folder) / 'subject-companion'
    _require(not output.exists(), 'output already exists; no reconnect/replay')
    output.mkdir()
    manifest = output / 'executor-manifest.json'
    m.write(manifest, {'schemaVersion': 1, 'files': plan['executorPins']})
    worker = runner.native.identity(os.getpid())
    _require(companion_evidence._identity(worker) and m.read(Path(folder) / 'worker.json').get('identity') == worker,
             'exact qualification worker required')
    from skyrim_autotest.config import load
    expected_config = load(Path(folder) / 'config.json')
    expires = row['expires']; maximum = spec['maximumSeconds']
    _require(expires - time.time() >= maximum + RESTORATION_RESERVE_SECONDS,
             'original outer window cannot fit declared companion plus restoration before native start')
    p.qualification_verify(p.qualification_show(plan['id']))  # Original pins before native mutations.
    stop = threading.Event(); admission_lock = threading.Lock(); outcome = {}
    client_box = {}

    def save():
        m.write(output / 'dispatch.json', {'schemaVersion': 1, 'orderId': order['id'], 'qualificationId': plan['id'],
            'worker': worker, **outcome})

    def companion():
        child = tracker = None
        try:
            start_end = min(time.monotonic() + STARTUP_RESERVE_SECONDS,
                time.monotonic() + expires - time.time() - maximum - RESTORATION_RESERVE_SECONDS)
            _require(start_end > time.monotonic(), 'insufficient original outer window for declared companion and restoration')
            while not stop.is_set() and time.monotonic() < start_end:
                matches = _matching_live_runs(order, plan['configuration']['runtime'], {}, None, stop, start_end)
                _require(len(matches) <= 1, 'multiple native qualification runs')
                if not matches: stop.wait(.1); continue
                state_path, state = matches[0]
                _require(state.get('runner') == worker and not state.get('done'), 'matching native qualification ended/changed before client admission')
                if state.get('interactiveSession', {}).get('ready') is not True: stop.wait(.1); continue
                _ready(state, worker, expected_config, maximum)
                _require(expires - time.time() >= maximum + RESTORATION_RESERVE_SECONDS,
                         'declared companion plus restoration no longer fits original outer deadline')
                outcome['ownedMO2Admission'] = p.qualification_verify_owned_mo2(
                    p.qualification_show(plan['id']), state_path, state, runner)
                # Re-read through the existing bounded state reader before client spawn.
                fresh = _matching_live_runs(order, plan['configuration']['runtime'], {}, None, stop, start_end)
                _require(len(fresh) == 1 and fresh[0][0] == state_path, 'native owner changed during MO2 admission')
                _ready(fresh[0][1], worker, expected_config, maximum)
                _require(fresh[0][1].get('game') == state['game'], 'game identity changed during MO2 admission')
                _require(expires - time.time() >= maximum + RESTORATION_RESERVE_SECONDS,
                         'MO2 admission consumed the original outer window')
                save()
                args = [sys.executable, spec['transport']['path'], '--executor', plan['executor'],
                    '--executor-manifest', str(manifest), '--executor-manifest-sha256', m.digest(manifest),
                    '--plan', spec['plan']['path'], '--plan-sha256', spec['plan']['sha256'],
                    '--sequencer', spec['sequencer']['path'], '--sequencer-sha256', spec['sequencer']['sha256'],
                    '--runtime', plan['configuration']['runtime'], '--channel-config', expected_config['interactive_session']['channelConfig'],
                    '--order-id', order['id'], '--attempt-id', order['id'], '--worker-identity', json.dumps(worker),
                    '--game-identity', json.dumps(state['game']), '--output', str(output / 'report.json'),
                    '--maximum-seconds', str(maximum)]
                record = {'argv': args, 'source': spec['transport'], 'identity': None, 'timedOut': False,
                          'terminatedOwnedClient': False, 'returncode': None, 'exit': None}
                outcome['client'] = record
                outcome['nativeRun'] = {'path': str(state_path), 'runId': state['id'], 'game': state['game'],
                                        'interactiveDeadline': state['deadline'], 'outerExpires': expires}
                save()  # Durable client intent precedes CreateProcess.
                with (output / 'client.log').open('x', encoding='utf-8') as log:
                    with admission_lock:
                        if stop.is_set(): return
                        for identity in (worker, state['game'], outcome['ownedMO2Admission']['manager']):
                            _require(runner.native.identity(identity['pid']) == identity,
                                     'owned native/manager identity changed before client spawn')
                        owned_mo2 = outcome['ownedMO2Admission']
                        _require(m.digest(owned_mo2['path']) == owned_mo2['liveSha256']
                                 and m.digest(owned_mo2['backup']['path']) == owned_mo2['originalSha256'],
                                 'owned MO2 settings changed before client spawn')
                        _require(time.time() < state['deadline'] and
                                 expires - time.time() >= maximum + RESTORATION_RESERVE_SECONDS,
                                 'original native/outer deadline expired before client spawn')
                        child = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), shell=False)
                        client_box['child'] = child
                    record['identity'], tracker = _retain_client(child); save()
                    # The client also clamps itself to the original native window.
                    # Parent supervision never extends the original frozen outer limit.
                    end = min(expires - RESTORATION_RESERVE_SECONDS, state['deadline'] + 5)
                    while child.poll() is None:
                        if stop.is_set() or time.time() >= end:
                            record['timedOut'] = time.time() >= end
                            record['terminatedOwnedClient'] = True
                            child.terminate()  # Only this retained Popen handle.
                            child.wait(timeout=5)
                            break
                        try: child.wait(timeout=min(.2, max(.001, end - time.time())))
                        except subprocess.TimeoutExpired: pass
                    record['returncode'] = outcome['returncode'] = child.returncode
                return
            if not stop.is_set(): raise TimeoutError('Original qualification startup/client admission window expired')
        except _PollingStopped:
            return
        except Exception as error:
            outcome['error'] = type(error).__name__ + ': ' + str(error)
            outcome['errorDetails'] = {'traceback': traceback.format_exc(), 'operation': getattr(error, 'state_read_operation', 'qualification-companion'),
                'path': getattr(error, 'state_read_path', None), 'errno': getattr(error, 'errno', None), 'winerror': getattr(error, 'winerror', None)}
        finally:
            if child is not None:
                if child.poll() is None:
                    outcome['client']['terminatedOwnedClient'] = True
                    child.terminate(); child.wait(timeout=5)
                outcome['client']['returncode'] = outcome['returncode'] = child.returncode
            if tracker is not None:
                try: outcome['client']['exit'] = tracker.snapshot()
                finally: outcome['client']['handleClose'] = tracker.close()
            save()

    thread = threading.Thread(target=companion, name='qualification-companion', daemon=True)
    thread.start()
    try:
        return run_native()
    finally:
        with admission_lock: stop.set()
        thread.join(timeout=10)
        _require(not thread.is_alive(), 'client did not settle; retain qualification/session barrier')
        save()


def verify_processes_dead(plan, identities):
    """Fresh native inventory, never PID-only death or a cached report flag."""
    _require(all(companion_evidence._identity(value) for value in identities), 'exact child identities required')
    native = Path(plan['executor']) / 'skyrim_autotest/native.py'
    expected = next((item['sha256'] for item in plan['executorPins'] if Path(item['path']) == native), None)
    _require(expected and _api().digest(native) == expected, 'pinned native process observer unavailable')
    code = """import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve();source=root/'skyrim_autotest/native.py'
assert hashlib.sha256(source.read_bytes()).hexdigest()==sys.argv[2],'Native observer source changed'
sys.dont_write_bytecode=True;sys.pycache_prefix=str(root.parent/'qualification-no-bytecode')
sys.path.insert(0,str(root))
from skyrim_autotest import native
assert Path(native.__file__).resolve()==source,'Wrong native process observer'
rows=native.processes();assert isinstance(rows,list) and rows,'Complete native inventory required'
for expected in json.loads(sys.argv[3]):
 matches=[row for row in rows if row.get('pid')==expected['pid']]
 assert len(matches)<=1,'Duplicate native PID'
 if matches:
  current=native.identity(expected['pid'])
  assert current and current['birth']!=expected['birth'],'Owned process alive or identity unavailable'
print(json.dumps({'verified':True}))
"""
    child = subprocess.run([sys.executable, '-B', '-c', code, plan['executor'], expected, json.dumps(identities)],
        capture_output=True, text=True, timeout=30, shell=False)
    _require(child.returncode == 0 and child.stdout.strip() == '{"verified": true}',
             'client/sequencer death unproven: ' + child.stderr[-1200:])
    return True


class _Context:
    def __init__(self, plan, folder): self.plan, self.folder = plan, Path(folder)
    def evidence_dir(self, identity):
        _require(identity == 'qualification-' + self.plan['id'], 'collector qualification identity differs')
        return self.folder
    def attempt_plan(self, order):
        _require(order['id'] == 'qualification-' + self.plan['id'], 'collector native order differs')
        return {'executor': self.plan['executor'], 'configuration': self.plan['configuration'],
                'companionSelection': {'transport': self.plan['companion']['transport']}}
    def verify_companion_processes_dead(self, order, identities):
        self.attempt_plan(order)
        return verify_processes_dead(self.plan, identities)


def collect(p, plan, run):
    if 'companion' not in plan: return None
    folder = p.local / 'qualifications' / plan['id']
    state = _api().read(Path(run) / 'state.json')
    _require(state.get('done') is True and state.get('restored') is True and not state.get('restoreErrors'), 'native completion/restoration required before companion collection')
    summary = companion_evidence.collect(_Context(plan, folder), order_view(plan), run)
    _require(summary is not None, 'strict component evidence unavailable')
    summary.update(scope='tool-qualification-only', subjectModAccepted=False, physicsQualified=False)
    return summary


def successful(plan, packet):
    if 'companion' not in plan: return True
    summary = packet.get('toolCompanion', {})
    names = [row['name'] for row in _api().read(plan['companion']['plan']['path'])['checks']]
    return (summary.get('completed') is True and summary.get('uncertain') is False and summary.get('subjectStarted') is True and
            summary.get('checks') == [{'name': name, 'result': 'passed'} for name in names] and
            summary.get('scope') == 'tool-qualification-only' and summary.get('subjectModAccepted') is False)


def verify_packet(p, plan, packet):
    if 'companion' not in plan: return
    if packet.get('runDirectory') is None:
        _require('toolCompanion' not in packet, 'pre-native packet cannot claim companion results')
        return
    actual = collect(p, plan, packet['runDirectory'])
    _require(actual == packet.get('toolCompanion'), 'retained companion summary changed')
    pins = {str(Path(item['path']).resolve()): item['sha256'] for item in packet.get('files', [])}
    _require(all(pins.get(str(Path(item['path']).resolve())) == item['sha256'] for item in actual['pins']),
             'companion evidence absent from qualification packet')

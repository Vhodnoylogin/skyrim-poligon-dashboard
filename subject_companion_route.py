"""Explicit first-attempt SE file plans over an unchanged owned executor.

This route admits subject capabilities under test; it never relabels the
baseline's core lifecycle evidence as qualification of those capabilities.
"""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
import threading
import time


def api():
    import polygon
    return polygon


def selected(order):
    return order.get('schemaVersion') == 2 and order.get('subjectPlan', {}).get('interface') == 'polygon-file-plan/1'


def init(p):
    with p.connect() as con:
        con.executescript('''CREATE TABLE IF NOT EXISTS companion_bindings
          (id TEXT PRIMARY KEY, request TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS companion_admissions (id TEXT PRIMARY KEY, review TEXT NOT NULL);''')


def pin(value):
    m = api()
    if type(value) is not dict or set(value) != {'path', 'sha256'} or not Path(value['path']).is_absolute():
        raise ValueError('Absolute exact companion pin required')
    path = Path(value['path'])
    for part in (path, *path.parents):
        if part.exists() and (part.is_symlink() or bool(getattr(part.lstat(), 'st_file_attributes', 0) & 0x400)):
            raise ValueError('Companion pins cannot traverse links/reparse points')
    if not m.SHA.fullmatch(value.get('sha256', '')) or m.digest(path) != value['sha256']:
        raise ValueError('Companion pin changed: ' + str(path))
    return path.resolve()


def normalize_subject(order, source):
    """Resolve immutable subject files without compiling provider selectors."""
    if not selected(order): return
    m = api(); spec = order['subjectPlan']
    for key in ('plan', 'sequencer'):
        spec[key]['path'] = str((source.parent / spec[key]['path']).absolute())
        spec[key]['path'] = str(pin(spec[key]))
    if Path(spec['sequencer']['path']).suffix != '.py':
        raise ValueError('Origin sequencer must be an explicitly pinned Python source')
    origin = m.read(spec['plan']['path'])
    m.subject_contract.identity(origin)  # Refuse nonfinite/non-JSON origin data before launch.
    cases, checks = origin.get('cases'), origin.get('checks')
    declared = []
    if isinstance(cases, list):
        if not all(isinstance(x, dict) for x in cases): raise ValueError('Malformed origin case checklist')
        declared.append([x.get('id') for x in cases])
    if isinstance(checks, list):
        if not all(isinstance(x, dict) and x.get('role') == 'subject' for x in checks):
            raise ValueError('Malformed origin subject checklist')
        declared.append([x.get('name') for x in checks])
    if not declared or any(names != spec['checks'] for names in declared):
        raise ValueError('Exact origin case checklist/order required')
    if origin.get('bounds', {}).get('maximumSeconds') != spec['maximumSeconds']:
        raise ValueError('Origin plan and ordinary execution window differ')
    testing = order['testing']
    if (testing['start'] != {'kind': 'check', 'name': spec['checks'][0]} or
            testing['checks'] != [{'name': x, 'role': 'subject'} for x in spec['checks']]):
        raise ValueError('File plan requires the exact first-case boundary and complete subject checklist')


def scenario(order):
    return {'schemaVersion': 1, **order['subjectPlan']['fixture'], 'steps': [
        {'name': 'companion-core-preparation', 'tool': 'platform',
         'args': {'operation': 'state.read'}, 'timeout': 20,
         'assert': [{'path': 'world.ready', 'equals': True}]}]}


def normalize(path):
    m = api(); r = m.read(path)
    fields = {'schemaVersion', 'kind', 'orderId', 'subjectOrderSha256', 'executor', 'configuration',
              'transport', 'qualificationId', 'baselinePacket', 'holdId', 'ownerAuthorization',
              'subjectCapabilitiesUnderTest', 'verifiedBy', 'reason'}
    if set(r) != fields or r['schemaVersion'] != 1 or r['kind'] != 'operator-subject-companion':
        raise ValueError('Exact explicit companion selection required')
    for key in ('orderId', 'qualificationId', 'holdId'):
        if not isinstance(r[key], str) or not m.SAFE_ID.fullmatch(r[key]): raise ValueError('Safe exact companion identities required')
    if r['subjectCapabilitiesUnderTest'] is not True:
        raise ValueError('Subject capabilities must remain explicitly under test')
    for key in ('verifiedBy', 'reason'): m.required_string(r, key)
    m.owner_evidence(r, path, require_deadline=False)
    r['executor'] = str((path.parent / m.required_string(r, 'executor')).resolve())
    for key in ('configuration', 'transport', 'baselinePacket'):
        r[key]['path'] = str((path.parent / r[key]['path']).absolute()); r[key]['path'] = str(pin(r[key]))
    return r


def find(p, order, con=None):
    if not selected(order): return None
    m = api()
    if con is None:
        with p.connect() as connection: return find(p, order, connection)
    row = con.execute('SELECT * FROM companion_bindings WHERE id=?', (order['id'],)).fetchone()
    if not row: raise ValueError('File plan needs separate explicit companion-bind selection')
    path = pin({'path': row['path'], 'sha256': row['sha256']}); r = normalize(path)
    if json.dumps(r, sort_keys=True) != row['request'] or r['subjectOrderSha256'] != m.subject_contract.identity(order):
        raise ValueError('Companion selection/order changed')
    return {'request': {'path': str(path), 'sha256': row['sha256']}, **r}


def admission(p, key):
    m = api()
    with p.connect() as con: row = con.execute('SELECT review FROM companion_admissions WHERE id=?', (key,)).fetchone()
    if not row: return None
    saved = json.loads(row['review']); value = {'path': saved['path'], 'sha256': saved['sha256']}
    path = pin(value); current = m.read(path)
    m.owner_evidence(current, path, require_deadline=False)
    if current != saved['review']: raise ValueError('Companion admission changed')
    return value


def baseline(p, selection):
    """Only a released, fully collected core baseline; not subject qualification."""
    m = api(); row = p.qualification_show(selection['qualificationId'])
    if row['status'] != 'released' or not row.get('packet') or json.loads(row['packet']) != selection['baselinePacket']:
        raise ValueError('Exact released baseline qualification/packet required')
    q = p.qualification_verify(row, authority=False); packet = m.read(pin(selection['baselinePacket']))
    if (Path(q['executor']).resolve() != Path(selection['executor']).resolve() or
            packet.get('executionOutcome') != 'passed' or packet.get('actualGameStarts') != 1 or
            packet.get('restored') is not True or packet.get('collectionFinished') is not True or
            packet.get('collectionFindings') or not p.qualification_successful_result(q, packet)):
        raise ValueError('Successful restored single-game core baseline required')
    from qualification import inventory
    if inventory(selection['executor']) != q['executorPins']:
        raise ValueError('Companion requires the byte-identical frozen baseline executor')
    for entry in packet['files']:
        if m.digest(entry['path']) != entry['sha256']: raise ValueError('Baseline collected evidence changed')
    run = Path(packet['runDirectory']); state = m.read(run / 'state.json')
    worker = m.read(p.local / 'qualifications' / selection['qualificationId'] / 'worker.json')['identity']
    child = m.read(p.local / 'qualifications' / selection['qualificationId'] / 'child-exit.json')
    if (type(child.get('returncode')) is not int or child['returncode'] != 0 or child.get('timeout') or
            state.get('done') is not True or state.get('restored') is not True or state.get('restoreErrors') or
            state.get('runner') != worker or p.native_game_starts(state) != 1 or
            state.get('order', {}).get('id') != 'qualification-' + selection['qualificationId']):
        raise ValueError('Ended exact baseline worker/run required')
    archive = run / 'test-profile'
    pins = [{'path': str(f), 'sha256': m.digest(f)} for f in sorted(archive.rglob('*')) if f.is_file()]
    if (not pins or pins != packet.get('profileArchivePins') or
            Path(state.get('profileArchive', '')).resolve() != archive.resolve() or Path(state['testProfile']).exists()):
        raise ValueError('Baseline archived/removed profile required')
    return q, packet, state, worker


def configuration(p, order, selection, q):
    from order_platform import isolated_config
    m = api(); cfg = isolated_config(selection['executor'], pin(selection['configuration']), scenario(order))
    if cfg.get('game_edition') != 'se' or cfg.get('se_new_game_ui') is not True or cfg.get('root_builder') or cfg.get('reuse_test_profile'):
        raise ValueError('Companion supports one cold-owned initialized SE game only')
    # Qualification stores the original JSON, whereas config.load supplies
    # defaults and resolves paths relative to that file. Normalize both inputs
    # through the same frozen loader, retaining the original pinned base path.
    baseline_path = Path(q['configPath']).resolve()
    baseline_pins = [x for x in q['pins'] if Path(x['path']).resolve() == baseline_path]
    if len(baseline_pins) != 1 or m.read(pin(baseline_pins[0])) != q['configuration']:
        raise ValueError('Exact pinned raw baseline configuration required')
    old = isolated_config(selection['executor'], baseline_path, scenario(order))
    delta = {'runtime', 'interactive_session'}
    if {k: v for k, v in cfg.items() if k not in delta} != {k: v for k, v in old.items() if k not in delta}:
        raise ValueError('Core baseline configuration changed outside runtime/interactive subject data')
    interactive = cfg.get('interactive_session', {})
    allowed = {'maximumSeconds', 'nativeBindings'}
    prior = old.get('interactive_session', {})
    if {k: v for k, v in interactive.items() if k not in allowed} != {k: v for k, v in prior.items() if k not in allowed}:
        raise ValueError('Baseline interactive channel/source/allowed tools changed')
    if (not interactive.get('nativeBindings') or interactive.get('sourceId') != 'operator.actions' or
            interactive.get('maximumSeconds') != order['subjectPlan']['maximumSeconds']):
        raise ValueError('Explicit bounded subject binding policy required')
    return cfg


def register(p, path):
    m = api(); path = Path(path).resolve(); r = normalize(path); key = r['orderId']
    row = p.get(key); order = json.loads(row['request'])
    if (not selected(order) or row['status'] != 'queued' or order.get('cycle') or
            r['subjectOrderSha256'] != m.subject_contract.identity(order)):
        raise ValueError('Exact untouched first solo file-plan subject required')
    q, _, _, _ = baseline(p, r); configuration(p, order, r, q); p.verify_inputs(order)
    canonical = json.dumps(r, sort_keys=True)
    with p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        prior = con.execute('SELECT * FROM companion_bindings WHERE id=?', (key,)).fetchone()
        if prior:
            if (prior['request'], prior['path'], prior['sha256']) != (canonical, str(path), m.digest(path)):
                raise ValueError('Companion selection is immutable')
            return {'id': key, 'duplicate': True, 'launch': False}
        current = con.execute('SELECT status,request FROM jobs WHERE id=?', (key,)).fetchone()
        if not current or current['status'] != 'queued' or current['request'] != row['request']:
            raise ValueError('Queued subject changed during companion selection')
        if (con.execute('SELECT id FROM platform_attempts WHERE id=?', (key,)).fetchone() or
                con.execute('SELECT id FROM attempts WHERE id=?', (key,)).fetchone() or
                con.execute('SELECT order_id FROM session_members WHERE order_id=?', (key,)).fetchone() or
                con.execute('SELECT id FROM operator_platform_bindings WHERE order_id=?', (key,)).fetchone()):
            raise ValueError('Prepared/dispatched/grouped subject cannot select a companion')
        if p.qualification_busy(con) or con.execute("SELECT id FROM qualifications WHERE status IN ('prepared','running')").fetchone():
            raise ValueError('Active owner retains companion admission barrier')
        if [x['id'] for x in con.execute('SELECT id FROM pipeline_holds')] != [r['holdId']]:
            raise ValueError('Exact sole reviewed preparation hold required')
        con.execute('INSERT INTO companion_bindings VALUES(?,?,?,?)', (key, canonical, str(path), m.digest(path)))
        p.event(con, key, 'companion_bound', canonical)
    return {'id': key, 'launch': False, 'globalHostChanged': False, 'subjectCapabilitiesQualified': False}


def freeze(p, order):
    m = api(); selection = find(p, order); q, _, _, _ = baseline(p, selection)
    cfg = configuration(p, order, selection, q); review = admission(p, order['id'])
    if not review: raise ValueError('Atomic companion admission required before preparation')
    pins = []
    def add(value):
        path = pin(value); item = {'path': str(path), 'sha256': value['sha256']}
        if item not in pins: pins.append(item)
    for item in q['executorPins'] + q['pins']: add(item)
    for item in (selection['request'], selection['configuration'], selection['transport'], selection['baselinePacket'], review,
                 order['subjectPlan']['plan'], order['subjectPlan']['sequencer']): add(item)
    auth = selection['ownerAuthorization']; add({'path': auth['path'], 'sha256': auth['sha256']})
    for path in sorted(m.HERE.glob('*.py')): add({'path': str(path), 'sha256': m.digest(path)})
    for entry in cfg.get('staged_plugins', []): add({'path': entry['source'], 'sha256': entry['sha256']})
    core = {x['path']: x['sha256'] for x in q['executorPins'] + q['pins']}
    for entry in order['inputs']:
        if entry['path'] in core and (entry['role'] != 'dependency' or entry['sha256'] != core[entry['path']]):
            raise ValueError('Subject cannot impersonate a core baseline provider')
    plan = {'schemaVersion': 1, 'interface': 'polygon-file-plan/1', 'orderId': order['id'],
            'subjectOrderSha256': m.subject_contract.identity(order), 'subjectSpecificationSha256': m.subject_contract.subject_identity(order),
            'executor': selection['executor'], 'configuration': cfg, 'scenario': scenario(order), 'pins': pins,
            'companionSelection': selection, 'companionAdmission': review, 'baselineCoreOnly': True,
            'subjectCapabilitiesQualified': False, 'preparedAt': time.time()}
    with p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        if con.execute('SELECT status FROM jobs WHERE id=?', (order['id'],)).fetchone()[0] != 'running':
            raise ValueError('Companion preparation requires the atomic claimed order')
        canonical = json.dumps(plan, sort_keys=True, ensure_ascii=False)
        con.execute('INSERT INTO platform_attempts VALUES(?,?,?)', (order['id'], canonical, m.subject_contract.identity(plan)))
    m.write(p.evidence_dir(order['id']) / 'platform-plan.json', plan)
    return verify(p, order)


def verify(p, order, require_file=True):
    m = api(); plan = p.attempt_plan(order)
    if require_file and m.read(p.evidence_dir(order['id']) / 'platform-plan.json') != plan:
        raise ValueError('Companion platform plan changed')
    if find(p, order) != plan['companionSelection'] or admission(p, order['id']) != plan['companionAdmission']:
        raise ValueError('Companion selection/admission changed')
    for entry in plan['pins']: pin(entry)
    from qualification import inventory
    actual = inventory(plan['executor'])
    expected = [x for x in plan['pins'] if Path(x['path']).is_relative_to(Path(plan['executor']))]
    if actual != sorted(expected, key=lambda x: x['path']):
        # inventory's order follows Path ordering, so compare by exact path/hash pairs.
        if {(x['path'], x['sha256']) for x in actual} != {(x['path'], x['sha256']) for x in expected}:
            raise ValueError('Frozen companion executor inventory changed')
    return plan


def verify_processes_dead(p, order, identities):
    """Fresh isolated read-only inventory; unavailable same-PID identity refuses."""
    plan = verify(p, order)
    code = """import json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root))
from skyrim_autotest import native
assert Path(native.__file__).resolve()==root/'skyrim_autotest/native.py','Wrong native observer'
identities=json.loads(sys.argv[2]);rows=native.processes()
assert isinstance(rows,list) and rows,'Complete native inventory required'
for expected in identities:
 assert type(expected)==dict and set(expected)=={'pid','birth','path'} and type(expected['pid'])==int and expected['pid']>0 and type(expected['birth'])==int and expected['birth']>0 and expected['path'],'Exact client identity required'
 matches=[r for r in rows if r['pid']==expected['pid']]
 assert len(matches)<=1,'Duplicate inventory PID'
 if matches:
  actual=native.identity(expected['pid'])
  assert actual and actual['birth']!=expected['birth'],'Owned client alive or identity unavailable'
print(json.dumps({'verified':True}))
"""
    child = subprocess.run([sys.executable, '-B', '-c', code, plan['executor'], json.dumps(identities)],
                           capture_output=True, text=True, timeout=30, shell=False)
    if child.returncode != 0 or json.loads(child.stdout) != {'verified': True}:
        raise ValueError('Companion process death unavailable: ' + child.stderr[-1500:])
    return True


def _retain_client(child):
    # Popen owns this handle from CreateProcess. All identity components are read
    # from it, before opening a separate read/synchronize telemetry handle.
    from skyrim_autotest import process_exit
    identity = process_exit._Win32().identity(child._handle)
    if identity['pid'] != child.pid: raise ValueError('Retained client PID differs from created process')
    tracker = process_exit.capture(identity)
    if tracker.snapshot()['identityVerified'] is not True:
        tracker.close(); raise ValueError('Owned client exit handle identity unavailable')
    return identity, tracker


def execute(p, path):
    """One reviewed preparation-hold transfer, without changing legacy admission."""
    m = api(); path = Path(path).resolve(); r = m.read(path)
    required = {'schemaVersion', 'kind', 'orderId', 'binding', 'baselinePacket', 'ownerAuthorization', 'verifiedBy', 'reason',
                'preparationReviewed', 'restorationReviewed', 'archiveReviewed', 'exactOnlySubjectReviewed', 'subjectCapabilitiesUnderTest'}
    if (set(r) != required or r['schemaVersion'] != 1 or r['kind'] != 'operator-subject-companion-admission' or
            any(r[key] is not True for key in required if key.endswith('Reviewed') or key == 'subjectCapabilitiesUnderTest')):
        raise ValueError('Explicit reviewed companion admission required')
    m.owner_evidence(r, path, require_deadline=False)
    for key in ('verifiedBy', 'reason'): m.required_string(r, key)
    key = r['orderId']; order = json.loads(p.get(key)['request']); selection = find(p, order)
    from order_platform import authority, activate
    if (r['binding'] != selection['request'] or r['baselinePacket'] != selection['baselinePacket'] or
            authority(r) != authority(selection)):
        raise ValueError('Exact current owner, binding and baseline review required')
    pin(r['binding']); pin(r['baselinePacket'])
    canonical = json.dumps({'path': str(path), 'sha256': m.digest(path), 'review': r}, sort_keys=True)
    with p.connect() as con:
        prior = con.execute('SELECT review FROM companion_admissions WHERE id=?', (key,)).fetchone()
    if prior:
        if prior['review'] != canonical: raise ValueError('Companion admission is immutable')
        return {'id': key, 'status': 'already_admitted', 'rerun': False}
    q, _, state, worker = baseline(p, selection); cfg = configuration(p, order, selection, q)
    runner = activate(selection['executor'])
    with runner.native.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        if find(p, order, con) != selection: raise ValueError('Companion binding changed during admission')
        current_baseline = con.execute('SELECT * FROM qualifications WHERE id=?', (selection['qualificationId'],)).fetchone()
        if not current_baseline or current_baseline['status'] != 'released' or json.loads(current_baseline['packet']) != selection['baselinePacket']:
            raise ValueError('Released core baseline changed before admission')
        p.qualification_verify(dict(current_baseline), authority=False)
        if p.qualification_busy(con) or con.execute("SELECT id FROM qualifications WHERE status IN ('prepared','running')").fetchone():
            raise ValueError('Another active owner retains the barrier')
        if [x['id'] for x in con.execute('SELECT id FROM pipeline_holds')] != [selection['holdId']]:
            raise ValueError('Exact sole preparation hold required')
        waiting = con.execute("SELECT j.id,r.release_id FROM jobs j JOIN released_orders r ON r.id=j.id WHERE j.status IN ('queued','running','waiting_player','session_waiting')").fetchall()
        if len(waiting) != 1 or waiting[0]['id'] != key or p.get(key)['status'] != 'queued':
            raise ValueError('Only the exact released queued subject may be admitted')
        release = con.execute('SELECT authorization FROM releases WHERE id=?', (waiting[0]['release_id'],)).fetchone()
        if authority(json.loads(release[0])) != authority(r): raise ValueError('Current one-shot human release required')
        if (con.execute("SELECT id FROM retry_attempts WHERE status='queued'").fetchone() or
                con.execute("SELECT id FROM game_sessions WHERE status='queued'").fetchone() or
                con.execute("SELECT id FROM jobs WHERE status IN ('queued','session_waiting') AND json_extract(request,'$.cycle') IS NOT NULL").fetchone()):
            raise ValueError('Other queued cycle/retry/shared work retains barrier')
        rows = runner.native.processes()
        if not isinstance(rows, list) or not rows or any(x['name'].lower() in {
                'skyrimse.exe', 'skyrimvr.exe', 'skse64_loader.exe', 'sksevr_loader.exe', 'vrserver.exe', 'vrcompositor.exe'} for x in rows):
            raise ValueError('Current game/VR or unavailable inventory blocks admission')
        for ident in [worker] + [x['identity'] for x in state.get('owned', [])]:
            if (type(ident) is not dict or type(ident.get('pid')) is not int or type(ident.get('birth')) is not int or
                    ident['pid'] <= 0 or ident['birth'] <= 0 or not ident.get('path') or runner.native.alive(ident) or
                    any(x['pid'] == ident['pid'] and runner.native.identity(ident['pid']) is None for x in rows)):
                raise ValueError('Baseline worker/owned identity alive or unknown')
        runtimes = {Path(cfg['runtime']), Path(q['configuration']['runtime'])}
        if p.host().get('runnerConfig'): runtimes.add(Path(m.read(p.host()['runnerConfig'])['runtime']))
        for runtime in runtimes:
            for file in (runtime / 'runs').glob('*/state.json'):
                if m.read(file).get('done') is not True: raise ValueError('Unfinished native session retains barrier')
        if m.digest(path) != json.loads(canonical)['sha256']: raise ValueError('Companion admission review changed')
        p.verify_inputs(order)
        con.execute('DELETE FROM pipeline_holds WHERE id=?', (selection['holdId'],))
        p.check_launch_authorization(order, connection=con)
        con.execute("UPDATE jobs SET status='running',note='' WHERE id=?", (key,))
        con.execute('INSERT INTO companion_admissions VALUES(?,?)', (key, canonical))
        p.event(con, key, 'companion_subject_admitted', canonical)
        p.event(con, selection['holdId'], 'reviewed_preparation_transferred_to_exact_subject', canonical)
        row = dict(con.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone())
    return p.execute_claimed(row)


def run(p, order, plan, runner):
    """Original main thread owns the runner; a bounded companion only exchanges data."""
    m = api(); folder = p.evidence_dir(order['id']); output = folder / 'subject-companion'
    if output.exists(): raise ValueError('Companion output exists; reconnect/replay refused')
    output.mkdir()
    inventory = [{'path': x['path'], 'sha256': x['sha256']} for x in plan['pins']
                 if Path(x['path']).is_relative_to(Path(plan['executor']))]
    manifest = output / 'executor-manifest.json'; m.write(manifest, {'schemaVersion': 1, 'files': inventory})
    worker = runner.native.identity(__import__('os').getpid())
    if (type(worker) is not dict or set(worker) != {'pid', 'birth', 'path'} or
            type(worker['pid']) is not int or worker['pid'] <= 0 or
            type(worker['birth']) is not int or worker['birth'] <= 0 or not worker['path']):
        raise ValueError('Exact companion/native worker identity required before launch')
    stop = threading.Event(); outcome = {}
    def companion():
        try:
            end = time.monotonic() + 600
            while not stop.is_set() and time.monotonic() < end:
                matches = p.matching_runs(order)
                if len(matches) > 1: raise ValueError('Multiple native runs for one companion subject')
                if matches:
                    _, state = matches[0]
                    if state.get('runner') != worker: raise ValueError('Companion native worker identity mismatch')
                    if state.get('interactiveSession', {}).get('ready') is True:
                        spec = order['subjectPlan']; selection = plan['companionSelection']
                        args = [sys.executable, str(pin(selection['transport'])), '--executor', plan['executor'],
                                '--executor-manifest', str(manifest), '--executor-manifest-sha256', m.digest(manifest),
                                '--plan', spec['plan']['path'], '--plan-sha256', spec['plan']['sha256'],
                                '--sequencer', spec['sequencer']['path'], '--sequencer-sha256', spec['sequencer']['sha256'],
                                '--runtime', plan['configuration']['runtime'], '--channel-config', plan['configuration']['interactive_session']['channelConfig'],
                                '--order-id', order['id'], '--attempt-id', order['id'], '--worker-identity', json.dumps(worker),
                                '--game-identity', json.dumps(state['game']), '--output', str(output / 'report.json'),
                                '--maximum-seconds', str(spec['maximumSeconds'])]
                        record = {'argv': args, 'source': selection['transport'], 'identity': None,
                                  'timedOut': False, 'terminatedOwnedClient': False, 'returncode': None, 'exit': None}
                        outcome['client'] = record
                        with (output / 'client.log').open('x', encoding='utf-8') as log:
                            child = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT,
                                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), shell=False)
                            tracker = None
                            try:
                                record['identity'], tracker = _retain_client(child)
                                m.write(output / 'dispatch.json', {'schemaVersion': 1, 'orderId': order['id'], 'worker': worker, **outcome})
                                try:
                                    child.wait(timeout=spec['maximumSeconds'] + 60)
                                except subprocess.TimeoutExpired:
                                    record['timedOut'] = True
                                    record['terminatedOwnedClient'] = True
                                    child.terminate()  # Only the retained handle returned by our own Popen.
                                    child.wait(timeout=10)
                            finally:
                                if child.poll() is None and not record['terminatedOwnedClient']:
                                    record['terminatedOwnedClient'] = True
                                    child.terminate()
                                    child.wait(timeout=10)
                                record['returncode'] = outcome['returncode'] = child.returncode
                                if tracker is not None:
                                    try: record['exit'] = tracker.snapshot()
                                    finally: record['handleClose'] = tracker.close()
                        return
                    if state.get('done'): return
                stop.wait(.1)
            if not stop.is_set(): raise TimeoutError('Owned interactive readiness did not arrive within startup bound')
        except Exception as error:
            outcome['error'] = type(error).__name__ + ': ' + str(error)
        finally:
            m.write(output / 'dispatch.json', {'schemaVersion': 1, 'orderId': order['id'], 'worker': worker, **outcome})
    thread = threading.Thread(target=companion, name='subject-companion', daemon=True); thread.start()
    try:
        return runner.run(p.source_profile(order, runner), folder / 'scenario.json', restart_idle_mo2=True,
                          order={'id': order['id'], 'owner': order['sourceChat']})
    finally:
        stop.set(); thread.join(timeout=order['subjectPlan']['maximumSeconds'] + 65)
        if thread.is_alive(): raise ValueError('Companion did not settle; preserve native/session barrier')
        m.write(output / 'dispatch.json', {'schemaVersion': 1, 'orderId': order['id'], 'worker': worker, **outcome})

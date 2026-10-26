"""One separately reviewed file-plan replay after the recorded selector failure."""
from __future__ import annotations
import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import time

KIND = 'companion-post-start-tooling'
FIELDS = {'schemaVersion', 'kind', 'restartMode', 'id', 'orderId', 'previousAttemptId',
          'previousPacketSha256', 'previousReport', 'technicalFailure', 'launchAccounting',
          'ownerAuthority', 'authorityReview', 'companionSelection', 'configuration', 'repair'}
PINS = ('previousReport', 'technicalFailure', 'launchAccounting', 'ownerAuthority',
        'companionSelection', 'configuration', 'repair')


def api():
    import polygon
    return polygon


def is_ticket(ticket):
    return isinstance(ticket, dict) and ticket.get('kind') == KIND


def require(condition, reason):
    if not condition: raise ValueError('Companion post-start: ' + reason)


def pin(value):
    from subject_companion_route import pin as checked
    return checked(value)


def init(p):
    with p.connect() as con:
        con.executescript('''CREATE TABLE IF NOT EXISTS companion_poststart_tickets
          (id TEXT PRIMARY KEY, path TEXT NOT NULL, sha256 TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS companion_poststart_admissions
          (id TEXT PRIMARY KEY, review TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS companion_poststart_dispatches
          (id TEXT PRIMARY KEY, started REAL NOT NULL);''')


def normalize(path):
    m = api(); path = Path(path).resolve(); value = m.read(path)
    require(type(value) is dict and set(value) == FIELDS and type(value['schemaVersion']) is int and
            value['schemaVersion'] == 1 and value['kind'] == KIND and value['restartMode'] == 'initial-fixture',
            'exact separate full-replay ticket required')
    for key in ('id', 'orderId', 'previousAttemptId'):
        require(isinstance(value[key], str) and m.SAFE_ID.fullmatch(value[key]), 'safe exact identifiers required')
    require(len({value[key] for key in ('id', 'orderId', 'previousAttemptId')}) == 3, 'distinct attempt identities required')
    require(isinstance(value['previousPacketSha256'], str) and m.SHA.fullmatch(value['previousPacketSha256']),
            'exact predecessor packet hash required')
    for key in PINS:
        require(type(value[key]) is dict and set(value[key]) == {'path', 'sha256'}, 'exact pinned ' + key + ' required')
        value[key]['path'] = str((path.parent / value[key]['path']).resolve())
        pin(value[key])
    return value


def registered(p, attempt_id):
    m = api(); row = p.retry_show(attempt_id); ticket = json.loads(row['request'])
    require(ticket.get('kind') == KIND and ticket.get('id') == attempt_id and ticket.get('orderId') == row['order_id'],
            'registered companion attempt identity differs')
    with p.connect() as con:
        source = con.execute('SELECT path,sha256 FROM companion_poststart_tickets WHERE id=?', (attempt_id,)).fetchone()
    require(source is not None, 'immutable ticket source missing')
    source_pin = {'path': source['path'], 'sha256': source['sha256']}
    require(normalize(pin(source_pin)) == ticket, 'registered ticket source changed')
    return row, ticket, source_pin


def authority(p, ticket, dispatch=True):
    """A new prospective review; never reuse the consumed predecessor ticket."""
    m = api()
    from order_platform import authority as owner
    from subject_companion_route import find
    order = json.loads(p.get(ticket['orderId'])['request']); selection = find(p, order)
    require(ticket['companionSelection'] == selection['request'], 'original selection changed')
    document = m.read(pin(ticket['ownerAuthority']))
    # Historical collection is valid after expiry; launch-time authority is not.
    evidence_document = copy.deepcopy(document)
    if not dispatch: evidence_document.pop('deadlineUtc', None)
    m.owner_evidence(evidence_document, pin(ticket['ownerAuthority']), require_deadline=dispatch)
    require(document.get('state') == 'active' and document.get('orderIds') == [order['id']] and
            owner(document) == owner(selection), 'current exact actual human scope required')
    review = ticket['authorityReview']
    required = {'verifiedBy', 'reason', 'retryPermitted', 'postStartContinuationPermitted', 'fullReplayReviewed',
                'preservePriorCoverage', 'previousAttemptBudgetConsumed', 'maxAdditionalAttempts',
                'subjectActualLaunchesBefore', 'maximumSubjectActualLaunches', 'historicalGlobalActualLaunches'}
    require(type(review) is dict and set(review) == required and
            all(review[key] is True for key in ('retryPermitted', 'postStartContinuationPermitted', 'fullReplayReviewed',
                'preservePriorCoverage', 'previousAttemptBudgetConsumed')) and
            type(review['maxAdditionalAttempts']) is int and review['maxAdditionalAttempts'] == 1 and
            type(review['subjectActualLaunchesBefore']) is int and review['subjectActualLaunchesBefore'] == 1 and
            type(review['maximumSubjectActualLaunches']) is int and review['maximumSubjectActualLaunches'] == 2 and
            review['historicalGlobalActualLaunches'] is None, 'review exactly one additional subject start, cumulative 1 to 2, global unknown')
    for key in ('verifiedBy', 'reason'): m.required_string(review, key)
    old = json.loads(p.retry_show(ticket['previousAttemptId'])['request'])
    require(ticket['ownerAuthority'] != old.get('ownerAuthority'), 'spent predecessor authority cannot be reused')
    deadline = document.get('deadlineUtc')
    require(type(deadline) in (int, float) and math.isfinite(deadline), 'separate finite prospective deadline required')
    return order, selection


def predecessor(p, ticket, allow_current=False):
    """Keep exact ended partial coverage, repaired collection and registered report."""
    m = api(); row = p.get(ticket['orderId']); order = json.loads(row['request'])
    require(row['status'] == 'blocked' and order.get('schemaVersion') == 2 and order.get('mode') == 'automatic' and
            not order.get('cycle') and order.get('subjectPlan', {}).get('interface') == 'polygon-file-plan/1',
            'same blocked solo immutable file plan required')
    prior = p.retry_show(ticket['previousAttemptId']); prior_ticket = json.loads(prior['request'])
    require(prior['order_id'] == order['id'] and prior['status'] in ('recorded', 'blocked') and
            prior_ticket.get('kind') == 'companion-pre-session', 'exact ended first companion attempt required')
    require(prior.get('packet') and m.digest(prior['packet']) == ticket['previousPacketSha256'], 'predecessor raw packet changed')
    packet = p.verify_retry_packet(prior)
    require(packet.get('orderId') == order['id'] and packet.get('attemptId') == prior['id'] and
            packet.get('subjectOrderSha256') == m.subject_contract.identity(order) and
            packet.get('executionOutcome') in ('failed', 'blocked') and packet.get('restored') is True and packet.get('runDirectory'),
            'ended native predecessor and unchanged full subject required')
    require(packet.get('collectionRepair') and packet.get('originalPacket', {}).get('sha256') == ticket['previousPacketSha256'],
            'verified additive ended collection repair required')
    pin({key: packet['collectionRepair'][key] for key in ('path', 'sha256')})
    require(prior.get('report') and Path(prior['report']).resolve() == pin(ticket['previousReport']), 'registered predecessor final report required')
    report = p.verify_retry_report(prior)
    require(report.get('collectionFinished') is True and report.get('packetSha256') == ticket['previousPacketSha256'] and
            report.get('testResult', {}).get('testingStarted') is True, 'registered final report must prove ended collection and factual start')
    projection = p.test_projection(order, packet)
    require(projection.get('testingStarted') is True and projection.get('interruptionObserved') is True and
            not projection.get('subjectMismatchObserved'), 'corroborated tooling interruption required; subject mismatch is ineligible')
    run = Path(packet['runDirectory']).resolve(); state = m.read(run / 'state.json')
    require(state.get('order', {}).get('id') == order['id'] and state['order'].get('attemptId') == prior['id'] and
            state['order'].get('subjectOrderId') == order['id'] and state.get('done') is True and
            state.get('restored') is True and not state.get('restoreErrors') and p.native_game_starts(state) == 1,
            'exact original-plus-attempt native identity, one start and restoration required')
    proof = m.read(pin(ticket['technicalFailure']))
    require(proof.get('schemaVersion') == 1 and proof.get('classification') == 'confirmed-tooling-post-start-failure' and
            proof.get('orderId') == order['id'] and proof.get('attemptId') == prior['id'] and
            proof.get('packetSha256') == ticket['previousPacketSha256'] and proof.get('reportSha256') == ticket['previousReport']['sha256'] and
            Path(proof.get('run', '')).resolve() == run and all(proof.get(key) is True for key in ('subjectStarted', 'done', 'restored', 'collectionFinished')) and
            proof.get('restoreErrors') == [], 'tooling proof must bind exact final packet/report/restoration')
    native_pins = {str(Path(item['path']).resolve()): item['sha256'] for item in packet['files']}
    reviewed = set()
    require(isinstance(proof.get('evidence'), list) and proof['evidence'], 'pinned native tooling evidence required')
    for item in proof['evidence']:
        path = pin(item); require(native_pins.get(str(path)) == item['sha256'], 'tooling proof evidence outside predecessor packet')
        reviewed.add(path)
    require({run / name for name in ('state.json', 'result.json', 'steps.jsonl')} <= reviewed, 'native state/result/steps must be reviewed')
    for key in ('verifiedBy', 'reason'): m.required_string(proof, key)
    accounting = m.read(pin(ticket['launchAccounting']))
    require(accounting.get('schemaVersion') == 1 and accounting.get('scope') == 'same-immutable-order' and
            accounting.get('orderId') == order['id'] and accounting.get('previousAttemptId') == prior['id'] and
            accounting.get('previousPacketSha256') == ticket['previousPacketSha256'] and
            type(accounting.get('previousAttemptActualLaunches')) is int and accounting['previousAttemptActualLaunches'] == 1 and
            type(accounting.get('subjectActualLaunchesBefore')) is int and accounting['subjectActualLaunchesBefore'] == 1 and
            accounting.get('historicalGlobalActualLaunches', 'missing') is None, 'exact subject cumulative one, global unknown accounting required')
    for key in ('verifiedBy', 'reason'): m.required_string(accounting, key)
    with p.connect() as con:
        others = con.execute('SELECT id FROM retry_attempts WHERE order_id=? AND id NOT IN (?,?)',
                             (order['id'], prior['id'], ticket['id'])).fetchall()
        require(not others, 'ended attempts cannot branch or silently reticket')
        if not allow_current:
            require(not con.execute('SELECT id FROM attempts WHERE id=?', (ticket['id'],)).fetchone(), 'new attempt already dispatched')
    p.verify_inputs(order)
    return order


def effective_selection(p, order, attempt_id, original):
    """Overlay only the separately pinned attempt configuration, never rebind."""
    if attempt_id is None: return original
    _, ticket, _ = registered(p, attempt_id)
    require(ticket['orderId'] == order['id'] and ticket['companionSelection'] == original['request'], 'attempt original binding differs')
    result = copy.deepcopy(original); result['configuration'] = ticket['configuration']
    return result


def repair(p, ticket):
    m = api(); value = m.read(pin(ticket['repair']))
    require(value.get('schemaVersion') == 1 and value.get('kind') == 'companion-native-selector-repair' and
            value.get('orderId') == ticket['orderId'] and value.get('previousAttemptId') == ticket['previousAttemptId'] and
            value.get('previousPacketSha256') == ticket['previousPacketSha256'], 'exact reviewed selector repair required')
    from subject_companion_route import find, baseline, configuration
    order = json.loads(p.get(ticket['orderId'])['request']); original = find(p, order)
    q, _, _, _ = baseline(p, original)  # Verify inventory before importing its metadata validator.
    old = m.read(pin(original['configuration'])); new = m.read(pin(ticket['configuration']))
    require(value.get('originalConfiguration') == original['configuration'] and value.get('configuration') == ticket['configuration'],
            'repair configuration pins differ')
    entries = old.get('interactive_session', {}).get('nativeBindings', {}).get('bindings', [])
    matches = [i for i, entry in enumerate(entries) if isinstance(entry, dict) and entry.get('id') == 'morph_keys']
    require(len(matches) == 1, 'unique original morph_keys declaration required')
    index = matches[0]; entry = entries[index]
    require(entry.get('script') == 'NiOverride' and entry.get('function') == 'GetBodyMorphKeys' and
            entry.get('scope') == 'global' and [str(x).casefold() for x in entry.get('params', [])] == ['objectreference', 'string'] and
            str(entry.get('returnType')).casefold() == 'string[]' and entry.get('effect') == 'read', 'exact failed getter signature required')
    require(isinstance(old.get('runtime'), str) and isinstance(new.get('runtime'), str) and Path(new['runtime']).is_absolute() and
            Path(old['runtime']).resolve() != Path(new['runtime']).resolve(), 'fresh distinct absolute runtime required')
    expected = copy.deepcopy(old); expected['runtime'] = new['runtime']
    expected['interactive_session']['nativeBindings']['bindings'][index]['function'] = 'GetMorphKeys'
    require(new == expected, 'only fresh runtime and morph_keys function may change')
    configuration(p, order, dict(original, configuration=ticket['configuration']), q)
    new_runtime = Path(new['runtime']).resolve()
    old_runtimes = {Path(old['runtime']).resolve(), Path(q['configuration']['runtime']).resolve()}
    if p.host().get('runnerConfig'):
        host = m.read(p.host()['runnerConfig']); require(Path(host['runtime']).is_absolute(), 'global runtime must be absolute')
        old_runtimes.add(Path(host['runtime']).resolve())
    require(all(not new_runtime.is_relative_to(old_runtime) and not old_runtime.is_relative_to(new_runtime)
                for old_runtime in old_runtimes), 'fresh runtime cannot overlap prior/baseline/global runtime')
    prior = p.retry_show(ticket['previousAttemptId']); packet = p.verify_retry_packet(prior)
    record = pin(value['recordedSteps']); run = Path(packet['runDirectory']).resolve()
    require(record == run / 'steps.jsonl' and any(Path(item['path']).resolve() == record and item['sha256'] == value['recordedSteps']['sha256']
            for item in packet['files']), 'metadata must be the pinned predecessor steps')
    require(record.stat().st_size <= 64 * 1024 * 1024 and type(value.get('metadataStep')) is int and value['metadataStep'] > 0,
            'bounded exact recorded metadata step required')
    rows = record.read_text(encoding='utf-8').splitlines(); number = value['metadataStep']
    require(number <= len(rows), 'recorded metadata step absent'); row = json.loads(rows[number - 1])
    require(row.get('kind') == 'tool' and row.get('tool') == 'papyrus' and
            row.get('args') == {'action': 'describe', 'script': 'NiOverride'}, 'recorded step must be exact NiOverride describe')
    before = [json.loads(line) for line in rows[:number - 1]]
    deliveries = [item for item in before if item.get('kind') == 'interactive-action-delivered']
    require(deliveries and deliveries[-1].get('request', {}).get('operation') == 'binding' and
            deliveries[-1]['request'].get('bindingId') == 'morph_keys', 'metadata must follow the actual morph_keys delivery')
    require(number < len(rows), 'recorded metadata failure absent')
    stopped = json.loads(rows[number])
    require(stopped.get('kind') == 'interactive-stopped' and stopped.get('commandId') == deliveries[-1].get('commandId') and
            isinstance(stopped.get('commandId'), str) and stopped['commandId'] and stopped.get('replayed') is False and
            stopped.get('reason') == 'Unique declared native function metadata is unavailable', 'exact delivered selector failure must immediately follow metadata')
    code = '''import json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root))
from skyrim_autotest import interactive_bindings as b
assert Path(b.__file__).resolve()==root/'skyrim_autotest/interactive_bindings.py'
x=json.load(sys.stdin);policy=b.validate(x['policy']);entry=next(v for v in policy['bindings'] if v['id']=='morph_keys')
class Recorded:
 def call(self,tool,request):
  assert tool=='papyrus' and request=={'action':'describe','script':'NiOverride'}
  return x['description']
try: b._metadata(Recorded(),entry)
except b.BindingError: pass
else: raise AssertionError('Original selector unexpectedly available')
entry=dict(entry,function='GetMorphKeys');checked=b._metadata(Recorded(),entry)
print(json.dumps(checked))'''
    child = subprocess.run([sys.executable, '-I', '-c', code, original['executor']], input=json.dumps({
        'policy': old['interactive_session']['nativeBindings'], 'description': row['result']}), capture_output=True, text=True, timeout=30)
    require(child.returncode == 0, 'exact frozen metadata correction validation failed: ' + child.stderr[-1500:])
    expected_sources = {str(path.resolve()): m.digest(path) for path in m.HERE.glob('*.py')}
    actual = {}
    for item in value.get('operatorFiles', []):
        path = pin(item); require(str(path) not in actual, 'duplicate operator repair source'); actual[str(path)] = item['sha256']
    require(actual == expected_sources, 'complete executing operator source inventory required')
    require(isinstance(value.get('testEvidence'), list) and value['testEvidence'], 'retained repair test evidence required')
    for item in value['testEvidence']: require(pin(item).stat().st_size > 0, 'empty repair test evidence')
    for key in ('verifiedBy', 'reason'): m.required_string(value, key)
    return new


def register(p, path):
    m = api(); path = Path(path).resolve(); ticket = normalize(path); init(p)
    canonical = json.dumps(ticket, sort_keys=True, ensure_ascii=False)
    with p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        old = con.execute('SELECT request FROM retry_attempts WHERE id=?', (ticket['id'],)).fetchone()
        if old:
            require(old[0] == canonical, 'attempt identity is immutable'); registered(p, ticket['id'])
            return {'id': ticket['id'], 'duplicate': True, 'launch': False}
        require(not con.execute('SELECT id FROM jobs WHERE id=?', (ticket['id'],)).fetchone(), 'attempt conflicts with subject job')
        authority(p, ticket); predecessor(p, ticket); cfg = repair(p, ticket)
        require(not Path(cfg['runtime']).exists() or Path(cfg['runtime']).is_dir() and not any(Path(cfg['runtime']).iterdir()), 'new runtime must be empty')
        require([r[0] for r in con.execute('SELECT id FROM pipeline_holds')] == [ticket['previousAttemptId']], 'retain sole genuine failed-attempt hold')
        con.execute("INSERT INTO retry_attempts(id,order_id,request,created,status) VALUES(?,?,?,?,'queued')",
                    (ticket['id'], ticket['orderId'], canonical, time.time()))
        con.execute('INSERT INTO companion_poststart_tickets VALUES(?,?,?)', (ticket['id'], str(path), m.digest(path)))
        p.event(con, ticket['id'], 'companion_post_start_registered', 'Partial predecessor and consumed attempt budget preserved; no launch')
    return {'id': ticket['id'], 'orderId': ticket['orderId'], 'status': 'queued', 'launch': False, 'holdRetained': True}


def context(p, order, attempt_id):
    _, ticket, _ = registered(p, attempt_id)
    require(ticket['orderId'] == order['id'] and predecessor(p, ticket, allow_current=True) == order, 'attempt subject differs')
    with p.connect() as con:
        saved = con.execute('SELECT review FROM companion_poststart_admissions WHERE id=?', (attempt_id,)).fetchone()
    require(saved is not None, 'separate reviewed hold transfer missing')
    saved = json.loads(saved[0]); review_pin = {'path': saved['path'], 'sha256': saved['sha256']}
    require(api().read(pin(review_pin)) == saved['review'], 'post-start admission changed')
    return {'attemptId': attempt_id, 'folder': p.local / 'retry-attempts' / attempt_id, 'reviewPin': review_pin}


def _environment(p, con, ticket, order, selection, cfg, runner, admitted=False):
    m = api()
    require([r[0] for r in con.execute('SELECT id FROM pipeline_holds')] == ([] if admitted else [ticket['previousAttemptId']]),
            'genuine hold/claimed environment differs')
    for sql, params in [
        ("SELECT id FROM jobs WHERE status='running'", ()),
        ("SELECT id FROM retry_attempts WHERE status IN ('running','collecting') AND id!=?", (ticket['id'],)),
        ("SELECT id FROM game_sessions WHERE status IN ('queued','preparing','running','finalizing')", ()),
        ("SELECT id FROM cycle_slots WHERE status IN ('reserved','blocked')", ()),
        ("SELECT id FROM qualifications WHERE status IN ('prepared','running')", ()),
        ("SELECT id FROM retry_attempts WHERE status='queued' AND id!=?", (ticket['id'],)),
        ("SELECT j.id FROM jobs j JOIN released_orders r ON r.id=j.id WHERE j.status IN ('queued','running','waiting_player','session_waiting')", ()),
        ("SELECT id FROM jobs WHERE status IN ('queued','session_waiting') AND json_extract(request,'$.cycle') IS NOT NULL", ())]:
        require(not con.execute(sql, params).fetchone(), 'another active/queued owner retains the environment')
    rows = runner.native.processes()
    require(isinstance(rows, list) and rows and not any(r['name'].casefold() in {
        'skyrimse.exe', 'skyrimvr.exe', 'skse64_loader.exe', 'sksevr_loader.exe', 'vrserver.exe', 'vrcompositor.exe'} for r in rows),
        'game/VR or unavailable process inventory blocks admission')
    packet = p.verify_retry_packet(p.retry_show(ticket['previousAttemptId'])); run = Path(packet['runDirectory'])
    state = m.read(run / 'state.json'); identities = [state.get('runner'), state.get('game')] + [v['identity'] for v in state.get('owned', [])]
    companion = p.local / 'retry-attempts' / ticket['previousAttemptId'] / 'subject-companion'
    retained = {Path(item['path']).resolve(): item for item in packet['files']}
    processes = []
    for name in ('dispatch.json', 'report.json'):
        path = (companion / name).resolve(); require(path in retained, 'pinned predecessor companion process evidence missing')
        processes.append(m.read(pin({key: retained[path][key] for key in ('path', 'sha256')})))
    identities.extend([processes[0].get('client', {}).get('identity'), processes[1].get('sequencerProcess', {}).get('identity')])
    from subject_companion_route import baseline
    q, _, baseline_state, worker = baseline(p, selection)
    identities.extend([worker] + [v['identity'] for v in baseline_state.get('owned', [])])
    for ident in identities:
        require(type(ident) is dict and type(ident.get('pid')) is int and ident['pid'] > 0 and
                type(ident.get('birth')) is int and ident['birth'] > 0 and isinstance(ident.get('path'), str) and ident['path'] and
                not runner.native.alive(ident) and not any(r['pid'] == ident['pid'] and runner.native.identity(ident['pid']) is None for r in rows),
                'predecessor/baseline identity alive or unavailable')
    require(p.verify_companion_processes_dead(order, identities, attempt_id=ticket['previousAttemptId']) is True,
            'independent predecessor process-death verification unavailable')
    runtimes = {Path(cfg['runtime']), run.parent.parent, Path(q['configuration']['runtime'])}
    if p.host().get('runnerConfig'):
        host = m.read(p.host()['runnerConfig']); require(Path(host['runtime']).is_absolute(), 'global runtime must be explicit absolute')
        runtimes.add(Path(host['runtime']))
    for runtime in runtimes:
        require(all(m.read(file).get('done') is True for file in (runtime / 'runs').glob('*/state.json')), 'unfinished known runtime retains environment')
    require(not Path(cfg['runtime']).exists() or Path(cfg['runtime']).is_dir() and not any(Path(cfg['runtime']).iterdir()), 'fresh runtime already contains state')
    p.validate_profile_selection(order); p.verify_inputs(order)


def admit(p, path):
    m = api(); path = Path(path).resolve(); review = m.read(path)
    flags = {'predecessorFinalReportReviewed', 'restorationReviewed', 'archiveReviewed', 'repairReviewed', 'fullReplayReviewed', 'additionalStartReviewed'}
    required = flags | {'schemaVersion', 'kind', 'attemptId', 'ticket', 'ownerAuthorization', 'verifiedBy', 'reason'}
    require(type(review) is dict and set(review) == required and review['schemaVersion'] == 1 and
            review['kind'] == 'operator-companion-post-start-admission' and all(review[k] is True for k in flags), 'explicit independent prospective admission required')
    m.owner_evidence(review, path, require_deadline=False)
    for key in ('verifiedBy', 'reason'): m.required_string(review, key)
    row, ticket, source = registered(p, review['attemptId']); require(review['ticket'] == source, 'registered ticket differs')
    canonical = json.dumps({'path': str(path), 'sha256': m.digest(path), 'review': review}, sort_keys=True)
    with p.connect() as con:
        saved = con.execute('SELECT review FROM companion_poststart_admissions WHERE id=?', (ticket['id'],)).fetchone()
    if saved:
        require(saved[0] == canonical, 'admission is immutable'); context(p, json.loads(p.get(ticket['orderId'])['request']), ticket['id'])
        return {'id': ticket['id'], 'status': 'already_admitted', 'launch': False}
    require(row['status'] == 'queued', 'unused queued ticket required')
    from order_platform import activate, authority as owner
    order, selection = authority(p, ticket); require(owner(review) == owner(selection), 'actual admission owner differs')
    predecessor(p, ticket); cfg = repair(p, ticket); runner = activate(selection['executor'])
    with runner.native.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        saved = con.execute('SELECT review FROM companion_poststart_admissions WHERE id=?', (ticket['id'],)).fetchone()
        if saved:
            require(saved[0] == canonical, 'admission is immutable')
            return {'id': ticket['id'], 'status': 'already_admitted', 'launch': False}
        require(con.execute('SELECT status FROM retry_attempts WHERE id=?', (ticket['id'],)).fetchone()[0] == 'queued', 'retry owner changed')
        authority(p, ticket); predecessor(p, ticket); require(repair(p, ticket) == cfg, 'repair changed')
        _environment(p, con, ticket, order, selection, cfg, runner)
        require(m.digest(path) == json.loads(canonical)['sha256'], 'admission changed during review')
        con.execute('DELETE FROM pipeline_holds WHERE id=?', (ticket['previousAttemptId'],))
        con.execute('INSERT INTO companion_poststart_admissions VALUES(?,?)', (ticket['id'], canonical))
        con.execute("UPDATE retry_attempts SET status='running' WHERE id=?", (ticket['id'],))
        p.event(con, ticket['id'], 'companion_post_start_admitted', canonical)
        p.event(con, ticket['previousAttemptId'], 'reviewed_post_start_hold_transferred', ticket['id'])
    return {'id': ticket['id'], 'orderId': order['id'], 'status': 'running', 'launch': False,
            'subjectActualLaunchesBefore': 1, 'maximumSubjectActualLaunches': 2}


def before_dispatch(p, ticket):
    order, selection = authority(p, ticket); predecessor(p, ticket); cfg = repair(p, ticket); context(p, order, ticket['id'])
    from subject_companion_route import baseline
    baseline(p, selection)
    from order_platform import activate
    runner = activate(selection['executor'])
    with runner.native.SessionMutex(), p.connect() as con:
        _environment(p, con, ticket, order, selection, cfg, runner, admitted=True)
    require(not list((Path(cfg['runtime']) / 'runs').glob('*/state.json')), 'new native run already exists; never replay')
    return order


def dispatch_claimed(p, ticket):
    with p.connect() as con:
        row = con.execute('SELECT status FROM retry_attempts WHERE id=?', (ticket['id'],)).fetchone()
        marker = con.execute('SELECT id FROM companion_poststart_dispatches WHERE id=?', (ticket['id'],)).fetchone()
    require(row is not None and row[0] == 'running' and marker is not None, 'exact supported dispatch claim missing')


def run(p, attempt_id):
    row, ticket, _ = registered(p, attempt_id); before_dispatch(p, ticket)
    with p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        require(con.execute('SELECT status FROM retry_attempts WHERE id=?', (attempt_id,)).fetchone()[0] == 'running', 'exact admitted running owner required')
        require(not con.execute('SELECT id FROM companion_poststart_dispatches WHERE id=?', (attempt_id,)).fetchone(), 'attempt already dispatched; never replay')
        require(not con.execute('SELECT id FROM pipeline_holds').fetchone(), 'pipeline hold blocks dispatch')
        con.execute('INSERT INTO companion_poststart_dispatches VALUES(?,?)', (attempt_id, time.time()))
        p.event(con, attempt_id, 'companion_post_start_dispatch_claimed', 'One separately authorized full replay; previous attempt budget remains consumed')
    return p.execute_retry(p.retry_show(attempt_id))


def packet_metadata(p, ticket, run):
    m = api()
    if run:
        state = m.read(Path(run) / 'state.json'); native = state.get('order', {})
        require(native.get('id') == ticket['orderId'] and native.get('attemptId') == ticket['id'] and
                native.get('subjectOrderId') == ticket['orderId'], 'native attempt attribution differs')
        count = p.native_game_starts(state)
    else:
        with p.connect() as con:
            require(not con.execute('SELECT id FROM attempts WHERE id=?', (ticket['id'],)).fetchone(), 'admitted native execution without result is not zero starts')
        count = 0
    require(type(count) is int and 0 <= count <= 1, 'additional subject physical-start budget exceeded or unavailable')
    return {'attemptKind': 'companion_post_start_tooling', 'restartMode': 'initial-fixture',
            'previousAttemptId': ticket['previousAttemptId'], 'previousReportSha256': ticket['previousReport']['sha256'],
            'launchAccounting': {'scope': 'same-immutable-order', 'subjectActualLaunchesBefore': 1,
                'thisAttemptActualGameStarts': count, 'subjectActualLaunchesAfter': 1 + count,
                'maximumSubjectActualLaunches': 2, 'historicalGlobalActualLaunches': None}}

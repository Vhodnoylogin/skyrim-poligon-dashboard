"""One reviewed zero-native companion continuation; never reopen a subject job."""
from __future__ import annotations
import json
import math
from pathlib import Path
import time

KIND = 'companion-pre-session'
FIELDS = {'schemaVersion', 'kind', 'id', 'orderId', 'previousPacketSha256', 'technicalAbort',
          'ownerAuthority', 'authorityReview', 'companionSelection', 'previousAdmission', 'repair'}
PINS = ('technicalAbort', 'ownerAuthority', 'companionSelection', 'previousAdmission', 'repair')


def api():
    import polygon
    return polygon


def is_ticket(ticket):
    return isinstance(ticket, dict) and ticket.get('kind') == KIND


def require(condition, reason):
    if not condition:
        raise ValueError('Companion pre-session: ' + reason)


def pin(value):
    from subject_companion_route import pin as verify
    return verify(value)


def init(p):
    with p.connect() as con:
        con.executescript('''
          CREATE TABLE IF NOT EXISTS companion_pretest_tickets
            (id TEXT PRIMARY KEY, path TEXT NOT NULL, sha256 TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS companion_pretest_admissions
            (id TEXT PRIMARY KEY, review TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS companion_pretest_dispatches
            (id TEXT PRIMARY KEY, started REAL NOT NULL);
        ''')


def normalize(path):
    m = api(); path = Path(path).resolve(); value = m.read(path)
    require(type(value) is dict and set(value) == FIELDS and type(value['schemaVersion']) is int and
            value['schemaVersion'] == 1 and value['kind'] == KIND, 'exact reviewed ticket required')
    for key in ('id', 'orderId'):
        require(isinstance(value[key], str) and m.SAFE_ID.fullmatch(value[key]), 'safe exact identifiers required')
    require(value['id'] != value['orderId'], 'attempt must differ from immutable subject order')
    require(isinstance(value['previousPacketSha256'], str) and m.SHA.fullmatch(value['previousPacketSha256']),
            'exact predecessor packet hash required')
    for key in PINS:
        value[key]['path'] = str((path.parent / value[key]['path']).absolute())
        value[key]['path'] = str(pin(value[key]))
    return value


def registered(p, attempt_id):
    m = api(); row = p.retry_show(attempt_id); ticket = json.loads(row['request'])
    require(is_ticket(ticket) and ticket['id'] == attempt_id and ticket['orderId'] == row['order_id'],
            'registered companion attempt identity differs')
    with p.connect() as con:
        source = con.execute('SELECT path,sha256 FROM companion_pretest_tickets WHERE id=?', (attempt_id,)).fetchone()
    require(source is not None, 'immutable ticket source missing')
    source_pin = {'path': source['path'], 'sha256': source['sha256']}
    path = pin(source_pin)
    require(normalize(path) == ticket, 'registered ticket source changed')
    return row, ticket, source_pin


def authority(p, ticket, dispatch=True):
    """Check the original unused launch deadline, never mint another one."""
    m = api()
    from order_platform import authority as owner
    from subject_companion_route import find
    order = json.loads(p.get(ticket['orderId'])['request'])
    selection = find(p, order)
    require(ticket['companionSelection'] == selection['request'], 'original companion binding differs')
    document = m.read(pin(ticket['ownerAuthority']))
    m.owner_evidence(document, pin(ticket['ownerAuthority']), require_deadline=False)
    require(document.get('state', 'active') == 'active' and ticket['orderId'] in document.get('orderIds', []),
            'current owner authority does not cover this exact subject')
    require(owner(document) == owner(selection), 'continuation must retain the actual original owner scope')
    review = ticket['authorityReview']
    required = {'verifiedBy', 'reason', 'retryPermitted', 'maxAdditionalAttempts', 'subjectActualLaunchesBefore',
                'maximumSubjectActualLaunches', 'originalDeadlineUtc'}
    require(type(review) is dict and set(review) == required and review['retryPermitted'] is True and
            type(review['maxAdditionalAttempts']) is int and review['maxAdditionalAttempts'] == 1 and
            type(review['subjectActualLaunchesBefore']) is int and review['subjectActualLaunchesBefore'] == 0 and
            type(review['maximumSubjectActualLaunches']) is int and review['maximumSubjectActualLaunches'] == 1,
            'only one unused original subject launch may be reviewed')
    for key in ('verifiedBy', 'reason'):
        m.required_string(review, key)
    with p.connect() as con:
        row = con.execute('SELECT authorization FROM releases JOIN released_orders ON releases.id=release_id '
                          'WHERE released_orders.id=?', (order['id'],)).fetchone()
    require(row is not None, 'original one-shot release missing')
    release = json.loads(row[0]); deadline = release.get('deadlineUtc')
    require(type(deadline) in (int, float) and math.isfinite(deadline) and deadline == review['originalDeadlineUtc'] and owner(release) == owner(selection),
            'original release owner/deadline changed or was extended')
    if dispatch:
        require(time.time() < deadline, 'original unused-launch deadline expired')
        if document.get('deadlineUtc') is not None:
            require(time.time() < document['deadlineUtc'] <= deadline, 'owner authority expired or extends original release')
    return order, selection


def repair(p, ticket):
    m = api(); value = m.read(pin(ticket['repair']))
    require(value.get('schemaVersion') == 1 and value.get('kind') == 'companion-pre-session-tooling-repair' and
            value.get('orderId') == ticket['orderId'] and value.get('previousPacketSha256') == ticket['previousPacketSha256'],
            'repair review must bind the exact refusal')
    for key in ('verifiedBy', 'reason'):
        m.required_string(value, key)
    expected = {str(path.resolve()): m.digest(path) for path in m.HERE.glob('*.py')}
    entries = value.get('operatorFiles')
    require(isinstance(entries, list) and len(entries) == len(expected), 'complete repaired operator source inventory required')
    actual = {}
    for entry in entries:
        path = pin(entry)
        require(str(path) not in actual, 'duplicate repaired operator source')
        actual[str(path)] = entry['sha256']
    require(actual == expected, 'repair pins differ from the executing operator source')
    tests = value.get('testEvidence')
    require(isinstance(tests, list) and tests, 'retained repair test evidence required')
    for entry in tests:
        require(pin(entry).stat().st_size > 0, 'repair test evidence is empty')
    return value


def predecessor(p, ticket, allow_current=False):
    """Verify immutable zero-native history; only this later attempt may exist."""
    m = api()
    from subject_companion_route import find, admission
    row = p.get(ticket['orderId']); order = json.loads(row['request'])
    require(row['status'] == 'blocked' and order.get('schemaVersion') == 2 and order.get('mode') == 'automatic' and
            not order.get('cycle') and order.get('subjectPlan', {}).get('interface') == 'polygon-file-plan/1',
            'only this blocked solo file-plan refusal is eligible')
    require(row.get('packet') and m.digest(row['packet']) == ticket['previousPacketSha256'], 'predecessor packet changed')
    _, packet = p.verify_packet(row)
    require(packet.get('orderId') == order['id'] and packet.get('subjectOrderSha256') == m.subject_contract.identity(order) and
            packet.get('executionOutcome') == 'blocked' and packet.get('runDirectory') is None and
            packet.get('platformPlanSha256') is None and packet.get('restored') is None,
            'predecessor is not an untouched zero-native refusal')
    folder = p.evidence_dir(order['id'])
    summary_path = folder / 'execution-summary.json'
    require(any(Path(item['path']).resolve() == summary_path.resolve() for item in packet['files']), 'pre-session summary is not pinned')
    summary = m.read(summary_path)
    require(summary.get('orderId') == order['id'] and summary.get('terminationCause') == 'pre_session_refusal' and
            summary.get('runId') is None and summary.get('phase') is None and summary.get('evidence') is None,
            'native/subject execution cannot be excluded')
    require(not any((folder / name).exists() for name in
        ('platform-plan.json', 'executor-pins.json', 'executor.log', 'config.json', 'scenario.json', 'worker.json')),
        'predecessor has prepared/dispatched native material')
    with p.connect() as con:
        for table in ('attempts', 'platform_attempts'):
            require(not con.execute('SELECT id FROM ' + table + ' WHERE id=?', (order['id'],)).fetchone(),
                    'original native/platform attempt exists')
        others = con.execute('SELECT id,request FROM retry_attempts WHERE order_id=? AND id!=?', (order['id'], ticket['id'])).fetchall()
        descendants = [json.loads(other['request']) for other in others]
        require(not others or allow_current and len(others) == 1 and
                descendants[0].get('kind') == 'companion-post-start-tooling' and
                descendants[0].get('previousAttemptId') == ticket['id'] and
                descendants[0].get('orderId') == order['id'] and descendants[0].get('id') == others[0]['id'],
                'zero-native continuation cannot branch or follow another retry')
    require(admission(p, order['id']) == ticket['previousAdmission'], 'original admission changed')
    selection = find(p, order)
    cfg = m.read(pin(selection['configuration']))
    require(isinstance(cfg.get('runtime'), str) and Path(cfg['runtime']).is_absolute(), 'explicit absolute runtime required for zero-native proof')
    current = []
    for path in (Path(cfg['runtime']) / 'runs').glob('*/state.json'):
        state = m.read(path)
        if state.get('order', {}).get('id') == order['id']:
            require(allow_current and state['order'].get('attemptId') == ticket['id'] and
                    state['order'].get('subjectOrderId') == order['id'], 'earlier/foreign native run exists')
            current.append(path)
    require(len(current) <= 1, 'multiple native executions for this one unused launch')
    abort = m.read(pin(ticket['technicalAbort']))
    require(abort.get('classification') == 'confirmed-tooling-pre-session-refusal' and abort.get('orderId') == order['id'] and
            abort.get('packetSha256') == ticket['previousPacketSha256'] and abort.get('subjectStarted') is False and
            type(abort.get('actualGameStarts')) is int and abort['actualGameStarts'] == 0 and
            abort.get('platformPlanCreated') is False and abort.get('preSessionUntouched') is True,
            'review must explicitly prove zero-native untouched preparation')
    for key in ('verifiedBy', 'reason'):
        m.required_string(abort, key)
    original = m.read(pin(abort['refusal']))
    require(original.get('actualGameStarts') == 0 and original.get('subjectStarted') is False and
            original.get('platformPlanCreated') is False and original.get('historyPreserved') is True,
            'original refusal evidence differs')
    restored = m.read(pin(abort['managerRestoration']))
    require(restored.get('gameVRIdle') is True and restored.get('gameStartsThisAttempt') == 0 and
            restored.get('procs', {}).get('running') == 0 and isinstance(restored.get('identity'), dict),
            'original manager restoration/idle observation missing')
    p.verify_inputs(order)
    return order


def register(p, path):
    """Queue one distinct attempt. The genuine predecessor hold remains in place."""
    m = api(); path = Path(path).resolve(); ticket = normalize(path)
    init(p)
    canonical = json.dumps(ticket, sort_keys=True, ensure_ascii=False)
    with p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        old = con.execute('SELECT request FROM retry_attempts WHERE id=?', (ticket['id'],)).fetchone()
        if old:
            require(old[0] == canonical, 'attempt identity is immutable')
            registered(p, ticket['id'])
            return {'id': ticket['id'], 'duplicate': True, 'launch': False}
        require(not con.execute('SELECT id FROM jobs WHERE id=?', (ticket['id'],)).fetchone(), 'attempt conflicts with subject job')
        authority(p, ticket); predecessor(p, ticket); repair(p, ticket)
        require([r[0] for r in con.execute('SELECT id FROM pipeline_holds')] == [ticket['orderId']],
                'exact genuine predecessor hold required')
        con.execute("INSERT INTO retry_attempts(id,order_id,request,created,status) VALUES(?,?,?,?,'queued')",
                    (ticket['id'], ticket['orderId'], canonical, time.time()))
        con.execute('INSERT INTO companion_pretest_tickets VALUES(?,?,?)', (ticket['id'], str(path), m.digest(path)))
        p.event(con, ticket['id'], 'companion_pre_session_registered', 'Original blocked subject and zero-native packet preserved')
    return {'id': ticket['id'], 'orderId': ticket['orderId'], 'status': 'queued', 'launch': False, 'holdRetained': True}


def context(p, order, attempt_id):
    """Pure immutable lookup, valid during collection after the launch deadline."""
    m = api(); row, ticket, _ = registered(p, attempt_id)
    require(ticket['orderId'] == order['id'] and predecessor(p, ticket, allow_current=True) == order, 'attempt subject differs')
    with p.connect() as con:
        saved = con.execute('SELECT review FROM companion_pretest_admissions WHERE id=?', (attempt_id,)).fetchone()
    require(saved is not None, 'reviewed hold transfer has not admitted this attempt')
    saved = json.loads(saved[0]); review_pin = {'path': saved['path'], 'sha256': saved['sha256']}
    require(m.read(pin(review_pin)) == saved['review'], 'pre-session admission changed')
    return {'attemptId': attempt_id, 'folder': p.local / 'retry-attempts' / attempt_id, 'reviewPin': review_pin}


def before_dispatch(p, ticket):
    """Recheck unused budget immediately before the one native dispatch."""
    authority(p, ticket)
    order = predecessor(p, ticket)
    repair(p, ticket)
    context(p, order, ticket['id'])
    return order


def dispatch_claimed(p, ticket):
    with p.connect() as con:
        row = con.execute('SELECT status FROM retry_attempts WHERE id=?', (ticket['id'],)).fetchone()
        marker = con.execute('SELECT id FROM companion_pretest_dispatches WHERE id=?', (ticket['id'],)).fetchone()
    require(row is not None and row[0] == 'running' and marker is not None, 'exact supported dispatch claim missing')


def admit(p, path):
    """Atomically transfer only the reviewed hold; registration never launches."""
    m = api(); path = Path(path).resolve(); review = m.read(path)
    required = {'schemaVersion', 'kind', 'attemptId', 'ticket', 'ownerAuthorization', 'verifiedBy', 'reason',
                'zeroNativeReviewed', 'preSessionUntouchedReviewed', 'restorationReviewed', 'repairReviewed', 'unusedStartReviewed'}
    require(type(review) is dict and set(review) == required and review['schemaVersion'] == 1 and
            review['kind'] == 'operator-companion-pre-session-admission' and
            all(review[key] is True for key in required if key.endswith('Reviewed')), 'explicit current operator review required')
    m.owner_evidence(review, path, require_deadline=False)
    for key in ('verifiedBy', 'reason'):
        m.required_string(review, key)
    row, ticket, source = registered(p, review['attemptId'])
    require(review['ticket'] == source, 'registered ticket differs')
    from order_platform import activate, authority as owner
    from subject_companion_route import baseline
    canonical = json.dumps({'path': str(path), 'sha256': m.digest(path), 'review': review}, sort_keys=True)
    with p.connect() as con:
        previous = con.execute('SELECT review FROM companion_pretest_admissions WHERE id=?', (ticket['id'],)).fetchone()
    if previous:
        require(previous[0] == canonical, 'admission is immutable')
        context(p, json.loads(p.get(ticket['orderId'])['request']), ticket['id'])
        return {'id': ticket['id'], 'status': 'already_admitted', 'launch': False}
    require(row['status'] == 'queued', 'unused queued ticket required')
    order, selection = authority(p, ticket)
    require(owner(review) == owner(selection), 'admission owner scope differs')
    predecessor(p, ticket); repair(p, ticket)
    q, _, old_state, old_worker = baseline(p, selection)
    runner = activate(selection['executor'])
    with runner.native.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        saved = con.execute('SELECT review FROM companion_pretest_admissions WHERE id=?', (ticket['id'],)).fetchone()
        if saved:
            require(saved[0] == canonical, 'admission is immutable')
            return {'id': ticket['id'], 'status': 'already_admitted', 'launch': False}
        authority(p, ticket); predecessor(p, ticket); repair(p, ticket)
        require(con.execute('SELECT status FROM retry_attempts WHERE id=?', (ticket['id'],)).fetchone()[0] == 'queued',
                'retry owner changed before admission')
        require([r[0] for r in con.execute('SELECT id FROM pipeline_holds')] == [order['id']], 'genuine sole hold differs')
        require(not con.execute("SELECT id FROM jobs WHERE status='running'").fetchone() and
                not con.execute("SELECT id FROM retry_attempts WHERE status IN ('running','collecting')").fetchone() and
                not con.execute("SELECT id FROM game_sessions WHERE status IN ('preparing','running','finalizing')").fetchone() and
                not con.execute("SELECT id FROM cycle_slots WHERE status IN ('reserved','blocked')").fetchone() and
                not p.qualification_busy(con), 'another owner retains the environment')
        require(not con.execute("SELECT id FROM qualifications WHERE status IN ('prepared','running')").fetchone() and
                not con.execute("SELECT id FROM retry_attempts WHERE status='queued' AND id!=?", (ticket['id'],)).fetchone() and
                not con.execute("SELECT id FROM game_sessions WHERE status='queued'").fetchone() and
                not con.execute("SELECT j.id FROM jobs j JOIN released_orders r ON r.id=j.id WHERE j.status IN ('queued','running','waiting_player','session_waiting')").fetchone() and
                not con.execute("SELECT id FROM jobs WHERE status IN ('queued','session_waiting') AND json_extract(request,'$.cycle') IS NOT NULL").fetchone(),
                'other queued/released work or qualification cannot receive the cleared environment')
        rows = runner.native.processes()
        require(isinstance(rows, list) and rows and not any(r['name'].lower() in runner.GAME_NAMES | runner.VR_NAMES for r in rows),
                'game/VR or unavailable inventory blocks unused launch admission')
        for expected in [old_worker] + [r['identity'] for r in old_state.get('owned', [])]:
            require(not runner.native.alive(expected) and not any(r['pid'] == expected['pid'] and
                    runner.native.identity(expected['pid']) is None for r in rows), 'baseline process alive or unknown')
        cfg = m.read(pin(selection['configuration']))
        runtimes = {Path(cfg['runtime']), Path(q['configuration']['runtime'])}
        if p.host().get('runnerConfig'):
            runtimes.add(Path(m.read(p.host()['runnerConfig'])['runtime']))
        for runtime in runtimes:
            require(all(m.read(file).get('done') is True for file in (runtime / 'runs').glob('*/state.json')),
                    'unfinished native session retains the environment')
        con.execute('DELETE FROM pipeline_holds WHERE id=?', (order['id'],))
        p.check_launch_authorization(order, connection=con)
        con.execute('INSERT INTO companion_pretest_admissions VALUES(?,?)', (ticket['id'], canonical))
        con.execute("UPDATE retry_attempts SET status='running' WHERE id=?", (ticket['id'],))
        p.event(con, ticket['id'], 'companion_pre_session_admitted', canonical)
        p.event(con, order['id'], 'zero_native_hold_transferred', ticket['id'])
    return {'id': ticket['id'], 'orderId': order['id'], 'status': 'running', 'launch': False,
            'subjectActualLaunchesBefore': 0, 'maximumSubjectActualLaunches': 1}


def run(p, attempt_id):
    """Dispatch exactly once through the existing retry execution machinery."""
    row, ticket, _ = registered(p, attempt_id)
    before_dispatch(p, ticket)
    with p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        require(con.execute('SELECT status FROM retry_attempts WHERE id=?', (attempt_id,)).fetchone()[0] == 'running',
                'exact admitted running owner required')
        require(not con.execute('SELECT id FROM companion_pretest_dispatches WHERE id=?', (attempt_id,)).fetchone(),
                'this attempt already dispatched; never replay')
        require(not con.execute('SELECT id FROM pipeline_holds').fetchone(), 'pipeline hold blocks dispatch')
        con.execute('INSERT INTO companion_pretest_dispatches VALUES(?,?)', (attempt_id, time.time()))
        p.event(con, attempt_id, 'companion_pre_session_dispatch_claimed', 'One original unused launch; no requeue')
    return p.execute_retry(p.retry_show(attempt_id))


def packet_metadata(p, ticket, run):
    m = api(); count = p.native_game_starts(m.read(Path(run) / 'state.json')) if run else 0
    require(type(count) is int and 0 <= count <= 1, 'subject physical-start budget exceeded or unavailable')
    return {'attemptKind': 'companion_pre_session', 'preSessionUntouched': True,
            'launchAccounting': {'subjectActualLaunchesBefore': 0, 'thisAttemptActualGameStarts': count,
                'subjectActualLaunchesAfter': count, 'maximumSubjectActualLaunches': 1},
            'originalDeadlineUtc': ticket['authorityReview']['originalDeadlineUtc']}


def archive_record(run):
    """Exact nonempty copied-profile membership, including later additions."""
    m = api(); run = Path(run).resolve(); state = m.read(run / 'state.json')
    archive = run / 'test-profile'
    require(archive.is_dir() and Path(state.get('profileArchive', '')).resolve() == archive and
            isinstance(state.get('testProfile'), str) and not Path(state['testProfile']).exists(),
            'archived/removed owned profile required')
    files = []
    for path in sorted(archive.rglob('*')):
        require(not path.is_symlink() and not getattr(path.lstat(), 'st_file_attributes', 0) & 0x400,
                'profile archive link/reparse refused')
        if path.is_file():
            files.append({'path': str(path.resolve()), 'sha256': m.digest(path), 'bytes': path.stat().st_size})
    require(files, 'nonempty profile archive inventory required')
    return {'schemaVersion': 1, 'runDirectory': str(run), 'profileArchive': str(archive),
            'removedProfile': state['testProfile'], 'files': files}


def freeze_archive(folder, run):
    m = api(); target = Path(folder) / 'profile-archive.json'; value = archive_record(run)
    if target.exists(): require(m.read(target) == value, 'profile archive inventory changed')
    else: m.write(target, value)
    return target


def verify_archive(packet):
    m = api(); run = packet.get('runDirectory')
    if not run: return
    records = [entry for entry in packet['files'] if Path(entry['path']).name == 'profile-archive.json']
    require(len(records) == 1 and m.read(records[0]['path']) == archive_record(run), 'profile archive changed after collection')

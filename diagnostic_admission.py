"""Explicit one-shot subject diagnostics under one retained failed tool hold.

This is not qualification or ordinary dispatch. Native actions occur only through
the existing executor after a consumed exact admission. Nothing here clears holds.
"""
import contextlib
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import order_platform
import subject_contract
from qualification import inventory
from qualification_pre_native import _absolute, _pin, _hash
from qualification_terminal import _json

# Deliberately first-case-only. A different qualification is a protocol/source
# extension, not a new caller-selected counter epoch.
Q1_ID = 'autotest-se-finite-native-20261029-1'
APPROVED_INSTALLATION_PLAN_SHA256 = '4bd589605544581d9054afe4539e2633d66345ca2c9416c9b661350997f491a3'
APPROVED_BASELINE_AUDIT_SHA256 = 'ae31de7fb71e78bda0d1f5f55363640321372d0449a4eb8043dd5d6e827077d6'
APPROVED_ARCHIVE_SHA256 = '938c27f342fbe9b19da778992ae9e67987f0c12c4fec8f814e020a09ca0731bb'
APPROVED_CASE_REVIEW_SHA256 = '5f7241d5914d74c937d4c0982f24d8339a55bd398c9eb5efe28e58e8090e87c3'
APPROVED_SLOT_REQUEST_SHA256 = '959359cfa6dc7f3b69fdaf7d1ce0c415d2980ed2bd4a498604d132a6b32db3d4'
APPROVED_SUBJECT_DRAFT_SHA256 = '0bdbcb785ea6cf22682aa054d9e0312dce19c17ad50063688ca8fde385ea3331'
APPROVED_SUBJECT_SPECIFICATION_SHA256 = '9f507a7a1f2fd2cf202473370dfbcf852f7b1d5273a2a2a09038ff35dd73f3cf'
APPROVED_SUBJECT_PLAN_SHA256 = '350edeff194133026f76a0fb7d0e40f7a67ed61999d12b38f839987609540e69'
APPROVED_TESTING_SHA256 = '39c9ce78dc71069ae7b653270fb3d13cbe37c539838c5929ae13d24958e3c459'


def api():
    import polygon
    return polygon


def init(p):
    with p.connect() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS diagnostic_admissions
          (id TEXT PRIMARY KEY, order_id TEXT UNIQUE NOT NULL, cycle_id TEXT NOT NULL,
           request TEXT NOT NULL, status TEXT NOT NULL, plan TEXT, review TEXT,
           actual_starts INTEGER)''')


def pin(value):
    return _pin(value)


def read_hashed(value, maximum=16 * 1024 * 1024):
    path = _absolute(value['path'])
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno()); raw = stream.read(maximum + 1); after = os.fstat(stream.fileno())
    stamp = lambda x: (x.st_dev, x.st_ino, x.st_size, x.st_mtime_ns)
    if (len(raw) > maximum or stamp(before) != stamp(after) or stamp(after) != stamp(path.stat())
            or hashlib.sha256(raw).hexdigest() != value['sha256']):
        raise ValueError('Diagnostic evidence changed/oversized while reading')
    return raw


def read_pin(value):
    pin(value)
    return _json(read_hashed(value))


def document(path):
    path = _absolute(str(path)); value = file_pin(path)
    return read_pin(value), value


def file_pin(path):
    path = _absolute(str(path))
    return {'path': str(path), 'sha256': _hash(path)}


def source_pins():
    return [file_pin(x) for x in sorted(Path(__file__).parent.glob('*.py'))]


def saved(p, order_id, con=None):
    if con is None:
        with p.connect() as connection:
            return saved(p, order_id, connection)
    row = con.execute('SELECT * FROM diagnostic_admissions WHERE order_id=?', (order_id,)).fetchone()
    return dict(row) if row else None


def _request(row):
    request = json.loads(row['request'])
    if read_pin(request['requestPin']) != request['originalRequest']:
        raise ValueError('Immutable diagnostic preparation review changed')
    if source_pins() != request['dashboardPins'] or inventory(request['executor']) != request['executorPins']:
        raise ValueError('Diagnostic source/executor inventory changed')
    for entry in request['protectedInputs']:
        pin(entry)
    for entry in request['reviewPins']:
        pin(entry)
    if row.get('review'):
        review = json.loads(row['review'])
        if read_pin(review['pin']) != review['review']:
            raise ValueError('Consumed diagnostic execution review changed')
    return request


def _historical(p, request, con):
    """Only frozen packet evidence, never obsolete live installation hashes."""
    m = api()
    qrow = con.execute('SELECT * FROM qualifications WHERE id=?', (request['qualificationId'],)).fetchone()
    if not qrow or qrow['status'] != 'recorded' or json.loads(qrow['packet'] or 'null') != request['qualificationPacket']:
        raise ValueError('Exact recorded failed qualification required')
    packet = read_pin(request['qualificationPacket'])
    if (packet.get('kind') != 'tool-qualification-result' or packet.get('id') != request['qualificationId']
            or packet.get('actualGameStarts') != 1 or packet.get('executionOutcome') != 'failed'
            or packet.get('restored') is not True or packet.get('collectionFinished') is not True
            or packet.get('collectionFindings') or packet.get('globalProviderQualified') is not False):
        raise ValueError('Completed normal FAILED one-game tool packet required')
    for entry in packet['files']:
        pin({'path': entry['path'], 'sha256': entry['sha256']})
    run = Path(packet['runDirectory'])
    evidence = {Path(x['path']): {'path': x['path'], 'sha256': x['sha256']} for x in packet['files']}
    if run / 'state.json' not in evidence or run / 'result.json' not in evidence:
        raise ValueError('Native state/result pins required')
    state = read_pin(evidence[run / 'state.json'])
    result = read_pin(evidence[run / 'result.json'])
    if (state.get('done') is not True or state.get('restored') is not True or state.get('restoreErrors')
            or result.get('restored') is not True or result.get('restoreErrors')
            or state.get('order', {}).get('id') != 'qualification-' + request['qualificationId']
            or p.native_game_starts(state) != 1):
        raise ValueError('Exact ended/restored native qualification required')
    folder = p.local / 'qualifications' / request['qualificationId']
    required = {run / 'state.json', run / 'result.json', folder / 'worker.json', folder / 'child-exit.json', folder / 'plan.json'}
    if not required <= {Path(x['path']) for x in packet['files']}:
        raise ValueError('Native identities/results/original plan absent from frozen packet manifest')
    if read_pin(evidence[folder / 'plan.json']) != json.loads(qrow['request']):
        raise ValueError('Original qualification plan changed')
    worker = read_pin(evidence[folder / 'worker.json'])['identity']
    child = read_pin(evidence[folder / 'child-exit.json'])
    if type(child.get('returncode')) is not int or child.get('timeout') or worker != state.get('runner'):
        raise ValueError('Closed exact qualification child required')
    archive = run / 'test-profile'
    actual = [file_pin(x) for x in sorted(archive.rglob('*')) if x.is_file()]
    if (not actual or actual != packet.get('profileArchivePins')
            or Path(state.get('profileArchive', '')).resolve() != archive.resolve()
            or not state.get('testProfile') or Path(state['testProfile']).exists()):
        raise ValueError('Exact archived/removed qualification profile required')
    if not {x['path'] for x in actual} <= {x['path'] for x in packet['files']}:
        raise ValueError('Archive pins absent from frozen qualification evidence')
    for directory in [archive, *archive.rglob('*')]:
        if directory.is_symlink() or getattr(directory.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Linked qualification archive refused')
    qplan = json.loads(qrow['request'])
    if request['executor'] != qplan['executor'] or inventory(request['executor']) != qplan['executorPins']:
        raise ValueError('Diagnostic must use the exact historically exercised Q1 executor')
    import diagnostic_b6_fault
    diagnostic_b6_fault.verify(request, state, result, qplan)
    return packet, state, worker, qplan


def _authority(p, request, con):
    m = api()
    if request['qualificationId'] != Q1_ID:
        raise ValueError('Version1 is bound to the independently approved first Q1 only')
    m.owner_evidence(request, Path(request['requestPin']['path']))
    cycle = con.execute('SELECT * FROM cycles WHERE id=?', (request['cycleId'],)).fetchone()
    if not cycle or cycle['status'] != 'active':
        raise ValueError('Active existing cycle required')
    approval = json.loads(cycle['authorization'])
    m.owner_evidence(approval, Path(request['requestPin']['path']))
    if (request['deadlineUtc'] > approval['deadlineUtc'] or order_platform.authority(request) != order_platform.authority(approval)
            or request['sourceChat'] != approval['sourceChat'] or request['sourceThreadId'] != approval['sourceThreadId']):
        raise ValueError('Current exact cycle authority/origin required')
    accounting = read_pin(request['taskAccounting'])
    if (accounting.get('kind') != 'diagnostic-task-start-accounting' or accounting.get('cycleId') != request['cycleId']
            or accounting.get('qualificationId') != request['qualificationId']
            or accounting.get('cumulativeActualGameStarts') is not None
            or type(accounting.get('maximumActualGameStarts')) is not int
            or accounting['maximumActualGameStarts'] != 2
            or not accounting.get('verifiedBy') or not accounting.get('reason')):
        raise ValueError('Reviewed bounded task accounting required; historical count stays null')
    # Version1 deliberately admits only Q1 plus the FIRST diagnostic. A new
    # cycle/qualification cannot refresh this narrow allowance.
    if con.execute('SELECT id FROM diagnostic_admissions WHERE id!=?', (request['id'],)).fetchone():
        raise ValueError('First-shot diagnostic scope already used; separately reviewed extension required')
    start = con.execute("SELECT MIN(seq) FROM events WHERE id=? AND status='qualification_prepared'", (request['qualificationId'],)).fetchone()[0]
    if start is None or con.execute("SELECT id FROM events WHERE status='qualification_prepared' AND seq>? AND id!=?", (start, request['qualificationId'])).fetchone():
        raise ValueError('Later/unknown qualification accounting needs separate review; no allowance reset')
    hold = con.execute('SELECT note FROM pipeline_holds WHERE id=?', ('qualification-' + request['qualificationId'],)).fetchone()
    if (not hold or hold['note'] != 'Exclusive qualification lease; retain after completion until owner-reviewed clearance'
            or con.execute("SELECT seq FROM events WHERE id=? AND status='pipeline_cleared' AND seq>?",
                           ('qualification-' + request['qualificationId'], start)).fetchone()):
        raise ValueError('Original qualification hold continuity lost or recreated')
    admitted = con.execute('SELECT started FROM attempts WHERE id=?', ('qualification-' + request['qualificationId'],)).fetchone()
    if not admitted or con.execute('SELECT id FROM attempts WHERE started>=? AND id NOT IN (?,?)',
                                   (admitted['started'], 'qualification-' + request['qualificationId'], request['orderId'])).fetchone():
        raise ValueError('Later/unknown ordinary native admissions need separate accounting review')
    total = 1
    if type(accounting.get('actualGameStartsBefore')) is not int or accounting['actualGameStartsBefore'] != total or total >= accounting['maximumActualGameStarts']:
        raise ValueError('Actual task start budget differs/exhausted')
    return approval


def _native_closed(p, request, runner, con):
    packet, state, worker, qplan = _historical(p, request, con)
    rows = runner.native.processes()
    if not isinstance(rows, list) or not rows:
        raise ValueError('Complete native process inventory required')
    forbidden = {'skyrimse.exe', 'skyrimvr.exe', 'skse64_loader.exe', 'sksevr_loader.exe',
                 'vrserver.exe', 'vrmonitor.exe', 'vrcompositor.exe', 'vrstartup.exe', 'vrdashboard.exe',
                 'vrwebhelper.exe', 'vrprismhost.exe'}
    if any(x['name'].lower() in forbidden for x in rows):
        raise ValueError('Current game/VR process blocks diagnostic admission')
    for ident in [worker, *[x['identity'] for x in state.get('owned', [])]]:
        if (not isinstance(ident, dict) or type(ident.get('pid')) is not int or ident['pid'] <= 0
                or type(ident.get('birth')) is not int or ident['birth'] <= 0 or not ident.get('path')
                or runner.native.alive(ident)
                or any(x['pid'] == ident['pid'] for x in rows) and runner.native.identity(ident['pid']) is None):
            raise ValueError('Prior native owner alive or identity unknown')
    runtimes = {Path(qplan['configuration']['runtime'])}
    if p.host().get('runnerConfig'):
        runtimes.add(Path(api().read(p.host()['runnerConfig'])['runtime']))
    if request.get('configuration'):
        runtimes.add(Path(request['configuration']['runtime']))
    for runtime in runtimes:
        for path in (runtime / 'runs').glob('*/state.json'):
            prior = document(path)[0]
            if prior.get('done') is not True or prior.get('restored') is not True or prior.get('restoreErrors'):
                raise ValueError('Unfinished native session blocks diagnostic admission')
            observed_game = prior.get('game')
            if (isinstance(observed_game, dict) and observed_game.get('birth', 0) >= state['game']['birth']
                    and prior.get('order', {}).get('id') not in {'qualification-' + request['qualificationId'], request['orderId']}):
                raise ValueError('Another later native game needs accounting review; no first-shot reset')


def _barriers(p, request, con, own_slot=False, own_job=False):
    holds = [x['id'] for x in con.execute('SELECT id FROM pipeline_holds')]
    if holds != ['qualification-' + request['qualificationId']]:
        raise ValueError('Only the exact retained qualification hold is supported')
    for table, statuses in [('jobs', "'running'"), ('game_sessions', "'preparing','running','finalizing'"),
                            ('retry_attempts', "'running','collecting'"), ('qualifications', "'prepared','running'")]:
        for row in con.execute('SELECT id FROM ' + table + ' WHERE status IN (' + statuses + ')'):
            if not (own_job and table == 'jobs' and row['id'] == request['orderId']):
                raise ValueError('Another active owner blocks diagnostics')
    for row in con.execute("SELECT * FROM cycle_slots WHERE status IN ('reserved','blocked')"):
        if not own_slot or row['id'] != request['slotId'] or row['status'] != 'reserved':
            raise ValueError('Another/blocked installation reservation exists')


def _installed(request, after):
    for item in request['installation']:
        pin(item['source'])
        path = _absolute(item['target'])
        expected = item['source']['sha256'] if after else item['beforeSha256']
        if expected is None:
            if path.exists():
                raise ValueError('Unexpected existing installation target')
        elif not path.is_file() or path.is_symlink() or api().digest(path) != expected:
            raise ValueError('Installed composition differs from exact reviewed delta: ' + str(path))


def _pending_released_authority(p, con):
    """Classify release authority without mistaking the retained hold for expiry.

    The ordinary helper runs only when no holds exist. Here unknown provenance
    stays a barrier; ONLY positively expired, untouched releases may be skipped.
    """
    rows = con.execute("SELECT j.*,r.authorization FROM jobs j JOIN released_orders x ON x.id=j.id JOIN releases r ON r.id=x.release_id WHERE j.status='queued'").fetchall()
    for row in rows:
        if p.queued_preparation_started(con, row):
            return True
        try:
            order = json.loads(row['request'])
            if order.get('cycle') is not None:
                return True
            approval = json.loads(row['authorization']); owner = approval['ownerAuthorization']
            for key in ('threadId', 'messageId', 'quote', 'verifiedBy'):
                api().required_string(owner, key)
            text = read_hashed(_short_pin(owner)).decode('utf-8-sig')
            if owner['quote'] not in text or order['id'] not in approval['orderIds']:
                return True
            deadline = approval.get('deadlineUtc')
            if deadline is None:
                return True  # A release without a deadline retains its authority.
            if type(deadline) not in (int, float) or not math.isfinite(deadline):
                return True
            if time.time() < deadline:
                return True
            # Exact untouched/expired release with intact owner provenance only.
        except (KeyError, ValueError, OSError, TypeError, UnicodeError):
            return True
    return False


def prepare(p, path):
    """Grant only exact FIFO preparation, no installation or game start."""
    m = api(); path = _absolute(str(path)); raw, request_pin = document(path)
    # A lost preparation response must not reread a legitimately changed modlist
    # or offer a second installation. This is only a retained status receipt.
    with p.connect() as con:
        prior = con.execute('SELECT * FROM diagnostic_admissions WHERE id=?', (raw.get('id'),)).fetchone()
    if prior:
        request = _request(dict(prior))
        if request['requestPin'] != request_pin or request['originalRequest'] != raw:
            raise ValueError('Diagnostic preparation identity is immutable')
        return {'id': prior['id'], 'slotId': request['slotId'], 'duplicate': True,
                'status': prior['status'], 'launch': False, 'newInstallationGranted': False}
    keys = {'schemaVersion', 'kind', 'id', 'slotId', 'orderId', 'cycleId', 'sourceChat', 'sourceThreadId',
            'qualificationId', 'qualificationPacket', 'executor', 'installation', 'protectedInputs',
            'taskAccounting', 'knownFault', 'ownerAuthorization', 'deadlineUtc', 'verifiedBy', 'reason',
            'installationPlan', 'baselineAudit', 'prospectiveSubject', 'caseReview'}
    if set(raw) != keys or raw['schemaVersion'] != 1 or raw['kind'] != 'one-shot-diagnostic-preparation':
        raise ValueError('Exact versioned diagnostic preparation required')
    for key in ('id', 'slotId', 'orderId', 'cycleId', 'qualificationId'):
        if not m.SAFE_ID.fullmatch(raw[key]):
            raise ValueError('Safe diagnostic identities required')
    for key in ('sourceChat', 'sourceThreadId', 'verifiedBy', 'reason'):
        m.required_string(raw, key)
    m.owner_evidence(raw, path)
    items = raw['installation']
    if not isinstance(items, list) or len(items) != 10:
        raise ValueError('Exactly the ten agreed published payload files are required')
    targets = set()
    for item in items:
        if set(item) != {'source', 'target', 'beforeSha256'} or not Path(item['target']).is_absolute() or item['target'].casefold() in targets:
            raise ValueError('Exact unique installation targets required')
        targets.add(item['target'].casefold()); pin(item['source'])
        if item['beforeSha256'] is not None and not m.SHA.fullmatch(item['beforeSha256']):
            raise ValueError('Original target hash or explicit absence required')
    if not isinstance(raw['protectedInputs'], list) or not raw['protectedInputs']:
        raise ValueError('Current installed provider/dependency pins required')
    for item in raw['protectedInputs']:
        pin(item)
        if item['path'].casefold() in targets:
            raise ValueError('Changed subject target must not masquerade as protected provider')
    fault = read_pin(raw['knownFault'])
    if (fault.get('kind') != 'known-external-shutdown-fault' or fault.get('qualificationId') != raw['qualificationId']
            or fault.get('phase') != 'ordinary-shutdown' or not fault.get('verifiedBy') or not fault.get('reason')
            or not fault.get('evidence') or fault.get('module') not in raw['protectedInputs']):
        raise ValueError('Exact reviewed external shutdown fault/provider required')
    for item in fault['evidence']:
        pin(item)
    plan = read_pin(raw['installationPlan']); audit = read_pin(raw['baselineAudit']); draft = read_pin(raw['prospectiveSubject'])
    _installation_intent(raw, plan, audit, draft)
    case = read_pin(raw['caseReview'])
    if (raw['caseReview']['sha256'] != APPROVED_CASE_REVIEW_SHA256
            or case.get('actualSlotRequest', {}).get('sha256') != APPROVED_SLOT_REQUEST_SHA256
            or case.get('authoritativeStagingAnchors', {}).get('installation-plan.json') != raw['installationPlan']
            or case.get('authoritativeStagingAnchors', {}).get('baseline-audit.json') != raw['baselineAudit']):
        raise ValueError('Actual independent race/staging review and exact seven-path slot anchor required')
    slot_request_pin = _short_pin(case['actualSlotRequest'])
    actual_ticket = read_pin(slot_request_pin)
    request = {**raw, 'executor': str(_absolute(raw['executor'])), 'originalRequest': read_pin(request_pin),
               'requestPin': request_pin, 'dashboardPins': source_pins(),
               'executorPins': inventory(raw['executor']),
               'reviewPins': [raw['knownFault'], raw['taskAccounting'], raw['installationPlan'], raw['baselineAudit'], raw['prospectiveSubject'], raw['caseReview'], slot_request_pin,
                              _short_pin(plan['sourceArchive']), _short_pin(plan['originalSidecar']['pin']),
                              *fault['evidence'], *[x['source'] for x in items]]}
    with p.connect() as con:
        qrow = con.execute('SELECT request FROM qualifications WHERE id=?', (request['qualificationId'],)).fetchone()
    if not qrow:
        raise ValueError('No historical executor closure')
    qplan = json.loads(qrow['request'])
    if request['executor'] != qplan['executor'] or request['executorPins'] != qplan['executorPins']:
        raise ValueError('Different unqualified executor cannot inherit Q1 evidence')
    profile = Path(qplan['configuration']['profiles']) / draft['profile']
    qinputs = {Path(x['path']): _short_pin(x) for x in qplan['orderData']['inputs']}
    modlist = profile / 'modlist.txt'
    if modlist not in qinputs:
        raise ValueError('Original actual profile modlist pin required')
    modlist_before = read_hashed(qinputs[modlist]).decode('utf-8-sig')
    request['profileBaseline'] = {'profile': str(profile), 'modlistBefore': modlist_before,
                                  'newModName': plan['name']}
    runner = order_platform.activate(request['executor'])
    with runner.native.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        prior = con.execute('SELECT * FROM diagnostic_admissions WHERE id=?', (request['id'],)).fetchone()
        canonical = json.dumps(request, sort_keys=True)
        if prior:
            if prior['request'] != canonical:
                raise ValueError('Diagnostic preparation is immutable')
            _request(dict(prior))
            return {'id': request['id'], 'duplicate': True, 'launch': False}
        approval = _authority(p, request, con)
        _barriers(p, request, con); _native_closed(p, request, runner, con)
        for existing in con.execute("SELECT id FROM diagnostic_admissions WHERE status IN ('preparing','frozen','consumed')"):
            raise ValueError('Another diagnostic owns unresolved preparation/admission: ' + existing['id'])
        _installed(request, False)
        if _pending_released_authority(p, con):
            raise ValueError('Valid released work owns installation before diagnostic preparation')
        slot = None
        for candidate in con.execute("SELECT * FROM cycle_slots WHERE status='waiting' ORDER BY seq").fetchall():
            owner = con.execute('SELECT * FROM cycles WHERE id=?', (candidate['cycle_id'],)).fetchone()
            approval_row = json.loads(owner['authorization']) if owner else {}
            if (not owner or owner['status'] != 'active' or time.time() >= approval_row.get('deadlineUtc', 0)
                    or api().digest(approval_row['ownerAuthorization']['path']) != approval_row['ownerAuthorization']['sha256']):
                con.execute("UPDATE cycle_slots SET status='cancelled',note='Approval stopped/expired/changed' WHERE id=?", (candidate['id'],))
                p.event(con, candidate['id'], 'diagnostic_skipped_inactive_waiting_slot', 'Original request/history retained; no reserved slot cleared')
                continue
            slot = candidate
            break
        if (not slot or slot['id'] != request['slotId'] or slot['order_id'] != request['orderId']
                or slot['cycle_id'] != request['cycleId']):
            raise ValueError('Exact oldest waiting FIFO ticket required')
        ticket = json.loads(slot['request'])
        if ticket != actual_ticket:
            raise ValueError('Actual FIFO ticket differs from independently reviewed exact slot bytes')
        if any(ticket[key] != request[key] for key in ('sourceChat', 'sourceThreadId')):
            raise ValueError('Exact origin installation reservation required')
        if type(slot['iteration']) is not int or not 1 <= slot['iteration'] <= approval['maxIterations']:
            raise ValueError('Exact cycle iteration required')
        writes = [Path(x).resolve() for x in ticket['writePaths']]
        if sorted(map(str, writes)) != sorted(str(_absolute(x)) for x in case['actualSlotRequest']['writePaths']):
            raise ValueError('Native UI/manager side-effect intent differs from agreed slot')
        if any(not any(Path(x['target']).resolve() == w or Path(x['target']).resolve().is_relative_to(w) for w in writes) for x in items):
            raise ValueError('Staged target escapes declared slot writes')
        # Broad UI/profile/log side-effect scopes are NEVER provider exemptions.
        # Only the two specifically approved native metadata files may change.
        metadata = {modlist, _absolute(qplan['configuration']['mo2_ini'])}
        expected = [_short_pin(x) for x in qplan['orderData']['inputs'] if _absolute(x['path']) not in metadata]
        if sorted(expected, key=lambda x: x['path']) != sorted(request['protectedInputs'], key=lambda x: x['path']):
            raise ValueError('Complete unchanged Q1 provider/dependency closure required outside declared UI writes')
        _request({'request': canonical})
        con.execute("INSERT INTO diagnostic_admissions VALUES(?,?,?,?, 'preparing',NULL,NULL,NULL)",
                    (request['id'], request['orderId'], request['cycleId'], canonical))
        con.execute("UPDATE cycle_slots SET status='reserved' WHERE id=?", (request['slotId'],))
        p.event(con, request['slotId'], 'diagnostic_slot_granted', canonical)
    return {'id': request['id'], 'slotId': request['slotId'], 'status': 'reserved', 'launch': False,
            'qualified': False, 'holdRetained': True}


def show(p, identity):
    """Read-only durable dashboard proof; caller must still hold native ownership."""
    with p.connect() as con:
        row = con.execute('SELECT * FROM diagnostic_admissions WHERE id=?', (identity,)).fetchone()
        if not row:
            raise ValueError('Unknown diagnostic identity')
        request = _request(dict(row))
        _authority(p, request, con)
        _barriers(p, request, con, own_slot=True, own_job=row['status'] == 'consumed')
        slot = con.execute('SELECT * FROM cycle_slots WHERE id=?', (request['slotId'],)).fetchone()
        if not slot or slot['status'] != 'reserved':
            raise ValueError('Exact diagnostic installation reservation is not currently reserved')
        return {'schemaVersion': 1, 'kind': 'one-shot-diagnostic-status', 'id': row['id'],
                'status': row['status'], 'slotId': request['slotId'], 'orderId': request['orderId'],
                'sourceChat': request['sourceChat'], 'sourceThreadId': request['sourceThreadId'],
                'preparation': request['requestPin'], 'slotGrantSha256': p.slot_view(slot)['grantSha256'],
                'retainedHoldId': 'qualification-' + request['qualificationId'], 'qualified': False,
                'launchGranted': False, 'nativeIdleVerified': False}


def freeze(p, path):
    """Freeze one actual installed schema2 subject; no game start."""
    m = api(); path = _absolute(str(path)); review, review_pin = document(path)
    if (set(review) != {'schemaVersion', 'kind', 'id', 'subjectOrderSha256', 'platform', 'methodReview', 'installationReceipt', 'verifiedBy', 'reason'}
            or review['schemaVersion'] != 1 or review['kind'] != 'one-shot-diagnostic-freeze'):
        raise ValueError('Exact diagnostic freeze review required')
    for key in ('verifiedBy', 'reason'):
        m.required_string(review, key)
    with p.connect() as con:
        row = con.execute('SELECT * FROM diagnostic_admissions WHERE id=?', (review['id'],)).fetchone()
    if not row:
        raise ValueError('No exact diagnostic preparation')
    request = _request(dict(row)); runner = order_platform.activate(request['executor'])
    with runner.native.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        row = dict(con.execute('SELECT * FROM diagnostic_admissions WHERE id=?', (review['id'],)).fetchone())
        if row['status'] != 'preparing':
            raise ValueError('Freeze requires unconsumed preparation')
        _request(row); _authority(p, request, con); _barriers(p, request, con, own_slot=True)
        _native_closed(p, request, runner, con); _installed(request, True)
        _profile_after(request)
        job = p.get(request['orderId']); order = json.loads(job['request'])
        if (job['status'] != 'queued' or order.get('schemaVersion') != 2 or order.get('mode') != 'automatic'
                or subject_contract.identity(order) != review['subjectOrderSha256']
                or order.get('cycle', {}).get('id') != request['cycleId']
                or order['cycle'].get('slotId') != request['slotId']
                or any(order[x] != request[x] for x in ('sourceChat', 'sourceThreadId'))):
            raise ValueError('Exact untouched installed schema2 cycle subject required')
        p.validate_cycle(con, order); p.verify_inputs(order)
        draft = read_pin(request['prospectiveSubject'])
        if subject_contract.subject_identity(order) != subject_contract.subject_identity(draft):
            raise ValueError('Installed subject differs from reviewed prospective first-case specification')
        receipt = read_pin(review['installationReceipt'])
        _installation_receipt(request, order, receipt)
        if any(con.execute('SELECT 1 FROM ' + t + ' WHERE ' + k + '=?', (order['id'],)).fetchone()
               for t, k in [('attempts', 'id'), ('platform_attempts', 'id'), ('session_members', 'order_id'), ('operator_platform_bindings', 'order_id')]):
            raise ValueError('Prepared/dispatched/grouped subject cannot enter diagnostic admission')
        manifest_path = pin(review['platform']); manifest = read_pin(review['platform'])
        if (set(manifest) != {'schemaVersion', 'kind', 'qualified', 'interface', 'config', 'inputs', 'operations'}
                or manifest['schemaVersion'] != 1 or manifest['kind'] != 'one-shot-diagnostic-platform'
                or manifest['qualified'] is not False or manifest['interface'] != subject_contract.INTERFACE):
            raise ValueError('Explicitly UNQUALIFIED diagnostic platform required')
        providers = manifest['inputs']
        if not providers or any(x not in request['protectedInputs'] for x in providers):
            raise ValueError('Diagnostic providers differ from protected preparation pins')
        for entry in providers:
            pin(entry)
        config_path = _absolute(str(manifest_path.parent / manifest['config']))
        config_pin = file_pin(config_path)
        scenario = subject_contract.compile_plan(order['subjectPlan'], manifest['operations'])
        config_document = read_pin(config_pin)
        # Parse the exact hash-checked document in the validator; do not reread a
        # mutable source path between validation and capturing its expected pin.
        with tempfile.TemporaryDirectory(prefix='diagnostic-config-', dir=p.local) as directory:
            snapshot = Path(directory) / 'config.json'; m.write(snapshot, config_document)
            cfg = order_platform.isolated_config(request['executor'], snapshot, scenario)
        proof = read_pin(review['methodReview'])
        _, state, _, qplan = _historical(p, request, con)
        if not isinstance(state.get('configuration'), dict):
            raise ValueError('Actual effective Q1 configuration required')
        qpacket = read_pin(request['qualificationPacket'])
        result_path = Path(state['profileArchive']).parent / 'result.json'
        result_pin = next(_short_pin(x) for x in qpacket['files'] if Path(x['path']) == result_path)
        qresult = read_pin(result_pin)
        _methods(proof, request, scenario, qplan, qresult)
        delta = _configuration_delta(state['configuration'], cfg, scenario, proof)
        _zero_restarts(request['executor'], scenario)
        for item in proof['evidence']:
            pin(item)
        pins = [*request['dashboardPins'], *request['executorPins'], *request['protectedInputs'],
                *request['reviewPins'], request['requestPin'], review['platform'], review['methodReview'],
                config_pin, review_pin, review['installationReceipt'], request['qualificationPacket'],
                file_pin(Path(request['executor']) / 'run.py'), *proof['evidence']]
        plan = {'schemaVersion': 1, 'kind': 'one-shot-diagnostic-attempt', 'qualified': False,
                'orderId': order['id'], 'subjectOrderSha256': subject_contract.identity(order),
                'subjectSpecificationSha256': subject_contract.subject_identity(order),
                'interface': subject_contract.INTERFACE, 'executor': request['executor'], 'pins': pins,
                'manifestPath': str(manifest_path), 'configuration': cfg, 'scenario': scenario,
                'configurationDelta': delta,
                'diagnosticAdmissionId': request['id'], 'preparedAt': time.time(),
                'diagnosticReview': review_pin}
        canonical = json.dumps(plan, sort_keys=True)
        for value in pins:
            pin(value)
        if read_pin(review_pin) != review or read_pin(review['platform']) != manifest or read_pin(review['methodReview']) != proof:
            raise ValueError('Diagnostic review/mapping/method bytes changed during freeze')
        _request(row); _installed(request, True); p.verify_inputs(order)
        con.execute('INSERT INTO platform_attempts VALUES(?,?,?)', (order['id'], canonical, subject_contract.identity(plan)))
        con.execute("UPDATE diagnostic_admissions SET status='frozen',plan=? WHERE id=?", (canonical, request['id']))
        p.event(con, order['id'], 'unqualified_diagnostic_frozen', canonical)
    m.write(p.evidence_dir(order['id']) / 'platform-plan.json', plan)
    return {'id': request['id'], 'orderId': order['id'], 'qualified': False, 'launch': False}


def _short_pin(value):
    return {'path': value['path'], 'sha256': value['sha256']}


def _configuration_delta(before, after, scenario, proof):
    """Permit only an isolated runtime and the single explicitly reviewed SUT race."""
    expected = copy.deepcopy(before)
    expected['runtime'] = after['runtime']
    fields = ['runtime'] if before.get('runtime') != after['runtime'] else []
    has_beast = any(x.get('args', {}).get('request', {}).get('domain') == 'actor-race'
                    and x['args']['request'].get('race') == '0x000CDD84' for x in scenario['steps'])
    if has_beast and '0x000CDD84' not in after.get('native_session', {}).get('nativeBindings', {}).get('allowedRaceForms', []):
        raise ValueError('Werewolf subject target lacks its explicitly reviewed race permission')
    if expected != after:
        old = expected.get('native_session', {}).get('nativeBindings', {}).get('allowedRaceForms')
        new = after.get('native_session', {}).get('nativeBindings', {}).get('allowedRaceForms')
        if old != ['0x00013746', '0x00013741'] or new != old + ['0x000CDD84']:
            raise ValueError('Only the exact independently reviewed werewolf SUT target may extend Q1 configuration')
        expected['native_session']['nativeBindings']['allowedRaceForms'] = new
        if expected != after:
            raise ValueError('Other bindings/guards/providers/persistence changed from effective Q1')
        target_steps = []
        for step, reviewed in zip(scenario['steps'], proof['steps']):
            request = step.get('args', {}).get('request', {})
            if request.get('domain') == 'actor-race' and request.get('race') == '0x000CDD84':
                if (step.get('tool') != 'platform' or step['args'].get('operation') != 'object.perform'
                        or request.get('action') != 'change-current-race'
                        or request.get('actor') != {'fixtureTag': 'MHeavy'}
                        or request.get('preserveBaseRecord') is not True
                        or reviewed.get('methodStatus') != 'reviewed-diagnostic-target'):
                    raise ValueError('New race target must use the same owned MHeavy method/once guards')
                target_steps.append(step['name'])
        if not target_steps:
            raise ValueError('New race permission lacks its exact reviewed diagnostic subject target')
        fields.append('native_session.nativeBindings.allowedRaceForms')
    return {'kind': 'reviewed-first-case-config-delta', 'beforeSha256': subject_contract.identity(before),
            'afterSha256': subject_contract.identity(after), 'changedFields': fields,
            'werewolfBusinessResultQualified': False}


def _profile_after(request):
    baseline = request['profileBaseline']; profile = Path(baseline['profile'])
    def entries(text):
        return [x.strip() for x in text.splitlines() if x.strip() and not x.lstrip().startswith('#')]
    before = entries(baseline['modlistBefore'])
    after = document_text(profile / 'modlist.txt')
    if entries(after) != ['+' + baseline['newModName'], *before]:
        raise ValueError('Profile activation must preserve every prior mod/order plus ONLY new published base highest')
    mod_root = next(Path(x) for x in read_pin(request['installationPlan'])['writePaths'] if Path(x).name == baseline['newModName'])
    expected = {str(Path(x['target']).relative_to(mod_root)).casefold() for x in request['installation']}
    actual = set()
    for path in mod_root.rglob('*'):
        _absolute(str(path))
        if path.is_file(): actual.add(str(path.relative_to(mod_root)).casefold())
    if actual != expected | {'meta.ini'}:
        raise ValueError('Native installed mod must contain exactly ten original payload files plus meta.ini')


def document_text(path):
    return read_hashed(file_pin(path)).decode('utf-8-sig')


def _installation_intent(request, plan, audit, draft):
    if (request['installationPlan']['sha256'] != APPROVED_INSTALLATION_PLAN_SHA256
            or request['baselineAudit']['sha256'] != APPROVED_BASELINE_AUDIT_SHA256
            or plan['sourceArchive']['sha256'] != APPROVED_ARCHIVE_SHA256
            or plan.get('schemaVersion') != 1 or plan.get('sourceThreadId') != request['sourceThreadId']
            or plan.get('sourceChat') != request['sourceChat'] or plan.get('liveWritesPerformed') is not False
            or plan.get('gameStarted') is not False or plan.get('raceMenuChanged') is not False
            or plan.get('archiveInspection', {}).get('fileCount') != 10
            or _short_pin(plan['stagedAudit']) != request['baselineAudit']
            or _short_pin(plan['sourceArchive']) != _short_pin(audit['archive'])
            or audit.get('expectedArchiveSha256Verified') is not True):
        raise ValueError('Agreed published archive/native UI plan and baseline audit required')
    pin(_short_pin(plan['sourceArchive'])); pin(_short_pin(plan['originalSidecar']['pin']))
    payload = plan['archiveInspection']['payloadFiles']
    if len(payload) != 10 or sorted((x['source']['path'], x['source']['sha256']) for x in request['installation']) != sorted((x['path'], x['sha256']) for x in payload):
        raise ValueError('Staged list differs from the ten original published archive members')
    mod_roots = [Path(x) for x in plan['writePaths'] if Path(x).name == plan['name']]
    if len(mod_roots) != 1:
        raise ValueError('Exact separately accounted published-mod target required')
    expected = sorted(str(_absolute(str(mod_roots[0] / x['destination']))) for x in payload)
    if sorted(x['target'] for x in request['installation']) != expected:
        raise ValueError('Published payload destination changed')
    if (draft.get('schemaVersion') != 2 or draft.get('id') != request['orderId']
            or draft.get('sourceThreadId') != request['sourceThreadId'] or draft.get('sourceChat') != request['sourceChat']):
        raise ValueError('Exact prospective schema2 first-case origin required')
    if (request['prospectiveSubject']['sha256'] != APPROVED_SUBJECT_DRAFT_SHA256
            or subject_contract.subject_identity(draft) != APPROVED_SUBJECT_SPECIFICATION_SHA256
            or subject_contract.identity(draft['subjectPlan']) != APPROVED_SUBJECT_PLAN_SHA256
            or subject_contract.identity(draft['testing']) != APPROVED_TESTING_SHA256):
        raise ValueError('Only the independently approved exact20 subject specification is supported')
    subject_contract.validate(draft['subjectPlan'])


def _installation_receipt(request, order, receipt):
    if (receipt.get('kind') != 'diagnostic-native-installation-receipt'
            or receipt.get('preparationId') != request['id'] or receipt.get('slotId') != request['slotId']
            or receipt.get('orderId') != order['id'] or receipt.get('sourceThreadId') != order['sourceThreadId']
            or receipt.get('installationPlan') != request['installationPlan'] or receipt.get('baselineAudit') != request['baselineAudit']
            or receipt.get('archiveInstalled') is not True or receipt.get('managerRefreshed') is not True
            or receipt.get('installationSettled') is not True or receipt.get('profile') != order['profile']
            or not receipt.get('verifiedBy') or not receipt.get('reason') or not receipt.get('evidence')
            or receipt.get('installedInputs') != order['inputs']):
        raise ValueError('Complete native UI/Installed accounting/profile/current input receipt required')
    expected = sorted((x['target'], x['source']['sha256']) for x in request['installation'])
    if sorted((x['path'], x['sha256']) for x in receipt.get('vfsWinners', [])) != expected:
        raise ValueError('All ten actual native VFS winners must match the published payload')
    for value in receipt['evidence']:
        pin(value)


def _method_key(step):
    args = step.get('args', {}); request = args.get('request', {})
    return (step.get('tool'), args.get('operation'), request.get('domain'), request.get('action'))


def _methods(proof, request, scenario, qplan, qresult):
    if (set(proof) != {'schemaVersion', 'kind', 'qualificationPacket', 'steps', 'evidence', 'verifiedBy', 'reason'}
            or proof['schemaVersion'] != 1 or proof['kind'] != 'diagnostic-method-review'
            or proof['qualificationPacket'] != request['qualificationPacket']
            or not proof['verifiedBy'] or not proof['reason'] or not proof['evidence']):
        raise ValueError('Actual per-method diagnostic evidence review required')
    reviewed = proof['steps']
    if not isinstance(reviewed, list) or len(reviewed) != len(scenario['steps']):
        raise ValueError('Each compiled diagnostic step needs method review')
    checks = qresult.get('checks', [])
    passed = {x['name'] for x in checks if x.get('result') == 'passed'
              and sum(y.get('name') == x['name'] for y in checks) == 1}
    factual = [x for x in qplan['scenario']['steps'] if x['name'] in passed]
    for step, row in zip(scenario['steps'], reviewed):
        if (set(row) != {'name', 'compiledStepSha256', 'methodStatus', 'nativeMethodCovered', 'reason'}
                or row['name'] != step['name'] or row['compiledStepSha256'] != subject_contract.identity(step)
                or row['methodStatus'] not in {'observed-Q1', 'reviewed-diagnostic-target'}
                or row['nativeMethodCovered'] is not True or not row['reason']):
            raise ValueError('Unknown/uncovered native method or changed diagnostic target')
        if step.get('tool') != 'platform' or step.get('args', {}).get('operation') not in {'state.read', 'world.read', 'object.perform'}:
            raise ValueError('Only reviewed core platform operation families are supported')
        candidates = [x for x in factual if _method_key(x) == _method_key(step)]
        if not candidates:
            raise ValueError('Native method family has no positive Q1 evidence')
        if row['methodStatus'] == 'observed-Q1' and not any(x['args'] == step['args'] for x in candidates):
            raise ValueError('Changed request is a diagnostic target, not observed Q1 behavior')


def _zero_restarts(executor, scenario):
    code = "import sys,json;from pathlib import Path;r=Path(sys.argv[1]).resolve();sys.path.insert(0,str(r));from skyrim_autotest.restart_budget import plan;assert plan(json.load(sys.stdin))['maximum']==0,'Diagnostic restarts forbidden'"
    child = subprocess.run([sys.executable, '-c', code, executor], input=json.dumps(scenario), capture_output=True, text=True, timeout=30)
    if child.returncode:
        raise ValueError('Diagnostic restart budget refused: ' + child.stderr[-1000:])


def verify_plan(p, order, plan, require_file=True):
    m = api(); row = saved(p, order['id'])
    if (not row or row['status'] not in {'frozen', 'consumed', 'completed'} or row['plan'] != json.dumps(plan, sort_keys=True)
            or plan.get('qualified') is not False or plan.get('diagnosticAdmissionId') != row['id']
            or plan['subjectOrderSha256'] != subject_contract.identity(order)):
        raise ValueError('Exact registered unqualified diagnostic plan required')
    request = _request(row)
    for entry in plan['pins']:
        pin(entry)
    _installed(request, True)
    _profile_after(request)
    if require_file and m.read(p.evidence_dir(order['id']) / 'platform-plan.json') != plan:
        raise ValueError('Frozen diagnostic plan file changed')
    return plan


def authorize(p, order, con):
    row = saved(p, order['id'], con)
    if not row:
        return False
    if row['status'] != 'consumed':
        raise ValueError('Diagnostic order needs its once-only consumed admission')
    request = _request(row)
    _authority(p, request, con); _barriers(p, request, con, own_slot=True, own_job=True)
    p.validate_cycle(con, order); p.validate_profile_selection(order)
    if subject_contract.identity(order) != json.loads(row['plan'])['subjectOrderSha256']:
        raise ValueError('Diagnostic subject changed')
    return True


def execute(p, path):
    """Consume exactly one frozen subject, retaining the qualification hold."""
    m = api(); path = _absolute(str(path)); review, review_pin = document(path)
    if (set(review) != {'schemaVersion', 'kind', 'id', 'platformPlanSha256', 'verifiedBy', 'reason'}
            or review['schemaVersion'] != 1 or review['kind'] != 'one-shot-diagnostic-execution'
            or not review['verifiedBy'] or not review['reason']):
        raise ValueError('Exact one-shot execution review required')
    with p.connect() as con:
        row = con.execute('SELECT * FROM diagnostic_admissions WHERE id=?', (review['id'],)).fetchone()
    if not row:
        raise ValueError('No registered diagnostic')
    row = dict(row); request = _request(row); runner = order_platform.activate(request['executor'])
    with runner.native.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        row = dict(con.execute('SELECT * FROM diagnostic_admissions WHERE id=?', (review['id'],)).fetchone())
        canonical = json.dumps({'review': review, 'pin': review_pin}, sort_keys=True)
        if row['status'] in {'consumed', 'completed'}:
            if row['review'] != canonical:
                raise ValueError('Consumed diagnostic review is immutable')
            return {'id': row['id'], 'status': 'already_consumed', 'rerun': False}
        if row['status'] != 'frozen':
            raise ValueError('Exact frozen diagnostic required')
        _request(row); _authority(p, request, con); _barriers(p, request, con, own_slot=True)
        plan = json.loads(row['plan'])
        if subject_contract.identity(plan) != review['platformPlanSha256']:
            raise ValueError('Reviewed diagnostic plan differs')
        _native_closed(p, {**request, 'configuration': plan['configuration']}, runner, con)
        job = dict(con.execute('SELECT * FROM jobs WHERE id=?', (request['orderId'],)).fetchone())
        order = json.loads(job['request'])
        if job['status'] != 'queued':
            raise ValueError('Only exact untouched queued diagnostic subject may be claimed')
        verify_plan(p, order, plan); p.verify_inputs(order); p.validate_cycle(con, order)
        p.validate_profile_selection(order)
        if read_pin(review_pin) != review:
            raise ValueError('Execution review changed before atomic consumption')
        con.execute("UPDATE diagnostic_admissions SET status='consumed',review=? WHERE id=?", (canonical, row['id']))
        con.execute("UPDATE jobs SET status='running' WHERE id=?", (order['id'],))
        p.event(con, order['id'], 'one_shot_unqualified_diagnostic_consumed', canonical)
        job = dict(con.execute('SELECT * FROM jobs WHERE id=?', (order['id'],)).fetchone())
    return p.execute_claimed(job)


def complete(p, path):
    """Record exact ended attempt accounting, keeping the consumed identity/hold."""
    m = api(); review, review_pin = document(path)
    if (set(review) != {'schemaVersion', 'kind', 'orderId', 'packet', 'verifiedBy', 'reason'}
            or review['schemaVersion'] != 1 or review['kind'] != 'one-shot-diagnostic-completion'
            or not review['verifiedBy'] or not review['reason']):
        raise ValueError('Explicit reviewed diagnostic completion required')
    order = json.loads(p.get(review['orderId'])['request'])
    row = saved(p, order['id']); request = _request(row)
    runner = order_platform.activate(request['executor'])
    folder = p.evidence_dir(order['id'])
    child, child_pin = document(folder / 'diagnostic-child-exit.json')
    worker_document, worker_pin = document(folder / 'diagnostic-worker.json'); worker = worker_document['identity']
    with runner.native.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        current = dict(con.execute('SELECT * FROM diagnostic_admissions WHERE id=?', (row['id'],)).fetchone())
        if current['status'] != 'consumed' or current['review'] != row['review']:
            raise ValueError('Diagnostic completion identity changed')
        if type(child.get('returncode')) is not int or child.get('timeout'):
            raise ValueError('Diagnostic child completion remains uncertain')
        matches = p.matching_runs(order)
        if len(matches) != 1:
            raise ValueError('Exact one-run diagnostic accounting required')
        state_path, state = matches[0]
        if state.get('runner') != worker or state.get('done') is not True or state.get('restored') is not True or state.get('restoreErrors'):
            raise ValueError('Exact completed diagnostic worker/restoration required')
        starts = p.native_game_starts(state)
        if starts != 1:
            raise ValueError('Diagnostic physical start count uncertain or exceeded')
        rows = runner.native.processes()
        if not isinstance(rows, list) or not rows:
            raise ValueError('Complete current native inventory required')
        for ident in [worker, *[x['identity'] for x in state.get('owned', [])]]:
            if runner.native.alive(ident) or any(x['pid'] == ident['pid'] for x in rows) and runner.native.identity(ident['pid']) is None:
                raise ValueError('Diagnostic owner remains live or unknown')
        job = dict(con.execute('SELECT * FROM jobs WHERE id=?', (order['id'],)).fetchone())
        _, packet = p.verify_packet(job)
        if file_pin(job['packet']) != review['packet'] or read_pin(review['packet']) != packet:
            raise ValueError('Exact reviewed completed packet required')
        for value in (child_pin, worker_pin):
            if not any(x['path'] == value['path'] and x['sha256'] == value['sha256'] for x in packet['files']):
                raise ValueError('Completed worker/child identity must be in pinned ordinary packet')
            pin(value)
        if packet.get('runDirectory') != str(state_path.parent) or packet.get('restored') is not True:
            raise ValueError('Diagnostic packet/restoration differs')
        archive = state_path.parent / 'test-profile'
        if (Path(state.get('profileArchive', '')).resolve() != archive.resolve() or not archive.is_dir()
                or not any(x.is_file() for x in archive.rglob('*')) or Path(state['testProfile']).exists()):
            raise ValueError('Diagnostic archive/removal unproven')
        if not con.execute('SELECT id FROM pipeline_holds WHERE id=?', ('qualification-' + request['qualificationId'],)).fetchone():
            raise ValueError('Retained qualification hold disappeared')
        if read_pin(review_pin) != review:
            raise ValueError('Completion review changed before recording')
        con.execute("UPDATE diagnostic_admissions SET status='completed',actual_starts=? WHERE id=?", (starts, row['id']))
        p.event(con, order['id'], 'diagnostic_completed_unqualified_hold_retained',
                json.dumps({'actualGameStarts': starts, 'historicalCumulativeActualGameStarts': None,
                            'qualified': False, 'review': review_pin}))
    return {'id': row['id'], 'status': 'completed', 'actualGameStarts': starts, 'qualified': False,
            'holdRetained': True, 'newLaunchGranted': False}


def dispatch(p, order, command, log):
    """Bound the ordinary fresh child only for this consumed diagnostic."""
    m = api(); row = saved(p, order['id']); request = _request(row)
    folder = p.evidence_dir(order['id'])
    expires = min(time.time() + 900, request['deadlineUtc'])
    m.write(folder / 'diagnostic-dispatch-intent.json', {'id': row['id'], 'expires': expires, 'maximumActualGameStarts': 1})
    try:
        child = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, shell=False,
                               timeout=max(.01, expires - time.time()), env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        result = {'returncode': child.returncode}
    except subprocess.TimeoutExpired:
        result = {'timeout': True, 'reason': 'Diagnostic deadline exhausted; exact child stopped, guardian recovery required'}
    m.write(folder / 'diagnostic-child-exit.json', result)
    return result.get('returncode', -1)


@contextlib.contextmanager
def child_guard(p, order, runner):
    m = api(); row = saved(p, order['id']); request = _request(row)
    folder = p.evidence_dir(order['id'])
    intent = m.read(folder / 'diagnostic-dispatch-intent.json')
    if row['status'] != 'consumed' or intent['id'] != row['id'] or time.time() >= intent['expires']:
        raise ValueError('Unconsumed/expired diagnostic child refused')
    worker_path = folder / 'diagnostic-worker.json'
    if worker_path.exists():
        raise ValueError('Diagnostic child admission is once-only; recover lost response')
    with runner.native.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        authorize(p, order, con)
        _native_closed(p, {**request, 'configuration': json.loads(row['plan'])['configuration']}, runner, con)
        if worker_path.exists():
            raise ValueError('Another diagnostic child already owns admission')
        ident = runner.native.identity(os.getpid())
        if not isinstance(ident, dict) or ident.get('pid') != os.getpid() or type(ident.get('birth')) is not int or ident['birth'] <= 0 or not ident.get('path'):
            raise ValueError('Exact current diagnostic worker identity unavailable')
        m.write(worker_path, {'identity': ident, 'admissionId': row['id']})
    original = runner.request; starts = 0
    def guarded(port, route, *args, **kwargs):
        nonlocal starts
        if route == 'run':
            if starts or time.time() >= intent['expires']:
                raise ValueError('Diagnostic one-start/deadline budget exhausted')
            starts += 1
            m.write(folder / 'diagnostic-launch-intent.json', {'id': row['id'], 'maximumActualGameStarts': 1})
        return original(port, route, *args, **kwargs)
    runner.request = guarded
    try:
        yield
    finally:
        runner.request = original

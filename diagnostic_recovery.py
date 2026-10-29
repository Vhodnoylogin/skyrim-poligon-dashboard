"""Two-phase cleanup only: preserve the queued subject and all launch barriers."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import time

import diagnostic_admission as d
import order_platform
from qualification import inventory
from qualification_mo2_boundary import gui_delta

ASSESSMENT_SHA256 = '28eef031b6518ad63a0349d55b17a1cc820faae8ceac1be3bf7a9330775d37d6'
INSTALL_HELPER_SHA256 = 'ac55685cb9ca165a552550be687b73fa02943d96ff6d3481fea87ff642efad8a'
LEGACY_MANIFEST_SHA256 = '67e0c34e0d246cdc5d7722d4262e2ecd25dee12ac1da04fc231ccc3d9482b9a0'


def _known_source():
    return d.read_pin({'path': str(Path(__file__).with_name('legacy-diagnostic-917-source.json')),
                       'sha256': LEGACY_MANIFEST_SHA256})['files']


def _hash(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _table(con):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='diagnostic_recoveries'").fetchone())


def _schema(con):
    con.execute('''CREATE TABLE IF NOT EXISTS diagnostic_recoveries
      (id TEXT PRIMARY KEY, diagnostic_id TEXT UNIQUE NOT NULL, request TEXT NOT NULL,
       status TEXT NOT NULL, completion TEXT)''')


def _row(con, identity):
    row = con.execute('SELECT * FROM diagnostic_recoveries WHERE id=?', (identity,)).fetchone() if _table(con) else None
    return dict(row) if row else None


def _events(con, identity):
    return [dict(x) for x in con.execute('SELECT * FROM events WHERE id=? ORDER BY seq', (identity,))]


def inspect(p, identity):
    """Read-only review data; no lease, cleanup or launch authorization."""
    with p.connect() as con:
        legacy = con.execute('SELECT * FROM diagnostic_admissions WHERE id=?', (identity,)).fetchone()
        if not legacy:
            raise ValueError('Unknown diagnostic preparation')
        legacy = dict(legacy); request = json.loads(legacy['request'])
        job = dict(con.execute('SELECT * FROM jobs WHERE id=?', (request['orderId'],)).fetchone())
        slot = con.execute('SELECT * FROM cycle_slots WHERE id=?', (request['slotId'],)).fetchone()
        return {'diagnosticId': identity, 'status': legacy['status'], 'preparedRequestSha256': _hash(legacy['request']),
                'subjectOrderSha256': d.subject_contract.identity(json.loads(job['request'])),
                'slotGrantSha256': p.slot_view(slot)['grantSha256'], 'cleanupGranted': False, 'launchGranted': False}


def _legacy(p, con, review, status):
    legacy = dict(con.execute('SELECT * FROM diagnostic_admissions WHERE id=?', (review['diagnosticId'],)).fetchone() or {})
    if (not legacy or legacy['status'] != status or legacy['plan'] is not None or legacy['review'] is not None
            or legacy['actual_starts'] is not None or _hash(legacy['request']) != review['preparedRequestSha256']):
        raise ValueError('Exact never-frozen/consumed legacy preparation required')
    request = json.loads(legacy['request'])
    if d.read_pin(request['requestPin']) != request['originalRequest']:
        raise ValueError('Original immutable preparation document changed')
    job = dict(con.execute('SELECT * FROM jobs WHERE id=?', (request['orderId'],)).fetchone() or {})
    slot = dict(con.execute('SELECT * FROM cycle_slots WHERE id=?', (request['slotId'],)).fetchone() or {})
    cycle = dict(con.execute('SELECT * FROM cycles WHERE id=?', (request['cycleId'],)).fetchone() or {})
    if (not job or job['status'] != 'queued' or any(job[k] is not None for k in ('packet', 'delivery', 'mailbox_id'))
            or d.subject_contract.identity(json.loads(job['request'])) != review['subjectOrderSha256']
            or not cycle or not slot or slot['cycle_id'] != request['cycleId'] or slot['status'] != 'reserved' or slot['order_id'] != job['id']
            or not slot['receipt'] or p.slot_view(slot)['grantSha256'] != review['slotGrantSha256']):
        raise ValueError('Exact acknowledged reserved slot and unchanged queued subject required')
    if [x['status'] for x in _events(con, job['id'])] != ['queued']:
        raise ValueError('Subject already has execution/progress history')
    diag_events = _events(con, review['diagnosticId']); slot_events = _events(con, slot['id'])
    semantic=[x for x in slot_events if x['status']!='slot_ever_granted']
    witnesses=[x for x in slot_events if x['status']=='slot_ever_granted']
    allowed_witnesses={'SQLite witness: waiting -> reserved; grant/ack state observed',
                       'SQLite witness: reserved -> reserved; grant/ack state observed',
                       'SQLite witness: retained reserved/blocked/acknowledged slot at initialization'}
    if (diag_events or any(x['note'] not in allowed_witnesses for x in witnesses)
            or [x['status'] for x in semantic] != ['slot_requested','diagnostic_slot_granted','slot_acknowledged']
            or json.loads(semantic[1]['note']) != request or semantic[2]['note'] != slot['receipt']
            or json.loads(semantic[0]['note']) != json.loads(slot['request'])):
        raise ValueError('Exact original never-dispatched917 grant/request/event graph required')
    ack = json.loads(slot['receipt'])
    expected_ack = {'schemaVersion':1,'slotId':slot['id'],'cycleId':slot['cycle_id'],'iteration':slot['iteration'],
                    'orderId':slot['order_id'],'sourceChat':request['sourceChat'],'sourceThreadId':request['sourceThreadId'],
                    'grantSha256':review['slotGrantSha256']}
    if set(ack) != {'kind','path','sha256'} or ack['kind'] != 'file-ack':
        raise ValueError('Original file-ack hash and exact origin/grant tuple required')
    ack_document=d.read_pin(d._short_pin(ack))
    if any(ack_document.get(k)!=v for k,v in expected_ack.items()):
        raise ValueError('Original file-ack hash and exact origin/grant tuple required')
    for table, key in (('attempts', 'id'), ('platform_attempts', 'id'), ('session_members', 'order_id'),
                       ('retry_attempts', 'order_id'), ('operator_platform_bindings', 'order_id'),
                       ('operator_bound_admissions', 'id'), ('notification_results', 'id')):
        if con.execute('SELECT 1 FROM ' + table + ' WHERE ' + key + '=?', (job['id'],)).fetchone():
            raise ValueError('Dispatch, platform, attempt, session or notification trace exists')
    folder = p.evidence_dir(job['id']); logs = []
    d._absolute(str(folder))
    if folder.exists():
        for path in folder.iterdir():
            if path.name != 'service-findings.jsonl' or not path.is_file():
                raise ValueError('Unknown native/dispatch evidence cannot become zero starts')
            logs.append(d.file_pin(path))
    qrow = con.execute('SELECT request FROM qualifications WHERE id=?',(request['qualificationId'],)).fetchone()
    managed_ini = json.loads(qrow['request'])['configuration']['mo2_ini']
    return request, {'diagnostic': legacy, 'diagnosticEvents':diag_events, 'job': job, 'slot': slot, 'cycle': cycle,
                     'managedIni': managed_ini,'ackPin':d._short_pin(ack),'ackDocument':ack_document,
                     'cycleEvents': _events(con, request['cycleId']),
                     'jobEvents': _events(con, job['id']), 'slotEvents': _events(con, slot['id']), 'logs': logs}


def _source(request):
    """Validate ORIGINAL source directly; never _request(new-code) or repin it."""
    if inventory(request['executor']) != request['executorPins']:
        raise ValueError('Original pinned native observer changed')
    known=_known_source();pins=request['dashboardPins']
    if (len(pins)!=len(known) or len({Path(x['path']).parent for x in pins})!=1
            or {Path(x['path']).name:x['sha256'] for x in pins} != known):
        raise ValueError('Legacy producer must match the exact published917 source manifest')
    frozen = []
    for item in request['dashboardPins']:
        raw = d.read_hashed(item)
        frozen.append({'pin': item, 'base64': base64.b64encode(raw).decode('ascii')})
    for item in request['reviewPins']:
        d.pin(item)
    return frozen


def _assessment(review, request, managed_ini):
    if review['assessment']['sha256'] != ASSESSMENT_SHA256 or review['installHelper']['sha256'] != INSTALL_HELPER_SHA256:
        raise ValueError('Exact independently reviewed real installation/preimages required')
    assessment = d.read_pin(review['assessment']); d.pin(review['installHelper'])
    if (assessment.get('kind') != 'read-only-minimal-unstarted-preparation-restoration-assessment'
            or len(assessment.get('modFiles', [])) != 11 or len(assessment.get('newDownloadFiles', [])) != 2
            or len(assessment.get('freshPreimages', [])) != 11 or not assessment.get('noRestorationPerformed')
            or any(x['beforeSha256'] is not None for x in request['installation'])):
        raise ValueError('Owned thirteen-file delta and true before-install absence required')
    root = d._absolute(assessment['rootMod'])
    expected = {d._absolute(x['target']): x['source']['sha256'] for x in request['installation']}
    observed = {d._absolute(x['path']): x['sha256'] for x in assessment['modFiles']}
    if (len(expected) != 10 or len(observed) != 11 or any(observed.get(k) != v for k, v in expected.items())
            or set(observed) - set(expected) != {root / 'meta.ini'}
            or any(root not in path.parents for path in observed)):
        raise ValueError('Assessment does not describe exactly ten published files plus native meta.ini')
    plan = d.read_pin(request['installationPlan']); downloads = assessment['newDownloadFiles']
    if (downloads[0]['sha256'] != plan['sourceArchive']['sha256']
            or Path(downloads[1]['path']) != Path(downloads[0]['path'] + '.meta')
            or any(not x.get('beforeAbsentProvenBy') for x in downloads)):
        raise ValueError('Exactly the owned copied archive and sidecar required')
    started = d.read_pin(review['installationStarted']); ready = d.read_pin(review['nativeUiReady'])
    if (started.get('slotId') != request['slotId'] or started.get('grantSha256') != review['slotGrantSha256']
            or ready.get('slotId') != request['slotId'] or ready.get('archive') != downloads[0]['path']
            or ready.get('sha256') != downloads[0]['sha256']
            or any(x.get('gameStarted') is not False or x.get('nativeMutexHeld') is not True for x in (started, ready))):
        raise ValueError('Executed absence-preflight/owned installation provenance required')
    preimages = assessment['freshPreimages']; paths = {Path(x['path']) for x in preimages}
    profile = Path(request['profileBaseline']['profile'])
    if (len(paths) != 11 or len([x for x in paths if x.parent == profile]) != 10
            or profile/'modlist.txt' not in paths or paths-{x for x in paths if x.parent==profile} != {Path(managed_ini)}):
        raise ValueError('Fresh native manager plus ten exact profile preimages required')
    index = Path(preimages[0]['backup']).parent/'index.jsonl'; index_pin=d.file_pin(index); raw = d.read_hashed(index_pin)
    rows = [d._json(line.encode('utf-8')) for line in raw.decode('utf-8').splitlines() if line]
    if rows != [{k: x[k] for k in ('path', 'backup', 'sha256')} for x in preimages]:
        raise ValueError('Fresh eleven-file preimage index differs')
    for x in preimages:
        d.pin({'path': x['backup'], 'sha256': x['sha256']})
    assessment['managedIniPath']=managed_ini
    return assessment,index_pin


def _profiles(request, restored):
    profile=Path(request['profileBaseline']['profile']); name=request['profileBaseline']['newModName']
    listing=[];references=[]
    directories=list(profile.parent.iterdir())
    if len(directories)>256:raise ValueError('Profile scope exceeds bounded cleanup inventory')
    for directory in sorted(directories):
        d._absolute(str(directory))
        if not directory.is_dir():raise ValueError('Unknown entry in native profile scope')
        path=directory/'modlist.txt'; value=d.file_pin(path); raw=d.read_hashed(value).decode('utf-8-sig')
        listing.append(value)
        for line in raw.splitlines():
            if line.strip().lstrip('+-').casefold()==name.casefold():references.append((str(path),line.strip()))
    expected=[] if restored else [(str(profile/'modlist.txt'),'+'+name)]
    if references!=expected:raise ValueError('Another profile references the globally removed mod, or source reference changed')
    return listing


def _current(request, assessment, restored):
    root = d._absolute(assessment['rootMod'])
    owned = [*assessment['modFiles'], *assessment['newDownloadFiles']]
    if restored:
        if root.exists() or any(d._absolute(x['path']).exists() for x in assessment['newDownloadFiles']):
            raise ValueError('Owned new mod/download preimages were absent; restoration is incomplete')
    else:
        expected_files={Path(x['path']) for x in assessment['modFiles']}
        expected_dirs={parent for path in expected_files for parent in path.parents if root in parent.parents}
        entries=set()
        for item in root.rglob('*'):
            checked=d._absolute(str(item))
            if checked not in expected_files|expected_dirs:raise ValueError('Changed/extra owned mod entries forbid cleanup reservation')
            entries.add(checked)
        if entries != expected_files|expected_dirs or any(not x.is_file() and not x.is_dir() for x in entries):
            raise ValueError('Changed/extra owned mod files forbid cleanup reservation')
        for x in owned:
            d.pin(d._short_pin(x))
    fresh_paths = {Path(x['path']) for x in assessment['freshPreimages']}
    for x in request['protectedInputs']:
        if Path(x['path']) not in fresh_paths:
            d.pin(x)
    for x in assessment['freshPreimages']:
        if Path(x['path']) == Path(assessment['managedIniPath']):
            gui_delta(d.read_hashed({'path': x['backup'], 'sha256': x['sha256']}), d.read_hashed(d.file_pin(x['path'])))
        else:
            expected = x['sha256'] if restored else x['currentSha256']
            d.pin({'path': x['path'], 'sha256': expected})
    for item in assessment['diagnosticEvidencePathFacts']:
        if item['exists'] is not False or d._absolute(item['path']).exists():
            raise ValueError('Original no-dispatch/runtime evidence boundary changed')
    return _profiles(request,restored)


def _archive(review, assessment, recovery_id, p):
    manifest = d.read_pin(review['archive'])
    expected = [d._short_pin(x) for x in [*assessment['modFiles'], *assessment['newDownloadFiles']]]
    root = p.local/'diagnostic-recoveries'/recovery_id/'archive'
    if (set(manifest) != {'schemaVersion', 'kind', 'recoveryId', 'files'} or manifest['schemaVersion'] != 1
            or manifest.get('kind') != 'diagnostic-preexecution-recovery-archive' or manifest.get('recoveryId') != recovery_id
            or [x.get('original') for x in manifest.get('files', [])] != expected):
        raise ValueError('Exact thirteen archived owned postimages required')
    seen = set()
    for item in manifest['files']:
        if set(item) != {'original', 'archived'}:
            raise ValueError('Exact original/archive member pins required')
        path = d.pin(item['archived'])
        if root not in path.parents or path in seen or item['archived']['sha256'] != item['original']['sha256']:
            raise ValueError('Independent scoped archive member/payload differs')
        seen.add(path)
    return [review['archive'],*[x['archived'] for x in manifest['files']]]


def _reserve_proofs(record):
    review=record['review'];request=json.loads(record['legacy']['diagnostic']['request'])
    return [record['reviewPin'],record['preimageIndex'],record['legacy']['ackPin'],
            d._short_pin(review['ownerAuthorization']),*record['implementationPins'],*request['executorPins'],
            {'path':str(Path(__file__).with_name('legacy-diagnostic-917-source.json')),'sha256':LEGACY_MANIFEST_SHA256},
            *[review[k] for k in ('assessment','installationReceipt','installHelper','installationStarted','nativeUiReady')],
            *record['installationEvidence'],
            *request['reviewPins'],*[x['pin'] for x in record['source']],
            *[{'path':x['backup'],'sha256':x['sha256']} for x in record['assessment']['freshPreimages']]]


def _restoration(review, record, p, runner=None, native=None, historical=None):
    receipt=d.read_pin(review['restorationReceipt']);request=json.loads(record['legacy']['diagnostic']['request'])
    order=json.loads(record['legacy']['job']['request']);assessment=record['assessment']
    keys={'schemaVersion','kind','recoveryId','reservedReviewPin','sourceChat','sourceThreadId','instance','profile',
          'managerIdentity','noGameStarted','archive','rollbackTargets','nativeUiActor','readback','verifiedBy','reason'}
    targets=[x['path'] for x in [*assessment['modFiles'],*assessment['newDownloadFiles']]]
    modlist=str(Path(request['profileBaseline']['profile'])/'modlist.txt')
    managed=Path(assessment['managedIniPath'])
    if (set(receipt)!=keys or receipt['schemaVersion']!=1 or receipt['kind']!='diagnostic-preexecution-native-restoration-receipt'
            or receipt['recoveryId']!=record['review']['id'] or receipt['reservedReviewPin']!=record['reviewPin']
            or any(receipt[k]!=request[k] for k in ('sourceChat','sourceThreadId'))
            or Path(receipt['instance'])!=managed.parent or receipt['profile']!=order['profile']
            or receipt['noGameStarted'] is not True or receipt['archive']!=review['archive']
            or receipt['rollbackTargets']!=targets+[modlist] or not receipt['verifiedBy'] or not receipt['reason']):
        raise ValueError('Exact external native-UI restoration provenance/scope required')
    actor=receipt['nativeUiActor']
    if set(actor)!={'helper','evidence'} or not actor['evidence']:raise ValueError('Reviewed native UI actor/source evidence required')
    if runner is not None:
        actor_source={'pin':actor['helper'],'base64':base64.b64encode(d.read_hashed(actor['helper'])).decode('ascii')}
    else:
        actor_source=historical['actorSource']
        if actor_source['pin']!=actor['helper'] or hashlib.sha256(base64.b64decode(actor_source['base64'],validate=True)).hexdigest()!=actor['helper']['sha256']:
            raise ValueError('Frozen native actor source proof differs')
    for value in actor['evidence']:d.pin(value)
    readback=d.read_pin(receipt['readback']);manager=receipt['managerIdentity']
    if (set(manager)!={'pid','birth','path'} or type(manager['pid']) is not int or manager['pid']<=0
            or type(manager['birth']) is not int or manager['birth']<=0 or Path(manager['path'])!=managed.parent/'ModOrganizer.exe'
            or readback.get('managerIdentity')!=manager or readback.get('profile')!=order['profile']
            or readback.get('busyKnown') is not True or readback.get('busy') is not None
            or readback.get('managerRefreshed') is not True or readback.get('newModAbsent') is not True
            or readback.get('downloadsAbsent')!=[True,True] or len(readback.get('vfsWinners',[]))!=10):
        raise ValueError('Exact refreshed SE manager/idle/absence/VFS readback required')
    original={Path(x['path']):x['sha256'] for x in order['inputs'] if Path(x['path']) not in {Path(v['target']) for v in request['installation']}}
    virtual=[str(Path(x['target']).relative_to(Path(assessment['rootMod']))) for x in request['installation']]
    for row,name in zip(readback['vfsWinners'],virtual):
        provider=row.get('provider');metadata=name.casefold() in {'claw-build.json','readme.md','readme.ru.md'}
        if set(row)!={'virtualPath','provider'} or row['virtualPath']!=name:raise ValueError('Exact ten virtual paths required')
        if metadata and provider is None:continue
        if not isinstance(provider,dict):raise ValueError('Original game provider cannot be absent')
        path=Path(provider.get('path',''))
        if ((not metadata and original.get(path)!=provider.get('sha256')) or Path(assessment['rootMod']) in path.parents
                or tuple(x.casefold() for x in path.parts[-len(Path(name).parts):])!=tuple(x.casefold() for x in Path(name).parts)):
            raise ValueError('Seven game VFS winners must be original; exact three metadata observations cannot point to removed mod')
        if runner is not None:d.pin(provider)
    if runner is not None:
        if (not any(x['pid']==manager['pid'] and x['name'].lower()=='modorganizer.exe' for x in native['processes'])
                or runner.native.identity(manager['pid'])!=manager):
            raise ValueError('Restoration manager identity is stale or not the current native SE process')
    return {'receipt':review['restorationReceipt'],'readback':receipt['readback'],'managerIdentity':manager,'actorSource':actor_source,
            'proofPins':[review['restorationReceipt'],receipt['readback'],actor['helper'],*actor['evidence'],
                         *[x['provider'] for x in readback['vfsWinners'] if x['provider'] is not None]],
            'certification':'Physical postconditions plus independently reviewed pinned native-UI/VFS evidence'}


def reserve(p, path):
    review, review_pin = d.document(path)
    keys = {'schemaVersion', 'kind', 'id', 'diagnosticId', 'preparedRequestSha256', 'subjectOrderSha256',
            'slotGrantSha256', 'assessment', 'installationReceipt', 'installHelper', 'installationStarted',
            'nativeUiReady', 'ownerAuthorization', 'noLaunchAuthority', 'verifiedBy', 'reason'}
    if (set(review) != keys or review['schemaVersion'] != 1 or review['kind'] != 'diagnostic-preexecution-recovery-reserve'
            or review['noLaunchAuthority'] is not True or not d.api().SAFE_ID.fullmatch(review['id'])
            or not review['verifiedBy'] or not review['reason']):
        raise ValueError('Explicit cleanup-only recovery reservation required')
    d.api().owner_evidence(review, Path(path), require_deadline=False)
    with p.connect() as con:
        prior = _row(con, review['id'])
        if prior:
            saved = json.loads(prior['request'])
            if saved['reviewPin'] != review_pin or saved['review'] != review:
                raise ValueError('Recovery identity is immutable')
            return {'id': prior['id'], 'status': prior['status'], 'duplicate': True, 'newCleanupGranted': False, 'launchGranted': False}
        request, snapshot = _legacy(p, con, review, 'preparing')
        if (review['id'] in {request['id'], request['orderId'], request['slotId'],request['cycleId']}
                or con.execute('SELECT 1 FROM events WHERE id=?', (review['id'],)).fetchone()):
            raise ValueError('Recovery audit identity cannot overlap any existing subject/lease history')
    if review['ownerAuthorization'] != request['ownerAuthorization']:
        raise ValueError('Recovery must retain original owned-installation provenance; no launch extension')
    _source(request)  # Verify observer and old producer BEFORE activating code.
    runner = order_platform.activate(request['executor'])
    with runner.native.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE'); _schema(con)
        if _row(con, review['id']) or con.execute('SELECT id FROM diagnostic_recoveries WHERE diagnostic_id=?', (review['diagnosticId'],)).fetchone():
            raise ValueError('Recovery already reserved; inspect existing identity')
        request, current = _legacy(p, con, review, 'preparing')
        if current != snapshot:
            raise ValueError('Legacy rows changed before cleanup reservation')
        d._barriers(p, request, con, own_slot=True)
        source = _source(request); assessment,index_pin = _assessment(review, request,current['managedIni'])
        profile_inventory=_current(request, assessment, False)
        order = json.loads(snapshot['job']['request']); p.verify_inputs(order)
        installation_receipt=d.read_pin(review['installationReceipt'])
        d._installation_receipt(request, order, installation_receipt)
        record = {'review': review, 'reviewPin': review_pin, 'legacy': snapshot, 'source': source,
                  'assessment': assessment, 'implementationPins': d.source_pins(),'profiles':profile_inventory,
                  'installationReceiptData':installation_receipt,'installationEvidence':installation_receipt['evidence'],
                  'hold': dict(con.execute('SELECT * FROM pipeline_holds WHERE id=?', ('qualification-' + request['qualificationId'],)).fetchone()),
                  'preimageIndex': index_pin}
        _source(request)
        if _current(request,assessment,False)!=profile_inventory:raise ValueError('Profile inventory changed before reservation')
        if d.read_pin(review_pin) != review:
            raise ValueError('Cleanup review changed before reservation')
        d.api().owner_evidence(review, Path(path), require_deadline=False)
        d.pin(index_pin)
        record['nativeIdleObservation']=d._native_closed(p, request, runner, con)
        if d.read_pin(current['ackPin'])!=current['ackDocument']:raise ValueError('File-ack changed before cleanup reservation')
        if _current(request,assessment,False)!=profile_inventory:raise ValueError('Installed/profile state changed at cleanup boundary')
        for value in _reserve_proofs(record):d.pin(value)
        con.execute("INSERT INTO diagnostic_recoveries VALUES(?,?,?,'restoring',NULL)",
                    (review['id'], review['diagnosticId'], json.dumps(record, sort_keys=True)))
        con.execute("UPDATE diagnostic_admissions SET status='restoring' WHERE id=?", (review['diagnosticId'],))
        p.event(con, review['id'], 'diagnostic_recovery_reserved', json.dumps(record, sort_keys=True))
    return {'id': review['id'], 'status': 'restoring', 'launchGranted': False, 'slotRetained': True, 'subjectChanged': False}


def complete(p, path):
    review, review_pin = d.document(path)
    if (set(review) != {'schemaVersion', 'kind', 'id', 'archive', 'managedIniAfter','restorationReceipt', 'verifiedBy', 'reason'}
            or review['schemaVersion'] != 1 or review['kind'] != 'diagnostic-preexecution-recovery-complete'
            or not review['verifiedBy'] or not review['reason']):
        raise ValueError('Explicit completed restoration review required')
    with p.connect() as con:
        row = _row(con, review['id'])
    if not row:
        raise ValueError('No exact cleanup reservation')
    if row['status'] == 'completed':
        old = json.loads(row['completion'])
        if old['reviewPin'] != review_pin or old['review'] != review or not settled(p, row['id']):
            raise ValueError('Completed recovery identity/proof changed')
        return {'id': row['id'], 'status': 'completed', 'duplicate': True, 'newCleanupGranted': False, 'launchGranted': False}
    record = json.loads(row['request']); reserve_review = record['review']; request = json.loads(record['legacy']['diagnostic']['request'])
    _source(request)
    runner = order_platform.activate(request['executor'])
    with runner.native.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        if _row(con, row['id']) != row or row['status'] != 'restoring' or d.source_pins() != record['implementationPins']:
            raise ValueError('Cleanup source/ownership changed')
        _, current = _legacy(p, con, reserve_review, 'restoring')
        expected = copy.deepcopy(record['legacy']); expected['diagnostic']['status'] = 'restoring'
        if current != expected:
            raise ValueError('Original queued subject/slot/legacy state changed')
        d._barriers(p, request, con, own_slot=True)
        if dict(con.execute('SELECT * FROM pipeline_holds WHERE id=?', ('qualification-' + request['qualificationId'],)).fetchone()) != record['hold']:
            raise ValueError('Retained qualification hold changed')
        d.pin(record['preimageIndex'])
        _source(request); _assessment(reserve_review, request,current['managedIni'])
        assessment = record['assessment']; profile_inventory=_current(request, assessment, True); _archive(review, assessment, row['id'], p)
        expected_profiles=copy.deepcopy(record['profiles'])
        modlist_path=Path(request['profileBaseline']['profile'])/'modlist.txt'
        modlist_before=next(x['sha256'] for x in assessment['freshPreimages'] if Path(x['path'])==modlist_path)
        for item in expected_profiles:
            if Path(item['path'])==modlist_path:item['sha256']=modlist_before
        if profile_inventory!=expected_profiles:raise ValueError('Other profile inventory changed during owned restoration')
        managed = next(x for x in assessment['freshPreimages'] if Path(x['path']) == Path(assessment['managedIniPath']))
        after_path=d._absolute(review['managedIniAfter']['path']);evidence_root=p.local/'diagnostic-recoveries'/row['id']
        if evidence_root not in after_path.parents or after_path==Path(managed['path']):
            raise ValueError('ManagedINI proof must be an immutable scoped byte copy, never liveINI')
        after_raw = d.read_hashed(review['managedIniAfter'])
        if hashlib.sha256(after_raw).hexdigest() != d.file_pin(managed['path'])['sha256']:
            raise ValueError('ManagedINI completion copy differs from current actual bytes')
        changed = gui_delta(d.read_hashed({'path': managed['backup'], 'sha256': managed['sha256']}), after_raw)
        result = {'review': review, 'reviewPin': review_pin, 'actualStartsThisPreparation': 0,
                  'globalActualStarts': None, 'queuedSubjectUnchanged': True, 'managedIniChangedKeys': changed,
                  'legacy': current,'profilesAfter':profile_inventory, 'completedAt': time.time()}
        _current(request, assessment, True); _archive(review, assessment, row['id'], p)
        d.pin({'path': managed['path'], 'sha256': review['managedIniAfter']['sha256']})
        result['nativeIdleObservation']=d._native_closed(p, request, runner, con)
        result['restorationProvenance']=_restoration(review,record,p,runner,result['nativeIdleObservation'])
        if _current(request,assessment,True)!=profile_inventory:raise ValueError('Profile inventory changed before completion')
        d.pin(record['preimageIndex'])
        d.pin({'path':managed['path'],'sha256':review['managedIniAfter']['sha256']})
        if d.read_pin(current['ackPin'])!=current['ackDocument']:raise ValueError('File-ack changed before recovery completion')
        if d.read_pin(review_pin) != review or d.read_pin(record['reviewPin']) != reserve_review:
            raise ValueError('Recovery proof changed before completion')
        d.api().owner_evidence(reserve_review, Path(record['reviewPin']['path']), require_deadline=False)
        for value in [*_reserve_proofs(record),review_pin,review['managedIniAfter'],
                      *_archive(review,assessment,row['id'],p),*result['restorationProvenance']['proofPins']]:d.pin(value)
        d.pin({'path':managed['path'],'sha256':review['managedIniAfter']['sha256']})
        con.execute("UPDATE diagnostic_admissions SET status='recovered-unstarted' WHERE id=?", (reserve_review['diagnosticId'],))
        con.execute("UPDATE cycle_slots SET status='released' WHERE id=?", (request['slotId'],))
        con.execute("UPDATE diagnostic_recoveries SET status='completed',completion=? WHERE id=?", (json.dumps(result, sort_keys=True), row['id']))
        p.event(con, row['id'], 'diagnostic_recovery_completed', json.dumps(result, sort_keys=True))
        p.event(con, request['slotId'], 'diagnostic_recovery_slot_released', json.dumps({'recoveryId': row['id'], 'completionReview': review_pin}, sort_keys=True))
    return {'id': row['id'], 'status': 'completed', 'actualStartsThisPreparation': 0, 'globalActualStarts': None,
            'queuedSubjectUnchanged': True, 'launchGranted': False, 'holdRetained': True}


def settled(p, identity):
    """Historical supported completion; never requalify old live provider files."""
    try:
        with p.connect() as con:
            row = _row(con, identity)
            if not row or row['status'] != 'completed' or not row['completion']:
                return False
            record = json.loads(row['request']); result = json.loads(row['completion']); request = json.loads(record['legacy']['diagnostic']['request'])
            diag = dict(con.execute('SELECT * FROM diagnostic_admissions WHERE id=?', (row['diagnostic_id'],)).fetchone())
            expected = copy.deepcopy(record['legacy']['diagnostic']); expected['status'] = 'recovered-unstarted'
            slot = dict(con.execute('SELECT * FROM cycle_slots WHERE id=?', (request['slotId'],)).fetchone())
            old_slot = copy.deepcopy(record['legacy']['slot']); old_slot['status'] = 'released'
            job = con.execute('SELECT * FROM jobs WHERE id=?', (request['orderId'],)).fetchone()
            old_job = record['legacy']['job']
            if (diag != expected or slot != old_slot or not job or job['request'] != old_job['request']
                    or type(result['actualStartsThisPreparation']) is not int or result['actualStartsThisPreparation'] != 0 or result['globalActualStarts'] is not None
                    or result['queuedSubjectUnchanged'] is not True):
                return False
            events = _events(con, identity)
            if ([x['status'] for x in events] != ['diagnostic_recovery_reserved', 'diagnostic_recovery_completed']
                    or json.loads(events[0]['note']) != record or json.loads(events[1]['note']) != result):
                return False
            if [x for x in _events(con,request['orderId']) if x['seq']<events[-1]['seq']] != record['legacy']['jobEvents']:
                return False
            completed_legacy=copy.deepcopy(record['legacy']);completed_legacy['diagnostic']['status']='restoring'
            if result['legacy']!=completed_legacy:return False
            slot_events = _events(con, request['slotId'])
            if (slot_events[:-2] != record['legacy']['slotEvents']
                    or slot_events[-2]['status']!='slot_ever_granted'
                    or slot_events[-2]['note']!='SQLite witness: reserved -> released; grant/ack state observed'
                    or slot_events[-1]['status'] != 'diagnostic_recovery_slot_released'
                    or json.loads(slot_events[-1]['note']) != {'recoveryId': identity, 'completionReview': result['reviewPin']}):
                return False
        if d.read_pin(record['reviewPin']) != record['review'] or d.read_pin(result['reviewPin']) != result['review']:
            return False
        if d.read_pin(record['review']['installationReceipt'])!=record['installationReceiptData']:return False
        for value in record['installationEvidence']:d.pin(value)
        if [x['pin'] for x in record['source']] != request['dashboardPins']:
            return False
        for value in record['source']:
            if hashlib.sha256(base64.b64decode(value['base64'], validate=True)).hexdigest() != value['pin']['sha256']:
                return False
        _archive(result['review'], record['assessment'], identity, p)
        if _restoration(result['review'],record,p,historical=result['restorationProvenance'])!=result['restorationProvenance']:return False
        managed = next(x for x in record['assessment']['freshPreimages'] if Path(x['path']) == Path(record['assessment']['managedIniPath']))
        if gui_delta(d.read_hashed({'path': managed['backup'], 'sha256': managed['sha256']}),
                     d.read_hashed(result['review']['managedIniAfter'])) != [tuple(x) for x in result['managedIniChangedKeys']]:
            return False
        d.pin(record['preimageIndex'])
        return True
    except (ValueError, KeyError, TypeError, OSError):
        return False


def show(p, identity):
    with p.connect() as con:
        row = _row(con, identity)
    if not row:
        raise ValueError('Unknown recovery')
    return {'id': identity, 'status': row['status'], 'historicallyCompleted': settled(p, identity),
            'launchGranted': False, 'newCleanupGranted': False}

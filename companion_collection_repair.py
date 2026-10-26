"""Add collection evidence to one ended failed companion attempt, never replay it."""
import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import uuid

from companion_evidence import _identity, _json, _path, collect
from companion_pretest_resume import archive_record

FLAGS = {'endedReviewed', 'restorationReviewed', 'archiveReviewed', 'uncertaintyRetained', 'retainHold'}
FIELDS = {'schemaVersion', 'kind', 'attemptId', 'packet', 'platformPlan', 'state', 'result', 'childExit',
          'companionReport', 'profileArchive', 'implementationPins', 'verifiedBy', 'reason'} | FLAGS


def api():
    import polygon
    return polygon


def require(value, message):
    if not value: raise ValueError('Companion collection repair: ' + message)


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def pin(path):
    path = _path(path)
    data = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def checked(value, expected=None):
    require(isinstance(value, dict) and set(value) <= {'path', 'sha256', 'bytes'}, 'path/hash pin required')
    actual = pin(value['path'])
    require(value.get('sha256') == actual['sha256'] and
            ('bytes' not in value or value['bytes'] == actual['bytes']) and
            (expected is None or Path(actual['path']) == _path(expected)), 'evidence path/hash changed')
    return Path(actual['path'])


def read(path):
    return _json(_path(path).read_bytes())


def implementations():
    return [{'path': str(path.resolve()), 'sha256': pin(path)['sha256']} for path in sorted(api().HERE.glob('*.py'))]


@contextmanager
def native_scope(p, order, attempt):
    """One selected frozen observer/mutex; no foreign game or VR may be present."""
    from order_platform import activate
    platform = p.verify_platform(order, attempt_id=attempt)
    runner = activate(platform['executor'])
    with runner.native.SessionMutex():
        rows = runner.native.processes()
        require(isinstance(rows, list) and rows and all(isinstance(row, dict) and
                type(row.get('pid')) is int and isinstance(row.get('name'), str) for row in rows),
                'complete native process inventory required')
        require(not any(row['name'].lower() in runner.GAME_NAMES | runner.VR_NAMES for row in rows),
                'current foreign game/VR blocks collection repair')
        yield


def _archive(run, history=False):
    _path(run / 'test-profile')
    if history:
        state = read(run / 'state.json'); archive = run / 'test-profile'
        require(archive.is_dir() and _path(state['profileArchive']) == archive and isinstance(state['testProfile'], str),
                'recorded archive identity differs')
        record = {'schemaVersion': 1, 'runDirectory': str(run), 'profileArchive': str(archive),
                  'removedProfile': state['testProfile'], 'files': []}
    else:
        record = archive_record(run)
    directories = []
    for path in sorted((run / 'test-profile').rglob('*')):
        _path(path)
        require(path.is_file() or path.is_dir(), 'unsupported archive object')
        if path.is_dir(): directories.append(str(path.resolve()))
        elif history: record['files'].append(pin(path))
    require(record['files'], 'nonempty profile archive required')
    return record, directories


def archive_evidence(raw):
    archive = _path(Path(raw['runDirectory']) / 'test-profile')
    count = sum(_path(item['path']).is_relative_to(archive) for item in raw['files'])
    return {'originalFilePinCount': count,
            'inventoryBasis': 'retained-original-file-pins' if count else 'reviewed-current-ended-owned-profile',
            'historicalFileContinuityEstablished': bool(count)}


def _checked(p, row, raw, review, con):
    attempt = row['id']; order = p.retry_order(row); folder = _path(p.local / 'retry-attempts' / attempt)
    live = con.execute('SELECT * FROM retry_attempts WHERE id=?', (attempt,)).fetchone()
    require(live and all(live[key] == row[key] for key in ('request', 'status', 'packet')) and
            row['status'] == 'recorded' and json.loads(row['request']).get('kind') == 'companion-pre-session',
            'exact recorded companion attempt required')
    require(set(review) == FIELDS and review['schemaVersion'] == 1 and
            review['kind'] == 'companion-ended-collection-repair' and review['attemptId'] == attempt and
            all(review[flag] is True for flag in FLAGS) and
            all(isinstance(review[key], str) and review[key].strip() for key in ('verifiedBy', 'reason')),
            'explicit ended/restored/uncertain review required')
    require(con.execute('SELECT id FROM pipeline_holds WHERE id=?', (attempt,)).fetchone(), 'original fault hold must remain')
    for table, states, extra in (('retry_attempts', "'running','collecting'", ' AND id!=?'),
                                 ('jobs', "'running','session_waiting'", ''),
                                 ('qualifications', "'prepared','running'", ''),
                                 ('game_sessions', "'preparing','running','finalizing'", '')):
        require(not con.execute('SELECT id FROM ' + table + ' WHERE status IN (' + states + ')' + extra,
                                (attempt,) if extra else ()).fetchone(), 'another unfinished owner blocks repair')
    raw_path = checked(review['packet'], row['packet'])
    _, actual_raw = p.verify_packet({'id': order['id'], 'request': json.dumps(order), 'packet': str(raw_path)})
    require(actual_raw == raw and raw.get('attemptId') == attempt and raw.get('orderId') == order['id'] and
            raw.get('executionOutcome') == 'failed' and raw.get('restored') is True,
            'original failed/restored raw packet required')
    require(not any(Path(item['path']).name == 'profile-archive.json' for item in raw['files']),
            'original archive inventory was already collected')
    for item in raw['files']: checked(item)
    platform = p.verify_platform(order, attempt_id=attempt)
    require(read(checked(review['platformPlan'], folder / 'platform-plan.json')) == platform,
            'original frozen platform differs')
    run = _path(raw['runDirectory'])
    require(run == _path(Path(platform['configuration']['runtime']) / 'runs' / run.name), 'run outside original runtime')
    state = read(checked(review['state'], run / 'state.json'))
    result = read(checked(review['result'], run / 'result.json'))
    native = state.get('order', {})
    require(native.get('id') == order['id'] and native.get('attemptId') == attempt and native.get('subjectOrderId') == order['id'] and
            state.get('id') == result.get('id') == run.name and state.get('configuration') == platform['configuration'] and
            state.get('scenarioHash') == pin(folder / 'scenario.json')['sha256'] and p.native_game_starts(state) == 1,
            'exact attributed single-start native run required')
    for value in (state, result):
        require(value.get('restored') is True and not value.get('restoreErrors') and value.get('result') == raw['executionOutcome'] and
                value.get('reason') == raw['reason'] and value.get('collectionComplete') is True and not value.get('collectionErrors'),
                'native failure/restoration/collection evidence differs')
    require(state.get('done') is True and raw.get('launchAccounting') == {
                'subjectActualLaunchesBefore': 0, 'thisAttemptActualGameStarts': 1,
                'subjectActualLaunchesAfter': 1, 'maximumSubjectActualLaunches': 1},
            'ended consumed launch required')
    child = read(checked(review['childExit'], folder / 'child-exit.json'))
    require(type(child.get('returncode')) is int and not child.get('timeout'), 'actual ended worker receipt required')
    require(review['implementationPins'] == implementations(), 'reviewed current implementation closure differs')
    for item in review['implementationPins']: checked(item)
    current = collect(p, order, run, attempt_id=attempt)
    require(current == raw.get('subjectCompanion') and current['reportPin'] == pin(checked(review['companionReport'])),
            'original companion evidence differs')
    require(current['uncertain'] is True and current['completed'] is False, 'uncertain outcome must remain unqualified')
    snapshots = state.get('snapshots')
    require(isinstance(snapshots, list) and snapshots and len({item['path'] for item in snapshots}) == len(snapshots),
            'complete restoration snapshots required')
    for item in snapshots:
        target = _path(item['path'])
        require(type(item.get('exists')) is bool and
                ((target.is_file() and pin(target)['sha256'] == item.get('sha256')) if item['exists'] else not target.exists()),
                'restored target existence/hash differs')
    archive, directories = _archive(run)
    require(review['profileArchive'] == archive, 'complete restored profile archive differs')
    retained_archive = [item for item in raw['files'] if _path(item['path']).is_relative_to(run / 'test-profile')]
    if retained_archive:
        expected = {str(_path(item['path'])): (item['sha256'], item['bytes']) for item in retained_archive}
        actual = {item['path']: (item['sha256'], item['bytes']) for item in archive['files']}
        require(expected == actual, 'archive differs from retained original file inventory')
    runtimes = {Path(platform['configuration']['runtime'])}
    host = p.host()
    if host.get('runnerConfig'): runtimes.add(Path(read(host['runnerConfig'])['runtime']))
    for runtime in runtimes:
        require(all(read(path).get('done') is True for path in (runtime / 'runs').glob('*/state.json')),
                'unfinished native session blocks repair')
    identities = [state.get('runner'), state.get('game')] + [item.get('identity') for item in state.get('owned', [])]
    require(all(_identity(identity) for identity in identities) and
            any(item.get('role') == 'game' and item.get('identity') == state['game'] for item in state.get('owned', [])),
            'exact worker/owned game identities required')
    identities = list({encoded(identity): identity for identity in identities}.values())
    require(p.verify_companion_processes_dead(order, identities, attempt) is True, 'independent process death proof unavailable')
    return order, folder, archive, directories


ATTESTATIONS = {'holdPresent', 'globalIdle', 'ownedProcessesDead', 'restoredTargetsVerified',
                'temporaryProfileAbsent', 'platformPinsVerified', 'companionRowsVerified'}


def _proof(row, raw, review, review_pin, order, folder):
    platform = read(checked(review['platformPlan']))
    executor = _path(platform['executor'])
    return {'schemaVersion': 1, 'kind': 'companion-ended-verification-proof', 'attemptId': row['id'],
        'ticketSha256': hashlib.sha256(row['request'].encode('utf-8')).hexdigest(),
        'order': order, 'subjectOrderSha256': hashlib.sha256(encoded(order)).hexdigest(),
        'originalPacket': review['packet'], 'review': review_pin,
        'closedEvidence': {key: review[key] for key in ('platformPlan', 'state', 'result', 'childExit', 'companionReport')},
        'scenario': pin(folder / 'scenario.json'), 'companion': copy.deepcopy(raw['subjectCompanion']),
        'nativeGameStarts': 1, 'attestations': {flag: True for flag in ATTESTATIONS},
        'nativeCorePins': [item for item in platform['pins'] if _path(item['path']).is_relative_to(executor)]}


def _history(p, row, raw, review, proof, pointer, folder):
    """Only closed evidence and the retained archive; no current owner/OS gates."""
    attempt = row['id']; order = p.retry_order(row)
    require(set(review) == FIELDS and review['schemaVersion'] == 1 and
            review['kind'] == 'companion-ended-collection-repair' and review['attemptId'] == attempt and
            all(review[flag] is True for flag in FLAGS), 'recorded review differs')
    require(proof.get('schemaVersion') == 1 and proof.get('kind') == 'companion-ended-verification-proof' and
            proof.get('attemptId') == attempt and proof.get('originalPacket') == review['packet'] and
            proof.get('review') == pointer['review'] and proof.get('order') == order and
            proof.get('ticketSha256') == hashlib.sha256(row['request'].encode('utf-8')).hexdigest() and
            json.loads(row['request']).get('kind') == 'companion-pre-session' and
            proof.get('subjectOrderSha256') == hashlib.sha256(encoded(order)).hexdigest() == raw.get('subjectOrderSha256') and
            proof.get('attestations') == {flag: True for flag in ATTESTATIONS} and proof.get('nativeGameStarts') == 1,
            'recorded verification identity/attestation differs')
    raw_path = checked(review['packet'], row['packet'])
    _, actual = p.verify_packet({'id': order['id'], 'request': json.dumps(order), 'packet': str(raw_path)})
    require(actual == raw and raw.get('attemptId') == attempt and raw.get('orderId') == order['id'] and
            raw.get('executionOutcome') == 'failed' and raw.get('restored') is True, 'original raw packet differs')
    for item in raw['files']: checked(item)
    expected = {key: review[key] for key in ('platformPlan', 'state', 'result', 'childExit', 'companionReport')}
    require(proof.get('closedEvidence') == expected, 'closed evidence pins differ')
    platform = read(checked(review['platformPlan'], folder / 'platform-plan.json'))
    run = _path(raw['runDirectory'])
    require(run == _path(Path(platform['configuration']['runtime']) / 'runs' / run.name), 'recorded runtime differs')
    state = read(checked(review['state'], run / 'state.json')); result = read(checked(review['result'], run / 'result.json'))
    scenario = checked(proof['scenario'], folder / 'scenario.json')
    native = state.get('order', {})
    games = [item.get('identity') for item in state.get('owned', []) if item.get('role') == 'game']
    require(native.get('id') == order['id'] and native.get('attemptId') == attempt and native.get('subjectOrderId') == order['id'] and
            state.get('id') == result.get('id') == run.name and state.get('configuration') == platform['configuration'] and
            state.get('scenarioHash') == pin(scenario)['sha256'] and state.get('done') is True and
            games and all(_identity(game) for game in games) and len({encoded(game) for game in games}) == 1 and
            state.get('game') in games and type(state.get('ownedGameRestartCount', 0)) is int and state.get('ownedGameRestartCount', 0) == 0,
            'recorded ended native identity/start count differs')
    require(raw.get('launchAccounting') == {'subjectActualLaunchesBefore': 0, 'thisAttemptActualGameStarts': 1,
                'subjectActualLaunchesAfter': 1, 'maximumSubjectActualLaunches': 1}, 'recorded consumed launch differs')
    for value in (state, result):
        require(value.get('restored') is True and not value.get('restoreErrors') and value.get('result') == raw['executionOutcome'] and
                value.get('reason') == raw['reason'] and value.get('collectionComplete') is True and not value.get('collectionErrors'),
                'recorded native outcome/restoration differs')
    child = read(checked(review['childExit'], folder / 'child-exit.json'))
    require(type(child.get('returncode')) is int and not child.get('timeout'), 'recorded worker receipt differs')
    executor = _path(platform['executor'])
    require(proof.get('nativeCorePins') == [item for item in platform['pins'] if _path(item['path']).is_relative_to(executor)],
            'original native core inventory differs')
    for item in proof['nativeCorePins'] + review['implementationPins']: checked(item)
    summary = proof.get('companion'); report = read(checked(review['companionReport']))
    require(summary == raw.get('subjectCompanion') and summary['reportPin'] == pin(review['companionReport']['path']) and
            summary['uncertain'] is True and summary['completed'] is False and report.get('done') is True and
            report.get('runId') == state['id'] and report.get('orderId') == order['id'] and report.get('attemptId') == attempt and
            report.get('subjectStarted') == summary['subjectStarted'] and report.get('uncertain') is True and report.get('completed') is False and
            [{'name': case['id'], 'result': case['status']} for case in report['cases']] == summary['checks'],
            'recorded companion facts differ')
    archive, directories = _archive(run, history=True)
    require(review['profileArchive'] == archive, 'complete restored profile archive differs')
    retained = [item for item in raw['files'] if _path(item['path']).is_relative_to(run / 'test-profile')]
    if retained:
        require({item['path']: (item['sha256'], item['bytes']) for item in archive['files']} ==
                {str(_path(item['path'])): (item['sha256'], item['bytes']) for item in retained},
                'archive differs from retained original file inventory')
    return archive, directories


def _verify(p, row, raw):
    folder = _path(p.local / 'retry-attempts' / row['id']); root = _path(folder / 'collection-repair')
    pointer_path = root / 'pointer.json'; pointer = read(pointer_path)
    require(set(pointer) == {'review', 'supplement'}, 'immutable pointer shape required')
    review_path = checked(pointer['review']); supplement_path = checked(pointer['supplement'], root / 'supplement.json')
    review, supplement = read(review_path), read(supplement_path)
    require(supplement.get('schemaVersion') == 1 and supplement.get('kind') == 'companion-ended-collection-supplement' and
            supplement.get('attemptId') == row['id'] and supplement.get('originalPacket') == review['packet'] and
            supplement.get('review') == pointer['review'], 'supplement identity differs')
    proof_path = checked(supplement['verificationProof'], root / 'verification-proof.json')
    archive, directories = _history(p, row, raw, review, read(proof_path), pointer, folder)
    require(read(root / 'profile-archive.json') == archive and supplement.get('profileArchiveDirectories') == directories,
            'archive membership changed after repair')
    require(supplement.get('archiveEvidence') == archive_evidence(raw), 'archive evidence limits differ')
    require((root / 'review.json').read_bytes() == review_path.read_bytes(), 'review snapshot differs')
    expected = {root / 'pointer.json', supplement_path}
    for item in supplement['files']:
        path = checked(item)
        require(path.is_relative_to(root), 'supplement file outside private repair folder')
        expected.add(path)
    for source in review['implementationPins']:
        checked({'path': str(root / 'implementation' / Path(source['path']).name), 'sha256': source['sha256']})
    entries = [_path(path) for path in root.rglob('*')]
    require({path for path in entries if path.is_dir()} == {root / 'implementation'}, 'repair directory inventory changed')
    actual = {path for path in entries if path.is_file()}
    require(actual == expected, 'repair file inventory changed')
    return pointer, supplement, pin(pointer_path), pin(supplement_path)


def apply(p, row, rawpacket):
    """Return an additive verified view; never write the retained raw packet."""
    root = _path(p.local / 'retry-attempts' / row['id'] / 'collection-repair')
    require(not {'collectionRepair', 'originalPacket'} & set(rawpacket), 'raw packet contains reserved repair tags')
    if not root.exists(): return rawpacket
    pointer, supplement, pointer_pin, supplement_pin = _verify(p, row, rawpacket)
    derived = copy.deepcopy(rawpacket)
    additions = [*supplement['files'], pin(checked(pointer['review'])), pointer_pin, supplement_pin]
    for item in additions:
        same = [old for old in derived['files'] if _path(old['path']) == _path(item['path'])]
        require(not same or same == [item], 'supplement conflicts with original file inventory')
        if not same: derived['files'].append(item)
    derived.update(collectionRepair=supplement_pin, originalPacket=copy.deepcopy(supplement['originalPacket']))
    return derived


def projection(p, order, packet):
    """Historical companion facts with independent closed-evidence verification."""
    row = p.retry_show(packet['attemptId'])
    require(p.retry_order(row) == order, 'projection order differs')
    _, raw = p.verify_packet({'id': order['id'], 'request': json.dumps(order), 'packet': row['packet']})
    derived = apply(p, row, raw)
    require(derived == packet and derived.get('collectionRepair'), 'historical repaired view differs')
    return copy.deepcopy(derived['subjectCompanion'])


def record(p, attempt_id, review_path):
    """Publish only new private collection files. Hold, budget and DB rows stay intact."""
    row = p.retry_show(attempt_id); order = p.retry_order(row)
    _, raw = p.verify_packet({'id': order['id'], 'request': json.dumps(order), 'packet': row['packet']})
    review_path = _path(review_path); review = read(review_path)
    folder = _path(p.local / 'retry-attempts' / attempt_id); root = folder / 'collection-repair'
    review_pin = {key: pin(review_path)[key] for key in ('path', 'sha256')}
    duplicate = root.exists()
    if duplicate:
        require(read(root / 'pointer.json').get('review') == review_pin, 'existing repair review is immutable')
        with native_scope(p, order, attempt_id), p.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            _checked(p, row, raw, review, con)
        derived = apply(p, row, raw)
    else:
        require(not row.get('report'), 'a final report is already registered')
        require(not review_path.is_relative_to(root), 'review must precede private repair folder')
        stage = folder / ('.collection-repair-' + uuid.uuid4().hex)
        created = []
        with native_scope(p, order, attempt_id), p.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            _, _, archive, directories = _checked(p, row, raw, review, con)
            stage.mkdir(); (stage / 'implementation').mkdir()
            try:
                def write(relative, data):
                    path = stage / relative
                    with path.open('xb') as stream: stream.write(data)
                    created.append(path)
                    return {'path': str(root / relative), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
                files = [write(Path('profile-archive.json'), encoded(archive)), write(Path('review.json'), review_path.read_bytes())]
                for item in review['implementationPins']:
                    source = checked(item)
                    files.append(write(Path('implementation') / source.name, source.read_bytes()))
                proof_pin = write(Path('verification-proof.json'), encoded(_proof(row, raw, review, review_pin, order, folder)))
                files.append(proof_pin)
                supplement = {'schemaVersion': 1, 'kind': 'companion-ended-collection-supplement', 'attemptId': attempt_id,
                    'originalPacket': review['packet'], 'review': review_pin, 'files': files,
                    'profileArchiveDirectories': directories, 'archiveEvidence': archive_evidence(raw), 'verificationProof': proof_pin}
                supplement_pin = write(Path('supplement.json'), encoded(supplement))
                write(Path('pointer.json'), encoded({'review': review_pin, 'supplement': supplement_pin}))
                _checked(p, row, raw, review, con)
                require(not root.exists(), 'foreign repair folder appeared')
                stage.rename(root)
            finally:
                if stage.exists():
                    for path in reversed(created):
                        try:
                            _path(path); path.unlink(missing_ok=True)
                        except (OSError, ValueError): pass
                    for path in (stage / 'implementation', stage):
                        try: path.rmdir()
                        except OSError: pass  # Preserve an unexpected foreign file, never erase it.
        derived = apply(p, row, raw)
    return {'attemptId': attempt_id, 'originalPacket': derived['originalPacket'], 'collectionRepair': derived['collectionRepair'],
            'holdRetained': True, 'repaired': True, 'duplicate': duplicate}

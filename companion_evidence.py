"""Verify additive companion evidence without rewriting native executor checks."""
import hashlib
import json
from pathlib import Path, PureWindowsPath
import stat

INTERFACE = 'polygon-file-plan/1'
STATUSES = {'passed', 'failed', 'unavailable', 'not_run'}


def _require(condition, message):
    if not condition:
        raise ValueError('Subject companion: ' + message)


def _path(value):
    path = Path(value)
    _require(path.is_absolute(), 'absolute evidence path required')
    for item in (path, *path.parents):
        try: info = item.lstat()
        except FileNotFoundError: continue
        _require(not item.is_symlink() and not getattr(info, 'st_file_attributes', 0) &
                 getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400), 'linked evidence path refused')
    return path.resolve()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def _json(data):
    def invalid(_): raise ValueError('Subject companion: nonfinite JSON')
    return json.loads(data.decode('utf-8-sig'), object_pairs_hook=_pairs, parse_constant=invalid)


class _Files:
    def __init__(self, roots):
        self.roots, self.pins = roots, {}

    def read(self, value, *, confined=True, maximum=32 * 1024 * 1024):
        expected = value if isinstance(value, dict) else None
        path = _path(expected['path'] if expected else value)
        if confined:
            _require(any(path.is_relative_to(root) for root in self.roots), 'evidence escapes owned folders')
        _require(path.is_file() and path.stat().st_size <= maximum, 'missing or oversized evidence')
        data = path.read_bytes()
        pin = {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        if expected:
            _require(set(expected) <= {'path', 'sha256', 'bytes', 'format'} and
                     expected.get('sha256') == pin['sha256'] and
                     ('bytes' not in expected or expected['bytes'] == pin['bytes']), 'artifact hash/size changed')
        previous = self.pins.setdefault(str(path), pin)
        _require(previous == pin, 'artifact changed during collection')
        return data, pin

    def json(self, value, **kwargs):
        data, pin = self.read(value, **kwargs)
        return _json(data), pin

    def lines(self, value, **kwargs):
        data, pin = self.read(value, **kwargs)
        _require(not data or data.endswith(b'\n'), 'incomplete evidence log')
        return [_json(line) for line in data.splitlines()], pin


def _identity(value):
    return (isinstance(value, dict) and set(value) == {'pid', 'birth', 'path'} and
            type(value['pid']) is int and value['pid'] > 0 and type(value['birth']) is int and value['birth'] > 0 and
            isinstance(value['path'], str) and '\0' not in value['path'] and
            (Path(value['path']).is_absolute() or PureWindowsPath(value['path']).is_absolute()))


def _processes(p, order, state, report, dispatch, files, root):
    frozen = p.attempt_plan(order)
    source = frozen['companionSelection']['transport']
    client = dispatch['client']
    _require(client.get('source') == report.get('transport') == source and _identity(client.get('identity')),
             'retained client source/identity differs')
    files.read(source, confined=False)
    argv = client.get('argv')
    _require(isinstance(argv, list) and len(argv) >= 2 and len(argv) % 2 == 0 and
             all(isinstance(value, str) for value in argv) and _path(argv[0]) == _path(client['identity']['path']) and
             _path(argv[1]) == _path(source['path']), 'retained client argv/source differs')
    flags = dict(zip(argv[2::2], argv[3::2]))
    cfg, spec = frozen['configuration'], order['subjectPlan']
    required = {'--executor': frozen['executor'], '--plan': spec['plan']['path'],
        '--plan-sha256': spec['plan']['sha256'], '--sequencer': spec['sequencer']['path'],
        '--sequencer-sha256': spec['sequencer']['sha256'], '--runtime': cfg['runtime'],
        '--channel-config': cfg['interactive_session']['channelConfig'], '--order-id': order['id'],
        '--attempt-id': order['id'], '--output': str(root / 'report.json')}
    extra = {'--worker-identity', '--game-identity', '--maximum-seconds', '--executor-manifest', '--executor-manifest-sha256'}
    _require(len(flags) == (len(argv) - 2) // 2 and set(flags) == set(required) | extra and
             all(flags[key] == value for key, value in required.items()) and
             _json(flags['--worker-identity'].encode()) == state['runner'] and
             _json(flags['--game-identity'].encode()) == state['game'] and
             float(flags['--maximum-seconds']) == spec['maximumSeconds'], 'retained client target arguments differ')
    _, manifest = files.read({'path': flags['--executor-manifest'], 'sha256': flags['--executor-manifest-sha256']})
    _require(Path(manifest['path']) == root / 'executor-manifest.json' and
             report.get('executorManifest') == {'path': manifest['path'], 'sha256': manifest['sha256']}, 'executor manifest differs')
    observed = client['exit']
    _require(observed.get('identityVerified') is True and observed.get('identity') == client['identity'], 'client exit identity differs')
    code = client.get('returncode')
    exit_ok = (observed.get('schemaVersion') == 1 and observed.get('status') == 'exited' and
        observed.get('exitCodeAvailable') is True and type(code) is int and type(observed.get('exitCode')) is int and
        0 <= observed['exitCode'] <= 0xFFFFFFFF and observed['exitCode'] == (code & 0xFFFFFFFF) and
        observed.get('exitCodeHex') == f'0x{observed["exitCode"]:08X}')
    _require(type(client.get('timedOut')) is bool and type(client.get('terminatedOwnedClient')) is bool, 'client lifetime flags required')
    inner = report['sequencerProcess']
    _require(_identity(inner.get('identity')) and inner.get('pid') == inner['identity']['pid'] and
             inner['identity']['pid'] != client['identity']['pid'] and type(inner.get('stoppedByClient')) is bool,
             'sequencer process identity differs')
    verifier = getattr(p, 'verify_companion_processes_dead', None)
    _require(callable(verifier) and verifier(order, [client['identity'], inner['identity']]) is True,
             'independent complete process-death verification required')
    return (exit_ok and code == dispatch.get('returncode') == 0 and not client['timedOut'] and
            not client['terminatedOwnedClient'] and type(inner.get('returnCode')) is int and
            inner['returnCode'] == 0 and not inner['stoppedByClient'])


def collect(p, order, run):
    """Return verified additive checks/pins, or None for an ordinary static plan.

    Invalid/missing evidence raises; callers must record a collection fault and
    retain the ownership hold. A verified but uncertain/incomplete report remains
    a tooling fault: callers must check both returned flags before finalization.
    """
    try:
        return _collect(p, order, run)
    except (KeyError, TypeError, AttributeError, IndexError) as error:
        raise ValueError('Subject companion: malformed evidence shape') from error


def _collect(p, order, run):
    plan = order.get('subjectPlan', {})
    if plan.get('interface') != INTERFACE:
        return None
    run = _path(run)
    root = _path(p.evidence_dir(order['id']) / 'subject-companion')
    files = _Files((root, _path(run / 'interactive-results')))
    state, _ = files.json(run / 'state.json', confined=False)
    steps, _ = files.lines(run / 'steps.jsonl', confined=False, maximum=128 * 1024 * 1024)
    report, report_pin = files.json(root / 'report.json')
    dispatch, _ = files.json(root / 'dispatch.json')
    _require(report.get('schemaVersion') == 1 and report.get('kind') == 'subject-companion-report' and
             report.get('done') is True and type(report.get('completed')) is bool and
             type(report.get('uncertain')) is bool and type(report.get('subjectStarted')) is bool and
             report.get('status') in {'completed', 'stopped'}, 'final report shape required')
    _require(state.get('order', {}).get('id') == order['id'] and report.get('orderId') == order['id'] and
             report.get('attemptId') == order['id'] and report.get('runId') == state.get('id') and
             isinstance(state.get('id'), str) and bool(state['id']), 'run/order/attempt differs')
    metadata = state.get('interactiveSession', {})
    binding = {'provider': 'skyrim-autotest', 'conversationId': state['id'], 'agentId': 'owned-game-executor'}
    _require(report.get('sessionId') == metadata.get('sessionId') == 'game-' + state['id'] and
             report.get('binding') == metadata.get('binding') == binding, 'interactive owner differs')
    for key, native_key in (('worker', 'runner'), ('game', 'game')):
        _require(_identity(state.get(native_key)) and report.get(key) == state[native_key], 'native identity differs')
    _require(dispatch.get('schemaVersion') == 1 and dispatch.get('orderId') == order['id'] and
             dispatch.get('worker') == state['runner'], 'dispatch identity differs')
    dispatch_ok = type(dispatch.get('returncode')) is int and dispatch['returncode'] == 0 and 'error' not in dispatch
    processes_ok = _processes(p, order, state, report, dispatch, files, root)
    dispatch_ok = dispatch_ok and processes_ok
    for key in ('plan', 'sequencer'):
        _require(report.get(key) == plan.get(key), key + ' pin differs')
        _, pin = files.read(plan[key], confined=False)
        _require(any(item.get('role') == 'fixture' and _path(item['path']) == Path(pin['path']) and
                     item.get('sha256') == pin['sha256'] for item in order.get('inputs', [])), key + ' not pinned by order')
    declared, _ = files.json(plan['plan'], confined=False)
    names = plan['checks']
    _require(isinstance(names, list) and names and len(set(names)) == len(names) and
             report.get('caseIds') == names and isinstance(report.get('cases'), list) and
             [case.get('id') for case in report['cases']] == names, 'exact unique case inventory required')
    inventories = []
    if 'checks' in declared:
        _require(isinstance(declared['checks'], list) and all(check.get('role') == 'subject' for check in declared['checks']),
                 'pinned plan checks require subject roles')
        inventories.append([check.get('name') for check in declared['checks']])
    if 'cases' in declared:
        inventories.append([case.get('id') for case in declared['cases']])
    _require(inventories and all(inventory == names for inventory in inventories), 'pinned plan case inventory differs')
    _require(order.get('testing', {}).get('start') == {'kind': 'check', 'name': names[0]} and
             order['testing'].get('checks') == [{'name': name, 'role': 'subject'} for name in names], 'testing declaration differs')
    events, _ = files.lines(report['events'], maximum=128 * 1024 * 1024)
    for pin in report.get('evidence', []):
        files.read(pin)
    origins = [(index, row.get('record')) for index, row in enumerate(events) if row.get('kind') == 'origin']
    _require(all(isinstance(row, dict) for _, row in origins), 'invalid origin event')
    for index, record in origins:
        retained, _ = files.json(events[index]['evidence'])
        _require(retained == record, 'retained origin event differs')
        if record.get('kind') == 'assertion':
            _require(isinstance(record.get('check'), str) and record['check'] and
                     record.get('outcome') in {'passed', 'mismatch'} and
                     'actual' in record and 'expected' in record, 'mechanical assertion evidence required')
    actions = report.get('actions')
    _require(isinstance(actions, list), 'action inventory required')
    action_ids, source_ids, completed, delivered = set(), set(), {}, {}
    for number, action in enumerate(actions, 1):
        case = action.get('caseId')
        command, source = action.get('commandId'), action.get('sourceEventId')
        _require(action.get('sequence') == number and (case in names or case is None) and isinstance(source, str) and source and
                 source not in source_ids and action.get('status') in {'intent', 'received', 'delivered', 'completed', 'uncertain'}, 'action order/source/status differs')
        source_ids.add(source)
        if command is not None:
            _require(isinstance(command, str) and command and command not in action_ids, 'duplicate command identity')
            action_ids.add(command)
        request, _ = files.json(action['request'])
        envelope = action['envelope']
        _require(case is not None or (number == len(actions) and envelope.get('operation') == 'finish'), 'only terminal finish may omit case')
        _require(request.get('sessionId') == report['sessionId'] and request.get('expectedBinding') == binding and
                 request.get('sourceId') == metadata.get('sourceId') and request.get('sourceEventId') == source and
                 request.get('kind') == 'text' and _json(request['text'].encode('utf-8')) == envelope and
                 request.get('metadata') == {'subjectOrder': order['id'], 'attemptId': order['id'], 'caseId': case, 'sequence': number},
                 'ingress request differs')
        if action.get('ack'):
            ack, _ = files.json(action['ack'])
            row = ack.get('command', {})
            _require(ack.get('acknowledged') is True and ack.get('duplicate') is False and row.get('id') == command and
                     row.get('sessionId') == report['sessionId'] and row.get('binding') == binding and
                     all(row.get(key) == request[key] for key in ('sourceId', 'sourceEventId', 'kind', 'text', 'metadata')), 'ACK identity differs')
        if action.get('deliveredEvidence'):
            native, _ = files.json(action['deliveredEvidence'])
            _require(native.get('kind') == 'interactive-action-delivered' and native.get('commandId') == command and
                     native.get('request') == envelope and sum(row == native for row in steps) == 1,
                     'actual executor delivery missing or replayed')
            wrappers = [(i, row) for i, row in enumerate(events) if row.get('kind') == 'action-delivered' and row.get('commandId') == command]
            _require(len(wrappers) == 1 and wrappers[0][1].get('caseId') == case and
                     wrappers[0][1].get('sourceEventId') == source and wrappers[0][1].get('executorLog') == native,
                     'delivery event differs')
            delivered[command] = (action, wrappers[0][0])
        if action['status'] == 'completed':
            _require(action.get('ack') and command in delivered, 'completion without receipt and native delivery')
            completion, _ = files.json(action['completion'])
            raw, raw_pin = files.json(action['rawResult'])
            _require(completion.get('type') == 'command.completed' and completion.get('sessionId') == report['sessionId'] and
                     completion.get('data', {}).get('commandId') == command, 'completion identity differs')
            result = completion['data'].get('result')
            if action.get('artifact'):
                _require(set(action['artifact']) == {'path', 'sha256', 'bytes', 'format'} and
                         action['artifact']['format'] == 'json' and type(action['artifact']['bytes']) is int and
                         0 < action['artifact']['bytes'] <= 16 * 1024 * 1024, 'native artifact format/size differs')
                native_artifact, native_pin = files.json(action['artifact'])
                artifact, artifact_pin = files.json(action['artifactCopy'])
                _require(result == {'outcome': 'result-recorded', 'evidence': action['artifact']} and
                         Path(native_pin['path']) == run / 'interactive-results' / (command + '.json') and
                         dict(action['artifact'], commandId=command) in state.get('interactiveArtifacts', []) and
                         native_pin['sha256'] == artifact_pin['sha256'] and native_artifact == artifact == raw, 'large result differs')
            else:
                _require(result == raw, 'raw result differs from completion')
            completed.setdefault(case, []).append(raw_pin['path'])
    finishes = [action for action in actions if action['caseId'] is None]
    _require(not report['completed'] or (len(finishes) == 1 and finishes[0]['status'] == 'completed' and
             files.json(finishes[0]['rawResult'])[0] == {'outcome': 'owner-finished'}), 'completed lifecycle lacks known finish')
    uncertain = any(action['status'] != 'completed' for action in actions)
    _require(not uncertain or report['uncertain'], 'uncertain action masked')
    stopped = False
    checks = []
    for case in report['cases']:
        name, status = case['id'], case.get('status')
        _require(status in STATUSES and (not stopped or status == 'not_run'), 'case status or stop remainder differs')
        case_actions = [action for action in actions if action['caseId'] == name]
        _require(case.get('commandIds') == [action['commandId'] for action in case_actions if action.get('commandId')], 'case command inventory differs')
        evidence = [files.read(pin)[1]['path'] for pin in case.get('evidence', [])]
        results = [row for _, row in origins if row.get('kind') == 'check-result' and row.get('caseId') == name]
        assertions = [row for _, row in origins if row.get('kind') == 'assertion' and row.get('caseId') == name]
        _require(len(results) <= 1, 'duplicate case verdict')
        if status in {'passed', 'failed', 'unavailable'}:
            outcome = {'passed': 'passed', 'failed': 'mismatch', 'unavailable': 'unavailable'}[status]
            transport = (status == 'unavailable' and case.get('verdictSource') == 'transport' and
                         report['status'] == 'stopped' and not report['completed'] and
                         isinstance(case.get('reason'), str) and bool(case['reason']) and not results and
                         not any(row.get('outcome') == 'mismatch' for row in assertions))
            _require(transport or (len(results) == 1 and results[0].get('outcome') == outcome), 'case verdict lacks origin result')
            starts = [index for index, row in origins if row == {'kind': 'check-start', 'caseId': name, 'role': 'subject'}]
            end = next((index for index, row in origins if row in results), len(events))
            _require(len(starts) == 1 and starts[0] < end and
                     all(starts[0] < position < end for action, position in delivered.values() if action['caseId'] == name),
                     'case check-start/result/delivery order differs')
        if status == 'passed':
            _require(completed.get(name) and all(action['status'] == 'completed' for action in case_actions) and
                     any(path in evidence for path in completed[name]) and
                     any(row.get('outcome') == 'passed' for row in assertions) and
                     not any(row.get('outcome') == 'mismatch' for row in assertions), 'passed case lacks actual assertion/readback')
        if status == 'failed':
            _require(any(row.get('outcome') == 'mismatch' for row in assertions), 'failed case lacks mismatch assertion')
        if status == 'not_run':
            _require(not case_actions and (not results or results[0].get('outcome') == 'not_run'), 'not_run case has executed actions')
        stopped |= status in {'failed', 'unavailable'}
        checks.append({'name': name, 'result': status})
    start = report.get('subjectStart')
    first_deliveries = [(action, position) for action, position in delivered.values() if action['caseId'] == names[0]]
    _require(report['subjectStarted'] == bool(first_deliveries), 'factual subject start was masked or invented')
    if report['subjectStarted']:
        _require(isinstance(start, dict) and start.get('caseId') == names[0] and start.get('commandId') in delivered, 'subject boundary lacks delivery')
        action, position = delivered[start['commandId']]
        _require((action, position) == min(first_deliveries, key=lambda row: row[1]) and
                 action['caseId'] == names[0] and start.get('sourceEventId') == action['sourceEventId'] and
                 start.get('deliveredEvidence') == action['deliveredEvidence'] and action['envelope'].get('operation') != 'finish' and
                 sum(row == {'kind': 'check-start', 'caseId': names[0], 'role': 'subject'} for index, row in origins if index < position) == 1,
                 'subject boundary lacks prior matching check-start')
    else:
        _require(start is None and not any(check['result'] in {'passed', 'failed'} for check in checks), 'unstarted report claims tested checks')
    _require(not (report['status'] == 'completed' and (report['uncertain'] or not report['completed'])), 'completed status masks interruption')
    return {'reportPin': report_pin, 'pins': sorted(files.pins.values(), key=lambda pin: pin['path']),
            'checks': checks, 'subjectStarted': report['subjectStarted'],
            'uncertain': report['uncertain'] or not dispatch_ok, 'completed': report['completed'] and dispatch_ok}


def projection(p, order, packet):
    """Reverify collected bytes before using companion cases in test projection."""
    if order.get('subjectPlan', {}).get('interface') != INTERFACE:
        return None
    current = collect(p, order, packet['runDirectory'])
    _require(packet.get('subjectCompanion') == current, 'retained companion summary differs')
    inventory = {_path(pin['path']): pin for pin in packet.get('files', [])}
    for pin in current['pins']:
        _require(inventory.get(Path(pin['path'])) == pin, 'evidence absent from raw packet')
    return current

"""Operator-only, single-start candidate qualification under the shared barrier."""
from __future__ import annotations
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time


def api():
    import polygon
    return polygon


def inventory(root):
    m = api()
    root = Path(root).resolve()
    files = []
    for p in sorted(root.rglob('*')):
        if '__pycache__' in p.parts or p.suffix == '.pyc':
            continue
        if p.is_symlink() or bool(getattr(p.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Candidate inventory cannot contain links')
        if p.is_file():
            files.append({'path': str(p), 'sha256': m.digest(p)})
    if not files or not (root / 'skyrim_autotest/runner.py').is_file():
        raise ValueError('Candidate executor package required')
    return files


class Qualifications:
    def init_qualifications(self):
        with self.connect() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS qualifications (
                id TEXT PRIMARY KEY, request TEXT NOT NULL, status TEXT NOT NULL,
                expires REAL, packet TEXT)''')
            con.execute('''CREATE TABLE IF NOT EXISTS qualification_releases (
                id TEXT PRIMARY KEY, review TEXT NOT NULL)''')

    def qualification_show(self, identity):
        with self.connect() as con:
            row = con.execute('SELECT * FROM qualifications WHERE id=?', (identity,)).fetchone()
        if not row:
            raise ValueError('Unknown qualification')
        return dict(row)

    @staticmethod
    def qualification_busy(con):
        return (con.execute("SELECT id FROM jobs WHERE status='running'").fetchone() or
                con.execute("SELECT id FROM game_sessions WHERE status IN ('preparing','running','finalizing')").fetchone() or
                con.execute("SELECT id FROM retry_attempts WHERE status IN ('running','collecting')").fetchone() or
                con.execute("SELECT id FROM cycle_slots WHERE status IN ('reserved','blocked')").fetchone())

    def qualification_verify(self, row, authority=True):
        m = api()
        plan = json.loads(row['request'])
        if inventory(plan['executor']) != plan['executorPins']:
            raise ValueError('Candidate executor inventory changed')
        if not authority and (self.local / 'qualifications' / plan['id'] / 'collection-repair.json').exists():
            from qualification_collection_repair import verify
            verify(self, row, plan)
            return plan
        for pin in plan['pins']:
            if m.digest(pin['path']) != pin['sha256']:
                raise ValueError('Qualification pin changed: ' + pin['path'])
        if authority:
            m.owner_evidence(plan, Path(plan['requestPath']))
        return plan

    def register_qualification(self, path):
        m = api()
        path = Path(path).resolve()
        request = m.read(path)
        if (request.get('schemaVersion') != 1 or request.get('kind') != 'tool-qualification'
                or not m.SAFE_ID.fullmatch(request.get('id', ''))
                or request.get('maximumActualGameStarts') != 1
                or type(request.get('maximumActualGameStarts')) is not int
                or type(request.get('maximumWallSeconds')) is not int
                or not 900 <= request['maximumWallSeconds'] <= 14400):
            raise ValueError('Operator tool qualification requires one start and an explicit900..14400second wall')
        m.owner_evidence(request, path)
        baseline = request.get('cumulativeActualGameStartsBefore')
        if ('cumulativeActualGameStartsBefore' not in request or
                (baseline is not None and (type(baseline) is not int or baseline < 0))):
            raise ValueError('Reviewed cumulative actual start baseline required')
        for key in ('verifiedBy', 'reason'):
            m.required_string(request, key)
        for key in ('order', 'executor'):
            request[key] = str((path.parent / m.required_string(request, key)).resolve())
        order = m.read(request['order'])
        if (order.get('schemaVersion') != 1 or order.get('mode') != 'automatic'
                or order.get('cycle') or order.get('profileSelection', {}).get('mode', 'active') != 'active'):
            raise ValueError('Dedicated schema1 automatic tool order, active profile only')
        for key in ('id', 'sourceThreadId', 'sourceChat', 'subject', 'purpose', 'profile'):
            m.required_string(order, key)
        if not m.SAFE_ID.fullmatch(order['id']) or not order.get('testing') or not order.get('collect'):
            raise ValueError('Tool order identity/testing/collection required')
        self.validate_testing(order['testing'])
        config_path = (Path(request['order']).parent / order['config']).resolve()
        scenario_path = (Path(request['order']).parent / order['scenario']).resolve()
        config, scenario = m.read(config_path), m.read(scenario_path)
        # This bounded qualification supports generic sequential operations only.
        if scenario.get('kind') or scenario.get('postSteps') or not scenario.get('steps'):
            raise ValueError('Qualification requires generic steps without probes/postSteps')
        for step in scenario['steps']:
            args = step.get('args', {})
            if (step.get('tool') in ('console', 'game') or
                    'restart' in json.dumps(args).lower()):
                raise ValueError('Qualification forbids restarts and arbitrary game/console commands')
        if 'companion' in request:
            from qualification_companion import validate as validate_companion
            request['companion'] = validate_companion(request, config, scenario, path.parent)
        pins = []
        def pin(file):
            file = Path(file).resolve()
            pins.append({'path': str(file), 'sha256': m.digest(file)})
        for file in (path, request['order'], config_path, scenario_path,
                     self.local / 'config.json', request['ownerAuthorization']['path']):
            pin(file)
        if 'companion' in request:
            for name in ('transport', 'plan', 'sequencer'):
                pin(request['companion'][name]['path'])
        accounting = request.get('launchAccounting')
        if not isinstance(accounting, dict):
            raise ValueError('Pinned independently reviewed launch accounting required')
        accounting_path = (path.parent / m.required_string(accounting, 'path')).resolve()
        if m.digest(accounting_path) != accounting.get('sha256'):
            raise ValueError('Launch accounting pin mismatch')
        review = m.read(accounting_path)
        if ('cumulativeActualGameStarts' not in review or
                review['cumulativeActualGameStarts'] != baseline or
                not review.get('verifiedBy') or not review.get('reason')):
            raise ValueError('Accounting review and baseline differ')
        pin(accounting_path)
        request.pop('accountingPins', None)  # derived evidence; never caller-selected packet files
        if baseline is None:
            # An ended uncertain history never becomes zero merely because a
            # newly authorized, independently bounded qualification is starting.
            history = review.get('historyPins')
            if (review.get('accountingStatus') != 'historical_unknown' or
                    not isinstance(history, list) or not 1 <= len(history) <= 32):
                raise ValueError('Unknown cumulative accounting requires reviewed historical packet pins')
            m.required_string(review, 'verifiedBy')
            m.required_string(review, 'reason')
            with self.connect() as con:
                registered = {r['id']: json.loads(r['packet']) for r in
                              con.execute('SELECT id,packet FROM qualifications WHERE packet IS NOT NULL')}
            history_pins, seen = [], set()
            for item in history:
                if not isinstance(item, dict):
                    raise ValueError('Historical accounting packet pin required')
                file = (accounting_path.parent / m.required_string(item, 'path')).resolve()
                expected = item.get('sha256')
                if (not isinstance(expected, str) or not m.SHA.fullmatch(expected) or
                        m.digest(file) != expected or file in seen):
                    raise ValueError('Historical accounting packet pin mismatch or duplicate')
                prior = m.read(file)
                reference = registered.get(prior.get('id'))
                if (prior.get('schemaVersion') != 1 or prior.get('kind') not in
                        ('qualification-held-diagnostic', 'tool-qualification-result',
                         'qualification-pre-native-result', 'qualification-preclient-diagnostic', 'qualification-startup-diagnostic', 'qualification-prebinding-diagnostic') or
                        'cumulativeActualGameStartsAfter' not in prior or
                        prior['cumulativeActualGameStartsAfter'] is not None or
                        not reference or Path(reference['path']).resolve() != file or
                        reference.get('sha256') != expected):
                    raise ValueError('Historical accounting must retain a registered unknown cumulative packet')
                seen.add(file)
                pin(file)
                history_pins.append({'path': str(file), 'sha256': expected})
            request['accountingPins'] = [{'path': str(accounting_path),
                                          'sha256': m.digest(accounting_path)}, *history_pins]
        for item in order.get('inputs', []):
            file = (Path(request['order']).parent / item['path']).resolve()
            if m.digest(file) != item.get('sha256'):
                raise ValueError('Qualification input mismatch')
            pin(file)
        for item in config.get('staged_plugins', []):
            file = Path(item['source']).resolve()
            if m.digest(file) != item.get('sha256'):
                raise ValueError('Staged qualification plugin mismatch')
            pin(file)
        fixture = scenario.get('fixture')
        if fixture:
            directory = Path(config.get('fixture_dir') or Path(config['profiles']) / order['profile'] / 'saves')
            for ext in ('ess', 'skse'):
                file = directory / (fixture['saveStem'] + '.' + ext)
                if m.digest(file) != fixture[ext + 'Sha256']:
                    raise ValueError('Qualification fixture mismatch')
                pin(file)
        for file in m.HERE.glob('*.py'):
            pin(file)
        request.update(requestPath=str(path), orderData=order, configuration=config,
                       scenario=scenario, configPath=str(config_path), scenarioPath=str(scenario_path),
                       executorPins=inventory(request['executor']), pins=pins)
        canonical = json.dumps(request, sort_keys=True)
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT * FROM qualifications WHERE id=?', (request['id'],)).fetchone()
            if old:
                if old['request'] != canonical:
                    raise ValueError('Qualification identity is immutable')
                return {'id': request['id'], 'duplicate': True}
            if (self.qualification_busy(con) or con.execute("SELECT id FROM qualifications WHERE status NOT IN ('recorded','released','abandoned')").fetchone()
                    or con.execute('SELECT id FROM jobs WHERE id=?', (order['id'],)).fetchone()):
                raise ValueError('Recover existing owner or qualification first; do not reuse mod orders')
            con.execute("INSERT INTO qualifications VALUES(?,?,'prepared',NULL,NULL)", (request['id'], canonical))
            con.execute('INSERT INTO pipeline_holds VALUES(?,?)',
                        ('qualification-' + request['id'], 'Exclusive qualification lease; retain after completion until owner-reviewed clearance'))
            self.event(con, request['id'], 'qualification_prepared')
        return {'id': request['id'], 'status': 'prepared', 'holdId': 'qualification-' + request['id']}

    def qualification_abandon_prepared(self, identity, review_path):
        """Retire an explicitly reviewed reservation which never reached dispatch.

        Changed live input pins are why a fresh reservation may be needed; they
        are never rewritten here. No result packet, attempt or launch is created.
        """
        m = api(); review_path = Path(review_path).resolve(); review = m.read(review_path)
        review_hash = m.digest(review_path)
        if (review.get('schemaVersion') != 1 or review.get('kind') != 'qualification-prepared-abandon-review' or
                review.get('qualificationId') != identity or any(review.get(key) is not True for key in
                ('noDispatchReviewed', 'zeroStartsReviewed', 'installationSettled'))):
            raise ValueError('Explicit exact prepared-abandon review required')
        for key in ('verifiedBy', 'reason'): m.required_string(review, key)
        m.owner_evidence(review, review_path, require_deadline=False)
        row = self.qualification_show(identity); plan = json.loads(row['request'])
        if (review.get('preparedRequestSha256') != hashlib.sha256(row['request'].encode('utf-8')).hexdigest() or
                inventory(plan['executor']) != plan['executorPins']):
            raise ValueError('Original prepared request or pinned native observer changed')
        from order_platform import activate
        runner = activate(plan['executor'])
        with runner.native.SessionMutex(), self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            current = con.execute('SELECT * FROM qualifications WHERE id=?', (identity,)).fetchone()
            if (dict(current) != row or row['status'] != 'prepared' or row['expires'] is not None or
                    row['packet'] is not None or self.qualification_busy(con) or
                    con.execute('SELECT id FROM attempts WHERE id=?', ('qualification-' + identity,)).fetchone()):
                raise ValueError('Only unchanged unstarted prepared reservation may be abandoned')
            hold = con.execute('SELECT note FROM pipeline_holds WHERE id=?', ('qualification-' + identity,)).fetchone()
            if not hold or hold['note'] != 'Exclusive qualification lease; retain after completion until owner-reviewed clearance':
                raise ValueError('Exact routine reservation required; other holds remain unchanged')
            if (con.execute("SELECT id FROM qualifications WHERE id != ? AND status IN ('prepared','running')", (identity,)).fetchone() or
                    con.execute("SELECT j.id FROM jobs j JOIN released_orders r ON r.id=j.id WHERE j.status IN ('queued','running','waiting_player','session_waiting')").fetchone() or
                    con.execute("SELECT id FROM jobs WHERE status IN ('queued','session_waiting') AND json_extract(request,'$.cycle') IS NOT NULL").fetchone() or
                    con.execute("SELECT id FROM retry_attempts WHERE status='queued'").fetchone() or
                    con.execute("SELECT id FROM game_sessions WHERE status='queued'").fetchone()):
                raise ValueError('Other active or released work retains reservation')
            folder = self.local / 'qualifications' / identity
            runtime = Path(plan['configuration']['runtime'])
            from qualification_pre_native import _absolute
            _absolute(str(folder)); _absolute(str(runtime))
            if (folder.exists() and (not folder.is_dir() or any(folder.iterdir())) or
                    runtime.exists() and (not runtime.is_dir() or any(runtime.iterdir()))):
                raise ValueError('Dispatch/native artifacts exist; no zero-start inference permitted')
            if self.host().get('runnerConfig'):
                for state in (Path(m.read(self.host()['runnerConfig'])['runtime']) / 'runs').glob('*/state.json'):
                    if m.read(state).get('done') is not True: raise ValueError('Unfinished host session retains reservation')
            processes = runner.native.processes()
            if (not isinstance(processes, list) or not processes or
                    any(not isinstance(p, dict) or not isinstance(p.get('name'), str) or not p['name'] or
                        type(p.get('pid')) is not int or p['pid'] < 0 or
                        (p['pid'] == 0 and (p['name'] != '[System Process]' or p.get('parent') != 0)) for p in processes) or
                    any(p['name'].lower() in runner.GAME_NAMES for p in processes)):
                raise ValueError('Fresh complete native idle inventory required')
            if inventory(plan['executor']) != plan['executorPins'] or m.digest(review_path) != review_hash:
                raise ValueError('Observer or prepared-abandon review changed')
            result = {'id': identity, 'status': 'abandoned', 'actualGameStarts': 0,
                      'cumulativeActualGameStartsBefore': plan['cumulativeActualGameStartsBefore'],
                      'cumulativeActualGameStartsAfter': plan['cumulativeActualGameStartsBefore'],
                      'review': {'path': str(review_path), 'sha256': review_hash},
                      'globalProviderQualified': False, 'launchAuthorityGranted': False}
            con.execute("UPDATE qualifications SET status='abandoned' WHERE id=?", (identity,))
            con.execute('DELETE FROM pipeline_holds WHERE id=?', ('qualification-' + identity,))
            self.event(con, identity, 'qualification_prepared_abandoned', json.dumps(dict(result, reviewed=review), sort_keys=True))
        return result

    def qualification_guard(self, con, identity):
        if self.qualification_busy(con):
            raise ValueError('Another shared owner or installation blocks qualification')
        holds = [r['id'] for r in con.execute('SELECT id FROM pipeline_holds')]
        if holds != ['qualification-' + identity]:
            raise ValueError('Qualification requires its own exclusive lease and no other holds')

    def qualification_run(self, identity):
        m = api()
        row = self.qualification_show(identity)
        plan = self.qualification_verify(row)
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            if con.execute('SELECT status FROM qualifications WHERE id=?', (identity,)).fetchone()[0] != 'prepared':
                raise ValueError('Qualification may be dispatched only once')
            self.qualification_guard(con, identity)
            expires = min(time.time() + plan['maximumWallSeconds'], plan['deadlineUtc'])
            con.execute("UPDATE qualifications SET status='running',expires=? WHERE id=?", (expires, identity))
        folder = self.local / 'qualifications' / identity
        m.write(folder / 'plan.json', plan)
        m.write(folder / 'config.json', plan['configuration'])
        m.write(folder / 'scenario.json', plan['scenario'])
        # Durable dispatch intent precedes process creation; a crash cannot imply zero starts.
        m.write(folder / 'dispatch-intent.json', {'id': identity, 'at': time.time(), 'expires': expires})
        with (folder / 'executor.log').open('w', encoding='utf-8') as log:
            try:
                child = subprocess.run([sys.executable, str(m.HERE / 'polygon.py'), '--root', str(self.root),
                                        '_execute-qualification', identity], stdout=log, stderr=subprocess.STDOUT,
                                       timeout=max(.01, expires - time.time()),
                                       env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
                result = {'returncode': child.returncode}
            except subprocess.TimeoutExpired:
                # subprocess.run kills/waits only for this exact child. Native guardian restores.
                result = {'timeout': True, 'reason': f"{plan['maximumWallSeconds']}-second authority exhausted; guardian/native recovery required"}
        m.write(folder / 'child-exit.json', result)
        return self.qualification_collect(identity)

    def qualification_check(self, identity):
        m = api()
        self.qualification_verify(self.qualification_show(identity))
        child = subprocess.run([sys.executable, str(m.HERE / 'polygon.py'), '--root', str(self.root),
                                '_check-qualification', identity], capture_output=True, text=True, timeout=30,
                               env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        if child.returncode:
            raise ValueError('Candidate offline validation refused: ' + child.stdout + child.stderr)
        return {'id': identity, 'validated': True, 'launched': False}

    def child_qualification_check(self, identity):
        plan = self.qualification_verify(self.qualification_show(identity))
        sys.path.insert(0, plan['executor'])
        from skyrim_autotest.config import load
        from skyrim_autotest.scenarios import validate
        from skyrim_autotest.restart_budget import plan as restart_plan
        configuration = load(plan['configPath'])
        validate(plan['scenario'])
        if 'companion' in plan:
            from qualification_companion import validate as validate_companion
            if validate_companion(plan, configuration, plan['scenario'], Path(plan['requestPath']).parent) != plan['companion']:
                raise ValueError('Normalized qualification companion recipe differs')
        if restart_plan(plan['scenario'])['maximum'] != 0:
            raise ValueError('Qualification cannot reserve a restart')
        return 0

    def child_qualification(self, identity):
        m = api()
        row = self.qualification_show(identity)
        plan = self.qualification_verify(row)
        folder = self.local / 'qualifications' / identity
        if (row['status'] != 'running' or time.time() >= row['expires'] or
                m.read(folder / 'plan.json') != plan or m.read(folder / 'config.json') != plan['configuration'] or
                m.read(folder / 'scenario.json') != plan['scenario']):
            raise ValueError('Qualification ownership, deadline or frozen plan changed')
        sys.path.insert(0, plan['executor'])
        from skyrim_autotest import runner
        from skyrim_autotest.config import load
        from skyrim_autotest.scenarios import validate
        if Path(runner.__file__).resolve() != Path(plan['executor']) / 'skyrim_autotest/runner.py':
            raise ValueError('Wrong candidate module imported')
        validate(plan['scenario'])
        runner.configure(load(folder / 'config.json'))
        m.write(folder / 'worker.json', {'identity': runner.native.identity(os.getpid())})
        # Never let runner.run's automatic recover() take over an older native session.
        for state_file in (Path(plan['configuration']['runtime']) / 'runs').glob('*/state.json'):
            if m.read(state_file).get('done') is not True:
                raise ValueError('Unfinished native session requires separate recovery')
        profile = self.source_profile(plan['orderData'], runner, output_dir=folder)
        original_request = runner.request
        starts = 0
        def guarded_request(port, route, *args, **kwargs):
            nonlocal starts
            if route == 'run':
                if starts or time.time() >= row['expires']:
                    raise ValueError('Qualification launch budget exhausted')
                starts += 1
                m.write(folder / 'launch-intent.json', {'at': time.time(), 'maximumActualGameStarts': 1})
            return original_request(port, route, *args, **kwargs)
        runner.request = guarded_request
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            self.qualification_guard(con, identity)
            self.qualification_verify(row)
            if con.execute('SELECT status FROM qualifications WHERE id=?', (identity,)).fetchone()[0] != 'running':
                raise ValueError('Qualification claim changed')
            con.execute('INSERT INTO attempts VALUES(?,?)', ('qualification-' + identity, time.time()))
        def run_native():
            return runner.run(profile, folder / 'scenario.json', restart_idle_mo2=True,
                              order={'id': 'qualification-' + identity, 'owner': plan['orderData']['sourceChat']})
        if 'companion' in plan:
            from qualification_companion import run as run_companion
            return run_companion(self, plan, row, folder, runner, run_native)
        return run_native()

    def qualification_recover(self, identity):
        """Restore only this candidate runtime; never launch or refresh its allowance."""
        m = api()
        row = self.qualification_show(identity)
        self.qualification_verify(row, authority=False)
        if row['status'] != 'running':
            raise ValueError('Only an active qualification can need recovery')
        child = subprocess.run([sys.executable, str(m.HERE / 'polygon.py'), '--root', str(self.root),
                                '_recover-qualification', identity], capture_output=True, text=True,
                               env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        if child.returncode:
            return {'id': identity, 'status': 'running', 'reason': child.stdout + child.stderr}
        return self.qualification_collect(identity)

    def child_qualification_recover(self, identity):
        m = api()
        row = self.qualification_show(identity)
        plan = self.qualification_verify(row, authority=False)
        folder = self.local / 'qualifications' / identity
        if row['status'] != 'running':
            raise ValueError('No running qualification')
        sys.path.insert(0, plan['executor'])
        from skyrim_autotest import runner
        from skyrim_autotest.config import load
        worker = folder / 'worker.json'
        if not (folder / 'child-exit.json').exists():
            if not worker.exists() or not m.read(worker).get('identity'):
                raise ValueError('Unproven worker completion; no recovery takeover')
            if runner.native.alive(m.read(worker)['identity']):
                raise ValueError('Qualification worker is alive; no recovery takeover')
            m.write(folder / 'child-exit.json', {'verifiedDeadWorker': m.read(worker)})
        runner.configure(load(folder / 'config.json'))
        runs = Path(plan['configuration']['runtime']) / 'runs'
        for state in runs.glob('*/state.json'):
            data = m.read(state)
            if data.get('done') is not True and data.get('order', {}).get('id') != 'qualification-' + identity:
                raise ValueError('Foreign unfinished native session; separate review required')
        runner.recover()
        return 0

    def qualification_collect(self, identity):
        m = api()
        row = self.qualification_show(identity)
        plan = json.loads(row['request'])
        if row['packet']:
            retained = json.loads(row['packet'])
            if m.digest(retained['path']) != retained['sha256']:
                raise ValueError('Qualification result changed')
            packet = m.read(retained['path'])
            for pin in packet['files']:
                if m.digest(pin['path']) != pin['sha256']:
                    raise ValueError('Qualification evidence changed')
            if packet.get('kind') in ('qualification-preclient-diagnostic', 'qualification-startup-diagnostic', 'qualification-prebinding-diagnostic'):
                from qualification_preclient import verify_packet
                verify_packet(self, plan, packet)
                return packet
            if packet.get('kind') == 'qualification-held-diagnostic':
                from qualification_diagnostic import verify_archive
                verify_archive(packet)
            if packet.get('collectionRepair'):
                from qualification_collection_repair import verify_packet_archive
                verify_packet_archive(packet)
            if 'companion' in plan:
                from qualification_companion import verify_packet
                verify_packet(self, plan, packet)
            return packet
        folder = self.local / 'qualifications' / identity
        if row['status'] != 'running' or not (folder / 'child-exit.json').is_file():
            return {'id': identity, 'status': row['status'], 'reason': 'Child completion unproven; retain lease'}
        runs = [(p, m.read(p)) for p in (Path(plan['configuration']['runtime']) / 'runs').glob('*/state.json')
                if m.read(p).get('order', {}).get('id') == 'qualification-' + identity]
        with self.connect() as con:
            admitted = con.execute('SELECT id FROM attempts WHERE id=?', ('qualification-' + identity,)).fetchone()
        if not runs and not admitted:
            packet = {'schemaVersion': 1, 'kind': 'tool-qualification-result', 'id': identity,
                      'orderId': plan['orderData']['id'], 'testingStarted': False, 'actualGameStarts': 0,
                      'runDirectory': None, 'restored': None, 'reason': 'Child ended before native admission',
                      'collectionFinished': True, 'globalProviderQualified': False,
                      'cumulativeActualGameStartsBefore': plan['cumulativeActualGameStartsBefore'],
                      'cumulativeActualGameStartsAfter': plan['cumulativeActualGameStartsBefore'],
                      'files': [{'path': str(folder / name), 'sha256': m.digest(folder / name)}
                                for name in ('plan.json', 'dispatch-intent.json', 'child-exit.json', 'executor.log')]}
            packet['files'].extend(plan.get('accountingPins', []))
            m.write(folder / 'packet.json', packet)
            with self.connect() as con:
                con.execute("UPDATE qualifications SET status='recorded',packet=? WHERE id=?", (json.dumps({'path': str(folder / 'packet.json'), 'sha256': m.digest(folder / 'packet.json')}), identity))
            return packet
        if len(runs) != 1:
            return {'id': identity, 'status': 'running', 'reason': 'Native run/accounting unproven; retain lease and recover separately'}
        state_path, state = runs[0]
        if state.get('done') is not True or state.get('restored') is not True or state.get('restoreErrors'):
            return {'id': identity, 'status': 'running', 'reason': 'Native restoration unproven; retain lease'}
        result = m.read(state_path.parent / 'result.json')
        if result.get('restored') is not True or result.get('restoreErrors'):
            raise ValueError('Native result restoration differs')
        starts = (0 if not state.get('game') and not any(p.get('role') == 'game' for p in state.get('owned', []))
                  and not (folder / 'launch-intent.json').exists() else self.native_game_starts(state))
        if starts > 1:
            raise ValueError('Qualification exceeded one physical game start; retain lease')
        archive = state_path.parent / 'test-profile'
        if (Path(state.get('profileArchive', '')).resolve() != archive.resolve() or not archive.is_dir()
                or not any(p.is_file() for p in archive.rglob('*'))
                or not state.get('testProfile') or Path(state['testProfile']).exists()):
            raise ValueError('Native profile archive/removal unproven; retain lease')
        packet = {'schemaVersion': 1, 'kind': 'tool-qualification-result', 'id': identity,
                  'orderId': plan['orderData']['id'], 'sourceThreadId': plan['orderData']['sourceThreadId'],
                  'runDirectory': str(state_path.parent), 'restored': True, 'collectionFinished': True,
                  'executionOutcome': result.get('result'), 'actualGameStarts': starts,
                  'attemptId': 'qualification-' + identity, 'reason': result.get('reason', ''),
                  'cumulativeActualGameStartsBefore': plan['cumulativeActualGameStartsBefore'],
                  'cumulativeActualGameStartsAfter': (None if plan['cumulativeActualGameStartsBefore'] is None
                                                       else plan['cumulativeActualGameStartsBefore'] + starts),
                  'files': [], 'globalProviderQualified': False}
        for directory in (folder, state_path.parent):
            for file in sorted(directory.iterdir()):
                if file.is_file() and file.suffix in ('.json', '.jsonl', '.log') and file.name != 'packet.json':
                    packet['files'].append({'path': str(file), 'sha256': m.digest(file)})
        packet['files'].extend(m.raw_evidence_pins(state_path.parent))
        packet['files'].extend(plan.get('accountingPins', []))
        packet['profileArchivePins'] = [{'path': str(p), 'sha256': m.digest(p)}
                                        for p in sorted(archive.rglob('*')) if p.is_file()]
        packet['files'].extend(packet['profileArchivePins'])
        packet['testResult'] = self.test_projection(plan['orderData'], packet)
        packet['collectionFindings'] = self.collection_findings(state_path.parent)
        # This is evidence for operator/tool-chat review, never automatic platform acceptance.
        self.qualification_verify(row, authority=False)
        if 'companion' in plan:
            from qualification_companion import collect as collect_companion
            packet['toolCompanion'] = collect_companion(self, plan, state_path.parent)
            packet['files'].extend(packet['toolCompanion']['pins'])
        if (folder / 'collection-repair.json').exists():
            from qualification_collection_repair import evidence_pins
            packet['collectionRepair'] = m.read(folder / 'collection-repair.json')
            packet['files'].extend(evidence_pins(self, identity))
        m.write(folder / 'packet.json', packet)
        with self.connect() as con:
            con.execute("UPDATE qualifications SET status='recorded',packet=? WHERE id=?", (json.dumps({'path': str(folder / 'packet.json'), 'sha256': m.digest(folder / 'packet.json')}), identity))
            self.event(con, identity, 'qualification_recorded', 'Lease remains held; no old queue dispatch')
        return packet

    def qualification_release(self, identity, review_path):
        """Explicitly finish a successful planned reservation, never a recovery hold."""
        m = api()
        review_path = Path(review_path).resolve()
        child = subprocess.run([sys.executable, str(m.HERE / 'polygon.py'), '--root', str(self.root),
                                '_release-qualification', identity, str(review_path)],
                               capture_output=True, text=True, timeout=30,
                               env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        if child.returncode:
            raise ValueError('Qualification reservation retained: ' + child.stdout + child.stderr)
        return json.loads(child.stdout)

    @staticmethod
    def qualification_successful_result(plan, packet):
        """Allow declared tool observations, without converting them into passed assertions."""
        m = api()
        if packet.get('kind') in ('qualification-preclient-diagnostic', 'qualification-startup-diagnostic', 'qualification-prebinding-diagnostic'):
            return False
        if 'companion' in plan:
            from qualification_companion import successful
            if not successful(plan, packet):
                return False
        if packet.get('kind') == 'qualification-held-diagnostic':
            return False
        projection = packet.get('testResult', {})
        if (projection.get('testingStarted') is not True or projection.get('interruptionObserved')
                or projection.get('subjectMismatchObserved') or packet.get('executionOutcome') != 'passed'
                or any(c['status'] != 'passed' for c in projection.get('auxiliaryCoverage', {}).get('checks', []))):
            return False
        declared = {c['name']: c['role'] for c in plan['orderData']['testing']['checks']}
        checks = projection.get('coverage', {}).get('checks', [])
        if len(checks) != len(declared) or {c['name'] for c in checks} != set(declared):
            return False
        observations = {s['name'] for s in plan['scenario']['steps']
                        if s.get('observe') is True and not s.get('assert')}
        actual = m.read(Path(packet['runDirectory']) / 'result.json').get('checks', [])
        for check in checks:
            if check['status'] == 'passed':
                continue
            matches = [c for c in actual if c.get('name') == check['name']]
            if (check['status'] != 'unavailable' or declared[check['name']] != 'tooling'
                    or check['name'] not in observations or len(matches) != 1
                    or matches[0].get('result') != 'observed' or matches[0].get('provenance')):
                return False
        return True

    def child_qualification_release(self, identity, review_path):
        m = api()
        review_path = Path(review_path).resolve()
        review = m.read(review_path)
        if (review.get('schemaVersion') != 1 or review.get('kind') != 'tool-qualification-release'
                or review.get('qualificationId') != identity or
                any(review.get(key) is not True for key in ('successfulResultReviewed', 'collectionReviewed',
                    'nativeCompletionReviewed', 'restorationReviewed', 'archiveReviewed'))):
            raise ValueError('Exact qualification and explicit technical completion review required')
        for key in ('verifiedBy', 'summary'):
            m.required_string(review, key)
        canonical = json.dumps({'review': review, 'path': str(review_path), 'sha256': m.digest(review_path)}, sort_keys=True)
        row = self.qualification_show(identity)
        packet = self.qualification_collect(identity)  # recheck final packet AND every retained evidence hash
        if not row['packet'] or review.get('packetSha256') != json.loads(row['packet'])['sha256']:
            raise ValueError('Review must bind the exact registered final packet hash')
        with self.connect() as con:
            prior = con.execute('SELECT review FROM qualification_releases WHERE id=?', (identity,)).fetchone()
        if row['status'] == 'released':
            if not prior or prior['review'] != canonical:
                raise ValueError('Completed reservation review is immutable')
            return {'id': identity, 'status': 'released', 'duplicate': True}
        plan = self.qualification_verify(row, authority=False)  # completion need not extend expired launch authority
        if (row['status'] != 'recorded' or not self.qualification_successful_result(plan, packet)
                or packet.get('actualGameStarts') != 1 or packet.get('restored') is not True
                or packet.get('collectionFinished') is not True or packet.get('collectionFindings')):
            raise ValueError('Only factually successful fully collected/restored qualification can finish normally')
        folder = self.local / 'qualifications' / identity
        exit_record = m.read(folder / 'child-exit.json')
        if type(exit_record.get('returncode')) is not int or exit_record['returncode'] != 0 or exit_record.get('timeout'):
            raise ValueError('Exact successful child exit required; timeout/recovery remains held')
        worker = m.read(folder / 'worker.json').get('identity')
        def checked_identity(value):
            if (not isinstance(value, dict) or type(value.get('pid')) is not int or value['pid'] <= 0
                    or type(value.get('birth')) is not int or value['birth'] <= 0 or not value.get('path')):
                raise ValueError('Exact native identity required')
            return value
        checked_identity(worker)
        run = Path(packet['runDirectory'])
        state, result = m.read(run / 'state.json'), m.read(run / 'result.json')
        if (state.get('runner') != worker or state.get('order', {}).get('id') != 'qualification-' + identity
                or state.get('done') is not True or state.get('restored') is not True or state.get('restoreErrors')
                or result.get('restored') is not True or result.get('restoreErrors') or result.get('result') != 'passed'
                or self.native_game_starts(state) != 1):
            raise ValueError('Native worker/run/result ownership or restoration differs')
        archive = (run / 'test-profile').resolve()
        current_archive = [{'path': str(p), 'sha256': m.digest(p)}
                           for p in sorted(archive.rglob('*')) if p.is_file()]
        if (not packet.get('profileArchivePins') or current_archive != packet['profileArchivePins']
                or Path(state.get('profileArchive', '')).resolve() != archive
                or not state.get('testProfile') or Path(state['testProfile']).exists()):
            raise ValueError('Collected profile archive/removal differs')
        sys.path.insert(0, plan['executor'])
        from skyrim_autotest import runner
        if Path(runner.__file__).resolve() != Path(plan['executor']) / 'skyrim_autotest/runner.py':
            raise ValueError('Wrong candidate native observer')
        # Hold the same native mutex AND SQLite write transaction while observing
        # and removing only this reservation. No launch, recovery or next call.
        with runner.native.SessionMutex(), self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            if con.execute('SELECT status FROM qualifications WHERE id=?', (identity,)).fetchone()[0] != 'recorded':
                raise ValueError('Qualification ownership changed')
            self.qualification_guard(con, identity)
            if con.execute("SELECT id FROM qualifications WHERE id != ? AND status IN ('prepared','running')", (identity,)).fetchone():
                raise ValueError('Another qualification reservation exists')
            if (con.execute("SELECT j.id FROM jobs j JOIN released_orders r ON r.id=j.id WHERE j.status IN ('queued','running','waiting_player','session_waiting')").fetchone()
                    or con.execute("SELECT id FROM jobs WHERE status IN ('queued','session_waiting') AND json_extract(request,'$.cycle') IS NOT NULL").fetchone()
                    or con.execute("SELECT id FROM retry_attempts WHERE status='queued'").fetchone()
                    or con.execute("SELECT id FROM game_sessions WHERE status='queued'").fetchone()):
                raise ValueError('Previously released ordinary work would become runnable; retain reservation')
            identities = [worker] + [checked_identity(p['identity']) for p in state.get('owned', [])]
            if any(runner.native.alive(ident) for ident in identities):
                raise ValueError('Exact worker/owned native process is still alive')
            processes = runner.native.processes()
            if not isinstance(processes, list) or not processes:
                raise ValueError('Native process inventory is unavailable')
            if any(any(p.get('pid') == ident['pid'] for p in processes)
                   and runner.native.identity(ident['pid']) is None for ident in identities):
                raise ValueError('Listed worker/owned PID identity is unknown; retain reservation')
            if any(p['name'].lower() in runner.GAME_NAMES for p in processes):
                raise ValueError('Current game/loader blocks reservation completion')
            runtimes = {Path(plan['configuration']['runtime'])}
            if self.host().get('runnerConfig'):
                runtimes.add(Path(m.read(self.host()['runnerConfig'])['runtime']))
            for runtime in runtimes:
                for state_file in (runtime / 'runs').glob('*/state.json'):
                    if m.read(state_file).get('done') is not True:
                        raise ValueError('Unfinished native session retains reservation')
            self.qualification_collect(identity)
            if m.digest(review_path) != json.loads(canonical)['sha256']:
                raise ValueError('Technical review changed')
            con.execute('DELETE FROM pipeline_holds WHERE id=?', ('qualification-' + identity,))
            con.execute("UPDATE qualifications SET status='released' WHERE id=?", (identity,))
            con.execute('INSERT INTO qualification_releases VALUES(?,?)', (identity, canonical))
            self.event(con, identity, 'qualification_released', canonical)
        return {'id': identity, 'status': 'released', 'globalProviderQualified': False}

"""Durable multi-order sessions; native executor still owns one physical launch."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import sys
import time


def api():
    # Imported lazily to avoid the Polygon/mixin import cycle (also CLI __main__).
    import polygon
    return polygon


class SharedSessions:
    def init_sessions(self):
        with self.connect() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS game_sessions (
              id TEXT PRIMARY KEY, request TEXT NOT NULL, status TEXT NOT NULL,
              plan TEXT, sha256 TEXT, note TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS session_members (
              order_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, position INTEGER NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_session ON game_sessions((1))
              WHERE status IN ('preparing','running','finalizing');
            """)

    def member_session(self, job):
        with self.connect() as con:
            row = con.execute("SELECT s.* FROM game_sessions s JOIN session_members m ON s.id=m.session_id WHERE m.order_id=?", (job,)).fetchone()
        return dict(row) if row else None

    def session_show(self, session):
        with self.connect() as con:
            row = con.execute("SELECT * FROM game_sessions WHERE id=?", (session,)).fetchone()
        if not row:
            raise ValueError("Unknown shared session")
        return dict(row)

    def register_session(self, path):
        m = api()
        request = m.read(path)
        if set(request) != {'schemaVersion', 'id', 'orderIds', 'compatibility'} or request['schemaVersion'] != 1 or not m.SAFE_ID.fullmatch(request['id']):
            raise ValueError("Session requires schemaVersion1, id, orderIds and compatibility")
        ids = request['orderIds']
        if not isinstance(ids, list) or not 2 <= len(ids) <= 32 or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("Session needs 2..32 unique orders in execution order")
        review = request['compatibility']
        if not isinstance(review, dict) or review.get('stateIndependent') is not True:
            raise ValueError("Review and confirm segment state compatibility before grouping")
        for key in ('verifiedBy', 'reason'):
            m.required_string(review, key)
        canonical = json.dumps(request, sort_keys=True, ensure_ascii=False)
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            prior = con.execute('SELECT request FROM game_sessions WHERE id=?', (request['id'],)).fetchone()
            if prior:
                if prior['request'] != canonical:
                    raise ValueError('Shared session id is immutable')
                return {'id': request['id'], 'duplicate': True}
            orders = []
            for job in ids:
                row = con.execute('SELECT * FROM jobs WHERE id=?', (job,)).fetchone()
                if not row or row['status'] != 'queued' or row['mode'] != 'automatic':
                    raise ValueError('Only queued automatic orders may join a session')
                if con.execute('SELECT order_id FROM session_members WHERE order_id=?', (job,)).fetchone():
                    raise ValueError('Order already belongs to an immutable session')
                order = json.loads(row['request'])
                if order.get('cycle'):
                    raise ValueError('Cycle installation slots are single-order; use separate sessions until shared slot preparation is supported')
                orders.append(order)
            self.compatible_orders(orders)
            con.execute('INSERT INTO game_sessions(id,request,status) VALUES(?,?,?)', (request['id'], canonical, 'queued'))
            for i, job in enumerate(ids):
                con.execute('INSERT INTO session_members VALUES(?,?,?)', (job, request['id'], i))
        return {'id': request['id'], 'orderIds': ids, 'status': 'queued'}

    def cancel_session(self, session_id):
        # Cancel only an unclaimed plan; preserve request/history, release no live owner.
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT status FROM game_sessions WHERE id=?', (session_id,)).fetchone()
            if not row or row['status'] not in ('queued', 'cancelled'):
                raise ValueError('Only an unstarted session may be dissolved')
            con.execute("UPDATE game_sessions SET status='cancelled' WHERE id=?", (session_id,))
            con.execute('DELETE FROM session_members WHERE session_id=?', (session_id,))
            self.event(con, session_id, 'session_cancelled', 'Unstarted grouping dissolved; member orders unchanged')
        return {'id': session_id, 'status': 'cancelled'}

    @staticmethod
    def compatible_orders(orders):
        first = orders[0]
        pins = {}
        for order in orders:
            if (order['profile'], order.get('profileSelection', {'mode': 'active'})) != (first['profile'], first.get('profileSelection', {'mode': 'active'})):
                raise ValueError('Incompatible profile/composition requirements')
            if not order.get('testing') or order['testing']['start']['kind'] != 'check':
                raise ValueError('Shared sessions require per-member factual check boundaries')
            for pin in order['inputs']:
                key = str(Path(pin['path']).resolve()).casefold()
                if key in pins and pins[key] != pin['sha256']:
                    raise ValueError('Conflicting member input pins')
                pins[key] = pin['sha256']

    def claim_shared(self):
        """Called before normal claim; claim the oldest released work, never bypass FIFO."""
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            if con.execute("SELECT id FROM game_sessions WHERE status IN ('preparing','running','finalizing')").fetchone():
                return {'busy': True}
            if con.execute("SELECT id FROM retry_attempts WHERE status IN ('running','collecting')").fetchone():
                return {'busy': True}
            if (con.execute('SELECT id FROM pipeline_holds').fetchone() or
                con.execute("SELECT id FROM jobs WHERE status='running'").fetchone() or
                con.execute("SELECT id FROM cycle_slots WHERE status IN ('reserved','blocked')").fetchone()):
                return None
            ready = con.execute("SELECT j.* FROM jobs j WHERE status='queued' AND mode='automatic' AND (id IN (SELECT id FROM released_orders) OR json_extract(request,'$.cycle') IS NOT NULL) ORDER BY submitted,id").fetchall()
            if not ready:
                return None
            member = con.execute('SELECT session_id FROM session_members WHERE order_id=?', (ready[0]['id'],)).fetchone()
            if not member:
                return None
            session = con.execute('SELECT * FROM game_sessions WHERE id=?', (member['session_id'],)).fetchone()
            if session['status'] != 'queued':
                return {'busy': True}
            ids = json.loads(session['request'])['orderIds']
            # A group cannot skip older eligible work between its members.
            if [r['id'] for r in ready[:len(ids)]] != ids:
                return {'id': session['id'], 'status': 'awaiting_members_or_fifo', 'reason': 'Members must be the contiguous oldest released ready orders'}
            for i, job in enumerate(ids):
                con.execute('UPDATE jobs SET status=? WHERE id=?', ('running' if i == 0 else 'session_waiting', job))
                self.event(con, job, 'session_waiting', 'Shared session ' + session['id'])
            con.execute("UPDATE game_sessions SET status='preparing' WHERE id=?", (session['id'],))
        return {'id': session['id'], 'orderIds': ids}

    def prepare_shared(self, session_id):
        m = api()
        session = self.session_show(session_id)
        if session['status'] != 'preparing' or session['plan']:
            raise ValueError('Shared session is not a fresh claimed preparation')
        request = json.loads(session['request'])
        orders = [json.loads(self.get(i)['request']) for i in request['orderIds']]
        self.compatible_orders(orders)
        parts, members = [], []
        for index, order in enumerate(orders):
            self.check_launch_authorization(order)
            self.verify_inputs(order)
            folder = self.evidence_dir(order['id'])
            folder.mkdir(parents=True, exist_ok=True)
            m.write(folder / 'request.json', order)
            if order['schemaVersion'] == 2:
                platform = self.prepare_platform(order)
                config, scenario = platform['configuration'], platform['scenario']
            else:
                platform = None
                config, scenario = order['resolvedConfig'], order['scenarioData']
            if scenario.get('kind') or not scenario.get('steps') or set(scenario) - {'schemaVersion', 'steps', 'cell', 'fixture', 'startMode'}:
                raise ValueError('Specialized or process-specific scenarios require separate sessions')
            globals_ = {k: v for k, v in scenario.items() if k != 'steps'}
            pins = self.runtime_pins(order)
            signature = (config, globals_, pins)
            if parts and signature != parts[0]:
                raise ValueError('Incompatible platform, configuration or initial fixture')
            parts.append(signature)
            mapping = {f'm{index}-{i}': step['name'] for i, step in enumerate(scenario['steps'])}
            if len(set(mapping.values())) != len(mapping):
                raise ValueError('Member checks need unique names')
            members.append({'orderId': order['id'], 'orderSha256': m.subject_contract.identity(order),
                            'sourceChat': order['sourceChat'], 'sourceThreadId': order['sourceThreadId'],
                            'checkNames': mapping, 'scenario': scenario,
                            'platformSha256': m.subject_contract.identity(platform) if platform else None})
            m.write(folder / 'executor-pins.json', pins)
            m.write(folder / 'config.json', config)
            m.write(folder / 'scenario.json', scenario)
        combined = copy.deepcopy(parts[0][1])
        combined['steps'] = []
        for member in members:
            for name, step in zip(member['checkNames'], member['scenario']['steps']):
                combined['steps'].append({**copy.deepcopy(step), 'name': name})
        if len(combined['steps']) > 256:
            raise ValueError('Shared scenario exceeds 256 bounded checks')
        self.executor()[1](combined)
        plan = {'schemaVersion': 1, 'id': session_id, 'anchorOrderId': orders[0]['id'],
                'request': request, 'members': members, 'configuration': parts[0][0],
                'scenario': combined, 'pins': parts[0][2], 'executor': str(self.executor()[0])}
        canonical = json.dumps(plan, sort_keys=True, ensure_ascii=False)
        folder = self.local / 'sessions' / session_id
        m.write(folder / 'session-plan.json', plan)
        m.write(folder / 'config.json', plan['configuration'])
        m.write(folder / 'scenario.json', combined)
        with self.connect() as con:
            con.execute("UPDATE game_sessions SET plan=?,sha256=?,status='running' WHERE id=? AND status='preparing'", (canonical, m.subject_contract.identity(plan), session_id))
        return self.verify_shared(session_id)

    def verify_shared(self, session_id):
        m = api()
        row = self.session_show(session_id)
        if not row['plan']:
            raise ValueError('No frozen shared session plan')
        plan = json.loads(row['plan'])
        folder = self.local / 'sessions' / session_id
        if m.subject_contract.identity(plan) != row['sha256'] or m.read(folder / 'session-plan.json') != plan:
            raise ValueError('Shared session plan changed')
        if str(self.executor()[0]) != plan['executor']:
            raise ValueError('Shared executor selection changed')
        for name, expected in [('config.json', plan['configuration']), ('scenario.json', plan['scenario'])]:
            if m.read(folder / name) != expected:
                raise ValueError('Materialized shared plan changed')
        for member in plan['members']:
            order = json.loads(self.get(member['orderId'])['request'])
            if m.subject_contract.identity(order) != member['orderSha256']:
                raise ValueError('Shared member request changed')
            self.verify_inputs(order)
            if member['platformSha256']:
                if m.subject_contract.identity(self.verify_platform(order)) != member['platformSha256']:
                    raise ValueError('Shared member platform changed')
            elif self.runtime_pins(order) != plan['pins']:
                raise ValueError('Shared executor inventory changed')
            for pin in plan['pins']:
                if m.digest(pin['path']) != pin['sha256']:
                    raise ValueError('Shared platform pin changed')
        return plan

    def child_shared(self, session_id):
        m = api()
        session = self.session_show(session_id)
        if session['status'] != 'running':
            raise ValueError('No claimed shared session')
        plan = self.verify_shared(session_id)
        orders = [json.loads(self.get(member['orderId'])['request']) for member in plan['members']]
        for order in orders:
            self.check_launch_authorization(order)
        self.executor()
        from skyrim_autotest import runner
        from skyrim_autotest.config import load
        folder = self.local / 'sessions' / session_id
        runner.configure(load(folder / 'config.json'))
        for order in orders:
            self.source_profile(order, runner)
        # UNIQUE attempts make replay of a claimed child refuse before another launch.
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            if con.execute('SELECT status FROM game_sessions WHERE id=?', (session_id,)).fetchone()[0] != 'running':
                raise ValueError('Shared ownership changed before native dispatch')
            for order in orders:
                con.execute('INSERT INTO attempts VALUES(?,?)', (order['id'], time.time()))
        return runner.run(orders[0]['profile'], folder / 'scenario.json', restart_idle_mo2=True,
                          order={'id': plan['anchorOrderId'], 'owner': 'Polygon session ' + session_id})

    def execute_shared(self, claimed):
        m = api()
        if 'orderIds' not in claimed:
            return claimed
        session_id = claimed['id']
        try:
            self.prepare_shared(session_id)
        except (ValueError, OSError) as error:
            return self.finish_shared(session_id, reason=str(error))
        folder = self.local / 'sessions' / session_id
        with (folder / 'executor.log').open('w', encoding='utf-8') as log:
            child = subprocess.run([sys.executable, str(Path(__file__).with_name('polygon.py')), '--root', str(self.root), '_execute-session', session_id],
                                   stdout=log, stderr=subprocess.STDOUT, shell=False)
        m.write(folder / 'child-exit.json', {'returncode': child.returncode})
        self.reconcile_shared()
        if self.session_show(session_id)['status'] == 'complete':
            return {'sessionId': session_id, 'status': 'complete', 'orders': [self.get(i) for i in claimed['orderIds']]}
        anchor = json.loads(self.get(claimed['orderIds'][0])['request'])
        if child.returncode == 2 and not self.matching_runs(anchor):
            return self.finish_shared(session_id, reason='Executor refused before a recorded shared game session; see executor.log')
        return {'sessionId': session_id, 'status': 'running', 'reason': 'Recovery/reconciliation required; never automatically repeat'}

    def reconcile_shared(self):
        m = api()
        with self.connect() as con:
            sessions = con.execute("SELECT * FROM game_sessions WHERE status IN ('preparing','running','finalizing')").fetchall()
        result = []
        for row in sessions:
            ids = json.loads(row['request'])['orderIds']
            order = json.loads(self.get(ids[0])['request'])
            runs = self.matching_runs(order)
            if len(runs) > 1:
                raise ValueError('Multiple native runs for one shared session')
            if runs and runs[0][1].get('done'):
                path, state = runs[0]
                # Keep one barrier until restoration is actually proven.
                if state.get('restored') is not True or state.get('restoreErrors'):
                    self.hold_pipeline(row['id'], 'Shared session restoration requires recovery')
                    continue
                self.finish_shared(row['id'], path.parent)
                result.extend(ids)
        return result

    def finish_shared(self, session_id, run=None, reason=None):
        m = api()
        session = self.session_show(session_id)
        if session['status'] == 'complete':
            return {'sessionId': session_id, 'duplicate': True}
        request = json.loads(session['request'])
        plan = json.loads(session['plan']) if session['plan'] else None
        if plan and (m.subject_contract.identity(plan) != session['sha256'] or m.read(self.local / 'sessions' / session_id / 'session-plan.json') != plan):
            raise ValueError('Frozen shared session provenance changed')
        state = m.read(Path(run) / 'state.json') if run else {}
        if run and (not plan or state.get('order', {}).get('id') != plan['anchorOrderId'] or state.get('scenarioHash') != m.digest(self.local / 'sessions' / session_id / 'scenario.json') or state.get('done') is not True or state.get('restored') is not True or state.get('restoreErrors')):
            raise ValueError('Shared native completion, scenario identity and restoration required')
        checks = m.read(Path(run) / 'result.json').get('checks', []) if run else []
        with self.connect() as con:
            con.execute("UPDATE game_sessions SET status='finalizing' WHERE id=?", (session_id,))
        for job in reversed(request['orderIds']):
            # Anchor finishes last; the session barrier also protects a crash here.
            if self.get(job)['packet']:
                self.verify_packet(self.get(job))
                continue
            member = next((x for x in plan['members'] if x['orderId'] == job), None) if plan else None
            selected = [c for c in checks if member and c.get('name') in member['checkNames']]
            complete = bool(member) and len(selected) == len(member['checkNames']) and len({c['name'] for c in selected}) == len(selected)
            if not run:
                outcome, note = 'blocked', reason or 'Shared preparation refused'
            elif complete and all(c.get('result') == 'passed' for c in selected):
                outcome, note = 'passed', 'Member checks completed; shared session restored'
            else:
                outcome, note = 'failed', state.get('reason', 'Shared session stopped before member checks completed')
            folder = self.evidence_dir(job)
            ref = {'id': session_id, 'anchorOrderId': request['orderIds'][0], 'checkNames': member['checkNames'] if member else {}, 'memberComplete': complete}
            if plan:
                path = self.local / 'sessions' / session_id / 'session-plan.json'
                ref.update({'path': str(path), 'sha256': m.digest(path)})
            m.write(folder / 'shared-session.json', ref)
            self.finish(job, outcome, note, run, True if run else None, _shared=True)
        with self.connect() as con:
            con.execute("UPDATE game_sessions SET status='complete',note=? WHERE id=?", (reason or '', session_id))
        return {'sessionId': session_id, 'status': 'complete', 'orderIds': request['orderIds']}

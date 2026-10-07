"""Tooling-only continuation tickets, separate from immutable subject orders."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import sys
import time


def api():
    import polygon
    return polygon


class ToolingRetries:
    def init_retries(self):
        with self.connect() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS retry_attempts (
              id TEXT PRIMARY KEY, order_id TEXT NOT NULL, request TEXT NOT NULL,
              created REAL NOT NULL, status TEXT NOT NULL, packet TEXT,
              report TEXT, report_request TEXT, report_sha TEXT, receipt TEXT);
            CREATE UNIQUE INDEX IF NOT EXISTS one_retry_owner ON retry_attempts((1))
              WHERE status IN ('running','collecting');
            CREATE UNIQUE INDEX IF NOT EXISTS one_pending_retry_per_subject ON retry_attempts(order_id)
              WHERE status IN ('queued','running','collecting');
            """)

    def retry_show(self, attempt_id):
        with self.connect() as con:
            row = con.execute('SELECT * FROM retry_attempts WHERE id=?', (attempt_id,)).fetchone()
        if not row:
            raise ValueError('Unknown tooling retry attempt')
        return dict(row)

    def retry_order(self, row):
        return json.loads(self.get(row['order_id'])['request'])

    @staticmethod
    def checked_pin(pin):
        m = api()
        path = Path(m.required_string(pin, 'path')).resolve()
        if not m.SHA.fullmatch(pin.get('sha256', '')) or m.digest(path) != pin['sha256']:
            raise ValueError('Retry evidence/authority/platform pin changed')
        return path

    def retry_authority(self, ticket):
        m = api()
        path = self.checked_pin(ticket['ownerAuthority'])
        authority = m.read(path)
        m.owner_evidence(copy.deepcopy(authority), path, require_deadline=False)
        if authority.get('state', 'active') != 'active':
            raise ValueError('Retry owner authority is not active')
        ids = authority.get('orderIds', [x.get('id') for x in authority.get('roster', [])])
        if ticket['orderId'] not in ids:
            raise ValueError('Retry order is outside owner-authorized scope')
        # An explicit accountable review is necessary; hashes do not establish human permission.
        review = ticket['authorityReview']
        if review.get('retryPermitted') is not True or type(review.get('maxAdditionalAttempts')) is not int or review['maxAdditionalAttempts'] != 1:
            raise ValueError('Verify owner permission for this one additional tooling attempt')
        for key in ('verifiedBy', 'reason'):
            m.required_string(review, key)
        if type(review.get('cumulativeActualLaunchesBefore')) is not int or review['cumulativeActualLaunchesBefore'] < 0:
            raise ValueError('Retain reviewed cumulative launch accounting')
        if str(self.checked_pin(ticket['platform'])) != str(Path(self.host()['platformManifest']).resolve()):
            raise ValueError('Retry must use the reviewed current qualified platform')

    def retry_predecessor(self, ticket):
        m = api()
        original = self.get(ticket['orderId'])
        order = json.loads(original['request'])
        if order['schemaVersion'] != 2 or order['mode'] != 'automatic' or order.get('cycle'):
            raise ValueError('Tooling retry supports schema2 standard automatic subjects; cycle slots remain unchanged')
        previous = ticket.get('previousAttemptId')
        if previous:
            row = self.retry_show(previous)
            if row['order_id'] != ticket['orderId'] or row['status'] not in ('recorded', 'blocked'):
                raise ValueError("Retry predecessor must be this subject's ended attempt")
            path = row['packet']
            packet = self.verify_retry_packet(row)
        else:
            if original['status'] not in ('recorded', 'blocked') or not original['packet']:
                raise ValueError('Preserve an ended original packet before registering tooling continuation')
            _, packet = self.verify_packet(original)
            path = original['packet']
            session = self.member_session(order['id'])
            if session and session['status'] != 'complete':
                raise ValueError('Restore and finalize the previous shared session first')
        if m.digest(path) != ticket['previousPacketSha256'] or packet['executionOutcome'] not in ('failed', 'blocked'):
            raise ValueError('Retry predecessor packet/hash is not an ended failed attempt')
        if packet.get('subjectOrderSha256') != m.subject_contract.identity(order):
            raise ValueError('Original subject specification changed since predecessor packet')
        projection = self.test_projection(order, packet)
        if not projection['startContractAvailable'] or projection['testingStarted']:
            raise ValueError('Tooling-only continuation requires proven pre-subject abort')
        abort = m.read(self.checked_pin(ticket['technicalAbort']))
        if (abort.get('orderId') != order['id'] or abort.get('classification') != 'confirmed-tooling-pretest-abort'
            or abort.get('subjectStarted') is not False or abort.get('done') is not True or abort.get('restored') is not True
            or abort.get('restoreErrors') or abort.get('packetSha256') != ticket['previousPacketSha256']):
            raise ValueError('Reviewed technical abort must bind exact pre-subject packet and restoration')
        if previous and abort.get('attemptId') != previous:
            raise ValueError('Technical abort must identify the previous retry attempt')
        m.required_string(abort, 'reason')
        run = packet.get('runDirectory')
        if run:
            state_path = Path(run) / 'state.json'
            if not any(Path(x['path']).resolve() == state_path.resolve() for x in packet['files']):
                raise ValueError('Native predecessor completion is not hash-pinned')
            state = m.read(state_path)
            expected = previous or packet.get('sharedSession', {}).get('anchorOrderId', order['id'])
            if (state.get('order', {}).get('id') != expected or state.get('done') is not True or state.get('restored') is not True
                or state.get('restoreErrors') or packet.get('restored') is not True or Path(abort.get('run', '')).resolve() != Path(run).resolve()):
                raise ValueError('Native predecessor restoration/identity not proven')
        else:
            # Without a native run, no runner dispatch may be inferred as restored.
            if abort.get('actualGameLaunches') != 0 or packet.get('restored') not in (None, True):
                raise ValueError('Pre-session refusal requires explicit zero-launch review')
        self.verify_inputs(order)
        return order

    def register_retry(self, path):
        m = api()
        ticket = m.read(path)
        required = {'schemaVersion', 'id', 'orderId', 'previousPacketSha256', 'technicalAbort', 'ownerAuthority', 'authorityReview', 'platform'}
        if set(ticket) - (required | {'previousAttemptId'}) or not required <= set(ticket) or ticket['schemaVersion'] != 1:
            raise ValueError('Invalid tooling continuation ticket')
        for key in ('id', 'orderId'):
            if not m.SAFE_ID.fullmatch(m.required_string(ticket, key)):
                raise ValueError('Safe subject/attempt ids required')
        if ticket['id'] == ticket['orderId']:
            raise ValueError('Attempt identity must differ from immutable subject order')
        # Paths in a ticket resolve from that file, not the current shell directory.
        for key in ('technicalAbort', 'ownerAuthority', 'platform'):
            pin = ticket[key]
            pin['path'] = str((Path(path).resolve().parent / m.required_string(pin, 'path')).resolve())
        canonical = json.dumps(ticket, sort_keys=True, ensure_ascii=False)
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT request FROM retry_attempts WHERE id=?', (ticket['id'],)).fetchone()
            if old:
                if old['request'] != canonical:
                    raise ValueError('Retry attempt id is immutable')
                return {'id': ticket['id'], 'duplicate': True}
            if con.execute('SELECT id FROM jobs WHERE id=?', (ticket['id'],)).fetchone():
                raise ValueError('Retry id conflicts with an existing subject order')
            self.retry_authority(ticket)
            order = self.retry_predecessor(ticket)
            latest = con.execute('SELECT id,status FROM retry_attempts WHERE order_id=? ORDER BY created DESC,id DESC LIMIT 1', (order['id'],)).fetchone()
            if (latest and (latest['id'] != ticket.get('previousAttemptId') or latest['status'] not in ('recorded', 'blocked'))) or (not latest and ticket.get('previousAttemptId')):
                raise ValueError('Tooling attempts form one ended, nonbranching chain')
            con.execute("INSERT INTO retry_attempts(id,order_id,request,created,status) VALUES(?,?,?,?,'queued')", (ticket['id'], order['id'], canonical, time.time()))
            self.event(con, ticket['id'], 'tooling_retry_registered', 'Immutable subject ' + order['id'])
        return {'id': ticket['id'], 'orderId': order['id'], 'status': 'queued'}

    def claim_retry(self):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            if (con.execute('SELECT id FROM pipeline_holds').fetchone() or
                con.execute("SELECT id FROM jobs WHERE status='running'").fetchone() or
                con.execute("SELECT id FROM game_sessions WHERE status IN ('preparing','running','finalizing')").fetchone() or
                con.execute("SELECT id FROM retry_attempts WHERE status IN ('running','collecting')").fetchone() or
                con.execute("SELECT id FROM cycle_slots WHERE status IN ('reserved','blocked')").fetchone()):
                return None
            row = con.execute("SELECT * FROM retry_attempts WHERE status='queued' ORDER BY created,id LIMIT 1").fetchone()
            if not row:
                return None
            if con.execute("SELECT id FROM jobs WHERE status='queued' AND submitted < ? AND (id IN (SELECT id FROM released_orders) OR json_extract(request,'$.cycle') IS NOT NULL)", (row['created'],)).fetchone():
                return None
            con.execute("UPDATE retry_attempts SET status='running' WHERE id=?", (row['id'],))
        return dict(row)

    def retry_runs(self, row):
        m = api()
        order = self.retry_order(row)
        with self.connect() as con:
            if not con.execute('SELECT id FROM platform_attempts WHERE id=?', (row['id'],)).fetchone():
                return []
        plan = self.attempt_plan(order, row['id'])
        return [(p, m.read(p)) for p in (Path(plan['configuration']['runtime']) / 'runs').glob('*/state.json') if m.read(p).get('order', {}).get('id') == row['id']]

    def child_retry(self, attempt_id):
        m = api()
        row = self.retry_show(attempt_id)
        if row['status'] != 'running':
            raise ValueError('No active tooling retry claim')
        ticket = json.loads(row['request'])
        self.retry_authority(ticket)
        order = self.retry_predecessor(ticket)
        plan = self.verify_platform(order, attempt_id=attempt_id)
        folder = self.local / 'retry-attempts' / attempt_id
        if m.read(folder / 'config.json') != plan['configuration'] or m.read(folder / 'scenario.json') != plan['scenario']:
            raise ValueError('Materialized retry plan changed')
        with self.connect() as con:
            if (con.execute('SELECT id FROM pipeline_holds').fetchone() or
                con.execute("SELECT id FROM jobs WHERE status='running'").fetchone() or
                con.execute("SELECT id FROM cycle_slots WHERE status IN ('reserved','blocked')").fetchone()):
                raise ValueError('Another owner/hold blocks retry dispatch')
        self.executor()
        from skyrim_autotest import runner
        from skyrim_autotest.config import load
        runner.configure(load(folder / 'config.json'))
        profile = self.source_profile(order, runner, output_dir=folder)
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            if con.execute('SELECT status FROM retry_attempts WHERE id=?', (attempt_id,)).fetchone()[0] != 'running':
                raise ValueError('Retry ownership changed before native dispatch')
            con.execute('INSERT INTO attempts VALUES(?,?)', (attempt_id, time.time()))
        return runner.run(profile, folder / 'scenario.json', restart_idle_mo2=True,
                          order={'id': attempt_id, 'subjectOrderId': order['id'], 'owner': order['sourceChat']})

    def execute_retry(self, row):
        m = api()
        attempt_id = row['id']
        ticket = json.loads(row['request'])
        folder = self.local / 'retry-attempts' / attempt_id
        m.write(folder / 'attempt-request.json', ticket)
        try:
            self.retry_authority(ticket)
            order = self.retry_predecessor(ticket)
            plan = self.prepare_platform(order, attempt_id=attempt_id)
            m.write(folder / 'config.json', plan['configuration'])
            m.write(folder / 'scenario.json', plan['scenario'])
        except (ValueError, OSError) as error:
            return self.finish_retry(attempt_id, reason=str(error))
        with (folder / 'executor.log').open('w', encoding='utf-8') as log:
            child = subprocess.run([sys.executable, str(Path(__file__).with_name('polygon.py')), '--root', str(self.root), '_execute-retry', attempt_id], stdout=log, stderr=subprocess.STDOUT, shell=False)
        m.write(folder / 'child-exit.json', {'returncode': child.returncode})
        self.reconcile_retries()
        current = self.retry_show(attempt_id)
        if current['packet']:
            return m.read(current['packet'])
        if child.returncode == 2 and not self.retry_runs(current):
            return self.finish_retry(attempt_id, reason='Executor refused before a recorded retry game session')
        return {'attemptId': attempt_id, 'status': 'running', 'reason': 'Recovery/evidence reconciliation required; no automatic repeat'}

    def finish_retry(self, attempt_id, run=None, reason=None):
        m = api()
        row = self.retry_show(attempt_id)
        if row['packet']:
            return self.verify_retry_packet(row)
        order = self.retry_order(row)
        folder = self.local / 'retry-attempts' / attempt_id
        folder.mkdir(parents=True, exist_ok=True)
        state = m.read(Path(run) / 'state.json') if run else {}
        if run and (state.get('order', {}).get('id') != attempt_id or state.get('done') is not True
                    or state.get('restored') is not True or state.get('restoreErrors')
                    or state.get('scenarioHash') != m.digest(folder / 'scenario.json')):
            raise ValueError('Retry native completion/scenario/restoration not proven')
        outcome = state.get('result', 'failed') if run else 'blocked'
        note = state.get('reason', '') if run else reason or 'Retry preparation refused'
        findings = self.collection_findings(run)
        if findings:
            self.hold_pipeline(attempt_id, 'Retry evidence collection incomplete; tooling review required')
        if run:
            try:
                self.verify_platform(order, attempt_id=attempt_id)
            except (ValueError, OSError) as error:
                findings.append({'component': 'platform', 'kind': 'changed_build', 'details': str(error), 'confirmed': True})
                self.hold_pipeline(attempt_id, 'Retry platform drift requires review')
        m.write(folder / 'execution-summary.json', self.execution_summary(order, run, outcome, note))
        m.write(folder / 'self-checks.json', {'findings': findings, 'subjectAnalysis': None})
        files = []
        for directory in [folder] + ([Path(run)] if run else []):
            for path in directory.iterdir():
                if path.is_file() and path.name != 'packet.json' and path.suffix in ('.json', '.jsonl', '.log'):
                    files.append({'path': str(path), 'sha256': m.digest(path), 'bytes': path.stat().st_size})
        if run:
            files.extend(m.raw_evidence_pins(run))
        packet = {'schemaVersion': 1, 'attemptId': attempt_id, 'orderId': order['id'], 'mode': 'automatic',
                  'sourceChat': order['sourceChat'], 'sourceThreadId': order['sourceThreadId'], 'subject': order['subject'],
                  'executionOutcome': outcome, 'reason': note, 'runDirectory': str(run) if run else None,
                  'restored': True if run else None, 'files': files, 'requestedData': order['collect'], 'analysis': None,
                  'subjectOrderSha256': m.subject_contract.identity(order), 'finishedAt': time.time(),
                  'previousPacketSha256': json.loads(row['request'])['previousPacketSha256']}
        path = folder / 'packet.json'
        m.write(path, packet)
        with self.connect() as con:
            con.execute('UPDATE retry_attempts SET status=?,packet=? WHERE id=?', ('blocked' if not run else 'recorded', str(path), attempt_id))
            self.event(con, attempt_id, 'tooling_retry_ended', note)
        return packet

    def verify_retry_packet(self, row):
        m = api()
        if not row['packet']:
            raise ValueError('Retry packet not ready')
        order = self.retry_order(row)
        _, packet = self.verify_packet({'id': order['id'], 'request': json.dumps(order), 'packet': row['packet']})
        if packet.get('attemptId') != row['id'] or packet.get('subjectOrderSha256') != m.subject_contract.identity(order) or packet.get('previousPacketSha256') != json.loads(row['request'])['previousPacketSha256']:
            raise ValueError('Retry subject/attempt identity mismatch')
        return packet

    def reconcile_retries(self):
        result = []
        with self.connect() as con:
            rows = con.execute("SELECT * FROM retry_attempts WHERE status IN ('running','collecting')").fetchall()
        for row in rows:
            runs = self.retry_runs(row)
            if len(runs) > 1:
                raise ValueError('Multiple native executions for one tooling attempt')
            if runs and runs[0][1].get('done'):
                path, state = runs[0]
                if state.get('restored') is not True or state.get('restoreErrors'):
                    self.hold_pipeline(row['id'], 'Retry restoration requires native recovery')
                    continue
                self.finish_retry(row['id'], path.parent)
                result.append(row['id'])
        return result

    def recover_retry(self, row):
        m = api()
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            attempt = con.execute('SELECT id FROM attempts WHERE id=?', (row['id'],)).fetchone()
            if not attempt:
                # Serialize with the child's final ownership check before runner.run.
                con.execute("UPDATE retry_attempts SET status='collecting' WHERE id=?", (row['id'],))
        if not attempt:
            return self.finish_retry(row['id'], reason='Interrupted during retry preparation; no dispatch')
        if not self.retry_runs(row) and not (self.local / 'retry-attempts' / row['id'] / 'child-exit.json').is_file():
            return {'status': 'worker_completion_unproven', 'reason': 'Dispatched child may still start; retain barrier until worker/run evidence is available'}
        frozen = self.attempt_plan(self.retry_order(row), row['id'])
        child = subprocess.run([sys.executable, str(Path(frozen['executor']) / 'run.py'), '--config', str(self.local / 'retry-attempts' / row['id'] / 'config.json'), 'recover'], capture_output=True, text=True)
        if child.returncode:
            return {'status': 'recovery_refused', 'output': child.stdout, 'error': child.stderr}
        recovered = self.reconcile_retries()
        if not recovered and not self.retry_runs(row):
            self.finish_retry(row['id'], reason='Interrupted before a recorded retry game session')
        return {'reconciled': recovered}

    def retry_notification_ready(self, order):
        with self.connect() as con:
            for row in con.execute("SELECT * FROM jobs WHERE status IN ('running','queued','session_waiting')"):
                other = json.loads(row['request'])
                if ((other['sourceChat'], other['sourceThreadId']) == (order['sourceChat'], order['sourceThreadId'])
                    and (row['status'] in ('running','session_waiting') or other.get('cycle') or
                         con.execute('SELECT id FROM released_orders WHERE id=?', (row['id'],)).fetchone())):
                    raise ValueError('Origin testing work is still pending; retry notification deferred')

    def retry_report_ready(self, path):
        m = api()
        request = m.read(path)
        if request.get('schemaVersion') != 1 or not m.SAFE_ID.fullmatch(request.get('id', '')) or request.get('collectionFinished') is not True:
            raise ValueError('Retry final report needs identity and completed collection')
        m.required_string(request, 'summary')
        row = self.retry_show(request['attemptId'])
        canonical = json.dumps(request, sort_keys=True, ensure_ascii=False)
        if row['report']:
            if row['report_request'] != canonical:
                raise ValueError('Retry final report is immutable')
            self.verify_retry_report(row)
            return {'id': request['id'], 'duplicate': True, 'report': row['report']}
        if row['status'] not in ('recorded', 'blocked'):
            raise ValueError('Finish retry before finalizing its report')
        order = self.retry_order(row)
        self.retry_notification_ready(order)
        packet = self.verify_retry_packet(row)
        run = packet.get('runDirectory')
        if run:
            state = m.read(Path(run) / 'state.json')
            if state.get('order', {}).get('id') != row['id'] or state.get('done') is not True or state.get('restored') is not True or state.get('restoreErrors'):
                raise ValueError('Retry completion and restoration required')
        projection = self.test_projection(order, packet)
        self_checks = self.local / 'retry-attempts' / row['id'] / 'self-checks.json'
        if self_checks.is_file() and m.read(self_checks).get('findings') and projection['testingStarted']:
            projection['interruptionObserved'] = True
            if projection['outcome'] != 'tested_with_errors':
                projection['outcome'] = 'interrupted_external'
        supplied = request.get('dataCoverage', [])
        if supplied:
            if not isinstance(supplied, list) or {d.get('name') for d in supplied} != set(order['collect']) or len(supplied) != len(order['collect']):
                raise ValueError('Assess all requested retry collection data exactly once')
            for item in supplied:
                if item.get('status') not in ('collected', 'unavailable', 'not_collected'):
                    raise ValueError('Invalid retry data coverage')
                if item['status'] == 'collected' and (not item.get('evidence') or any(not any(e['path'] == pin.get('path') and e['sha256'] == pin.get('sha256') for e in packet['files']) for pin in item['evidence'])):
                    raise ValueError('Retry collection references must be hash-pinned packet evidence')
            projection['requestedData'] = supplied
        if projection['outcome'] == 'tested_successfully' and not all(x['status'] == 'collected' for x in projection['requestedData']):
            projection['outcome'] = 'incomplete'
        report = {'schemaVersion': 1, 'id': request['id'], 'attemptId': row['id'], 'orderId': order['id'],
                  'sourceChat': order['sourceChat'], 'sourceThreadId': order['sourceThreadId'],
                  'summary': request['summary'], 'collectionFinished': True, 'packet': row['packet'],
                  'packetSha256': m.digest(row['packet']), 'testResult': projection,
                  'eligibility': 'eligible' if projection['testingStarted'] else 'suppressed'}
        target = self.local / 'final-reports' / request['id'] / 'report.json'
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            current = con.execute('SELECT report FROM retry_attempts WHERE id=?', (row['id'],)).fetchone()
            if current['report'] or target.exists():
                raise ValueError('Final report already registered or unregistered file exists')
            m.write(target, report)
            con.execute('UPDATE retry_attempts SET report=?,report_request=?,report_sha=? WHERE id=?', (str(target), canonical, m.digest(target), row['id']))
        return {'id': request['id'], 'report': str(target), 'eligibility': report['eligibility']}

    def verify_retry_report(self, row):
        m = api()
        if not row['report'] or m.digest(row['report']) != row['report_sha']:
            raise ValueError('Retry final report hash mismatch')
        report = m.read(row['report'])
        self.verify_retry_packet(row)
        if report['packetSha256'] != m.digest(row['packet']):
            raise ValueError('Retry final packet hash mismatch')
        return report

    def pending_retries(self):
        m = api()
        with self.connect() as con:
            rows = con.execute("SELECT * FROM retry_attempts WHERE report IS NOT NULL AND receipt IS NULL ORDER BY created,id").fetchall()
        result = []
        for row in rows:
            report = self.verify_retry_report(row)
            if report['eligibility'] != 'eligible':
                continue
            try:
                self.retry_notification_ready(self.retry_order(row))
            except ValueError:
                continue
            result.append({'orderId': row['order_id'], 'attemptId': row['id'], 'threadId': report['sourceThreadId'],
                           'sourceChat': report['sourceChat'], 'packet': row['packet'], 'packetSha256': report['packetSha256'],
                           'report': row['report'], 'reportSha256': row['report_sha'], 'testOutcome': report['testResult']['outcome'],
                           'text': f"Skyrim-Polygon order {row['order_id']}, attempt {row['id']}: {report['testResult']['outcome']}. Completed report: {row['report']}. Analyze this attempt once; original order and prior evidence remain unchanged."})
        return result

    def retry_delivered(self, attempt_id, receipt):
        if not isinstance(receipt, str) or not receipt.strip():
            raise ValueError('Exact-origin verified app receipt required')
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM retry_attempts WHERE id=?', (attempt_id,)).fetchone()
            if row['receipt']:
                return {'id': attempt_id, 'duplicate': True}
            report = self.verify_retry_report(row)
            self.retry_notification_ready(self.retry_order(row))
            if report['eligibility'] != 'eligible':
                raise ValueError('Pre-subject retry abort cannot notify an origin')
            con.execute('UPDATE retry_attempts SET receipt=? WHERE id=?', (receipt, attempt_id))
        return {'id': attempt_id, 'delivered': True}

    def retry_board(self):
        with self.connect() as con:
            rows = con.execute('SELECT * FROM retry_attempts ORDER BY created DESC,id DESC').fetchall()
        result = []
        for row in rows:
            order = self.retry_order(row)
            report = self.verify_retry_report(row) if row['report'] else None
            projection = report['testResult'] if report else None
            result.append({'id': row['id'], 'subjectOrderId': order['id'], 'attemptKind': 'tooling_retry',
                           'subject': order['subject'], 'mode': 'automatic', 'workflow': 'standard',
                           'origin': order['sourceChat'], 'status': 'delivered' if row['receipt'] else row['status'],
                           'submitted': row['created'], 'note': 'Tooling-only continuation; original evidence retained',
                           'packet': row['packet'], 'delivery': row['receipt'], 'awaitingOwnerStart': False,
                           'testingLifecycle': 'completed' if projection and projection['testingStarted'] else 'not_started',
                           'testOutcome': projection['outcome'] if projection else None,
                           'coverage': projection['coverage'] if projection else None,
                           'auxiliaryCoverage': projection.get('auxiliaryCoverage') if projection else None,
                           'notificationEligibility': report['eligibility'] if report else None})
        return result

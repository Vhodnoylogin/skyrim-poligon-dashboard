"""Explicit one-shot owner workflow, independent of immutable mod specifications."""
import json
from pathlib import Path


def api():
    import polygon
    return polygon


class AutotestWorkflow:
    def init_autotest_workflow(self):
        with self.connect() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS autotest_receipts (
                order_id TEXT NOT NULL, recipient TEXT NOT NULL, thread_id TEXT NOT NULL,
                report_sha TEXT NOT NULL, receipt TEXT NOT NULL,
                PRIMARY KEY(order_id,recipient))''')

    @staticmethod
    def autotest_approval(con, job):
        row = con.execute('''SELECT authorization FROM releases JOIN released_orders
                            ON releases.id=release_id WHERE released_orders.id=?''', (job,)).fetchone()
        approval = json.loads(row['authorization']) if row else {}
        return approval if approval.get('workflow') == 'autotest' else None

    def autotest_messages(self, con, row):
        """Read verified final evidence only. No messages or launch side effects here."""
        m = api()
        approval = self.autotest_approval(con, row['id'])
        if not approval:
            return []
        decision = con.execute('SELECT * FROM notification_results WHERE id=?', (row['id'],)).fetchone()
        if not decision:
            return []
        registered = con.execute('SELECT * FROM final_reports WHERE id=?', (decision['report_id'],)).fetchone()
        report = self.verify_final_report(con, registered)
        entry = next(e for e in report['orders'] if e['orderId'] == row['id'])
        order, packet = self.verify_packet(row)
        result = entry['testResult']
        if report.get('collectionFinished') is not True or row['status'] not in ('recorded', 'blocked', 'delivered'):
            raise ValueError('Autotest must finish collection and final report first')
        if result.get('testingStarted') is not True:
            return []
        # Hashes prove bytes, not semantic classification. Only pinned technical facts route repair.
        path = self.evidence_dir(row['id']) / 'self-checks.json'
        findings = m.read(path).get('findings', []) if any(
            Path(p['path']).resolve() == path.resolve() for p in packet['files']) else []
        technical = bool(findings) or result.get('interruptionObserved') is True
        mismatch = result.get('subjectMismatchObserved') is True
        success = result['outcome'] == 'tested_successfully' and not technical and not mismatch
        if technical:
            action = 'review_failed_attempt'
            instruction = ('Analyze this unsuccessful attempt. A tooling failure prevented reliable completion; '
                           'do not diagnose a mod defect from that failure or claim successful testing.')
            if mismatch:
                instruction += ' Also analyze the independently recorded subject mismatches.'
        elif mismatch:
            action = 'analyze_subject_errors'
            instruction = 'Analyze the recorded subject check errors and report findings to the owner.'
        elif success:
            action = 'analyze_successful_report'
            instruction = ('Analyze the successful report, required checks and requested evidence. '
                           'Then tell the owner that testing completed successfully if the report supports it.')
        else:
            action = 'analyze_incomplete_report'
            instruction = 'Analyze the incomplete or unstarted attempt; report missing evidence without claiming success.'
        base = {'orderId': row['id'], 'packet': row['packet'], 'packetSha256': m.digest(row['packet']),
                'report': registered['path'], 'reportSha256': registered['sha256'],
                'testOutcome': result['outcome'], 'testingStarted': result['testingStarted'],
                'workflow': 'autotest', 'attemptSuccessful': success}
        messages = [{**base, 'recipient': 'origin', 'threadId': order['sourceThreadId'],
                     'sourceChat': order['sourceChat'], 'action': action, 'instruction': instruction}]
        if technical:
            messages.append({**base, 'recipient': 'tooling', 'threadId': approval['toolThreadId'],
                             'sourceChat': 'skyrim-autotest', 'action': 'test_tooling',
                             'instruction': 'Analyze the tool failure, repair within existing scope and test the tooling. '
                                            'This message grants no mod repair cycle, live installation, hold clearance '
                                            'or repeated subject launch; use separately verified existing authority.'})
        for message in messages:
            message['notificationId'] = f"autotest:{row['id']}:{message['recipient']}"
            message['text'] = (f"Polygon autotest {row['id']}: {result['outcome']}. "
                               f"Completed report: {registered['path']}. {message.pop('instruction')} "
                               'Process this notification id/report hash once.')
        return messages

    def pending_autotests(self):
        result = []
        with self.connect() as con:
            for row in con.execute("SELECT * FROM jobs WHERE status IN ('recorded','blocked','delivered') ORDER BY submitted").fetchall():
                for message in self.autotest_messages(con, row):
                    receipt = con.execute('SELECT * FROM autotest_receipts WHERE order_id=? AND recipient=?',
                                          (row['id'], message['recipient'])).fetchone()
                    if receipt:
                        if (receipt['thread_id'], receipt['report_sha']) != (message['threadId'], message['reportSha256']):
                            raise ValueError('Autotest receipt target/report mismatch')
                        continue
                    result.append(message)
        return result

    def autotest_delivered(self, notification_id, receipt):
        """A receipt for one exact target never acknowledges the other target."""
        parts = notification_id.split(':')
        if len(parts) != 3 or parts[0] != 'autotest' or parts[2] not in ('origin', 'tooling'):
            raise ValueError('Invalid autotest notification id')
        job, recipient = parts[1:]
        if not isinstance(receipt, str) or not receipt.strip():
            raise ValueError('Structured exact-target app receipt required')
        try:
            evidence = json.loads(receipt)
        except ValueError as error:
            raise ValueError('Structured exact-target app receipt required') from error
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM jobs WHERE id=?', (job,)).fetchone()
            message = next((e for e in self.autotest_messages(con, row) if e['recipient'] == recipient), None) if row else None
            if not message:
                raise ValueError('No finalized autotest notification for this target')
            if (not isinstance(evidence, dict) or not isinstance(evidence.get('messageId'), str) or not evidence['messageId'].strip()
                    or any(evidence.get(k) != message[k] for k in ('notificationId', 'threadId', 'reportSha256'))):
                raise ValueError('Autotest receipt must match notification, exact target and report hash')
            existing = con.execute('SELECT * FROM autotest_receipts WHERE order_id=? AND recipient=?', (job, recipient)).fetchone()
            if existing:
                if (existing['thread_id'], existing['report_sha']) != (message['threadId'], message['reportSha256']):
                    raise ValueError('Autotest receipt target/report mismatch')
                return {'id': notification_id, 'duplicate': True}
            con.execute('INSERT INTO autotest_receipts VALUES(?,?,?,?,?)',
                        (job, recipient, message['threadId'], message['reportSha256'], receipt))
            if recipient == 'origin':
                con.execute("UPDATE jobs SET status='delivered',delivery=? WHERE id=?", (receipt, job))
            self.event(con, job, 'autotest_' + recipient + '_delivered', receipt)
        return {'id': notification_id, 'delivered': True}

"""Reviewed full replays after a proven post-start tooling failure, never resume checkpoints."""
import json
import hashlib
from pathlib import Path


def api():
    import polygon
    return polygon


class PostStartContinuations:
    def register_continuation(self, path):
        return self._register_retry(path, post_start=True)

    def freeze_continuation_review(self, ticket, folder):
        """Retain dispatch-time review bytes even if authority is later cancelled."""
        m = api()
        for key in ('technicalFailure', 'previousReport', 'launchAccounting', 'ownerAuthority', 'platform'):
            data = self.checked_pin(ticket[key]).read_bytes()
            if hashlib.sha256(data).hexdigest() != ticket[key]['sha256']:
                raise ValueError('Continuation proof changed while freezing')
            value = {'source': ticket[key], 'documentText': data.decode('utf-8')}
            target = folder / ('review-' + key + '.json')
            if target.exists():
                if m.read(target) != value:
                    raise ValueError('Frozen continuation review is immutable')
            else:
                m.write(target, value)

    def verify_continuation_review(self, ticket, folder, pinned_paths=None):
        m = api()
        for key in ('technicalFailure', 'previousReport', 'launchAccounting', 'ownerAuthority', 'platform'):
            path = folder / ('review-' + key + '.json')
            if not path.is_file() or (pinned_paths is not None and path.resolve() not in pinned_paths):
                raise ValueError('Pinned dispatch-time continuation review is missing or mismatched')
            value = m.read(path)
            if (value.get('source') != ticket[key] or not isinstance(value.get('documentText'), str)
                    or hashlib.sha256(value['documentText'].encode('utf-8')).hexdigest() != ticket[key]['sha256']):
                raise ValueError('Frozen continuation review bytes do not match approved proof')

    @staticmethod
    def native_game_starts(state):
        """Count distinct captured game processes, not dispatches or loader launches."""
        identities = set()
        for item in state.get('owned', []):
            if item.get('role') != 'game':
                continue
            identity = item.get('identity', {})
            if (type(identity.get('pid')) is not int or identity['pid'] <= 0
                    or type(identity.get('birth')) is not int or identity['birth'] <= 0
                    or not isinstance(identity.get('path'), str) or not identity['path'].strip()):
                raise ValueError('Physical game launch identity is unproven')
            identities.add((identity['pid'], identity['birth'], identity['path'].casefold()))
        game = state.get('game') or {}
        current = (game.get('pid'), game.get('birth'), str(game.get('path', '')).casefold())
        restarts = state.get('ownedGameRestartCount', 0)
        if (not identities or current not in identities or type(restarts) is not int
                or restarts < 0 or len(identities) != restarts + 1):
            raise ValueError('Physical game launch/restart accounting is unproven')
        return len(identities)

    def continuation_authority(self, ticket, authority):
        review = ticket['authorityReview']
        if (ticket.get('restartMode') != 'initial-fixture'
                or authority.get('state') != 'active'
                or any(review.get(k) is not True for k in
                       ('postStartContinuationPermitted', 'fullReplayReviewed', 'preservePriorCoverage'))):
            raise ValueError('Explicit active authority and reviewed full post-start replay required')

    def continuation_predecessor(self, ticket, order, packet, previous, projection):
        m = api()
        if not projection['startContractAvailable'] or projection['testingStarted'] is not True:
            raise ValueError('Post-start continuation needs proven factual subject start')
        if not packet.get('runDirectory'):
            raise ValueError('Post-start continuation requires native run evidence')
        # Require the already finalized predecessor, including delivered originals.
        report_path = self.checked_pin(ticket['previousReport'])
        with self.connect() as con:
            if previous:
                registered = self.retry_show(previous)
                if not registered['report'] or Path(registered['report']).resolve() != report_path:
                    raise ValueError('Continuation needs the registered predecessor final report')
                report = self.verify_retry_report(registered)
                entry = report
            else:
                registered = con.execute('''SELECT final_reports.* FROM final_reports JOIN notification_results
                                            ON final_reports.id=notification_results.report_id WHERE notification_results.id=?''',
                                         (order['id'],)).fetchone()
                if not registered or Path(registered['path']).resolve() != report_path:
                    raise ValueError('Continuation needs the registered predecessor final report')
                report = self.verify_final_report(con, registered)
                entry = next(e for e in report['orders'] if e['orderId'] == order['id'])
        if (report.get('collectionFinished') is not True
                or entry['packetSha256'] != ticket['previousPacketSha256']
                or entry['testResult'].get('testingStarted') is not True):
            raise ValueError('Predecessor report must prove ended collection and factual testing start')
        proof = m.read(self.checked_pin(ticket['technicalFailure']))
        if (proof.get('schemaVersion') != 1 or proof.get('classification') != 'confirmed-tooling-post-start-failure'
                or proof.get('orderId') != order['id'] or proof.get('subjectStarted') is not True
                or proof.get('done') is not True or proof.get('restored') is not True or proof.get('restoreErrors')
                or proof.get('collectionFinished') is not True
                or proof.get('packetSha256') != ticket['previousPacketSha256']
                or proof.get('reportSha256') != ticket['previousReport']['sha256']
                or proof.get('attemptId') != previous):
            raise ValueError('Reviewed post-start tooling failure must bind exact packet/report/restoration')
        for key in ('reason', 'verifiedBy'):
            m.required_string(proof, key)
        run = Path(packet['runDirectory'])
        native = {Path(p['path']).resolve(): p['sha256'] for p in packet['files']}
        evidence = proof.get('evidence')
        if not isinstance(evidence, list) or not evidence:
            raise ValueError('Reviewed tool failure needs pinned native evidence')
        reviewed = set()
        for pin in evidence:
            path = self.checked_pin(pin)
            if native.get(path) != pin['sha256']:
                raise ValueError('Tool failure evidence must belong to predecessor packet')
            reviewed.add(path)
        required = {(run / name).resolve() for name in ('state.json', 'result.json')}
        if not required <= reviewed:
            raise ValueError('Review both pinned native state and result')
        # A label or a failed subject assertion alone cannot qualify as a tooling failure.
        failure = proof.get('failedCheck')
        raw = m.read(run / 'result.json')
        request_failure = (isinstance(failure, dict) and set(failure) == {'name', 'reason'}
                           and isinstance(failure['reason'], str) and failure['reason'].startswith('Tool request failed:')
                           and sum(c.get('name') == failure['name'] and c.get('reason') == failure['reason']
                                   and c.get('result') == 'failed' and c.get('observation') is None
                                   for c in raw.get('checks', [])) == 1)
        if not projection.get('interruptionObserved') and not request_failure:
            raise ValueError('No corroborated operational/tool request failure; subject failure alone is ineligible')
        accounting = m.read(self.checked_pin(ticket['launchAccounting']))
        state = m.read(run / 'state.json')
        starts = self.native_game_starts(state)
        baseline = ticket['authorityReview']['cumulativeActualLaunchesBefore']
        if (accounting.get('schemaVersion') != 1 or accounting.get('orderId') != order['id']
                or accounting.get('previousAttemptId') != previous
                or accounting.get('previousPacketSha256') != ticket['previousPacketSha256']
                or type(accounting.get('previousAttemptActualLaunches')) is not int
                or accounting['previousAttemptActualLaunches'] != starts
                or type(accounting.get('cumulativeActualLaunches')) is not int
                or accounting['cumulativeActualLaunches'] != baseline or baseline < starts):
            raise ValueError('Preserve reviewed cumulative physical launches and exact native predecessor starts')
        for key in ('verifiedBy', 'reason'):
            m.required_string(accounting, key)
        if previous:
            prior = json.loads(self.retry_show(previous)['request'])
            if baseline < prior['authorityReview']['cumulativeActualLaunchesBefore'] + starts:
                raise ValueError('Cumulative physical launch counter cannot reset across attempts')
        return proof

    def continuation_launch_accounting(self, ticket, run, attempt_id):
        m = api()
        baseline = ticket['authorityReview']['cumulativeActualLaunchesBefore']
        if run:
            starts = self.native_game_starts(m.read(Path(run) / 'state.json'))
        else:
            with self.connect() as con:
                if con.execute('SELECT id FROM attempts WHERE id=?', (attempt_id,)).fetchone():
                    raise ValueError('Dispatched continuation physical launch accounting is unproven; retain recovery barrier')
            starts = 0
        return {'cumulativeActualLaunchesBefore': baseline, 'attemptActualLaunches': starts,
                'cumulativeActualLaunchesAfter': baseline + starts,
                'source': 'pinned native distinct game identities and reviewed cumulative baseline'}

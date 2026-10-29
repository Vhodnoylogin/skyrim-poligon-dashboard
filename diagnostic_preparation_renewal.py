"""Retire one never-frozen preparation generation without reinstalling its payload.

This updates tool preparation, not the immutable subject or its reservation.  The
old request/cycle/source are retained byte-for-byte in a pinned certificate and
an append-only audit event.  It does not consume admission or launch a child.
"""
import copy
import json
from pathlib import Path

import diagnostic_admission as d
import diagnostic_recovery as r
import order_platform


def _next_request(certificate, certificate_pin):
    request = json.loads(certificate['previous']['diagnostic']['request'])
    review = certificate['review']
    request.update(ownerAuthorization=review['ownerAuthorization'],
                   deadlineUtc=review['deadlineUtc'],
                   dashboardPins=certificate['implementationPins'],
                   preparationRenewal=certificate_pin)
    additions = [certificate['reviewPin'], certificate_pin]
    if 'releasedWorkDeferral' in review:
        request['releasedWorkDeferral'] = review['releasedWorkDeferral']
        additions.append(review['releasedWorkDeferral'])
    request['reviewPins'] = [*request['reviewPins'], *additions]
    return request


def validate_request(request):
    certificate_pin = request['preparationRenewal']
    certificate = d.read_pin(certificate_pin)
    if (certificate.get('kind') != 'retired-unstarted-preparation-generation'
            or _next_request(certificate, certificate_pin) != request
            or d.read_pin(certificate['reviewPin']) != certificate['review']):
        raise ValueError('Preparation generation certificate changed')


def renew(p, path):
    review, review_pin = d.document(path)
    keys = {'schemaVersion', 'kind', 'id', 'diagnosticId', 'previousReview',
            'previousCycleAuthorizationSha256', 'ownerAuthorization',
            'deadlineUtc', 'verifiedBy', 'reason'}
    if (set(review) not in (keys, keys | {'releasedWorkDeferral'})
            or type(review['schemaVersion']) is not int or review['schemaVersion'] != 1
            or review['kind'] != 'diagnostic-preparation-renewal'
            or not d.api().SAFE_ID.fullmatch(review['id'])
            or not review['verifiedBy'] or not review['reason']):
        raise ValueError('Exact explicit preparation renewal required')
    # Idempotence cannot renew time, create a second generation or execute a run.
    with p.connect() as con:
        for row in con.execute("SELECT note FROM events WHERE status='diagnostic_preparation_renewed'"):
            old = json.loads(row['note'])
            if old['review']['id'] == review['id']:
                if old['review'] != review or old['reviewPin'] != review_pin:
                    raise ValueError('Preparation renewal identity is immutable')
                d.pin(old['certificate'])
                return {'id': review['id'], 'duplicate': True,
                        'launchGranted': False, 'newInstallationGranted': False}
    d.api().owner_evidence(review, Path(path))
    prior_review = d.read_pin(review['previousReview'])
    if prior_review.get('diagnosticId') != review['diagnosticId']:
        raise ValueError('Exact prior preparation review required')
    with p.connect() as con:
        request, snapshot = r._legacy(p, con, prior_review, 'preparing')
    r._source(request)  # Validate old source directly; do not execute or repin it.
    runner = order_platform.activate(request['executor'])
    with runner.native.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        current_request, current = r._legacy(p, con, prior_review, 'preparing')
        if current != snapshot or current_request != request:
            raise ValueError('Preparation changed before generation renewal')
        if (current['cycle']['status'] != 'active'
                or r._hash(current['cycle']['authorization']) != review['previousCycleAuthorizationSha256']):
            raise ValueError('Exact active prior cycle authorization required')
        # A pending cleanup transaction owns this state even if it has not moved
        # any file yet.  This API cannot adopt or steal that recovery lease.
        if r._table(con) and con.execute(
                'SELECT 1 FROM diagnostic_recoveries WHERE diagnostic_id=?',
                (review['diagnosticId'],)).fetchone():
            raise ValueError('Recovery already owns this preparation')
        d._barriers(p, request, con, own_slot=True)
        source = r._source(request)
        assessment, index_pin = r._assessment(prior_review, request, current['managedIni'])
        profiles = r._current(request, assessment, False)
        order = json.loads(current['job']['request'])
        p.verify_inputs(order)
        d._installation_receipt(request, order, d.read_pin(prior_review['installationReceipt']))
        d._installed(request, True); d._profile_after(request)
        approval = json.loads(current['cycle']['authorization'])
        approval.update(ownerAuthorization=copy.deepcopy(review['ownerAuthorization']),
                        deadlineUtc=review['deadlineUtc'])
        if request.get('releasedWorkDeferral'):
            if 'releasedWorkDeferral' not in review:
                raise ValueError('Renewed authority must preserve the reviewed released-work deferral')
            previous = d.read_pin(request['releasedWorkDeferral'])
            expected = copy.deepcopy(previous)
            expected.update(ownerAuthorization=copy.deepcopy(review['ownerAuthorization']),
                            deadlineUtc=review['deadlineUtc'])
            if d.read_pin(review['releasedWorkDeferral']) != expected:
                raise ValueError('Only authority/time may change in the retained deferral')
        elif 'releasedWorkDeferral' in review:
            raise ValueError('Renewal cannot create a new scheduling deferral')
        certificate = {'schemaVersion': 1,
            'kind': 'retired-unstarted-preparation-generation',
            'previous': current, 'review': review, 'reviewPin': review_pin,
            'previousSource': source, 'implementationPins': d.source_pins(),
            'profiles': profiles, 'preimageIndex': index_pin,
            'installationAssessment': assessment,
            'nativeIdle': d._native_closed(p, request, runner, con),
            'historicalPhysicalStartsPreserved': True,
            'subjectChanged': False, 'installationGranted': False,
            'launchGranted': False}
        # Failed transactions may leave a captured but unregistered certificate.
        # Retain it as evidence. A later fresh observation gets a distinct immutable
        # path instead of overwriting or adopting an unregistered older snapshot.
        content_id = r._hash(json.dumps(certificate, sort_keys=True, ensure_ascii=False))
        certificate_path = p.local / 'diagnostic-preparation-generations' / (review['id'] + '-' + content_id + '.json')
        if certificate_path.exists():
            if d.read_pin(d.file_pin(certificate_path)) != certificate:
                raise ValueError('Retained preparation generation certificate differs')
        else:
            d.api().write(certificate_path, certificate)
        certificate_pin = d.file_pin(certificate_path)
        renewed = _next_request(certificate, certificate_pin)
        # Validate using a private in-transaction policy replacement.  Any failed
        # check rolls it back; no independent unlocked policy window exists.
        con.execute('UPDATE cycles SET authorization=? WHERE id=?',
                    (json.dumps(approval, sort_keys=True, ensure_ascii=False), request['cycleId']))
        d._authority(p, renewed, con)
        d._request({'request': json.dumps(renewed, sort_keys=True)})
        d._native_closed(p, renewed, runner, con)
        if (r._current(request, assessment, False) != profiles
                or d.read_pin(review_pin) != review
                or d.read_pin(review['previousReview']) != prior_review):
            raise ValueError('Preparation inputs changed at renewal boundary')
        p.verify_inputs(order)
        d.pin(index_pin)
        d.api().owner_evidence(review, Path(path))
        # This is the same diagnostic allowance, subject, slot and accounting.
        # The old canonical request remains in the certificate and audit event.
        con.execute('UPDATE diagnostic_admissions SET request=? WHERE id=?',
                    (json.dumps(renewed, sort_keys=True), review['diagnosticId']))
        p.event(con, review['diagnosticId'], 'diagnostic_preparation_renewed',
                json.dumps({'review': review, 'reviewPin': review_pin,
                            'certificate': certificate_pin}, sort_keys=True))
    return {'id': review['id'], 'diagnosticId': review['diagnosticId'],
            'status': 'preparing', 'certificate': certificate_pin,
            'sameSubject': True, 'sameSlot': True, 'launchGranted': False,
            'newInstallationGranted': False, 'holdRetained': True}

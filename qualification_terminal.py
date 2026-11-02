"""Recognize the supported prepared-abandon audit, never a bare terminal label."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

MAX_DOCUMENT_BYTES = 1024 * 1024


def _bytes(path):
    from qualification_pre_native import _absolute
    path = _absolute(str(path))
    with path.open('rb') as stream:
        raw = stream.read(MAX_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError('Qualification terminal evidence exceeds bounded document size')
    return path, raw


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate qualification terminal evidence key')
            result[key] = value
        return result
    value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError('Qualification terminal evidence must be an object')
    return value


def _pin(pin):
    import polygon as m
    if (not isinstance(pin, dict) or set(pin) != {'path', 'sha256'}
            or not isinstance(pin['path'], str) or not Path(pin['path']).is_absolute()
            or not isinstance(pin['sha256'], str) or not m.SHA.fullmatch(pin['sha256'])):
        raise ValueError('Exact absolute qualification terminal evidence pin required')
    path, raw = _bytes(Path(pin['path']))
    if hashlib.sha256(raw).hexdigest() != pin['sha256']:
        raise ValueError('Qualification terminal evidence pin changed')
    return path, raw


def settled_abandonment(p, con, row):
    """Read-only historical recognition; this grants no new start or clearance."""
    import polygon as m
    try:
        if row['status'] != 'abandoned' or row['expires'] is not None or row['packet'] is not None:
            return False
        identity = row['id']
        attempt = 'qualification-' + identity
        if (con.execute('SELECT id FROM pipeline_holds WHERE id=?', (attempt,)).fetchone()
                or con.execute('SELECT id FROM attempts WHERE id=?', (attempt,)).fetchone()
                or con.execute('SELECT id FROM platform_attempts WHERE id=?', (attempt,)).fetchone()):
            return False
        history = con.execute('SELECT status,note FROM events WHERE id=? ORDER BY seq', (identity,)).fetchall()
        if [event['status'] for event in history] != ['qualification_prepared', 'qualification_prepared_abandoned']:
            return False
        event = _json(history[-1]['note'].encode('utf-8'))
        if set(event) != {'id', 'status', 'actualGameStarts', 'cumulativeActualGameStartsBefore',
                          'cumulativeActualGameStartsAfter', 'review', 'globalProviderQualified',
                          'launchAuthorityGranted', 'reviewed'}:
            return False
        plan = _json(row['request'].encode('utf-8'))
        baseline = plan['cumulativeActualGameStartsBefore']
        if baseline is not None and (type(baseline) is not int or baseline < 0):
            return False
        if (event['id'] != identity or event['status'] != 'abandoned'
                or type(event['actualGameStarts']) is not int or event['actualGameStarts'] != 0
                or event['globalProviderQualified'] is not False or event['launchAuthorityGranted'] is not False
                or any(type(event[key]) is not type(baseline) or event[key] != baseline
                       for key in ('cumulativeActualGameStartsBefore', 'cumulativeActualGameStartsAfter'))):
            return False
        review_path, review_raw = _pin(event['review'])
        review = _json(review_raw)  # Parse the same bounded bytes whose SHA was checked.
        if (type(review.get('schemaVersion')) is not int or review['schemaVersion'] != 1
                or review.get('kind') != 'qualification-prepared-abandon-review'
                or review.get('qualificationId') != identity
                or review.get('preparedRequestSha256') != hashlib.sha256(row['request'].encode('utf-8')).hexdigest()
                or any(review.get(key) is not True for key in
                       ('noDispatchReviewed', 'zeroStartsReviewed', 'installationSettled'))):
            return False
        for key in ('verifiedBy', 'reason'):
            m.required_string(review, key)
        owner = review['ownerAuthorization']
        for key in ('threadId', 'messageId', 'quote', 'verifiedBy', 'path'):
            m.required_string(owner, key)
        owner['path'] = str((review_path.parent / owner['path']).resolve())
        _, owner_raw = _pin({'path': owner['path'], 'sha256': owner['sha256']})
        if owner['quote'] not in owner_raw.decode('utf-8-sig') or review != event['reviewed']:
            return False
        # Historical clearance is not a current launch authorization. Do not
        # revalidate old installed inputs/inventory or demand a permanently empty
        # runtime, which may legitimately serve later, independently owned runs.
        folder = p.local / 'qualifications' / identity
        from qualification_pre_native import _absolute
        _absolute(str(folder))
        if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
            return False
        states = (Path(plan['configuration']['runtime']) / 'runs').glob('*/state.json')
        for index, path in enumerate(states):
            if index >= 1024:
                return False
            _, raw = _bytes(path)
            if _json(raw).get('order', {}).get('id') == attempt:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return False

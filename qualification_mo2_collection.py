"""Explicit completion-only collection of the reviewed failed managed-MO2 run."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from qualification_diagnostic import _api, _sources, _observer, _native, archive_inventory
from qualification_pre_native import _absolute, _hash, _identity, _pin
from qualification_mo2_boundary import validate, read_pin, document

POINTER = 'managed-mo2-collection.json'
SNAPSHOTS = 'managed-mo2-collection-implementation'
FLAGS = ('managedIniBoundaryReviewed', 'nativeCompletionReviewed', 'restorationReviewed', 'archiveReviewed', 'retainHold')


def _checked(p, row, plan, review_path, con):
    m = _api()
    identity = plan['id']
    folder = _absolute(str(p.local / 'qualifications' / identity))
    live = con.execute('SELECT * FROM qualifications WHERE id=?', (identity,)).fetchone()
    if (not live or dict(live) != row or row['status'] != 'running' or row['packet']
            or m.read(folder / 'plan.json') != plan):
        raise ValueError('Exact original uncollected qualification required')
    p.qualification_guard(con, identity)
    if con.execute("SELECT id FROM qualifications WHERE id!=? AND status IN ('prepared','running')", (identity,)).fetchone():
        raise ValueError('Another qualification owner blocks collection')
    if not con.execute('SELECT id FROM attempts WHERE id=?', ('qualification-' + identity,)).fetchone():
        raise ValueError('Original native admission required')
    review_path, raw = read_pin({'path': str(review_path), 'sha256': _hash(review_path)})
    review = document(raw)
    if (review.get('schemaVersion') != 1 or review.get('kind') != 'qualification-managed-mo2-collection-review'
            or review.get('qualificationId') != identity or any(review.get(k) is not True for k in FLAGS)):
        raise ValueError('Explicit failed managed-MO2 collection review required')
    for key in ('verifiedBy', 'summary'):
        m.required_string(review, key)
    _sources(plan, review, folder / 'plan.json', managed_mo2_boundary=True)
    boundary = validate(plan, review, folder / 'plan.json')
    state_path, state_raw = read_pin(review['state'])
    state = document(state_raw)
    result_path, result_raw = read_pin(review['result'])
    result = document(result_raw)
    runtimes = {Path(plan['configuration']['runtime'])}
    if p.host().get('runnerConfig'):
        runtimes.add(Path(m.read(p.host()['runnerConfig'])['runtime']))
    matches = []
    for runtime in runtimes:
        for path in (runtime / 'runs').glob('*/state.json'):
            candidate = m.read(path)
            if candidate.get('done') is not True:
                raise ValueError('Unfinished native session blocks collection')
            if candidate.get('order', {}).get('id') == 'qualification-' + identity:
                matches.append(path)
    if matches != [state_path] or not state_path.is_relative_to(Path(plan['configuration']['runtime'])):
        raise ValueError('One exact ended candidate native run required')
    worker_path = _pin(review['worker'], folder / 'worker.json')
    worker = _identity(m.read(worker_path).get('identity'))
    child_path = _pin(review['childExit'], folder / 'child-exit.json')
    child = m.read(child_path)
    if (type(child.get('returncode')) is not int or child['returncode'] != 1 or child.get('timeout')
            or state.get('runner') != worker or result.get('id') != state.get('id')):
        raise ValueError('Exact failed child and matching native worker required')
    archive = state_path.parent / 'test-profile'
    files, directories = archive_inventory(archive)
    if (not files or review.get('profileArchivePins') != files or review.get('profileArchiveDirectories') != directories
            or Path(state.get('profileArchive', '')).resolve() != archive.resolve()
            or not state.get('testProfile') or Path(state['testProfile']).exists()):
        raise ValueError('Complete exact profile archive/removal required')
    identities = [worker] + [_identity(item['identity']) for item in state.get('owned', [])]
    export_path = _pin(review['originalDashboardExport'])
    export = m.read(export_path)
    paths = [folder / 'plan.json', review_path, state_path, result_path, worker_path, child_path,
             export_path, *(Path(item['exportPath']) for item in export['files']), *boundary['paths'],
             *(Path(item['path']) for item in files)]
    paths.extend(Path(item['path']) for item in m.raw_evidence_pins(state_path.parent))
    return review, boundary, identities, sorted(set(paths))


def _frozen_inputs(review, boundary):
    result = dict(boundary['frozen'])
    for pin in review['implementationPins'] + [review['observer']]:
        source = _pin(pin)
        name = 'observer-native.py' if pin == review['observer'] else source.name
        if name in result:
            raise ValueError('Frozen managed-MO2 implementation name collision')
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != pin['sha256']:
            raise ValueError('Collection implementation changed while reading')
        result[name] = raw
    return result


def verify(p, row, plan):
    """Called only by final collection, never generic verification/recovery."""
    folder = _absolute(str(p.local / 'qualifications' / plan['id']))
    pointer = folder / POINTER
    review_path = _pin(_api().read(pointer))
    review = _api().read(review_path)
    observer = _observer(review['observer'])
    with observer.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        review, boundary, identities, paths = _checked(p, row, plan, review_path, con)
        _native(observer, identities)
        frozen = _frozen_inputs(review, boundary)
        snapshots = folder / SNAPSHOTS
        if not snapshots.is_dir() or {item.name for item in snapshots.iterdir()} != set(frozen):
            raise ValueError('Complete frozen managed-MO2 collection inventory required')
        for name, raw in frozen.items():
            if _hash(snapshots / name) != hashlib.sha256(raw).hexdigest():
                raise ValueError('Frozen managed-MO2 collection bytes changed')
        summary = {key: value for key, value in boundary.items() if key not in ('frozen', 'paths', 'ini', 'proofPath')}
        summary.update(originalPlanUnchanged=True, qualificationPassed=False, holdRetained=True)
        return paths + [pointer] + sorted(snapshots.iterdir()), summary


def record(p, identity, review_path):
    m = _api()
    if not m.SAFE_ID.fullmatch(identity):
        raise ValueError('Safe qualification identity required')
    review_path = _absolute(str(Path(review_path).absolute()))
    folder = _absolute(str(p.local / 'qualifications' / identity))
    pointer, snapshots = folder / POINTER, folder / SNAPSHOTS
    row = p.qualification_show(identity)
    plan = json.loads(row['request'])
    reference = {'path': str(review_path), 'sha256': _hash(review_path)}
    if pointer.exists():
        if m.read(pointer) != reference:
            raise ValueError('Managed-MO2 collection review pointer is immutable')
        if row['packet']:
            return p.qualification_collect(identity)  # Frozen historical evidence only.
        verify(p, row, plan)
        return p.qualification_collect(identity)
    review = m.read(review_path)
    observer = _observer(review['observer'])
    with observer.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        review, boundary, identities, paths = _checked(p, row, plan, review_path, con)
        _native(observer, identities)
        if snapshots.exists():
            raise ValueError('Unregistered managed-MO2 collection artifact requires review')
        frozen = _frozen_inputs(review, boundary)
        snapshots.mkdir()
        for name, raw in frozen.items():
            with (snapshots / name).open('xb') as stream:
                stream.write(raw)
        for path in paths:
            _hash(path)
        _checked(p, row, plan, review_path, con)
        _native(observer, identities)
        if _hash(review_path) != reference['sha256']:
            raise ValueError('Managed-MO2 collection review changed')
        with pointer.open('x', encoding='utf-8') as stream:
            json.dump(reference, stream, indent=2)
            stream.write('\n')
    return p.qualification_collect(identity)


def verify_packet_archive(packet):
    review_path = _pin(packet['managedMo2Collection'])
    review = _api().read(review_path)
    if (review.get('kind') != 'qualification-managed-mo2-collection-review'
            or review.get('qualificationId') != packet.get('id') or packet.get('executionOutcome') != 'failed'
            or packet.get('actualGameStarts') != 1 or packet.get('qualificationPassed') is not False):
        raise ValueError('Cached failed managed-MO2 collection identity differs')
    files, directories = archive_inventory(Path(packet['runDirectory']) / 'test-profile')
    if (files != packet.get('profileArchivePins') or files != review.get('profileArchivePins')
            or directories != review.get('profileArchiveDirectories')):
        raise ValueError('Collected profile archive membership or bytes changed')

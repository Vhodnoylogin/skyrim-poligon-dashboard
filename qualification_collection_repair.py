"""Explicit ended-run collection bridge for the sole nullable-success-reason repair."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from qualification_diagnostic import (_api, _sources, _observer, _native, archive_inventory)
from qualification_pre_native import _absolute, _hash, _identity, _pin

LINE = '        reason = "" if reason is None else reason\n'
ANCHOR = '        """Technical evidence projection; never a test-order result or mod diagnosis."""\n'
FLAGS = ('nullableSuccessReasonReviewed', 'nativeCompletionReviewed', 'restorationReviewed', 'archiveReviewed', 'retainHold')


def validate_patch(original, current):
    if original.count(ANCHOR) != 1 or LINE in original or current != original.replace(ANCHOR, ANCHOR + LINE, 1):
        raise ValueError('Only the exact nullable success reason normalization is supported')


def _folder(p, identity):
    if not _api().SAFE_ID.fullmatch(identity): raise ValueError('Invalid qualification identity')
    return _absolute(str(p.local / 'qualifications' / identity))


def _checked(p, row, plan, review_path, con):
    m = _api(); identity = plan['id']; folder = _folder(p, identity); plan_path = folder / 'plan.json'
    live = con.execute('SELECT * FROM qualifications WHERE id=?', (identity,)).fetchone()
    if (not live or live['request'] != row['request'] or json.loads(row['request']) != plan
            or live['status'] not in ('running', 'recorded') or m.read(plan_path) != plan):
        raise ValueError('Exact original frozen qualification and ended owner required')
    p.qualification_guard(con, identity)
    if con.execute("SELECT id FROM qualifications WHERE id!=? AND status IN ('prepared','running')", (identity,)).fetchone():
        raise ValueError('Another qualification owner blocks collection repair')
    if not con.execute('SELECT id FROM attempts WHERE id=?', ('qualification-' + identity,)).fetchone():
        raise ValueError('Original native admission required')
    review = m.read(review_path)
    if (review.get('schemaVersion') != 1 or review.get('kind') != 'qualification-collection-repair-review'
            or review.get('qualificationId') != identity or any(review.get(k) is not True for k in FLAGS)):
        raise ValueError('Explicit reviewed nullable-success-reason collection repair required')
    for key in ('verifiedBy', 'summary'): m.required_string(review, key)
    _sources(plan, review, plan_path)  # complete original export + all other pins + exact candidate inventory
    export_path = _pin(review['originalDashboardExport']); export = m.read(export_path)
    original = next((r for r in export['files'] if Path(r['originalPath']).name == 'polygon.py'), None)
    if original is None: raise ValueError('Original polygon.py export required')
    validate_patch(Path(original['exportPath']).read_text(encoding='utf-8-sig'),
                   (m.HERE / 'polygon.py').read_text(encoding='utf-8-sig'))
    child = _pin(review['childExit'], folder / 'child-exit.json'); exit_record = m.read(child)
    if type(exit_record.get('returncode')) is not int or exit_record['returncode'] != 0 or exit_record.get('timeout'):
        raise ValueError('Strict child exit zero without timeout required')
    worker_path = _pin(review['worker'], folder / 'worker.json'); worker = _identity(m.read(worker_path).get('identity'))
    runtimes = {Path(plan['configuration']['runtime'])}
    if p.host().get('runnerConfig'): runtimes.add(Path(m.read(p.host()['runnerConfig'])['runtime']))
    matches = []
    for runtime in runtimes:
        for state_path in (runtime / 'runs').glob('*/state.json'):
            state = m.read(state_path)
            if state.get('done') is not True: raise ValueError('Unfinished native run blocks collection repair')
            if state.get('order', {}).get('id') == 'qualification-' + identity:
                matches.append((state_path, state))
    if len(matches) != 1: raise ValueError('One exact ended native run required')
    state_path, state = matches[0]
    if not state_path.is_relative_to(Path(plan['configuration']['runtime'])):
        raise ValueError('Native run outside exact candidate runtime')
    _pin(review['state'], state_path); result_path = _pin(review['result'], state_path.parent / 'result.json'); result = m.read(result_path)
    if (state.get('runner') != worker or state.get('done') is not True or state.get('restored') is not True
            or state.get('restoreErrors') or result.get('restored') is not True or result.get('restoreErrors')
            or state.get('result') != 'passed' or result.get('result') != 'passed'
            or state.get('reason') is not None
            or 'reason' not in result or result['reason'] is not None
            or state.get('id') != state_path.parent.name or result.get('id') != state.get('id')
            or p.native_game_starts(state) != 1):
        raise ValueError('Only one successful fully restored native run with exact null reason is supported')
    archive = state_path.parent / 'test-profile'
    if (Path(state.get('profileArchive', '')).resolve() != archive.resolve()
            or not state.get('testProfile') or Path(state['testProfile']).exists()):
        raise ValueError('Tracked profile archive/removal required')
    files, directories = archive_inventory(archive)
    if not files or review.get('profileArchivePins') != files or review.get('profileArchiveDirectories') != directories:
        raise ValueError('Complete exact nonempty profile archive inventory required')
    identities = [worker] + [_identity(x.get('identity')) for x in state.get('owned', [])]
    game = _identity(state.get('game'))
    if not any(x.get('role') == 'game' and x.get('identity') == game for x in state.get('owned', [])):
        raise ValueError('Exact owned game identity required')
    paths = [plan_path, review_path, export_path, child, worker_path, state_path, result_path,
             *(Path(r['exportPath']) for r in export['files']), *(Path(r['path']) for r in files)]
    paths.extend(Path(r['path']) for r in m.raw_evidence_pins(state_path.parent))
    return review, identities, sorted(set(paths))


def verify(p, row, plan):
    """Completion only: no launch/recovery authority and no frozen-plan mutation."""
    m = _api(); folder = _folder(p, plan['id']); pointer = folder / 'collection-repair.json'
    review_path = _pin(m.read(pointer)); review = m.read(review_path); observer = _observer(review['observer'])
    with observer.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        review, identities, paths = _checked(p, row, plan, review_path, con)
        _native(observer, identities)
        snapshots = folder / 'collection-repair-implementation'
        expected = [(Path(pin['path']).name, pin['sha256']) for pin in review['implementationPins']]
        expected.append(('observer-native.py', review['observer']['sha256']))
        if not snapshots.is_dir() or {x.name for x in snapshots.iterdir()} != {name for name, _ in expected}:
            raise ValueError('Complete frozen collection implementation inventory required')
        for name, digest in expected: _pin({'path': str(snapshots / name), 'sha256': digest})
        return sorted(set(paths + [pointer] + list(snapshots.iterdir())))


def evidence_pins(p, identity):
    row = p.qualification_show(identity); plan = json.loads(row['request'])
    return [{'path': str(path), 'sha256': _hash(path)} for path in verify(p, row, plan)]


def record(p, identity, review_path):
    m = _api(); review_path = _absolute(str(Path(review_path).absolute())); folder = _folder(p, identity)
    pointer = folder / 'collection-repair.json'; row = p.qualification_show(identity); plan = json.loads(row['request'])
    if pointer.exists():
        if m.read(pointer) != {'path': str(review_path), 'sha256': _hash(review_path)}:
            raise ValueError('Collection repair review pointer is immutable')
        verify(p, row, plan)
        return p.qualification_collect(identity)
    if row['status'] != 'running' or row['packet']: raise ValueError('Uncollected ended running qualification required')
    review = m.read(review_path); observer = _observer(review['observer'])
    with observer.SessionMutex(), p.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        review, identities, paths = _checked(p, row, plan, review_path, con)
        _native(observer, identities)
        snapshots = folder / 'collection-repair-implementation'
        if snapshots.exists(): raise ValueError('Unregistered frozen repair implementation requires review')
        snapshots.mkdir()
        for pin in review['implementationPins'] + [review['observer']]:
            source = _pin(pin); name = 'observer-native.py' if pin == review['observer'] else source.name
            target = snapshots / name
            if target.exists(): raise ValueError('Frozen implementation name collision')
            with target.open('xb') as stream: stream.write(source.read_bytes())
            _pin({'path': str(target), 'sha256': pin['sha256']})
        for path in paths: _hash(path)
        _checked(p, row, plan, review_path, con)
        _native(observer, identities)
        with pointer.open('x', encoding='utf-8') as stream:
            json.dump({'path': str(review_path), 'sha256': _hash(review_path)}, stream, indent=2); stream.write('\n')
    verify(p, row, plan)
    return p.qualification_collect(identity)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True); parser.add_argument('--id', required=True); parser.add_argument('--review', required=True)
    args = parser.parse_args(); print(json.dumps(record(_api().Polygon(Path(args.root)), args.id, Path(args.review)), indent=2))


# Cached packets recheck directory membership using the immutable reviewed inventory,
# without depending on mutable current repository implementation paths.
def verify_packet_archive(packet):
    review_path = _pin(packet['collectionRepair']); review = _api().read(review_path)
    if (review.get('kind') != 'qualification-collection-repair-review'
            or review.get('qualificationId') != packet.get('id')):
        raise ValueError('Packet collection repair review identity differs')
    files, directories = archive_inventory(Path(packet['runDirectory']) / 'test-profile')
    if (files != packet.get('profileArchivePins') or files != review.get('profileArchivePins')
            or directories != review.get('profileArchiveDirectories')):
        raise ValueError('Collected profile archive membership or bytes changed')


if __name__ == '__main__': main()

"""Bound one diagnostic exception to the actual known B6 post-action quit fault."""
import os
from pathlib import Path
import struct
import uuid

B6_SHA256 = '207eda2f751599b34f3acacea449e8a4162f3936418c5bf8201d4b7f7a94fff8'
B6_TIMESTAMP = 0x6AB9CB41
B6_RVA = 0x2EE3BA
B6_PDB = uuid.UUID('dc02441e-18cc-4bc5-b03a-9c4a5e3506ba')


def _same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def verify(request, state, result, qplan):
    import diagnostic_admission as d
    fault = d.read_pin(request['knownFault'])
    if fault.get('module', {}).get('sha256') != B6_SHA256:
        raise ValueError('Only the exact independently reviewed official B6 binary is supported')
    d.pin(fault['module'])
    termination = result.get('gameTermination', {})
    reason = 'All action checks completed; owned game shutdown was abnormal_exit (0xC0000005)'
    if (state.get('fault') is not None or result.get('fault') is not None
            or state.get('reason') != reason or result.get('reason') != reason
            or any(x.get('collectionComplete') is not True or x.get('collectionErrors') for x in (state, result))):
        raise ValueError('Q1 must have no other fault or incomplete collection besides the sole known ordinary-close AV')
    if (termination != state.get('gameTermination') or termination.get('kind') != 'abnormal_exit'
            or termination.get('game') != state.get('game') or termination.get('exitCode') != 0xC0000005
            or termination.get('identityVerified') is not True or termination.get('ownQuitRequest') is not True
            or termination.get('exitCodeAvailable') is not True or termination.get('forcedGameStop') is not False
            or termination.get('observationStage') != 'owned-processes-ended'):
        raise ValueError('Only identity-verified ordinary post-action own-close AV is supported')
    checks = result.get('checks', [])
    if not checks or any(x.get('result') != 'passed' for x in checks):
        raise ValueError('Every Q1 action/bootstrap check must have passed before the known quit fault')
    names = [x.get('name') for x in checks]
    declared = {x['name'] for x in qplan['scenario']['steps']}
    extra = [x for x in checks if x.get('name') not in declared]
    if len(names) != len(declared) + 1 or len(names) != len(set(names)) or len(extra) != 1:
        raise ValueError('Exact Q1 action plus bootstrap check set required')
    provenance = extra[0].get('provenance', {})
    if (provenance != {'schemaVersion': 1, 'component': 'skyrim-autotest', 'stage': 'bootstrap',
                       'role': 'tooling', 'runId': state['id'], 'checkId': 'new-game-world-transition'}
            or extra[0] not in state.get('checks', [])):
        raise ValueError('Actual same-run loaded-world bootstrap attestation required')
    for step in qplan['scenario']['steps']:
        if len([x for x in checks if x.get('name') == step['name'] and x.get('result') == 'passed']) != 1:
            raise ValueError('Missing/ambiguous successful Q1 action checkpoint')
    if not all(key in fault for key in ('dump', 'wer', 'debuggerLog')):
        raise ValueError('Actual pinned dump/WER/private-symbol teardown stack proof required')
    raw = d.read_hashed(fault['dump'], maximum=128 * 1024 * 1024)
    try:
        _dump(raw, fault['module']['path'], state['game'])
    except (struct.error, UnicodeError, IndexError) as error:
        raise ValueError('Invalid/truncated native fault dump') from error
    text = d.read_hashed(fault['wer'], maximum=2 * 1024 * 1024).decode('utf-16')
    fields = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
    identity = uuid.UUID(fields.get('AppSessionGuid', ''))
    game = state['game']
    if (int.from_bytes(identity.bytes[:4], 'big') != game['pid']
            or int.from_bytes(identity.bytes[-8:], 'little') != game['birth']
            or not _same_path(fields.get('AppPath', ''), game['path'])):
        raise ValueError('WER exact native PID/birth/path differs from Q1')
    log = d.read_hashed(fault['debuggerLog'], maximum=8 * 1024 * 1024).decode('utf-8-sig', errors='replace')
    if any(token not in log for token in ('DeleteStringEntry', 'BodyMorphInterface', 'LdrShutdownProcess', 'g_stringTable')):
        raise ValueError('Reviewed private-symbol StringTable teardown stack is missing')


def _dump(raw, module_path, game):
    if raw[:4] != b'MDMP':
        raise ValueError('Actual MDMP signature required')
    count, directory = struct.unpack_from('<II', raw, 8)
    if not 1 <= count <= 1024:
        raise ValueError('Invalid native dump directory')
    streams = {}
    for i in range(count):
        kind, size, offset = struct.unpack_from('<3I', raw, directory + i * 12)
        if kind == 0 and size == 0 and offset == 0:
            continue  # Reserved UnusedStream slots in actual Windows dumps.
        if offset + size > len(raw) or kind in streams:
            raise ValueError('Invalid/duplicate native dump stream')
        streams[kind] = (offset, size)
    if not {4, 6, 15} <= set(streams):
        raise ValueError('Native module/exception/process identity streams required')
    if streams[15][1] < 16 or streams[6][1] < 32 or streams[4][1] < 4:
        raise ValueError('Declared native identity/exception/module streams are too short')
    misc = streams[15][0]
    _, flags, pid, creation = struct.unpack_from('<4I', raw, misc)
    if flags & 3 != 3 or pid != game['pid'] or creation != game['birth'] // 10000000 - 11644473600:
        raise ValueError('Native dump PID/create time differs from Q1')
    exception = streams[6][0]
    code = struct.unpack_from('<I', raw, exception + 8)[0]
    address = struct.unpack_from('<Q', raw, exception + 24)[0]
    if code != 0xC0000005:
        raise ValueError('Native dump is not the known AV')
    found = False
    modules, module_bytes = streams[4]
    module_count = struct.unpack_from('<I', raw, modules)[0]
    if not 1 <= module_count <= 4096 or 4 + 108 * module_count > module_bytes:
        raise ValueError('Invalid/bounded native module list required')
    for i in range(module_count):
        at = modules + 4 + i * 108
        base, _, _, timestamp, name = struct.unpack_from('<Q4I', raw, at)
        size = struct.unpack_from('<I', raw, name)[0]
        if not 0 < size < 32768 or size % 2 or name + 4 + size > len(raw):
            raise ValueError('Invalid native dump module path')
        path = raw[name + 4:name + 4 + size].decode('utf-16-le')
        if _same_path(path, module_path):
            cv_size, cv = struct.unpack_from('<II', raw, at + 76)
            if (found or timestamp != B6_TIMESTAMP or address - base != B6_RVA or cv_size < 24 or cv + cv_size > len(raw)
                    or raw[cv:cv + 4] != b'RSDS' or uuid.UUID(bytes_le=raw[cv + 4:cv + 20]) != B6_PDB
                    or struct.unpack_from('<I', raw, cv + 20)[0] != 10):
                raise ValueError('Native fault module/RVA/private PDB does not match known B6')
            found = True
    if not found:
        raise ValueError('Exact loaded B6 module missing from actual dump')

"""Live-state contention and client admission, using temporary files only."""
import ctypes
import errno
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import polygon as m
import subject_companion_route as route
import test_subject_companion_route as fixtures
from qualification import inventory


class LiveStateReadTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.runs = self.root / 'runtime/runs'
        self.path = self.runs / 'fresh/state.json'
        self.state = {'id': 'fresh', 'order': {'id': 'exact'}, 'done': False}
        m.write(self.path, self.state)

    def test_permission_denial_then_fresh_read_succeeds_without_cached_state(self):
        original = Path.open; attempts = []
        def opening(path, *args, **kwargs):
            if path == self.path:
                attempts.append(path)
                if len(attempts) == 1: raise PermissionError(errno.EACCES, 'temporary denial', str(path))
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', new=opening):
            result = route._read_live_state(self.path, self.runs, threading.Event(), time.monotonic() + 3)
        self.assertEqual(result, self.state); self.assertEqual(len(attempts), 2)

    def test_persistent_access_denial_has_attempt_and_monotonic_limits(self):
        clock = [0.0]; waits = []; calls = []
        def pause(seconds): waits.append(seconds); clock[0] += seconds; return False
        stop = SimpleNamespace(is_set=lambda: False, wait=pause)
        def denied(path, *args, **kwargs):
            calls.append(path); raise PermissionError(errno.EACCES, 'persistent denial', str(path))
        with patch.object(Path, 'open', new=denied), patch.object(route.time, 'monotonic', side_effect=lambda: clock[0]):
            with self.assertRaises(PermissionError) as raised:
                route._read_live_state(self.path, self.runs, stop, .12)
        self.assertLessEqual(clock[0], .12); self.assertLessEqual(len(calls), route.STATE_READ_ATTEMPTS)
        self.assertEqual(raised.exception.state_read_attempts, len(calls)); self.assertGreater(len(calls), 1)
        self.assertTrue(all(seconds <= .05 for seconds in waits))

    def test_unclassified_permission_error_is_not_retried(self):
        calls = []
        def denied(path, *args, **kwargs):
            calls.append(path); raise PermissionError(errno.EPERM, 'not a sharing/access error', str(path))
        with patch.object(Path, 'open', new=denied), self.assertRaises(PermissionError):
            route._read_live_state(self.path, self.runs, threading.Event(), time.monotonic() + 3)
        self.assertEqual(len(calls), 1)

    def test_stop_during_retry_abandons_read(self):
        stop = threading.Event(); calls = []
        def denied(path, *args, **kwargs):
            calls.append(path); stop.set(); raise PermissionError(errno.EACCES, 'denial', str(path))
        with patch.object(Path, 'open', new=denied), self.assertRaises(route._PollingStopped):
            route._read_live_state(self.path, self.runs, stop, time.monotonic() + 3)
        self.assertEqual(len(calls), 1)

    def test_reader_is_scoped_and_immutable_reads_remain_strict(self):
        other = self.root / 'pinned-state.json'; other.write_text('{}')
        with patch.object(Path, 'open', side_effect=AssertionError('Scoped refusal precedes I/O')):
            with self.assertRaisesRegex(ValueError, 'exact runtime'):
                route._read_live_state(other, self.runs, threading.Event(), time.monotonic() + 3)
        with patch.object(Path, 'open', side_effect=PermissionError(errno.EACCES, 'deny immutable input', str(other))) as opened:
            with self.assertRaises(PermissionError): m.read(other)
        opened.assert_called_once()

    def test_malformed_duplicate_nonfinite_and_oversized_json_are_not_retried(self):
        original = Path.open
        for raw in (b'{broken', b'{"id":1,"id":2}', b'{"value":NaN}', b'{' + b' ' * 100):
            self.path.write_bytes(raw); calls = []
            def opening(path, *args, **kwargs): calls.append(path); return original(path, *args, **kwargs)
            with self.subTest(raw=raw), patch.object(Path, 'open', new=opening), patch.object(route, 'LIVE_STATE_BYTES', 64):
                with self.assertRaises(ValueError):
                    route._read_live_state(self.path, self.runs, threading.Event(), time.monotonic() + 3)
            self.assertEqual(calls, [self.path])

    @unittest.skipUnless(os.name == 'nt', 'Actual Windows sharing semantics')
    def test_actual_windows_exclusive_handle_denies_then_releases_temporary_state(self):
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                           wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        close = kernel.CloseHandle; close.argtypes = [wintypes.HANDLE]; close.restype = wintypes.BOOL
        handle = create(str(self.path), 0x80000000, 0, None, 3, 0x80, None)
        if handle == ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
        release = threading.Event(); closed = []
        def unlock(): release.wait(.12); closed.append(bool(close(handle)))
        thread = threading.Thread(target=unlock); thread.start()
        original = Path.open; denied = []
        def opening(path, *args, **kwargs):
            try: return original(path, *args, **kwargs)
            except PermissionError as error:
                denied.append((error.errno, getattr(error, 'winerror', None))); raise
        try:
            with patch.object(Path, 'open', new=opening):
                result = route._read_live_state(self.path, self.runs, threading.Event(), time.monotonic() + 3)
        finally:
            release.set(); thread.join(timeout=2)
        self.assertEqual(result, self.state); self.assertTrue(denied)
        self.assertEqual(closed, [True]); self.assertFalse(thread.is_alive())


class CompanionPollingTests(unittest.TestCase):
    setUp = fixtures.CompanionRouteTests.setUp
    pin = fixtures.CompanionRouteTests.pin

    def exercise(self, *, retry=False, scenario='temporary'):
        worker = {'pid': 888, 'birth': 999, 'path': 'offline-owned-worker'}
        game = {'pid': 222, 'birth': 333, 'path': 'offline-owned-game'}
        attempt = 'exact-retry' if retry else None
        key = attempt or self.order['id']; folder = self.p.local / 'retry-attempts' / key if retry else self.p.evidence_dir(key)
        folder.mkdir(parents=True)
        context = {'attemptId': key, 'folder': folder, 'reviewPin': None}
        native_order = {'id': self.order['id']}
        if retry: native_order.update(attemptId=key, subjectOrderId=self.order['id'])
        state = {'id': 'fresh', 'order': native_order, 'runner': worker, 'game': game,
                 'done': scenario == 'ended', 'interactiveSession': {'ready': True}}
        if scenario == 'wrong-worker': state['runner'] = dict(worker, birth=1000)
        if scenario == 'wrong-attempt': state['order']['attemptId'] = 'different-attempt'
        path = Path(self.cfg['runtime']) / 'runs/fresh/state.json'
        finished = threading.Event(); at_admission = threading.Event(); events = []
        original_event, original_pin, original_open = threading.Event, route.pin, Path.open
        def event_factory(*args, **kwargs):
            value = original_event(*args, **kwargs); events.append(value); return value
        def pin_gate(value):
            if scenario == 'stopped' and value == self.pin(self.transport):
                at_admission.set(); self.assertTrue(events[0].wait(3))
            return original_pin(value)
        reads = []
        def opening(target, *args, **kwargs):
            if target == path and args and args[0] == 'rb':
                reads.append(target)
                if scenario == 'persistent' or len(reads) == 1 and scenario in ('temporary', 'wrong-worker', 'wrong-attempt'):
                    raise PermissionError(errno.EACCES, 'injected live-state denial', str(target))
            return original_open(target, *args, **kwargs)
        def owned_run(*args, **kwargs):
            m.write(path, state)
            if scenario == 'stopped': self.assertTrue(at_admission.wait(3)); return 0
            if scenario == 'temporary': self.assertTrue(finished.wait(3)); return 0
            deadline = time.monotonic() + 3
            while not (folder / 'subject-companion/dispatch.json').exists() and time.monotonic() < deadline:
                finished.wait(.005)
            self.assertTrue((folder / 'subject-companion/dispatch.json').exists()); return 0
        runner = SimpleNamespace(native=SimpleNamespace(identity=lambda pid: worker), run=owned_run)
        tracker = SimpleNamespace(snapshot=lambda: {'identityVerified': True, 'status': 'exited', 'exitCode': 0},
                                  close=lambda: {'closeConfirmed': True})
        launches = []
        def client(args, **kwargs):
            launches.append(args); finished.set()
            child = Mock(pid=500, returncode=None)
            def wait(**kwargs): child.returncode = 0; return 0
            child.wait.side_effect = wait; child.poll.side_effect = lambda: child.returncode
            return child
        plan = {'executor': str(self.executor), 'configuration': self.cfg, 'pins': inventory(self.executor),
                'companionSelection': {'transport': self.pin(self.transport)}}
        with patch.object(route, 'attempt_context', return_value=context), \
                patch.object(self.p, 'source_profile', return_value=self.order['profile']), \
                patch.object(Path, 'open', new=opening), patch.object(route, 'pin', side_effect=pin_gate), \
                patch.object(route.threading, 'Event', side_effect=event_factory), \
                patch.object(route.subprocess, 'Popen', side_effect=client), \
                patch.object(route, '_retain_client', return_value=({'pid': 500, 'birth': 501, 'path': 'owned-client'}, tracker)):
            self.assertEqual(route.run(self.p, self.order, plan, runner, attempt_id=attempt), 0)
        return launches, reads, m.read(folder / 'subject-companion/dispatch.json')

    def test_first_attempt_transient_state_denial_recovers_and_launches_once(self):
        launches, reads, dispatch = self.exercise()
        self.assertEqual(len(launches), 1); self.assertEqual(len(reads), 2); self.assertNotIn('error', dispatch)

    def test_retry_transient_state_denial_recovers_and_preserves_exact_attempt(self):
        launches, reads, dispatch = self.exercise(retry=True)
        self.assertEqual(len(launches), 1); self.assertEqual(len(reads), 2)
        self.assertEqual(launches[0][launches[0].index('--attempt-id') + 1], 'exact-retry')

    def test_permanent_denial_never_launches_and_retains_structured_diagnostics(self):
        launches, reads, dispatch = self.exercise(retry=True, scenario='persistent')
        self.assertEqual(launches, []); self.assertLessEqual(len(reads), route.STATE_READ_ATTEMPTS)
        self.assertEqual(dispatch['errorDetails']['errno'], errno.EACCES)
        self.assertEqual(dispatch['errorDetails']['stateReadAttempts'], len(reads))
        self.assertIn('_read_live_state', dispatch['errorDetails']['traceback'])

    def test_worker_mismatch_after_recovered_read_never_launches(self):
        launches, _, dispatch = self.exercise(scenario='wrong-worker')
        self.assertEqual(launches, []); self.assertIn('worker identity mismatch', dispatch['error'])

    def test_retry_identity_mismatch_after_recovered_read_never_launches(self):
        launches, _, dispatch = self.exercise(retry=True, scenario='wrong-attempt')
        self.assertEqual(launches, []); self.assertIn('attempt identity differs', dispatch['error'])

    def test_done_is_checked_before_ready_and_client_creation(self):
        launches, _, dispatch = self.exercise(scenario='ended')
        self.assertEqual(launches, []); self.assertNotIn('client', dispatch)

    def test_main_thread_stop_before_admission_prevents_late_client(self):
        launches, _, dispatch = self.exercise(retry=True, scenario='stopped')
        self.assertEqual(launches, []); self.assertNotIn('client', dispatch)


if __name__ == '__main__': unittest.main()

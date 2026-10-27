"""Exact pre-runner window guard; missing state alone never establishes zero."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import polygon as m
import qualification_pre_native as q
import test_qualification_pre_native as fixture


class PreWindowTests(unittest.TestCase):
    def setUp(self):
        f = self.f = fixture.PreNativeTests(); f.setUp(); self.addCleanup(f.doCleanups)
        f.config['game_edition'] = 'se'; m.write(f.root / 'config.json', f.config)
        (f.game / 'SkyrimSE.exe').write_bytes(b'fixture game'); (f.game / 'skse64_loader.exe').write_bytes(b'fixture loader')
        f.plan['configuration'] = f.config; f.plan['companion'] = {'maximumSeconds': 600}
        f.plan['cumulativeActualGameStartsBefore'] = None
        f.plan['pins'].append(f.pin(f.ini))
        for pin in f.plan['pins']: pin['sha256'] = m.digest(pin['path'])
        with f.p.connect() as con:
            con.execute('UPDATE qualifications SET request=?,expires=?', (json.dumps(f.plan, sort_keys=True), f.started + 650))
        for name, value in (('plan', f.plan), ('config', f.config), ('scenario', f.plan['scenario'])):
            m.write(f.folder / (name + '.json'), value)
        m.write(f.folder / 'dispatch-intent.json', {'id': f.identity, 'at': f.started, 'expires': f.started + 650})
        m.write(f.folder / 'executor.log', {'error': q.WINDOW_ERROR})
        m.write(f.folder / 'subject-companion/executor-manifest.json', {'schemaVersion': 1, 'files': f.plan['executorPins']})
        source = [pin for pin in f.plan['pins'] if Path(pin['path']).parent == m.HERE and Path(pin['path']).suffix == '.py']
        hashes = {name: m.digest(m.HERE / name) for name in q.SUPPORTED_WINDOW_DASHBOARD}
        for item in (patch.object(q, 'SUPPORTED_WINDOW_DASHBOARD', hashes),
                     patch.object(q, 'SUPPORTED_WINDOW_DASHBOARD_INVENTORY', q.source_inventory_digest(source, m.HERE)),
                     patch.object(q, 'SUPPORTED_WINDOW_CANDIDATE_INVENTORY', q.source_inventory_digest(f.plan['executorPins'], f.candidate))):
            item.start(); self.addCleanup(item.stop)
        flow = {'case': q.WINDOW_CASE, 'executedDashboardRoot': str(m.HERE)}
        script = f.root / 'original-operator-script.py'; script.write_text('# synthetic original invocation')
        audit = f.root / 'window-audit.json'
        m.write(audit, {'schemaVersion': 1, 'kind': 'qualification-window-prefix-audit', 'qualificationId': f.identity,
            'worker': f.worker, 'sourceFlow': flow, 'executedSourceHashes': hashes,
            'candidateInventorySha256': q.SUPPORTED_WINDOW_CANDIDATE_INVENTORY,
            'guardBeforeThreadClientAndNativeRunReviewed': True, 'operatorScript': f.pin(script),
            'verifiedBy': 'offline operator', 'summary': 'Synthetic exact source guard proof'})
        f.review.pop('protectedBaseline'); f.review.pop('originalDashboardExport')
        f.review.update(sourceFlow=flow, proofMode='executed-window-guard-prefix', executedControlFlowAudit=f.pin(audit))
        f.review['plan'] = f.pin(f.folder / 'plan.json')
        paths = {p.name: p for p in f.folder.iterdir() if p.is_file()}
        paths['executor-manifest.json'] = f.folder / 'subject-companion/executor-manifest.json'
        f.review['evidence'] = {name: f.pin(path) for name, path in paths.items()}
        self.f.observer.GAME_NAMES |= {'skyrimse.exe', 'skse64_loader.exe'}
        f.save_review()

    def test_zero_record_and_separate_finish_preserve_unknown_admission_and_hold(self):
        f = self.f; packet = q.reconcile(f.p, f.identity, f.review_path)
        self.assertEqual(packet['actualGameStarts'], 0); self.assertIsNone(packet['cumulativeActualGameStartsAfter'])
        self.assertIsNone(packet['restored']); self.assertFalse(packet['testingStarted'])
        self.assertEqual(len(f.p.pipeline_status()['holds']), 1)
        self.assertEqual(f.p.qualification_collect(f.identity), packet)
        self.assertEqual(q.finish(f.p, f.identity, f.finish_review(packet))['actualGameStarts'], 0)
        with f.p.connect() as con: self.assertEqual(dict(con.execute('SELECT * FROM attempts').fetchone()), f.admission)
        self.assertFalse((f.folder / 'subject-companion/report.json').exists())

    def test_other_error_child_status_or_any_client_trace_refuses(self):
        f = self.f
        for name, value in (('executor.log', {'error': 'unrelated refusal'}), ('child-exit.json', {'returncode': 1})):
            old = (f.folder / name).read_bytes(); m.write(f.folder / name, value)
            f.review['evidence'][name] = f.pin(f.folder / name); f.save_review()
            with self.assertRaisesRegex(ValueError, 'exact exit2'): q.reconcile(f.p, f.identity, f.review_path)
            (f.folder / name).write_bytes(old); f.review['evidence'][name] = f.pin(f.folder / name); f.save_review()
        for path in (f.folder / 'launch-intent.json', f.folder / 'subject-companion/dispatch.json',
                     Path(f.config['runtime']) / 'runs/native/state.json'):
            with self.subTest(path=path):
                m.write(path, {})
                with self.assertRaises(ValueError): q.reconcile(f.p, f.identity, f.review_path)
                path.unlink()
                try: path.parent.rmdir()
                except OSError: pass

    def test_wrong_source_or_unproved_timing_never_uses_missing_state_as_zero(self):
        f = self.f; original = copy.deepcopy(f.review)
        f.review['sourceFlow']['executedDashboardRoot'] = str(f.root); f.save_review()
        with self.assertRaisesRegex(ValueError, 'inventory'): q.reconcile(f.p, f.identity, f.review_path)
        f.review = original; f.save_review()
        with f.p.connect() as con: con.execute('UPDATE qualifications SET expires=?', (f.started + 900,))
        m.write(f.folder / 'dispatch-intent.json', {'id': f.identity, 'at': f.started, 'expires': f.started + 900})
        f.review['evidence']['dispatch-intent.json'] = f.pin(f.folder / 'dispatch-intent.json'); f.save_review()
        with self.assertRaisesRegex(ValueError, 'chronology'): q.reconcile(f.p, f.identity, f.review_path)

    def test_live_or_unknown_worker_and_game_remain_blocking(self):
        f = self.f; f.native.alive.return_value = True
        with self.assertRaisesRegex(ValueError, 'remains alive'): q.reconcile(f.p, f.identity, f.review_path)
        f.native.alive.return_value = False; f.process_rows.append({'pid': f.worker['pid'], 'name': 'python.exe'})
        with self.assertRaisesRegex(ValueError, 'unknown or still present'): q.reconcile(f.p, f.identity, f.review_path)

    def test_only_explicit_post_refusal_settings_normalization_is_retained_as_current(self):
        f = self.f; original = m.digest(f.ini); f.ini.write_text('selected_profile=Core\nnormalized=true\n')
        with self.assertRaisesRegex(ValueError, 'pin mismatch'): q.reconcile(f.p, f.identity, f.review_path)
        close = f.root / 'post-refusal-close.json'
        manager = {'pid': 55555, 'birth': int((f.started + 1 + 11644473600) * 10000000), 'path': f.config['mo2_exe']}
        value = {'identity': manager, 'session': {'mo2Pid': manager['pid'], 'serverBootId': 'boot', 'instanceId': 'instance',
            'profilesPath': f.config['profiles']}, 'profile': 'Core', 'normalExitObserved': True,
            'idleProcesses': {'serverBootId': 'boot', 'procs': [], 'launchedByMO2': [], 'running': 0, 'busy': None}}
        m.write(close, value)
        f.review['postRefusalNormalization'] = {'path': str(f.ini), 'originalSha256': original,
            'currentSha256': m.digest(f.ini), 'managerCloseReceipt': f.pin(close)}; f.save_review()
        packet = q.reconcile(f.p, f.identity, f.review_path)
        self.assertEqual(packet['actualGameStarts'], 0)
        self.assertEqual(packet['runtimeEvidence']['stateProof']['originalGlobalStateComparison'], 'not_attested')
        self.assertEqual(packet['runtimeEvidence']['stateProof']['postRefusalNormalization']['originalSha256'], original)
        self.assertNotEqual(m.digest(f.ini), original)


if __name__ == '__main__': unittest.main()

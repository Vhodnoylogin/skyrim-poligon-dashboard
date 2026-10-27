"""Collection-only counterproofs; fake owners and files, no game or live queue."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import polygon as m
import qualification_preclient as d


class PreclientTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.p = m.Polygon(self.root)
        self.folder = self.p.local / 'qualifications/q-one'; self.run = self.root / 'runtime/runs/run-one'
        self.folder.mkdir(parents=True); self.run.mkdir(parents=True)
        self.worker = {'pid': 10, 'birth': 100, 'path': str(self.root / 'python.exe')}
        self.game = {'pid': 11, 'birth': 101, 'path': str(self.root / 'SkyrimSE.exe')}
        self.client = {'pid': 12, 'birth': 102, 'path': str(self.root / 'python.exe')}
        self.profile = self.run / 'test-profile'; self.profile.mkdir(); (self.profile / 'settings.ini').write_text('archived')
        self.target = self.root / 'restored.ini'; self.target.write_text('original')
        (self.run / 'backups').mkdir(); (self.run / 'backups/0').write_text('original')
        self.state = {'id': 'run-one', 'order': {'id': 'qualification-q-one'}, 'runner': self.worker, 'game': self.game,
            'owned': [{'role': 'game', 'identity': self.game}], 'ownedGameRestartCount': 0,
            'done': True, 'restored': True, 'restoreErrors': [], 'result': 'passed', 'collectionComplete': True, 'collectionErrors': [],
            'profileArchive': str(self.profile), 'testProfile': str(self.root / 'absent-profile'),
            'gameplayBootstrap': {'completed': True}, 'interactiveSession': {'ready': False, 'reason': 'owner-finished'},
            'snapshots': [{'path': str(self.target), 'exists': True, 'sha256': m.digest(self.target), 'backup': str(self.run / 'backups/0')}]}
        self.write(self.run / 'state.json', self.state)
        self.write(self.run / 'result.json', {'id': 'run-one', 'restored': True, 'restoreErrors': [], 'result': 'passed'})
        (self.run / 'steps.jsonl').write_text(json.dumps({'kind': 'interactive-action-delivered', 'commandId': 'a'*32,
            'request': {'schemaVersion': 1, 'operation': 'finish'}})+'\n')
        self.write(self.folder / 'worker.json', {'identity': self.worker}); self.write(self.folder / 'child-exit.json', {'returncode': 0})
        self.comp = self.folder / 'subject-companion'; self.comp.mkdir()
        (self.comp / 'events.jsonl').write_bytes(b'')
        self.plan = {'id': 'q-one', 'executor': str(self.root / 'executor'), 'executorPins': [], 'pins': [],
            'orderData': {'id': 'tool-order', 'sourceThreadId': 'tool-thread'}, 'cumulativeActualGameStartsBefore': None,
            'configuration': {'runtime': str(self.root / 'runtime'), 'interactive_session': {'channelConfig': str(self.root / 'channel.json')}},
            'companion': {'maximumSeconds': 600}}
        self.installed = self.root / 'installed-input.bin'; self.installed.write_bytes(b'actual installed input')
        self.plan['pins'].append(self.pin(self.installed))
        for name, content in [('plan', {'checks': [{'name': 'case-one', 'role': 'subject'}, {'name': 'case-two', 'role': 'subject'}]}),
                              ('sequencer', '# reviewed finite source'), ('transport', '# reviewed client')]:
            path = self.root / (name + '.json' if name == 'plan' else name + '.py')
            self.write(path, content) if name == 'plan' else path.write_text(content)
            self.plan['companion'][name] = self.pin(path)
        self.write(self.folder / 'plan.json', self.plan)
        manifest = self.comp / 'executor-manifest.json'; self.write(manifest, {'schemaVersion': 1, 'files': []})
        self.report = {'schemaVersion': 1, 'kind': 'subject-companion-report', 'done': True, 'status': 'stopped',
            'completed': False, 'uncertain': False, 'subjectStarted': False, 'subjectStart': None, 'actions': [], 'evidence': [],
            'actionsRetried': False, 'audioOpened': False, 'errorType': 'ConnectionRefusedError', 'reason': 'peer refused',
            'orderId': 'qualification-q-one', 'attemptId': 'qualification-q-one', 'worker': self.worker, 'game': self.game,
            'caseIds': ['case-one', 'case-two'], 'cases': [{'id': n, 'status': 'not_run', 'commandIds': [], 'evidence': []} for n in ['case-one', 'case-two']],
            **{k: self.plan['companion'][k] for k in ('plan', 'sequencer', 'transport')},
            'events': {**self.pin(self.comp / 'events.jsonl'), 'bytes': 0}, 'executorManifest': self.pin(manifest)}
        args = {'--executor': self.plan['executor'], '--executor-manifest': str(manifest), '--executor-manifest-sha256': m.digest(manifest),
            '--runtime': self.plan['configuration']['runtime'], '--channel-config': self.plan['configuration']['interactive_session']['channelConfig'],
            '--order-id': 'qualification-q-one', '--attempt-id': 'qualification-q-one', '--output': str(self.comp / 'report.json'),
            '--maximum-seconds': '600', '--worker-identity': json.dumps(self.worker), '--game-identity': json.dumps(self.game)}
        for key in ('plan', 'sequencer'):
            args['--'+key] = self.plan['companion'][key]['path']; args['--'+key+'-sha256'] = self.plan['companion'][key]['sha256']
        argv = [self.client['path'], self.plan['companion']['transport']['path']] + [item for pair in args.items() for item in pair]
        self.dispatch = {'schemaVersion': 1, 'orderId': 'qualification-q-one', 'qualificationId': 'q-one', 'worker': self.worker,
            'returncode': 2, 'nativeRun': {'path': str(self.run / 'state.json'), 'runId': 'run-one', 'game': self.game},
            'client': {'argv': argv, 'source': self.report['transport'], 'identity': self.client, 'timedOut': False,
                'terminatedOwnedClient': False, 'returncode': 2, 'exit': {'schemaVersion': 1, 'status': 'exited', 'identityVerified': True,
                    'identity': self.client, 'exitCodeAvailable': True, 'exitCode': 2, 'exitCodeHex': '0x00000002'}}}
        self.save()
        with self.p.connect() as con:
            con.execute('INSERT INTO qualifications VALUES(?,?,?,?,?)', ('q-one', json.dumps(self.plan), 'running', 1, None))
            con.execute('INSERT INTO pipeline_holds VALUES(?,?)', ('qualification-q-one', 'retain'))
            con.execute('INSERT INTO attempts VALUES(?,?)', ('qualification-q-one', 1))
        self.qual = patch.object(self.p, 'qualification_verify', return_value=self.plan); self.qual.start(); self.addCleanup(self.qual.stop)
        self.death = patch.object(d, '_native_dead'); self.dead = self.death.start(); self.addCleanup(self.death.stop)

    def write(self, path, data): m.write(path, data)
    def pin(self, path): return {'path': str(path), 'sha256': m.digest(path)}
    def save(self):
        self.write(self.comp / 'report.json', self.report); self.write(self.comp / 'dispatch.json', self.dispatch)

    def review(self):
        v = {'schemaVersion': 1, 'kind': 'qualification-preclient-review', 'qualificationId': 'q-one',
            'verifiedBy': 'offline operator', 'summary': 'Explicit collection only', 'nativeCompletionReviewed': True,
            'restorationReviewed': True, 'archiveReviewed': True, 'preclientFailureReviewed': True, 'retainHold': True,
            'implementationPins': d.implementation_pins()}
        for key, path in {'plan': self.folder / 'plan.json', 'state': self.run / 'state.json', 'result': self.run / 'result.json',
            'report': self.comp / 'report.json', 'dispatch': self.comp / 'dispatch.json', 'childExit': self.folder / 'child-exit.json',
            'worker': self.folder / 'worker.json'}.items(): v[key] = self.pin(path)
        v['profileArchivePins'], v['profileArchiveDirectories'] = d.archive_inventory(self.profile)
        path = self.root / 'review.json'; self.write(path, v); return path

    def test_genuine_preclient_record_keeps_hold_counts_and_raw_absent_identity(self):
        packet = d.record(self.p, 'q-one', self.review())
        self.assertEqual(packet['actualGameStarts'], 1); self.assertIsNone(packet['cumulativeActualGameStartsAfter'])
        self.assertFalse(packet['testingStarted']); self.assertTrue(packet['retainHold'])
        self.assertTrue(all(c['result'] == 'not_run' for c in packet['componentCoverage']))
        self.assertNotIn('runId', m.read(self.comp / 'report.json'))
        self.assertFalse(self.p.qualification_successful_result(self.plan, packet))
        self.assertEqual(self.p.qualification_show('q-one')['status'], 'recorded')
        self.assertEqual(len(self.p.pipeline_status()['holds']), 1)
        self.installed.write_bytes(b'legitimate installation rollback after collected proof')
        self.assertEqual(self.p.qualification_collect('q-one'), packet)
        self.assertEqual(self.dead.call_args.args[1], [self.worker, self.client, self.game])
        with self.assertRaisesRegex(ValueError, 'uncollected'): d.record(self.p, 'q-one', self.review())

    def test_action_unknown_or_initialized_report_cannot_be_reclassified(self):
        for field, value in [('actions', [{'unknown': True}]), ('uncertain', True), ('runId', 'run-one'),
                             ('errorType', 'TimeoutError'), ('sequencerProcess', {}), ('subjectStarted', True)]:
            with self.subTest(field=field):
                old = copy.deepcopy(self.report); self.report[field] = value; self.save()
                with self.assertRaises(ValueError): d.record(self.p, 'q-one', self.review())
                self.report = old; self.save()
        (self.run / 'steps.jsonl').write_text(json.dumps({'kind': 'interactive-action-delivered', 'commandId': 'b'*32,
            'request': {'schemaVersion': 1, 'operation': 'tool', 'tool': 'platform'}})+'\n')
        with self.assertRaisesRegex(ValueError, 'component action'): d.record(self.p, 'q-one', self.review())

    def test_wrong_argv_exit_or_origin_events_do_not_become_no_action_proof(self):
        original = copy.deepcopy(self.dispatch)
        self.dispatch['client']['argv'][-1] = 'other-source'; self.save()
        with self.assertRaises(ValueError): d.record(self.p, 'q-one', self.review())
        self.dispatch = original; self.save()
        self.dispatch['client']['exit']['exitCode'] = 0; self.save()
        with self.assertRaisesRegex(ValueError, 'client exit'): d.record(self.p, 'q-one', self.review())
        self.dispatch['client']['exit']['exitCode'] = 2; self.save()
        (self.comp / 'events.jsonl').write_text('{}\n')
        with self.assertRaisesRegex(ValueError, 'events'): d.record(self.p, 'q-one', self.review())

    def test_missing_restore_archive_changed_backup_and_unknown_death_refuse(self):
        self.target.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'hash'): d.record(self.p, 'q-one', self.review())
        self.target.write_text('original'); (self.run / 'backups/0').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'backup'): d.record(self.p, 'q-one', self.review())
        (self.run / 'backups/0').write_text('original'); self.dead.side_effect = ValueError('unknown process')
        with self.assertRaisesRegex(ValueError, 'unknown process'): d.record(self.p, 'q-one', self.review())
        self.assertEqual(self.p.qualification_show('q-one')['status'], 'running')
        self.assertFalse((self.folder / 'preclient-diagnostic').exists())

    def test_game_must_be_exactly_owned_not_merely_copied_into_report_and_argv(self):
        self.state['game'] = dict(self.game, pid=999)
        self.write(self.run / 'state.json', self.state)
        with self.assertRaisesRegex(ValueError, 'this native owner'):
            d.record(self.p, 'q-one', self.review())


if __name__ == '__main__': unittest.main()

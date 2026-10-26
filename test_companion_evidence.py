"""Offline provenance fixtures: no game, bus server or native process calls."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import companion_evidence as evidence


class CompanionEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.folder = self.root / 'order' / 'subject-companion'
        self.run = self.root / 'runtime' / 'runs' / 'fresh-run'
        self.folder.mkdir(parents=True)
        self.run.mkdir(parents=True)
        self.p = SimpleNamespace(evidence_dir=lambda _: self.folder.parent)
        self.names = ['case-' + str(number) for number in range(17)]
        self.plan_pin = self.write(self.root / 'plan.json', {'cases': [{'id': name} for name in self.names]})
        self.sequencer_pin = self.write(self.root / 'sequencer.py', '# pinned origin sequencer')
        self.order = {'id': 'owned-order', 'subjectPlan': {'interface': evidence.INTERFACE,
            'plan': self.plan_pin, 'sequencer': self.sequencer_pin, 'checks': self.names, 'maximumSeconds': 1200},
            'inputs': [dict(pin, role='fixture') for pin in (self.plan_pin, self.sequencer_pin)],
            'testing': {'start': {'kind': 'check', 'name': self.names[0]},
                'checks': [{'name': name, 'role': 'subject'} for name in self.names]}}
        self.binding = {'provider': 'skyrim-autotest', 'conversationId': 'fresh-run', 'agentId': 'owned-game-executor'}
        self.worker = {'pid': 111, 'birth': 222, 'path': str(self.root / 'python.exe')}
        self.game = {'pid': 333, 'birth': 444, 'path': str(self.root / 'SkyrimSE.exe')}
        self.state = {'id': 'fresh-run', 'order': {'id': self.order['id']}, 'runner': self.worker,
            'game': self.game, 'interactiveSession': {'sessionId': 'game-fresh-run', 'binding': self.binding, 'sourceId': 'operator.actions'}}
        self.write(self.run / 'state.json', self.state)
        self.transport = self.write(self.root / 'subject_companion.py', '# independently pinned transport')
        self.transport = {key: self.transport[key] for key in ('path', 'sha256')}
        self.manifest = self.write(self.folder / 'executor-manifest.json', {'schemaVersion': 1, 'files': []})
        self.manifest = {key: self.manifest[key] for key in ('path', 'sha256')}
        self.client_identity = dict(self.worker, pid=555, birth=666)
        self.child_identity = dict(self.worker, pid=777, birth=888)
        self.frozen = {'executor': str(self.root / 'executor'), 'companionSelection': {'transport': self.transport},
            'configuration': {'runtime': str(self.root / 'runtime'),
                'interactive_session': {'channelConfig': str(self.root / 'channel.json')}}}
        self.p.attempt_plan = lambda _: self.frozen
        self.p.verify_companion_processes_dead = Mock(return_value=True)
        self.dispatch = CompanionEvidenceTests.dispatch_record(self)
        self.write(self.folder / 'dispatch.json', self.dispatch)
        self.steps, self.events, self.actions, self.cases = [], [], [], []
        for number, name in enumerate(self.names, 1):
            action, raw = self.action(number, name)
            self.actions.append(action)
            self.cases.append({'id': name, 'status': 'passed', 'commandIds': [action['commandId']], 'evidence': [raw]})
        self.actions.append(self.action(18, None)[0])
        self.report = {'schemaVersion': 1, 'kind': 'subject-companion-report', 'orderId': self.order['id'],
            'attemptId': self.order['id'], 'runId': 'fresh-run', 'sessionId': 'game-fresh-run', 'binding': self.binding,
            'worker': self.worker, 'game': self.game, 'plan': self.plan_pin, 'sequencer': self.sequencer_pin,
            'transport': self.transport, 'executorManifest': self.manifest,
            'sequencerProcess': {'pid': self.child_identity['pid'], 'identity': self.child_identity, 'returnCode': 0, 'stoppedByClient': False},
            'caseIds': self.names, 'cases': self.cases, 'actions': self.actions, 'subjectStarted': True,
            'subjectStart': {'caseId': self.names[0], 'commandId': self.actions[0]['commandId'],
                'sourceEventId': self.actions[0]['sourceEventId'], 'deliveredEvidence': self.actions[0]['deliveredEvidence']},
            'done': True, 'completed': True, 'status': 'completed', 'uncertain': False}
        self.save()

    def dispatch_record(self, code=0):
        cfg, spec = self.frozen['configuration'], self.order['subjectPlan']
        flags = {'--executor': self.frozen['executor'], '--plan': spec['plan']['path'], '--plan-sha256': spec['plan']['sha256'],
            '--sequencer': spec['sequencer']['path'], '--sequencer-sha256': spec['sequencer']['sha256'],
            '--runtime': cfg['runtime'], '--channel-config': cfg['interactive_session']['channelConfig'],
            '--order-id': self.order['id'], '--attempt-id': getattr(self, 'attempt_id', self.order['id']), '--output': str(self.folder / 'report.json'),
            '--worker-identity': json.dumps(self.worker), '--game-identity': json.dumps(self.game),
            '--maximum-seconds': str(spec['maximumSeconds']), '--executor-manifest': self.manifest['path'],
            '--executor-manifest-sha256': self.manifest['sha256']}
        argv = [self.client_identity['path'], self.transport['path']]
        for key, value in flags.items(): argv.extend((key, value))
        return {'schemaVersion': 1, 'orderId': self.order['id'], 'worker': self.worker, 'returncode': code,
            'client': {'identity': self.client_identity, 'source': self.transport, 'argv': argv,
                'returncode': code, 'timedOut': False, 'terminatedOwnedClient': False,
                'exit': {'schemaVersion': 1, 'status': 'exited', 'identityVerified': True, 'identity': self.client_identity,
                    'exitCodeAvailable': True, 'exitCode': code & 0xFFFFFFFF, 'exitCodeHex': f'0x{code & 0xFFFFFFFF:08X}'}}}

    def write(self, path, value):
        data = value.encode() if isinstance(value, str) else json.dumps(value).encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

    def lines(self, path, rows):
        return self.write(path, ''.join(json.dumps(row) + '\n' for row in rows))

    def action(self, number, name):
        command, source = 'command-' + str(number), 'owned-order:' + self.state['id'] + ':' + str(number)
        envelope = {'schemaVersion': 1, 'operation': 'tool', 'tool': 'inspect', 'args': {'kind': 'state'}, 'timeoutSeconds': 5} if name else {'schemaVersion': 1, 'operation': 'finish'}
        request = {'sessionId': self.state['interactiveSession']['sessionId'], 'expectedBinding': self.binding, 'sourceId': 'operator.actions',
            'sourceEventId': source, 'kind': 'text', 'text': json.dumps(envelope),
            'metadata': {'subjectOrder': self.order['id'], 'attemptId': getattr(self, 'attempt_id', self.order['id']), 'caseId': name, 'sequence': number}}
        prefix = self.folder / str(number)
        native = {'at': number, 'kind': 'interactive-action-delivered', 'commandId': command, 'request': envelope}
        value = {'actual': True} if name else {'outcome': 'owner-finished'}
        raw = self.write(prefix / 'raw.json', value)
        delivered = self.write(prefix / 'delivered.json', native)
        self.steps.append(native)
        wrapper = {'kind': 'action-delivered', 'caseId': name, 'commandId': command, 'sourceEventId': source, 'executorLog': native, 'evidence': delivered}
        self.events.extend([{'kind': 'origin', 'record': {'kind': 'check-start', 'caseId': name, 'role': 'subject'}}, wrapper,
            {'kind': 'origin', 'record': {'kind': 'assertion', 'caseId': name, 'check': 'actual-value', 'outcome': 'passed', 'actual': True, 'expected': True}},
            {'kind': 'origin', 'record': {'kind': 'check-result', 'caseId': name, 'outcome': 'passed', 'detail': 'readback'}}] if name else [wrapper])
        row = {key: value for key, value in request.items() if key != 'expectedBinding'}
        row.update(id=command, binding=self.binding)
        return {'sequence': number, 'caseId': name, 'sourceEventId': source, 'commandId': command, 'status': 'completed',
            'envelope': envelope, 'request': self.write(prefix / 'request.json', request),
            'ack': self.write(prefix / 'ack.json', {'acknowledged': True, 'duplicate': False, 'command': row}),
            'deliveredEvidence': delivered, 'completion': self.write(prefix / 'completion.json',
                {'id': number, 'sessionId': self.state['interactiveSession']['sessionId'], 'type': 'command.completed', 'createdAt': number,
                 'data': {'commandId': command, 'result': value}}), 'rawResult': raw}, raw

    def save(self):
        self.lines(self.run / 'steps.jsonl', self.steps)
        for index, wrapper in enumerate(self.events):
            if wrapper.get('kind') == 'origin':
                wrapper['evidence'] = self.write(self.folder / 'origin' / (str(index) + '.json'), wrapper['record'])
        self.report['events'] = self.lines(self.folder / 'events.jsonl', self.events)
        self.write(self.folder / 'report.json', self.report)

    def collect(self):
        return evidence.collect(self.p, self.order, self.run)

    def test_valid_seventeen_cases_and_reverified_packet(self):
        summary = self.collect()
        self.assertTrue(summary['subjectStarted'])
        self.assertTrue(summary['completed'])
        self.assertFalse(summary['uncertain'])
        self.assertEqual(summary['checks'], [{'name': name, 'result': 'passed'} for name in self.names])
        packet = {'runDirectory': str(self.run), 'subjectCompanion': summary, 'files': summary['pins']}
        self.assertEqual(evidence.projection(self.p, self.order, packet), summary)
        packet['files'] = packet['files'][1:]
        with self.assertRaisesRegex(ValueError, 'absent'): evidence.projection(self.p, self.order, packet)

    def test_old_run_attempt_worker_game_and_binding_refuse(self):
        for field, value in [('runId', 'old-run'), ('attemptId', 'old-attempt'), ('worker', dict(self.worker, birth=9)),
                             ('game', dict(self.game, pid=8)), ('binding', dict(self.binding, conversationId='old'))]:
            original = self.report[field]
            self.report[field] = value; self.save()
            with self.subTest(field=field), self.assertRaises(ValueError): self.collect()
            self.report[field] = original

    def test_changed_artifact_or_plan_bytes_refuse(self):
        for pin in (self.actions[0]['rawResult'], self.plan_pin):
            path = Path(pin['path']); original = path.read_bytes(); path.write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'hash'): self.collect()
            path.write_bytes(original)

    def test_missing_actual_delivery_cannot_be_replaced_by_ack(self):
        self.steps = self.steps[1:]; self.save()
        with self.assertRaisesRegex(ValueError, 'delivery missing'): self.collect()

    def test_replayed_duplicate_native_delivery_refuses(self):
        self.steps.append(copy.deepcopy(self.steps[0])); self.save()
        with self.assertRaisesRegex(ValueError, 'replayed'): self.collect()

    def test_duplicate_cases_and_missing_start_refuse(self):
        self.report['cases'][1]['id'] = self.names[0]; self.save()
        with self.assertRaisesRegex(ValueError, 'inventory'): self.collect()
        self.report['cases'][1]['id'] = self.names[1]
        self.events = self.events[1:]; self.save()
        with self.assertRaisesRegex(ValueError, 'check-start'): self.collect()

    def test_receipts_without_assertions_never_pass(self):
        self.events = [row for row in self.events if row.get('record', {}).get('kind') != 'assertion']; self.save()
        with self.assertRaisesRegex(ValueError, 'assertion/readback'): self.collect()

    def stop(self, status='failed', uncertain=False):
        self.report.update(status='stopped', uncertain=uncertain, completed=not uncertain)
        self.report['actions'] = self.actions[:1]
        self.events = self.events[:4]
        self.events[2]['record']['outcome'] = 'mismatch'
        self.events[3]['record']['outcome'] = 'mismatch' if status == 'failed' else 'unavailable'
        self.steps = self.steps[:1]
        if not uncertain:
            self.report['actions'].append(self.action(2, None)[0])
        self.report['cases'] = [dict(self.cases[0], status=status)] + [
            {'id': name, 'status': 'not_run', 'commandIds': [], 'evidence': []} for name in self.names[1:]]

    def test_known_mismatch_preserves_stopped_remainder(self):
        self.stop(); self.save()
        result = self.collect()
        self.assertEqual([row['result'] for row in result['checks']], ['failed'] + ['not_run'] * 16)
        self.assertTrue(result['completed'])
        self.assertFalse(result['uncertain'])

    def test_uncertain_result_and_nonzero_dispatch_remain_tool_faults(self):
        self.stop('unavailable', True)
        self.report['actions'][0]['status'] = 'uncertain'; self.save()
        result = self.collect()
        self.assertTrue(result['uncertain']); self.assertFalse(result['completed'])
        self.report['uncertain'] = False; self.save()
        with self.assertRaisesRegex(ValueError, 'masked'): self.collect()
        self.report['uncertain'] = True; self.save()
        self.write(self.folder / 'dispatch.json', self.dispatch_record(7))
        self.assertFalse(self.collect()['completed'])

    def test_nonzero_dispatch_overrides_an_otherwise_clean_report(self):
        self.write(self.folder / 'dispatch.json', self.dispatch_record(7))
        result = self.collect()
        self.assertTrue(result['uncertain']); self.assertFalse(result['completed'])

    def test_completed_report_requires_actual_finish(self):
        self.report['actions'].pop(); self.save()
        with self.assertRaisesRegex(ValueError, 'known finish'): self.collect()

    def test_transport_stop_preserves_actual_start_without_fabricated_verdict(self):
        self.stop('unavailable', True)
        self.report['actions'][0]['status'] = 'uncertain'
        self.report['cases'][0].update(verdictSource='transport', reason='Lost completion after delivery')
        self.events = self.events[:2]; self.save()
        result = self.collect()
        self.assertTrue(result['subjectStarted']); self.assertTrue(result['uncertain'])
        self.assertEqual(result['checks'][0]['result'], 'unavailable')
        self.assertTrue(all(check['result'] == 'not_run' for check in result['checks'][1:]))
        self.report['subjectStarted'] = False; self.report['subjectStart'] = None; self.save()
        with self.assertRaisesRegex(ValueError, 'masked or invented'): self.collect()

    def test_large_native_artifact_matches_exact_registry_copy_and_completion(self):
        action = self.report['actions'][0]
        value = {'catalog': ['long-preset-name'] * 3000}
        native = self.write(self.run / 'interactive-results' / (action['commandId'] + '.json'), value)
        native['format'] = 'json'
        action['artifact'] = native
        action['artifactCopy'] = self.write(self.folder / 'artifact-copy.json', value)
        action['rawResult'] = self.write(Path(action['rawResult']['path']), value)
        self.report['cases'][0]['evidence'] = [action['rawResult']]
        action['completion'] = self.write(Path(action['completion']['path']), {'id': 1, 'sessionId': 'game-fresh-run',
            'type': 'command.completed', 'data': {'commandId': action['commandId'],
            'result': {'outcome': 'result-recorded', 'evidence': native}}})
        self.state['interactiveArtifacts'] = [dict(native, commandId=action['commandId'])]
        self.write(self.run / 'state.json', self.state); self.save()
        self.assertTrue(self.collect()['completed'])
        self.state['interactiveArtifacts'] = []
        self.write(self.run / 'state.json', self.state)
        with self.assertRaisesRegex(ValueError, 'large result differs'): self.collect()

    def test_path_escape_and_symbolic_link_refuse(self):
        foreign = self.write(self.root / 'foreign.json', {'actual': True})
        self.report['cases'][0]['evidence'] = [foreign]; self.save()
        with self.assertRaisesRegex(ValueError, 'escapes'): self.collect()
        linked = self.folder / 'linked.json'
        try: linked.symlink_to(Path(foreign['path']))
        except OSError: return  # Windows may withhold symbolic-link privilege.
        self.report['cases'][0]['evidence'] = [dict(foreign, path=str(linked))]; self.save()
        with self.assertRaisesRegex(ValueError, 'linked'): self.collect()

    def test_windows_reparse_refusal_without_link_creation_privilege(self):
        target = Path(self.actions[0]['rawResult']['path'])
        original = Path.lstat
        def attributes(path):
            info = original(path)
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400) if path == target else info
        with patch.object(Path, 'lstat', attributes), self.assertRaisesRegex(ValueError, 'linked'):
            self.collect()

    def test_projection_detects_changed_report_and_duplicate_json(self):
        summary = self.collect()
        packet = {'runDirectory': str(self.run), 'subjectCompanion': summary, 'files': summary['pins']}
        self.report['completed'] = False; self.report['status'] = 'stopped'; self.save()
        with self.assertRaisesRegex(ValueError, 'summary differs'): evidence.projection(self.p, self.order, packet)
        (self.folder / 'report.json').write_text('{"done":true,"done":false}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON'): self.collect()

    def test_ordinary_orders_untouched(self):
        self.assertIsNone(evidence.collect(self.p, {'subjectPlan': {'interface': 'polygon-actions/1'}}, None))
        self.assertIsNone(evidence.projection(self.p, {'subjectPlan': {}}, {}))

    def test_malformed_evidence_shapes_are_collection_refusals(self):
        self.write(self.folder / 'report.json', [])
        with self.assertRaisesRegex(ValueError, 'malformed evidence shape'): self.collect()

    def test_compact_plan_checks_names_and_legacy_inventory_must_agree(self):
        path = Path(self.plan_pin['path'])
        content = {'checks': [{'name': name, 'role': 'subject'} for name in self.names]}
        self.plan_pin.update(self.write(path, content))
        self.order['inputs'][0].update(self.plan_pin)
        self.dispatch = self.dispatch_record(); self.write(self.folder / 'dispatch.json', self.dispatch); self.save()
        self.assertTrue(self.collect()['completed'])
        content['cases'] = [{'id': 'unrelated'}]
        self.plan_pin.update(self.write(path, content))
        self.order['inputs'][0].update(self.plan_pin)
        self.write(self.folder / 'dispatch.json', self.dispatch_record()); self.save()
        with self.assertRaisesRegex(ValueError, 'inventory differs'): self.collect()

    def test_missing_or_negative_independent_death_proof_refuses(self):
        self.collect()
        self.p.verify_companion_processes_dead.assert_called_with(self.order, [self.client_identity, self.child_identity])
        self.p.verify_companion_processes_dead.return_value = False
        with self.assertRaisesRegex(ValueError, 'process-death'): self.collect()
        del self.p.verify_companion_processes_dead
        with self.assertRaisesRegex(ValueError, 'process-death'): self.collect()

    def test_client_telemetry_identity_and_arguments_cannot_change(self):
        for change in ('identity', 'source', 'argv'):
            dispatch = copy.deepcopy(self.dispatch)
            if change == 'identity': dispatch['client']['exit']['identity'] = dict(self.client_identity, birth=667)
            if change == 'source': dispatch['client']['source']['sha256'] = '0' * 64
            if change == 'argv': dispatch['client']['argv'][-1] = '0' * 64
            self.write(self.folder / 'dispatch.json', dispatch)
            with self.subTest(change=change), self.assertRaises(ValueError): self.collect()

    def test_client_timeout_lost_exit_and_inner_nonzero_cannot_finalize(self):
        for field in ('timedOut', 'terminatedOwnedClient'):
            dispatch = self.dispatch_record(); dispatch['client'][field] = True
            self.write(self.folder / 'dispatch.json', dispatch)
            result = self.collect(); self.assertFalse(result['completed']); self.assertTrue(result['uncertain'])
        dispatch = self.dispatch_record(); dispatch['client']['exit']['exitCodeAvailable'] = False
        self.write(self.folder / 'dispatch.json', dispatch)
        self.assertFalse(self.collect()['completed'])
        self.write(self.folder / 'dispatch.json', self.dispatch_record())
        for code in (7, None):
            self.report['sequencerProcess']['returnCode'] = code; self.save()
            result = self.collect(); self.assertFalse(result['completed']); self.assertTrue(result['uncertain'])
        self.report['sequencerProcess'].update(returnCode=0, stoppedByClient=True); self.save()
        self.assertFalse(self.collect()['completed'])

    def retry_fixture(self):
        self.initial_folder = self.folder
        self.initial_run = self.run
        self.initial_report = copy.deepcopy(self.report)
        self.attempt_id = 'pre-session-retry-1'
        self.p.local = self.root / 'local'
        retry_root = self.p.local / 'retry-attempts' / self.attempt_id
        self.folder = retry_root / 'subject-companion'; self.folder.mkdir(parents=True)
        self.run = self.root / 'runtime' / 'runs' / 'retry-run'; self.run.mkdir()
        self.state = copy.deepcopy(self.state)
        self.state.update(id='retry-run', order={'id': self.order['id'], 'attemptId': self.attempt_id,
            'subjectOrderId': self.order['id'], 'owner': 'preserved-origin'})
        self.binding = dict(self.binding, conversationId='retry-run')
        self.state['interactiveSession'].update(sessionId='game-retry-run', binding=self.binding)
        self.write(self.run / 'state.json', self.state)
        manifest = self.write(self.folder / 'executor-manifest.json', {'schemaVersion': 1, 'files': []})
        self.manifest = {key: manifest[key] for key in ('path', 'sha256')}
        self.steps, self.events, self.actions, self.cases = [], [], [], []
        for number, name in enumerate(self.names, 1):
            action, raw = self.action(number, name)
            self.actions.append(action)
            self.cases.append({'id': name, 'status': 'passed', 'commandIds': [action['commandId']], 'evidence': [raw]})
        self.actions.append(self.action(len(self.names) + 1, None)[0])
        self.report = copy.deepcopy(self.initial_report)
        self.report.update(attemptId=self.attempt_id, runId='retry-run', sessionId='game-retry-run', binding=self.binding,
            executorManifest=self.manifest, actions=self.actions, cases=self.cases,
            subjectStart={key: self.actions[0][key] for key in ('caseId', 'commandId', 'sourceEventId', 'deliveredEvidence')})
        self.write(self.folder / 'dispatch.json', self.dispatch_record()); self.save()
        review = self.write(self.root / 'registered-retry-review.json', {'reviewed': 'registered zero-prior-native ticket'})
        self.retry_context = {'attemptId': self.attempt_id, 'folder': retry_root,
            'reviewPin': {key: review[key] for key in ('path', 'sha256')}}
        self.context = Mock(return_value=self.retry_context)
        module_patch = patch.dict(sys.modules, {'companion_pretest_resume': SimpleNamespace(context=self.context)})
        module_patch.start(); self.addCleanup(module_patch.stop)
        self.p.attempt_plan = Mock(return_value=self.frozen)

    def test_registered_retry_collects_current_report_and_reverifies_projection(self):
        self.retry_fixture()
        summary = evidence.collect(self.p, self.order, self.run, self.attempt_id)
        self.assertTrue(summary['completed']); self.assertTrue(summary['subjectStarted'])
        self.context.assert_called_with(self.p, self.order, self.attempt_id)
        self.p.attempt_plan.assert_called_with(self.order, self.attempt_id)
        self.p.verify_companion_processes_dead.assert_called_with(self.order, [self.client_identity, self.child_identity], self.attempt_id)
        self.assertIn(self.retry_context['reviewPin']['path'], [pin['path'] for pin in summary['pins']])
        packet = {'attemptId': self.attempt_id, 'runDirectory': str(self.run), 'subjectCompanion': summary, 'files': summary['pins']}
        self.assertEqual(evidence.projection(self.p, self.order, packet), summary)
        Path(self.retry_context['reviewPin']['path']).write_bytes(b'changed admission')
        with self.assertRaisesRegex(ValueError, 'hash/size changed'):
            evidence.projection(self.p, self.order, packet)

    def test_retry_wrong_attempt_folder_or_unregistered_context_refuses(self):
        self.retry_fixture()
        for replacement in (dict(self.retry_context, attemptId='foreign-attempt'),
                            dict(self.retry_context, folder=self.initial_folder.parent)):
            self.context.return_value = replacement
            with self.assertRaisesRegex(ValueError, 'context differs'):
                evidence.collect(self.p, self.order, self.run, self.attempt_id)
        self.context.side_effect = ValueError('No registered zero-start retry proof')
        with self.assertRaisesRegex(ValueError, 'No registered'):
            evidence.collect(self.p, self.order, self.run, self.attempt_id)

    def test_retry_cannot_adopt_initial_report_old_run_or_missing_attempt_attribution(self):
        self.retry_fixture()
        with self.assertRaisesRegex(ValueError, 'run/order/attempt'):
            evidence.collect(self.p, self.order, self.initial_run, self.attempt_id)
        self.write(self.folder / 'report.json', self.initial_report)
        with self.assertRaisesRegex(ValueError, 'run/order/attempt'):
            evidence.collect(self.p, self.order, self.run, self.attempt_id)
        self.save()
        del self.state['order']['subjectOrderId']; self.write(self.run / 'state.json', self.state)
        with self.assertRaisesRegex(ValueError, 'retry native order'):
            evidence.collect(self.p, self.order, self.run, self.attempt_id)

    def test_retry_packet_without_registered_attempt_and_cross_runtime_refuse(self):
        self.retry_fixture()
        summary = evidence.collect(self.p, self.order, self.run, self.attempt_id)
        packet = {'runDirectory': str(self.run), 'subjectCompanion': summary, 'files': summary['pins']}
        with self.assertRaises(ValueError): evidence.projection(self.p, self.order, packet)
        old_runtime = self.frozen['configuration']['runtime']
        self.frozen['configuration']['runtime'] = str(self.root / 'foreign-runtime')
        self.write(self.folder / 'dispatch.json', self.dispatch_record())
        with self.assertRaisesRegex(ValueError, 'outside selected runtime'):
            evidence.collect(self.p, self.order, self.run, self.attempt_id)
        self.frozen['configuration']['runtime'] = old_runtime

    def test_initial_collection_does_not_consult_retry_module(self):
        with patch.dict(sys.modules, {'companion_pretest_resume': None}):
            self.assertTrue(self.collect()['completed'])


if __name__ == '__main__': unittest.main()

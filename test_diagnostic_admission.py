"""Composed Dashboard diagnostics; fake native boundary, no applications launched."""
import copy
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

import diagnostic_admission as d
import diagnostic_b6_fault as bf
import polygon as m
from test_qualification import FAKE_RUNNER


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=os.environ.get('SKYRIM_POLYGON_TEST_TMP')); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.p = m.Polygon(self.root)
        previous = {k: v for k, v in m.sys.modules.items() if k == 'skyrim_autotest' or k.startswith('skyrim_autotest.')}
        for key in previous:
            del m.sys.modules[key]
        def restore():
            for key in list(m.sys.modules):
                if key == 'skyrim_autotest' or key.startswith('skyrim_autotest.'):
                    del m.sys.modules[key]
            m.sys.modules.update(previous)
        self.addCleanup(restore)
        original_b6 = bf.B6_SHA256
        self.addCleanup(setattr, bf, 'B6_SHA256', original_b6)
        original_q1 = d.Q1_ID
        self.addCleanup(setattr, d, 'Q1_ID', original_q1)
        self.executor = self.root / 'executor'; pkg = self.executor / 'skyrim_autotest'; pkg.mkdir(parents=True)
        runner = FAKE_RUNNER.replace("'done':True,'restored':True", "'done':True,'result':'failed','reason':'Owned close abnormal0xC0000005','restored':True")
        runner = runner.replace("checks=[{'name':'tool-check','result':'failed' if scenario.get('failCheck') else 'passed'}]",
                                "checks=[{'name':x['name'],'result':'passed'} for x in scenario['steps']]")
        runner = runner.replace("'result':'passed','checks':checks", "'result':'failed','reason':'Owned close abnormal0xC0000005','checks':checks,'collectionComplete':True")
        (pkg / 'runner.py').write_text(runner)
        (pkg / '__init__.py').write_text('')
        (self.executor / 'run.py').write_text('# offline fixture executor')
        (pkg / 'config.py').write_text('import json\nfrom pathlib import Path\ndef load(p):\n x=json.loads(Path(p).read_text());x.setdefault("fixture_dir",None);x.setdefault("collected_files",[]);x.setdefault("subject_state_bindings",{});return x\n')
        (pkg / 'scenarios.py').write_text('def validate(s): assert s["steps"]\n')
        (pkg / 'restart_budget.py').write_text('def plan(s): return {"maximum":0}\n')
        self.ini = self.root / 'mo2.ini'; self.ini.write_text('selected_profile=Core\n')
        self.profile = self.root / 'profiles' / 'Core'; self.profile.mkdir(parents=True)
        (self.profile / 'modlist.txt').write_text('+original\n')
        (self.profile / 'plugins.txt').write_text('original.esp\n')
        (self.profile / 'loadorder.txt').write_text('original.esp\n')
        self.config = self.root / 'config.json'
        m.write(self.config, {'runtime': str(self.root / 'runtime'), 'ini': str(self.ini), 'mo2_ini': str(self.ini), 'profiles': str(self.profile.parent)})
        m.write(self.p.local / 'config.json', {'executor': 'missing-global-VR', 'platformManifest': 'missing-global-VR'})
        self.host_bytes = (self.p.local / 'config.json').read_bytes()
        self.owner = self.root / 'owner.txt'; self.owner.write_text('Run the bounded stock baseline')
        self.auth = {'threadId': 'owner', 'messageId': 'human', 'quote': self.owner.read_text(),
                     'verifiedBy': 'offline fixture', 'path': str(self.owner), 'sha256': m.digest(self.owner)}
        self.cycle = {'schemaVersion': 1, 'id': 'cycle', 'subject': 'Fixture mod', 'sourceChat': 'mod',
                      'sourceThreadId': 'origin', 'profile': 'Core', 'scopeId': 'core', 'maxIterations': 6,
                      'deadlineUtc': time.time() + 3600, 'ownerAuthorization': self.auth}
        with self.p.connect() as con:
            con.execute("INSERT INTO cycles VALUES(?,?,'active','')", ('cycle', json.dumps(self.cycle)))
        self.ticket = {'schemaVersion': 1, 'id': 'slot', 'cycleId': 'cycle', 'iteration': 1, 'orderId': 'subject',
                       'sourceChat': 'mod', 'sourceThreadId': 'origin',
                       'writePaths': [str(self.root / 'installed'), str(self.ini), str(self.profile / 'modlist.txt')]}
        ticket = self.root / 'ticket.json'; m.write(ticket, self.ticket); self.p.request_slot(ticket)
        self.provider = self.root / 'provider.dll'; self.provider.write_bytes(b'official B6 offline fixture')
        # The selected fake native executor supplies the synthetic binary hash in
        # both parent and fresh child; production retains the actual fixed B6 hash.
        (pkg / 'runner.py').write_text('import diagnostic_b6_fault as fixture_fault\nfixture_fault.B6_SHA256='+repr(m.digest(self.provider))+'\n'+runner)
        self.installation = []
        for i in range(10):
            source = self.root / 'staged' / ('file' + str(i)); source.parent.mkdir(exist_ok=True); source.write_bytes(('new'+str(i)).encode())
            target = self.root / 'installed' / ('file' + str(i)); target.parent.mkdir(exist_ok=True); target.write_bytes(('old'+str(i)).encode())
            self.installation.append({'source': d.file_pin(source), 'target': str(target), 'beforeSha256': m.digest(target)})
        self.qfolder = self.p.local / 'qualifications' / d.Q1_ID; self.qfolder.mkdir(parents=True)
        self.qrun = self.root / 'q-runtime' / 'runs' / d.Q1_ID; self.qrun.mkdir(parents=True)
        archive = self.qrun / 'test-profile'; archive.mkdir(); (archive / 'settings.ini').write_text('archive')
        self.worker = {'pid': 90001, 'birth': 1, 'path': 'offline-old-worker'}
        game = {'pid': 90002, 'birth': 134377390166072988, 'path': str(self.root / 'SkyrimSE.exe')}
        self.qscenario = {'schemaVersion': 1, 'steps': [{'name': 'q-ready', 'tool': 'platform', 'args': {'operation': 'state.read'},
                                                     'assert': [{'path': 'world.ready', 'equals': True}]}]}
        qstate = {'id': d.Q1_ID, 'runner': self.worker, 'done': True, 'restored': True, 'restoreErrors': [],
                  'order': {'id': 'qualification-' + d.Q1_ID}, 'game': game, 'owned': [{'role': 'game', 'identity': game}],
                  'ownedGameRestartCount': 0, 'profileArchive': str(archive), 'testProfile': str(self.root / 'removed')}
        termination = {'kind': 'abnormal_exit', 'game': game, 'exitCode': 0xC0000005,
                       'identityVerified': True, 'ownQuitRequest': True, 'forcedGameStop': False,
                       'exitCodeAvailable': True, 'observationStage': 'owned-processes-ended'}
        qstate['gameTermination'] = termination
        bootstrap = {'name': 'new game world transition observed', 'result': 'passed',
                     'provenance': {'schemaVersion': 1, 'component': 'skyrim-autotest', 'stage': 'bootstrap',
                                    'role': 'tooling', 'runId': d.Q1_ID, 'checkId': 'new-game-world-transition'}}
        qstate['checks'] = [bootstrap]
        reason = 'All action checks completed; owned game shutdown was abnormal_exit (0xC0000005)'
        qstate.update(reason=reason, collectionComplete=True, collectionErrors=[])
        qplan = {'id': d.Q1_ID, 'executor': str(self.executor), 'executorPins': d.inventory(self.executor),
                 'configuration': {**m.read(self.config), 'runtime': str(self.root / 'q-runtime')}, 'scenario': self.qscenario,
                 'orderData': {'inputs': [d.file_pin(x) for x in [self.provider, self.ini, self.profile/'modlist.txt', self.profile/'plugins.txt', self.profile/'loadorder.txt']]}}
        qstate['configuration'] = {**qplan['configuration'], 'fixture_dir': None, 'collected_files': [], 'subject_state_bindings': {}}
        m.write(self.qrun / 'state.json', qstate)
        m.write(self.qrun / 'result.json', {'restored': True, 'result': 'failed', 'gameTermination': termination,
                                           'reason': reason, 'collectionComplete': True, 'collectionErrors': [],
                                           'checks': [bootstrap, {'name': 'q-ready', 'result': 'passed'}]})
        m.write(self.qfolder / 'worker.json', {'identity': self.worker}); m.write(self.qfolder / 'child-exit.json', {'returncode': 2})
        m.write(self.qfolder / 'plan.json', qplan)
        self.qpacket = {'kind': 'tool-qualification-result', 'id': d.Q1_ID, 'actualGameStarts': 1,
                        'executionOutcome': 'failed', 'restored': True, 'collectionFinished': True,
                        'collectionFindings': [], 'globalProviderQualified': False, 'runDirectory': str(self.qrun),
                        'cumulativeActualGameStartsAfter': None,
                        'profileArchivePins': [d.file_pin(archive / 'settings.ini')],
                        'files': [d.file_pin(x) for x in [self.qrun / 'state.json', self.qrun / 'result.json',
                                 self.qfolder / 'worker.json', self.qfolder / 'child-exit.json', self.qfolder / 'plan.json', archive / 'settings.ini']]}
        self.qpacket_path = self.root / 'q-packet.json'; m.write(self.qpacket_path, self.qpacket)
        with self.p.connect() as con:
            con.execute("INSERT INTO qualifications VALUES(?,?,'recorded',NULL,?)", (d.Q1_ID, json.dumps(qplan), json.dumps(d.file_pin(self.qpacket_path))))
            self.p.event(con, d.Q1_ID, 'qualification_prepared')
            self.p.event(con, d.Q1_ID, 'qualification_recorded')
            con.execute("INSERT INTO attempts VALUES(?,0)", ("qualification-" + d.Q1_ID,))
        self.p.hold_pipeline('qualification-' + d.Q1_ID, 'Exclusive qualification lease; retain after completion until owner-reviewed clearance')
        self.accounting = self.root / 'accounting.json'
        m.write(self.accounting, {'kind': 'diagnostic-task-start-accounting', 'cycleId': 'cycle', 'qualificationId': d.Q1_ID,
                                 'cumulativeActualGameStarts': None, 'actualGameStartsBefore': 1, 'maximumActualGameStarts': 2,
                                 'verifiedBy': 'offline', 'reason': 'One Q1 start; global historical count unknown'})
        self.fault = self.root / 'known-fault.json'; self.evidence = self.root / 'fault-evidence.txt'; self.evidence.write_text('Offline fault fixture')
        dump = self.root / 'native.dmp'; wer = self.root / 'Report.wer'; log = self.root / 'cdb.log'
        raw = bytearray(2048); raw[:4] = b'MDMP'; struct.pack_into('<II', raw, 8, 3, 32)
        for i, value in enumerate([(15, 24, 128), (6, 168, 160), (4, 112, 400)]):
            struct.pack_into('<3I', raw, 32+i*12, *value)
        struct.pack_into('<4I', raw, 128, 24, 3, game['pid'], game['birth']//10000000-11644473600)
        struct.pack_into('<I', raw, 168, 0xC0000005)
        struct.pack_into('<Q', raw, 184, 0x180000000 + 0x2EE3BA)
        struct.pack_into('<I', raw, 400, 1)
        struct.pack_into('<Q4I', raw, 404, 0x180000000, 0x7DB000, 0, 0x6AB9CB41, 600)
        name = str(self.provider).encode('utf-16-le'); struct.pack_into('<I', raw, 600, len(name)); raw[604:604+len(name)] = name
        cv = b'RSDS'+uuid.UUID('dc02441e-18cc-4bc5-b03a-9c4a5e3506ba').bytes_le+struct.pack('<I', 10)
        struct.pack_into('<II', raw, 404+76, len(cv), 1600); raw[1600:1600+len(cv)] = cv; dump.write_bytes(raw)
        guid = uuid.UUID(bytes=game['pid'].to_bytes(4,'big')+b'\0\1\1\xf5'+game['birth'].to_bytes(8,'little'))
        wer.write_text('AppSessionGuid='+str(guid)+'\nAppPath='+game['path'], encoding='utf-16')
        log.write_text('DeleteStringEntry BodyMorphInterface LdrShutdownProcess g_stringTable')
        m.write(self.fault, {'kind': 'known-external-shutdown-fault', 'qualificationId': d.Q1_ID, 'phase': 'ordinary-shutdown',
                            'module': d.file_pin(self.provider), 'evidence': [d.file_pin(dump), d.file_pin(wer), d.file_pin(log)],
                            'dump': d.file_pin(dump), 'wer': d.file_pin(wer), 'debuggerLog': d.file_pin(log),
                            'verifiedBy': 'offline fixture', 'reason': 'Fixture known shutdown fault'})
        archive = self.root / 'published.7z'; archive.write_bytes(b'published archive fixture')
        sidecar = self.root / 'published.7z.meta'; sidecar.write_bytes(b'original sidecar fixture')
        audit = self.root / 'audit.json'; m.write(audit, {'archive': d.file_pin(archive), 'expectedArchiveSha256Verified': True})
        intent = self.root / 'intent.json'
        m.write(intent, {'schemaVersion': 1, 'sourceChat': 'mod', 'sourceThreadId': 'origin',
                         'name': 'installed', 'liveWritesPerformed': False, 'gameStarted': False, 'raceMenuChanged': False,
                         'stagedAudit': d.file_pin(audit), 'sourceArchive': d.file_pin(archive), 'originalSidecar': {'pin': d.file_pin(sidecar)},
                         'writePaths': self.ticket['writePaths'], 'archiveInspection': {'fileCount': 10,
                         'payloadFiles': [{'path': x['source']['path'], 'sha256': x['source']['sha256'], 'destination': Path(x['target']).name} for x in self.installation]}})
        case = self.root / 'case-review.json'
        m.write(case, {'actualSlotRequest': {**d.file_pin(ticket), **self.ticket},
                       'authoritativeStagingAnchors': {'installation-plan.json': d.file_pin(intent), 'baseline-audit.json': d.file_pin(audit)}})
        for key, value in [('APPROVED_INSTALLATION_PLAN_SHA256', m.digest(intent)),
                           ('APPROVED_BASELINE_AUDIT_SHA256', m.digest(audit)), ('APPROVED_ARCHIVE_SHA256', m.digest(archive)),
                           ('APPROVED_CASE_REVIEW_SHA256', m.digest(case)), ('APPROVED_SLOT_REQUEST_SHA256', m.digest(ticket))]:
            previous_value = getattr(d, key); setattr(d, key, value); self.addCleanup(setattr, d, key, previous_value)
        draft = self.root / 'draft.json'; m.write(draft, self.order_template())
        for key, value in [('APPROVED_SUBJECT_DRAFT_SHA256', m.digest(draft)),
                           ('APPROVED_SUBJECT_SPECIFICATION_SHA256', m.subject_contract.subject_identity(self.order_template())),
                           ('APPROVED_SUBJECT_PLAN_SHA256', m.subject_contract.identity(self.order_template()['subjectPlan'])),
                           ('APPROVED_TESTING_SHA256', m.subject_contract.identity(self.order_template()['testing']))]:
            previous_value = getattr(d, key); setattr(d, key, value); self.addCleanup(setattr, d, key, previous_value)
        self.request = {'schemaVersion': 1, 'kind': 'one-shot-diagnostic-preparation', 'id': 'diag', 'slotId': 'slot',
                        'orderId': 'subject', 'cycleId': 'cycle', 'sourceChat': 'mod', 'sourceThreadId': 'origin',
                        'qualificationId': d.Q1_ID, 'qualificationPacket': d.file_pin(self.qpacket_path), 'executor': str(self.executor),
                        'installation': self.installation, 'protectedInputs': [d.file_pin(x) for x in [self.provider, self.profile/'plugins.txt', self.profile/'loadorder.txt']],
                        'taskAccounting': d.file_pin(self.accounting), 'knownFault': d.file_pin(self.fault),
                        'installationPlan': d.file_pin(intent), 'baselineAudit': d.file_pin(audit), 'prospectiveSubject': d.file_pin(draft),
                        'caseReview': d.file_pin(case),
                        'ownerAuthorization': self.auth, 'deadlineUtc': self.cycle['deadlineUtc'],
                        'verifiedBy': 'offline', 'reason': 'Exact bounded diagnostic, not qualification'}
        self.prepare_path = self.root / 'prepare.json'; m.write(self.prepare_path, self.request)

    def prepare(self):
        return d.prepare(self.p, self.prepare_path)

    def install_submit(self):
        slot = self.p.slots()[0]
        ack = {'schemaVersion': 1, 'slotId': 'slot', 'cycleId': 'cycle', 'iteration': 1, 'orderId': 'subject',
               'sourceChat': 'mod', 'sourceThreadId': 'origin', 'grantSha256': slot['grantSha256']}
        path = self.root / 'ack.json'; m.write(path, ack); self.p.acknowledge_slot('slot', path)
        for item in self.installation:
            Path(item['target']).write_bytes(Path(item['source']['path']).read_bytes())
        (self.root/'installed'/'meta.ini').write_text('[General]\ninstalled=true\n')
        (self.profile/'modlist.txt').write_text('+installed\n+original\n')
        self.order = self.order_template()
        path = self.root / 'subject.json'; m.write(path, self.order); self.p.submit(path)
        self.order = json.loads(self.p.get('subject')['request'])

    def order_template(self):
        return {'schemaVersion': 2, 'id': 'subject', 'mode': 'automatic', 'subject': 'Fixture mod',
                      'sourceChat': 'mod', 'sourceThreadId': 'origin', 'profile': 'Core', 'purpose': 'Core diagnostic',
                      'inputs': [{'path': x['target'], 'sha256': x['source']['sha256'], 'role': 'subject'} for x in self.installation],
                      'collect': ['state'], 'subjectPlan': {'interface': 'polygon-actions/1', 'fixture': {'cell': 'QASmoke', 'startMode': 'new-game'},
                      'steps': [{'name': 'subject-ready', 'operation': 'state.read', 'timeout': 10, 'assert': [{'field': 'world.ready', 'equals': True}]}]},
                      'testing': {'start': {'kind': 'check', 'name': 'subject-ready'}, 'checks': [{'name': 'subject-ready', 'role': 'subject'}]},
                      'cycle': {'id': 'cycle', 'scopeId': 'core', 'iteration': 1, 'buildId': 'release', 'slotId': 'slot'}}

    def freeze(self):
        operations = {'state.read': {'tool': 'platform', 'args': {'operation': 'state.read'}, 'fields': {'world.ready': 'world.ready'}}}
        manifest = self.root / 'diagnostic-platform.json'
        m.write(manifest, {'schemaVersion': 1, 'kind': 'one-shot-diagnostic-platform', 'qualified': False,
                          'interface': 'polygon-actions/1', 'config': str(self.config), 'inputs': [d.file_pin(self.provider)], 'operations': operations})
        scenario = m.subject_contract.compile_plan(self.order['subjectPlan'], operations)
        method = self.root / 'methods.json'
        m.write(method, {'schemaVersion': 1, 'kind': 'diagnostic-method-review', 'qualificationPacket': d.file_pin(self.qpacket_path),
                         'steps': [{'name': x['name'], 'compiledStepSha256': m.subject_contract.identity(x), 'methodStatus': 'observed-Q1',
                                    'nativeMethodCovered': True, 'reason': 'Same positive Q1 method/args'} for x in scenario['steps']],
                         'evidence': [d.file_pin(self.evidence)], 'verifiedBy': 'offline', 'reason': 'Actual method fixture'})
        self.freeze_path = self.root / 'freeze.json'
        receipt = self.root / 'receipt.json'
        receipt_data = {'kind': 'diagnostic-native-installation-receipt', 'preparationId': 'diag', 'slotId': 'slot',
                         'orderId': 'subject', 'sourceThreadId': 'origin', 'installationPlan': self.request['installationPlan'],
                         'baselineAudit': self.request['baselineAudit'], 'archiveInstalled': True, 'managerRefreshed': True,
                         'installationSettled': True, 'profile': 'Core', 'verifiedBy': 'offline', 'reason': 'Native boundary fixture',
                         'installedInputs': self.order['inputs'], 'vfsWinners': [{'path': x['target'], 'sha256': x['source']['sha256']} for x in self.installation],
                         'evidence': [d.file_pin(self.evidence)]}
        if hasattr(self, 'receipt_mutator'):
            self.receipt_mutator(receipt_data)
        m.write(receipt, receipt_data)
        m.write(self.freeze_path, {'schemaVersion': 1, 'kind': 'one-shot-diagnostic-freeze', 'id': 'diag',
                                  'subjectOrderSha256': m.subject_contract.identity(self.order), 'platform': d.file_pin(manifest),
                                  'installationReceipt': d.file_pin(receipt),
                                  'methodReview': d.file_pin(method), 'verifiedBy': 'offline', 'reason': 'Bounded subject diagnostic'})
        return d.freeze(self.p, self.freeze_path)

    def ready(self):
        self.prepare(); self.install_submit(); self.freeze()
        self.execute_path = self.root / 'execute.json'
        m.write(self.execute_path, {'schemaVersion': 1, 'kind': 'one-shot-diagnostic-execution', 'id': 'diag',
                                   'platformPlanSha256': m.subject_contract.identity(self.p.attempt_plan(self.order)),
                                   'verifiedBy': 'offline', 'reason': 'One immutable subject only'})

    def test_composed_ordinary_parent_child_semantics_collect_report_and_hold(self):
        self.ready()
        self.assertTrue(self.prepare()['duplicate'])
        self.assertEqual(d.show(self.p, 'diag')['retainedHoldId'], 'qualification-' + d.Q1_ID)
        packet = d.execute(self.p, self.execute_path)
        self.assertEqual(packet['executionOutcome'], 'failed')
        self.assertTrue(packet['restored']); self.assertEqual(packet['sourceThreadId'], 'origin')
        self.assertEqual(self.p.test_projection(self.order, packet)['coverage']['passed'], 1)
        self.assertNotEqual(self.p.test_projection(self.order, packet)['outcome'], 'tested_successfully')
        self.assertEqual((self.p.local / 'config.json').read_bytes(), self.host_bytes)
        self.assertEqual([x['id'] for x in self.p.pipeline_status()['holds']], ['qualification-' + d.Q1_ID])
        review = self.root / 'final.json'
        m.write(review, {'schemaVersion': 1, 'id': 'final', 'orderIds': ['subject'], 'collectionFinished': True,
                        'summary': 'Actual subject checks and external shutdown fault'})
        self.p.report_ready(review)
        self.assertEqual(self.p.pending()[0]['threadId'], 'origin')
        self.assertFalse(d.execute(self.p, self.execute_path)['rerun'])
        self.assertEqual(len(self.p.matching_runs(self.order)), 1)
        self.assertFalse(self.p.attempt_plan(self.order)['qualified'])
        with self.p.connect() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM attempts WHERE id='subject'").fetchone()[0], 1)
        completion = self.root / 'complete.json'
        m.write(completion, {'schemaVersion': 1, 'kind': 'one-shot-diagnostic-completion', 'orderId': 'subject',
                            'packet': d.file_pin(self.p.get('subject')['packet']), 'verifiedBy': 'offline', 'reason': 'Explicit ended packet review'})
        self.assertEqual(d.complete(self.p, completion)['actualGameStarts'], 1)
        self.assertFalse(d.execute(self.p, self.execute_path)['rerun'])

    def test_normal_routes_still_refuse_unqualified_held_order(self):
        self.ready()
        self.assertEqual(self.p.grant_slot()['status'], 'pipeline_held'); self.assertIsNone(self.p.claim())
        with self.assertRaises(ValueError):
            self.p.check_launch_authorization(self.order)
        # Even independent hold removal cannot expose this registered diagnostic to normal next.
        with self.p.connect() as con:
            con.execute('DELETE FROM pipeline_holds')
        self.assertIsNone(self.p.claim())
        with self.assertRaises(ValueError):
            d.execute(self.p, self.execute_path)

    def test_foreign_hold_fifo_owner_worker_and_budget_fail_before_grant(self):
        for mutation in ['foreign', 'fifo', 'worker', 'budget', 'owner']:
            with self.subTest(mutation=mutation):
                if mutation == 'foreign':
                    self.p.hold_pipeline('foreign', 'Unknown'); self.addCleanup(lambda: None)
                elif mutation == 'fifo':
                    with self.p.connect() as con:
                        con.execute("UPDATE cycle_slots SET order_id='different' WHERE id='slot'")
                elif mutation == 'budget':
                    value = m.read(self.accounting); value['actualGameStartsBefore'] = 0; m.write(self.accounting, value)
                    self.request['taskAccounting'] = d.file_pin(self.accounting); m.write(self.prepare_path, self.request)
                elif mutation == 'owner':
                    self.owner.write_text('changed')
                with patch.dict(os.environ, {'OFFLINE_NATIVE_ALIVE': '1'} if mutation == 'worker' else {}, clear=False):
                    with self.assertRaises(ValueError):
                        self.prepare()
                with self.p.connect() as con:
                    self.assertEqual(con.execute('SELECT COUNT(*) FROM diagnostic_admissions').fetchone()[0], 0)
                if mutation == 'foreign':
                    with self.p.connect() as con: con.execute("DELETE FROM pipeline_holds WHERE id='foreign'")
                elif mutation == 'fifo':
                    with self.p.connect() as con: con.execute("UPDATE cycle_slots SET order_id='subject' WHERE id='slot'")
                elif mutation == 'budget':
                    value['actualGameStartsBefore'] = 1; m.write(self.accounting, value)
                    self.request['taskAccounting'] = d.file_pin(self.accounting); m.write(self.prepare_path, self.request)
                elif mutation == 'owner': self.owner.write_text('Run the bounded stock baseline')

    def test_changed_install_source_or_provider_refuses_freeze(self):
        self.prepare(); self.install_submit()
        Path(self.installation[0]['target']).write_bytes(b'wrong')
        with self.assertRaises(ValueError): self.freeze()
        Path(self.installation[0]['target']).write_bytes(Path(self.installation[0]['source']['path']).read_bytes())
        self.provider.write_bytes(b'changed')
        with self.assertRaises(ValueError): self.freeze()

    def test_unknown_native_method_cannot_be_asserted_covered_by_review(self):
        self.prepare(); self.install_submit()
        with self.p.connect() as con:
            order = json.loads(con.execute("SELECT request FROM jobs WHERE id='subject'").fetchone()[0])
            order['subjectPlan']['steps'][0]['operation'] = 'world.read'
            order['subjectPlan']['steps'][0]['parameters'] = {'request': {'domain': 'uncovered-native-method'}}
            con.execute("UPDATE jobs SET request=? WHERE id='subject'", (json.dumps(order),))
        self.order = order
        with self.assertRaises(ValueError): self.freeze()

    def test_sole_known_fault_requires_bootstrap_clean_actions_full_identity(self):
        d.order_platform.activate(str(self.executor))
        original_state = m.read(self.qrun / 'state.json'); original_result = m.read(self.qrun / 'result.json')
        qplan = m.read(self.qfolder / 'plan.json')
        bf.verify(self.request, original_state, original_result, qplan)
        for mutation in ('bootstrap', 'extra', 'action', 'fault', 'reason', 'forced', 'birth', 'collection'):
            with self.subTest(mutation=mutation):
                state, result = copy.deepcopy(original_state), copy.deepcopy(original_result)
                if mutation == 'bootstrap': result['checks'].pop(0)
                elif mutation == 'extra': result['checks'].append({'name': 'unknown', 'result': 'passed'})
                elif mutation == 'action': result['checks'][-1]['result'] = 'failed'
                elif mutation == 'fault': state['fault'] = {'code': 'another fault'}
                elif mutation == 'reason': state['reason'] = 'mid-test crash'
                elif mutation == 'forced':
                    state['gameTermination']['forcedGameStop'] = result['gameTermination']['forcedGameStop'] = True
                elif mutation == 'birth':
                    state['game']['birth'] += 1
                    state['gameTermination']['game']['birth'] = result['gameTermination']['game']['birth'] = state['game']['birth']
                else: result['collectionErrors'] = ['missing evidence']
                with self.assertRaises(ValueError): bf.verify(self.request, state, result, qplan)

    def test_lease_clear_recreate_later_attempt_or_qualification_cannot_reset_first_shot(self):
        for mutation in ('cleared', 'ordinary', 'qualification'):
            with self.subTest(mutation=mutation):
                with self.p.connect() as con:
                    if mutation == 'cleared': self.p.event(con, 'qualification-' + d.Q1_ID, 'pipeline_cleared')
                    elif mutation == 'ordinary': con.execute("INSERT INTO attempts VALUES('other-native',1)")
                    else: self.p.event(con, 'later-q2', 'qualification_prepared')
                with self.assertRaises(ValueError): self.prepare()
                with self.p.connect() as con:
                    if mutation == 'cleared': con.execute("DELETE FROM events WHERE status='pipeline_cleared'")
                    elif mutation == 'ordinary': con.execute("DELETE FROM attempts WHERE id='other-native'")
                    else: con.execute("DELETE FROM events WHERE id='later-q2'")
        changed = copy.deepcopy(self.request); changed['qualificationId'] = 'later-q2'
        with self.p.connect() as con:
            with self.assertRaisesRegex(ValueError, 'first Q1'):
                d._authority(self.p, {**changed, 'requestPin': d.file_pin(self.prepare_path)}, con)

    def test_executor_replacement_is_rejected_before_activating_its_code(self):
        alternate = self.root / 'replacement'; alternate.mkdir(); (alternate / 'skyrim_autotest').mkdir()
        (alternate / 'skyrim_autotest/runner.py').write_text('raise RuntimeError("must never import")')
        self.request['executor'] = str(alternate); m.write(self.prepare_path, self.request)
        with patch.object(d.order_platform, 'activate') as activate:
            with self.assertRaises(ValueError): self.prepare()
            activate.assert_not_called()

    def test_configuration_change_other_than_reviewed_delta_refuses(self):
        self.prepare(); self.install_submit()
        cfg = m.read(self.config); cfg['native_session'] = {'unreviewed': True}; m.write(self.config, cfg)
        with self.assertRaisesRegex(ValueError, 'configuration|bindings'):
            self.freeze()

    def test_incomplete_native_installation_receipt_refuses_freeze(self):
        self.prepare(); self.install_submit()
        self.receipt_mutator = lambda x: x.pop('archiveInstalled')
        with self.assertRaisesRegex(ValueError, 'receipt'):
            self.freeze()

    def test_eleventh_payload_and_unapproved_archive_plan_refused(self):
        changed = copy.deepcopy(self.request); changed['installation'].append(copy.deepcopy(changed['installation'][0]))
        m.write(self.prepare_path, changed)
        with self.assertRaisesRegex(ValueError, 'ten'):
            self.prepare()
        m.write(self.prepare_path, self.request)
        intent = d.read_pin(self.request['installationPlan']); intent['name'] = 'other'
        target = self.root / 'unapproved-intent.json'; m.write(target, intent)
        changed = copy.deepcopy(self.request); changed['installationPlan'] = d.file_pin(target); m.write(self.prepare_path, changed)
        with self.assertRaisesRegex(ValueError, 'agreed|Agreed'):
            self.prepare()

    def test_lost_response_timeout_cannot_launch_again_or_infer_zero(self):
        self.ready()
        with patch.object(d.subprocess, 'run', side_effect=subprocess.TimeoutExpired('offline child', 900)):
            result = d.execute(self.p, self.execute_path)
        self.assertEqual(result['status'], 'running')
        self.assertFalse(d.execute(self.p, self.execute_path)['rerun'])
        self.assertIsNone(self.p.claim())
        self.assertIsNone(d.saved(self.p, 'subject')['actual_starts'])
        self.assertFalse(self.p.matching_runs(self.order))

    def test_consumed_review_cannot_change_and_expired_authority_refuses(self):
        self.ready()
        with self.p.connect() as con:
            approval = json.loads(con.execute("SELECT authorization FROM cycles WHERE id='cycle'").fetchone()[0])
            approval['deadlineUtc'] = time.time() - 1
            con.execute("UPDATE cycles SET authorization=? WHERE id='cycle'", (json.dumps(approval),))
        with self.assertRaises(ValueError): d.execute(self.p, self.execute_path)
        self.assertEqual(d.saved(self.p, 'subject')['status'], 'frozen')

    def test_exact_werewolf_subject_target_delta_preserves_all_other_guards(self):
        before = {'runtime': 'old', 'native_session': {'nativeBindings': {'allowedRaceForms': ['0x00013746', '0x00013741'], 'guard': 'same'}}}
        after = copy.deepcopy(before); after['runtime'] = 'new'
        after['native_session']['nativeBindings']['allowedRaceForms'].append('0x000CDD84')
        step = {'name': 'beast', 'tool': 'platform', 'args': {'operation': 'object.perform', 'request': {
            'domain': 'actor-race', 'action': 'change-current-race', 'race': '0x000CDD84',
            'actor': {'fixtureTag': 'MHeavy'}, 'preserveBaseRecord': True}}}
        scenario = {'steps': [step]}; proof = {'steps': [{'methodStatus': 'reviewed-diagnostic-target'}]}
        delta = d._configuration_delta(before, after, scenario, proof)
        self.assertFalse(delta['werewolfBusinessResultQualified'])
        for mutation in ('race', 'guard', 'actor', 'status'):
            with self.subTest(mutation=mutation):
                candidate, sc, pr = copy.deepcopy(after), copy.deepcopy(scenario), copy.deepcopy(proof)
                if mutation == 'race': candidate['native_session']['nativeBindings']['allowedRaceForms'].append('0x12345678')
                elif mutation == 'guard': candidate['native_session']['nativeBindings']['guard'] = 'weakened'
                elif mutation == 'actor': sc['steps'][0]['args']['request']['actor']['fixtureTag'] = 'unowned'
                else: pr['steps'][0]['methodStatus'] = 'observed-Q1'
                with self.assertRaises(ValueError): d._configuration_delta(before, candidate, sc, pr)
        with self.assertRaisesRegex(ValueError, 'lacks'):
            d._configuration_delta(before, before, scenario, proof)

    def test_cancelled_older_waiting_slot_is_skipped_but_active_older_keeps_fifo(self):
        approval = {**self.cycle, 'id': 'older'}
        ticket = {**self.ticket, 'id': 'older-slot', 'cycleId': 'older', 'orderId': 'older-order'}
        with self.p.connect() as con:
            con.execute("INSERT INTO cycles VALUES(?,?,'active','')", ('older', json.dumps(approval)))
            con.execute("INSERT INTO cycle_slots(seq,id,cycle_id,iteration,order_id,request,status) VALUES(0,'older-slot','older',1,'older-order',?,'waiting')", (json.dumps(ticket),))
        with self.assertRaisesRegex(ValueError, 'oldest'):
            self.prepare()
        with self.p.connect() as con: con.execute("UPDATE cycles SET status='cancelled' WHERE id='older'")
        self.prepare()
        with self.p.connect() as con:
            row = con.execute("SELECT * FROM cycle_slots WHERE id='older-slot'").fetchone()
            self.assertEqual(row['status'], 'cancelled'); self.assertEqual(json.loads(row['request']), ticket)
            self.assertTrue(con.execute("SELECT seq FROM events WHERE id='older-slot' AND status='diagnostic_skipped_inactive_waiting_slot'").fetchone())

    def test_broad_profile_side_effect_scope_does_not_exempt_plugins_or_extra_dll(self):
        self.prepare(); self.install_submit()
        (self.profile/'plugins.txt').write_text('changed-provider.esp')
        with self.assertRaises(ValueError): self.freeze()
        (self.profile/'plugins.txt').write_text('original.esp\n')
        (self.root/'installed'/'unexpected.dll').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'exactly ten'):
            self.freeze()

    def test_malformed_dump_module_count_and_string_spans_refuse(self):
        fault = d.read_pin(self.request['knownFault']); original = Path(fault['dump']['path']).read_bytes()
        state = m.read(self.qrun/'state.json')
        for mutation in ('count', 'name', 'cv', 'misc-size', 'exception-size'):
            raw = bytearray(original)
            if mutation == 'count': struct.pack_into('<I', raw, 400, 0xFFFFFFFF)
            elif mutation == 'name': struct.pack_into('<I', raw, 600, 0x7FFF)
            elif mutation == 'cv': struct.pack_into('<II', raw, 404+76, 5000, 2000)
            elif mutation == 'misc-size': struct.pack_into('<I', raw, 36, 8)
            else: struct.pack_into('<I', raw, 48, 24)
            with self.assertRaises(ValueError): bf._dump(raw, str(self.provider), state['game'])


if __name__ == '__main__':
    unittest.main()

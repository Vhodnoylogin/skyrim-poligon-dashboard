"""Offline ended late-dispatch diagnostics; no native application is executed."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import polygon as m
import qualification_diagnostic as q
import test_qualification_diagnostic as fixtures


class LateGateTests(unittest.TestCase):
    def setUp(self):
        f = self.f = fixtures.HeldDiagnosticTests(); f.setUp(); self.addCleanup(f.doCleanups)
        f.plan['configuration']['mo2_ini'] = str(f.ini)
        if not any(pin['path'] == str(f.ini) for pin in f.plan['pins']):
            f.plan['pins'].append(f.pin(f.ini))
        other = f.root / 'older-source' / 'polygon.py'; other.parent.mkdir(); other.write_text('# earlier pinned source')
        f.plan['pins'].append(f.pin(other))
        component_plan = f.root / 'component-plan.json'
        m.write(component_plan, {'schemaVersion': 1, 'checks': [{'name': 'manual-owner-scene', 'role': 'subject'}]})
        sequencer, transport = f.root / 'sequencer.py', f.root / 'subject_companion.py'
        sequencer.write_text('def run(exchange, emit):\n return {}\n')
        transport.write_text('# Historical transport never started; no official report\n')
        f.plan['companion'] = {'maximumSeconds': 3600, 'plan': f.pin(component_plan),
                               'sequencer': f.pin(sequencer), 'transport': f.pin(transport)}
        f.plan['pins'].extend(f.pin(path) for path in (component_plan, sequencer, transport))
        f.state.update(game=f.game, result='failed', ownedGameRestartCount=0)
        m.write(f.run / 'state.json', f.state)
        (f.run / 'steps.jsonl').write_text('')
        f.review.update(state=f.pin(f.run / 'state.json'), exactSingleStartReviewed=True,
            observedGameIdentities=[f.game], observedMinimumActualGameStarts=1,
            observedIdentityEvidence=f.review['observedIdentityEvidence'][:1])
        f.plan['cumulativeActualGameStartsBefore'] = None
        m.write(f.folder / 'plan.json', f.plan)
        with f.p.connect() as con:
            con.execute('UPDATE qualifications SET request=? WHERE id=?', (json.dumps(f.plan, sort_keys=True), f.identity))
        message = 'Qualification pin changed: ' + str(f.ini)
        dispatch = f.folder / 'subject-companion' / 'dispatch.json'
        m.write(dispatch, {'schemaVersion': 1, 'orderId': 'qualification-' + f.identity,
            'qualificationId': f.identity, 'worker': f.worker, 'error': 'ValueError: ' + message,
            'errorDetails': {'operation': 'qualification-companion', 'traceback':
                'Traceback (most recent call last):\n  File "' + str(m.HERE / 'qualification_companion.py') +
                '", line 154, in companion\n  File "' + str(m.HERE / 'qualification.py') +
                '", line 67, in qualification_verify\nValueError: ' + message + '\n'}})
        receipt_path = Path(f.review['originalDashboardExport']['path']); receipt = m.read(receipt_path)
        receipt.update(planSha256=m.digest(f.folder / 'plan.json'), executedDashboardRoot=str(m.HERE),
                       executionEvidence=f.pin(dispatch))
        m.write(receipt_path, receipt); f.review['originalDashboardExport'] = f.pin(receipt_path)
        raw = f.root / 'standalone-report.json'
        m.write(raw, {'actions': [{'status': 'completed'} for _ in range(62)], 'completed': False})
        f.review['additionalEvidencePins'] = [f.pin(raw)]

    def test_records_failed_single_start_without_adopting_standalone_companion(self):
        f = self.f; packet = f.record()
        self.assertEqual(packet['actualGameStarts'], 1)
        self.assertEqual(packet['observedMinimumActualGameStarts'], 1)
        self.assertIsNone(packet['cumulativeActualGameStartsBefore'])
        self.assertIsNone(packet['cumulativeActualGameStartsAfter'])
        self.assertEqual(packet['executionOutcome'], 'failed')
        self.assertFalse(packet['qualificationPassed'])
        self.assertNotIn('toolCompanion', packet)
        self.assertEqual(packet['testResult']['coverage']['performed'], 0)
        self.assertEqual(len(f.p.pipeline_status()['holds']), 1)
        self.assertEqual(f.p.qualification_show(f.identity)['status'], 'recorded')
        self.assertFalse((f.folder / 'subject-companion' / 'report.json').exists())
        self.assertEqual(f.p.qualification_collect(f.identity), packet)
        self.assertEqual(f.record(), packet)

    def test_diagnostic_does_not_invoke_official_companion_collector(self):
        f = self.f; packet = f.record()
        with patch('qualification_companion.verify_packet', side_effect=AssertionError('No official client existed')) as verify:
            self.assertEqual(f.p.qualification_collect(f.identity), packet)
        verify.assert_not_called()

    def test_normal_companion_packet_still_uses_strict_official_collector(self):
        f = self.f; packet = f.record()
        packet = dict(packet, kind='tool-qualification-result')
        normal = f.folder / 'normal-packet.json'; m.write(normal, packet)
        with f.p.connect() as con:
            con.execute('UPDATE qualifications SET packet=? WHERE id=?',
                        (json.dumps(f.pin(normal)), f.identity))
        with patch('qualification_companion.verify_packet', side_effect=ValueError('Official companion evidence missing')) as verify:
            with self.assertRaisesRegex(ValueError, 'Official companion evidence missing'):
                f.p.qualification_collect(f.identity)
        verify.assert_called_once()

    def test_diagnostic_code_snapshot_tamper_still_refuses(self):
        f = self.f; packet = f.record()
        Path(packet['implementationSnapshotPins'][0]['path']).write_text('changed diagnostic implementation')
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            f.p.qualification_collect(f.identity)

    def test_diagnostic_archive_membership_change_still_refuses(self):
        f = self.f; f.record()
        (f.archive / 'added.ini').write_text('new archive member')
        with self.assertRaisesRegex(ValueError, 'archive membership'):
            f.p.qualification_collect(f.identity)

    def test_diagnostic_packet_tamper_still_refuses(self):
        f = self.f; packet = f.record()
        path = f.folder / 'held-diagnostic.json'
        m.write(path, dict(packet, qualificationPassed=True))
        with self.assertRaisesRegex(ValueError, 'Qualification result changed'):
            f.p.qualification_collect(f.identity)

    def test_wrong_selected_root_or_traceback_refuses(self):
        f = self.f; path = Path(f.review['originalDashboardExport']['path']); original = m.read(path)
        for change in ('root', 'traceback'):
            receipt = copy.deepcopy(original)
            if change == 'root': receipt['executedDashboardRoot'] = str(f.root / 'older-source')
            else:
                dispatch = Path(receipt['executionEvidence']['path']); value = m.read(dispatch)
                value['errorDetails']['traceback'] = value['errorDetails']['traceback'].replace('qualification_verify', 'other')
                m.write(dispatch, value); receipt['executionEvidence'] = f.pin(dispatch)
            m.write(path, receipt); f.review['originalDashboardExport'] = f.pin(path)
            with self.assertRaisesRegex(ValueError, 'executed late companion-gate'): f.record()

    def test_changed_unselected_historical_root_remains_pinned(self):
        f = self.f; (f.root / 'older-source' / 'polygon.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'pin mismatch'): f.record()

    def test_single_count_refuses_second_observed_game(self):
        f = self.f
        f.review['observedGameIdentities'].append(f.second)
        f.review['observedMinimumActualGameStarts'] = 2
        f.review['observedIdentityEvidence'].append({'identity': f.second,
            'evidence': f.review['accountingEvidence'][0], 'locator': 'second identity'})
        with self.assertRaisesRegex(ValueError, 'single failed native start'): f.record()

    def test_supplemental_raw_evidence_remains_immutable(self):
        f = self.f; f.record()
        Path(f.review['additionalEvidencePins'][0]['path']).write_text('changed')
        with self.assertRaisesRegex(ValueError, 'evidence changed'): f.p.qualification_collect(f.identity)

    def test_additional_exact_process_must_be_dead(self):
        f = self.f; f.review['additionalDeadIdentities'] = [f.second]
        f.native.alive = lambda identity: identity == f.second
        with self.assertRaisesRegex(ValueError, 'remains alive'): f.record()

    def test_operational_mo2_settings_are_verified_then_frozen_for_history(self):
        f = self.f; original = f.ini.read_bytes(); packet = f.record()
        self.assertNotIn(str(f.ini), {pin['path'] for pin in packet['files']})
        retained = next(row for row in packet['originalInputSnapshots'] if row['original']['path'] == str(f.ini))
        self.assertEqual(Path(retained['snapshot']['path']).read_bytes(), original)
        f.ini.write_text('later separately authorized profile selection')
        self.assertEqual(f.p.qualification_collect(f.identity), packet)

    def test_mo2_settings_change_between_original_verification_and_snapshot_refuses(self):
        f = self.f
        original = q._sources

        def sources(*args):
            result = original(*args)
            f.ini.write_text('MO2 serialized settings after original pin verification')
            return result

        with patch.object(q, '_sources', side_effect=sources):
            with self.assertRaisesRegex(ValueError, 'Original diagnostic input changed during review'):
                f.record()
        self.assertEqual(f.p.qualification_show(f.identity)['status'], 'running')
        self.assertEqual(len(f.p.pipeline_status()['holds']), 1)


if __name__ == '__main__': unittest.main()

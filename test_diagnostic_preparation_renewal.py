"""Composed renewal boundary tests; temporary SQLite and fake native observers only."""
import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import unittest
from unittest.mock import patch

import diagnostic_admission as d
import diagnostic_preparation_renewal as renewal
import diagnostic_recovery as r
import polygon as m
import test_diagnostic_recovery as fixture


class PreparationRenewalTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.RecoveryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.p = self.fixture.root, self.fixture.p
        self.review = {
            'schemaVersion': 1, 'kind': 'diagnostic-preparation-renewal',
            'id': 'renewal-one', 'diagnosticId': 'diag',
            'previousReview': d.file_pin(self.fixture.path),
            'previousCycleAuthorizationSha256': r._hash(self.fixture.original_cycle['authorization']),
            'ownerAuthorization': copy.deepcopy(self.fixture.base.auth),
            'deadlineUtc': self.fixture.base.cycle['deadlineUtc'] + 3600,
            'verifiedBy': 'offline renewal reviewer',
            'reason': 'Renew only preparation authority, retaining the original test and allowance',
        }
        self.path = self.root / 'renewal-review.json'
        m.write(self.path, self.review)
        self.before = self.state()
        database_files = {str(self.p.db) + suffix for suffix in ('', '-wal', '-shm', '-journal')}
        self.original_files = {p: p.read_bytes() for p in self.root.rglob('*')
                               if p.is_file() and str(p) not in database_files}

    def state(self):
        with self.p.connect() as con:
            tables = [x[0] for x in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            return {name: [dict(x) for x in con.execute('SELECT * FROM ' + name + ' ORDER BY rowid')]
                    for name in tables}

    def renew(self):
        return renewal.renew(self.p, self.path)

    def saved_request(self):
        with self.p.connect() as con:
            return json.loads(con.execute("SELECT request FROM diagnostic_admissions WHERE id='diag'").fetchone()[0])

    def assert_preserved_success(self, result):
        after = self.state()
        for name, rows in self.before.items():
            if name not in ('diagnostic_admissions', 'cycles', 'events'):
                self.assertEqual(after[name], rows, name)
        self.assertEqual(len(after['events']), len(self.before['events']) + 1)
        self.assertEqual(after['events'][:-1], self.before['events'])
        self.assertEqual(after['events'][-1]['id'], 'diag')
        self.assertEqual(after['events'][-1]['status'], 'diagnostic_preparation_renewed')
        diagnostic = copy.deepcopy(after['diagnostic_admissions'])
        diagnostic[0]['request'] = self.before['diagnostic_admissions'][0]['request']
        self.assertEqual(diagnostic, self.before['diagnostic_admissions'])
        cycle = copy.deepcopy(after['cycles'])
        expected_authority = json.loads(self.before['cycles'][0]['authorization'])
        expected_authority.update(ownerAuthorization=self.review['ownerAuthorization'],
                                  deadlineUtc=self.review['deadlineUtc'])
        self.assertEqual(json.loads(cycle[0]['authorization']), expected_authority)
        cycle[0]['authorization'] = self.before['cycles'][0]['authorization']
        self.assertEqual(cycle, self.before['cycles'])
        for path, raw in self.original_files.items():
            self.assertEqual(path.read_bytes(), raw, str(path.relative_to(self.root)))
        certificate = d.read_pin(result['certificate'])
        self.assertEqual(certificate['previous']['diagnostic'], self.before['diagnostic_admissions'][0])
        self.assertEqual(certificate['previous']['cycle'], self.before['cycles'][0])
        self.assertEqual(certificate['previous']['job'], self.before['jobs'][0])
        self.assertEqual(certificate['previous']['slot'], self.before['cycle_slots'][0])
        self.assertTrue(certificate['historicalPhysicalStartsPreserved'])
        self.assertFalse(certificate['subjectChanged'])
        self.assertFalse(certificate['launchGranted'])
        self.assertFalse(certificate['installationGranted'])
        self.assertFalse(result['launchGranted'])
        self.assertFalse(result['newInstallationGranted'])
        self.assertTrue(result['holdRetained'])
        self.assertIsNone(after['diagnostic_admissions'][0]['actual_starts'])

    def test_success_preserves_subject_slot_payload_accounting_and_retains_old_generation(self):
        result = self.renew()
        self.assert_preserved_success(result)
        request = self.saved_request()
        renewal.validate_request(request)
        self.assertEqual(d._request({'request': json.dumps(request)}), request)
        self.assertEqual(request['taskAccounting'], json.loads(
            self.before['diagnostic_admissions'][0]['request'])['taskAccounting'])

    def test_duplicate_keeps_exact_registered_certificate_and_creates_no_events(self):
        first = self.renew()
        raw = Path(first['certificate']['path']).read_bytes()
        after = self.state()
        second = self.renew()
        self.assertTrue(second['duplicate'])
        self.assertFalse(second['launchGranted'])
        self.assertEqual(self.state(), after)
        self.assertEqual(Path(first['certificate']['path']).read_bytes(), raw)
        changed = copy.deepcopy(self.review)
        changed['deadlineUtc'] += 1
        m.write(self.path, changed)
        with self.assertRaises(ValueError):
            self.renew()
        self.assertEqual(self.state(), after)

    def test_wrong_prior_hash_authority_or_source_provenance_refuses_without_db_changes(self):
        for field in ('previousReview', 'previousCycleAuthorizationSha256', 'ownerAuthorization'):
            bad = copy.deepcopy(self.review)
            if field == 'previousCycleAuthorizationSha256':
                bad[field] = '0' * 64
            else:
                bad[field]['sha256'] = '0' * 64
            m.write(self.path, bad)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.renew()
            self.assertEqual(self.state(), self.before)
        m.write(self.path, self.review)
        source = next(self.fixture.legacy_source.glob('*.py'))
        old = source.read_bytes()
        source.write_bytes(old + b'\n# provenance changed\n')
        try:
            with self.assertRaises(ValueError):
                self.renew()
            self.assertEqual(self.state(), self.before)
        finally:
            source.write_bytes(old)

    def test_consumed_or_factual_start_evidence_never_becomes_a_fresh_preparation(self):
        mutations = (
            "UPDATE diagnostic_admissions SET status='frozen' WHERE id='diag'",
            "UPDATE diagnostic_admissions SET plan='{}' WHERE id='diag'",
            "UPDATE diagnostic_admissions SET actual_starts=1 WHERE id='diag'",
            "INSERT INTO attempts VALUES('subject',1)",
            "INSERT INTO events(id,status,note,at) VALUES('subject','testing_started','factual fixture',1)",
        )
        for mutation in mutations:
            with self.p.connect() as con:
                con.execute(mutation)
            changed = self.state()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.renew()
            self.assertEqual(self.state(), changed)
            with self.p.connect() as con:
                con.execute("UPDATE diagnostic_admissions SET status='preparing',plan=NULL,actual_starts=NULL WHERE id='diag'")
                con.execute("DELETE FROM attempts WHERE id='subject'")
                con.execute("DELETE FROM events WHERE id='subject' AND status='testing_started'")

    def test_post_certificate_failure_rolls_back_and_retry_retains_orphan_bytes(self):
        original = d._native_closed
        observation = [0]
        def fresh_observation(*args, **kwargs):
            value = original(*args, **kwargs)
            observation[0] += 1
            value['observedAt'] = 100.0 + observation[0]
            return value
        with patch.object(d, '_native_closed', side_effect=fresh_observation):
            with patch.object(d, '_authority', side_effect=ValueError('injected after certificate write')):
                with self.assertRaisesRegex(ValueError, 'injected after certificate'):
                    self.renew()
            self.assertEqual(self.state(), self.before)
            artifacts = list((self.p.local / 'diagnostic-preparation-generations').glob('*.json'))
            self.assertEqual(len(artifacts), 1)
            orphan = artifacts[0]
            old_bytes = orphan.read_bytes()
            result = self.renew()
        self.assertNotEqual(Path(result['certificate']['path']), orphan)
        self.assertEqual(orphan.read_bytes(), old_bytes)
        self.assertEqual(len(list(orphan.parent.glob('*.json'))), 2)
        self.assert_preserved_success(result)

    def test_registered_certificate_tampering_refuses_validation_and_duplicate(self):
        result = self.renew()
        path = Path(result['certificate']['path'])
        original = path.read_bytes()
        request, after = self.saved_request(), self.state()
        path.write_bytes(original + b'\n')
        for action in (lambda: renewal.validate_request(request), self.renew):
            with self.assertRaises(ValueError):
                action()
            self.assertEqual(self.state(), after)
        path.write_bytes(original)
        renewal.validate_request(request)

    def test_request_validation_binds_authority_deadline_and_source_pins(self):
        self.renew()
        request = self.saved_request()
        for field in ('deadlineUtc', 'ownerAuthorization', 'dashboardPins', 'reviewPins'):
            changed = copy.deepcopy(request)
            if field == 'deadlineUtc':
                changed[field] += 1
            elif field == 'ownerAuthorization':
                changed[field]['messageId'] = 'different-human'
            else:
                changed[field] = changed[field][:-1]
            with self.subTest(field=field), self.assertRaises(ValueError):
                renewal.validate_request(changed)
        renewal.validate_request(request)

    def test_review_requires_exact_fields_and_integer_schema(self):
        for change in ({'unexpected': True}, {'schemaVersion': True}):
            bad = {**copy.deepcopy(self.review), **change}
            m.write(self.path, bad)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.renew()
            self.assertEqual(self.state(), self.before)

    def test_renewal_cannot_introduce_a_new_released_work_deferral(self):
        path = self.root / 'invented-deferral.json'
        m.write(path, {'kind': 'unused synthetic deferral'})
        bad = {**self.review, 'releasedWorkDeferral': d.file_pin(path)}
        m.write(self.path, bad)
        with self.assertRaisesRegex(ValueError, 'cannot create'):
            self.renew()
        self.assertEqual(self.state(), self.before)

    def test_cli_dispatches_reviewed_renewal_without_launch(self):
        output = io.StringIO()
        with redirect_stdout(output):
            status = m.main(['--root', str(self.root), 'diagnostic-preparation-renew', str(self.path)])
        self.assertEqual(status, 0)
        result = json.loads(output.getvalue())
        self.assert_preserved_success(result)


if __name__ == '__main__':
    unittest.main()

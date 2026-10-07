"""Single-order capacity is independent of shared sessions and execution authority."""
import copy
import unittest

import subject_contract as contract
import test_subject_contract as fixtures
import test_shared_sessions as shared

mod = fixtures.mod


class SubjectCapacity(unittest.TestCase):
    def fixture(self):
        fixture = fixtures.SeparationTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def plan(self, fixture, count):
        plan = copy.deepcopy(fixture.order['subjectPlan'])
        step = plan['steps'][0]
        plan['steps'] = [{**copy.deepcopy(step), 'name': f'check-{i}'} for i in range(count)]
        if count:
            plan['steps'][0]['name'] = step['name']
        return plan

    def test_single_capacity_boundaries_compile_without_changing_timing_or_subject(self):
        fixture = self.fixture()
        for count in (1, 256, 257, 457, 512):
            with self.subTest(count=count):
                plan = self.plan(fixture, count)
                original = copy.deepcopy(plan)
                scenario = contract.compile_plan(plan, fixture.operations)
                self.assertEqual(len(scenario['steps']), count)
                self.assertTrue(all(s['timeout'] == 10 for s in scenario['steps']))
                self.assertEqual(plan, original)
        for count in (0, 513):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, '1..512'):
                contract.validate(self.plan(fixture, count))

    def test_last_step_at_capacity_retains_deadline_and_unique_name_validation(self):
        fixture = self.fixture()
        plan = self.plan(fixture, 512)
        plan['steps'][-1]['timeout'] = 180
        contract.validate(plan)
        for value in (0, 180.001, float('inf'), float('nan'), True):
            plan['steps'][-1]['timeout'] = value
            with self.subTest(timeout=value), self.assertRaisesRegex(ValueError, 'timeout'):
                contract.validate(plan)
        plan['steps'][-1]['timeout'] = 180
        plan['steps'][-1]['name'] = plan['steps'][0]['name']
        with self.assertRaisesRegex(ValueError, 'unique'):
            contract.validate(plan)

    def test_large_submission_still_requires_release_and_keeps_original_order(self):
        fixture = self.fixture()
        fixture.order['subjectPlan'] = self.plan(fixture, 512)
        order = fixture.submit()
        retained = fixture.p.get(order['id'])['request']
        self.assertIsNone(fixture.p.claim())
        with self.assertRaisesRegex(ValueError, 'claimed attempt'):
            fixture.p.prepare_platform(order)
        self.assertEqual(fixture.p.get(order['id'])['status'], 'queued')
        # Model a claimed attempt only in this isolated offline fixture.
        with fixture.p.connect() as con:
            con.execute("UPDATE jobs SET status='running' WHERE id=?", (order['id'],))
        platform = fixture.p.prepare_platform(order)
        self.assertEqual(len(platform['scenario']['steps']), 512)
        self.assertEqual(platform['configuration'], mod.read(fixture.config))
        self.assertEqual(platform['subjectOrderSha256'], contract.identity(order))
        self.assertEqual(fixture.p.get(order['id'])['request'], retained)
        self.assertEqual(fixture.p.get(order['id'])['status'], 'running')

    def test_combined_session_still_accepts_256_and_refuses_257(self):
        for count, accepted in ((128, True), (129, False)):
            with self.subTest(total=count + 128):
                fixture = shared.SharedSessionTests()
                fixture.setUp()
                self.addCleanup(fixture.doCleanups)
                orders = []
                for i, size in enumerate((128, count)):
                    extra = copy.deepcopy(fixture.order)
                    extra.update(id=f'member-{i}', sourceChat=f'origin-{i}', sourceThreadId=f'thread-{i}')
                    extra['subjectPlan'] = self.plan(fixture, size)
                    path = fixture.root / f'member-{i}.json'
                    mod.write(path, extra)
                    fixture.p.submit(path)
                    orders.append(extra)
                evidence = fixture.root / 'owner.txt'
                evidence.write_text('Run prepared members')
                release = fixture.root / 'release.json'
                mod.write(release, {'schemaVersion': 1, 'id': 'release', 'orderIds': [o['id'] for o in orders],
                    'ownerAuthorization': {'threadId': 'owner', 'messageId': 'turn', 'quote': 'Run prepared members',
                        'verifiedBy': 'offline-test', 'path': str(evidence), 'sha256': mod.digest(evidence)}})
                fixture.p.release_batch(release)
                fixture.group(orders)
                fixture.p.claim_shared()
                if accepted:
                    plan = fixture.p.prepare_shared('session-1')
                    self.assertEqual(len(plan['scenario']['steps']), 256)
                else:
                    with self.assertRaisesRegex(ValueError, 'exceeds 256'):
                        fixture.p.prepare_shared('session-1')
                    self.assertFalse(any(fixture.p.get(o['id'])['packet'] for o in orders))


if __name__ == '__main__':
    unittest.main()

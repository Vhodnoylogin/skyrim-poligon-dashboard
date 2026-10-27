"""Explicit longer owner windows remain frozen, finite and reserve restoration."""
import subprocess
import time
import unittest
from unittest.mock import patch

import polygon as m
import qualification_companion as companion
import test_qualification as fixture
import test_qualification_companion as companion_fixture


class WindowTests(unittest.TestCase):
    def fresh(self):
        f = fixture.QualificationTests(); f.setUp(); self.addCleanup(f.doCleanups); return f

    def test_explicit_outer_boundaries_and_existing900_are_frozen(self):
        for wall in (900, 7200, 14400):
            with self.subTest(wall=wall):
                f = self.fresh(); f.request['maximumWallSeconds'] = wall; f.register()
                plan = f.p.qualification_verify(f.p.qualification_show('candidate-one'))
                self.assertEqual(plan['maximumWallSeconds'], wall)
                self.assertEqual(f.p.qualification_show('candidate-one')['status'], 'prepared')

    def test_absent_noninteger_and_out_of_range_outer_bounds_refuse(self):
        f = self.fresh()
        for wall in (899, 14401, True, 900.0, None, '900'):
            with self.subTest(wall=wall):
                f.request['maximumWallSeconds'] = wall
                with self.assertRaisesRegex(ValueError, '900..14400'): f.register()
        f.request.pop('maximumWallSeconds')
        with self.assertRaisesRegex(ValueError, '900..14400'): f.register()
        with f.p.connect() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM qualifications').fetchone()[0], 0)

    def test_dispatch_uses_frozen_wall_and_never_exceeds_owner_deadline(self):
        for wall, remaining in ((900, 20000), (7200, 20000), (7200, 1800), (14400, 20000)):
            with self.subTest(wall=wall, remaining=remaining):
                f = self.fresh(); now = time.time(); f.request.update(maximumWallSeconds=wall, deadlineUtc=now+remaining)
                f.register()
                with patch('qualification.time.time', return_value=now), \
                        patch('qualification.subprocess.run', return_value=subprocess.CompletedProcess(['fake'], 0)) as run, \
                        patch.object(f.p, 'qualification_collect', return_value={'collected': 'synthetic'}):
                    f.p.qualification_run('candidate-one')
                expected = min(wall, remaining)
                self.assertEqual(f.p.qualification_show('candidate-one')['expires'], now+expected)
                self.assertEqual(run.call_args.kwargs['timeout'], expected)
                dispatch = m.read(f.p.local/'qualifications/candidate-one/dispatch-intent.json')
                self.assertEqual(dispatch['expires'], now+expected)
                with self.assertRaisesRegex(ValueError, 'only once'): f.p.qualification_run('candidate-one')


class CompanionWindowTests(unittest.TestCase):
    def setUp(self):
        self.base = companion_fixture.RegistrationTests(); self.base.setUp(); self.addCleanup(self.base.doCleanups)
        self.f = self.base.fixture

    def configure(self, wall, maximum):
        f = self.f; f.request['maximumWallSeconds'] = wall
        f.request['companion']['maximumSeconds'] = maximum
        f.config['interactive_session']['maximumSeconds'] = maximum
        data = m.read(self.base.plan); data['bounds']['maximumSeconds'] = maximum; m.write(self.base.plan, data)
        f.request['companion']['plan']['sha256'] = m.digest(self.base.plan)

    def validate(self):
        f = self.f; return companion.validate(f.request, f.config, f.scenario, f.root)

    def test_long_manual_window_has_exact_native_plan_client_window(self):
        for wall, maximum in ((900, 600), (7200, 6900), (14400, 14100)):
            with self.subTest(wall=wall):
                self.configure(wall, maximum)
                self.assertEqual(self.validate()['maximumSeconds'], maximum)
        self.f.config['interactive_session']['maximumSeconds'] = 14099
        with self.assertRaisesRegex(ValueError, 'interactive owner'): self.validate()

    def test_companion_cannot_spend_startup_or_restoration_reserves(self):
        for wall, maximum in ((900, 601), (7200, 6901), (14400, 14101), (7200, 0), (7200, True)):
            with self.subTest(wall=wall, maximum=maximum):
                self.configure(wall, maximum)
                with self.assertRaisesRegex(ValueError, 'reserves'): self.validate()

    def test_remaining_deadline_refuses_before_running_row_or_child(self):
        f = self.f; f.request['deadlineUtc'] = time.time() + 650; f.register()
        with patch('qualification.subprocess.run') as child:
            with self.assertRaisesRegex(ValueError, 'Original owner deadline'): f.p.qualification_check('candidate-one')
            with self.assertRaisesRegex(ValueError, 'Original owner deadline'): f.p.qualification_run('candidate-one')
        child.assert_not_called()
        self.assertEqual(f.p.qualification_show('candidate-one')['status'], 'prepared')
        self.assertFalse((f.p.local / 'qualifications/candidate-one').exists())


if __name__ == '__main__': unittest.main()

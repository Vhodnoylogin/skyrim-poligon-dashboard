import tempfile
from pathlib import Path
import unittest
import polygon


class NullableExecutionReasonTests(unittest.TestCase):
    def test_success_reason_null_projects_without_mutating_raw_result(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            state = {'id': 'native', 'done': True, 'restored': True, 'reason': None}
            polygon.write(run/'state.json', state)
            before = (run/'state.json').read_bytes()
            summary = polygon.Polygon.execution_summary({'id': 'order'}, run, 'passed', None)
            self.assertEqual(summary['terminationCause'], 'unknown')
            self.assertEqual(summary['reason'], '')
            self.assertEqual((run/'state.json').read_bytes(), before)

    def test_assertion_reason_and_invalid_non_string_are_not_hidden(self):
        summary = polygon.Polygon.execution_summary({'id': 'order'}, None, 'failed', 'Assertion failed: x')
        self.assertEqual(summary['terminationCause'], 'pre_session_refusal')
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(AttributeError):
                polygon.Polygon.execution_summary({'id': 'order'}, Path(directory), 'failed', {'bad': 'reason'})

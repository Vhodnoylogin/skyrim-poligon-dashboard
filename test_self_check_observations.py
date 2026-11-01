"""Shutdown observation counts must not break retained observer collection."""
import json
import unittest

import test_polygon

mod = test_polygon.mod


class SelfCheckObservations(unittest.TestCase):
    def test_shutdown_count_keeps_list_and_direct_observer_samples(self):
        fixture = test_polygon.Tests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.automatic_submit()
        folder = fixture.p.evidence_dir('test-1')
        folder.mkdir(parents=True, exist_ok=True)
        nested = {'query': {'args': {'kind': 'world_observer'}},
                  'response': {'ok': True, 'dropped': 2}}
        direct = {'at': 3, 'query': {'args': {'kind': 'world_observer'}},
                  'response': {'ok': True}}
        events = [{'kind': 'shutdown-identity-settled', 'observations': 1},
                  {'at': 2, 'observations': [nested]}, direct]
        (folder / 'observations.jsonl').write_text(
            ''.join(json.dumps(event) + '\n' for event in events), encoding='utf-8')

        self.assertEqual(fixture.p.self_checks('test-1', None), [])
        samples = mod.read(folder / 'self-checks.json')['observerSamples']
        self.assertEqual([row['at'] for row in samples], [2, 3])
        self.assertEqual([row['response'] for row in samples],
                         [nested['response'], direct['response']])
        self.assertEqual(samples[0]['qualityFlags'], [{'field': '.dropped', 'value': 2}])
        self.assertEqual(samples[1]['qualityFlags'], [])


if __name__ == '__main__':
    unittest.main()

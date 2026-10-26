import json
import unittest
from observation_log import parse


class ObservationLogTests(unittest.TestCase):
    def parse(self,*values): return parse('\n'.join(json.dumps(v)for v in values),'retained-steps.jsonl')

    def test_actual_shutdown_counter_and_valid_observer_samples_coexist(self):
        sample={'query':{'tool':'inspect','args':{'kind':'world_observer'}},'response':{'version':'actual'},'at':2}
        rows,diagnostics=self.parse({'kind':'shutdown-identity-settled','observations':1},
                                    {'at':1,'observations':[sample]},
                                    {'tool':'inspect','args':{'kind':'world_observer'},'result':{'gap':True}})
        self.assertEqual(len(rows),2);self.assertEqual(rows[0]['response'],{'version':'actual'})
        self.assertEqual(rows[1]['response'],{'gap':True})
        self.assertEqual(diagnostics,[{'source':'retained-steps.jsonl','line':1,
            'code':'observation_count_metadata','actualType':'int','severity':'info'}])

    def test_unrecognized_observation_shapes_are_diagnosed_not_silently_accepted(self):
        for value in (None,1,True,'bad',{}):
            with self.subTest(value=value):
                rows,diagnostics=self.parse({'observations':value})
                self.assertEqual(rows,[]);self.assertEqual(diagnostics[0]['code'],'observations_not_array')
                self.assertEqual(diagnostics[0]['severity'],'error')
        for value in (-1,True,'1'):
            rows,diagnostics=self.parse({'kind':'shutdown-identity-settled','observations':value})
            self.assertEqual(diagnostics[0]['severity'],'error')

    def test_malformed_items_query_and_args_do_not_hide_following_good_sample(self):
        good={'query':{'args':{'kind':'world_observer'}},'response':{'unsupported':True}}
        rows,diagnostics=self.parse({'observations':[42,{'query':None},{'query':{'args':[]}},good]})
        self.assertEqual([x['code']for x in diagnostics],['observation_not_object','query_not_object','args_not_object'])
        self.assertEqual(rows[0]['response'],{'unsupported':True})

    def test_invalid_json_and_non_object_events_preserve_source_line_diagnostics(self):
        rows,diagnostics=parse('invalid\n42\n{}','raw.jsonl')
        self.assertEqual(rows,[]);self.assertEqual([x['line']for x in diagnostics],[1,2])
        self.assertEqual([x['code']for x in diagnostics],['invalid_json','event_not_object'])


if __name__=='__main__':unittest.main()

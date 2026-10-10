"""Completeness and failure reporting for the fixed Beta performance protocol."""
from contextlib import redirect_stdout
import io
import unittest
from unittest.mock import patch
import benchmark_label_beta_summaries as benchmark


class Protocol(unittest.TestCase):
    def test_only_the_two_legacy_probes_can_increase_query_count(self):
        zero = {'catalog': 0, 'eligibility': 0}
        probes = {'catalog': 1, 'eligibility': 1}
        benchmark.verify_query_counts('AA', [10] * 31, [10] * 31, [zero] * 31, [zero] * 31)
        benchmark.verify_query_counts('AB', [10] * 31, [12] * 31, [zero] * 31, [probes] * 31)
        for counts, measured in [([13] * 31, probes), ([11] * 31, probes),
                                 ([12] * 31, zero), ([12] * 31, {'catalog': 2, 'eligibility': 0})]:
            with self.assertRaises(AssertionError):
                benchmark.verify_query_counts('AB', [10] * 31, counts, [zero] * 31, [measured] * 31)
        with self.assertRaises(AssertionError):
            benchmark.verify_query_counts('AA', [10] * 31, [12] * 31, [zero] * 31, [probes] * 31)
        with self.assertRaises(AssertionError):
            benchmark.verify_query_counts('AB', [10] * 31, [12] * 30 + [11], [zero] * 31, [probes] * 31)

    def record(self,mode,repetition,size,shape,reports):
        reports.append(dict(mode=mode,repetition=repetition,tasks=size,shape=shape))

    def run_protocol(self,measure):
        reports=[]
        with redirect_stdout(io.StringIO()):benchmark.execute_protocol(measure,reports)
        return reports

    def test_complete_plan_has_control_and_each_required_population(self):
        reports=self.run_protocol(self.record);cases=reports[-1]['cases']
        self.assertEqual(reports[-1]['planned_cases'],16)
        self.assertEqual((cases[0]['mode'],cases[0]['repetition']),('AA',0))
        expected={(1000,'small'),(1000,'large'),(10000,'large'),(1000,'fallback'),(10000,'mixed')}
        for rep in (1,2,3):
            rows=[c for c in cases if c['repetition']==rep]
            self.assertEqual(len(rows),5);self.assertEqual({(c['tasks'],c['shape']) for c in rows},expected)
        self.assertTrue(all(c['status']=='passed' for c in cases))

    def test_every_failed_position_preserves_failure_and_unrun_tail(self):
        for position in range(16):
            reports=[];error=RuntimeError('injected');calls=[]
            def fail(*args):
                calls.append(args[:-1])
                if len(calls)-1==position:raise error
                self.record(*args)
            with redirect_stdout(io.StringIO()),self.assertRaises(RuntimeError) as seen:benchmark.execute_protocol(fail,reports)
            self.assertIs(seen.exception,error)
            states=[x['status'] for x in reports[-1]['cases']]
            self.assertEqual(states,['passed']*position+['failed']+['not_run']*(15-position))

    def test_missing_duplicate_or_mislabeled_report_fails(self):
        for change in ('missing','duplicate','shape','size'):
            reports=[]
            def mutate(*args):
                if change!='missing':self.record(*args)
                if change=='duplicate':self.record(*args)
                if change=='shape':args[-1][-1]['shape']='wrong'
                if change=='size':args[-1][-1]['tasks']=99
            with redirect_stdout(io.StringIO()),self.assertRaises(AssertionError):benchmark.execute_protocol(mutate,reports)
            self.assertEqual(reports[-1]['cases'][0]['status'],'failed')

    def test_report_output_failure_does_not_replace_measurement_failure(self):
        error=RuntimeError('measurement')
        def fail(*args):raise error
        with patch('builtins.print',side_effect=OSError('report')),self.assertRaises(RuntimeError) as seen:
            benchmark.execute_protocol(fail,[])
        self.assertIs(seen.exception,error)


if __name__=='__main__':unittest.main()

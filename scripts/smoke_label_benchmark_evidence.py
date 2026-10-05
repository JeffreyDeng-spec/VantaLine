"""Failure propagation and arm/timer safeguards for the repeated reader benchmark."""
import ast
from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from label_benchmark_evidence import execute_protocol, prepared_counters, preserve_primary


class EvidenceTests(unittest.TestCase):
    def measure(self,mode,repetition,size,ratios,reports):
        for ratio in ratios:
            reports.append(dict(mode=mode,repetition=repetition,tasks=size,synthetic_run_cache_ratio=ratio))

    def execute(self,measure,reports):
        with redirect_stdout(io.StringIO()):execute_protocol(measure,reports)

    def test_complete_exact_coverage(self):
        reports=[]
        self.execute(self.measure,reports)
        self.assertEqual(len(reports),20)
        self.assertTrue(all(row['status']=='passed' for row in reports[-1]['groups']))
        self.assertEqual([row['repetition'] for row in reports[:-1] if row['mode']=='AB'],[1]*6+[2]*6+[3]*6)

    def test_every_failure_position_keeps_original_error_and_stops(self):
        for position in range(7):
            with self.subTest(position=position):
                reports=[];calls=[];failure=AssertionError('original guard')
                def measure(*args):
                    calls.append(args[:4])
                    if len(calls)==position+1:raise failure
                    self.measure(*args)
                with self.assertRaises(AssertionError) as caught:self.execute(measure,reports)
                self.assertIs(caught.exception,failure)
                self.assertEqual([row['status'] for row in reports[-1]['groups']],
                                 ['passed']*position+['failed']+['not_run']*(6-position))

    def test_late_missing_case_or_aa_substitution_rejected(self):
        for mutation in ('missing','duplicate','aa'):
            with self.subTest(mutation=mutation):
                reports=[]
                def measure(mode,repetition,size,ratios,rows):
                    self.measure(mode,repetition,size,ratios,rows)
                    if repetition==3 and size==10000:
                        if mutation=='missing':rows.pop()
                        elif mutation=='duplicate':rows.append(rows[-1])
                        else:rows[-1]['mode']='AA'
                with self.assertRaisesRegex(AssertionError,'benchmark cases'):self.execute(measure,reports)
                self.assertEqual(reports[-1]['groups'][-1]['status'],'failed')

    def test_diagnostics_do_not_rollback_or_expose_exception_text(self):
        connection=Mock()
        connection.execute.side_effect=RuntimeError('sensitive text')
        result=prepared_counters(connection)
        self.assertEqual(result['diagnostic_error_type'],'RuntimeError')
        self.assertNotIn('sensitive',str(result))
        connection.rollback.assert_not_called()
        connection.commit.assert_not_called()
        self.assertEqual(connection.execute.call_args.kwargs,{'prepare':False})

    def test_evidence_output_failure_preserves_primary(self):
        failure=AssertionError('latency guard')
        output_failure=OSError('evidence destination failed')
        action=Mock(side_effect=output_failure)
        with self.assertRaises(AssertionError) as caught:
            try:raise failure
            finally:preserve_primary(action)
        self.assertIs(caught.exception,failure)
        with self.assertRaises(OSError) as caught:preserve_primary(action)
        self.assertIs(caught.exception,output_failure)
        reports=[]
        with patch('builtins.print',side_effect=output_failure):
            with self.assertRaises(AssertionError) as caught:
                execute_protocol(Mock(side_effect=failure),reports)
        self.assertIs(caught.exception,failure)
        reports=[]
        with patch('builtins.print',side_effect=output_failure):
            with self.assertRaises(OSError):execute_protocol(self.measure,reports)

    def test_main_report_failure_preserves_guard_but_fails_success(self):
        import benchmark_label_summary_reads as benchmark
        failure=AssertionError('latency guard')
        report_error=OSError('report unavailable')
        with patch('sys.argv',['benchmark','--report','synthetic-report.json']), \
             patch.object(benchmark.Path,'open',side_effect=report_error):
            with patch.object(benchmark,'execute_protocol',side_effect=failure):
                with self.assertRaises(AssertionError) as caught:benchmark.main()
                self.assertIs(caught.exception,failure)
            with patch.object(benchmark,'execute_protocol',return_value=None):
                with self.assertRaises(OSError) as caught:benchmark.main()
                self.assertIs(caught.exception,report_error)

    def test_wall_window_and_ab_arm(self):
        source=Path(__file__).with_name('benchmark_label_summary_reads.py').read_text()
        tree=ast.parse(source)
        run=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='run')
        first=run.body[0]
        self.assertEqual(ast.unparse(first), "variant = variant if mode == 'AB' else True")
        start=next(i for i,node in enumerate(run.body) if isinstance(node,ast.Assign) and ast.unparse(node.targets[0])=='started')
        timed='\n'.join(ast.unparse(node) for node in run.body[start:start+3])
        self.assertEqual(timed,"started = time.perf_counter()\nwith patch.object(PostgresRuntimeRepository, '_cursor', cursor):\n    page = f.page(variant)\nelapsed = time.perf_counter() - started")
        self.assertNotIn('snapshot',timed)


if __name__=='__main__':unittest.main()

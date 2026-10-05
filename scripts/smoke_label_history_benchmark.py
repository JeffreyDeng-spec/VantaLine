"""Fixed history benchmark coverage and distinct baseline/candidate arm contracts."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import benchmark_label_history_statistics as benchmark
from smoke_label_summary_reads import Fixture, baseline_method
from smoke_label_history_statistics import StatisticsFixture
from local_inspection_service.storage.label_inspection import LabelRepository


class HistoryBenchmarkTests(unittest.TestCase):
    def measure(self,mode,repetition,size,depth,ratios,reports):
        for ratio in ratios:
            reports.append(dict(mode=mode,repetition=repetition,tasks=size,
                synthetic_history_depth=depth,synthetic_run_cache_ratio=ratio,
                comparison=benchmark.COMPARISON,baseline_sha256=benchmark.BASELINE_SHA256))

    def execute(self,measure,reports):
        with redirect_stdout(io.StringIO()):benchmark.execute_history_protocol(measure,reports)

    def test_all_twenty_eight_cases_and_ten_fresh_fixture_groups(self):
        reports=[];self.execute(self.measure,reports)
        self.assertEqual(len(reports),29)
        self.assertEqual(reports[-1]['planned_ab_cases'],27)
        self.assertEqual(reports[-1]['planned_aa_cases'],1)
        self.assertEqual([r['status'] for r in reports[-1]['groups']],['passed']*10)
        self.assertEqual([(r['tasks'],r['synthetic_history_depth']) for r in reports[-1]['groups']],
                         [(1000,None)]+[(1000,None),(10000,None),(1000,20)]*3)

    def test_every_case_failure_retains_original_and_not_run(self):
        for position in range(28):
            rows=[];seen=[];failure=AssertionError('original sample guard')
            def measure(mode,repetition,size,depth,ratios,reports):
                for ratio in ratios:
                    if len(seen)==position:raise failure
                    seen.append(ratio);self.measure(mode,repetition,size,depth,(ratio,),reports)
            with self.subTest(position=position),self.assertRaises(AssertionError) as caught:
                self.execute(measure,rows)
            self.assertIs(caught.exception,failure)
            statuses=[r['status'] for r in rows[-1]['groups']]
            group=0 if position==0 else 1+(position-1)//3
            self.assertEqual(statuses,['passed']*group+['failed']+['not_run']*(9-group))
            self.assertEqual(len(seen),position)

    def test_late_mislabeled_missing_duplicate_and_reordered_cases_fail(self):
        for mutation in ('depth','baseline','comparison','aa','missing','duplicate','reorder'):
            rows=[]
            def measure(mode,repetition,size,depth,ratios,reports):
                self.measure(mode,repetition,size,depth,ratios,reports)
                if repetition==3 and depth==20:
                    if mutation=='depth':reports[-1]['synthetic_history_depth']=None
                    elif mutation=='baseline':reports[-1]['baseline_sha256']='wrong'
                    elif mutation=='comparison':reports[-1]['comparison']='wrong'
                    elif mutation=='aa':reports[-1]['mode']='AA'
                    elif mutation=='missing':reports.pop()
                    elif mutation=='duplicate':reports.append(reports[-1])
                    else:reports[-1],reports[-2]=reports[-2],reports[-1]
            with self.subTest(mutation=mutation),self.assertRaisesRegex(AssertionError,'history benchmark cases'):
                self.execute(measure,rows)
            self.assertEqual(rows[-1]['groups'][-1]['status'],'failed')

    def test_explicit_fixture_and_baseline_selection(self):
        rows=[]
        with patch.object(benchmark,'measure_fixture') as measure:
            benchmark.measure('AB',3,1000,20,(0,.5,1),rows)
        measure.assert_called_once_with('AB',3,1000,(0,.5,1),rows,fixture_type=StatisticsFixture,
            comparison=benchmark.COMPARISON,history_depth=20,baseline_sha256=benchmark.BASELINE_SHA256)

    def test_reader_old_arm_calls_frozen_reader_candidate_calls_aggregate(self):
        fixture=Fixture.__new__(Fixture);repo=object();sentinel=object()
        original=baseline_method()
        frozen=Mock(return_value=sentinel)
        with patch('smoke_label_summary_reads.baseline_method',return_value=frozen), \
             patch.object(LabelRepository,'list_run_history_for_tasks',side_effect=AssertionError('candidate aggregate')):
            with fixture.variant(True):
                self.assertIs(LabelRepository.list_run_history_for_tasks(repo,'alice',['task'],summary_task_ids=[]),sentinel)
                self.assertIs(LabelRepository.list_run_payloads_for_tasks(repo,'alice',['task']),sentinel)
            self.assertEqual(frozen.call_args_list,[((repo,'alice',['task']),),((repo,'alice',['task']),)])
            with fixture.variant(False),self.assertRaisesRegex(AssertionError,'candidate aggregate'):
                LabelRepository.list_run_history_for_tasks(repo,'alice',['task'],summary_task_ids=[])
        self.assertIs(baseline_method(),original)

    def test_history_switches_endpoints_without_reader_baseline_adapter(self):
        fixture=StatisticsFixture.__new__(StatisticsFixture)
        fixture.candidate_endpoint=Mock(return_value='aggregate')
        fixture.parent_endpoint=Mock(return_value='parent cached payload')
        fixture.endpoint=fixture.candidate_endpoint
        failure=RuntimeError('inside arm')
        with patch('smoke_label_summary_reads.baseline_method',side_effect=AssertionError('wrong baseline')):
            self.assertEqual(fixture.page(True),'parent cached payload')
            self.assertEqual(fixture.page(False),'aggregate')
            self.assertEqual(fixture.parent_endpoint.call_count,1)
            self.assertEqual(fixture.candidate_endpoint.call_count,1)
            with self.assertRaises(RuntimeError) as caught:
                with fixture.variant(True):raise failure
            self.assertIs(caught.exception,failure)
            self.assertIs(fixture.endpoint,fixture.candidate_endpoint)

    def test_output_failure_preserves_guard_and_fails_success(self):
        guard=AssertionError('original guard');output=OSError('output failure');rows=[]
        with patch('builtins.print',side_effect=output):
            with self.assertRaises(AssertionError) as caught:
                benchmark.execute_history_protocol(Mock(side_effect=guard),rows)
            self.assertIs(caught.exception,guard)
            with self.assertRaises(OSError):benchmark.execute_history_protocol(self.measure,[])
        with patch('sys.argv',['history','--report','synthetic.json']), \
             patch.object(benchmark,'parent_register'),patch.object(Path,'open',side_effect=output):
            with patch.object(benchmark,'execute_history_protocol',side_effect=guard):
                with self.assertRaises(AssertionError) as caught:benchmark.main()
                self.assertIs(caught.exception,guard)
            with patch.object(benchmark,'execute_history_protocol'):
                with self.assertRaises(OSError):benchmark.main()


if __name__=='__main__':unittest.main()

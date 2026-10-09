"""Counterexamples for fixed manual benchmark accounting, without performance work."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from contextlib import ExitStack
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import benchmark_manual_history as benchmark


def entry(mode, rep, size):
    return dict(mode=mode,repetition=rep,tasks=size,fixture='ManualFixture',
                manual_baseline_sha256=benchmark.BASELINE_SHA256,tasks_baseline_sha256=benchmark.TASKS_SHA256,
                comparison=benchmark.COMPARISON)


class FakeConnection:
    def execute(self, *args): return self
    def fetchone(self): return (1,)
    def commit(self): pass


class FakeWriter:
    connection = FakeConnection()
    def _qualified_table(self, name): return name


class FakeCursor:
    def execute(self, *args): return self


class MeasuredFixture:
    def __init__(self, queries=10): self.calls = []; self.queries = queries
    def __enter__(self): self.reader = object(); self.writer = FakeWriter(); self.table = 'synthetic'; return self
    def __exit__(self, *args): pass
    def insert(self, *args): pass
    def traverse(self, *args): return [{'id':'legacy-manual:manual_00000'}]
    def page(self, variant):
        self.calls.append(variant)
        cursor = benchmark.PostgresRuntimeRepository._cursor(self.reader)
        for _ in range(self.queries if variant else (7 if benchmark.PUBLISH_DERIVED else 12)): cursor.execute('SELECT synthetic')
        return {'items':self.traverse()}


def measured_fixture(stack, fixture, p95s=(1.,1.), peaks=None):
    stack.enter_context(patch.object(benchmark, 'ManualFixture', return_value=fixture))
    stack.enter_context(patch.object(benchmark.PostgresRuntimeRepository, '_cursor', return_value=FakeCursor()))
    stack.enter_context(patch.object(benchmark, 'p95', side_effect=p95s))
    stack.enter_context(patch.object(benchmark.gc, 'collect'))
    stack.enter_context(patch.object(benchmark, 'snapshot', return_value={}))
    stack.enter_context(patch.object(benchmark, 'difference', return_value={}))
    start = stack.enter_context(patch.object(benchmark.tracemalloc, 'start'))
    stop = stack.enter_context(patch.object(benchmark.tracemalloc, 'stop'))
    stack.enter_context(patch.object(benchmark.tracemalloc, 'get_traced_memory',
                                    **({'side_effect':peaks} if peaks else {'return_value':(1,1)})))
    return start, stop


class Protocol(unittest.TestCase):
    def test_fixed_plan_and_both_arm_selection(self):
        calls=[];reports=[]
        def measure(mode,rep,size,reports): calls.append((mode,rep,size));reports.append(entry(mode,rep,size))
        with patch('builtins.print'): benchmark.execute_manual_protocol(measure,reports)
        self.assertEqual(calls,[('AA',0,1000)]+[('AB',r,s) for r in (1,2,3) for s in (1000,10000)])
        self.assertEqual([g['status'] for g in reports[-1]['groups']],['passed']*7)
        self.assertEqual([benchmark.arm('AA',v) for v in (True,False)],[True,True])
        self.assertEqual([benchmark.arm('AB',v) for v in (True,False)],[True,False])

    def test_missing_duplicate_wrong_order_fixture_and_baseline_fail_closed(self):
        for mutation in ('missing','duplicate','order','fixture','manual','tasks','comparison'):
            with self.subTest(mutation=mutation):
                calls=[];reports=[]
                def measure(mode,rep,size,reports):
                    calls.append(1);record=entry(mode,rep,size)
                    if mutation=='missing':return
                    if mutation=='order':record['repetition']=99
                    if mutation=='fixture':record['fixture']='StatisticsFixture'
                    if mutation=='manual':record['manual_baseline_sha256']='wrong'
                    if mutation=='tasks':record['tasks_baseline_sha256']='wrong'
                    if mutation=='comparison':record['comparison']='wrong'
                    reports.append(record)
                    if mutation=='duplicate':reports.append(record.copy())
                with patch('builtins.print'), self.assertRaises(AssertionError): benchmark.execute_manual_protocol(measure,reports)
                self.assertEqual(calls,[1]);self.assertEqual([g['status'] for g in reports[-1]['groups']],['failed']+['not_run']*6)

    def test_primary_failure_survives_output_failure_and_accounting_is_preserved(self):
        reports=[];primary=RuntimeError('measurement failed')
        def fail(*args):raise primary
        with patch('builtins.print',side_effect=OSError('output')),self.assertRaises(RuntimeError) as caught:
            benchmark.execute_manual_protocol(fail,reports)
        self.assertIs(caught.exception,primary)
        self.assertEqual([g['status'] for g in reports[-1]['groups']],['failed']+['not_run']*6)

    def test_output_failure_does_not_turn_success_into_pass(self):
        reports=[]
        def measure(mode,rep,size,reports):reports.append(entry(mode,rep,size))
        with patch('builtins.print',side_effect=OSError('output')),self.assertRaises(OSError):
            benchmark.execute_manual_protocol(measure,reports)
        self.assertEqual([g['status'] for g in reports[-1]['groups']],['passed']*7)


    def test_real_measure_routes_every_warmup_latency_and_memory_arm(self):
        expected = [True,False]*4 + [v for i in range(31) for v in ((True,False) if i%2==0 else (False,True))] + [True,False,False,True,True,False]
        for mode in ('AA','AB'):
            with self.subTest(mode=mode), ExitStack() as stack:
                fixture = MeasuredFixture(); reports = []
                start, stop = measured_fixture(stack, fixture)
                stack.enter_context(patch('builtins.print'))
                benchmark.measure(mode, 0 if mode=='AA' else 1, 1, reports)
                self.assertEqual(fixture.calls, [True]*76 if mode=='AA' else expected)
                self.assertEqual((start.call_count,stop.call_count),(6,6))
                self.assertEqual(len(reports[0]['old_seconds']),31); self.assertEqual(len(reports[0]['new_seconds']),31)
                self.assertEqual(len(reports[0]['old_peak_samples']),3); self.assertEqual(len(reports[0]['new_peak_samples']),3)

    def test_real_measure_latency_and_memory_failure_survive_output_failure(self):
        for kind in ('latency','memory'):
            with self.subTest(kind=kind), ExitStack() as stack:
                fixture = MeasuredFixture(); reports = []
                measured_fixture(stack,fixture,p95s=(1.,3.) if kind=='latency' else (1.,1.),
                    peaks=[(1,1),(1,3000000),(1,3000000),(1,1),(1,1),(1,3000000)] if kind=='memory' else None)
                stack.enter_context(patch('builtins.print',side_effect=OSError('output')))
                with self.assertRaisesRegex(AssertionError,'manual first-page '+('P95' if kind=='latency' else 'peak-memory')+' regression'):
                    benchmark.measure('AB',1,1,reports)
                self.assertEqual(len(reports),1)

    def test_real_measure_success_still_fails_if_output_fails(self):
        with ExitStack() as stack:
            fixture = MeasuredFixture();reports=[];measured_fixture(stack,fixture)
            stack.enter_context(patch('builtins.print',side_effect=OSError('output')))
            with self.assertRaises(OSError):benchmark.measure('AB',1,1,reports)
            self.assertEqual(len(reports),1)

    def test_real_measure_rejects_query_count_before_accepting_sample(self):
        with ExitStack() as stack:
            fixture = MeasuredFixture(queries=9);reports=[];measured_fixture(stack,fixture)
            stack.enter_context(patch('builtins.print'))
            with self.assertRaises(AssertionError):benchmark.measure('AB',1,1,reports)
            self.assertEqual(fixture.calls,[True]);self.assertEqual(reports,[])


if __name__=='__main__':unittest.main()

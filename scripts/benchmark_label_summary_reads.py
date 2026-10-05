"""Same-environment full list endpoint/cache-read benchmark on isolated PostgreSQL.

31 alternating samples after four warmups; first-page work includes real SQL,
legacy/manual/Beta projection and the persisted 15-minute snapshot. No HTTP
transport/serialization or production-workload claim. Memory is measured in a
separate balanced pass to avoid tracing distorting latency samples.
"""
import argparse
import gc
import json
import math
from pathlib import Path
import sys
import time
import tracemalloc
from unittest.mock import patch
from smoke_label_summary_reads import Fixture, baseline_method
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.label_inspection import LabelRepository
from label_benchmark_evidence import snapshot, difference, prepared_counters, execute_protocol, preserve_primary


def p95(values):return sorted(values)[math.ceil(.95*len(values))-1]


class CountingCursor:
    def __init__(self,cursor,calls):self.cursor=cursor;self.calls=calls
    def execute(self,sql,params=None):
        self.calls.append(str(sql));return self.cursor.execute(sql,params)
    def __getattr__(self,key):return getattr(self.cursor,key)


def measure_fixture(mode,repetition,size,ratios,reports):
    with Fixture() as f:
        def native_rows():
            for i in range(size):
                tid=f'task_{i:05}'
                yield {**f.task(tid),'created_at':i,'updated_at':i,
                       **({'legacy_id':f'legacy_{i}'} if i%500==0 else {})}
                count=30 if i%200==0 else (0 if i%7==0 else 1)
                for j in range(count):yield f.run(f'run_{i:05}_{j:02}',tid,created_at=i+j/10,
                    profile_snapshot={'synthetic':'x'*2048})
        f.insert('label_inspection_objects',native_rows())
        f.insert('text_inspection_standards',[
            dict(id=f'legacy_{i}',owner_user_id='alice',name=f'Legacy {i}',standard_type='label',created_at=i,updated_at=i)
            for i in range(0,size,500)]+[dict(id='manual',owner_user_id='alice',name='Manual',standard_type='manual',created_at=0,updated_at=0)])
        f.insert('text_inspection_records',[
            dict(id=f'history_{i}_{j}',owner_user_id='alice',standard_id=f'legacy_{i}',created_at=i+j/7,status='completed',decision='DIFFERENCES')
            for i in range(0,size,500) for j in range(3)]+[dict(id='manual-page',owner_user_id='alice',standard_id='manual',standard_type='manual',created_at=1)])
        f.insert('codex_comparison_tasks',[dict(id='beta',owner_user_id='alice',created_at=1,updated_at=1,status='succeeded',
            inputs={'standard_name':'Beta'},summary={'decision':'MATCH'})])
        baseline_method()  # compilation never enters timed baseline arm
        def cleanup_pages():
            f.writer.connection.execute(f"DELETE FROM {f.table} WHERE kind='page'");f.writer.connection.commit()
        original=PostgresRuntimeRepository._cursor
        for ratio in ratios:
            ids=[r[0] for r in f.writer.connection.execute(f"SELECT id FROM {f.table} WHERE kind='run' ORDER BY id")]
            f.writer.connection.commit()
            for identity in ids[:int(len(ids)*ratio)]:assert f.store.publish('alice',identity)
            f.writer.connection.execute(f'ANALYZE {f.table}');f.writer.connection.execute(f'ANALYZE {f.cache}');f.writer.connection.commit()
            expected=f.traverse(True)
            assert f.traverse()==expected
            cleanup_pages()
            observations={True:[],False:[]}
            def run(variant,trace=False):
                variant=variant if mode=="AB" else True
                calls=[]
                def cursor(raw):
                    result=original(raw)
                    return CountingCursor(result,calls) if raw is f.reader else result
                gc.collect()
                before=snapshot()
                if trace:tracemalloc.start()
                started=time.perf_counter()
                with patch.object(PostgresRuntimeRepository,'_cursor',cursor):page=f.page(variant)
                elapsed=time.perf_counter()-started
                peak=tracemalloc.get_traced_memory()[1] if trace else None
                if trace:tracemalloc.stop()
                observed=difference(before,snapshot())
                assert page['items']==expected[:100]
                native_queries=[sql for sql in calls if 'task_id=ANY' in sql]
                assert len(native_queries)==math.ceil(size/64)
                # At most task + six legacy sources + bounded native batches + snapshot statements.
                assert len(calls)<=math.ceil(size/64)+12,(len(calls),size)
                cleanup_pages()
                return elapsed,peak,len(calls),len(native_queries),observed
            for _ in range(4):run(True);run(False)
            times={True:[],False:[]};counts={}
            for iteration in range(31):
                for variant in ((True,False) if iteration%2==0 else (False,True)):
                    elapsed,_,queries,batches,observed=run(variant);times[variant].append(elapsed);counts[variant]=(queries,batches);observations[variant].append(observed)
            peaks={True:[],False:[]}
            for iteration in range(3):
                for variant in ((True,False) if iteration%2==0 else (False,True)):
                    _,peak,_,_,_=run(variant,True);peaks[variant].append(peak)
            old=p95(times[True]);new=p95(times[False]);old_peak=max(peaks[True]);new_peak=max(peaks[False])
            report=dict(tasks=size,synthetic_run_cache_ratio=ratio,synthetic_quality_bytes=8192,
                samples=31,old_seconds=times[True],new_seconds=times[False],old_p95_seconds=old,new_p95_seconds=new,
                old_peak_bytes=old_peak,new_peak_bytes=new_peak,old_queries=counts[True],new_queries=counts[False],
                latency_limit=max(old*1.25,old+.01),memory_limit=max(old_peak*1.25,old_peak+1024*1024))
            report.update(mode=mode,repetition=repetition,cpu_gc_envelope='outside wall timer; includes timer/tracemalloc bookkeeping',
                          old_observations=observations[True],new_observations=observations[False])
            print(json.dumps(report),flush=True);reports.append(report)
            try:
                assert new<=report['latency_limit'],'first-page P95 regression'
                assert new_peak<=report['memory_limit'],'first-page peak-memory regression'
            except BaseException:
                # Read counters before any diagnostic rollback or fixture cleanup.
                def diagnostics():
                    report['failure_prepared_counters']=prepared_counters(f.reader.connection)
                    print(json.dumps({'failure_diagnostics':report['failure_prepared_counters']}),flush=True)
                preserve_primary(diagnostics)
                raise

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report');args=parser.parse_args()
    reports=[]
    try:
        execute_protocol(measure_fixture,reports)
    finally:
        if args.report:
            def save_report():
                with Path(args.report).open('x',encoding='utf8') as output:json.dump(reports,output,indent=2)
            preserve_primary(save_report)
    print('PASS three complete A/B repetitions and separate A/A control; unchanged query/memory/latency guards')


if __name__=='__main__':main()

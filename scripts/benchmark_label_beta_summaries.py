"""Full Beta first-page evidence compaction benchmark with a fixed 16-case protocol.

Synthetic PostgreSQL only; timed work includes the account-bound 15-minute page
snapshot, excludes HTTP transport and separately measures peak Python memory.
"""
import argparse
import gc
import json
from pathlib import Path
import time
import tracemalloc
from unittest.mock import patch
from benchmark_label_summary_reads import CountingCursor,p95
from label_benchmark_evidence import snapshot,difference,preserve_primary
from smoke_label_beta_summaries import beta
from smoke_label_history_statistics import StatisticsFixture,parent_register
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository

PLAN=[('AA',0,1000,'large')]+[
    ('AB',rep,size,shape) for rep in (1,2,3)
    for size,shape in ((1000,'small'),(1000,'large'),(10000,'large'),(1000,'fallback'),(10000,'mixed'))]
BASELINE='ce5b2beaacf9b6d16957ed22470b2cec36da30596ad1fccab6f60cd4bf2bb086'


def measure(mode,repetition,size,shape,reports):
    with StatisticsFixture() as f:
        def rows():
            for i in range(size):
                row=beta(f'beta-{i:05}',updated_at=i)
                if shape=='small':row['labels']={}
                if shape=='fallback' or (shape=='mixed' and i%2):
                    nested='unprojected'
                    for _ in range(40):nested={'level':nested}
                    row['unused']=nested
                yield row
        f.insert('codex_comparison_tasks',rows())
        table=f.writer._qualified_table('codex_comparison_tasks')
        assert f.writer.connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==size
        f.writer.connection.execute(f'ANALYZE {table}');f.writer.connection.commit()
        compacted=sum(r.payload.get('labels')=={'one':{}} for r in f.repo.list_beta_history('alice'))
        assert compacted==(0 if shape=='small' else size)
        expected=f.traverse(True);assert f.traverse()==expected and len(expected)==size
        def cleanup():
            f.writer.connection.execute(f"DELETE FROM {f.table} WHERE kind='page'");f.writer.connection.commit()
        cleanup();original=PostgresRuntimeRepository._cursor
        def run(baseline,trace=False):
            baseline=baseline if mode=='AB' else True
            calls=[]
            def cursor(raw):
                result=original(raw)
                return CountingCursor(result,calls) if raw is f.reader else result
            gc.collect();before=snapshot()
            if trace:tracemalloc.start()
            try:
                started=time.perf_counter()
                with patch.object(PostgresRuntimeRepository,'_cursor',cursor):page=f.page(baseline)
                elapsed=time.perf_counter()-started
                peak=tracemalloc.get_traced_memory()[1] if trace else None
            finally:
                if trace:tracemalloc.stop()
            observation=difference(before,snapshot())
            assert page['items']==expected[:100]
            assert len(calls)<=12,(len(calls),size)
            assert len([q for q in calls if 'codex_comparison_tasks' in q])==1
            cleanup()
            return elapsed,peak,len(calls),observation
        for _ in range(4):run(True);run(False)
        samples={True:[],False:[]};queries={True:[],False:[]};observations={True:[],False:[]};peaks={True:[],False:[]}
        for iteration in range(31):
            for baseline in ((True,False) if iteration%2==0 else (False,True)):
                elapsed,_,count,obs=run(baseline);samples[baseline].append(elapsed);queries[baseline].append(count);observations[baseline].append(obs)
        for iteration in range(3):
            for baseline in ((True,False) if iteration%2==0 else (False,True)):
                _,peak,_,_=run(baseline,True);peaks[baseline].append(peak)
        old,new=p95(samples[True]),p95(samples[False]);old_peak,new_peak=max(peaks[True]),max(peaks[False])
        record=dict(mode=mode,repetition=repetition,tasks=size,shape=shape,compacted_rows=compacted,projection_contract=3,baseline_sha256=BASELINE,
            samples=31,old_seconds=samples[True],new_seconds=samples[False],old_p95_seconds=old,new_p95_seconds=new,
            old_peak_samples=peaks[True],new_peak_samples=peaks[False],old_peak_bytes=old_peak,new_peak_bytes=new_peak,
            old_queries=queries[True],new_queries=queries[False],old_observations=observations[True],new_observations=observations[False],
            latency_limit=max(old*1.25,old+.01),memory_limit=max(old_peak*1.25,old_peak+1024*1024))
        reports.append(record);print(json.dumps(record),flush=True)
        assert new<=record['latency_limit'],'Beta first-page P95 regression'
        assert new_peak<=record['memory_limit'],'Beta first-page peak-memory regression'
        assert set(queries[True])==set(queries[False]),'Beta query count increased'


def execute_protocol(measure,reports):
    accounting=[dict(mode=m,repetition=r,tasks=n,shape=s,status='not_run') for m,r,n,s in PLAN]
    try:
        for entry in accounting:
            entry['status']='running';offset=len(reports)
            try:
                measure(entry['mode'],entry['repetition'],entry['tasks'],entry['shape'],reports)
                assert len(reports)==offset+1
                assert all(reports[-1][key]==entry[key] for key in ('mode','repetition','tasks','shape'))
            except BaseException:entry['status']='failed';raise
            entry['status']='passed'
    finally:
        report=dict(protocol='beta-list-summaries-v1',planned_cases=16,cases=accounting)
        reports.append(report);preserve_primary(lambda:print(json.dumps(report),flush=True))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report');args=parser.parse_args();reports=[]
    try:
        parent_register()
        execute_protocol(measure,reports)
    finally:
        if args.report:
            def save():
                with Path(args.report).open('x',encoding='utf-8') as output:json.dump(reports,output,indent=2)
            preserve_primary(save)
    print('PASS Beta A/A + three complete five-case repetitions with original latency/memory guards')


if __name__=='__main__':main()

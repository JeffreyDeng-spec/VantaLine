"""Private bounded attribution experiment; never an acceptance replacement."""
import ast, hashlib, json, sys, time, argparse, os, subprocess, threading, platform
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
parser=argparse.ArgumentParser()
parser.add_argument('--root',required=True)
parser.add_argument('--expected-sha',required=True)
parser.add_argument('--output',required=True)
parser.add_argument('--label',required=True)
args=parser.parse_args()
ROOT=Path(args.root).resolve()
OUTPUT=Path(args.output).resolve()
assert not OUTPUT.exists()
actual_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
assert actual_sha==args.expected_sha
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,text=True)
observed_opens={}
audit_enabled=True
def source_audit(event,values):
    if not audit_enabled or event!='open' or not values or not isinstance(values[0],(str,bytes)):return
    try:
        path=Path(os.fsdecode(values[0])).absolute()
        relative=str(path.relative_to(ROOT)).replace('\\','/')
    except (ValueError,OSError):return
    row=observed_opens.setdefault(relative,dict(count=0,modes=[]))
    row['count']+=1
    mode=str(values[1]) if len(values)>1 else ''
    if mode not in row['modes']:row['modes'].append(mode)
sys.addaudithook(source_audit)
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import benchmark_label_summary_reads as bench
import smoke_label_history_statistics as history
from benchmark_label_history_statistics import BASELINE_SHA256
import local_inspection_service.storage.postgres_runtime_repository as runtime

active=None
samples=[]
cleanups=[]
page_counts={}
cleanup_counts={}
def timed(kind,fn,*args,**kwargs):
    started_ns=time.monotonic_ns()
    sql_index=len(active['sql'])-1 if active is not None else None
    start=time.perf_counter();cpu=time.process_time()
    try:return fn(*args,**kwargs)
    finally:
        if active is not None:
            elapsed=time.perf_counter()-start;used=time.process_time()-cpu
            if kind in ('generic_field_decode','row_mapping'):
                d=active.setdefault(kind,dict(count=0,elapsed=0.0,cpu=0.0,max_elapsed=0.0))
                d.update(count=d['count']+1,elapsed=d['elapsed']+elapsed,cpu=d['cpu']+used,max_elapsed=max(d['max_elapsed'],elapsed))
            else:
                owner=getattr(fn,'__self__',None);connection=getattr(owner,'connection',owner)
                info=getattr(connection,'info',None)
                active['phases'].append(dict(kind=kind,elapsed=elapsed,cpu=used,started_ns=started_ns,ended_ns=time.monotonic_ns(),sql_index=sql_index,backend_pid=getattr(info,'backend_pid',None)))

class Cursor:
    def __init__(self,cursor):self.raw=cursor
    def execute(self,sql,params=None,**kwargs):
        if active is not None:
            active['sql'].append(dict(sql=str(sql),parameter_types=[type(p).__name__ for p in params] if params else [],parameter_sizes=[len(p) if isinstance(p,(str,list,tuple,dict)) else None for p in params] if params else []))
        timed('execute',self.raw.execute,sql,params,**kwargs)
        return self
    def __enter__(self):
        self.raw.__enter__();return self
    def __exit__(self,*args):return self.raw.__exit__(*args)
    def __iter__(self):return self
    def __next__(self):return timed('iterate',self.raw.__next__)
    def fetchall(self):return timed('fetchall',self.raw.fetchall)
    def fetchone(self):return timed('fetchone',self.raw.fetchone)
    def __getattr__(self,key):return getattr(self.raw,key)

class Connection:
    def __init__(self,raw):self.raw=raw
    def cursor(self,*args,**kwargs):return Cursor(self.raw.cursor(*args,**kwargs))
    def execute(self,sql,params=None,**kwargs):
        if active is not None:
            active['sql'].append(dict(sql=str(sql),parameter_types=[type(p).__name__ for p in params] if params else [],parameter_sizes=[len(p) if isinstance(p,(str,list,tuple,dict)) else None for p in params] if params else []))
        return Cursor(timed('execute',self.raw.execute,sql,params,**kwargs))
    def commit(self):return timed('commit',self.raw.commit)
    def rollback(self):return timed('rollback',self.raw.rollback)
    def __getattr__(self,key):return getattr(self.raw,key)


observer_events=[]
observer_errors=[]
class Observer:
    """Read-only sampled evidence; overhead is explicit and not acceptance."""
    def __init__(self,reader,writer):
        self.connection=None
        self.thread=None
        self.pids=[reader,writer]
        self.stop_event=threading.Event()
    def start(self):
        import psycopg
        self.connection=psycopg.connect(os.environ['VANTALINE_POSTGRES_DSN'],autocommit=True)
        self.connection.execute("SET statement_timeout='2000ms'",prepare=False)
        self.thread=threading.Thread(target=self.run,name='diagnostic-observer',daemon=True)
        self.thread.start()
    def run(self):
        while not self.stop_event.is_set():
            sample=active
            if sample is not None:
                started=time.monotonic_ns();cpu=time.thread_time()
                tag={k:sample.get(k) for k in ['mode','sequence','phase','index','logical_arm','page_sequence']}
                try:
                    rows=self.connection.execute("SELECT clock_timestamp(),pid,state,wait_event_type,wait_event,query_start,xact_start,backend_xid,backend_xmin FROM pg_stat_activity WHERE pid=ANY(%s)",(self.pids,),prepare=False).fetchall()
                    ended=time.monotonic_ns()
                    observer_events.append(dict(tag=tag,client_started_ns=started,client_ended_ns=ended,observer_cpu=time.thread_time()-cpu,rows=[[v.isoformat() if isinstance(v,datetime) else v for v in row] for row in rows]))
                except BaseException as error:
                    observer_errors.append(dict(type=type(error).__name__,sqlstate=getattr(error,'sqlstate',None)))
                    self.stop_event.set()
            self.stop_event.wait(.005)
    def close(self):
        self.stop_event.set()
        try:
            if self.thread is not None:
                self.thread.join(2)
                if self.thread.is_alive() and self.connection is not None:
                    self.connection.cancel();self.thread.join(2)
                if self.thread.is_alive():raise RuntimeError('observer did not stop')
        except BaseException as error:
            observer_errors.append(dict(stage='join_or_cancel_incomplete',type=type(error).__name__,joined=False))
        finally:
            try:
                if self.connection is not None:self.connection.close()
            except BaseException as error:
                observer_errors.append(dict(stage='close',type=type(error).__name__))
        if observer_errors:raise RuntimeError('observer evidence incomplete')

class Fixture(history.StatisticsFixture):
    def __enter__(self):
        super().__enter__()
        self.observer=None
        try:
            reader=Connection(self.reader.connection);writer=Connection(self.writer.connection)
            object.__setattr__(self.reader,'connection',reader)
            object.__setattr__(self.writer,'connection',writer)
            self.observer=Observer(reader.info.backend_pid,writer.info.backend_pid)
            self.observer.start()
            return self
        except BaseException:
            if self.observer is not None:
                bench.preserve_primary(self.observer.close)
            super().__exit__(*sys.exc_info());raise
    def __exit__(self,kind,*rest):
        error=None
        try:
            if self.observer is not None:self.observer.close()
        except BaseException as failure:error=failure
        super().__exit__(kind,*rest)
        if error is not None and kind is None:raise error

def diagnostic_page(f,variant,trace):
    global active
    seq=page_counts.get(current_mode,0);page_counts[current_mode]=seq+1
    if seq<8:phase='warmup';index=seq//2;logical_old=seq%2==0
    elif seq<70:
        phase='latency';index=(seq-8)//2;logical_old=(seq-8)%2==(index%2)
    else:
        phase='memory';index=(seq-70)//2;logical_old=(seq-70)%2==(index%2)
    assert trace==(phase=='memory') and seq<76
    assert variant==(logical_old if current_mode=='AB' else True)
    active=dict(mode=current_mode,sequence=seq,phase=phase,index=index,logical_arm='old' if logical_old else 'new',effective_baseline=variant,memory_pass=trace,phases=[],sql=[],backend_pid=f.reader.connection.info.backend_pid)
    start=time.perf_counter();cpu=time.process_time()
    try:return f.page(variant)
    finally:
        active.update(elapsed=time.perf_counter()-start,cpu=time.process_time()-cpu)
        samples.append(active);active=None

def diagnostic_cleanup(fn,f):
    global active
    seq=cleanup_counts.get(current_mode,0);cleanup_counts[current_mode]=seq+1
    active=dict(mode=current_mode,page_sequence=seq-1 if seq else None,phase='cleanup' if seq else 'preflight_cleanup',writer_pid=f.writer.connection.info.backend_pid,phases=[],sql=[])
    start=time.perf_counter();cpu=time.process_time()
    try:return fn()
    finally:
        active.update(elapsed=time.perf_counter()-start,cpu=time.process_time()-cpu)
        cleanups.append(active);active=None

source=(ROOT/'scripts/benchmark_label_summary_reads.py').read_text()
tree=ast.parse(source)
function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='measure_fixture')
class Instrument(ast.NodeTransformer):
    def visit_Call(self,node):
        self.generic_visit(node)
        if isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='f' and node.func.attr=='page':
            return ast.copy_location(ast.Call(ast.Name('diagnostic_page',ast.Load()),[ast.Name('f',ast.Load()),*node.args,ast.Name('trace',ast.Load())],[]),node)
        if isinstance(node.func,ast.Name) and node.func.id=='cleanup_pages':
            return ast.copy_location(ast.Call(ast.Name('diagnostic_cleanup',ast.Load()),[ast.Name('cleanup_pages',ast.Load()),ast.Name('f',ast.Load())],[]),node)
        return node
    def visit_Assert(self,node):
        # Only diagnostic latency/memory guard disposition changes. Every oracle,
        # population and query assertion remains. Original reports retain guards.
        if isinstance(node.msg,ast.Constant) and node.msg.value in ('first-page P95 regression','first-page peak-memory regression'):
            return ast.copy_location(ast.Pass(),node)
        return node
function=Instrument().visit(function)
module=ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[]))
namespace=dict(bench.__dict__,diagnostic_page=diagnostic_page,diagnostic_cleanup=diagnostic_cleanup)
exec(compile(module,'<private-phase-instrumentation>','exec'),namespace)
original_decode=runtime._decode_value
def decode(*args,**kwargs):return timed('generic_field_decode',original_decode,*args,**kwargs)
original_mapping=runtime.PostgresRuntimeRepository._row_to_dict
original_rows=bench.LabelRepository.rows
def mapping(*args,**kwargs):return timed('row_mapping',original_mapping,*args,**kwargs)
def rows(*args,**kwargs):return timed('native_rows_fetch_map_decode',original_rows,*args,**kwargs)
reports=[]
history.parent_register()
try:
    with patch.object(runtime,'_decode_value',decode), patch.object(runtime.PostgresRuntimeRepository,'_row_to_dict',mapping), patch.object(bench.LabelRepository,'rows',rows):
        for current_mode,repetition in [('AA',0),('AB',1)]:
            namespace['measure_fixture'](current_mode,repetition,1000,(0,),reports,fixture_type=Fixture,comparison='PRIVATE instrumented history diagnostic',history_depth=None,baseline_sha256=BASELINE_SHA256)
        assert page_counts=={'AA':76,'AB':76} and cleanup_counts=={'AA':77,'AB':77}
finally:
    for report in reports:
        for sample in samples:
            if sample['mode']==report['mode'] and sample['phase']=='latency':
                sample['original_run_elapsed']=report[sample['logical_arm']+'_seconds'][sample['index']]
                sample['uncovered_probe_envelope']=sample['original_run_elapsed']-sample['elapsed']
    result=dict(scope='diagnostic only; not acceptance; original CI NoGos retained',source_sha256=hashlib.sha256(source.encode()).hexdigest(),head=actual_sha,plan='one AA and one AB at 1000/cache0; 4 warmups, 31 alternating pairs, 3 memory pairs; no repeats',limitations=['Instrumented overhead changes measured path','No historical CI wait telemetry available','Sampled observer includes backend waits, not PostgreSQL CPU; SQL execute still includes network/scheduling','Generic field decode and row mapping aggregated per page; native_rows_fetch_map_decode includes fetch/map/JSON; in-driver adaptation and other projection logic unobserved; nested phases not additive','Inner page and original run timers have different boundaries; difference is only uncovered probe envelope','Cleanup separately traced outside the original wall timer'],reports=reports,samples=samples,cleanups=cleanups)
    audit_enabled=False
    metadata_errors=[]
    result.update(label=args.label,actual_checkout_sha=actual_sha,observer_events=list(observer_events),observer_errors=list(observer_errors),observer_interval_seconds=.005)
    try:
        from importlib import metadata
        blob_rows=subprocess.check_output(['git','ls-tree','-r','-z','HEAD'],cwd=ROOT).split(b'\0')
        git_blobs={}
        for entry in blob_rows:
            if entry:
                meta,name=entry.split(b'\t',1);git_blobs[name.decode()]=meta.split()[2].decode()
        def identity(path,relative):
            data=path.read_bytes() if path.is_file() else None
            blob=git_blobs.get(relative)
            actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest() if data is not None else None
            if blob is not None and actual!=blob:metadata_errors.append(dict(stage='git_blob_mismatch',path=relative))
            return dict(sha256=hashlib.sha256(data).hexdigest() if data is not None else None,git_blob=blob,actual_blob=actual)
        project_modules=[]
        external_modules=[]
        for name,module in list(sys.modules.items()):
            file=getattr(module,'__file__',None)
            if not file:continue
            path=Path(file).resolve()
            try:relative=str(path.relative_to(ROOT))
            except ValueError:
                external_modules.append(dict(name=name,path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None))
            else:
                relative=relative.replace('\\','/')
                project_modules.append(dict(name=name,path=relative,**identity(path,relative)))
        reads=[]
        for relative,value in list(observed_opens.items()):
            path=ROOT/relative
            reads.append(dict(path=relative,**value,**identity(path,relative)))
        result.update(checkout_tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=ROOT,text=True).strip(),tracked_status=subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,text=True),full_status=subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=ROOT,text=True),label=args.label,actual_checkout_sha=actual_sha,expected_checkout_sha=args.expected_sha,diagnostic_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),observer_events=observer_events,observer_errors=observer_errors,observer_interval_seconds=.005,observed_project_modules=project_modules,external_module_files=external_modules,observed_project_file_opens=reads,installed_distributions=sorted([(str(d.metadata.get('Name') or '<unnamed>'),d.version) for d in metadata.distributions()]),python=sys.version,platform=platform.uname()._asdict(),observed_input_limits=['Observed loaded modules and audited project opens only, not all possible paths','File hashes bind final source to corresponding Git blobs when tracked; generated cache/ignored reads have no blob; host/code-cache history not universal execution proof','External module hashes cover loaded files only; distribution versions are not every installed package file hash','No historical CI telemetry recovered','5ms observer misses shorter waits and perturbs shared database/client scheduling','Observer tag describes sample-start page only; cross-query/page association requires monotonic interval overlap and can remain uncertain','ABBA balances this study order only; it cannot restore historical PostgreSQL cache or host state','process_time includes observer thread CPU; observer_cpu covers query segment only and is not subtractable; tracemalloc includes observer allocations','Repository default app and preceding smoke commands run in separate processes; prelude recorded separately'])
    except BaseException as error:
        metadata_errors.append(dict(stage='metadata_collection',type=type(error).__name__))
    result['metadata_errors']=metadata_errors
    def save_report():
        with OUTPUT.open('x') as output:json.dump(result,output,indent=2)
    bench.preserve_primary(save_report)
print('Completed private phase diagnostic; no acceptance verdict')

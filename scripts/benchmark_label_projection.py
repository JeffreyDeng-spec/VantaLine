"""Synthetic settlement/claim latency; never production workload inference."""
import argparse,concurrent.futures,json,math,os,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.storage.label_inspection import LabelRepository
from local_inspection_service.storage.label_run_projection import LabelRunProjection
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.runtime_selector import default_postgres_connector
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--report',type=Path)
args=parser.parse_args()
schema='summary_cost_'+uuid.uuid4().hex[:12]
conns=[];report=[]
def execute(conn,sql,params=()):
 with conn.cursor() as c:c.execute(sql,params)
def p95(values):return sorted(values)[math.ceil(.95*len(values))-1]
try:
 for _ in range(3):conns.append(default_postgres_connector(os.environ['VANTALINE_POSTGRES_DSN']))
 writer,publisher,contender=conns
 execute(writer,postgres_ddl(schema));writer.commit()
 raws=[PostgresRuntimeRepository(c,'<synthetic>',schema_name=schema) for c in conns]
 repo=LabelRepository(raws[0]);summary=LabelRunProjection(raws[1]);other=LabelRepository(raws[2])
 for size in (256,8192,200*1024):
  samples={k:{'settlement':[],'publication':[],'worker_total':[],'competing_claim':[]} for k in ('before','after')}
  task=repo.new('alice','task','task','task',id='task',name='synthetic',assets=[])
  run=repo.new('alice','task','run','run',id='run',status='running',deadline=time.time()+420,quality={'synthetic':'x'*size})
  queued=repo.new('alice','task','run','queued',id='queued',status='queued',deadline=time.time()+420)
  for iteration in range(35):
   for enabled in ((False,True) if iteration%2==0 else (True,False)):
    # Reset source fixtures outside the measured transaction; never invoke a model.
    with repo.tx() as c:
     repo.put(c,task);repo.put(c,{**run,'status':'running'});repo.put(c,{**queued,'status':'queued'})
    started=time.perf_counter()
    repo.update_run('alice','run',status='completed',decision='MATCH',phase='completed')
    settled=time.perf_counter();published=False
    if enabled:published=summary.publish('alice','run');assert published
    finished=time.perf_counter()
    # Race a real old-style write of the same completed row against a projection
    # and actual global-fenced claim. This sample does not force an artificial
    # Python pause; the separate correctness smoke proves the adversarial chain.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
     def mutation():
      with other.tx() as c:c.execute(f'UPDATE {repo.table} SET updated_at=updated_at WHERE id=%s',('run',))
     def projected():
      if enabled:summary.publish('alice','run')
     future=pool.submit(mutation);background=pool.submit(projected)
     begin_claim=time.perf_counter();claimed=repo.claim();claim_end=time.perf_counter()
     future.result();background.result()
    assert claimed and claimed['id']=='queued'
    if iteration>=4:
     sample=samples['after' if enabled else 'before']
     for key,value in [('settlement',settled-started),('publication',finished-settled),('worker_total',finished-started),('competing_claim',claim_end-begin_claim)]:sample[key].append(value)
  item={'quality_fixture_bytes':size,'samples_seconds':samples,'p95_seconds':{name:{key:p95(v) for key,v in values.items()} for name,values in samples.items()}}
  report.append(item);print(json.dumps({'bytes':size,'p95_seconds':item['p95_seconds']}),flush=True)
 result={'scope':'31 alternating samples per synthetic size after 4 warmups; actual update_run settlement and claim, no model/PLC; production payload distribution unknown',
         'p95_method':'nearest-rank ceil(.95*n)-1','cases':report}
 if args.report:
  with args.report.open('x',encoding='utf-8') as output:output.write(json.dumps(result,indent=2)+'\n')
 else:print(json.dumps(result),flush=True)
 # Declared before execution: bounded optional occupancy; no notable global-path
 # regression beyond scheduling noise. These are offline, synthetic gates only.
 for item in report:
  before=item['p95_seconds']['before'];after=item['p95_seconds']['after']
  assert after['publication']<=.05,after
  for key in ('settlement','competing_claim'):
   assert after[key]<=max(before[key]*1.25,before[key]+.005),(key,before,after)
finally:
 pending=sys.exc_info()[0] is not None;cleanup_error=None
 for conn in conns:
  try:conn.rollback()
  except Exception as exc:cleanup_error=cleanup_error or exc
 if conns:
  try:
   with default_postgres_connector(os.environ['VANTALINE_POSTGRES_DSN']) as cleanup:
    execute(cleanup,f'DROP SCHEMA IF EXISTS "{schema}" CASCADE');cleanup.commit()
  except Exception as exc:cleanup_error=cleanup_error or exc
 for conn in conns:
  try:conn.close()
  except Exception as exc:cleanup_error=cleanup_error or exc
 if cleanup_error is not None:
  if not pending:raise cleanup_error
  print('Additional fixture cleanup failure; original exception retained',file=sys.stderr)

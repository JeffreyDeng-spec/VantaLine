"""Pipeline application-instance state ownership and original guard semantics."""
import ast,os,sys,threading,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from canonical_application_source_contract import read_checked_application_source
from application_integration_source_contract import restore_plc_domain_root
BASELINE=os.environ.get('VANTALINE_PIPELINE_OWNER_BASELINE_SOURCE')
NAMES={'_pipeline_tasks_lock':'task_lock','_pipeline_state_lock':'state_lock','_pipeline_auto_agent_lock':'auto_agent_lock','_pipeline_auto_agent_inflight':'auto_agent_inflight','_pipeline_recommendation_lock':'recommendation_lock','_pipeline_recommendation_inflight':'recommendation_inflight','_pipeline_advance_registry_lock':'advance_registry_lock','_pipeline_advance_inflight':'advance_inflight','_pipeline_advance_cancel':'advance_cancel','_pipeline_tasks_sync_last_at':'last_sync_at'}
def create():
 if BASELINE:
  t=ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig'));nodes=[n for n in t.body if isinstance(n,(ast.Assign,ast.AnnAssign)) and any(isinstance(x,ast.Name) and x.id in NAMES for x in (n.targets if isinstance(n,ast.Assign) else [n.target]))];assert len(nodes)==10;ns={'threading':threading};exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return {v:ns[k] for k,v in NAMES.items()}
 from local_inspection_service.pipeline.runtime_state import PipelineRuntimeState
 return PipelineRuntimeState().__dict__
class Contracts(unittest.TestCase):
 def test_initial_empty_registries_and_clock(self):
  s=create();self.assertEqual(s['auto_agent_inflight'],set());self.assertEqual(s['recommendation_inflight'],set());self.assertEqual(s['advance_inflight'],set());self.assertEqual(s['advance_cancel'],{});self.assertEqual(s['last_sync_at'],0.0)
 def test_independent_instances_do_not_share_locks_or_registries(self):
  a,b=create(),create()
  for n in NAMES.values():
   if n!='last_sync_at':self.assertIsNot(a[n],b[n])
  a['advance_inflight'].add('task');event=threading.Event();a['advance_cancel']['task']=event;event.set();self.assertFalse(b['advance_inflight']);self.assertFalse(b['advance_cancel']);self.assertTrue(a['advance_cancel']['task'].is_set())
 def test_original_lock_types_and_independent_guard_scopes(self):
  s=create()
  for n in ('task_lock','auto_agent_lock','recommendation_lock','advance_registry_lock'):
   lock=s[n];self.assertTrue(lock.acquire(False));self.assertFalse(lock.acquire(False));lock.release()
  lock=s['state_lock'];self.assertTrue(lock.acquire(False));self.assertTrue(lock.acquire(False));lock.release();lock.release()
  with s['task_lock']:
   for n in ('auto_agent_lock','recommendation_lock','advance_registry_lock'):self.assertTrue(s[n].acquire(False));s[n].release()
 def test_guarded_registration_from_two_threads(self):
  s=create();barrier=threading.Barrier(3);out=[]
  def run():
   barrier.wait(timeout=3)
   with s['advance_registry_lock']:
    if 'same' in s['advance_inflight']:out.append(False)
    else:s['advance_inflight'].add('same');out.append(True)
  workers=[threading.Thread(target=run) for _ in range(2)]
  for w in workers:w.start()
  barrier.wait(timeout=3)
  for w in workers:w.join(timeout=3);self.assertFalse(w.is_alive())
  self.assertEqual(sorted(out),[False,True])
 @unittest.skipIf(bool(BASELINE),'new owner setter and composition')
 def test_setter_no_conversion_and_live_entry_clock(self):
  from local_inspection_service.pipeline.runtime_state import PipelineRuntimeState
  a,b=PipelineRuntimeState(),PipelineRuntimeState();value=object();a.set_last_sync_at(value);self.assertIs(a.last_sync_at,value);self.assertEqual(b.last_sync_at,0.0)
  tree=ast.parse(restore_plc_domain_root(read_checked_application_source(ROOT / 'local_inspection_service/server.py')));self.assertFalse(any(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_pipeline_tasks_sync_last_at' for t in n.targets) for n in tree.body));self.assertTrue(any(isinstance(n,ast.Lambda) and ast.unparse(n.body)=='_pipeline_runtime.last_sync_at' for n in ast.walk(tree)))
if __name__=='__main__':unittest.main()

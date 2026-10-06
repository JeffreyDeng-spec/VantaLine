"""Auto-optimization shared guard and separate task-thread registries."""
import ast,os,sys,threading,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_AUTO_OPT_OWNER_BASELINE_SOURCE')
NAMES={'_auto_optimize_lock':'lock','_auto_optimize_label_threads':'label_threads','_auto_optimize_shadow_threads':'shadow_threads'}
def create():
 if BASELINE:
  tree=ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig'));nodes=[n for n in tree.body if isinstance(n,(ast.Assign,ast.AnnAssign)) and any(isinstance(t,ast.Name) and t.id in NAMES for t in(n.targets if isinstance(n,ast.Assign) else[n.target]))];assert len(nodes)==3;ns={'threading':threading};exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return {v:ns[k] for k,v in NAMES.items()}
 from local_inspection_service.training.auto_optimization_runtime_state import AutoOptimizationRuntimeState
 return AutoOptimizationRuntimeState().__dict__
class Contracts(unittest.TestCase):
 def test_separate_registries_preserve_thread_identity(self):
  s=create();thread=threading.Thread();s['label_threads']['same']=thread;self.assertIs(s['label_threads']['same'],thread);self.assertEqual(s['shadow_threads'],{});self.assertFalse(thread.is_alive())
 def test_guard_is_reentrant_and_released_after_error(self):
  s=create();lock=s['lock']
  with self.assertRaises(ValueError):
   with lock:
    with lock:raise ValueError('failure')
  self.assertTrue(lock.acquire(False));lock.release()
 def test_guard_excludes_other_thread(self):
  s=create();entered=threading.Event();release=threading.Event();out=[]
  def run():
   with s['lock']:entered.set();release.wait(timeout=3)
  worker=threading.Thread(target=run);worker.start();self.assertTrue(entered.wait(timeout=3))
  try:self.assertFalse(s['lock'].acquire(False))
  finally:release.set();worker.join(timeout=3)
  self.assertFalse(worker.is_alive());self.assertTrue(s['lock'].acquire(False));s['lock'].release()
 def test_application_instances_isolate_state(self):
  a,b=create(),create()
  for n in NAMES.values():self.assertIsNot(a[n],b[n])
  a['label_threads']['one']=object();a['shadow_threads']['two']=object();self.assertEqual(b['label_threads'],{});self.assertEqual(b['shadow_threads'],{})
 @unittest.skipIf(bool(BASELINE),'candidate owner composition')
 def test_actual_aliases_have_one_owner(self):
  tree=ast.parse((ROOT/'local_inspection_service/server.py').read_text())
  for name,field in NAMES.items():
   node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets));self.assertEqual(ast.unparse(node.value),'_auto_optimization_runtime.'+field)
if __name__=='__main__':unittest.main()

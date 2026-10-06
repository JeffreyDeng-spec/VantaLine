"""Image worker ownership and concurrent starts without real jobs."""
import ast,os,sys,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_IMAGE_WORKER_OWNER_BASELINE_SOURCE')
def create(target, factory):
 if BASELINE:
  tree=ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig'));node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='start_image_worker');ns={'_image_worker_lock':threading.Lock(),'_image_worker_thread':None,'threading':SimpleNamespace(Thread=factory),'image_worker_loop':target};exec(compile(ast.Module(body=[node],type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(start=ns['start_image_worker'],peek=lambda:ns['_image_worker_thread']),ns
 from local_inspection_service.runtime.image_worker import ImageWorkerRuntime
 b={'factory':factory,'target':target};owner=ImageWorkerRuntime(target=lambda:b['target'],threads=lambda:b['factory']);return SimpleNamespace(start=owner.start,peek=lambda:owner.thread,owner=owner),b
class Thread:
 def __init__(self):self.alive=False;self.starts=0
 def is_alive(self):return self.alive
 def start(self):self.starts+=1;self.alive=True
class Contracts(unittest.TestCase):
 def setUp(self):self.target=Mock();self.thread=Thread();self.factory=Mock(return_value=self.thread);self.s,self.b=create(self.target,self.factory)
 def test_constructor_does_not_start_and_start_keeps_arguments(self):
  self.factory.assert_not_called();self.target.assert_not_called();self.assertIsNone(self.s.peek());self.assertTrue(self.s.start());self.factory.assert_called_once_with(target=self.target,name='image-generation-worker',daemon=True);self.assertIs(self.s.peek(),self.thread);self.assertEqual(self.thread.starts,1);self.target.assert_not_called()
 def test_live_worker_rejects_duplicate_and_dead_worker_replaced(self):
  self.assertTrue(self.s.start());self.assertFalse(self.s.start());self.assertEqual(self.factory.call_count,1);self.thread.alive=False;next_thread=Thread();self.factory.return_value=next_thread;self.assertTrue(self.s.start());self.assertIs(self.s.peek(),next_thread);self.assertEqual(self.thread.starts,1)
 def test_factory_failure_retains_previous_dead_thread(self):
  self.s.start();self.thread.alive=False;error=ValueError('factory');self.factory.side_effect=error
  with self.assertRaises(ValueError) as caught:self.s.start()
  self.assertIs(caught.exception,error);self.assertIs(self.s.peek(),self.thread)
 def test_start_failure_retains_new_thread_and_next_start_can_retry(self):
  error=RuntimeError('start');self.thread.start=Mock(side_effect=error)
  with self.assertRaises(RuntimeError) as caught:self.s.start()
  self.assertIs(caught.exception,error);self.assertIs(self.s.peek(),self.thread);next_thread=Thread();self.factory.return_value=next_thread;self.assertTrue(self.s.start());self.assertIs(self.s.peek(),next_thread)
 def test_liveness_error_releases_lock_and_does_not_construct(self):
  self.s.start();self.thread.is_alive=Mock(side_effect=RuntimeError('alive'))
  with self.assertRaisesRegex(RuntimeError,'alive'):self.s.start()
  self.factory.assert_called_once();self.thread.is_alive=Mock(return_value=True);self.assertFalse(self.s.start())
 def test_two_concurrent_requests_start_one_worker(self):
  barrier=threading.Barrier(3);results=[]
  def run():barrier.wait(timeout=3);results.append(self.s.start())
  threads=[threading.Thread(target=run) for _ in range(2)]
  for t in threads:t.start()
  barrier.wait(timeout=3)
  for t in threads:t.join(timeout=3);self.assertFalse(t.is_alive())
  self.assertEqual(sorted(results),[False,True]);self.factory.assert_called_once();self.assertEqual(self.thread.starts,1)
 def test_independent_owners_and_late_target(self):
  other_thread=Thread();other,_=create(Mock(),Mock(return_value=other_thread));new_target=Mock();self.b['image_worker_loop' if BASELINE else 'target']=new_target;self.assertTrue(self.s.start());self.factory.assert_called_once_with(target=new_target,name='image-generation-worker',daemon=True);self.assertTrue(other.start());self.assertIs(other.peek(),other_thread)
 @unittest.skipIf(bool(BASELINE),'candidate owns process registry')
 def test_registry_isolation_and_entry_state_removed(self):
  other,_=create(Mock(),Mock());self.s.owner.processes['test']=object();self.assertEqual(other.owner.processes,{})
  tree=ast.parse((ROOT/'local_inspection_service/server.py').read_text());assigned={t.id for n in tree.body if isinstance(n,ast.Assign) for t in n.targets if isinstance(t,ast.Name)}|{n.target.id for n in tree.body if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name)};self.assertNotIn('_image_worker_thread',assigned);self.assertNotIn('_image_worker_lock',assigned);self.assertIn('_image_worker_runtime',assigned)
if __name__=='__main__':unittest.main()

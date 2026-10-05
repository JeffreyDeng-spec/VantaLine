"""Request, TTL and JSON generation-cache lifecycle contracts."""
import ast,asyncio,contextlib,contextvars,json,os,sys,tempfile,threading,unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_READ_CACHE_BASELINE_SOURCE')
NAMES=('read_path_cache_scope','store_read_cache_get','store_read_cache_put','store_read_cache_invalidate','load_json_file_mtime_cached')
def create(b):
 if BASELINE:
  nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==5
  ns=dict(b,Any=Any,Path=Path,json=json,contextlib=contextlib);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
 from local_inspection_service.runtime.read_caches import RequestReadCache,StoreReadCache,JsonFileReadCache
 request=RequestReadCache();store=StoreReadCache(lambda:b['STORE_READ_CACHE_TTL_SECONDS'],lambda:b['time'].monotonic());files=JsonFileReadCache(lambda:b['_business_files']);b['_read_path_cache']=request.current;b['_store_read_cache']=store.values;b['_json_file_cache']=files.values
 return SimpleNamespace(read_path_cache_scope=request.scope,store_read_cache_get=store.get,store_read_cache_put=store.put,store_read_cache_invalidate=store.invalidate,load_json_file_mtime_cached=files.load),b
class Contracts(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'one.json';self.now=100.;self.runtime=None
  files=SimpleNamespace(runtime=lambda path:self.runtime,read_text=lambda path,**kw:path.read_text(**kw))
  b=dict(_read_path_cache=contextvars.ContextVar('test-request-cache',default=None),_store_read_cache_lock=threading.Lock(),_store_read_cache={},_json_file_cache_lock=threading.Lock(),_json_file_cache={},STORE_READ_CACHE_TTL_SECONDS=5.,time=SimpleNamespace(monotonic=lambda:self.now),_business_files=files)
  self.s,self.b=create(b)
 def test_nested_request_identity_and_exception_reset(self):
  current=self.b['_read_path_cache'];self.assertIsNone(current.get())
  with self.assertRaisesRegex(RuntimeError,'sentinel'):
   with self.s.read_path_cache_scope():
    first=current.get();first['value']=1
    with self.s.read_path_cache_scope():self.assertIs(current.get(),first)
    raise RuntimeError('sentinel')
  self.assertIsNone(current.get())
 def test_request_thread_and_async_context(self):
  current=self.b['_read_path_cache'];barrier=threading.Barrier(2)
  def worker(value):
   with self.s.read_path_cache_scope():current.get()['value']=value;barrier.wait();return current.get()['value']
  with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(list(pool.map(worker,['alice','bob'])),['alice','bob'])
  async def scenario():
   with self.s.read_path_cache_scope():
    current.get()['value']='async';self.assertEqual(await asyncio.to_thread(lambda:current.get()['value']),'async')
  asyncio.run(scenario());self.assertIsNone(current.get())
 def test_ttl_exact_boundary_and_value_identity(self):
  value={'mutable':[]};self.assertEqual(self.s.store_read_cache_get('x'),(False,None));self.s.store_read_cache_put('x',value);self.now=104.999;hit,cached=self.s.store_read_cache_get('x');self.assertTrue(hit);self.assertIs(cached,value);self.now=105.;self.assertEqual(self.s.store_read_cache_get('x'),(False,None));self.assertIn('x',self.b['_store_read_cache'])
 def test_ttl_replacement_invalidation_and_clock_failure(self):
  self.s.store_read_cache_put('x',None);self.assertEqual(self.s.store_read_cache_get('x'),(True,None));self.s.store_read_cache_put('y',1);self.s.store_read_cache_invalidate('x','missing');self.assertEqual(self.s.store_read_cache_get('x'),(False,None));self.assertEqual(self.s.store_read_cache_get('y'),(True,1));self.b['time'].monotonic=Mock(side_effect=RuntimeError('clock'))
  with self.assertRaisesRegex(RuntimeError,'clock'):self.s.store_read_cache_put('z',3)
  self.b['time'].monotonic=lambda:101.;self.assertEqual(self.s.store_read_cache_get('z'),(False,None))
 def test_local_missing_invalid_and_identity_revalidation(self):
  self.assertIsNone(self.s.load_json_file_mtime_cached(self.path));self.path.write_text('bad');self.assertIsNone(self.s.load_json_file_mtime_cached(self.path));self.path.write_text('{"v":1}');first=self.s.load_json_file_mtime_cached(self.path);self.assertEqual(first,{'v':1});self.assertIs(self.s.load_json_file_mtime_cached(self.path),first);self.path.write_text('{"v":222}');self.assertEqual(self.s.load_json_file_mtime_cached(self.path),{'v':222})
 def test_same_mtime_size_retains_original_cache_contract(self):
  self.path.write_text('{"v":1}');stat=self.path.stat();first=self.s.load_json_file_mtime_cached(self.path);self.path.write_text('{"v":2}');os.utime(self.path,ns=(stat.st_atime_ns,stat.st_mtime_ns));self.assertIs(self.s.load_json_file_mtime_cached(self.path),first)
 def test_local_read_error_scope(self):
  self.path.write_text('{}');self.b['_business_files'].read_text=Mock(side_effect=OSError('read'));self.assertIsNone(self.s.load_json_file_mtime_cached(self.path));self.b['_business_files'].read_text=Mock(side_effect=ValueError('not decode'))
  with self.assertRaisesRegex(ValueError,'not decode'):self.s.load_json_file_mtime_cached(self.path)
 def artifact(self,row,mode='cos'):
  self.runtime=SimpleNamespace(mode=mode,key=lambda path:'key',store=SimpleNamespace(locations=SimpleNamespace(get=lambda key:row),cache=SimpleNamespace(open=lambda r:contextlib.nullcontext(self.path))))
 def test_cos_unavailable_states_and_hybrid_fallback(self):
  self.path.write_text('{"v":1}');self.artifact(None);self.assertIsNone(self.s.load_json_file_mtime_cached(self.path));self.artifact(SimpleNamespace(state='pending'));self.assertIsNone(self.s.load_json_file_mtime_cached(self.path));self.artifact(None,'hybrid');self.assertEqual(self.s.load_json_file_mtime_cached(self.path),{'v':1})
 def test_cos_generation_and_size_cache_identity(self):
  row=SimpleNamespace(state='ready',generation=1,size=7);self.artifact(row);self.path.write_text('{"v":1}');first=self.s.load_json_file_mtime_cached(self.path);self.path.write_text('{"v":2}');self.assertIs(self.s.load_json_file_mtime_cached(self.path),first);row.generation=2;self.assertEqual(self.s.load_json_file_mtime_cached(self.path),{'v':2});row.size=9;self.path.write_text('{"v":333}');self.assertEqual(self.s.load_json_file_mtime_cached(self.path),{'v':333})
 def test_cos_decode_only_caught_and_read_error_propagates(self):
  row=SimpleNamespace(state='ready',generation=1,size=7);self.artifact(row);self.path.write_text('invalid');self.assertIsNone(self.s.load_json_file_mtime_cached(self.path));sentinel=OSError('cos read');self.b['_business_files'].read_text=Mock(side_effect=sentinel)
  with self.assertRaises(OSError) as err:self.s.load_json_file_mtime_cached(self.path)
  self.assertIs(err.exception,sentinel)
 @unittest.skipIf(bool(BASELINE),'new state ownership only')
 def test_independent_cache_instances(self):
  from local_inspection_service.runtime.read_caches import RequestReadCache,StoreReadCache,JsonFileReadCache
  first=RequestReadCache();second=RequestReadCache()
  with first.scope():self.assertIsNone(second.current.get())
  first=StoreReadCache(lambda:5.,lambda:0.);second=StoreReadCache(lambda:5.,lambda:0.);first.put('x',1);self.assertEqual(second.get('x'),(False,None));self.assertIsNot(first.lock,second.lock)
  first=JsonFileReadCache(lambda:self.b['_business_files']);second=JsonFileReadCache(lambda:self.b['_business_files']);self.assertIsNot(first.values,second.values);self.assertIsNot(first.lock,second.lock)
if __name__=='__main__':unittest.main()

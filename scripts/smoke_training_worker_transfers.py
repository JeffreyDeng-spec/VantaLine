"""Synthetic streamed transfer contracts; all HTTP, threads and events are test substitutes."""
from contextlib import ExitStack
import json
import io
import types
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, call, patch
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def _capture_worker_transfer_window(ns,site,mode):
 events=[];waits=[];started=[];targets=[]
 class Response:
  status_code=200;headers={'Content-Length':'2'}
  def __enter__(self):return self
  def __exit__(self,*exc):return False
  def iter_content(self,**kwargs):return iter([b'{}'])
 response=Response()
 class FakeThread:
  def __init__(self,**kwargs):targets.append(kwargs['target'])
  def start(self):started.append(True)
 def set_callback(callback):
  if site=='get':ns['requests'].get=callback
  elif site=='thread':ns['threading'].Thread=callback
  else:ns['update_training_task']=callback
 def called(label):
  def callback(*args,**kwargs):
   events.append(label)
   return response if site=='get' else FakeThread(**kwargs) if site=='thread' else None
  return callback
 a,b,c=called('A'),called('B'),called('C')
 def prior():events.append('prior');set_callback(a if mode=='ordinary' else b if mode=='prior' else None)
 def argument():events.append('argument');set_callback(c)
 def wait(interval):
  waits.append(interval)
  if len(waits)==1:
   if site=='update':prior()
   return False
  return True
 stop=types.SimpleNamespace(wait=wait)
 def event():
  if site=='thread':prior()
  return stop
 ns.update(windows_worker_base_url=lambda:'https://fixture.invalid',windows_worker_headers=lambda:{},requests=types.SimpleNamespace(get=lambda *a,**k:response,RequestException=requests.RequestException),threading=types.SimpleNamespace(Event=event,Thread=FakeThread),update_training_task=lambda *a,**k:None)
 set_callback(a);state={'done':1,'total':2};job='job';original_buffer=io.BytesIO
 def buffer(*args,**kwargs):prior();return original_buffer(*args,**kwargs)
 if site=='get':ns['windows_worker_headers']=lambda:argument() or {}
 elif site=='thread':
  class Job:
   def __format__(self,spec):argument();return 'job'
  job=Job()
 else:
  class State(dict):
   def get(self,key,default=None):
    if key=='done':argument()
    return super().get(key,default)
  state=State(state)
 caught=None
 try:
  if site=='get':
   with patch.object(io,'BytesIO',buffer):ns['windows_worker_get_json_streamed']('/download',state=state,timeout_seconds=1)
  else:
   ns['_start_transfer_progress_thread'](job,state,done_field='sent',total_field='size',status_field='status')
   if site=='update':targets[0]()
 except BaseException as error:caught=error
 if mode=='missing' and site!='update':assert type(caught) is TypeError,(caught,events)
 else:assert caught is None,(caught,events)
 assert events==['prior','argument']+([] if mode=='missing' else ['A' if mode=='ordinary' else 'B']),events
 if site=='thread':assert len(started)==int(mode!='missing'),started
 if site=='update':assert waits==[1.5,1.5],waits
 return events


class TransferFixture:
    def __init__(self,root):
        self.root=Path(root); self.archive=self.root/'归档.zip'; self.data=bytes(range(256))*2048+b'last!!!'; self.archive.write_bytes(self.data)
        self.events=[]; self.state={'done':77,'total':88,'other':99}; self.parts=[]; self.counts=[]; self.chunks=[b'{"ok":',b'',b'true}']
        self.base=Mock(side_effect=lambda:self.event('base') or 'https://fixture.invalid/base')
        self.headers=Mock(side_effect=lambda:self.event('headers') or {'X-Fixture':'yes','Content-Type':'old','Content-Length':'old'})
        self.uuid=Mock(side_effect=lambda:self.event('uuid') or SimpleNamespace(hex='abcdef'))
        self.response=MagicMock(status_code=200,headers={'Content-Length':'11'}); self.body={'ok':True}; self.response.text='fallback'
        self.response.json.side_effect=lambda:self.event('json') or self.body
        self.response.__enter__.side_effect=lambda:self.event('enter') or self.response
        self.response.__exit__.side_effect=lambda *args:self.event('exit') or False
        self.response.iter_content.side_effect=lambda **kwargs:iter(self.chunks)
        self.post=Mock(side_effect=self.consume); self.get=Mock(side_effect=lambda *args,**kwargs:self.event('get') or self.response)
        self.stop=Mock(); self.stop.wait.side_effect=[True]; self.event_factory=Mock(side_effect=lambda:self.event('event') or self.stop)
        self.thread=Mock(); self.thread.start.side_effect=lambda:self.event('start')
        self.thread_factory=Mock(side_effect=lambda **kwargs:self.event('thread') or self.thread)
        self.update=Mock(side_effect=lambda *args,**kwargs:self.event('update'))
    def event(self,name): self.events.append(name)
    def consume(self,*args,**kwargs):
        self.event('post')
        for part in kwargs['data']: self.parts.append(part); self.counts.append(dict(self.state))
        return self.response
    def bind(self,api,stack):
        for name,value in {'windows_worker_base_url':self.base,'windows_worker_headers':self.headers,'update_training_task':self.update}.items():
            stack.enter_context(patch.object(api,name,value))
        stack.enter_context(patch.object(requests,'post',self.post)); stack.enter_context(patch.object(requests,'get',self.get))
        stack.enter_context(patch('uuid.uuid4',self.uuid)); stack.enter_context(patch.object(threading,'Event',self.event_factory)); stack.enter_context(patch.object(threading,'Thread',self.thread_factory))


class TrainingWorkerTransferContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ); cls.environment.start(); cls.runtime=tempfile.TemporaryDirectory(prefix='worker-transfer-root-')
        root=Path(cls.runtime.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close); self.f=TransferFixture(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='worker-transfer-')))
        self.f.bind(self.api,self.stack)
        for target in ['requests.request','subprocess.Popen','os.kill']:
            self.stack.enter_context(patch(target,side_effect=AssertionError('unexpected external operation')))
    def upload(self): return self.api.windows_worker_upload_bundle_streamed('upload',metadata_json='环境 metadata',archive_path=self.f.archive,state=self.f.state,timeout_seconds=3.5)
    def download(self): return self.api.windows_worker_get_json_streamed('/download',state=self.f.state,timeout_seconds=4.5)
    def progress(self,**kwargs):
        values={'done_field':'sent','total_field':'size','status_field':'status',**kwargs}
        return self.api._start_transfer_progress_thread(' job ',self.f.state,**values)
    def test_upload_exact_utf8_multipart_chunk_size_and_progress_before_yield(self):
        f=self.f; self.assertIs(self.upload(),f.body)
        boundary='----vantalineabcdef'
        preamble=(f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n环境 metadata\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="dataset_archive"; filename="归档.zip"\r\nContent-Type: application/zip\r\n\r\n').encode('utf-8')
        epilogue=f'\r\n--{boundary}--\r\n'.encode()
        self.assertEqual(f.parts,[preamble,f.data[:262144],f.data[262144:524288],f.data[524288:],epilogue])
        self.assertEqual([s['done'] for s in f.counts],[0,262144,524288,len(f.data),len(f.data)])
        self.assertTrue(all(s['total']==len(f.data) and s['other']==99 for s in f.counts))
        f.post.assert_called_once(); self.assertEqual(f.post.call_args.args,('https://fixture.invalid/base/upload',))
        self.assertEqual(f.post.call_args.kwargs['headers'],{'X-Fixture':'yes','Content-Type':'multipart/form-data; boundary='+boundary,'Content-Length':str(len(preamble)+len(f.data)+len(epilogue))})
        self.assertEqual(f.post.call_args.kwargs['timeout'],3.5); self.assertEqual(f.events,['base','uuid','headers','post','json'])
        f.response.raise_for_status.assert_not_called(); f.response.close.assert_not_called(); f.response.__enter__.assert_not_called()
    def test_upload_shared_counter_is_read_again_between_chunks(self):
        f=self.f
        def consume(*args,**kwargs):
            body=kwargs['data']; next(body); next(body); self.assertEqual(f.state['done'],262144)
            f.state['done']='10'; next(body); self.assertEqual(f.state['done'],262154)
            list(body); return f.response
        f.post.side_effect=consume; self.upload(); self.assertEqual(f.state['done'],262161)
    def test_upload_empty_archive_and_lazy_open_after_preamble(self):
        f=self.f; f.archive.write_bytes(b''); self.upload(); self.assertEqual(len(f.parts),2); self.assertEqual((f.state['done'],f.state['total']),(0,0))
        original=Path.open; opened=[]; body_holder=[]
        def record(path,*args,**kwargs): opened.append(path); return original(path,*args,**kwargs)
        def consume(*args,**kwargs):
            body=kwargs['data']; body_holder.append(body); self.assertEqual(opened,[]); next(body); self.assertEqual(opened,[]); return f.response
        f.post.side_effect=consume
        with patch.object(Path,'open',autospec=True,side_effect=record):
            self.upload(); self.assertEqual(opened,[]); self.assertIsNotNone(body_holder[0].gi_frame)
            body_holder[0].close()
    def test_upload_preparation_failures_and_requestexception_boundary(self):
        f=self.f; f.base.side_effect=None; f.base.return_value=''
        with self.assertRaisesRegex(RuntimeError,'is not configured'): self.upload()
        f.uuid.assert_not_called(); f.headers.assert_not_called(); f.post.assert_not_called(); self.assertEqual(f.state,{'done':77,'total':88,'other':99})
        f.base.return_value='https://fixture.invalid'; error=OSError('stat')
        with patch.object(Path,'stat',side_effect=error):
            with self.assertRaises(OSError) as caught: self.upload()
        self.assertIs(caught.exception,error); self.assertEqual(f.state['done'],77); f.post.assert_not_called()
        error=requests.Timeout('headers'); f.headers.side_effect=[error,{}]
        with self.assertRaises(requests.Timeout) as caught: self.upload()
        self.assertIs(caught.exception,error); f.headers.assert_called_once(); f.post.assert_not_called(); self.assertEqual(f.state['done'],0)
        f.headers.side_effect=lambda:{}; f.post.side_effect=[requests.Timeout('uncertain'),f.response]
        with self.assertRaises(RuntimeError) as caught: self.upload()
        self.assertEqual(str(caught.exception),'Windows worker request failed: uncertain'); self.assertIsInstance(caught.exception.__cause__,requests.Timeout); f.post.assert_called_once()
    def test_upload_generator_read_error_is_not_retried_or_wrapped_as_request_error(self):
        f=self.f; error=OSError('read failed'); original=Path.open; holder=[]
        class BrokenReader:
            def __init__(self,handle): self.handle=handle; self.reads=0; holder.append(self)
            def __enter__(self): return self
            def __exit__(self,*args): self.handle.close()
            def read(self,size):
                self.reads+=1
                if self.reads==2: raise error
                return self.handle.read(size)
        with patch.object(Path,'open',autospec=True,side_effect=lambda path,*args,**kwargs:BrokenReader(original(path,*args,**kwargs))):
            with self.assertRaises(OSError) as caught: self.upload()
        self.assertIs(caught.exception,error); f.post.assert_called_once(); f.response.json.assert_not_called(); self.assertEqual(f.state['done'],262144)
        self.assertEqual(holder[0].reads,2); self.assertTrue(holder[0].handle.closed)
    def test_upload_json_http_error_and_nonmapping_response_contract(self):
        f=self.f
        for body,code,expected in [({'detail':''},400,'request failed'),({'detail':'denied'},403,'denied'),(['bad'],500,"['bad']"),(None,500,'request failed')]:
            f.body=body; f.response.status_code=code
            with self.assertRaisesRegex(RuntimeError,'Windows worker returned HTTP '+str(code)) as caught: self.upload()
            self.assertTrue(str(caught.exception).endswith(expected))
        f.response.status_code=200; f.response.json.side_effect=ValueError('bad json'); f.response.text='x'*550
        self.assertEqual(self.upload(),{'message':'x'*500})
        f.response.json.side_effect=lambda:f.body
        for body in [None,['ok'],3]: f.body=body; self.assertEqual(self.upload(),{'result':body})
        error=OSError('json'); f.response.json.side_effect=[error,{}]
        with self.assertRaises(OSError) as caught: self.upload()
        self.assertIs(caught.exception,error)
    def test_download_exact_request_shared_state_and_context_exit_before_decode(self):
        f=self.f; original=json.loads
        def loads(value): self.assertEqual(f.events[-1],'exit'); return original(value)
        with patch.object(json,'loads',side_effect=loads): self.assertEqual(self.download(),{'ok':True})
        f.get.assert_called_once_with('https://fixture.invalid/base/download',headers={'X-Fixture':'yes','Content-Type':'old','Content-Length':'old'},timeout=4.5,stream=True)
        f.response.iter_content.assert_called_once_with(chunk_size=262144); f.response.__exit__.assert_called_once()
        self.assertEqual(f.state,{'done':11,'total':11,'other':99}); self.assertEqual(f.events,['base','headers','get','enter','exit'])
        f.response.json.assert_not_called(); f.response.raise_for_status.assert_not_called()
    def test_download_bad_lengths_empty_chunks_and_nonmapping_json_remain_original(self):
        f=self.f
        for value in [None,'','invalid',[], -2,'-2']:
            f.response.headers={'Content-Length':value}; f.chunks=[b'null']; self.assertIsNone(self.download())
            self.assertEqual(f.state['total'],-2 if value in [-2,'-2'] else 0); self.assertEqual(f.state['done'],4)
        for value in [[],['x'],1,True,'scalar']:
            f.chunks=[json.dumps(value).encode()]; self.assertEqual(self.download(),value)
        f.state['done']=77; f.chunks=[b'',b'']; f.response.headers={}
        with self.assertRaisesRegex(RuntimeError,'non-JSON artifacts'): self.download()
        self.assertEqual((f.state['done'],f.state['total']),(77,0))
    def test_download_http_before_length_and_overflow_context_cleanup(self):
        f=self.f; f.response.status_code=400; f.response.headers=Mock(); f.response.iter_content.reset_mock()
        with self.assertRaisesRegex(RuntimeError,'HTTP 400'): self.download()
        f.response.headers.get.assert_not_called(); f.response.iter_content.assert_not_called(); self.assertEqual(f.state,{'done':77,'total':88,'other':99})
        f.response.status_code=200; f.response.headers={'Content-Length':float('inf')}; f.response.__exit__.reset_mock()
        with self.assertRaises(OverflowError): self.download()
        f.response.__exit__.assert_called_once(); f.response.iter_content.assert_not_called()
    def test_download_headers_requestexception_is_wrapped_but_generic_iteration_error_is_not(self):
        f=self.f; error=requests.Timeout('headers'); f.headers.side_effect=[error,{}]
        with self.assertRaises(RuntimeError) as caught: self.download()
        self.assertIs(caught.exception.__cause__,error); f.headers.assert_called_once(); f.get.assert_not_called()
        f.headers.side_effect=lambda:{}
        for error in [OSError('read'),requests.ConnectionError('disconnected')]:
            def chunks(**kwargs): yield b'{'; raise error
            f.response.iter_content.side_effect=chunks; f.get.reset_mock(); f.response.__exit__.reset_mock()
            with self.assertRaises(RuntimeError if isinstance(error,requests.RequestException) else OSError) as caught: self.download()
            if isinstance(error,requests.RequestException): self.assertIs(caught.exception.__cause__,error)
            else: self.assertIs(caught.exception,error)
            f.get.assert_called_once(); f.response.__exit__.assert_called_once(); self.assertEqual(f.state['done'],1)
    def test_download_invalid_utf8_or_json_wraps_after_context_exit(self):
        f=self.f
        for data in [bytes([255]),b'{bad']:
            f.chunks=[data]
            with self.assertRaisesRegex(RuntimeError,'Windows worker returned non-JSON artifacts') as caught: self.download()
            self.assertIsInstance(caught.exception.__cause__,ValueError); self.assertEqual(f.events[-1],'exit'); self.assertEqual(f.state['done'],len(data))
    def test_progress_constructor_and_stop_before_first_flush(self):
        f=self.f; result=self.progress(); self.assertEqual(result,(f.stop,f.thread)); self.assertEqual(f.events,['event','thread','start'])
        f.thread_factory.assert_called_once(); self.assertEqual(f.thread_factory.call_args.kwargs['name'],'transfer-progress- job '); self.assertTrue(f.thread_factory.call_args.kwargs['daemon'])
        f.stop.wait.assert_not_called(); f.thread_factory.call_args.kwargs['target'](); f.stop.wait.assert_called_once_with(1.5); f.update.assert_not_called()
        f.stop.set.assert_not_called(); f.thread.join.assert_not_called()
    def test_progress_state_and_update_are_late_and_ordinary_errors_are_swallowed(self):
        f=self.f; self.progress(interval=2.5); target=f.thread_factory.call_args.kwargs['target']; replacement=Mock(); loops=[]
        def wait(interval):
            self.assertEqual(interval,2.5); loops.append(True)
            if len(loops)==1: f.state.update(done='bad',total=10)
            elif len(loops)==2: f.state.update(done='3',total='4')
            elif len(loops)==3: f.state.update(done=8,total=9); self.api.update_training_task=replacement
            return len(loops)==4
        f.stop.wait.side_effect=wait; f.update.side_effect=OSError('flush')
        with patch.object(self.api,'update_training_task',f.update): target()
        f.update.assert_called_once_with(' job ',sent=3,size=4,status='running'); replacement.assert_called_once_with(' job ',sent=8,size=9,status='running')
        self.assertEqual(f.stop.wait.call_count,4)
    def test_progress_wait_and_baseexception_propagate_without_extra_flush(self):
        f=self.f; self.progress(); target=f.thread_factory.call_args.kwargs['target']; error=OSError('wait')
        f.stop.wait.side_effect=[error,True]
        with self.assertRaises(OSError) as caught: target()
        self.assertIs(caught.exception,error); f.stop.wait.assert_called_once(); f.update.assert_not_called()
        f.stop.wait.side_effect=[False,True]; f.update.side_effect=KeyboardInterrupt('cancel')
        with self.assertRaises(KeyboardInterrupt): target()
        f.update.assert_called_once(); f.stop.set.assert_not_called(); f.thread.join.assert_not_called()
    def test_progress_colliding_field_names_still_evaluate_both_counters_in_order(self):
        f=self.f; reads=[]
        class Counter:
            def __init__(self,name): self.name=name
            def __int__(self): reads.append(self.name); return 3
        f.state.update(done=Counter('done'),total=Counter('total')); self.progress(done_field='same',total_field='same',status_field='same')
        f.stop.wait.side_effect=[False,True]; f.thread_factory.call_args.kwargs['target']()
        self.assertEqual(reads,['done','total']); f.update.assert_called_once_with(' job ',same='running')
    def test_progress_factory_or_start_failure_does_not_stop_join_or_retry(self):
        f=self.f
        for stage,target in [('event',f.event_factory),('thread',f.thread_factory),('start',f.thread.start)]:
            with self.subTest(stage=stage):
                original=target.side_effect; error=OSError(stage); hits=[]
                def first(*args,**kwargs):
                    hits.append(True)
                    if len(hits)==1: raise error
                    return original(*args,**kwargs)
                target.side_effect=first
                try:
                    with self.assertRaises(OSError) as caught: self.progress()
                    self.assertIs(caught.exception,error); self.assertEqual(len(hits),1)
                finally: target.side_effect=original
                f.stop.set.assert_not_called(); f.thread.join.assert_not_called(); f.update.assert_not_called()


    def test_download_base_failures_precede_request_boundary_without_retry_or_state_mutation(self):
        f=self.f; before=dict(f.state); original_state=f.state
        f.base.side_effect=['','https://second.invalid']
        with self.assertRaises(RuntimeError) as caught: self.download()
        self.assertEqual(str(caught.exception),self.api.WINDOWS_WORKER_BASE_URL_ENV+' is not configured')
        f.base.assert_called_once_with()
        for callback in [f.headers,f.get,f.response.json,f.response.iter_content,f.response.__enter__,f.response.__exit__]: callback.assert_not_called()
        self.assertIs(f.state,original_state); self.assertEqual(f.state,before)
        f.base.reset_mock(); failure=requests.ConnectionError('base provider failed'); f.base.side_effect=[failure,'https://second.invalid']
        with self.assertRaises(requests.ConnectionError) as caught: self.download()
        self.assertIs(caught.exception,failure); f.base.assert_called_once_with()
        for callback in [f.headers,f.get,f.response.json,f.response.iter_content,f.response.__enter__,f.response.__exit__]: callback.assert_not_called()
        self.assertIs(f.state,original_state); self.assertEqual(f.state,before)

    def test_independent_transfers_and_progress_without_constructor_io_or_root_dependencies(self):
        from local_inspection_service.training.worker_transfers import WorkerTransfers
        from local_inspection_service.training.transfer_progress import TransferProgress
        instances=[]
        for owner in ['alice','bob']:
            directory=self.f.root/owner; directory.mkdir(); f=TransferFixture(directory)
            f.archive.write_bytes(owner.encode()); f.base.side_effect=lambda owner=owner:'https://'+owner+'.invalid/'
            f.headers.side_effect=None; f.headers.return_value={'X-Owner':owner}; f.body={'owner':owner}
            f.chunks=[json.dumps(f.body).encode()]; f.response.headers={'Content-Length':str(len(f.chunks[0]))}
            transport=WorkerTransfers(f.base,f.headers,f.post,lambda f=f:f.get,f.uuid)
            f.update_provider=Mock(side_effect=lambda f=f: f.update)
            progress=TransferProgress(f.update_provider,f.event_factory,lambda f=f:f.thread_factory)
            for callback in [f.base,f.headers,f.post,f.get,f.uuid,f.update,f.update_provider,f.event_factory,f.thread_factory]: callback.assert_not_called()
            self.assertEqual(f.events,[]); instances.append((owner,f,transport,progress))
        for name in ['windows_worker_base_url','windows_worker_headers','update_training_task','windows_worker_upload_bundle_streamed',
                     'windows_worker_get_json_streamed','_start_transfer_progress_thread']:
            self.stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('unexpected root callback')))
        for target in ['requests.post','requests.get','uuid.uuid4','threading.Event','threading.Thread']:
            self.stack.enter_context(patch(target,side_effect=AssertionError('unexpected global capability')))
        for index in [1,0,1,0]:
            owner,f,transport,progress=instances[index]; token=f.headers.return_value['X-Owner']
            result=transport.windows_worker_upload_bundle_streamed('upload',metadata_json=owner,archive_path=f.archive,state=f.state,timeout_seconds=2.5)
            self.assertIs(result,f.body); self.assertEqual(f.parts[-2],owner.encode()); self.assertEqual(f.state,{'done':len(owner),'total':len(owner),'other':99})
            self.assertEqual(f.post.call_args.args,('https://'+owner+'.invalid//upload',)); self.assertEqual(f.post.call_args.kwargs['headers']['X-Owner'],token)
            result=transport.windows_worker_get_json_streamed('download',state=f.state,timeout_seconds=7.5)
            self.assertEqual(result,{'owner':owner}); self.assertEqual(f.state['done'],len(f.chunks[0])); self.assertEqual(f.state['total'],len(f.chunks[0]))
            self.assertEqual(f.get.call_args.args,('https://'+owner+'.invalid//download',)); self.assertIs(f.get.call_args.kwargs['headers'],f.headers.return_value)
            f.stop.wait.side_effect=[False,True]
            returned=progress._start_transfer_progress_thread(owner,f.state,done_field='received',total_field='length',status_field='state',interval=2.5)
            self.assertEqual(returned,(f.stop,f.thread)); self.assertEqual(f.thread_factory.call_args.kwargs['name'],'transfer-progress-'+owner)
            f.state['done']+=1; f.thread_factory.call_args.kwargs['target']()
            self.assertEqual(f.update.call_args,call(owner,received=len(f.chunks[0])+1,length=len(f.chunks[0]),state='running'))
            self.assertEqual(f.stop.wait.call_args,call(2.5)); f.stop.set.assert_not_called(); f.thread.join.assert_not_called()
            f.headers.return_value={'X-Owner':owner+'-next'}
        for owner,f,transport,progress in instances:
            self.assertEqual(f.post.call_count,2); self.assertEqual(f.get.call_count,2); self.assertEqual(f.update.call_count,2)
            self.assertEqual(f.thread.start.call_count,2); self.assertEqual(f.response.__exit__.call_count,2)
            self.assertEqual(f.update_provider.call_args_list,[call(),call()])
        owner,f,transport,progress=instances[0]; f.update.reset_mock(); reads=[]
        class Counter:
            def __int__(counter): reads.append('int'); return 8
        f.state.update(done=Counter(),total=9)
        fatal=KeyboardInterrupt('provider cancelled')
        f.update_provider.reset_mock(); f.update_provider.side_effect=[OSError('lookup'),f.update,fatal]
        f.stop.wait.side_effect=[False,False,False,True]
        progress._start_transfer_progress_thread(owner,f.state,done_field='done',total_field='total',status_field='status')
        with self.assertRaises(KeyboardInterrupt) as caught:f.thread_factory.call_args.kwargs['target']()
        self.assertIs(caught.exception,fatal); self.assertEqual(reads,['int'])
        self.assertEqual(f.update_provider.call_args_list,[call(),call(),call()])
        f.update.assert_called_once_with(owner,done=8,total=9,status='running')
        f.stop.set.assert_not_called(); f.thread.join.assert_not_called()



    def test_progress_captures_update_before_state_get_and_counter_int(self):
        for stage in ['get','int']:
            with self.subTest(stage=stage):
                f=self.f; events=[]; first=Mock(side_effect=lambda *args,**kwargs:events.append('first'))
                later=Mock(side_effect=lambda *args,**kwargs:events.append('later')); self.api.update_training_task=first
                def switch(): events.append(stage); self.api.update_training_task=later
                class Counter:
                    def __int__(self): switch(); return 3
                class State(dict):
                    def get(self,key,default=None):
                        events.append(key)
                        if stage=='get' and key=='done':switch()
                        return super().get(key,default)
                f.state=State(done=Counter() if stage=='int' else 3,total='4')
                self.progress(); f.stop.wait.side_effect=[False,False,True]; f.thread_factory.call_args.kwargs['target']()
                first.assert_called_once_with(' job ',sent=3,size=4,status='running')
                later.assert_called_once_with(' job ',sent=3,size=4,status='running')
                self.assertEqual(events,['done',stage,'total','first','done',stage,'total','later'])
                f.stop.set.assert_not_called(); f.thread.join.assert_not_called()
    def test_progress_counter_failure_skips_write_and_next_iteration_rebinds(self):
        f=self.f; later=Mock(); reads=[]; error=ValueError('counter')
        class Counter:
            def __int__(counter):
                reads.append('int'); self.api.update_training_task=later
                if len(reads)==1:raise error
                return 5
        f.state.update(done=Counter(),total=6); self.progress(); f.stop.wait.side_effect=[False,False,True]
        f.thread_factory.call_args.kwargs['target'](); self.assertEqual(reads,['int','int'])
        f.update.assert_not_called(); later.assert_called_once_with(' job ',sent=5,size=6,status='running')


    def test_progress_two_counter_rebindings_keep_current_target_then_use_last(self):
        f=self.f; middle=Mock(); last=Mock(); reads=[]
        class Counter:
            def __init__(counter,name,target,value):counter.name,counter.target,counter.value=name,target,value
            def __int__(counter):reads.append(counter.name); self.api.update_training_task=counter.target; return counter.value
        f.state.update(done=Counter('done',middle,3),total=Counter('total',last,4))
        self.progress(); f.stop.wait.side_effect=[False,False,True]; f.thread_factory.call_args.kwargs['target']()
        f.update.assert_called_once_with(' job ',sent=3,size=4,status='running'); middle.assert_not_called()
        last.assert_called_once_with(' job ',sent=3,size=4,status='running'); self.assertEqual(reads,['done','total','done','total'])


    def test_progress_noncallable_update_evaluates_both_counters_before_next_flush(self):
        f=self.f; later=Mock(); reads=[]; self.api.update_training_task=None
        class Counter:
            def __init__(counter,name,value):counter.name,counter.value=name,value
            def __int__(counter):
                reads.append(counter.name)
                if counter.name=='done':self.api.update_training_task=later
                return counter.value
        f.state.update(done=Counter('done',3),total=Counter('total',4))
        self.progress(); f.stop.wait.side_effect=[False,False,True]; f.thread_factory.call_args.kwargs['target']()
        self.assertEqual(reads,['done','total','done','total']); f.update.assert_not_called()
        later.assert_called_once_with(' job ',sent=3,size=4,status='running')
        self.assertEqual(f.stop.wait.call_args_list,[call(1.5),call(1.5),call(1.5)])
        f.stop.set.assert_not_called(); f.thread.join.assert_not_called()


    def test_download_transport_captured_before_headers_and_refreshed_per_request(self):
        f=self.f; later=Mock(return_value=f.response); events=[]
        def headers():
            events.append('headers'); requests.get=later; return {'fixture':'yes'}
        f.headers.side_effect=headers
        self.assertEqual(self.download(),{'ok':True})
        f.get.assert_called_once(); later.assert_not_called()
        self.assertEqual(self.download(),{'ok':True})
        later.assert_called_once(); self.assertEqual(events,['headers','headers'])

    def test_thread_constructor_captured_after_event_before_job_format(self):
        f=self.f; later=Mock(return_value=f.thread); events=[]
        class Job:
            def __format__(job,spec):
                events.append('format'); threading.Thread=later; return 'job'
        self.api._start_transfer_progress_thread(Job(),f.state,done_field='done',total_field='total',status_field='status')
        f.thread_factory.assert_called_once(); later.assert_not_called()
        self.api._start_transfer_progress_thread(Job(),f.state,done_field='done',total_field='total',status_field='status')
        later.assert_called_once(); self.assertEqual(events,['format','format']); self.assertEqual(f.thread.start.call_count,2)

    def test_new_getters_fail_once_before_argument_effects_without_retry(self):
        from local_inspection_service.training.worker_transfers import WorkerTransfers
        from local_inspection_service.training.transfer_progress import TransferProgress
        f=self.f
        for site in ['get','thread']:
            with self.subTest(site=site):
                error=OSError(site); hits=[]; reads=[]
                def provider():
                    hits.append(site)
                    if len(hits)==1:raise error
                    return f.get if site=='get' else f.thread_factory
                class Job:
                    def __format__(job,spec):reads.append('format'); return 'job'
                f.headers.reset_mock(); f.thread_factory.reset_mock(); f.get.reset_mock(); f.event_factory.reset_mock()
                with self.assertRaises(OSError) as caught:
                    if site=='get': WorkerTransfers(f.base,f.headers,f.post,provider,f.uuid).windows_worker_get_json_streamed('download',state=f.state,timeout_seconds=4.5)
                    else: TransferProgress(lambda:f.update,f.event_factory,provider)._start_transfer_progress_thread(Job(),f.state,done_field='done',total_field='total',status_field='status')
                self.assertIs(caught.exception,error); self.assertEqual(hits,[site]); self.assertEqual(reads,[])
                f.headers.assert_not_called(); f.thread_factory.assert_not_called(); f.get.assert_not_called()
                self.assertEqual(f.event_factory.call_count,1 if site=='thread' else 0)


    def test_callback_selection_matches_original_before_argument_side_effects(self):
        for site in ('get','thread','update'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(site=site,mode=mode), patch.dict(self.api.__dict__):
                    _capture_worker_transfer_window(self.api.__dict__,site,mode)


    def test_transfer_io_first_failures_are_not_retried(self):
        for site in ['upload_base','uuid','stat','open','buffer','get','iterate','write','tell','getvalue','loads','length']:
            with self.subTest(site=site), ExitStack() as stack:
                f=TransferFixture(stack.enter_context(tempfile.TemporaryDirectory(prefix='transfer-failure-',dir=self.f.root)))
                f.bind(self.api,stack); error=OSError(site); hits=[]
                def first(callback):
                    def invoke(*args,**kwargs):
                        hits.append(site)
                        if len(hits)==1:raise error
                        return callback(*args,**kwargs)
                    return invoke
                action=lambda:self.api.windows_worker_get_json_streamed('download',state=f.state,timeout_seconds=4.5)
                if site in ['upload_base','uuid','stat','open']:
                    action=lambda:self.api.windows_worker_upload_bundle_streamed('upload',metadata_json='{}',archive_path=f.archive,state=f.state,timeout_seconds=3.5)
                if site=='upload_base':f.base.side_effect=first(f.base.side_effect)
                elif site=='uuid':f.uuid.side_effect=first(f.uuid.side_effect)
                elif site in ['stat','open']:
                    original=getattr(Path,site);fail=first(original)
                    def targeted(path,*args,**kwargs):return fail(path,*args,**kwargs) if path==f.archive else original(path,*args,**kwargs)
                    stack.enter_context(patch.object(Path,site,autospec=True,side_effect=targeted))
                elif site=='get':f.get.side_effect=first(f.get.side_effect)
                elif site=='iterate':f.response.iter_content.side_effect=first(f.response.iter_content.side_effect)
                elif site=='length':
                    class Headers(dict):
                        get=first(dict.get)
                    f.response.headers=Headers(f.response.headers)
                elif site=='loads':stack.enter_context(patch.object(json,'loads',side_effect=first(json.loads)))
                else:
                    original_buffer=io.BytesIO
                    if site=='buffer':factory=first(original_buffer)
                    else:
                        class Buffer:
                            def __init__(buffer):buffer.inner=original_buffer()
                            def write(buffer,*args):return buffer.inner.write(*args)
                            def tell(buffer,*args):return buffer.inner.tell(*args)
                            def getvalue(buffer,*args):return buffer.inner.getvalue(*args)
                        setattr(Buffer,site,first(getattr(Buffer,site)));factory=Buffer
                    stack.enter_context(patch.object(io,'BytesIO',factory))
                with self.assertRaises(OSError) as caught:action()
                self.assertIs(caught.exception,error); self.assertEqual(hits,[site])

    def test_progress_provider_error_skips_current_flush_without_inner_retry(self):
        from local_inspection_service.training.transfer_progress import TransferProgress
        f=self.f; hits=[]; reads=[]
        def provider():
            hits.append('provider')
            if len(hits)==1:raise OSError('provider')
            return f.update
        class State(dict):
            def get(state,*args):reads.append(args); return super().get(*args)
        progress=TransferProgress(provider,f.event_factory,lambda:f.thread_factory)
        progress._start_transfer_progress_thread('job',State(done=1,total=2),done_field='done',total_field='total',status_field='status')
        f.stop.wait.side_effect=[False,True]; f.thread_factory.call_args.kwargs['target']()
        self.assertEqual(hits,['provider']); self.assertEqual(reads,[]); f.update.assert_not_called()
        self.assertEqual(f.stop.wait.call_args_list,[call(1.5),call(1.5)])

    def test_json_and_content_length_fallbacks_do_not_retry_successful_second_read(self):
        f=self.f
        for site in ['upload_json','loads','length_value','length_type']:
            with self.subTest(site=site), ExitStack() as stack:
                hits=[]; error=TypeError(site) if site=='length_type' else ValueError(site)
                def first(callback):
                    def invoke(*args,**kwargs):
                        hits.append(site)
                        if len(hits)==1:raise error
                        return callback(*args,**kwargs)
                    return invoke
                if site=='upload_json':
                    stack.enter_context(patch.object(f.response,'json',side_effect=first(lambda:f.body)))
                    f.response.text='x'*550; self.assertEqual(self.upload(),{'message':'x'*500})
                elif site=='loads':
                    stack.enter_context(patch.object(json,'loads',side_effect=first(json.loads)))
                    with self.assertRaises(RuntimeError) as caught:self.download()
                    self.assertIs(caught.exception.__cause__,error)
                else:
                    class Headers(dict):get=first(dict.get)
                    stack.enter_context(patch.object(f.response,'headers',Headers({'Content-Length':'11'})))
                    self.assertEqual(self.download(),{'ok':True}); self.assertEqual(f.state['total'],0)
                self.assertEqual(hits,[site])


if __name__=='__main__': unittest.main()

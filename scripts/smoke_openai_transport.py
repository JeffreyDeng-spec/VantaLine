"""Offline OpenAI-compatible transport behavior captured before extraction."""
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
import urllib.error
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path.cwd()))


import json,time,urllib.error
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock,patch

def capture_openai_window(api,Fixture,site,mode='ordinary'):
 f=Fixture();f.setUp();events=[]
 try:
  with patch.dict(api.__dict__),ExitStack() as stack:
   config=api.AiProviderConfigError;error_type=api.AiProviderError;digest=api.sha256_bytes
   def factory(cls,label):
    def make(*a,**k):events.append(label);return cls(*a,**k)
    return make
   def pick(name,a,b,c):setattr(api,name,b if mode=='prior' else None if mode=='missing' else a)
   if site=='config':
    a,b,c=(factory(config,l) for l in 'ABC');api.AiProviderConfigError=a
    class Settings(dict):
     def get(self,k,*args):
      if k=='configured':pick('AiProviderConfigError',a,b,c);return False
      if k=='message':events.append('argument');api.AiProviderConfigError=c
      return super().get(k,*args)
    f.settings=Settings(f.settings,message='disabled')
   elif site=='open':
    original=f.open
    def opener(label):
     def call(*a,**k):events.append(label);return original(*a,**k)
     return call
    a,b,c=(opener(l) for l in 'ABC');api.ai_urlopen=a;clocks=[]
    def clock():
     clocks.append(1)
     if len(clocks)==2:pick('ai_urlopen',a,b,c)
     return float(len(clocks))
    stack.enter_context(patch.object(time,'monotonic',clock))
    class Timeout:
     def __float__(self):events.append('argument');api.ai_urlopen=c;return 13.5
    f.settings['timeout_seconds']=Timeout()
   elif site=='url_error':
    a,b,c=(factory(error_type,l) for l in 'ABC');api.AiProviderError=a
    class UrlError(urllib.error.URLError):
     def __getattribute__(self,k):
      if k=='reason':pick('AiProviderError',a,b,c)
      return super().__getattribute__(k)
    err=UrlError('synthetic')
    def fail(*a,**k):raise err
    f.open.side_effect=fail
    def text(*a):events.append('argument');api.AiProviderError=c;return 'bounded'
    api.bounded_text=text
   elif site in ('shape_digest','parse_digest'):
    def dig(label):
     def call(value):events.append(label);return digest(value)
     return call
    a,b,c=(dig(l) for l in 'ABC');api.sha256_bytes=a
    class Text(str):
     def __str__(self):return self
     def encode(self,*args,**kw):events.append('argument');api.sha256_bytes=c;return super().encode(*args,**kw)
    if site=='shape_digest':
     class Bytes(bytes):
      def decode(self,*args,**kw):return Text('invalid-json')
     f.response.read.side_effect=lambda:Bytes(b'bad')
     def error(message):pick('sha256_bytes',a,b,c);return error_type(message)
     api.AiProviderError=error
    else:
     original=json.loads
     def loads(value,*args,**kw):
      result=original(value,*args,**kw)
      if isinstance(result,dict) and 'choices' in result:result['choices'][0]['message']['content']=Text('content')
      return result
     stack.enter_context(patch.object(json,'loads',loads))
     def parse(value):pick('sha256_bytes',a,b,c);raise error_type('parse failure')
     api.parse_ai_json_object=parse
   else:raise AssertionError(site)
   caught=None;result=None
   try:result=f.provider().generate_json('system',[])
   except BaseException as exc:caught=exc
   assert 'argument' in events,(site,mode,caught,events)
   labels=[x for x in events if x in ('A','B','C')]
   if mode=='missing':
    assert type(caught) is TypeError,(site,caught,events)
    assert labels==[],events
   else:
    assert labels==['B' if mode=='prior' else 'A'],(site,caught,events)
    if site=='open':assert caught is None,(caught,events);assert result[0]=={'answer':42}
    else:assert isinstance(caught,config if site=='config' else error_type),(caught,events)
   return {'events':events,'error':type(caught).__name__ if caught else None,'open_count':f.open.call_count}
 finally:f.doCleanups()

def capture_openai_match(api,Fixture,mode):
 f=Fixture();f.setUp()
 try:
  with patch.dict(api.__dict__):
   original=api.AiProviderError;err=original('parse failure');other=type('OtherProviderError',(original,),{})
   def parse(value):api.AiProviderError=original if mode=='same' else other if mode=='changed' else None;raise err
   api.parse_ai_json_object=parse;digest=Mock(wraps=api.sha256_bytes);api.sha256_bytes=digest;caught=None
   try:f.provider().generate_json('s',[])
   except BaseException as exc:caught=exc
   if mode=='missing':assert type(caught) is TypeError and caught.__context__ is err,(caught,err)
   else:assert caught is err,caught
   assert hasattr(err,'response_sha256')==(mode=='same')
   assert digest.call_count==(1 if mode=='same' else 0)
   return {'error':type(caught).__name__,'evidence':hasattr(err,'response_sha256'),'digest_count':digest.call_count}
 finally:f.doCleanups()

def capture_openai_resources(api,Fixture,site):
 f=Fixture();f.setUp()
 try:
  failure=OSError('synthetic resource failure');caught=None
  if site=='enter':
   def enter():
    if f.response.__enter__.call_count==1:raise failure
    return f.response
   f.response.__enter__.side_effect=enter
  elif site in ('read','suppress'):
   def read():
    if f.response.read.call_count==1:raise failure
    return json.dumps(f.body).encode()
   f.response.read.side_effect=read
   if site=='suppress':f.response.__exit__.return_value=True
  elif site=='exit':
   def leave(*args):
    if f.response.__exit__.call_count==1:raise failure
    return False
   f.response.__exit__.side_effect=leave
  else:raise AssertionError(site)
  try:f.provider(True).generate_json('s',[])
  except BaseException as exc:caught=exc
  if site=='suppress':assert type(caught) is UnboundLocalError,caught
  else:assert caught is failure,caught
  assert f.open.call_count==1 and f.response.__enter__.call_count==1
  assert f.response.read.call_count==(0 if site=='enter' else 1)
  assert f.response.__exit__.call_count==(0 if site=='enter' else 1)
  if site in ('read','suppress'):assert f.response.__exit__.call_args.args[1] is failure
  f.record.assert_called_once();assert f.record.call_args.args[2:]==(False,{})
  return {'error':type(caught).__name__,'open':f.open.call_count,'enter':f.response.__enter__.call_count,'read':f.response.read.call_count,'exit':f.response.__exit__.call_count,'record':f.record.call_count,'usage':f.record.call_args.args[2:]}
 finally:f.doCleanups()

def capture_openai_resolver_binding(api,Fixture):
 f=Fixture();f.setUp()
 try:
  with patch.object(api,'resolve_model_profiles',side_effect=AssertionError('late resolver function lookup')) as forbidden:
   assert f.provider(True).generate_json('s',[])[0]=={'answer':42};forbidden.assert_not_called();f.record.assert_called_once()
  return {'transport_calls':f.open.call_count,'records':f.record.call_count,'late_resolver_lookup':0}
 finally:f.doCleanups()


class OpenAITransportContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = patch.dict(os.environ)
        cls.env.start()
        cls.tmp = tempfile.TemporaryDirectory(prefix='openai-transport-')
        root = Path(cls.tmp.name)
        (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        cls.env.stop()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name in ('requests.sessions.Session.request', 'urllib.request.urlopen', 'subprocess.Popen', 'os.kill'):
            self.stack.enter_context(patch(name, side_effect=AssertionError('external operation forbidden')))
        self.settings = dict(configured=True, provider='openai', model='synthetic-model',
                             base_url='https://fixture.invalid/completions', api_key='synthetic-key', timeout_seconds='13.5')
        self.record = Mock()
        self.stack.enter_context(patch.object(self.api, 'model_profile_service', SimpleNamespace(record_call=self.record)))
        self.open = self.stack.enter_context(patch.object(self.api, 'ai_urlopen'))
        self.body = dict(choices=[dict(message=dict(content='{"answer":42}'), finish_reason='stop')], usage={'total_tokens':7})
        self.response = Mock()
        self.response.__enter__ = Mock(return_value=self.response)
        self.response.__exit__ = Mock(return_value=False)
        self.response.read = Mock(side_effect=lambda:json.dumps(self.body).encode())
        self.open.return_value = self.response

    def provider(self, bound=False):
        if bound:self.settings['profile_id']='synthetic-profile'
        return self.api.OpenAICompatibleAiProvider(self.settings)

    def test_constructor_retains_settings_and_does_no_io(self):
        p=self.provider(True)
        self.assertIs(p.settings,self.settings)
        self.assertEqual(p.last_usage_metadata,{})
        self.open.assert_not_called();self.record.assert_not_called()

    def test_request_and_result_contract(self):
        p=self.provider();content=[{'type':'text','text':'synthetic input'}]
        with patch.object(self.api.time,'monotonic',side_effect=[10,11,11.125]):result=p.generate_json('system',content,max_tokens=71)
        self.assertEqual(result,({'answer':42},125))
        self.open.assert_called_once();request,settings=self.open.call_args.args
        self.assertIs(settings,self.settings);self.assertEqual(self.open.call_args.kwargs,{'timeout':13.5})
        self.assertEqual(request.full_url,self.settings['base_url']);self.assertEqual(request.method,'POST')
        self.assertEqual(dict(request.header_items()),{'Authorization':'Bearer synthetic-key','Content-type':'application/json'})
        self.assertEqual(json.loads(request.data),dict(model='synthetic-model',temperature=0,max_tokens=71,response_format={'type':'json_object'},messages=[{'role':'system','content':'system'},{'role':'user','content':content}]))
        self.assertEqual(p.last_usage_metadata,{'total_tokens':7});self.record.assert_not_called()
        self.response.read.assert_called_once_with();self.response.__exit__.assert_called_once_with(None,None,None)

    def test_provider_thinking_flags_and_default_budget(self):
        for name,extra in [('doubao',{'thinking':{'type':'disabled'}}),('qwen',{'enable_thinking':False}),('other',{})]:
            with self.subTest(name=name):
                self.settings['provider']=name;self.provider().generate_json('s',[])
                payload=json.loads(self.open.call_args.args[0].data)
                self.assertEqual(payload['max_tokens'],1400)
                self.assertEqual({k:v for k,v in payload.items() if k in ('thinking','enable_thinking')},extra)

    def test_configuration_failure_precedes_usage_reset(self):
        p=self.provider(True);p.last_usage_metadata={'prior':1};self.settings.update(configured=False,message='disabled')
        with self.assertRaises(self.api.AiProviderConfigError) as caught:p.generate_json('s',[])
        self.assertEqual(str(caught.exception),'disabled');self.open.assert_not_called()
        self.assertEqual(p.last_usage_metadata,{'prior':1});self.assertEqual(self.record.call_args.args[2:],(False,{'prior':1}))

    def test_bound_success_records_once_with_same_settings(self):
        p=self.provider(True);result=p.generate_json('s',[])
        self.assertEqual(result[0],{'answer':42});self.record.assert_called_once()
        args=self.record.call_args.args;self.assertIs(args[0],self.settings)
        self.assertGreaterEqual(args[1],0);self.assertEqual(args[2:],(True,{'total_tokens':7}))
        self.open.assert_called_once()

    def test_missing_bound_resolver_prevents_transport(self):
        p=self.provider(True)
        with patch.object(self.api,'model_profile_service',None),self.assertRaises(RuntimeError) as caught:p.generate_json('s',[])
        self.assertEqual(str(caught.exception),'Model profile resolver is not configured')
        self.open.assert_not_called();self.record.assert_not_called()

    def test_unbound_missing_resolver_remains_legacy(self):
        with patch.object(self.api,'model_profile_service',None):result=self.provider().generate_json('s',[])
        self.assertEqual(result[0],{'answer':42});self.open.assert_called_once();self.record.assert_not_called()

    def test_request_timeout_does_not_retry(self):
        for error in (TimeoutError('first'),socket.timeout('first'),urllib.error.URLError(socket.timeout('first'))):
            with self.subTest(error=error):
                self.open.reset_mock();self.open.side_effect=[error,self.response]
                with self.assertRaises(self.api.AiProviderTimeout) as caught:self.provider().generate_json('s',[])
                self.assertEqual(str(caught.exception),'AI provider timed out');self.assertIs(caught.exception.__cause__,error)
                self.open.assert_called_once()

    def test_http_classification_and_no_retry(self):
        for status,cls in [(401,self.api.AiProviderAuthError),(429,self.api.AiProviderOverloaded),(400,self.api.AiProviderConfigError),(500,self.api.AiProviderError),(418,self.api.AiProviderNonRetryableError)]:
            with self.subTest(status=status):
                self.open.reset_mock();err=urllib.error.HTTPError('https://fixture.invalid',status,'bad',{},io.BytesIO(b'detail'))
                self.open.side_effect=[err,self.response]
                with self.assertRaises(cls) as caught:self.provider().generate_json('s',[])
                self.assertIs(type(caught.exception),cls);self.assertEqual(caught.exception.http_status,status)
                self.assertIs(caught.exception.__cause__,err);self.open.assert_called_once()

    def test_url_error_uses_bounded_text_without_retry(self):
        error=urllib.error.URLError('bad destination');self.open.side_effect=[error,self.response]
        formatter=Mock(return_value='bounded')
        with patch.object(self.api,'bounded_text',formatter),self.assertRaises(self.api.AiProviderError) as caught:self.provider().generate_json('s',[])
        self.assertEqual(str(caught.exception),'AI provider request failed: bounded');formatter.assert_called_once_with(error,180)
        self.assertIs(caught.exception.__cause__,error);self.open.assert_called_once()

    def test_response_read_failure_keeps_exception_and_closes(self):
        err=OSError('read failed');self.response.read.side_effect=[err,b'{}']
        with self.assertRaises(OSError) as caught:self.provider(True).generate_json('s',[])
        self.assertIs(caught.exception,err);self.open.assert_called_once();self.response.read.assert_called_once()
        self.assertIs(self.response.__exit__.call_args.args[1],err)
        self.assertEqual(self.record.call_args.args[2:],(False,{}))

    def test_shape_failures_attach_response_evidence(self):
        for raw in (b'not json',b'{"choices":[]}',b'{"choices":[{}]}'):
            with self.subTest(raw=raw):
                self.response.read.side_effect=None;self.response.read.return_value=raw
                with self.assertRaises(self.api.AiProviderError) as caught:self.provider().generate_json('s',[])
                self.assertEqual(str(caught.exception),'AI provider response shape was not recognized')
                self.assertEqual(caught.exception.response_sha256,self.api.sha256_bytes(raw))
                self.assertEqual(caught.exception.response_preview,raw.decode())

    def test_non_object_json_preserves_attribute_error_boundary(self):
        self.body=[]
        with self.assertRaises(AttributeError):self.provider().generate_json('s',[])
        self.open.assert_called_once()

    def test_bound_incomplete_output_rejected_with_usage(self):
        for choices in ([dict(message={'content':'{}'},finish_reason='length')],self.body['choices']*2):
            with self.subTest(choices=choices):
                self.body['choices']=choices;self.record.reset_mock()
                with self.assertRaises(self.api.AiProviderError) as caught:self.provider(True).generate_json('s',[])
                self.assertEqual(str(caught.exception),'AI provider output is incomplete')
                self.assertFalse(hasattr(caught.exception,'response_sha256'))
                self.record.assert_called_once();self.assertEqual(self.record.call_args.args[2:],(False,{'total_tokens':7}))

    def test_unbound_incomplete_output_still_parses(self):
        self.body['choices'][0]['finish_reason']='length'
        self.assertEqual(self.provider().generate_json('s',[])[0],{'answer':42})

    def test_content_parts_join_and_usage_type_guard(self):
        self.body['choices'][0]['message']['content']=[{'text':'{"x":'},{'text':'1}'},'ignored']
        self.body['usage']=['not a dict'];p=self.provider()
        self.assertEqual(p.generate_json('s',[])[0],{'x':1});self.assertEqual(p.last_usage_metadata,{})

    def test_parse_error_preserves_identity_and_raw_text_evidence(self):
        err=self.api.AiProviderError('parse failed');parser=Mock(side_effect=err)
        raw='x'*9000;self.body['choices'][0]['message']['content']=raw
        with patch.object(self.api,'parse_ai_json_object',parser),self.assertRaises(self.api.AiProviderError) as caught:self.provider().generate_json('s',[])
        self.assertIs(caught.exception,err);parser.assert_called_once_with(raw)
        self.assertEqual(err.response_preview,raw[:8192]);self.assertEqual(err.response_sha256,self.api.sha256_bytes(raw.encode()))
        self.open.assert_called_once()

    def test_ledger_failure_does_not_repeat_paid_call(self):
        self.record.side_effect=RuntimeError('synthetic ledger failure')
        with self.assertLogs('local_inspection_service.model_profiles.audit',level='WARNING') as logs:result=self.provider(True).generate_json('s',[])
        self.assertEqual(result[0],{'answer':42});self.open.assert_called_once();self.record.assert_called_once()
        self.assertEqual(logs.output,['WARNING:local_inspection_service.model_profiles.audit:Model usage accounting unavailable'])

    def test_bound_error_redacts_synthetic_secret(self):
        self.body['choices'][0]['message']['content']='synthetic-key'
        with self.assertRaises(self.api.AiProviderError) as caught:self.provider(True).generate_json('s',[])
        self.assertEqual(caught.exception.response_preview,'[REDACTED]')
        self.open.assert_called_once();self.record.assert_called_once();self.assertFalse(self.record.call_args.args[2])

    def test_resolver_is_captured_before_transport_and_refreshed_next_call(self):
        second=Mock();p=self.provider(True)
        def open_response(*args,**kwargs):
            self.api.model_profile_service=SimpleNamespace(record_call=second)
            return self.response
        self.open.side_effect=open_response
        p.generate_json('s',[]);self.record.assert_called_once();second.assert_not_called()
        p.generate_json('s',[]);self.record.assert_called_once();second.assert_called_once();self.assertEqual(self.open.call_count,2)


    def test_independent_same_class_nested_calls_keep_accounting_separate(self):
        from local_inspection_service.model_providers.openai_transport import OpenAICompatibleAiProvider
        from local_inspection_service.model_providers.openai_ports import OpenAITransportIO, OpenAITransportErrors
        from local_inspection_service.model_providers.errors import AiProviderConfigError, AiProviderTimeout, AiProviderError
        errors=OpenAITransportErrors(lambda:AiProviderConfigError,lambda:AiProviderTimeout,lambda:AiProviderError)
        records=[Mock(),Mock()];events=[]
        def create(index,opener):
            settings={**self.settings,'profile_id':str(index)}
            io=OpenAITransportIO(lambda:opener,lambda:json.loads,lambda:lambda value,limit:str(value)[:limit],lambda:lambda value:'synthetic-digest',lambda:lambda prefix,error:AiProviderError(prefix))
            return OpenAICompatibleAiProvider(settings,io,errors,lambda:SimpleNamespace(record_call=records[index]))
        inner=create(1,lambda *args,**kwargs:self.response)
        def outer_open(*args,**kwargs):
            events.append('outer');self.assertEqual(inner.generate_json('inner',[])[0],{'answer':42});events.append('inner-complete')
            return self.response
        outer=create(0,outer_open)
        self.assertEqual(outer.generate_json('outer',[])[0],{'answer':42})
        self.assertEqual(events,['outer','inner-complete'])
        for p,record in zip((outer,inner),records):
            record.assert_called_once();self.assertIs(record.call_args.args[0],p.settings);self.assertEqual(record.call_args.args[2:],(True,{'total_tokens':7}))
        self.open.assert_not_called();self.record.assert_not_called()

    def test_independent_constructor_has_no_capability_reads(self):
        from local_inspection_service.model_providers.openai_transport import OpenAICompatibleAiProvider
        from local_inspection_service.model_providers.openai_ports import OpenAITransportIO, OpenAITransportErrors
        forbidden=Mock(side_effect=AssertionError('constructor capability read'))
        p=OpenAICompatibleAiProvider(self.settings,OpenAITransportIO(*([forbidden]*5)),OpenAITransportErrors(*([forbidden]*3)),forbidden)
        self.assertIs(p.settings,self.settings);self.assertEqual(p.last_usage_metadata,{});forbidden.assert_not_called()

    def test_independent_application_adapter_keeps_signature_and_resolver_capture(self):
        import inspect
        self.assertEqual(list(inspect.signature(self.api.OpenAICompatibleAiProvider).parameters),['settings'])
        self.assertEqual(list(inspect.signature(self.api.OpenAICompatibleAiProvider.generate_json).parameters),['self','system_prompt','user_content','max_tokens'])
        wrong=Mock(side_effect=AssertionError('resolver selected after composition'))
        with patch.object(self.api,'resolve_model_profiles',wrong):
            self.assertEqual(self.provider(True).generate_json('s',[])[0],{'answer':42})
        wrong.assert_not_called();self.record.assert_called_once()

    def test_capability_failures_do_not_retry(self):
        cases=('ai_urlopen','parse_ai_json_object','provider_http_error','bounded_text','sha256_bytes')
        for name in cases:
            with self.subTest(name=name):
                failure=RuntimeError('synthetic capability failure');hits=[]
                original=getattr(self.api,name)
                def recover(*args,**kwargs):
                    hits.append(1)
                    if len(hits)==1:raise failure
                    return original(*args,**kwargs)
                self.open.reset_mock();self.open.side_effect=None
                self.body=dict(choices=[dict(message=dict(content='{"answer":42}'),finish_reason='stop')],usage={})
                if name=='provider_http_error':self.open.side_effect=urllib.error.HTTPError('https://fixture.invalid',500,'bad',{},io.BytesIO(b'detail'))
                if name=='bounded_text':self.open.side_effect=urllib.error.URLError('bad destination')
                if name=='sha256_bytes':self.body={'choices':[]}
                with patch.object(self.api,name,recover),self.assertRaises(RuntimeError) as caught:self.provider().generate_json('s',[])
                self.assertIs(caught.exception,failure);self.assertEqual(hits,[1])
                if name!='ai_urlopen':self.open.assert_called_once()

    def test_transport_callee_capture_precedes_timeout_conversion(self):
        events=[];first=Mock(return_value=self.response);second=Mock(return_value=self.response)
        class Timeout:
            def __float__(value):
                events.append('timeout');self.api.ai_urlopen=second;return 1.0
        self.settings['timeout_seconds']=Timeout()
        with patch.object(self.api,'ai_urlopen',first):self.provider().generate_json('s',[])
        self.assertEqual(events,['timeout']);first.assert_called_once();second.assert_not_called()

    def test_response_enter_failure_does_not_exit_or_retry(self):
        err=ValueError('synthetic enter failure');self.response.__enter__.side_effect=[err,self.response]
        with self.assertRaises(ValueError) as caught:self.provider(True).generate_json('s',[])
        self.assertIs(caught.exception,err);self.open.assert_called_once();self.response.__enter__.assert_called_once()
        self.response.read.assert_not_called();self.response.__exit__.assert_not_called()
        self.assertEqual(self.record.call_args.args[2:],(False,{}))

    def test_response_exit_failure_remains_primary_without_retry(self):
        err=ValueError('synthetic exit failure');self.response.__exit__.side_effect=[err,False]
        with self.assertRaises(ValueError) as caught:self.provider(True).generate_json('s',[])
        self.assertIs(caught.exception,err);self.open.assert_called_once();self.response.read.assert_called_once()
        self.response.__exit__.assert_called_once_with(None,None,None)
        self.assertEqual(self.record.call_args.args[2:],(False,{}))

    def test_response_suppression_keeps_original_unbound_body_failure(self):
        err=ValueError('synthetic read failure');self.response.read.side_effect=err;self.response.__exit__.return_value=True
        with self.assertRaises(UnboundLocalError):self.provider(True).generate_json('s',[])
        self.open.assert_called_once();self.response.read.assert_called_once()
        self.assertIs(self.response.__exit__.call_args.args[1],err)
        self.assertEqual(self.record.call_args.args[2:],(False,{}))

    def test_original_dependency_capture_windows(self):
        for site in ('config','open','url_error','shape_digest','parse_digest'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(site=site,mode=mode):capture_openai_window(self.api,type(self),site,mode)

    def test_original_dynamic_exception_matching(self):
        for mode in ('same','changed','missing'):
            with self.subTest(mode=mode):capture_openai_match(self.api,type(self),mode)

    def test_original_resource_first_failure_recovery(self):
        for site in ('enter','read','exit','suppress'):
            with self.subTest(site=site):capture_openai_resources(self.api,type(self),site)

    def test_original_composition_resolver_binding(self):
        capture_openai_resolver_binding(self.api,type(self))

if __name__=='__main__':unittest.main()

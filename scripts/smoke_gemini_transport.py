"""Synthetic Gemini behavior baseline; no real provider or media requests."""
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

sys.path.insert(0,str(Path.cwd()))


def capture_gemini_window(api, Fixture, site, mode='ordinary'):
    import io, json, time, urllib.error
    from contextlib import ExitStack
    from unittest.mock import patch
    f=Fixture();f.setUp();events=[];code_reads=[]
    try:
        with patch.dict(api.__dict__), ExitStack() as stack:
            original_error=api.AiProviderError;original_config=api.AiProviderConfigError
            method=site.split(':',1)[0] if ':' in site else 'image'
            if method not in ('cache','json','image'):method='image'
            f.body={'name':'cachedContents/synthetic'} if method=='cache' else {'candidates':[{'content':{'parts':[{'text':'{"answer":42}'}] if method=='json' else [{'inlineData':{'data':'eA=='}}]},'finishReason':'STOP'}],'usageMetadata':{}}
            api.decode_b64_image=lambda value:b'image'
            user_content=[];direct_parts=False
            def install(name, result):
                def maker(label):
                    def call(*a,**kw):events.append(label);return result(*a,**kw)
                    return call
                callbacks=[maker(label) for label in 'ABC'];setattr(api,name,callbacks[0])
                def prior():
                    events.append('prior');setattr(api,name,callbacks[1] if mode=='prior' else None if mode=='missing' else callbacks[0])
                def argument():events.append('argument');setattr(api,name,callbacks[2])
                return prior,argument
            if site=='data_url':
                direct_parts=True;prior,argument=install('data_url_payload',lambda value:('image/png','eA=='))
                class URL(dict):
                    def get(self,key,*args):
                        if key=='url':argument()
                        return super().get(key,*args)
                class Item(dict):
                    reads=0
                    def get(self,key,*args):
                        if key=='image_url':
                            self.reads+=1
                            if self.reads==2:prior()
                        return super().get(key,*args)
                user_content=[Item(type='image_url',image_url=URL(url='data:image/png;base64,eA=='))]
            elif site=='decode':
                prior,argument=install('decode_b64_image',lambda value:b'image')
                class Inline(dict):
                    def get(self,key,*args):
                        if key=='data':argument()
                        return super().get(key,*args)
                class Part(dict):
                    reads=0
                    def get(self,key,*args):
                        if key=='inlineData':
                            self.reads+=1
                            if self.reads==2:prior()
                        return super().get(key,*args)
                f.body['candidates'][0]['content']['parts']=[Part(inlineData=Inline(data='eA=='))]
                stack.enter_context(patch.object(json,'loads',lambda *a,**k:f.body))
            elif site=='mask':
                prior,argument=install('masked_url_for_status',lambda value:'masked')
                class Settings(dict):
                    reads=0
                    def get(self,key,*args):
                        if key=='proxy_source_name':prior()
                        if key=='proxy_url_raw':
                            self.reads+=1
                            if self.reads==2:argument()
                        return super().get(key,*args)
                f.settings=Settings(f.settings,proxy_url_raw='synthetic-proxy')
            elif site.endswith(':open'):
                original=f.open;prior,argument=install('ai_urlopen',lambda *a,**kw:original(*a,**kw));ticks=[]
                def clock():
                    ticks.append(1)
                    if len(ticks)==(1 if method=='cache' else 2):prior()
                    return float(len(ticks))
                class Timeout:
                    def __float__(self):argument();return 12.5
                f.settings['timeout_seconds']=Timeout();stack.enter_context(patch.object(time,'monotonic',clock))
            elif site.endswith(':config'):
                prior,argument=install('AiProviderConfigError',original_config)
                class Settings(dict):
                    def get(self,key,*args):
                        if key=='configured':prior();return False
                        if key=='message':argument()
                        return super().get(key,*args)
                f.settings=Settings(f.settings,message='disabled')
            elif site in ('cache:url_error','json:url_error','image:url_proxy','image:url_direct'):
                prior,argument=install('AiProviderError',original_error)
                class URLFailure(urllib.error.URLError):
                    reads=0
                    def __getattribute__(self,key):
                        if key=='reason' and method!='image':
                            count=object.__getattribute__(self,'reads')+1;object.__setattr__(self,'reads',count)
                            if count==1:prior()
                        return super().__getattribute__(key)
                failure=URLFailure('synthetic');f.open.side_effect=failure
                if method=='image':
                    class Settings(dict):
                        def get(self,key,*args):
                            if key==('proxy_source_name' if site.endswith('proxy') else 'proxy_url'):prior()
                            return super().get(key,*args)
                    f.settings=Settings(f.settings,proxy_url_raw='synthetic-proxy' if site.endswith('proxy') else '',proxy_source_name='synthetic')
                original_formatter=api.bounded_text
                def formatter(value,limit):
                    if limit==180:argument();return 'bounded'
                    return original_formatter(value,limit)
                api.bounded_text=formatter
            elif site=='cache:http_error' or site.startswith('image:http_'):
                table={'cache:http_error':('AiProviderError',401,0,1),'image:http_auth':('AiProviderAuthError',401,3,4),'image:http_config':('AiProviderConfigError',404,5,6),'image:http_error':('AiProviderError',500,5,6),'image:http_overloaded':('AiProviderOverloaded',429,4,5)}
                name,status,prior_index,argument_index=table[site];expected_class=getattr(api,name);prior,argument=install(name,expected_class)
                class HTTPFailure(urllib.error.HTTPError):
                    armed=False
                    def __getattribute__(self,key):
                        if key=='code' and object.__getattribute__(self,'armed'):
                            code_reads.append(1)
                            if len(code_reads)==prior_index:prior()
                            if len(code_reads)==argument_index:argument()
                        return super().__getattribute__(key)
                    def read(self,*a,**kw):
                        if prior_index==0:prior()
                        return b'detail'
                failure=HTTPFailure('https://fixture.invalid',status,'synthetic',{},io.BytesIO(b'detail'));failure.armed=True;f.open.side_effect=failure
            else:raise AssertionError(site)
            p=f.provider();caught=None;result=None
            try:
                if direct_parts:result=p.content_parts(user_content)
                elif method=='cache':result=p.create_cached_content('system',[],display_name='synthetic')
                elif method=='json':result=p.generate_json('system',[])
                else:result=p.generate_image('prompt',[],model='synthetic-image')
            except BaseException as exc:caught=exc
            assert 'prior' in events and 'argument' in events,(site,mode,caught,events)
            assert events.index('prior')<events.index('argument'),events
            labels=[event for event in events if event in ('A','B','C')]
            if mode=='missing':
                assert type(caught) is TypeError,(site,mode,caught,events)
                assert labels==[],events
            else:
                assert labels==['B' if mode=='prior' else 'A'],(site,mode,caught,events)
                if site in ('data_url','decode','mask') or site.endswith(':open'):
                    assert caught is None,(site,mode,caught,events)
                    if site=='data_url':assert result==[{'inlineData':{'mimeType':'image/png','data':'eA=='}}]
                    elif method=='json':assert result[0]=={'answer':42}
                    elif method=='cache':assert result['name']=='cachedContents/synthetic'
                    else:assert result['bytes']==b'image'
                    if site=='mask':assert result['proxy_url']=='masked'
                else:
                    assert isinstance(caught,original_error),(site,mode,caught,events)
                    if ':http_' in site:assert type(caught) is expected_class and caught.__cause__ is failure
                    elif ':url_' in site:assert type(caught) is original_error and caught.__cause__ is failure
                    else:assert type(caught) is original_config
            return {'events':events,'error':type(caught).__name__ if caught else None,'open_calls':f.open.call_count,'code_reads':len(code_reads),'raw_text':p.last_raw_text,'usage':p.last_usage_metadata}
    finally:f.doCleanups()


def capture_gemini_refresh(api, Fixture, site):
    import io,json,urllib.error
    from unittest.mock import patch
    f=Fixture();f.setUp();events=[]
    try:
        with patch.dict(api.__dict__):
            caught=None;result=None
            if site=='data_url':
                def second(value):events.append(('B',value));return 'image/png','two'
                def first(value):events.append(('A',value));api.data_url_payload=second;return 'image/png','one'
                api.data_url_payload=first
                try:result=f.provider().content_parts([{'type':'image_url','image_url':{'url':'one'}},{'type':'image_url','image_url':{'url':'two'}}])
                except BaseException as exc:caught=exc
                assert caught is None,caught
                assert events==[('A','one'),('B','two')],events
                assert result==[{'inlineData':{'mimeType':'image/png','data':'one'}},{'inlineData':{'mimeType':'image/png','data':'two'}}]
            elif site=='decode':
                def second(value):events.append(('B',value));return b'image'
                def first(value):events.append(('A',value));api.decode_b64_image=second;return b''
                api.decode_b64_image=first;f.body['candidates'][0]['content']['parts']=[{'inlineData':{'data':'one'}},{'inlineData':{'data':'two'}}]
                try:result=f.provider().generate_image('prompt',[],model='synthetic')
                except BaseException as exc:caught=exc
                assert caught is None,caught
                assert events==[('A','one'),('B','two')],events
                assert result['bytes']==b'image'
            elif site=='formatter':
                def second(value,limit):events.append(('B',value,limit));return 'second'
                def first(value,limit):events.append(('A',value,limit));api.bounded_text=second;return 'first'
                api.bounded_text=first;failure=urllib.error.HTTPError('https://fixture.invalid',429,'synthetic',{},io.BytesIO(b'detail'));f.open.side_effect=failure
                try:f.provider().generate_image('prompt',[],model='synthetic')
                except BaseException as exc:caught=exc
                assert type(caught) is api.AiProviderOverloaded and caught.__cause__ is failure,caught
                assert str(caught)=='Gemini image provider overloaded: HTTP 429 second',caught
                assert events==[('A','detail',180),('B','detail',180)],events
            else:raise AssertionError(site)
            return {'events':events,'error':type(caught).__name__ if caught else None,'open_calls':f.open.call_count}
    finally:f.doCleanups()


class GeminiTransportContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env=patch.dict(os.environ);cls.env.start()
        cls.tmp=tempfile.TemporaryDirectory(prefix='gemini-transport-')
        root=Path(cls.tmp.name);(root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup();cls.env.stop()

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for name in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):
            self.stack.enter_context(patch(name,side_effect=AssertionError('external operation forbidden')))
        self.settings=dict(configured=True,model='gemini-3-synthetic',base_url='https://fixture.invalid/v1/',
                           api_key='synthetic-key',timeout_seconds='12.5')
        self.record=Mock();self.stack.enter_context(patch.object(self.api,'model_profile_service',SimpleNamespace(record_call=self.record)))
        self.open=self.stack.enter_context(patch.object(self.api,'ai_urlopen'))
        self.body={'candidates':[{'content':{'parts':[{'text':'{"answer":42}'}]},'finishReason':'STOP'}],'usageMetadata':{'totalTokenCount':7}}
        self.response=Mock();self.response.__enter__=Mock(return_value=self.response);self.response.__exit__=Mock(return_value=False)
        self.response.read=Mock(side_effect=lambda:json.dumps(self.body).encode());self.open.return_value=self.response

    def provider(self,bound=False):
        if bound:self.settings['profile_id']='synthetic-profile'
        return self.api.GeminiAiProvider(self.settings)

    def test_constructor_and_content_parts(self):
        p=self.provider();self.assertIs(p.settings,self.settings);self.assertEqual(p.last_usage_metadata,{});self.assertEqual(p.last_raw_text,'')
        parts=p.content_parts([{'type':'text','text':0},{'type':'image_url','image_url':{'url':'data:image/png;base64,eA=='}},{'type':'unknown'}])
        self.assertEqual(parts,[{'text':''},{'inlineData':{'mimeType':'image/png','data':'eA=='}}]);self.open.assert_not_called()

    def test_json_request_and_usage(self):
        p=self.provider(True)
        with patch.object(self.api.time,'monotonic',side_effect=[10,11,11.25,12]):result=p.generate_json('system',[{'type':'text','text':'user'}],max_tokens=71)
        self.assertEqual(result,({'answer':42},250));request,settings=self.open.call_args.args
        self.assertIs(settings,self.settings);self.assertEqual(request.full_url,'https://fixture.invalid/v1/models/gemini-3-synthetic:generateContent')
        self.assertEqual(request.method,'POST');self.assertEqual(self.open.call_args.kwargs,{'timeout':12.5})
        self.assertEqual(dict(request.header_items()),{'Content-type':'application/json','X-goog-api-key':'synthetic-key'})
        self.assertEqual(json.loads(request.data),{'contents':[{'role':'user','parts':[{'text':'user'}]}],'systemInstruction':{'parts':[{'text':'system'}]},'generationConfig':{'temperature':0,'maxOutputTokens':71,'responseMimeType':'application/json','thinkingConfig':{'thinkingLevel':'minimal'}}})
        self.assertEqual(p.last_raw_text,'{"answer":42}');self.assertEqual(p.last_usage_metadata,{'totalTokenCount':7})
        self.record.assert_called_once();self.assertIs(self.record.call_args.args[0],self.settings);self.assertEqual(self.record.call_args.args[1:],(2000,True,{'totalTokenCount':7}))

    def test_json_cache_reference_and_model_thinking_policy(self):
        for model,thinking in [('gemini-2.5-flash-x',{'thinkingBudget':0}),('gemini-flash-lite-x',{'thinkingBudget':0}),('gemini-2.5-pro-x',{'thinkingBudget':128}),('gemini-3-x',{'thinkingLevel':'minimal'}),('other',None)]:
            with self.subTest(model=model):
                self.settings['model']=model;self.provider().generate_json('ignored',[],cached_content='cachedContents/synthetic')
                payload=json.loads(self.open.call_args.args[0].data)
                self.assertEqual(payload['cachedContent'],'cachedContents/synthetic');self.assertNotIn('systemInstruction',payload)
                self.assertEqual(payload['generationConfig']['maxOutputTokens'],1400)
                self.assertEqual(payload['generationConfig'].get('thinkingConfig'),thinking)

    def test_configuration_failure_keeps_previous_state(self):
        for method in ('json','cache','image'):
            with self.subTest(method=method):
                p=self.provider();p.last_usage_metadata={'prior':1};p.last_raw_text='prior';self.settings.update(configured=False,message='disabled')
                with self.assertRaises(self.api.AiProviderConfigError) as caught:self.invoke(p,method)
                self.assertEqual(str(caught.exception),'disabled');self.assertEqual(p.last_usage_metadata,{'prior':1});self.assertEqual(p.last_raw_text,'prior')
        self.open.assert_not_called()

    def invoke(self,p,method):
        if method=='json':return p.generate_json('system',[])
        if method=='cache':return p.create_cached_content('system',[],display_name='synthetic')
        return p.generate_image('prompt',[],model='synthetic-image')

    def test_timeout_paths_never_repeat_requests(self):
        for method,prefix in [('json','AI provider'),('cache','AI cache provider'),('image','Gemini image provider')]:
            for error in (TimeoutError('first'),urllib.error.URLError(socket.timeout('first'))):
                with self.subTest(method=method,error=error):
                    self.open.reset_mock();self.open.side_effect=[error,self.response]
                    with self.assertRaises(self.api.AiProviderTimeout) as caught:self.invoke(self.provider(),method)
                    self.assertEqual(str(caught.exception),prefix+' timed out');self.assertIs(caught.exception.__cause__,error);self.open.assert_called_once()

    def test_json_strict_bound_finish_reason_and_legacy_compatibility(self):
        self.body['candidates'][0]['finishReason']='MAX_TOKENS'
        with self.assertRaises(self.api.AiProviderError) as caught:self.provider(True).generate_json('s',[])
        self.assertEqual(str(caught.exception),'AI provider output is incomplete');self.assertEqual(self.record.call_args.args[2:],(False,{'totalTokenCount':7}))
        self.settings.pop('profile_id');self.assertEqual(self.provider().generate_json('s',[])[0],{'answer':42})

    def test_cache_payload_ttl_result_and_no_direct_accounting(self):
        self.body={'name':'cachedContents/synthetic','usageMetadata':{'tokens':3},'expireTime':'synthetic-time'}
        p=self.provider(True);p.last_usage_metadata={'prior':1};p.last_raw_text='prior'
        with patch.object(self.api.time,'monotonic',side_effect=[10,10.5]):result=p.create_cached_content('system',[{'type':'text','text':'user'}],display_name='name',ttl_seconds=2)
        request=self.open.call_args.args[0];self.assertEqual(request.full_url,'https://fixture.invalid/v1/cachedContents')
        self.assertEqual(json.loads(request.data),{'model':'models/gemini-3-synthetic','displayName':'name','systemInstruction':{'parts':[{'text':'system'}]},'contents':[{'role':'user','parts':[{'text':'user'}]}],'ttl':'300s'})
        self.assertEqual(result,{'name':'cachedContents/synthetic','model':'gemini-3-synthetic','latency_ms':500,'usage_metadata':{'tokens':3},'expire_time':'synthetic-time'})
        self.assertEqual(p.last_usage_metadata,{'prior':1});self.assertEqual(p.last_raw_text,'prior');self.record.assert_not_called()

    def test_cache_response_validation(self):
        for body in ({},[],{'name':''}):
            with self.subTest(body=body):
                self.body=body
                with self.assertRaises(self.api.AiProviderError) as caught:self.invoke(self.provider(),'cache')
                self.assertEqual(str(caught.exception),'AI cache response did not include a cache name')

    def test_cache_http_error_retains_legacy_classification(self):
        error=urllib.error.HTTPError('https://fixture.invalid',401,'bad',{},io.BytesIO(b'detail'));self.open.side_effect=[error,self.response]
        with self.assertRaises(self.api.AiProviderError) as caught:self.invoke(self.provider(),'cache')
        self.assertIs(type(caught.exception),self.api.AiProviderError);self.assertEqual(str(caught.exception),'AI cache create failed: HTTP 401 detail')
        self.assertIsNone(caught.exception.http_status);self.open.assert_called_once();self.record.assert_not_called()

    def test_image_returns_first_decoded_image_and_preceding_text(self):
        self.body['candidates'][0]['content']['parts']=[{'text':'first'},'ignored',{'inline_data':{'data':'eA==','mime_type':'image/custom'}},{'text':'later'}]
        p=self.provider(True)
        with patch.object(self.api,'decode_b64_image',return_value=b'synthetic-image') as decode,patch.object(self.api,'masked_url_for_status',return_value='masked') as mask:
            result=p.generate_image('prompt',[{'type':'text','text':'user'}],model='override-model',system_prompt='system')
        self.assertEqual(result['bytes'],b'synthetic-image');self.assertEqual(result['mime_type'],'image/custom')
        self.assertEqual(result['text'],'first');self.assertEqual(p.last_raw_text,'first');self.assertEqual(result['model'],'override-model')
        self.assertIs(result['usage_metadata'],p.last_usage_metadata);self.assertFalse(result['proxy_used']);self.assertFalse(result['proxy_auto_local'])
        self.assertEqual(result['proxy_source_name'],'');self.assertEqual(result['proxy_url'],'masked');mask.assert_called_once_with('');decode.assert_called_once_with('eA==')
        payload=json.loads(self.open.call_args.args[0].data)
        self.assertEqual(payload,{'contents':[{'role':'user','parts':[{'text':'prompt'},{'text':'user'}]}],'systemInstruction':{'parts':[{'text':'system'}]}})
        self.record.assert_called_once();self.assertEqual(self.record.call_args.args[2:],(True,{'totalTokenCount':7}))

    def test_image_missing_model_fails_after_state_reset(self):
        p=self.provider();p.last_usage_metadata={'old':1};p.last_raw_text='old';self.settings['model']=' '
        with self.assertRaises(self.api.AiProviderConfigError) as caught:p.generate_image('p',[],model='')
        self.assertEqual(str(caught.exception),'Gemini image model is not configured');self.assertEqual(p.last_usage_metadata,{});self.assertEqual(p.last_raw_text,'');self.open.assert_not_called()

    def test_image_missing_inline_preserves_accumulated_text(self):
        p=self.provider(True);self.body['candidates'][0]['content']['parts']=[{'text':'one'},{'text':'two'},{'inlineData':{'data':''}}]
        with patch.object(self.api,'decode_b64_image',return_value=b''),self.assertRaises(self.api.AiProviderError) as caught:p.generate_image('p',[],model='m')
        self.assertEqual(str(caught.exception),'Gemini image provider did not return inline image data');self.assertEqual(p.last_raw_text,'one\ntwo')
        self.assertEqual(self.record.call_args.args[2:],(False,{'totalTokenCount':7}))

    def test_image_http_status_and_region_errors(self):
        cases=[(401,b'detail',self.api.AiProviderAuthError),(403,b'detail',self.api.AiProviderAuthError),(429,b'detail',self.api.AiProviderOverloaded),(503,b'detail',self.api.AiProviderOverloaded),(400,b'detail',self.api.AiProviderConfigError),(404,b'detail',self.api.AiProviderConfigError),(500,b'detail',self.api.AiProviderError)]
        for status,body,cls in cases:
            with self.subTest(status=status):
                self.open.reset_mock();error=urllib.error.HTTPError('https://fixture.invalid',status,'bad',{},io.BytesIO(body));self.open.side_effect=[error,self.response]
                with self.assertRaises(cls) as caught:self.invoke(self.provider(),'image')
                self.assertIs(type(caught.exception),cls);self.assertEqual(caught.exception.http_status,status);self.assertIs(caught.exception.__cause__,error);self.open.assert_called_once()
        for proxy,expected in [('', 'region-blocked on direct egress'),('synthetic-proxy','still region-blocked while using proxy source synthetic')]:
            self.settings.update(proxy_url_raw=proxy,proxy_source_name='synthetic')
            self.open.side_effect=urllib.error.HTTPError('https://fixture.invalid',400,'bad',{},io.BytesIO(b'User location is not supported'))
            with self.assertRaises(self.api.AiProviderConfigError) as caught:self.invoke(self.provider(),'image')
            self.assertIn(expected,str(caught.exception));self.assertIsNone(caught.exception.http_status)

    def test_bound_json_and_image_missing_resolver_fail_before_request(self):
        for method in ('json','image'):
            with self.subTest(method=method),patch.object(self.api,'model_profile_service',None),self.assertRaises(RuntimeError) as caught:self.invoke(self.provider(True),method)
            self.assertEqual(str(caught.exception),'Model profile resolver is not configured')
        self.open.assert_not_called();self.record.assert_not_called()

    def test_resource_read_failure_is_not_retried(self):
        for method in ('json','cache','image'):
            with self.subTest(method=method):
                error=ValueError('synthetic read error');self.response.read.reset_mock();self.response.read.side_effect=[error,b'{}'];self.open.reset_mock()
                with self.assertRaises(ValueError) as caught:self.invoke(self.provider(),method)
                self.assertIs(caught.exception,error);self.open.assert_called_once();self.response.read.assert_called_once()
                self.assertIs(self.response.__exit__.call_args.args[1],error)


    def test_cache_default_ttl_remains_captured_at_class_definition(self):
        import inspect
        p=self.provider();ttl=inspect.signature(p.create_cached_content).parameters['ttl_seconds'].default
        self.body={'name':'cachedContents/synthetic'}
        with patch.object(self.api,'AI_PROFILE_CACHE_TTL_SECONDS',ttl+100):
            p.create_cached_content('s',[],display_name='name')
        self.assertEqual(json.loads(self.open.call_args.args[0].data)['ttl'],str(max(300,int(ttl)))+'s')

    def test_json_raw_text_is_set_before_parser_failure(self):
        error=self.api.AiProviderError('synthetic parse failure');parser=Mock(side_effect=error);p=self.provider(True)
        with patch.object(self.api,'parse_ai_json_object',parser),self.assertRaises(self.api.AiProviderError) as caught:p.generate_json('s',[])
        self.assertIs(caught.exception,error);self.assertEqual(p.last_raw_text,'{"answer":42}');parser.assert_called_once_with(p.last_raw_text)
        self.open.assert_called_once();self.record.assert_called_once();self.assertEqual(self.record.call_args.args[2:],(False,{'totalTokenCount':7}))

    def test_image_decoder_failure_is_not_retried(self):
        self.body['candidates'][0]['content']['parts']=[{'inlineData':{'data':'eA=='}}]
        error=ValueError('synthetic decoder failure');hits=[]
        def decode(value):
            hits.append(value)
            if len(hits)==1:raise error
            return b'image'
        p=self.provider(True)
        with patch.object(self.api,'decode_b64_image',decode),self.assertRaises(ValueError) as caught:p.generate_image('p',[],model='m')
        self.assertIs(caught.exception,error);self.assertEqual(hits,['eA==']);self.open.assert_called_once()
        self.assertEqual(p.last_raw_text,'');self.assertEqual(self.record.call_args.args[2:],(False,{'totalTokenCount':7}))

    def test_image_proxy_metadata_and_text_precedence(self):
        self.settings.update(proxy_url_raw='synthetic-proxy',proxy_url='ignored',proxy_source_name='synthetic',proxy_auto_local=True)
        self.body['candidates'][0]['content']['parts']=[{'text':'text-first','inlineData':{'data':'ignored'}},{'inlineData':{'data':'eA=='}}]
        p=self.provider(True)
        with patch.object(self.api,'decode_b64_image',return_value=b'image') as decode,patch.object(self.api,'masked_url_for_status',return_value='masked') as mask:
            result=p.generate_image('p',[],model='m')
        decode.assert_called_once_with('eA==');mask.assert_called_once_with('synthetic-proxy')
        self.assertEqual((result['text'],result['proxy_used'],result['proxy_source_name'],result['proxy_url'],result['proxy_auto_local']),('text-first',True,'synthetic','masked',True))

    def valid_body(self,method):
        if method=='cache':return {'name':'cachedContents/synthetic','usageMetadata':{'tokens':3}}
        parts=[{'text':'{"answer":42}'}] if method=='json' else [{'inlineData':{'data':'eA=='}}]
        return {'candidates':[{'content':{'parts':parts},'finishReason':'STOP'}],'usageMetadata':{'tokens':3}}

    def test_resource_first_failure_has_infinite_valid_recovery(self):
        for method in ('json','cache','image'):
            for boundary in ('open','enter','read','exit','suppressed'):
                with self.subTest(method=method,boundary=boundary):
                    f=type(self)();f.setUp()
                    try:
                        f.body=f.valid_body(method);failure=RuntimeError('synthetic resource first failure');hits=[]
                        def recover(*args,**kwargs):
                            hits.append(1)
                            if len(hits)==1:raise failure
                            if boundary=='open' or boundary=='enter':return f.response
                            if boundary=='exit':return False
                            return json.dumps(f.body).encode()
                        target={'open':f.open,'enter':f.response.__enter__,'read':f.response.read,'exit':f.response.__exit__,'suppressed':f.response.read}[boundary]
                        target.side_effect=recover
                        if boundary=='suppressed':f.response.__exit__.return_value=True
                        caught=None
                        with patch.object(f.api,'decode_b64_image',return_value=b'image'):
                            try:f.invoke(f.provider(True),method)
                            except BaseException as exc:caught=exc
                        if boundary=='suppressed':self.assertIs(type(caught),UnboundLocalError)
                        else:self.assertIs(caught,failure)
                        self.assertEqual(hits,[1]);f.open.assert_called_once()
                        self.assertEqual(f.response.__enter__.call_count,0 if boundary=='open' else 1)
                        self.assertEqual(f.response.__exit__.call_count,0 if boundary in ('open','enter') else 1)
                        self.assertEqual(f.record.call_count,0 if method=='cache' else 1)
                        if method!='cache':self.assertEqual(f.record.call_args.args[2:],(False,{}))
                    finally:f.doCleanups()

    def test_request_first_failure_has_infinite_valid_recovery(self):
        for method in ('json','cache','image'):
            for kind in ('timeout','http','url'):
                with self.subTest(method=method,kind=kind):
                    f=type(self)();f.setUp()
                    try:
                        f.body=f.valid_body(method);hits=[]
                        failure=TimeoutError('synthetic') if kind=='timeout' else urllib.error.URLError('synthetic') if kind=='url' else urllib.error.HTTPError('https://fixture.invalid',503,'bad',{},io.BytesIO(b'detail'))
                        def recover(*args,**kwargs):
                            hits.append(1)
                            if len(hits)==1:raise failure
                            return f.response
                        f.open.side_effect=recover;caught=None
                        with patch.object(f.api,'decode_b64_image',return_value=b'image'):
                            try:f.invoke(f.provider(True),method)
                            except BaseException as exc:caught=exc
                        expected=f.api.AiProviderTimeout if kind=='timeout' else f.api.AiProviderOverloaded if kind=='http' and method!='cache' else f.api.AiProviderError
                        self.assertIs(type(caught),expected);self.assertEqual(hits,[1]);f.open.assert_called_once()
                        f.response.__enter__.assert_not_called();self.assertEqual(f.record.call_count,0 if method=='cache' else 1)
                        if method!='cache':self.assertEqual(f.record.call_args.args[2:],(False,{}))
                    finally:f.doCleanups()

    def test_http_error_body_first_failure_is_not_retried(self):
        for method in ('json','cache','image'):
            with self.subTest(method=method):
                f=type(self)();f.setUp()
                try:
                    error=urllib.error.HTTPError('https://fixture.invalid',500,'bad',{},None)
                    failure=OSError('synthetic error-body read failure');hits=[]
                    def read():
                        hits.append(1)
                        if len(hits)==1:raise failure
                        return b'valid error detail'
                    error.read=read;f.open.side_effect=error;p=f.provider(True)
                    p.last_usage_metadata={'prior':1};p.last_raw_text='prior';caught=None
                    try:f.invoke(p,method)
                    except BaseException as exc:caught=exc
                    self.assertIs(caught,failure);self.assertIs(caught.__context__,error);self.assertEqual(hits,[1]);f.open.assert_called_once()
                    self.assertEqual(f.record.call_count,0 if method=='cache' else 1)
                    self.assertEqual(p.last_usage_metadata,{'prior':1} if method=='cache' else {})
                    self.assertEqual(p.last_raw_text,'prior' if method=='cache' else '')
                finally:f.doCleanups()

    def test_resolver_function_binding_and_service_refresh(self):
        first=self.record;second=Mock();p=self.provider(True)
        original=self.open.side_effect
        def open_response(*args,**kwargs):
            self.api.model_profile_service=SimpleNamespace(record_call=second)
            return self.response
        self.open.side_effect=open_response
        with patch.object(self.api,'resolve_model_profiles',side_effect=AssertionError('late resolver function lookup')):
            p.generate_json('s',[]);first.assert_called_once();second.assert_not_called()
            p.generate_json('s',[]);first.assert_called_once();second.assert_called_once()
        self.assertEqual(self.open.call_count,2)

    def independent_provider(self,settings,opener,record):
        from local_inspection_service.model_providers.gemini_transport import GeminiAiProvider
        from local_inspection_service.model_providers.gemini_ports import GeminiTransportIO,GeminiTransportErrors
        from local_inspection_service.model_providers.errors import AiProviderConfigError,AiProviderTimeout,AiProviderError,AiProviderAuthError,AiProviderOverloaded
        from urllib.parse import quote
        io=GeminiTransportIO(lambda:opener,lambda:json.loads,lambda:lambda value,limit:str(value)[:limit],lambda:lambda value:('image/png','eA=='),lambda:lambda value:b'image',lambda:lambda value:'masked',lambda:quote,lambda:lambda prefix,error:AiProviderError(prefix))
        errors=GeminiTransportErrors(lambda:AiProviderConfigError,lambda:AiProviderTimeout,lambda:AiProviderError,lambda:AiProviderAuthError,lambda:AiProviderOverloaded)
        return GeminiAiProvider(settings,io,errors,lambda:SimpleNamespace(record_call=record))

    def test_independent_core_cache_requires_explicit_ttl_and_does_not_account(self):
        import inspect
        record=Mock();settings={**self.settings,'profile_id':'bound'};p=self.independent_provider(settings,self.open,record)
        self.assertIs(inspect.signature(p.create_cached_content).parameters['ttl_seconds'].default,inspect.Parameter.empty)
        self.body={'name':'cachedContents/synthetic'}
        p.create_cached_content('s',[],display_name='name',ttl_seconds=721)
        self.assertEqual(json.loads(self.open.call_args.args[0].data)['ttl'],'721s');record.assert_not_called()

    def test_independent_instances_keep_resolvers_and_state_separate(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier=Barrier(2);instances=[];records=[]
        for index in range(2):
            record=Mock();records.append(record)
            response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
            response.read=Mock(return_value=json.dumps({'candidates':[{'content':{'parts':[{'text':json.dumps({'instance':index})}]},'finishReason':'STOP'}],'usageMetadata':{'instance':index}}).encode())
            def opener(*args,response=response,**kwargs):barrier.wait(timeout=5);return response
            instances.append(self.independent_provider({**self.settings,'profile_id':str(index)},opener,record))
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(p.generate_json,'s',[]) for p in instances]
            self.assertEqual([future.result(timeout=10)[0] for future in futures],[{'instance':0},{'instance':1}])
        for index,(p,record) in enumerate(zip(instances,records)):
            record.assert_called_once();self.assertIs(record.call_args.args[0],p.settings)
            self.assertEqual(record.call_args.args[2:],(True,{'instance':index}));self.assertEqual(p.last_usage_metadata,{'instance':index})
        self.open.assert_not_called();self.record.assert_not_called()

    def test_independent_constructor_does_not_read_capabilities(self):
        from local_inspection_service.model_providers.gemini_transport import GeminiAiProvider
        from local_inspection_service.model_providers.gemini_ports import GeminiTransportIO,GeminiTransportErrors
        forbidden=Mock(side_effect=AssertionError('constructor capability read'))
        p=GeminiAiProvider(self.settings,GeminiTransportIO(*([forbidden]*8)),GeminiTransportErrors(*([forbidden]*5)),forbidden)
        self.assertIs(p.settings,self.settings);self.assertEqual(p.last_usage_metadata,{});self.assertEqual(p.last_raw_text,'');forbidden.assert_not_called()

    def test_original_dependency_capture_windows(self):
        sites=('data_url','decode','mask','cache:open','json:open','image:open','cache:config','json:config','image:config','cache:http_error','cache:url_error','json:url_error','image:url_proxy','image:url_direct','image:http_auth','image:http_config','image:http_error','image:http_overloaded')
        for site in sites:
            for mode in ('ordinary','prior','missing'):
                with self.subTest(site=site,mode=mode):capture_gemini_window(self.api,type(self),site,mode)

    def test_original_callbacks_refresh_between_items_and_formatting(self):
        for site in ('data_url','decode','formatter'):
            with self.subTest(site=site):capture_gemini_refresh(self.api,type(self),site)

if __name__=='__main__':unittest.main()

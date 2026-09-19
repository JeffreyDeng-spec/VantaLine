"""Offline behavior baseline for the existing Agnes and Qwen image providers."""
import copy
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


def capture_image_provider_window(api, Fixture, provider_name, site, mode='ordinary'):
    import io,time,urllib.error
    from contextlib import ExitStack
    from unittest.mock import patch
    f=Fixture();f.setUp();events=[]
    try:
        with patch.dict(api.__dict__),patch.object(api.requests,'get',api.requests.get),ExitStack() as stack:
            p=f.provider(provider_name);payload={};original_error=api.AiProviderError;original_overloaded=api.AiProviderOverloaded
            def install(owner,name,action):
                def callback(label):
                    def invoke(*a,**kw):events.append(label);return action(*a,**kw)
                    return invoke
                callbacks=[callback(label) for label in 'ABC'];setattr(owner,name,callbacks[0])
                def prior():events.append('prior');setattr(owner,name,callbacks[1] if mode=='prior' else None if mode=='missing' else callbacks[0])
                def argument():events.append('argument');setattr(owner,name,callbacks[2])
                return prior,argument
            if site=='open':
                original=f.open;prior,argument=install(api,'ai_urlopen',lambda *a,**kw:original(*a,**kw));ticks=[]
                def clock():
                    ticks.append(1)
                    if len(ticks)==1:prior()
                    return float(len(ticks))
                class Timeout:
                    def __float__(self):argument();return 12.5
                p.settings['timeout_seconds']=Timeout();stack.enter_context(patch.object(time,'monotonic',clock))
            elif site=='download':
                original=f.download;prior,argument=install(api.requests,'get',lambda *a,**kw:original(*a,**kw))
                class Item(dict):
                    def get(self,key,*args):
                        if key=='url':prior()
                        return super().get(key,*args)
                class Timeout:
                    def __float__(self):argument();return 12.5
                p.settings['timeout_seconds']=Timeout();payload=Item(url='https://fixture.invalid/image')
            elif site=='decode':
                prior,argument=install(api,'decode_b64_image',lambda value:b'image')
                def warmup(value):
                    assert value=='first',value
                    events.append('warmup');prior();return None
                api.decode_b64_image=warmup
                class Item(dict):
                    def get(self,key,*args):
                        if key=='base64':argument()
                        return super().get(key,*args)
                payload=Item(b64_json='first',base64='second')
            elif site=='mask':
                prior,argument=install(api,'masked_url_for_status',lambda value:'masked')
                class Settings(dict):
                    reads=0
                    def get(self,key,*args):
                        if key=='proxy_source_name':prior()
                        if key=='proxy_url_raw':
                            self.reads+=1
                            if self.reads==2:argument()
                        return super().get(key,*args)
                p.settings=Settings(p.settings,proxy_url_raw='synthetic-proxy')
            elif site=='http_overloaded':
                prior,argument=install(api,'AiProviderOverloaded',original_overloaded);formats=[]
                def formatter(value,limit):
                    formats.append((value,limit))
                    if len(formats)==1:prior()
                    elif len(formats)==2:argument()
                    else:raise AssertionError(formats)
                    return 'bounded'
                api.bounded_text=formatter;failure=urllib.error.HTTPError('https://fixture.invalid',429,'synthetic',{},io.BytesIO(b'detail'));f.open.side_effect=failure
            elif site=='url_error':
                prior,argument=install(api,'AiProviderError',original_error)
                class URLFailure(urllib.error.URLError):
                    reads=0
                    def __getattribute__(self,key):
                        if key=='reason':
                            count=object.__getattribute__(self,'reads')+1;object.__setattr__(self,'reads',count)
                            if count==1:prior()
                        return super().__getattribute__(key)
                failure=URLFailure('synthetic');f.open.side_effect=failure
                def formatter(value,limit):argument();return 'bounded'
                api.bounded_text=formatter
            else:raise AssertionError(site)
            caught=None;result=None
            try:
                if site in ('download','decode'):result=p.extract_image_bytes(payload)
                elif site=='mask':result=p.generate_image('prompt',[],model='synthetic')
                else:result=p.request_image({})
            except BaseException as exc:caught=exc
            assert 'prior' in events and 'argument' in events,(provider_name,site,mode,caught,events)
            assert events.index('prior')<events.index('argument'),events
            labels=[event for event in events if event in ('A','B','C')]
            if mode=='missing':
                assert type(caught) is TypeError,(provider_name,site,mode,caught,events)
                assert labels==[],events
            else:
                assert labels==['B' if mode=='prior' else 'A'],(provider_name,site,mode,caught,events)
                if site in ('http_overloaded','url_error'):
                    assert type(caught) is (original_overloaded if site=='http_overloaded' else original_error),(caught,events)
                    assert caught.__cause__ is failure
                else:
                    assert caught is None,(provider_name,site,mode,caught,events)
                    if site=='open':assert result[0]==f.body
                    elif site=='download':assert result==b'downloaded-image'
                    elif site=='decode':assert result==b'image'
                    else:assert result['bytes']==b'image' and result['proxy_url']=='masked'
            assert p.last_raw_text==''
            return {'events':events,'error':type(caught).__name__ if caught else None,'open_calls':f.open.call_count,'download_calls':f.download.call_count,'raw_text':p.last_raw_text,'record_calls':f.record.call_count}
    finally:f.doCleanups()


def capture_image_provider_decoder_refresh(api, Fixture, provider_name):
    from unittest.mock import patch
    f=Fixture();f.setUp();events=[]
    try:
        with patch.dict(api.__dict__):
            def second(value):
                if value is None:return None
                events.append(('B',value));return b'image' if value=='second' else None
            def first(value):
                if value is None:return None
                events.append(('A',value))
                if value=='first':api.decode_b64_image=second;return None
                return b'image' if value=='second' else None
            api.decode_b64_image=first;caught=None;result=None
            try:result=f.provider(provider_name).extract_image_bytes({'data':[{'b64_json':'first'},{'b64_json':'second'}]})
            except BaseException as exc:caught=exc
            assert caught is None,(provider_name,caught,events)
            assert result==b'image' and events==[('A','first'),('B','second')],events
            f.download.assert_not_called();f.open.assert_not_called();f.record.assert_not_called()
            return {'events':events,'result':'image','download_calls':0,'open_calls':0,'record_calls':0}
    finally:f.doCleanups()


class ImageProviderContracts(unittest.TestCase):
    names=('Agnes','Qwen')

    @classmethod
    def setUpClass(cls):
        cls.env=patch.dict(os.environ);cls.env.start()
        cls.tmp=tempfile.TemporaryDirectory(prefix='image-provider-')
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
        self.settings=dict(configured=True,model='synthetic-image',base_url='https://fixture.invalid/generate',api_key='synthetic-key',timeout_seconds='12.5')
        self.record=Mock();self.stack.enter_context(patch.object(self.api,'model_profile_service',SimpleNamespace(record_call=self.record)))
        self.open=self.stack.enter_context(patch.object(self.api,'ai_urlopen'))
        self.body={'data':[{'b64_json':'eA=='}]}
        self.response=Mock();self.response.__enter__=Mock(return_value=self.response);self.response.__exit__=Mock(return_value=False)
        self.response.read=Mock(side_effect=lambda:json.dumps(self.body).encode());self.open.return_value=self.response
        self.decode=self.stack.enter_context(patch.object(self.api,'decode_b64_image',side_effect=lambda value:b'image' if value=='eA==' else None))
        self.download=self.stack.enter_context(patch.object(self.api.requests,'get'))
        self.download.return_value.content=b'downloaded-image'

    def provider(self,name,bound=False):
        settings={**self.settings}
        if bound:settings['profile_id']='synthetic-profile'
        return getattr(self.api,name+'ImageProvider')(settings)

    def test_constructor_has_no_io_and_retains_state(self):
        for name in self.names:
            p=self.provider(name);self.assertEqual(p.settings,self.settings);self.assertEqual(p.last_raw_text,'')
            self.assertFalse(hasattr(p,'last_usage_metadata'))
        self.open.assert_not_called();self.download.assert_not_called();self.record.assert_not_called()

    def test_input_filtering_order_and_limits(self):
        items=[{'type':'text','text':' first '},{'type':'text','text':' '},{'type':'unknown'},*({'type':'image_url','image_url':{'url':f' image-{i} '}} for i in range(10))]
        self.assertEqual(self.provider('Agnes').input_images(items),[f'image-{i}' for i in range(8)])
        self.assertEqual(self.provider('Qwen').input_content(items),[{'text':'first'},*({'image':f'image-{i}'} for i in range(3))])

    def test_request_payload_headers_timeout_and_latency(self):
        for name in self.names:
            with self.subTest(name=name):
                self.open.reset_mock();p=self.provider(name);payload={'model':'synthetic','value':1}
                with patch.object(self.api.time,'monotonic',side_effect=[10,10.25]):result=p.request_image(payload)
                self.assertEqual(result,({'data':[{'b64_json':'eA=='}]},250));self.open.assert_called_once()
                request,settings=self.open.call_args.args;self.assertIs(settings,p.settings)
                self.assertEqual(request.full_url,self.settings['base_url']);self.assertEqual(request.method,'POST')
                self.assertEqual(request.data,b'{"model":"synthetic","value":1}')
                self.assertEqual(dict(request.header_items()),{'Authorization':'Bearer synthetic-key','Content-type':'application/json'})
                self.assertEqual(self.open.call_args.kwargs,{'timeout':12.5});self.record.assert_not_called()

    def test_request_shape_validation(self):
        for name in self.names:
            for raw in (b'not json',b'[]',b'null'):
                with self.subTest(name=name,raw=raw):
                    self.response.read.side_effect=None;self.response.read.return_value=raw
                    with self.assertRaises(self.api.AiProviderError) as caught:self.provider(name).request_image({})
                    self.assertEqual(str(caught.exception),name+' image provider response shape was not recognized')

    def test_request_failures_stop_before_infinite_valid_recovery(self):
        for name in self.names:
            for kind in ('timeout','url_timeout','url','http'):
                with self.subTest(name=name,kind=kind):
                    error=TimeoutError('synthetic') if kind=='timeout' else urllib.error.URLError(socket.timeout('synthetic')) if kind=='url_timeout' else urllib.error.URLError('synthetic') if kind=='url' else urllib.error.HTTPError('https://fixture.invalid',503,'bad',{},io.BytesIO(b'detail'))
                    hits=[]
                    def open_response(*args,**kwargs):
                        hits.append(1)
                        if len(hits)==1:raise error
                        return self.response
                    self.open.side_effect=open_response;caught=None
                    try:self.provider(name).request_image({})
                    except BaseException as exc:caught=exc
                    expected=self.api.AiProviderTimeout if 'timeout' in kind else self.api.AiProviderOverloaded if kind=='http' else self.api.AiProviderError
                    self.assertIs(type(caught),expected);self.assertIs(caught.__cause__,error);self.assertEqual(hits,[1])

    def test_request_http_classification(self):
        for name in self.names:
            for code,expected in [(401,self.api.AiProviderAuthError),(403,self.api.AiProviderAuthError),(429,self.api.AiProviderOverloaded),(503,self.api.AiProviderOverloaded),(400,self.api.AiProviderConfigError),(404,self.api.AiProviderConfigError),(500,self.api.AiProviderError)]:
                with self.subTest(name=name,code=code):
                    self.open.side_effect=urllib.error.HTTPError('https://fixture.invalid',code,'bad',{},io.BytesIO(b'detail'))
                    with self.assertRaises(expected) as caught:self.provider(name).request_image({})
                    self.assertIs(type(caught.exception),expected);self.assertEqual(caught.exception.http_status,code)

    def test_inline_extraction_and_key_priority(self):
        for name in self.names:
            with self.subTest(name=name):
                self.decode.reset_mock();payload={'data':[{'b64_json':'eA==','base64':'ignored','url':'https://fixture.invalid/image'}]}
                self.assertEqual(self.provider(name).extract_image_bytes(payload),b'image')
                self.download.assert_not_called();self.assertEqual(self.decode.call_args.args,('eA==',))

    def test_url_download_contract(self):
        for name in self.names:
            with self.subTest(name=name):
                self.download.reset_mock();p=self.provider(name)
                self.assertEqual(p.extract_image_bytes({'data':[{'url':'https://fixture.invalid/image'}]}),b'downloaded-image')
                self.download.assert_called_once_with('https://fixture.invalid/image',timeout=12.5)
                self.download.return_value.raise_for_status.assert_called_once_with()

    def test_url_failure_stops_without_retry(self):
        for name in self.names:
            with self.subTest(name=name):
                error=self.api.requests.RequestException('synthetic download failed');hits=[]
                def get(*args,**kwargs):
                    hits.append(1)
                    if len(hits)==1:raise error
                    return SimpleNamespace(content=b'image',raise_for_status=lambda:None)
                self.download.side_effect=get;caught=None
                try:self.provider(name).extract_image_bytes({'data':[{'url':'https://fixture.invalid/image'}]})
                except BaseException as exc:caught=exc
                self.assertIs(type(caught),self.api.AiProviderError);self.assertIs(caught.__cause__,error);self.assertEqual(hits,[1])
                self.assertIn(name+' image provider URL download failed:',str(caught))

    def test_missing_image_bytes_error(self):
        for name in self.names:
            with self.subTest(name=name),self.assertRaises(self.api.AiProviderError) as caught:self.provider(name).extract_image_bytes({'data':[{}]})
            self.assertEqual(str(caught.exception),name+' image provider did not return image bytes')

    def test_generation_configuration_failures_precede_request(self):
        for name in self.names:
            with self.subTest(name=name):
                p=self.provider(name);p.last_raw_text='prior';p.settings.update(configured=False,message='disabled')
                with self.assertRaises(self.api.AiProviderConfigError) as caught:p.generate_image('p',[],model='m')
                self.assertEqual(str(caught.exception),'disabled');self.assertEqual(p.last_raw_text,'prior')
                p.settings.update(configured=True,model=' ')
                with self.assertRaises(self.api.AiProviderConfigError):p.generate_image('p',[],model='')
        self.open.assert_not_called();self.download.assert_not_called()

    def test_agnes_payload_and_single_attempt_size(self):
        p=self.provider('Agnes',True);p.settings['single_attempt']=True
        with patch.dict(os.environ,{'VANTALINE_AGNES_IMAGE_SIZE':'2048x2048'}):result=p.generate_image('prompt',[{'type':'image_url','image_url':{'url':'image'}}],model='override',system_prompt='system')
        self.assertEqual(json.loads(self.open.call_args.args[0].data),{'model':'override','prompt':'SYSTEM_INSTRUCTIONS:\n\nsystem\n\nUSER_TASK:\n\nprompt','n':1,'size':'1024x1024','extra_body':{'response_format':'b64_json','image':['image']}})
        self.assertEqual(result['bytes'],b'image');self.assertEqual(result['model'],'override');self.record.assert_called_once();self.assertEqual(self.record.call_args.args[2:],(True,{}))

    def test_qwen_payload_and_single_attempt_size(self):
        p=self.provider('Qwen',True);p.settings['single_attempt']=True
        with patch.dict(os.environ,{'VANTALINE_QWEN_IMAGE_SIZE':'2048*2048'}):result=p.generate_image('prompt',[{'type':'image_url','image_url':{'url':'image'}}],model='override',system_prompt='system')
        self.assertEqual(json.loads(self.open.call_args.args[0].data),{'model':'override','input':{'messages':[{'role':'user','content':[{'text':'SYSTEM_INSTRUCTIONS:\n\nsystem\n\nUSER_TASK:\n\nprompt'},{'image':'image'}]}]},'parameters':{'n':1,'watermark':False,'size':'1024*1024'}})
        self.assertEqual(result['bytes'],b'image');self.assertEqual(result['model'],'override');self.record.assert_called_once();self.assertEqual(self.record.call_args.args[2:],(True,{}))

    def test_legacy_environment_sizes_and_generation_metadata(self):
        for name,key,value in [('Agnes','VANTALINE_AGNES_IMAGE_SIZE','1536x1536'),('Qwen','VANTALINE_QWEN_IMAGE_SIZE','1536*1536')]:
            with self.subTest(name=name),patch.dict(os.environ,{key:value}),patch.object(self.api,'masked_url_for_status',return_value='masked') as mask:
                p=self.provider(name);p.settings.update(proxy_url_raw='synthetic-proxy',proxy_source_name='synthetic',proxy_auto_local=True)
                result=p.generate_image('p',[],model='')
                payload=json.loads(self.open.call_args.args[0].data)
                self.assertEqual(payload['size'] if name=='Agnes' else payload['parameters']['size'],value)
                self.assertEqual({k:result[k] for k in ('mime_type','model','usage_metadata','text','proxy_used','proxy_source_name','proxy_url','proxy_auto_local')},{'mime_type':'image/png','model':'synthetic-image','usage_metadata':{},'text':'','proxy_used':True,'proxy_source_name':'synthetic','proxy_url':'masked','proxy_auto_local':True})
                mask.assert_called_once_with('synthetic-proxy')
        self.record.assert_not_called()

    def test_agnes_legacy_response_format_fallback_is_exactly_once(self):
        p=self.provider('Agnes',True);sent=[];error=self.api.AiProviderConfigError('unsupported response_format')
        def request(payload):
            sent.append(copy.deepcopy(payload))
            if len(sent)==1:raise error
            return self.body,17
        with patch.object(p,'request_image',side_effect=request) as call:result=p.generate_image('p',[{'type':'image_url','image_url':{'url':'image'}}],model='m')
        self.assertEqual(call.call_count,2);self.assertEqual(sent[0]['extra_body'],{'response_format':'b64_json','image':['image']});self.assertEqual(sent[1]['extra_body'],{'image':['image']})
        self.assertEqual(result['latency_ms'],17);self.record.assert_called_once();self.assertEqual(self.record.call_args.args[2:],(True,{}))

    def test_agnes_single_attempt_and_other_errors_never_fallback(self):
        for single,error in [(True,self.api.AiProviderConfigError('response_format')),(False,self.api.AiProviderConfigError('other option')),(False,self.api.AiProviderTimeout('unknown result')),(False,self.api.AiProviderError('unknown result'))]:
            with self.subTest(single=single,error=error):
                p=self.provider('Agnes');p.settings['single_attempt']=single;hits=[]
                def request(payload):
                    hits.append(1)
                    if len(hits)==1:raise error
                    return self.body,1
                caught=None
                with patch.object(p,'request_image',side_effect=request):
                    try:p.generate_image('p',[],model='m')
                    except BaseException as exc:caught=exc
                self.assertIs(caught,error);self.assertEqual(hits,[1])

    def test_missing_bound_resolver_prevents_all_io(self):
        for name in self.names:
            with self.subTest(name=name),patch.object(self.api,'model_profile_service',None),self.assertRaises(RuntimeError) as caught:self.provider(name,True).generate_image('p',[],model='m')
            self.assertEqual(str(caught.exception),'Model profile resolver is not configured')
        self.open.assert_not_called();self.download.assert_not_called();self.record.assert_not_called()

    def test_ledger_failure_does_not_repeat_generation(self):
        for name in self.names:
            with self.subTest(name=name):
                self.record.reset_mock();self.record.side_effect=RuntimeError('synthetic ledger failure');self.open.reset_mock()
                with self.assertLogs('local_inspection_service.model_profiles.audit',level='WARNING') as logs:result=self.provider(name,True).generate_image('p',[],model='m')
                self.assertEqual(result['bytes'],b'image');self.open.assert_called_once();self.record.assert_called_once()
                self.assertEqual(logs.output,['WARNING:local_inspection_service.model_profiles.audit:Model usage accounting unavailable'])


    def test_agnes_dynamic_config_exception_match(self):
        original = self.api.AiProviderConfigError
        for mode in ('same', 'other', 'missing'):
            with self.subTest(mode=mode), patch.object(self.api, 'AiProviderConfigError', original):
                error = original('unsupported response_format'); hits = []; caught = None; result = None
                replacement = original if mode == 'same' else type('Other', (Exception,), {}) if mode == 'other' else None
                def request(payload):
                    hits.append(copy.deepcopy(payload))
                    if len(hits) == 1:
                        self.api.AiProviderConfigError = replacement
                        raise error
                    return self.body, 1
                p = self.provider('Agnes', True); self.record.reset_mock()
                with patch.object(p, 'request_image', side_effect=request):
                    try: result = p.generate_image('p', [], model='m')
                    except BaseException as exc: caught = exc
                self.assertEqual(len(hits), 2 if mode == 'same' else 1)
                if mode == 'same': self.assertIsNone(caught); self.assertEqual(result['bytes'], b'image')
                elif mode == 'other': self.assertIs(caught, error)
                else: self.assertIs(type(caught), TypeError); self.assertIs(caught.__context__, error)
                self.record.assert_called_once(); self.assertEqual(self.record.call_args.args[2:], (mode == 'same', {}))

    def test_download_dynamic_exception_match_at_each_failure_site(self):
        original = self.api.requests.RequestException
        for name in self.names:
            for site in ('get', 'status', 'content'):
                for mode in ('same', 'other', 'missing'):
                    with self.subTest(name=name, site=site, mode=mode), patch.object(self.api.requests, 'RequestException', original):
                        error = original('synthetic'); hits = []; caught = None
                        replacement = original if mode == 'same' else type('Other', (Exception,), {}) if mode == 'other' else None
                        def fail(where):
                            hits.append(where)
                            if where == site and hits.count(where) == 1:
                                self.api.requests.RequestException = replacement
                                raise error
                        class Response:
                            def raise_for_status(inner): fail('status')
                            @property
                            def content(inner): fail('content'); return b'recovered'
                        def get(*args, **kwargs): fail('get'); return Response()
                        self.download.side_effect = get
                        try: self.provider(name).extract_image_bytes({'url':'https://fixture.invalid/image'})
                        except BaseException as exc: caught = exc
                        self.assertEqual(hits, ['get', 'status', 'content'][:('get','status','content').index(site)+1])
                        if mode == 'same': self.assertIs(type(caught), self.api.AiProviderError); self.assertIs(caught.__cause__, error)
                        elif mode == 'other': self.assertIs(caught, error)
                        else: self.assertIs(type(caught), TypeError); self.assertIs(caught.__context__, error)
                        self.record.assert_not_called()

    def test_agnes_second_compatibility_failure_never_third_attempt(self):
        p = self.provider('Agnes', True); errors = [self.api.AiProviderConfigError('response_format') for _ in range(2)]; hits = []; caught = None
        def request(payload):
            hits.append(copy.deepcopy(payload))
            if len(hits) <= 2: raise errors[len(hits)-1]
            return self.body, 1
        with patch.object(p, 'request_image', side_effect=request):
            try: p.generate_image('p', [], model='m')
            except BaseException as exc: caught = exc
        self.assertIs(caught, errors[1]); self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0]['extra_body'], {'response_format':'b64_json'}); self.assertEqual(hits[1]['extra_body'], {})
        self.record.assert_called_once(); self.assertEqual(self.record.call_args.args[2:], (False, {}))

    def test_size_lookup_skipped_for_single_attempt_and_refreshed_per_call(self):
        original_get = os.environ.get
        for name, key, default in [('Agnes','VANTALINE_AGNES_IMAGE_SIZE','1024x1024'),('Qwen','VANTALINE_QWEN_IMAGE_SIZE','1024*1024')]:
            with self.subTest(name=name):
                p = self.provider(name); p.settings['single_attempt'] = True; hits = []; value = [' first ']
                def get(k, fallback=None):
                    if k != key: return original_get(k, fallback)
                    hits.append((k, fallback)); return value[0]
                with patch.object(os.environ, 'get', side_effect=get):
                    p.generate_image('p', [], model='m'); self.assertEqual(hits, [])
                    payload = json.loads(self.open.call_args.args[0].data)
                    self.assertEqual(payload['size'] if name=='Agnes' else payload['parameters']['size'], default)
                    p.settings['single_attempt'] = False
                    for current in (' first ', ' second ', ' '):
                        value[0] = current; p.generate_image('p', [], model='m')
                        payload = json.loads(self.open.call_args.args[0].data)
                        self.assertEqual(payload['size'] if name=='Agnes' else payload['parameters']['size'], current.strip() or default)
                    self.assertEqual(hits, [(key, default)] * 3)

    def test_transport_resource_failure_accounted_once_without_retry(self):
        for name in self.names:
            for site in ('open', 'enter', 'read', 'exit', 'suppressed_read', 'http_read'):
                with self.subTest(name=name, site=site):
                    p = self.provider(name, True); p.last_raw_text = 'prior'; hits = []; error = RuntimeError('synthetic resource'); caught = None
                    def visit(where):
                        hits.append(where)
                        if where == site and hits.count(where) == 1: raise error
                    class Response:
                        def __enter__(inner): visit('enter'); return inner
                        def read(inner):
                            visit('read')
                            if site == 'suppressed_read' and hits.count('read') == 1: raise error
                            return json.dumps(self.body).encode()
                        def __exit__(inner, *args): visit('exit'); return site == 'suppressed_read'
                    def open_response(*args, **kwargs):
                        visit('open')
                        if site == 'http_read':
                            http = urllib.error.HTTPError('https://fixture.invalid', 503, 'bad', {}, None)
                            def read_http(): visit('http_read'); return b'valid error detail'
                            http.read = read_http
                            raise http
                        return Response()
                    self.open.side_effect = open_response; self.record.reset_mock()
                    try: p.generate_image('p', [], model='m')
                    except BaseException as exc: caught = exc
                    if site == 'suppressed_read': self.assertIs(type(caught), UnboundLocalError)
                    else: self.assertIs(caught, error)
                    expected = {'open':['open'], 'enter':['open','enter'], 'read':['open','enter','read','exit'], 'exit':['open','enter','read','exit'], 'suppressed_read':['open','enter','read','exit'], 'http_read':['open','http_read']}[site]
                    self.assertEqual(hits, expected); self.assertEqual(p.last_raw_text, 'prior')
                    self.record.assert_called_once(); self.assertEqual(self.record.call_args.args[2:], (False, {}))

    def test_resolver_function_capture_and_current_service_refresh(self):
        for name in self.names:
            with self.subTest(name=name):
                p = self.provider(name, True); first = Mock(); second = Mock()
                with patch.object(self.api, 'resolve_model_profiles', side_effect=AssertionError('must retain composition resolver')) as replacement:
                    for record in (first, second):
                        with patch.object(self.api, 'model_profile_service', SimpleNamespace(record_call=record)):
                            self.assertEqual(p.generate_image('p', [], model='m')['bytes'], b'image')
                    replacement.assert_not_called()
                first.assert_called_once(); second.assert_called_once()
                self.assertEqual(first.call_args.args[2:], (True, {})); self.assertEqual(second.call_args.args[2:], (True, {}))

    def test_decode_and_overload_formatter_refresh_between_calls(self):
        for name in self.names:
            with self.subTest(name=name), patch.object(self.api, 'decode_b64_image') as first:
                second = Mock(return_value=b'refreshed')
                def decode(value): self.api.decode_b64_image = second; return None
                first.side_effect = decode
                self.assertEqual(self.provider(name).extract_image_bytes({'b64_json':'first','base64':'second'}), b'refreshed')
                first.assert_called_once_with('first'); second.assert_called_once_with('second')
            with self.subTest(name=name), patch.object(self.api, 'bounded_text') as first:
                second = Mock(return_value='second')
                def text(value, limit): self.api.bounded_text = second; return 'first'
                first.side_effect = text
                self.open.side_effect = urllib.error.HTTPError('https://fixture.invalid',503,'bad',{},io.BytesIO(b'detail'))
                caught = None
                try: self.provider(name).request_image({})
                except BaseException as exc: caught = exc
                self.assertIs(type(caught), self.api.AiProviderOverloaded)
                self.assertEqual(str(caught), name+' image provider overloaded: HTTP 503 second')
                first.assert_called_once_with('detail',180); second.assert_called_once_with('detail',180)


    def independent_provider(self, name, settings, opener, record):
        from local_inspection_service.model_providers.agnes_transport import AgnesImageProvider
        from local_inspection_service.model_providers.qwen_image_transport import QwenImageProvider
        from local_inspection_service.model_providers.image_ports import ImageTransportIO, ImageTransportErrors
        from local_inspection_service.model_providers.errors import AiProviderConfigError, AiProviderTimeout, AiProviderError, AiProviderAuthError, AiProviderOverloaded
        import requests
        ports = ImageTransportIO(lambda:opener, lambda:lambda value,limit:str(value)[:limit], lambda:lambda value:b'image' if value=='eA==' else None, lambda:lambda value:'masked', lambda:Mock(side_effect=AssertionError('no download expected')))
        errors = ImageTransportErrors(lambda:AiProviderConfigError, lambda:AiProviderTimeout, lambda:AiProviderError, lambda:AiProviderAuthError, lambda:AiProviderOverloaded, lambda:requests.RequestException)
        args = (settings, ports, errors, lambda:SimpleNamespace(record_call=record), lambda:'synthetic-size')
        return AgnesImageProvider(*args, lambda:lambda payload:payload['data']) if name=='Agnes' else QwenImageProvider(*args)

    def test_independent_instances_keep_resolvers_and_state_separate(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier = Barrier(2); instances = []; records = []
        for index, name in enumerate(self.names):
            record = Mock(); records.append(record)
            response = Mock(); response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
            response.read = Mock(return_value=json.dumps(self.body).encode())
            def opener(*args, response=response, **kwargs): barrier.wait(timeout=5); return response
            p = self.independent_provider(name, {**self.settings,'profile_id':str(index)}, opener, record)
            p.last_raw_text = str(index); instances.append(p)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(p.generate_image,'p',[],model='m') for p in instances]
            self.assertEqual([future.result(timeout=10)['bytes'] for future in futures], [b'image',b'image'])
        for index, (p, record) in enumerate(zip(instances, records)):
            record.assert_called_once(); self.assertIs(record.call_args.args[0],p.settings)
            self.assertEqual(record.call_args.args[2:], (True,{})); self.assertEqual(p.last_raw_text,str(index))
            self.assertFalse(hasattr(p,'last_usage_metadata'))
        self.open.assert_not_called(); self.record.assert_not_called()

    def test_independent_constructor_does_not_read_capabilities(self):
        from local_inspection_service.model_providers.agnes_transport import AgnesImageProvider
        from local_inspection_service.model_providers.qwen_image_transport import QwenImageProvider
        from local_inspection_service.model_providers.image_ports import ImageTransportIO, ImageTransportErrors
        forbidden = Mock(side_effect=AssertionError('constructor capability read'))
        args = (self.settings,ImageTransportIO(*([forbidden]*5)),ImageTransportErrors(*([forbidden]*6)),forbidden,forbidden)
        for p in (AgnesImageProvider(*args,forbidden), QwenImageProvider(*args)):
            self.assertIs(p.settings,self.settings); self.assertEqual(p.last_raw_text,'')
            self.assertFalse(hasattr(p,'last_usage_metadata'))
        forbidden.assert_not_called()


    def test_original_dependency_capture_windows(self):
        for name in self.names:
            for site in ('open','download','decode','mask','http_overloaded','url_error'):
                for mode in ('ordinary','prior','missing'):
                    with self.subTest(name=name,site=site,mode=mode):
                        capture_image_provider_window(self.api,type(self),name,site,mode)

    def test_original_decoder_refresh_across_items(self):
        for name in self.names:
            with self.subTest(name=name):capture_image_provider_decoder_refresh(self.api,type(self),name)


if __name__=='__main__':unittest.main()

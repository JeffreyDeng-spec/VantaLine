"""Offline executor configuration and RunPod request contracts; transport always substituted."""
from contextlib import ExitStack
from itertools import chain, repeat
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


class TrainingExecutorContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ);cls.environment.start()
        cls.runtime=tempfile.TemporaryDirectory(prefix='executor-root-');root=Path(cls.runtime.name)
        (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.runtime.cleanup();cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ,{},clear=True))
        self.request=self.stack.enter_context(patch.object(requests,'request',side_effect=AssertionError('unexpected network request')))
    def response(self,status,body=None,text='',failure=None):
        value=Mock(status_code=status,text=text);value.json.return_value=body
        if failure is not None:value.json.side_effect=failure
        return value
    def configured(self):
        api=self.api
        os.environ.update({api.RUNPOD_YOLO_ENDPOINT_ID_ENV:' end /点 ',api.RUNPOD_YOLO_API_KEY_ENV:' fixture-key ',api.RUNPOD_YOLO_API_BASE_ENV:'https://runpod.invalid/v2/'})

    def test_executor_aliases_and_lazy_environment(self):
        api=self.api
        self.assertEqual(api.training_executor_mode(),'local')
        for raw,wanted in [(' Local ','local'),('REMOTE','remote'),('worker','runpod'),('RunPod','runpod'),('unknown','local'),('','local')]:
            os.environ[api.REMOTE_TRAINING_EXECUTOR_ENV]=raw;self.assertEqual(api.training_executor_mode(),wanted)
        for raw in ('1',' TRUE ','yes','on'):
            os.environ['INSPECTION_WORKER_LOCAL_TRAINING_FALLBACK']=raw;self.assertTrue(api.worker_local_training_fallback_enabled())
        for raw in ('','0','enabled','false'):
            os.environ['INSPECTION_WORKER_LOCAL_TRAINING_FALLBACK']=raw;self.assertFalse(api.worker_local_training_fallback_enabled())
        self.assertEqual(api.windows_worker_headers(),{})
        os.environ[api.WINDOWS_WORKER_TOKEN_ENV]=' fixture ';self.assertEqual(api.windows_worker_headers(),{'Authorization':'Bearer fixture'})
        self.request.assert_not_called()

    def test_private_host_and_remote_endpoint_validation(self):
        api=self.api
        for host in ('localhost','[::1]','127.0.0.1','10.1.2.3','100.64.0.1','100.127.255.254','box.local','BOX.LAN','node.internal'):
            self.assertTrue(api.host_is_private_or_tailnet(host),host)
        for host in ('public.invalid','8.8.8.8','100.128.0.1','', 'localhost.invalid'):
            self.assertFalse(api.host_is_private_or_tailnet(host),host)
        for validator,env,reader in [(api.validate_remote_training_endpoint,api.REMOTE_TRAINING_ENDPOINT_ENV,api.remote_training_endpoint),
                (api.validate_windows_worker_base_url,api.WINDOWS_WORKER_BASE_URL_ENV,api.windows_worker_base_url)]:
            self.assertEqual(validator(None),'');self.assertEqual(validator(' https://public.invalid/api/// '),'https://public.invalid/api')
            self.assertEqual(validator('http://node.internal/'),'http://node.internal')
            for raw,detail in [('ftp://x','must be an http(s) URL'),('/relative','must be an http(s) URL'),
                    ('https://user:pass@x','must not include credentials'),('https://x/?q=1','must not include query strings or fragments'),
                    ('https://x/#f','must not include query strings or fragments'),('http://8.8.8.8','uses http; use a private/Tailscale/reverse-tunnel host or HTTPS')]:
                with self.assertRaises(RuntimeError) as error:validator(raw)
                self.assertEqual(str(error.exception),env+' '+detail)
            os.environ[env]=' https://service.invalid/a/ ';self.assertEqual(reader(),'https://service.invalid/a')
            os.environ[env]='https://x:invalid/';self.assertEqual(reader(),'https://x:invalid')
        self.request.assert_not_called()

    def test_timeout_defaults_clamps_invalid_nan_and_integer_overflow(self):
        api=self.api
        cases=[('remote_training_timeout_seconds',api.REMOTE_TRAINING_TIMEOUT_ENV,600.0,5.0,3600.0,False),
            ('windows_worker_timeout_seconds',api.WINDOWS_WORKER_TIMEOUT_ENV,30.0,2.0,3600.0,False),
            ('windows_worker_image_timeout_seconds','VANTALINE_WORKER_IMAGE_TIMEOUT_SECONDS',960.0,60.0,1800.0,False),
            ('runpod_yolo_job_timeout_seconds',api.RUNPOD_YOLO_JOB_TIMEOUT_ENV,7200,300,604800,True),
            ('runpod_yolo_client_timeout_seconds',api.RUNPOD_YOLO_CLIENT_TIMEOUT_ENV,60.0,5.0,300.0,False),
            ('runpod_yolo_poll_interval_seconds',api.RUNPOD_YOLO_POLL_INTERVAL_ENV,20.0,5.0,120.0,False),
            ('runpod_yolo_dataset_token_ttl_seconds',api.RUNPOD_YOLO_DATASET_TOKEN_TTL_ENV,259200,3600,604800,True),
            ('runpod_yolo_inline_dataset_max_bytes',api.RUNPOD_YOLO_INLINE_DATASET_MAX_BYTES_ENV,0,0,8388608,True),
            ('runpod_yolo_artifact_max_bytes',api.RUNPOD_YOLO_ARTIFACT_MAX_BYTES_ENV,268435456,10485760,1073741824,True)]
        for name,key,default,minimum,maximum,integer in cases:
            fn=getattr(api,name)
            self.assertEqual(fn(),default,name)
            for raw,wanted in [('',default),('bad',default),('-1',minimum),('1e20',maximum),('nan',default if integer else maximum)]:
                os.environ[key]=raw;self.assertEqual(fn(),wanted,(name,raw))
            os.environ[key]='inf'
            if integer:
                with self.assertRaises(OverflowError,msg=name):fn()
            else:self.assertEqual(fn(),maximum)
            os.environ[key]=str(minimum+0.75)
            self.assertEqual(fn(),minimum if integer else minimum+0.75)
        self.request.assert_not_called()

    def test_runpod_required_fields_fallback_precedence_and_url_encoding(self):
        api=self.api
        for fn,key in [(api.runpod_yolo_endpoint_id,api.RUNPOD_YOLO_ENDPOINT_ID_ENV),(api.runpod_yolo_api_key,api.RUNPOD_YOLO_API_KEY_ENV)]:
            with self.assertRaises(RuntimeError) as error:fn()
            self.assertEqual(str(error.exception),key+' is not configured')
        os.environ['RUNPOD_API_KEY']=' fallback ';self.assertEqual(api.runpod_yolo_api_key(),'fallback')
        os.environ[api.RUNPOD_YOLO_API_KEY_ENV]='   '
        with self.assertRaises(RuntimeError):api.runpod_yolo_api_key()
        os.environ[api.RUNPOD_YOLO_API_KEY_ENV]='';self.assertEqual(api.runpod_yolo_api_key(),'fallback')
        self.assertEqual(api.runpod_yolo_api_base(),'https://api.runpod.ai/v2')
        for reader,key,fallback in [(api.runpod_yolo_api_base,api.RUNPOD_YOLO_API_BASE_ENV,None),
                (api.runpod_yolo_public_base_url,api.RUNPOD_YOLO_PUBLIC_BASE_URL_ENV,'INSPECTION_PUBLIC_BASE_URL')]:
            if fallback:os.environ[fallback]=' https://service.invalid/ ';self.assertEqual(reader(),'https://service.invalid')
            for raw in ('https://x/?q=1','https://x/#f','ftp://x','https://u:p@x',' '):
                os.environ[key]=raw
                with self.assertRaises(RuntimeError):reader()
            os.environ[key]=' http://8.8.8.8/api/// ';self.assertEqual(reader(),'http://8.8.8.8/api')
        self.configured()
        self.assertEqual(api.runpod_yolo_url(' /status/x '),'https://runpod.invalid/v2/end%20%2F%E7%82%B9/status/x')
        self.assertEqual(api.runpod_yolo_url(None),'https://runpod.invalid/v2/end%20%2F%E7%82%B9/')
        for scheme,wanted in [(' Raw ',['fixture-key','Bearer fixture-key']),('none',['fixture-key','Bearer fixture-key']),
                ('token',['fixture-key','Bearer fixture-key']),('', ['Bearer fixture-key','fixture-key']),('unexpected',['Bearer fixture-key','fixture-key'])]:
            os.environ[api.RUNPOD_YOLO_AUTH_SCHEME_ENV]=scheme;self.assertEqual(api.runpod_yolo_authorization_values(),wanted)
        self.request.assert_not_called()

    def test_status_endpoint_errors_flags_masking_and_retired_probe(self):
        api=self.api;os.environ[api.REMOTE_TRAINING_EXECUTOR_ENV]='worker'
        os.environ.update({api.REMOTE_TRAINING_ENDPOINT_ENV:'http://8.8.8.8',api.REMOTE_TRAINING_API_KEY_ENV:' fixture ',api.RUNPOD_YOLO_ENDPOINT_ID_ENV:' endpoint ',
            api.RUNPOD_YOLO_API_KEY_ENV:' ', 'RUNPOD_API_KEY':'fallback',api.RUNPOD_YOLO_PUBLIC_BASE_URL_ENV:' ', 'INSPECTION_PUBLIC_BASE_URL':' https://service.invalid '})
        result=api.training_execution_status(include_worker_probe=True,include_worker_services=True)
        self.assertEqual(result,{'executor':'runpod','remote_enabled':False,'remote_endpoint_configured':False,'remote_endpoint':'',
            'remote_endpoint_error':api.REMOTE_TRAINING_ENDPOINT_ENV+' uses http; use a private/Tailscale/reverse-tunnel host or HTTPS',
            'remote_api_key_present':True,'required_endpoint_env':api.REMOTE_TRAINING_ENDPOINT_ENV,'required_api_key_env':api.REMOTE_TRAINING_API_KEY_ENV,
            'runpod_enabled':True,'runpod_endpoint_configured':True,'runpod_api_key_present':False,'runpod_public_base_url_configured':True,
            'required_runpod_endpoint_env':api.RUNPOD_YOLO_ENDPOINT_ID_ENV,'required_runpod_api_key_env':api.RUNPOD_YOLO_API_KEY_ENV,
            'required_runpod_public_base_url_env':api.RUNPOD_YOLO_PUBLIC_BASE_URL_ENV,'retired_executors':['windows_worker']})
        os.environ[api.REMOTE_TRAINING_ENDPOINT_ENV]='https://x:invalid/path'
        self.assertEqual(api.training_execution_status()['remote_endpoint'],'https://x/path')
        self.assertEqual(api.windows_worker_status(force=True,probe=True,include_services=True),{'configured':False,'ok':False,'status':'retired',
            'message':'Windows Worker execution is retired. Production training uses RunPod.'})
        for request in (api.windows_worker_request,api.windows_worker_form_request):
            with self.assertRaisesRegex(RuntimeError,'Windows Worker execution is retired'):request('POST','/execute')
        self.request.assert_not_called()
        original_get=os.environ.get;events=[]
        def get(key,default=None):events.append(key);return original_get(key,default)
        with patch.object(os.environ,'get',side_effect=get),patch.object(api,'masked_url_for_status',side_effect=lambda value:events.append('mask') or 'masked'):
            self.assertEqual(api.training_execution_status()['remote_endpoint'],'masked')
        self.assertEqual(events[:3],[api.REMOTE_TRAINING_ENDPOINT_ENV,api.REMOTE_TRAINING_EXECUTOR_ENV,'mask'])
        os.environ[api.REMOTE_TRAINING_ENDPOINT_ENV]='https://['
        with self.assertRaises(ValueError):api.training_execution_status()
        os.environ[api.REMOTE_TRAINING_ENDPOINT_ENV]='https://x'
        with patch.object(api,'masked_url_for_status',side_effect=RuntimeError('mask')):
            with self.assertRaisesRegex(RuntimeError,'mask'):api.training_execution_status()

    def test_runpod_request_one_success_identity_headers_and_timeout(self):
        api=self.api;self.configured();body={'id':'job'};response=self.response(200,body);self.request.side_effect=None;self.request.return_value=response
        self.assertIs(api.runpod_yolo_http_request('POST','run',json_body={},timeout_seconds=12),body)
        self.request.assert_called_once_with('POST','https://runpod.invalid/v2/end%20%2F%E7%82%B9/run',json={},
            headers={'accept':'application/json','authorization':'Bearer fixture-key','content-type':'application/json'},timeout=12)
        response.json.assert_called_once_with();self.request.reset_mock();response.json.return_value=['value']
        self.assertEqual(api.runpod_yolo_http_request('GET','status',timeout_seconds=0),{'result':['value']})
        self.request.assert_called_once();kwargs=self.request.call_args.kwargs
        self.assertEqual(kwargs['timeout'],60.0);self.assertNotIn('content-type',kwargs['headers']);self.assertIsNone(kwargs['json'])
        self.request.reset_mock();api.runpod_yolo_http_request('GET','status',timeout_seconds=-1)
        self.assertEqual(self.request.call_args.kwargs['timeout'],-1)

    def test_runpod_auth_fallback_only_after_explicit_auth_failure(self):
        api=self.api;self.configured()
        for status in (401,403):
            self.request.reset_mock();self.request.side_effect=[self.response(status,{'error':'auth'}),self.response(201,{'id':'job'})]
            self.assertEqual(api.runpod_yolo_http_request('POST','run',json_body={'input':'synthetic'}),{'id':'job'})
            self.assertEqual(self.request.call_count,2)
            first,second=self.request.call_args_list
            self.assertEqual(first.args,second.args);self.assertEqual(first.kwargs['json'],second.kwargs['json'])
            self.assertEqual([call.kwargs['headers']['authorization'] for call in (first,second)],['Bearer fixture-key','fixture-key'])
        self.request.reset_mock();self.request.side_effect=[self.response(401,{}),self.response(403,{'detail':'denied'})]
        with self.assertRaises(RuntimeError) as error:api.runpod_yolo_http_request('POST','run')
        self.assertEqual(str(error.exception),'RunPod returned HTTP 403: denied');self.assertEqual(self.request.call_count,2)
        for status in (400,429,500):
            self.request.reset_mock();self.request.side_effect=[self.response(status,{'error':'first','detail':'second','message':'third'})]
            with self.assertRaises(RuntimeError) as error:api.runpod_yolo_http_request('POST','run')
            self.assertEqual(str(error.exception),f'RunPod returned HTTP {status}: first');self.assertEqual(self.request.call_count,1)

    def test_runpod_uncertain_failure_never_retries_and_preserves_exception(self):
        api=self.api;self.configured()
        for failure in (requests.Timeout('fixture secret'),requests.ConnectionError('fixture secret')):
            self.request.reset_mock();self.request.side_effect=failure
            with self.assertRaises(RuntimeError) as error:api.runpod_yolo_http_request('POST','run')
            self.assertEqual(str(error.exception),'RunPod request failed: '+type(failure).__name__)
            self.assertIs(error.exception.__cause__,failure);self.request.assert_called_once()
        failure=RuntimeError('transport');self.request.side_effect=failure
        with self.assertRaises(RuntimeError) as error:api.runpod_yolo_http_request('POST','run')
        self.assertIs(error.exception,failure)

    def test_runpod_captures_url_auth_once_but_default_timeout_per_attempt(self):
        api=self.api;self.configured();events=[];timeouts=iter([7,9]);auth=api.runpod_yolo_authorization_values
        def get_auth():events.append('auth');return auth()
        def timeout():events.append('timeout');return next(timeouts)
        def request(*args,**kwargs):
            events.append(('request',kwargs['headers']['authorization'],kwargs['timeout']))
            os.environ[api.RUNPOD_YOLO_API_KEY_ENV]='changed-key'
            return self.response(401 if self.request.call_count==1 else 200,{'ok':True})
        self.request.side_effect=request
        with patch.object(api,'runpod_yolo_url',side_effect=lambda path:events.append(('url',path)) or 'https://fixture.invalid/run') as url,\
                patch.object(api,'runpod_yolo_authorization_values',side_effect=get_auth) as authorization,\
                patch.object(api,'runpod_yolo_client_timeout_seconds',side_effect=timeout) as default_timeout:
            self.assertEqual(api.runpod_yolo_http_request('POST','run',timeout_seconds=0),{'ok':True})
            self.assertEqual(events,[('url','run'),'auth','timeout',('request','Bearer fixture-key',7),'timeout',('request','fixture-key',9)])
            url.assert_called_once_with('run');authorization.assert_called_once_with();self.assertEqual(default_timeout.call_count,2)
            self.request.reset_mock();authorization.reset_mock();url.side_effect=RuntimeError('url')
            with self.assertRaisesRegex(RuntimeError,'url'):api.runpod_yolo_http_request('POST','run')
            authorization.assert_not_called();self.request.assert_not_called()
            url.side_effect=None;url.return_value='https://fixture.invalid/run';authorization.side_effect=ValueError('auth')
            with self.assertRaisesRegex(ValueError,'auth'):api.runpod_yolo_http_request('POST','run')
            self.request.assert_not_called()
            authorization.side_effect=None;authorization.return_value=[]
            with self.assertRaisesRegex(RuntimeError,'RunPod returned HTTP 0: request failed'):api.runpod_yolo_http_request('POST','run')
            self.request.assert_not_called()

    def test_runpod_non_json_body_error_bounds_and_unexpected_shape(self):
        api=self.api;self.configured()
        self.request.side_effect=None;self.request.return_value=self.response(200,text='x'*600,failure=ValueError('json'))
        self.assertEqual(api.runpod_yolo_http_request('GET','status'),{'message':'x'*500})
        self.request.reset_mock();self.request.return_value=self.response(500,text='  '+('e '*400),failure=ValueError('json'))
        with self.assertRaises(RuntimeError) as error:api.runpod_yolo_http_request('POST','run')
        self.assertEqual(str(error.exception),'RunPod returned HTTP 500: '+('e '*120));self.request.assert_called_once()
        for body in (None,False,0,[],{'error':'','detail':'','message':''}):
            self.request.reset_mock();self.request.return_value=self.response(500,body)
            with self.assertRaisesRegex(RuntimeError,'RunPod returned HTTP 500: request failed'):api.runpod_yolo_http_request('POST','run')
            self.request.assert_called_once()
        self.request.reset_mock();self.request.return_value=self.response(200,failure=TypeError('decode'))
        with self.assertRaisesRegex(TypeError,'decode'):api.runpod_yolo_http_request('GET','status')
        self.request.assert_called_once()

    def test_summary_redaction_recursion_limits_hash_and_input_immutability(self):
        api=self.api;value={'Authorization':'secret','API_KEY':123,'nested':[{'dataset_url':'url','ok':'a\n b'}],
            'token':'','items':list(range(90)),'text':' z '*1500,'artifact_b64':'abc','Other':None}
        result=api.runpod_public_response_summary(value)
        self.assertEqual(result['Authorization'],'<redacted:6 chars>');self.assertEqual(result['API_KEY'],'<redacted>')
        self.assertEqual(result['nested'],[{'dataset_url':'<redacted:3 chars>','ok':'a b'}]);self.assertEqual(result['token'],'<redacted:0 chars>')
        self.assertEqual(result['items'],list(range(80)));self.assertEqual(result['text'],('z '*600))
        self.assertIsNone(result['Other']);self.assertEqual(value['Authorization'],'secret');self.assertEqual(len(value['items']),90)
        value=({'token':'tuple-preserved'},);self.assertIs(api.runpod_public_response_summary(value),value)
        for key in ('artifact_b64','dataset_url','base_model_url','artifact_upload_url','authorization','api_key','token','secret'):
            self.assertEqual(api.runpod_public_response_summary({key.upper():'x',' '+key:'x'}),{key.upper():'<redacted:1 chars>',' '+key:'x'})
        for token in (None,'',' 中文 ',123):
            self.assertEqual(api.runpod_dataset_token_hash(token),hashlib.sha256(str(token or '').encode('utf-8')).hexdigest())
        self.request.assert_not_called()

    def test_independent_settings_clients_lazy_providers_and_light_import(self):
        from local_inspection_service.training.executor_settings import ExecutorSettings
        from local_inspection_service.training.runpod_client import RunPodClient,RunPodRequestSettings
        api=self.api;values={api.RUNPOD_YOLO_ENDPOINT_ID_ENV:'one',api.RUNPOD_YOLO_API_KEY_ENV:'first'}
        environment=Mock(side_effect=lambda:values);mask=Mock(side_effect=lambda value:'masked:'+str(value))
        first=ExecutorSettings(environment,mask)
        second=ExecutorSettings(lambda:{api.RUNPOD_YOLO_ENDPOINT_ID_ENV:'two',api.RUNPOD_YOLO_API_KEY_ENV:'second'},str)
        environment.assert_not_called();mask.assert_not_called()
        self.assertEqual(first.runpod_yolo_endpoint_id(),'one');self.assertEqual(second.runpod_yolo_endpoint_id(),'two')
        values={api.RUNPOD_YOLO_ENDPOINT_ID_ENV:'three',api.RUNPOD_YOLO_API_KEY_ENV:'third'}
        self.assertEqual(first.runpod_yolo_endpoint_id(),'three');self.assertEqual(first.runpod_yolo_api_key(),'third')
        self.assertEqual(second.runpod_yolo_api_key(),'second')
        url=Mock(return_value='https://fixture.invalid/run');authorization=Mock(return_value=['fixture']);timeout=Mock(return_value=8)
        response={'id':'standalone'};transport=Mock(return_value=self.response(200,response));bound=Mock(side_effect=lambda value,limit:str(value)[:limit])
        client=RunPodClient(RunPodRequestSettings(url,authorization,timeout),lambda:transport,lambda:bound)
        for callback in (url,authorization,timeout,transport,bound):callback.assert_not_called()
        self.assertIs(client.runpod_yolo_http_request('POST','run'),response)
        url.assert_called_once_with('run');authorization.assert_called_once_with();timeout.assert_called_once_with()
        transport.assert_called_once_with('POST','https://fixture.invalid/run',json=None,headers={'accept':'application/json','authorization':'fixture'},timeout=8)
        self.assertEqual(client.runpod_public_response_summary('text'),'text');bound.assert_called_once_with('text',1200)
        self.request.assert_not_called()
        code='import sys; from local_inspection_service.training import executor_settings, runpod_client; assert "local_inspection_service.server" not in sys.modules; assert "torch" not in sys.modules; assert "ultralytics" not in sys.modules'
        result=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_callback_capture_before_argument_effects(self):
        api=self.api
        for window in ('request','error','terminal'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(window=window,mode=mode),ExitStack() as stack:
                    events=[];body={'ok':True}
                    def transport(label):
                        def call(*a,**kw):events.append(label);return self.response(200,body)
                        return call
                    def formatter(label):
                        def call(*a):events.append(label);return label
                        return call
                    first=transport('A') if window=='request' else formatter('A')
                    prior=transport('B') if window=='request' else formatter('B')
                    late=transport('C') if window=='request' else formatter('C')
                    target=requests if window=='request' else api;name='request' if window=='request' else 'bounded_text'
                    stack.enter_context(patch.object(target,name,first))
                    def before():
                        events.append('before')
                        if mode!='ordinary':setattr(target,name,prior if mode=='prior' else None)
                    def argument():setattr(target,name,late);events.append('argument');return 7
                    class Detail:
                        def __str__(self):argument();return 'detail'
                    class Status(int):
                        def __format__(self,spec):before();return int.__format__(self,spec)
                    class ShortAuth:
                        def __iter__(self):return iter(['synthetic'])
                        def __len__(self):return 2
                    class Body(dict):
                        def get(self,key,*args):
                            if window=='terminal' and key=='error':before()
                            return super().get(key,*args)
                    stack.enter_context(patch.object(api,'runpod_yolo_url',return_value='https://fixture.invalid/run'))
                    def authorization():
                        if window=='request':before()
                        return ShortAuth() if window=='terminal' else ['synthetic']
                    stack.enter_context(patch.object(api,'runpod_yolo_authorization_values',side_effect=authorization))
                    stack.enter_context(patch.object(api,'runpod_yolo_client_timeout_seconds',side_effect=argument if window=='request' else lambda:7))
                    if window!='request':
                        response=self.response(Status(500) if window=='error' else 401,Body(error=Detail()))
                        stack.enter_context(patch.object(requests,'request',return_value=response))
                    if mode=='missing':
                        with self.assertRaises(BaseException) as error:api.runpod_yolo_http_request('POST','run')
                        self.assertIs(type(error.exception),TypeError)
                    elif window=='request':self.assertIs(api.runpod_yolo_http_request('POST','run'),body)
                    else:
                        with self.assertRaises(RuntimeError) as error:api.runpod_yolo_http_request('POST','run')
                        self.assertEqual(str(error.exception),'RunPod returned HTTP '+('500' if window=='error' else '401')+': '+('A' if mode=='ordinary' else 'B'))
                    self.assertEqual(events,['before','argument']+([] if mode=='missing' else ['A' if mode=='ordinary' else 'B']))

    def test_http_first_failures_never_consume_later_valid_results(self):
        api=self.api
        for stage in ('url','auth','timeout','request','json','status','text','error','terminal','summary'):
            failures=(requests.Timeout('synthetic'),RuntimeError('synthetic'),KeyboardInterrupt('synthetic')) if stage in ('url','auth','timeout','request') else (OSError('synthetic'),)
            for failure in failures:
                with self.subTest(stage=stage,failure=type(failure).__name__),ExitStack() as stack:
                    good=self.response(200,{'ok':True});bad=self.response(500,{'error':'synthetic'})
                    callbacks={
                        'url':stack.enter_context(patch.object(api,'runpod_yolo_url',return_value='https://fixture.invalid/run')),
                        'auth':stack.enter_context(patch.object(api,'runpod_yolo_authorization_values',return_value=['one','two'])),
                        'timeout':stack.enter_context(patch.object(api,'runpod_yolo_client_timeout_seconds',return_value=7)),
                        'request':stack.enter_context(patch.object(requests,'request',side_effect=[bad,good])),
                        'bound':stack.enter_context(patch.object(api,'bounded_text',return_value='safe')),
                    }
                    if stage in ('url','auth','timeout','request'):callbacks['request'].side_effect=[good,good]
                    if stage in ('url','auth','timeout','request'):
                        callbacks[stage].side_effect=[failure,{'url':'https://fixture.invalid/run','auth':['one'],'timeout':7,'request':good}[stage]]
                    elif stage=='json':bad.status_code=401;bad.json.side_effect=[failure,{'ok':True}];probe=bad.json
                    elif stage=='status':
                        probe=Mock(side_effect=chain([failure],repeat(200)))
                        class Status(int):
                            def __int__(self):return probe()
                        bad.status_code=Status(200)
                    elif stage=='text':
                        bad.status_code=401;bad.json.side_effect=ValueError('decode');probe=Mock(side_effect=chain([failure],repeat('valid')))
                        class Text:
                            def __getitem__(self,key):return probe(key)
                        bad.text=Text()
                    else:
                        callbacks['bound'].side_effect=chain([failure],repeat('safe'))
                        if stage=='terminal':
                            class ShortAuth:
                                def __iter__(self):return iter(['one'])
                                def __len__(self):return 2
                            callbacks['auth'].return_value=ShortAuth();bad.status_code=401
                    wrapped=stage in ('timeout','request') and isinstance(failure,requests.RequestException)
                    with self.assertRaises(BaseException) as error:
                        if stage=='summary':api.runpod_public_response_summary(['first','later'])
                        else:api.runpod_yolo_http_request('POST','run')
                    if wrapped:
                        self.assertIs(error.exception.__cause__,failure);self.assertEqual(str(error.exception),'RunPod request failed: Timeout')
                    else:self.assertIs(error.exception,failure)
                    expected={'url':1,'auth':1,'timeout':1,'request':1,'bound':0}
                    if stage=='url':expected.update(auth=0,timeout=0,request=0)
                    if stage=='auth':expected.update(timeout=0,request=0)
                    if stage=='timeout':expected.update(request=0)
                    if stage in ('error','terminal'):expected['bound']=1
                    if stage=='summary':expected={key:int(key=='bound') for key in expected}
                    self.assertEqual({key:value.call_count for key,value in callbacks.items()},expected)
                    if stage in ('json','status','text'):self.assertEqual(probe.call_count,1)
                    if stage=='status':bad.json.assert_not_called()

    def test_second_authorized_attempt_failure_is_not_replayed(self):
        api=self.api
        for stage in ('timeout','request','json'):
            for status in (401,403):
                with self.subTest(stage=stage,status=status),ExitStack() as stack:
                    self.configured();failure=requests.Timeout('synthetic') if stage!='json' else OSError('synthetic')
                    second=self.response(200,{'ok':True});second.json.side_effect=[failure,{'ok':True}] if stage=='json' else None
                    self.request.reset_mock();self.request.side_effect=[self.response(status,{}),failure if stage=='request' else second,self.response(200,{})]
                    timeout=stack.enter_context(patch.object(api,'runpod_yolo_client_timeout_seconds',side_effect=[7,failure if stage=='timeout' else 8,9]))
                    with self.assertRaises(BaseException) as error:api.runpod_yolo_http_request('POST','run')
                    self.assertIs(error.exception if stage=='json' else error.exception.__cause__,failure)
                    self.assertEqual(timeout.call_count,2);self.assertEqual(self.request.call_count,1 if stage=='timeout' else 2)
                    self.assertEqual(second.json.call_count,1 if stage=='json' else 0)

    def test_json_value_error_fallback_precedes_authorization_retry(self):
        api=self.api;self.configured()
        for status in (401,403):
            self.request.reset_mock();first=self.response(status,text='raw',failure=ValueError('decode'));second=self.response(200,{'ok':True})
            self.request.side_effect=[first,second]
            self.assertEqual(api.runpod_yolo_http_request('POST','run'),{'ok':True});self.assertEqual(self.request.call_count,2)
            first.json.assert_called_once_with();second.json.assert_called_once_with()

    def test_new_getter_failures_stop_before_argument_effects(self):
        api=self.api
        for stage in ('request','error','terminal','summary'):
            for failure in (requests.Timeout('synthetic'),OSError('synthetic')):
                with self.subTest(stage=stage,failure=type(failure).__name__),ExitStack() as stack:
                    service=api._runpod_client;events=[]
                    class Detail:
                        def __str__(self):events.append('detail');return 'detail'
                    class ShortAuth:
                        def __iter__(self):return iter(['one'])
                        def __len__(self):return 2
                    stack.enter_context(patch.object(api,'runpod_yolo_url',return_value='https://fixture.invalid/run'))
                    stack.enter_context(patch.object(api,'runpod_yolo_authorization_values',return_value=ShortAuth() if stage=='terminal' else ['one']))
                    timeout=stack.enter_context(patch.object(api,'runpod_yolo_client_timeout_seconds',return_value=7))
                    request=stack.enter_context(patch.object(requests,'request',return_value=self.response(401 if stage=='terminal' else 500,{'error':Detail()})))
                    getter=stack.enter_context(patch.object(service,'request' if stage=='request' else 'bound_text',side_effect=chain([failure],repeat((lambda *a,**kw:self.response(200,{'ok':True})) if stage=='request' else (lambda *a:'valid')))))
                    wrapped=stage=='request' and isinstance(failure,requests.RequestException)
                    with self.assertRaises(BaseException) as error:
                        if stage=='summary':api.runpod_public_response_summary('text')
                        else:api.runpod_yolo_http_request('POST','run')
                    self.assertIs(error.exception.__cause__ if wrapped else error.exception,failure)
                    getter.assert_called_once_with();self.assertEqual(events,[])
                    self.assertEqual(timeout.call_count,int(stage not in ('request','summary')));self.assertEqual(request.call_count,int(stage not in ('request','summary')))


    def test_settings_first_failures_and_internal_exception_boundaries(self):
        api=self.api
        settings=api._training_executor_settings
        cases=[('remote_training_endpoint','validate_remote_training_endpoint',('https://fixture.invalid',),False),
            ('windows_worker_base_url','validate_windows_worker_base_url',('https://fixture.invalid',),False),
            ('runpod_yolo_url','runpod_yolo_endpoint_id',(),False),
            ('runpod_yolo_url','runpod_yolo_api_base',(),False),
            ('runpod_yolo_authorization_values','runpod_yolo_api_key',(),False),
            ('training_execution_status','remote_training_endpoint',(),True),
            ('training_execution_status','training_executor_mode',(),False)]
        for name,seam,args,caught in cases:
            for failure in (RuntimeError('first-only'),OSError('first-only')):
                with self.subTest(name=name,seam=seam,failure=type(failure).__name__),ExitStack() as stack:
                    self.configured();os.environ[api.REMOTE_TRAINING_ENDPOINT_ENV]='https://fixture.invalid';os.environ[api.WINDOWS_WORKER_BASE_URL_ENV]='https://fixture.invalid'
                    probe=stack.enter_context(patch.object(settings,seam,side_effect=chain([failure],repeat('valid'))))
                    if caught and isinstance(failure,RuntimeError):self.assertEqual(getattr(api,name)()['remote_endpoint_error'],'first-only')
                    else:
                        with self.assertRaises(BaseException) as error:getattr(api,name)(*(['run'] if name=='runpod_yolo_url' else []))
                        self.assertIs(error.exception,failure)
                    probe.assert_called_once_with(*args)
        for name in ('training_executor_mode','worker_local_training_fallback_enabled','remote_training_timeout_seconds',
            'windows_worker_timeout_seconds','windows_worker_image_timeout_seconds','windows_worker_headers',
            'runpod_yolo_endpoint_id','runpod_yolo_api_key','runpod_yolo_api_base','runpod_yolo_public_base_url',
            'runpod_yolo_job_timeout_seconds','runpod_yolo_client_timeout_seconds','runpod_yolo_poll_interval_seconds',
            'runpod_yolo_dataset_token_ttl_seconds','runpod_yolo_inline_dataset_max_bytes','runpod_yolo_artifact_max_bytes'):
            with self.subTest(reader=name),patch.object(os.environ,'get',side_effect=chain([OSError('first-only')],repeat('https://fixture.invalid' if name in ('runpod_yolo_api_base','runpod_yolo_public_base_url') else 'valid'))) as probe:
                with self.assertRaises(BaseException) as error:getattr(api,name)()
                self.assertIs(type(error.exception),OSError);self.assertEqual(str(error.exception),'first-only')
                self.assertEqual(probe.call_count,1)

    def test_summary_recursive_first_failures_preserve_input(self):
        api=self.api;service=api._runpod_client
        for kind in ('dict','list','key','slice','items'):
            with self.subTest(kind=kind),ExitStack() as stack:
                failure=OSError('first-only')
                if kind in ('dict','list'):
                    value={'a':'first','b':'later'} if kind=='dict' else ['first','later']
                    original=service.runpod_public_response_summary
                    probe=stack.enter_context(patch.object(service,'runpod_public_response_summary',side_effect=chain([failure],repeat('valid'))))
                    invoke=lambda:original(value)
                elif kind=='key':
                    probe=Mock(side_effect=chain([failure],repeat('ok')))
                    class Key:
                        def __str__(self):return probe()
                    value={Key():'first'};invoke=lambda:api.runpod_public_response_summary(value)
                elif kind=='items':
                    probe=Mock(side_effect=chain([failure],repeat([('a','first'),('b','later')])))
                    class Record(dict):
                        def items(self):return probe()
                    value=Record(a='first',b='later');invoke=lambda:api.runpod_public_response_summary(value)
                else:
                    probe=Mock(side_effect=chain([failure],repeat(['first'])))
                    class Items(list):
                        def __getitem__(self,key):return probe(key)
                    value=Items(['first','later']);invoke=lambda:api.runpod_public_response_summary(value)
                with self.assertRaises(BaseException) as error:invoke()
                self.assertIs(error.exception,failure);self.assertEqual(probe.call_count,1)
                self.assertEqual(len(value),1 if kind=='key' else 2)
                self.request.assert_not_called()


    def test_detail_conversion_first_failure_is_not_retried(self):
        api=self.api
        for terminal in (False,True):
            with self.subTest(terminal=terminal),ExitStack() as stack:
                failure=OSError('first-only');probe=Mock(side_effect=chain([failure],repeat('valid')))
                class Detail:
                    def __str__(self):return probe()
                class ShortAuth:
                    def __iter__(self):return iter(['one'])
                    def __len__(self):return 2
                stack.enter_context(patch.object(api,'runpod_yolo_url',return_value='https://fixture.invalid/run'))
                stack.enter_context(patch.object(api,'runpod_yolo_authorization_values',return_value=ShortAuth() if terminal else ['one']))
                stack.enter_context(patch.object(api,'runpod_yolo_client_timeout_seconds',return_value=7))
                transport=stack.enter_context(patch.object(requests,'request',return_value=self.response(401 if terminal else 500,{'error':Detail()})))
                bound=stack.enter_context(patch.object(api,'bounded_text',return_value='valid'))
                with self.assertRaises(BaseException) as error:api.runpod_yolo_http_request('POST','run')
                self.assertIs(error.exception,failure);probe.assert_called_once_with();transport.assert_called_once();bound.assert_not_called()

    def test_status_mask_and_environment_getter_first_failures(self):
        api=self.api
        for stage in ('mask','environment'):
            with self.subTest(stage=stage),ExitStack() as stack:
                failure=OSError('first-only')
                if stage=='mask':
                    self.configured();os.environ[api.REMOTE_TRAINING_ENDPOINT_ENV]='https://fixture.invalid'
                    probe=stack.enter_context(patch.object(api,'masked_url_for_status',side_effect=chain([failure],repeat('valid'))))
                    invoke=api.training_execution_status
                else:
                    probe=stack.enter_context(patch.object(api._training_executor_settings,'environment',side_effect=chain([failure],repeat({}))))
                    invoke=api.training_executor_mode
                with self.assertRaises(BaseException) as error:invoke()
                self.assertIs(error.exception,failure);self.assertEqual(probe.call_count,1);self.request.assert_not_called()

if __name__=='__main__':unittest.main()

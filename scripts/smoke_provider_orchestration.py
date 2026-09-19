"""Offline baseline of provider selection and existing retry orchestration."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path.cwd()))

def capture_provider_orchestration_window(api, Fixture, site, mode='ordinary'):
    from contextlib import ExitStack, nullcontext
    from types import SimpleNamespace
    from unittest.mock import patch
    f=Fixture();f.setUp();events=[];calls=[]
    try:
        with patch.dict(api.__dict__),ExitStack() as stack:
            caught=None;result=None;expected_error=None;expected=None
            def install(owner,name,action):
                def callback(label):
                    def invoke(*args,**kwargs):events.append(label);return action(*args,**kwargs)
                    return invoke
                callbacks=[callback(label) for label in 'ABC'];stack.enter_context(patch.object(owner,name,callbacks[0]))
                def prior():events.append('prior');setattr(owner,name,callbacks[1] if mode=='prior' else None if mode=='missing' else callbacks[0])
                def argument():events.append('argument');setattr(owner,name,callbacks[2])
                return prior,argument
            if site=='current_factory':
                expected=object();prior,argument=install(api,'ai_provider_from_settings',lambda settings:expected)
                def settings():argument();return dict(f.settings)
                api.ai_detection_settings=settings;prior();invoke=api.ai_provider
            elif site in ('json_config','image_config'):
                original=api.AiProviderConfigError;expected_error=original;prior,argument=install(api,'AiProviderConfigError',original)
                class ProviderName:
                    def __str__(self):prior();return 'invalid'
                class Settings(dict):
                    def get(self,key,*args):
                        if key=='message':argument()
                        return super().get(key,*args)
                settings=Settings(provider=ProviderName(),message='synthetic capture error');factory=api.ai_provider_from_settings if site=='json_config' else api.image_generation_provider_from_settings;invoke=lambda:factory(settings)
            elif site in ('key_identify','key_text'):
                if site=='key_identify':
                    prior,argument=install(api,'secret_key_item_id',lambda env,key:'identified')
                    class Candidate(dict):
                        env_reads=0
                        def get(self,key,*args):
                            if key=='id':prior()
                            if key=='env':
                                self.env_reads+=1
                                if self.env_reads==1:argument()
                            return super().get(key,*args)
                    candidate=Candidate(key='synthetic-key',id='',env='ENV',label='label')
                else:
                    prior,argument=install(api,'bounded_text',lambda value,limit:'bounded')
                    class Identifier:
                        def __str__(self):prior();return 'id'
                    class Candidate(dict):
                        def get(self,key,*args):
                            if key=='label':argument()
                            return super().get(key,*args)
                    candidate=Candidate(key='synthetic-key',id=Identifier(),label='',env='ENV')
                settings={**f.settings,'api_key':'','api_key_candidates':[candidate]};invoke=lambda:api.ai_provider_key_candidates(settings)
            elif site=='json_rotate':
                prior,argument=install(api,'rotate_ai_provider_key',lambda settings,used:None)
                class Settings(dict):
                    def get(self,key,*args):
                        if key=='model':argument()
                        return super().get(key,*args)
                settings=Settings(f.settings,model='')
                def generate(*args,**kwargs):
                    calls.append('generate')
                    if len(calls)==1:raise api.AiProviderTimeout('timeout')
                    return {'ok':True},7
                provider=SimpleNamespace(generate_json=generate,last_usage_metadata={});api.ai_settings_match_runtime=lambda settings:False;api.ai_provider_from_settings=lambda settings:provider
                def repair(exc):prior();return False
                api.provider_error_needs_repair_prompt=repair;invoke=lambda:api.generate_provider_json_with_fallback(settings,'s',[],max_tokens=1)
            elif site=='image_sleep':
                original_sleep=f.sleep;prior,argument=install(api.time,'sleep',lambda delay:original_sleep(delay))
                def generate(*args,**kwargs):
                    calls.append('generate')
                    if len(calls)==1:raise api.AiProviderTimeout('timeout')
                    return {'bytes':b'image'}
                provider=SimpleNamespace(generate_image=generate);api.image_generation_provider_from_settings=lambda settings:provider;api._auto_optimize_image_request_semaphore=nullcontext()
                def now():prior();return 123.0
                def delay(*args):argument();return 2.0
                stack.enter_context(patch.object(api.time,'time',now));api.auto_optimize_retry_delay_seconds=delay;invoke=lambda:api.auto_optimize_generate_image_with_retry(f.settings,'m','p',[])
            else:raise AssertionError(site)
            try:result=invoke()
            except BaseException as exc:caught=exc
            assert events.count('prior')==events.count('argument')==1,(site,mode,events,caught)
            assert events.index('prior')<events.index('argument'),events
            labels=[event for event in events if event in ('A','B','C')]
            if mode=='missing':
                assert type(caught) is TypeError,(site,mode,caught,events)
                assert labels==[],events
            else:
                assert labels==['B' if mode=='prior' else 'A'],(site,mode,events,caught)
                if expected_error:
                    assert type(caught) is expected_error and str(caught)=='synthetic capture error',(caught,events)
                else:
                    assert caught is None,(site,mode,caught,events)
                    if site=='current_factory':assert result is expected
                    elif site=='key_identify':assert result[0]['id']=='identified'
                    elif site=='key_text':assert result[0]['label']=='bounded'
                    elif site=='json_rotate':assert result[0]=={'ok':True} and result[2]['attempts']==2
                    elif site=='image_sleep':assert result['bytes']==b'image' and result['attempts']==2
            if site in ('json_rotate','image_sleep'):assert len(calls)==(1 if mode=='missing' else 2),calls
            return {'events':events,'error':type(caught).__name__ if caught else None,'generate_calls':len(calls),'sleep_calls':f.sleep.call_count}
    finally:f.doCleanups()


def capture_provider_orchestration_refresh(api, Fixture, site):
    from types import SimpleNamespace
    from unittest.mock import patch
    f=Fixture();f.setUp();events=[];calls=[]
    try:
        with patch.dict(api.__dict__),patch.object(api.time,'time',return_value=123.0):
            if site=='json_factory':
                def generate_a(*args,**kwargs):
                    calls.append('generateA')
                    if len(calls)==1:api.ai_provider_from_settings=factory_b;raise api.AiProviderError('invalid JSON')
                    return {'from':'A'},7
                def generate_b(*args,**kwargs):calls.append('generateB');return {'from':'B'},7
                a=SimpleNamespace(generate_json=generate_a,last_usage_metadata={});b=SimpleNamespace(generate_json=generate_b,last_usage_metadata={})
                def factory_a(settings):events.append('A');return a
                def factory_b(settings):events.append('B');return b
                api.ai_provider_from_settings=factory_a;api.ai_settings_match_runtime=lambda settings:False
                result=api.generate_provider_json_with_fallback(f.settings,'s',[],max_tokens=1)
                assert result[0]=={'from':'B'} and result[2]['attempts']==2,(result,events,calls)
                assert events==['A','B'] and calls==['generateA','generateB'],(events,calls)
            elif site=='image_gate':
                class Gate:
                    def __init__(self,label):self.label=label
                    def __enter__(self):events.append(self.label+'enter')
                    def __exit__(self,*args):events.append(self.label+'exit')
                def generate(*args,**kwargs):
                    calls.append('generate')
                    if len(calls)==1:api._auto_optimize_image_request_semaphore=Gate('B');raise api.AiProviderTimeout('timeout')
                    return {'bytes':b'image'}
                provider=SimpleNamespace(generate_image=generate);api.image_generation_provider_from_settings=lambda settings:provider;api._auto_optimize_image_request_semaphore=Gate('A');api.auto_optimize_retry_delay_seconds=lambda *args:0.0
                result=api.auto_optimize_generate_image_with_retry(f.settings,'m','p',[])
                assert result['bytes']==b'image' and result['attempts']==2,(result,events,calls)
                assert events==['Aenter','Aexit','Benter','Bexit'] and calls==['generate','generate'],(events,calls)
            else:raise AssertionError(site)
            f.sleep.assert_called_once()
            return {'events':events,'calls':calls,'sleep_calls':f.sleep.call_count}
    finally:f.doCleanups()


class ProviderOrchestrationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env=patch.dict(os.environ);cls.env.start();cls.tmp=tempfile.TemporaryDirectory(prefix='provider-flow-')
        root=Path(cls.tmp.name);(root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup();cls.env.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for target in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):
            self.stack.enter_context(patch(target,side_effect=AssertionError('external operation forbidden')))
        self.sleep=self.stack.enter_context(patch.object(self.api.time,'sleep'))
        self.uniform=self.stack.enter_context(patch.object(self.api.random,'uniform',return_value=0.2))
        self.stack.enter_context(patch.object(self.api,'AI_PROVIDER_MAX_ATTEMPTS',3))
        self.stack.enter_context(patch.object(self.api,'AI_PROVIDER_RETRY_BACKOFF_SECONDS',1.0))
        self.stack.enter_context(patch.object(self.api,'AUTO_OPTIMIZE_MASK_MAX_ATTEMPTS',3))
        self.settings=dict(provider='openai_compatible',model='synthetic',api_key='synthetic-key',base_url='https://fixture.invalid',timeout_seconds=5,proxy_url_raw='')
    def provider(self,gemini=False,usage=None):
        cls=self.api.GeminiAiProvider if gemini else self.api.OpenAICompatibleAiProvider
        p=cls(dict(self.settings));p.last_usage_metadata=usage or {};p.generate_json=Mock(return_value=({'ok':True},7))
        return p
    def flow(self,provider,settings=None,**kwargs):
        with patch.object(self.api,'ai_settings_match_runtime',return_value=False),patch.object(self.api,'ai_provider_from_settings',return_value=provider):
            return self.api.generate_provider_json_with_fallback(settings or self.settings,'system',[{'type':'text','text':'task'}],max_tokens=123,**kwargs)
    def test_provider_factories_and_setting_identity(self):
        for name,cls in [('gemini',self.api.GeminiAiProvider),('qwen',self.api.OpenAICompatibleAiProvider),('doubao',self.api.OpenAICompatibleAiProvider),('openai_compatible',self.api.OpenAICompatibleAiProvider)]:
            settings={**self.settings,'provider':name};p=self.api.ai_provider_from_settings(settings)
            self.assertIs(type(p),cls);self.assertIs(p.settings,settings)
        for name,cls in [('gemini',self.api.GeminiAiProvider),('agnes',self.api.AgnesImageProvider),('qwen_image',self.api.QwenImageProvider)]:
            settings={**self.settings,'provider':name};p=self.api.image_generation_provider_from_settings(settings)
            self.assertIs(type(p),cls);self.assertIs(p.settings,settings)
        for fn in (self.api.ai_provider_from_settings,self.api.image_generation_provider_from_settings):
            with self.assertRaises(self.api.AiProviderConfigError) as caught:fn({'provider':'invalid','message':'synthetic reason'})
            self.assertEqual(str(caught.exception),'synthetic reason')
    def test_runtime_selection_and_bound_settings(self):
        runtime=Mock(return_value=dict(self.settings))
        with patch.object(self.api,'ai_detection_settings',runtime):
            self.assertFalse(self.api.ai_settings_match_runtime({**self.settings,'profile_id':'bound'}));runtime.assert_not_called()
            self.assertTrue(self.api.ai_settings_match_runtime(dict(self.settings)))
            for key in ('provider','model','base_url','api_key','timeout_seconds','proxy_url_raw'):
                self.assertFalse(self.api.ai_settings_match_runtime({**self.settings,key:'different'}))
            p=self.api.ai_provider();self.assertIs(type(p),self.api.OpenAICompatibleAiProvider)
    def test_key_candidates_order_deduplication_and_rotation(self):
        settings={**self.settings,'active_key_id':'one','key_source_name':'ENV_ONE','api_key_candidates':[{'id':'duplicate','key':'synthetic-key'},{'id':'wrong','key':'wrong-provider-key','provider':'gemini'},None,{'id':'two','key':' second-key ','label':'second'},{'id':'three','key':'third-key','env':'ENV_THREE'}]}
        before=copy.deepcopy(settings);c=self.api.ai_provider_key_candidates(settings)
        self.assertEqual([x['id'] for x in c],['one','two','three']);self.assertEqual(c[1],{'id':'two','label':'second','env':'','provider':'openai_compatible','key':'second-key'})
        r=self.api.rotate_ai_provider_key(settings,{'one'})
        self.assertEqual({k:r[k] for k in ('api_key','active_key_id','key_source','key_source_name')},{'api_key':'second-key','active_key_id':'two','key_source':'env','key_source_name':'second'})
        self.assertIsNone(self.api.rotate_ai_provider_key(settings,{'one','two','three'}));self.assertEqual(settings,before)
    def test_json_shape_and_repair_policy(self):
        value={'ok':1};self.assertIs(self.api.require_ai_json_object(value),value)
        for value in ([],None,'text'):
            with self.assertRaises(self.api.AiProviderError) as caught:self.api.require_ai_json_object(value)
            self.assertEqual(str(caught.exception),'AI provider returned non-object JSON')
        for text,expected in [('invalid JSON',True),('response shape missing',True),('non-object',True),('timed out',False)]:
            self.assertIs(self.api.provider_error_needs_repair_prompt(self.api.AiProviderError(text)),expected)
    def test_retry_policy_matrix(self):
        for error,json_retry,image_retry in [(self.api.AiProviderNonRetryableError('timeout'),False,False),(self.api.AiProviderOverloaded('busy',http_status=429),False,True),(self.api.AiProviderOverloaded('busy',http_status=503),True,True),(self.api.AiProviderTimeout('timeout'),True,True),(self.api.AiProviderError('HTTP 400 bad'),False,False),(self.api.AiProviderError('malformed JSON'),True,False),(self.api.AiProviderError('connection reset'),True,True),(self.api.AiProviderError('bad',http_status=500),True,True)]:
            with self.subTest(error=error):
                self.assertIs(self.api.provider_error_is_retryable(error),json_retry);self.assertIs(self.api.image_provider_error_is_retryable(error),image_retry)
    def test_image_retry_delay_policy(self):
        with patch.object(self.api,'AUTO_OPTIMIZE_MASK_RETRY_BASE_SECONDS',2),patch.object(self.api,'AUTO_OPTIMIZE_MASK_RETRY_MAX_SECONDS',10):
            self.assertEqual(self.api.auto_optimize_retry_delay_seconds(1),2.2)
            self.assertEqual(self.api.auto_optimize_retry_delay_seconds(4),10.2)
            self.assertEqual(self.api.auto_optimize_retry_delay_seconds(2,self.api.AiProviderOverloaded('busy',http_status=503)),3.0)
            with patch.object(self.api,'AUTO_OPTIMIZE_MASK_MAX_ATTEMPTS',1):self.assertEqual(self.api.auto_optimize_retry_delay_seconds(2),0.0)
            with patch.object(self.api,'AUTO_OPTIMIZE_MASK_RETRY_BASE_SECONDS',0):self.assertEqual(self.api.auto_optimize_retry_delay_seconds(2),0.0)
    def test_json_success_usage_and_cached_content_branch(self):
        for gemini in (False,True):
            with self.subTest(gemini=gemini):
                p=self.provider(gemini,{'tokens':9});result=self.flow(p,cached_content='cached/synthetic')
                self.assertEqual(result,({'ok':True},7,{'attempts':1,'retry_count':0,'usage_metadata':{'tokens':9}}))
                self.assertEqual(p.generate_json.call_args.kwargs,{'max_tokens':123,**({'cached_content':'cached/synthetic'} if gemini else {})})
        self.sleep.assert_not_called()
    def test_runtime_factory_is_used_only_for_matching_settings(self):
        p=self.provider()
        with patch.object(self.api,'ai_settings_match_runtime',return_value=True),patch.object(self.api,'ai_provider',return_value=p) as live,patch.object(self.api,'ai_provider_from_settings') as frozen:
            result=self.api.generate_provider_json_with_fallback(self.settings,'s',[],max_tokens=1)
        self.assertEqual(result[0],{'ok':True});live.assert_called_once_with();frozen.assert_not_called()
    def test_json_repair_prompt_and_backoff(self):
        p=self.provider();error=self.api.AiProviderError('invalid JSON');p.generate_json.side_effect=[error,({'ok':True},9)]
        with patch.object(self.api,'rotate_ai_provider_key') as rotate:result=self.flow(p)
        self.assertEqual(p.generate_json.call_count,2);self.assertEqual(result[1],9)
        self.assertEqual(result[2],{'attempts':2,'retry_count':1,'previous_errors':['invalid JSON']})
        first,second=[c.args[1] for c in p.generate_json.call_args_list]
        self.assertEqual(first,[{'type':'text','text':'task'}]);self.assertEqual(second[:-1],first)
        self.assertEqual(second[-1],{'type':'text','text':'RETRY_REPAIR: the previous provider response was not a valid JSON object. Return only the compact JSON object matching the schema; no markdown, prose, or code fences.'})
        rotate.assert_not_called();self.sleep.assert_called_once_with(1.2)
    def test_json_max_attempts_and_terminal_failure_metadata(self):
        for maximum,count in [(0,1),(1,1),(2,2),(10,3)]:
            with self.subTest(maximum=maximum):
                self.sleep.reset_mock();p=self.provider();error=self.api.AiProviderError('malformed JSON');p.generate_json.side_effect=error
                caught=None
                try:self.flow(p,max_attempts=maximum)
                except BaseException as exc:caught=exc
                self.assertIs(caught,error);self.assertEqual(p.generate_json.call_count,count);self.assertEqual(error.attempts,count);self.assertEqual(error.retry_count,count-1)
                self.assertEqual(error.previous_errors,['malformed JSON']*min(count,2));self.assertEqual(self.sleep.call_count,count-1)
    def test_gemini_fallback_protection_for_bound_cached_or_disabled(self):
        for bound,cached,allowed,expected in [(False,'',True,'gemini-2.5-flash-lite'),(True,'',True,'synthetic'),(False,'cached',True,'synthetic'),(False,'',False,'synthetic')]:
            with self.subTest(bound=bound,cached=cached,allowed=allowed):
                settings={**self.settings,'provider':'gemini',**({'profile_id':'bound'} if bound else {})};p=self.provider(True);p.generate_json.side_effect=[self.api.AiProviderOverloaded('HTTP 503',http_status=503),({'ok':True},1)]
                with patch.object(self.api,'ai_settings_match_runtime',return_value=False),patch.object(self.api,'ai_provider_from_settings',return_value=p) as factory,patch.object(self.api,'rotate_ai_provider_key',return_value=None):
                    result=self.api.generate_provider_json_with_fallback(settings,'s',[],max_tokens=1,cached_content=cached,allow_overloaded_model_fallback=allowed)
                self.assertEqual(factory.call_args_list[1].args[0]['model'],expected)
                self.assertEqual(result[2].get('fallback_model'),expected if expected!='synthetic' else None)
                self.assertEqual(settings['model'],'synthetic')
    def test_json_key_rotation_and_explicit_overload_delay(self):
        p=self.provider();p.generate_json.side_effect=[self.api.AiProviderTimeout('timeout'),({'ok':True},1)]
        settings={**self.settings,'active_key_id':'one'};rotated={**settings,'active_key_id':'two','api_key':'second','key_source_name':'SECOND'}
        with patch.object(self.api,'rotate_ai_provider_key',return_value=rotated) as rotate:result=self.flow(p,settings)
        self.assertEqual(result[2]['provider_key_id'],'two');self.assertEqual(result[2]['fallback_key_id'],'two');self.assertEqual(result[2]['fallback_key_label'],'SECOND')
        self.assertEqual(rotate.call_args.args[1],{'one','two'})
        self.sleep.reset_mock();p.generate_json.side_effect=[self.api.AiProviderOverloaded('HTTP 503',http_status=503),({'ok':True},1)]
        with patch.object(self.api,'rotate_ai_provider_key') as rotate:self.flow(p,overloaded_retry_delay_seconds=-1)
        self.sleep.assert_called_once_with(0.0);rotate.assert_not_called()
    def test_failure_usage_and_annotation_retained(self):
        p=self.provider(True,{'used':2});error=self.api.AiProviderError('failure',usage_metadata={'original':1})
        self.assertEqual(self.api.provider_failure_usage_metadata(p,error),{'used':2});self.assertEqual(self.api.provider_failure_usage_metadata(None,error),{'original':1})
        self.assertIs(self.api.annotate_provider_failure(error,attempt=3,errors=['a','b','c'],failed_usage_metadata=[{'failed':1}],usage_metadata={'new':1},fallback_model='fallback',fallback_reason='busy'),error)
        self.assertEqual((error.usage_metadata,error.failed_usage_metadata,error.attempts,error.retry_count,error.previous_errors,error.fallback_model,error.fallback_reason),({'original':1},[{'failed':1}],3,2,['b','c'],'fallback','busy'))
    def test_image_retry_preserves_semaphore_and_failure_evidence(self):
        p=SimpleNamespace(generate_image=Mock(side_effect=[self.api.AiProviderTimeout('timeout'),{'bytes':b'image'}]));events=[]
        class Gate:
            def __enter__(inner):events.append('enter')
            def __exit__(inner,*args):events.append('exit')
        with patch.object(self.api,'image_generation_provider_from_settings',return_value=p) as factory,patch.object(self.api,'_auto_optimize_image_request_semaphore',Gate()),patch.object(self.api,'auto_optimize_retry_delay_seconds',return_value=3),patch.object(self.api.time,'time',return_value=123):
            result=self.api.auto_optimize_generate_image_with_retry(self.settings,'m','p',[],system_prompt='s')
        self.assertEqual(events,['enter','exit','enter','exit']);self.assertEqual(factory.call_count,2)
        self.assertEqual(result,{'bytes':b'image','attempts':2,'retry_count':1,'previous_errors':[{'attempt':1,'http_status':None,'retryable':True,'message':'timeout','created_at':123}]})
        self.sleep.assert_called_once_with(3)
    def test_image_terminal_failure_is_same_exception_and_no_extra_call(self):
        for retryable,count in [(True,3),(False,1)]:
            with self.subTest(retryable=retryable):
                self.sleep.reset_mock();error=self.api.AiProviderTimeout('timeout') if retryable else self.api.AiProviderNonRetryableError('unknown result');p=SimpleNamespace(generate_image=Mock(side_effect=error));caught=None
                with patch.object(self.api,'image_generation_provider_from_settings',return_value=p),patch.object(self.api,'auto_optimize_retry_delay_seconds',return_value=0):
                    try:self.api.auto_optimize_generate_image_with_retry(self.settings,'m','p',[])
                    except BaseException as exc:caught=exc
                self.assertIs(caught,error);self.assertEqual(p.generate_image.call_count,count);self.assertEqual((error.attempts,error.retry_count),(count,count-1));self.assertEqual(self.sleep.call_count,count-1)
    def test_detection_adapter_uses_existing_system_prompt(self):
        with patch.object(self.api,'generate_provider_json_with_fallback',return_value=({'ok':True},1,{})) as flow:
            content=[];self.assertEqual(self.api.generate_ai_detection_json(self.settings,content,max_tokens=9),({'ok':True},1,{}))
        flow.assert_called_once_with(self.settings,self.api.AI_DETECTION_SYSTEM_PROMPT,content,max_tokens=9)


    def test_image_gate_failures_do_not_repeat_generation(self):
        for site in ('enter','exit'):
            with self.subTest(site=site):
                error=RuntimeError('synthetic gate failure');events=[];p=SimpleNamespace(generate_image=Mock(return_value={'bytes':b'image'}));caught=None
                class Gate:
                    def __enter__(inner):
                        events.append('enter')
                        if site=='enter' and events.count('enter')==1:raise error
                    def __exit__(inner,*args):
                        events.append('exit')
                        if site=='exit' and events.count('exit')==1:raise error
                with patch.object(self.api,'image_generation_provider_from_settings',return_value=p) as factory,patch.object(self.api,'_auto_optimize_image_request_semaphore',Gate()):
                    try:self.api.auto_optimize_generate_image_with_retry(self.settings,'m','p',[])
                    except BaseException as exc:caught=exc
                self.assertIs(caught,error);factory.assert_called_once();self.assertEqual(p.generate_image.call_count,0 if site=='enter' else 1)
                self.assertEqual(events,['enter'] if site=='enter' else ['enter','exit'])
        self.sleep.assert_not_called()

    def test_json_boundary_first_failure_has_infinite_valid_recovery(self):
        sites=('ai_settings_match_runtime','ai_provider_from_settings','require_ai_json_object','provider_failure_usage_metadata','annotate_provider_failure')
        for site in sites:
            with self.subTest(site=site):
                p=self.provider();error=RuntimeError('synthetic callback failure');upstream=self.api.AiProviderNonRetryableError('unknown result');hits=[];caught=None
                if site in ('provider_failure_usage_metadata','annotate_provider_failure'):p.generate_json.side_effect=upstream
                valid={'ai_settings_match_runtime':lambda *a:False,'ai_provider_from_settings':lambda *a:p,'require_ai_json_object':lambda value:value,'provider_failure_usage_metadata':lambda *a:{},'annotate_provider_failure':lambda exc,**kw:exc}
                def callback(*args,**kwargs):
                    hits.append(1)
                    if len(hits)==1:raise error
                    return valid[site](*args,**kwargs)
                with patch.object(self.api,'ai_settings_match_runtime',return_value=False),patch.object(self.api,'ai_provider_from_settings',return_value=p),patch.object(self.api,site,side_effect=callback):
                    try:self.api.generate_provider_json_with_fallback(self.settings,'s',[],max_tokens=1)
                    except BaseException as exc:caught=exc
                self.assertIs(caught,error);self.assertEqual(hits,[1]);self.assertEqual(p.generate_json.call_count,0 if site in sites[:2] else 1)
                self.sleep.assert_not_called()

    def test_json_exception_match_is_resolved_after_provider_failure(self):
        original=self.api.AiProviderError
        for mode in ('same','other','missing'):
            with self.subTest(mode=mode),patch.object(self.api,'AiProviderError',original):
                p=self.provider();error=original('non-object JSON');calls=[];caught=None;result=None
                replacement=original if mode=='same' else type('Other',(Exception,),{}) if mode=='other' else None
                def generate(*args,**kwargs):
                    calls.append(1)
                    if len(calls)==1:self.api.AiProviderError=replacement;raise error
                    return {'ok':True},1
                p.generate_json.side_effect=generate
                try:result=self.flow(p)
                except BaseException as exc:caught=exc
                self.assertEqual(len(calls),2 if mode=='same' else 1)
                if mode=='same':self.assertIsNone(caught);self.assertEqual(result[0],{'ok':True})
                elif mode=='other':self.assertIs(caught,error)
                else:self.assertIs(type(caught),TypeError);self.assertIs(caught.__context__,error)

    def test_json_failed_usage_is_preserved_when_later_attempt_succeeds(self):
        p=self.provider(True);calls=[]
        def generate(*args,**kwargs):
            calls.append(1);p.last_usage_metadata={'attempt':len(calls)}
            if len(calls)==1:raise self.api.AiProviderTimeout('timeout')
            return {'ok':True},11
        p.generate_json.side_effect=generate
        with patch.object(self.api,'rotate_ai_provider_key',return_value=None):result=self.flow(p)
        self.assertEqual(result,({'ok':True},11,{'attempts':2,'retry_count':1,'usage_metadata':{'attempt':2},'failed_usage_metadata':[{'attempt':1}],'previous_errors':['timeout']}))
        self.assertEqual(calls,[1,1])


    def test_independent_constructors_do_not_read_dependencies(self):
        from dataclasses import fields
        from local_inspection_service.model_providers.orchestration_ports import ProviderFactories,ProviderKeys,RetryErrors,ImageDelay,FailureEvidence,JsonProviderSelection,JsonRetryEvidence,JsonRetryTiming,ImageRetryCalls,ImageRetryTiming
        from local_inspection_service.model_providers.selection import ProviderSelection,ProviderKeySelection
        from local_inspection_service.model_providers.retry_policy import ProviderRetryPolicy,ProviderFailureEvidence
        from local_inspection_service.model_providers.retry_flow import JsonRetryFlow,ImageRetryFlow
        forbidden=Mock(side_effect=AssertionError('constructor dependency read'))
        def port(cls):return cls(*([forbidden]*len(fields(cls))))
        services=[ProviderSelection(port(ProviderFactories)),ProviderKeySelection(port(ProviderKeys)),ProviderRetryPolicy(port(RetryErrors),port(ImageDelay)),ProviderFailureEvidence(port(FailureEvidence)),JsonRetryFlow(port(JsonProviderSelection),port(JsonRetryEvidence),port(RetryErrors),port(JsonRetryTiming)),ImageRetryFlow(port(ImageRetryCalls),port(RetryErrors),port(ImageRetryTiming))]
        self.assertEqual(len(services),6);forbidden.assert_not_called()

    def test_independent_json_flows_keep_factories_and_evidence_separate(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from local_inspection_service.model_providers.orchestration_ports import JsonProviderSelection,JsonRetryEvidence,RetryErrors,JsonRetryTiming
        from local_inspection_service.model_providers.retry_flow import JsonRetryFlow
        barrier=Barrier(2);services=[];histories=[];forbidden=Mock(side_effect=AssertionError('unexpected global or fallback'))
        for index in range(2):
            history=[];histories.append(history)
            class Provider:
                def __init__(inner,settings,index=index,history=history):inner.settings=settings;inner.index=index;inner.history=history;inner.last_usage_metadata={}
                def generate_json(inner,system_prompt,user_content,**kwargs):
                    barrier.wait(timeout=5);inner.history.append(dict(inner.settings));inner.last_usage_metadata={'instance':inner.index}
                    return {'instance':inner.index},1
            factory=lambda settings,cls=Provider:cls(settings)
            providers=JsonProviderSelection(lambda:lambda settings:False,lambda:forbidden,lambda factory=factory:factory,lambda cls=Provider:cls,lambda:forbidden)
            evidence=JsonRetryEvidence(lambda:lambda value:value,lambda:forbidden,lambda:forbidden,lambda:forbidden,lambda:forbidden,lambda:forbidden)
            errors=RetryErrors(lambda:self.api.AiProviderError,lambda:self.api.AiProviderNonRetryableError,lambda:self.api.AiProviderOverloaded,lambda:self.api.AiProviderTimeout)
            services.append(JsonRetryFlow(providers,evidence,errors,JsonRetryTiming(lambda:1,lambda:0,lambda:forbidden,lambda:forbidden)))
        with patch.object(self.api,'ai_provider_from_settings',forbidden),ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(service.generate_provider_json_with_fallback,{'instance':i},'s',[],max_tokens=1) for i,service in enumerate(services)]
            results=[future.result(timeout=10) for future in futures]
        self.assertEqual(results,[({'instance':i},1,{'attempts':1,'retry_count':0,'usage_metadata':{'instance':i}}) for i in range(2)])
        self.assertEqual(histories,[[{'instance':0}],[{'instance':1}]]);forbidden.assert_not_called()


    def test_original_dependency_capture_windows(self):
        for site in ('current_factory','json_config','image_config','key_identify','key_text','json_rotate','image_sleep'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(site=site,mode=mode):capture_provider_orchestration_window(self.api,type(self),site,mode)

    def test_original_callbacks_refresh_across_attempts(self):
        for site in ('json_factory','image_gate'):
            with self.subTest(site=site):capture_provider_orchestration_refresh(self.api,type(self),site)

if __name__=='__main__':unittest.main()

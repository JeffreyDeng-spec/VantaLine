"""Offline presence inspection orchestration contracts; no inference or device access."""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import itertools
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def capture_presence_window(api, Fixture, stage, mode):
    from contextlib import ExitStack
    from unittest.mock import Mock, patch
    with ExitStack() as stack:
        stack.enter_context(patch.dict(api.__dict__))
        f=Fixture();f.bind(api,stack);payload=f.payload();events=[]
        names={'resolve':'resolve_required_accessory_refs','disabled':'ai_presence_failure_payload','path':'image_path_data_url','path_failure':'ai_presence_failure_payload','image':'image_bgr_data_url','missing_image':'ai_presence_failure_payload','call1':'call_ai_mcp_tool','call2':'call_ai_mcp_tool','covers1':'ai_detection_parsed_covers_required','covers2':'ai_detection_parsed_covers_required','failure':'ai_presence_failure_payload','normalize':'normalize_ai_detection_result'}
        name=names[stage]
        value=f.required if stage=='resolve' else 'data:encoded' if stage in ('path','image') else f.response if stage.startswith('call') else True if stage.startswith('covers') else f.result if stage=='normalize' else f.failure
        b=Mock(side_effect=lambda *a,**k:events.append('B') or value);c=Mock(side_effect=AssertionError('late callback C used'))
        a=Mock(side_effect=AssertionError('entry callback A used'))
        def prior():events.append('prior');setattr(api,name,None if mode=='missing' else b)
        def argument():events.append('arg');setattr(api,name,c)
        setattr(api,name,b if mode=='ordinary' else a)
        if stage=='resolve':
            class Payload(dict):
                def get(self,key,default=None):
                    if key=='required_accessories' and mode!='ordinary':prior()
                    if key=='required_accessory_refs':argument()
                    return super().get(key,default)
            payload=Payload(payload);payload['required_accessories']=[];payload['required_accessory_refs']=['a']
        elif stage=='disabled':
            class Message:
                def __bool__(self):argument();return True
            f.settings.update(configured=False,message=Message());original=f.clock.side_effect
            def clock():
                result=original()
                if f.clock.call_count==2 and mode!='ordinary':prior()
                return result
            f.clock.side_effect=clock
        elif stage in ('path','image','missing_image'):
            class Payload(dict):
                def get(self,key,default=None):
                    if key==('inspection_image_path' if stage=='path' else 'inspection_image_bgr') and mode!='ordinary':prior()
                    return super().get(key,default)
            payload=Payload(payload);payload['inspection_image_data_url']='';payload['inspection_image_path']='source.png' if stage=='path' else '';payload['inspection_image_bgr']=None if stage=='missing_image' else f.image
        elif stage=='path_failure':
            payload.update(inspection_image_data_url='',inspection_image_path='source.png')
            def path(*a,**k):
                if mode!='ordinary':prior()
                return None
            f.path.side_effect=path
        elif stage=='call1':
            def tokens(*a,**k):
                if mode!='ordinary':prior()
                return 128
            f.tokens.side_effect=tokens
        elif stage=='call2':
            api.call_ai_mcp_tool=f.tool;f.settings['provider']='qwen'
            def covered(*a,**k):
                if f.covers.call_count==1:
                    prior();return False
                return True
            f.covers.side_effect=covered
        elif stage.startswith('covers'):
            f.settings['provider']='qwen'
            class Response(dict):
                def get(self,key,default=None):
                    if key=='ok' and mode!='ordinary':prior()
                    if key=='parsed':argument()
                    return super().get(key,default)
            response=Response(ok=True,parsed=f.parsed,latency_ms=31)
            if stage=='covers1':f.response=response
            else:
                api.ai_detection_parsed_covers_required=f.covers;f.covers.side_effect=lambda *a,**k:False
                f.tool.side_effect=lambda *a,**k:f.response if f.tool.call_count==1 else response
        elif stage in ('failure','normalize'):
            original=f.clock.side_effect
            def clock():
                result=original()
                if f.clock.call_count==6 and mode!='ordinary':prior()
                return result
            f.clock.side_effect=clock
            class Response(dict):
                def get(self,key,default=None):
                    if key==('error' if stage=='failure' else 'parsed'):argument()
                    return super().get(key,default)
            f.response=Response(f.response);f.response['ok']=stage=='normalize';f.response['error']='fail'
        captured=None
        try:result=api.tool_vision_inspect_presence(payload)
        except BaseException as exc:captured=exc
        effect=stage in ('resolve','disabled','covers1','covers2','failure','normalize')
        if mode=='missing':assert type(captured) is TypeError,(stage,mode,captured,events)
        else:assert captured is None,(stage,mode,captured,events)
        assert b.call_count==(0 if mode=='missing' else 1),(stage,mode,b.call_count,events)
        assert not c.called and not a.called,(stage,mode,'wrong callee',events)
        assert ('prior' in events)==(mode!='ordinary'),(stage,mode,events)
        if effect:
            assert 'arg' in events,(stage,mode,events)
            if mode!='missing':assert events.index('arg')<events.index('B'),(stage,mode,events)
        if stage=='call2':assert f.tool.call_count==1,(stage,f.tool.call_count)
        if stage=='covers2':assert f.covers.call_count==1,(stage,f.covers.call_count)
        return events

def capture_presence_budget_refresh(api, Fixture):
    from contextlib import ExitStack
    from unittest.mock import patch
    with ExitStack() as stack:
        stack.enter_context(patch.dict(api.__dict__))
        f=Fixture();f.bind(api,stack);events=[];f.cache['provider_call_count']=1
        class Budget(int):
            def __sub__(self,other):events.append(('subtract',other));api.AI_PROVIDER_MAX_ATTEMPTS=9;return int(self)-other
        api.AI_PROVIDER_MAX_ATTEMPTS=Budget(3)
        result=api.tool_vision_inspect_presence(f.payload())
        assert events==[('subtract',1)],events
        assert f.cache['generate_attempt_budget']==2 and f.cache['provider_call_budget']==9,f.cache
        assert f.tool.call_args.args[1]['max_attempts']==2
        assert result['ai']['profile_cache']['provider_call_budget']==9
        return events

def capture_presence_encoder_interface(api, Fixture, stage, missing):
    from contextlib import ExitStack
    from dataclasses import replace
    from unittest.mock import Mock, patch
    from local_inspection_service.detection.presence_inspection import PresenceInspection
    with ExitStack() as stack:
        stack.enter_context(patch.dict(api.__dict__))
        f=Fixture();f.bind(api,stack);events=[]
        b=Mock(side_effect=lambda *a,**k:events.append('B') or 'data:synthetic');c=Mock(side_effect=AssertionError('late encoder C used'));current=[None if missing else b]
        def side():events.append('arg');current[0]=c;return 800
        original=api._presence_inspection
        service=PresenceInspection(replace(original.input,**{stage:lambda:current[0]}),original.generation,original.output,replace(original.policy,max_side=side),original.clock)
        payload={**f.payload(),'inspection_image_data_url':'','inspection_image_path':'source.png' if stage=='path' else '', 'inspection_image_bgr':f.image}
        captured=None
        try:service.tool_vision_inspect_presence(payload)
        except BaseException as exc:captured=exc
        if missing:assert type(captured) is TypeError,(stage,captured,events)
        else:assert captured is None,(stage,captured,events)
        assert events==(['arg'] if missing else ['arg','B']),(stage,events)
        assert not c.called and b.call_count==int(not missing)
        return events


class PresenceFixture:
    def __init__(self):
        self.events=[]; self.settings={'configured':True,'provider':'gemini','model':'synthetic'}
        self.required=[{'accessory_id':'a','name':'Part A'},{'accessory_id':'b','name':'Part B'}]
        self.image=np.zeros((3,4,3),dtype=np.uint8); self.task={'task':{'required':['a','b']}}
        self.cache={'enabled':False,'status':'disabled','provider_call_count':0,'private':'not projected'}
        self.parsed={'detections':[{'accessory_id':'a'}]}; self.response={'ok':True,'parsed':self.parsed,'latency_ms':31,'meta':{'provider':'fixture'}}
        self.result={'passed':True,'ai':{'normalized':True}}; self.failure={'passed':False,'ai':{'failed':True}}
        def port(name,result): return Mock(side_effect=lambda *args,**kwargs:self.events.append(name) or result())
        self.settings_call=port('settings',lambda:self.settings); self.resolve=port('resolve',lambda:self.required)
        self.path=port('path',lambda:'data:path'); self.bgr=port('bgr',lambda:'data:bgr'); self.task_call=port('task',lambda:self.task)
        self.cache_call=port('cache',lambda:self.cache); self.tokens=port('tokens',lambda:128); self.tool=port('tool',lambda:self.response)
        self.covers=port('covers',lambda:True); self.normalize=port('normalize',lambda:self.result); self.fail=port('failure',lambda:self.failure)
        self.ticks=itertools.count(); self.clock=Mock(side_effect=lambda:self.events.append('clock') or next(self.ticks))
        self.schema={'type':'object'}
    def bind(self,api,stack):
        for name,value in {'time':SimpleNamespace(monotonic=self.clock),'ai_detection_settings':self.settings_call,
            'resolve_required_accessory_refs':self.resolve,'image_path_data_url':self.path,'image_bgr_data_url':self.bgr,
            'ai_detection_task_payload':self.task_call,'ensure_required_profile_cache':self.cache_call,
            'ai_detection_provider_output_token_budget':self.tokens,'call_ai_mcp_tool':self.tool,
            'ai_detection_parsed_covers_required':self.covers,'normalize_ai_detection_result':self.normalize,
            'ai_presence_failure_payload':self.fail,'AI_INSPECTION_IMAGE_MAX_SIDE':800,'AI_INSPECTION_IMAGE_QUALITY':81,
            'AI_REFERENCE_IMAGES_PER_ACCESSORY':2,'AI_PROVIDER_MAX_ATTEMPTS':3,'AI_DETECTION_SYSTEM_PROMPT':'original test prompt',
            'AI_DETECTION_OUTPUT_SCHEMA':self.schema}.items(): stack.enter_context(patch.object(api,name,value))
    def payload(self): return {'provider_config':self.settings,'required_accessories':self.required,'inspection_image_data_url':'data:inspection'}


class PresenceInspectionContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ); cls.environment.start(); cls.runtime=tempfile.TemporaryDirectory(prefix='presence-inspection-')
        root=Path(cls.runtime.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        for target in ['requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill']:
            self.stack.enter_context(patch(target,side_effect=AssertionError('unexpected external operation')))
        self.f=PresenceFixture(); self.f.bind(self.api,self.stack)
    def inspect(self,payload=None): return self.api.tool_vision_inspect_presence(self.f.payload() if payload is None else payload)

    def test_complete_generation_preserves_order_arguments_aliases_and_timing(self):
        f=self.f; result=self.inspect(); self.assertIs(result,f.result)
        self.assertEqual(f.events,['clock','clock','clock','task','cache','clock','clock','tokens','tool','clock','normalize'])
        f.settings_call.assert_not_called(); f.resolve.assert_not_called(); f.path.assert_not_called(); f.bgr.assert_not_called()
        required=f.task_call.call_args.args[0]; self.assertEqual(required,f.required); self.assertIsNot(required,f.required); self.assertIs(required[0],f.required[0])
        settings=f.cache_call.call_args.args[1]; self.assertEqual(settings,f.settings); self.assertIsNot(settings,f.settings)
        self.assertIs(f.cache_call.call_args.args[0],required); f.tokens.assert_called_once_with(2,settings)
        name,payload=f.tool.call_args.args; self.assertEqual(name,'provider.gemini.generate_json'); self.assertIs(payload['provider_config'],settings)
        self.assertEqual(payload['max_tokens'],128); self.assertIs(payload['schema_hint'],f.schema); self.assertEqual(payload['system_prompt'],'original test prompt')
        self.assertEqual(payload['cached_content'],''); self.assertEqual(payload['max_attempts'],3)
        self.assertEqual(json.loads(payload['user_content'][0]['text']),f.task); self.assertEqual(payload['user_content'][2],{'type':'image_url','image_url':{'url':'data:inspection','detail':'high'}})
        f.normalize.assert_called_once_with(f.parsed,required,31,settings); f.covers.assert_not_called(); f.fail.assert_not_called()
        self.assertEqual(result['ai']['timing'],{'resolved_required_ms':1000,'inspection_encoded_ms':2000,'profile_cache_ready_ms':3000,'user_content_ready_ms':4000,'provider_result_ready_ms':5000})
        self.assertEqual(f.cache['generate_attempt_budget'],3); self.assertNotIn('private',result['ai']['profile_cache']); self.assertEqual(result['ai']['reference_images'],0)

    def test_resolution_filters_then_defaults_and_early_failure_has_no_timing(self):
        f=self.f; f.settings['configured']=False; f.settings['message']='disabled'; payload={'required_accessories':[None,{}, {'accessory_id':''}], 'required_accessory_refs':['ref']}
        result=self.inspect(payload); self.assertIs(result,f.failure); self.assertEqual(f.events,['clock','settings','resolve','clock','failure'])
        f.resolve.assert_called_once_with(['ref']); f.fail.assert_called_once_with(f.required,f.settings,reason='disabled')
        self.assertNotIn('timing',result['ai']); f.task_call.assert_not_called(); f.tool.assert_not_called()
        f.events.clear(); f.resolve.reset_mock(); item={'accessory_id':'a'}; self.inspect({'provider_config':f.settings,'required_accessories':[None,{},item,5,{'accessory_id':0}]})
        f.resolve.assert_not_called(); self.assertEqual(f.fail.call_args.args[0],[item]); self.assertIs(f.fail.call_args.args[0][0],item)
        f.settings['message']=''; self.inspect({'provider_config':f.settings}); self.assertEqual(f.fail.call_args.kwargs['reason'],'AI provider is not configured')

    def test_image_input_priority_and_path_failure_do_not_fall_through(self):
        f=self.f; payload={**f.payload(),'inspection_image_path':'source.png','inspection_image_bgr':f.image}
        self.inspect(payload); f.path.assert_not_called(); f.bgr.assert_not_called()
        payload['inspection_image_data_url']=''; self.inspect(payload); f.path.assert_called_once_with(Path('source.png'),max_side=800,quality=81); f.bgr.assert_not_called()
        f.path.side_effect=None; f.path.return_value=None; f.tool.reset_mock(); result=self.inspect(payload)
        self.assertIs(result,f.failure); self.assertEqual(f.fail.call_args.kwargs['reason'],'Inspection image path could not be encoded'); f.bgr.assert_not_called(); f.tool.assert_not_called()
        payload['inspection_image_path']=''; self.inspect(payload); self.assertIs(f.bgr.call_args.args[0],f.image); self.assertEqual(f.bgr.call_args.kwargs,{'max_side':800,'quality':81})
        f.bgr.side_effect=None; f.bgr.return_value=''; self.inspect(payload); self.assertEqual(f.tool.call_args.args[1]['user_content'][-1]['image_url']['url'],'')
        payload['inspection_image_bgr']=[1,2]; f.tool.reset_mock(); self.inspect(payload); self.assertEqual(f.fail.call_args.kwargs['reason'],'Inspection image payload was missing'); f.tool.assert_not_called()

    def test_profile_cache_budget_mutates_original_and_preserves_minimum_one(self):
        for count,attempts in [(0,3),(1,2),(3,1),(8,1),(-2,3),(True,2),('2',1),(None,3)]:
            with self.subTest(count=count):
                f=self.f; f.cache={'enabled':True,'name':'cached/name','provider_call_count':count,'reference_images':5}; self.inspect()
                self.assertEqual(f.tool.call_args.args[1]['max_attempts'],attempts); self.assertEqual(f.tool.call_args.args[1]['cached_content'],'cached/name')
                self.assertEqual(f.cache['generate_attempt_budget'],attempts); self.assertEqual(f.cache['profile_provider_call_count'],max(0,int(count or 0)))
                self.assertEqual(f.cache['provider_call_budget'],3); self.assertEqual(f.result['ai']['reference_images'],5)
                content=f.tool.call_args.args[1]['user_content']; self.assertEqual(len(content),2); self.assertIn('cached required accessory',content[0]['text']); self.assertIn(json.dumps(f.task,ensure_ascii=False),content[0]['text'])
        f.cache={'provider_call_count':'invalid'}; f.tool.reset_mock()
        with self.assertRaises(ValueError): self.inspect()
        self.assertEqual(f.cache,{'provider_call_count':'invalid'}); f.tool.assert_not_called()
        f.cache={'provider_call_count':0}; self.api.AI_PROVIDER_MAX_ATTEMPTS=0; self.inspect(); self.assertEqual(f.cache['generate_attempt_budget'],1); self.assertEqual(f.cache['provider_call_budget'],0)

    def test_references_are_per_identity_and_keep_order_detail_and_unrequired_ids(self):
        f=self.f; refs=[None,{}, {'data_url':'missing id'}, {'accessory_id':'a','data_url':''}]
        refs += [{'accessory_id':identity,'data_url':identity+str(index),'detail':None if index==1 else 'low'} for identity,index in [('a',1),('b',1),('a',2),('a',3),('unrequired',1)]]
        result=self.inspect({**f.payload(),'reference_descriptors':refs}); content=f.tool.call_args.args[1]['user_content']
        self.assertEqual([x['image_url']['url'] for x in content if x['type']=='image_url'],['data:inspection','a1','b1','a2','unrequired1'])
        self.assertIsNone(content[4]['image_url']['detail']); self.assertEqual(result['ai']['reference_images'],4)
        for limit in [0,-1]:
            self.api.AI_REFERENCE_IMAGES_PER_ACCESSORY=limit; self.inspect({**f.payload(),'reference_descriptors':refs}); self.assertEqual(len(f.tool.call_args.args[1]['user_content']),3)
        self.api.AI_REFERENCE_IMAGES_PER_ACCESSORY=2; f.cache['reference_images']=-2; self.inspect({**f.payload(),'reference_descriptors':refs}); self.assertEqual(f.result['ai']['reference_images'],-2)

    def test_qwen_retries_only_successful_uncovered_result_once(self):
        f=self.f; f.settings['provider']='qwen'; first={'ok':True,'parsed':{'first':True}}; second={'ok':True,'parsed':{'second':True},'meta':{'attempt':2},'latency_ms':7}
        f.tool.side_effect=[first,second]; f.covers.side_effect=[False,True]; result=self.inspect()
        self.assertEqual(f.tool.call_count,2); self.assertEqual(f.covers.call_args_list,[call(first['parsed'],{'a','b'}),call(second['parsed'],{'a','b'})])
        initial=f.tool.call_args_list[0].args[1]; retry=f.tool.call_args_list[1].args[1]
        self.assertEqual(retry['max_attempts'],1); self.assertEqual(len(retry['user_content']),len(initial['user_content'])+1)
        for a,b in zip(initial['user_content'],retry['user_content']): self.assertIs(a,b)
        self.assertIn('RETRY_COVERAGE:',retry['user_content'][-1]['text']); self.assertEqual(second['meta'],{'attempt':2})
        self.assertTrue(result['ai']['coverage_retry']); f.normalize.assert_called_once_with(second['parsed'],f.required,7,f.settings)
        for provider,ok,covered in [('gemini',True,False),('QWEN',True,False),('qwen',False,False),('qwen',True,True)]:
            with self.subTest(provider=provider,ok=ok,covered=covered):
                f.settings['provider']=provider; f.tool.reset_mock(); f.tool.side_effect=None; f.tool.return_value={'ok':ok,'parsed':{}}
                f.covers.reset_mock(); f.covers.side_effect=None; f.covers.return_value=covered; self.inspect()
                f.tool.assert_called_once(); self.assertEqual(f.covers.call_count,int(provider=='qwen' and ok))

    def test_qwen_retry_failure_keeps_second_evidence_and_never_retries_unknown_errors(self):
        for retry in [{'ok':True,'parsed':{},'meta':None}, {'ok':False,'error':'denied','timed_out':True,'latency_ms':17,'meta':{'evidence':'second'}}]:
            with self.subTest(retry=retry), ExitStack() as stack:
                f=PresenceFixture(); f.bind(self.api,stack); f.settings['provider']='qwen'; f.tool.side_effect=[{'ok':True,'parsed':{}},retry]
                f.covers.side_effect=[False,False]; result=self.api.tool_vision_inspect_presence(f.payload())
                self.assertIs(result,f.failure); self.assertEqual(f.tool.call_count,2); self.assertEqual(f.covers.call_count,2 if retry['ok'] else 1)
                self.assertEqual(f.fail.call_args.kwargs,{'reason':retry.get('error') or 'AI provider response did not cover any required accessory','timed_out':bool(retry.get('timed_out')),'latency_ms':int(retry.get('latency_ms') or 0)})
                self.assertTrue(result['ai']['coverage_retry']); self.assertTrue(result['ai']['coverage_retry_failed']); f.normalize.assert_not_called()
        f=self.f; f.settings['provider']='qwen'; error=OSError('unknown outcome'); f.tool.side_effect=[error,f.response]
        with self.assertRaises(OSError) as caught: self.inspect()
        self.assertIs(caught.exception,error); f.tool.assert_called_once(); f.fail.assert_not_called(); f.normalize.assert_not_called()

    def test_success_and_failure_metadata_have_original_distinct_overwrite_order(self):
        for ok in [True,False]:
            with self.subTest(ok=ok), ExitStack() as stack:
                f=PresenceFixture(); f.bind(self.api,stack); metadata_cache={'from':'provider'}; metadata_timing={'wrong':True}
                f.response.update(ok=ok,meta={'profile_cache':metadata_cache,'reference_images':99,'timing':metadata_timing})
                f.cache.update(name='not exposed',error='cache error',usage_metadata={'tokens':5},cache_key='key',latency_ms=2)
                result=self.api.tool_vision_inspect_presence(f.payload()); ai=result['ai']
                if ok: self.assertIs(ai['profile_cache'],metadata_cache)
                else:
                    self.assertIsNot(ai['profile_cache'],metadata_cache); self.assertNotIn('name',ai['profile_cache']); self.assertNotIn('private',ai['profile_cache'])
                    self.assertIs(ai['profile_cache']['usage_metadata'],f.cache['usage_metadata']); self.assertEqual(ai['profile_cache']['error'],'cache error')
                self.assertEqual(ai['reference_images'],99); self.assertIsNot(ai['timing'],metadata_timing); self.assertEqual(ai['timing']['provider_result_ready_ms'],5000)
        f=self.f; f.response['parsed']=None; f.response['meta']=['bad']; self.inspect(); self.assertEqual(f.normalize.call_args.args[0],{})

    def test_first_error_at_each_stage_propagates_without_extra_attempts(self):
        stages=['settings_call','resolve','path','bgr','task_call','cache_call','tokens','tool','covers','normalize','fail']
        for stage in stages:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=PresenceFixture(); f.bind(self.api,stack); payload=f.payload(); error=OSError(stage)
                if stage=='settings_call': payload.pop('provider_config')
                if stage=='resolve': payload.pop('required_accessories')
                if stage in ['path','bgr']:
                    payload['inspection_image_data_url']=''; payload['inspection_image_path']='source.png' if stage=='path' else ''; payload['inspection_image_bgr']=f.image
                if stage=='covers': f.settings['provider']='qwen'
                if stage=='fail': f.response['ok']=False
                port=getattr(f,stage); normal=port.side_effect; calls=0
                def first_error(*args,**kwargs):
                    nonlocal calls
                    calls+=1
                    if calls==1: raise error
                    return normal(*args,**kwargs)
                port.side_effect=first_error
                with self.assertRaises(OSError) as caught: self.api.tool_vision_inspect_presence(payload)
                self.assertIs(caught.exception,error); self.assertEqual(calls,1)
                if stage not in ['normalize','fail']: f.normalize.assert_not_called(); f.fail.assert_not_called()
                self.assertLessEqual(f.tool.call_count,1)

    def test_clock_failure_at_every_mark_stops_at_that_mark(self):
        for index in range(6):
            with self.subTest(index=index), ExitStack() as stack:
                f=PresenceFixture(); f.bind(self.api,stack); error=OSError('clock'); f.clock.side_effect=[*range(index),error,*range(10)]
                with self.assertRaises(OSError) as caught: self.api.tool_vision_inspect_presence(f.payload())
                self.assertIs(caught.exception,error); self.assertEqual(f.clock.call_count,index+1); f.normalize.assert_not_called()
                self.assertEqual(f.tool.call_count,int(index==5))

    def test_resolver_is_captured_before_payload_get_even_when_noncallable(self):
        for missing in [False,True]:
            with self.subTest(missing=missing), ExitStack() as stack:
                f=PresenceFixture(); f.bind(self.api,stack); events=[]; later=Mock(return_value=f.required); self.api.resolve_required_accessory_refs=None if missing else f.resolve
                class Payload(dict):
                    def get(inner,key,default=None):
                        if key=='required_accessory_refs': events.append(key); self.api.resolve_required_accessory_refs=later
                        return super().get(key,default)
                payload=Payload(provider_config=f.settings,inspection_image_data_url='data:test',required_accessory_refs=['ref'])
                if missing:
                    with self.assertRaises(TypeError): self.api.tool_vision_inspect_presence(payload)
                    f.resolve.assert_not_called(); f.tool.assert_not_called()
                else: self.api.tool_vision_inspect_presence(payload); f.resolve.assert_called_once_with(['ref'])
                self.assertEqual(events,['required_accessory_refs']); later.assert_not_called()

    def test_failure_and_normalizer_capture_before_response_get_and_conversion(self):
        for stage in ['failure','normalize']:
            for missing in [False,True]:
                with self.subTest(stage=stage,missing=missing), ExitStack() as stack:
                    f=PresenceFixture(); f.bind(self.api,stack); name='ai_presence_failure_payload' if stage=='failure' else 'normalize_ai_detection_result'
                    original=f.fail if stage=='failure' else f.normalize; later=Mock(return_value=f.failure if stage=='failure' else f.result); events=[]
                    class Latency:
                        def __int__(inner): events.append('int'); setattr(self.api,name,later); return 9
                    f.response.update(ok=stage=='normalize',latency_ms=Latency()); setattr(self.api,name,None if missing else original)
                    if missing:
                        with self.assertRaises(TypeError): self.api.tool_vision_inspect_presence(f.payload())
                        original.assert_not_called()
                    else: self.api.tool_vision_inspect_presence(f.payload()); original.assert_called_once()
                    self.assertEqual(events,['int']); later.assert_not_called(); f.tool.assert_called_once()


    def test_cache_mutation_and_late_required_ids_preserve_aliases(self):
        f=self.f; f.settings['provider']='qwen'
        def cache(required,settings):
            f.task['cache_effect']='visible in prompt'; return f.cache
        def provider(*args):
            f.required[0]['accessory_id']='after-call'; return f.response
        f.cache_call.side_effect=cache; f.tool.side_effect=provider; self.inspect()
        content=f.tool.call_args.args[1]['user_content']; self.assertEqual(json.loads(content[0]['text'])['cache_effect'],'visible in prompt')
        f.covers.assert_called_once_with(f.parsed,{'after-call','b'}); self.assertIs(f.normalize.call_args.args[1][0],f.required[0])

    def test_cache_budget_writes_fail_in_order_without_rollback_or_provider_call(self):
        keys=['provider_call_budget','generate_attempt_budget','profile_provider_call_count']
        for failed in keys:
            with self.subTest(failed=failed), ExitStack() as stack:
                f=PresenceFixture(); f.bind(self.api,stack); writes=[]; error=OSError(failed)
                class Cache(dict):
                    def __setitem__(inner,key,value):
                        writes.append((key,value))
                        if key==failed: raise error
                        return super().__setitem__(key,value)
                f.cache=Cache(provider_call_count=1)
                with self.assertRaises(OSError) as caught: self.api.tool_vision_inspect_presence(f.payload())
                self.assertIs(caught.exception,error); self.assertEqual([key for key,value in writes],keys[:keys.index(failed)+1])
                self.assertEqual(set(f.cache),{'provider_call_count',*keys[:keys.index(failed)]}); f.tool.assert_not_called()

    def test_coverage_target_capture_and_second_call_unknown_outcome_are_not_retried(self):
        for missing in [False,True]:
            with self.subTest(missing=missing), ExitStack() as stack:
                f=PresenceFixture(); f.bind(self.api,stack); f.settings['provider']='qwen'; events=[]; later=Mock(return_value=True)
                class Response(dict):
                    def get(inner,key,default=None):
                        if key=='parsed': events.append('parsed'); self.api.ai_detection_parsed_covers_required=later
                        return super().get(key,default)
                f.response=Response(ok=True,parsed=f.parsed); self.api.ai_detection_parsed_covers_required=None if missing else f.covers
                if missing:
                    with self.assertRaises(TypeError): self.api.tool_vision_inspect_presence(f.payload())
                    self.assertEqual(events,['parsed']); f.covers.assert_not_called(); f.normalize.assert_not_called()
                else:
                    self.api.tool_vision_inspect_presence(f.payload()); f.covers.assert_called_once_with(f.parsed,{'a','b'})
                    self.assertEqual(events,['parsed','parsed'])
                later.assert_not_called(); f.tool.assert_called_once()
        f=self.f; f.settings['provider']='qwen'; failure=OSError('second unknown'); f.covers.side_effect=None; f.covers.return_value=False
        f.tool.side_effect=[f.response,failure,f.response]
        with self.assertRaises(OSError) as caught: self.inspect()
        self.assertIs(caught.exception,failure); self.assertEqual(f.tool.call_count,2); f.fail.assert_not_called(); f.normalize.assert_not_called()


    def test_independent_services_interleave_without_root_state_and_constructor_reads(self):
        from local_inspection_service.detection.presence_inspection import PresenceInspection
        from local_inspection_service.detection.presence_inspection_ports import PresenceInput,PresenceGeneration,PresenceOutput,PresencePolicy
        services=[]
        for owner in ['alice','bob']:
            f=PresenceFixture(); f.required=[{'accessory_id':owner}]; f.settings['owner']=owner; f.response['meta']={'owner':owner}; f.task={'owner':owner}; f.schema={'owner':owner}
            providers=[Mock(return_value=value) for value in [f.resolve,f.path,f.bgr,f.tokens,f.tool,f.covers,f.fail,f.normalize]]
            resolve,path,image,tokens,tool,covers,failure,normalize=providers
            service=PresenceInspection(PresenceInput(f.settings_call,resolve,path,image),
                PresenceGeneration(f.task_call,f.cache_call,tokens,tool,covers),PresenceOutput(failure,normalize),
                PresencePolicy(lambda:800,lambda:81,lambda:3,lambda:2,lambda:'test prompt',lambda f=f:f.schema),f.clock)
            for provider in providers: provider.assert_not_called()
            self.assertEqual(f.events,[]); services.append((owner,f,service))
        with ExitStack() as stack:
            for name in ['ai_detection_settings','resolve_required_accessory_refs','image_path_data_url','image_bgr_data_url',
                         'ai_detection_task_payload','ensure_required_profile_cache','ai_detection_provider_output_token_budget',
                         'call_ai_mcp_tool','ai_detection_parsed_covers_required','ai_presence_failure_payload','normalize_ai_detection_result']:
                stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('root dependency')))
            stack.enter_context(patch.object(self.api,'time',object()))
            for repetition in [1,2]:
                for owner,f,service in services:
                    result=service.tool_vision_inspect_presence(f.payload()); self.assertIs(result,f.result); self.assertEqual(result['ai']['owner'],owner)
                    self.assertEqual(json.loads(f.tool.call_args.args[1]['user_content'][0]['text']),{'owner':owner})
                    self.assertEqual(f.tool.call_count,repetition); self.assertEqual(f.normalize.call_count,repetition)
                    self.assertIs(f.tool.call_args.args[1]['schema_hint'],f.schema)
                    self.assertIs(f.normalize.call_args.args[1][0],f.required[0]); self.assertEqual(result['ai']['timing']['provider_result_ready_ms'],5000)
        self.assertIs(self.api.AI_MCP_TOOL_HANDLERS['vision.inspect.presence'],self.api.tool_vision_inspect_presence)
        self.assertFalse(hasattr(self.api.tool_vision_inspect_presence,'__wrapped__'))

    def test_independent_missing_encoder_provider_fails_before_policy_reads(self):
        from local_inspection_service.detection.presence_inspection import PresenceInspection
        from local_inspection_service.detection.presence_inspection_ports import PresenceInput,PresenceGeneration,PresenceOutput,PresencePolicy
        f=self.f; error=OSError('encoder provider'); path=Mock(side_effect=error); side=Mock(return_value=800); quality=Mock(return_value=81)
        service=PresenceInspection(PresenceInput(f.settings_call,lambda:f.resolve,path,lambda:f.bgr),
            PresenceGeneration(f.task_call,f.cache_call,lambda:f.tokens,lambda:f.tool,lambda:f.covers),PresenceOutput(lambda:f.fail,lambda:f.normalize),
            PresencePolicy(side,quality,lambda:3,lambda:2,lambda:'test prompt',lambda f=f:f.schema),f.clock)
        path.assert_not_called(); payload={**f.payload(),'inspection_image_data_url':'','inspection_image_path':'source.png'}
        with self.assertRaises(OSError) as caught: service.tool_vision_inspect_presence(payload)
        self.assertIs(caught.exception,error); path.assert_called_once_with(); side.assert_not_called(); quality.assert_not_called(); f.path.assert_not_called(); f.tool.assert_not_called()


    def test_prompt_text_is_exact_for_cache_reference_and_coverage_retry(self):
        normal='INSPECTION_IMAGE: decide presence only from the next image. Return compact boolean/count QA JSON only. No narrative. Count substantial identifiable partial views as present; reject only tiny or ambiguous fragments.'
        retry='RETRY_COVERAGE: the previous response did not include any of the required accessory_id entries. Return the compact QA JSON with one detections entry per required accessory_id listed in the task payload, using those exact accessory_id strings.'
        for enabled,name in [(False,''),(True,''),(True,'cached/name')]:
            with self.subTest(enabled=enabled,name=name), ExitStack() as stack:
                f=PresenceFixture(); f.bind(self.api,stack); f.settings['provider']='qwen'; f.cache.update(enabled=enabled,name=name)
                f.tool.side_effect=[f.response,f.response]; f.covers.side_effect=[False,True]
                self.api.tool_vision_inspect_presence({**f.payload(),'reference_descriptors':[{'accessory_id':'a','data_url':'data:ref'}]})
                content=f.tool.call_args_list[0].args[1]['user_content']; cached=enabled and bool(name)
                if cached:
                    expected='INSPECTION_IMAGE: decide presence only from the next image, using the cached required accessory profile context. Current required accessory IDs and cues are repeated here to avoid ID drift:\n'+json.dumps(f.task,ensure_ascii=False)+'\nReturn compact boolean/count QA JSON only. No narrative. Count substantial identifiable partial views as present; reject only tiny or ambiguous fragments.'
                    self.assertEqual(content[0]['text'],expected)
                else:
                    self.assertEqual(content[0]['text'],json.dumps(f.task,ensure_ascii=False)); self.assertEqual(content[1]['text'],normal)
                self.assertEqual(content[-2]['text'],'REFERENCE_IMAGE for accessory_id=a. Use this only as appearance evidence; do not count it as present.')
                self.assertEqual(f.tool.call_args_list[1].args[1]['user_content'][-1]['text'],retry)
                self.assertEqual(len(content),4 if cached else 5)

    def test_truthy_provider_success_flags_preserve_coverage_and_second_result(self):
        for first,second in [(1,1),('yes','yes')]:
            with self.subTest(first=first,second=second), ExitStack() as stack:
                f=PresenceFixture(); f.bind(self.api,stack); f.settings['provider']='qwen'
                f.tool.side_effect=[{'ok':first,'parsed':{}},{'ok':second,'parsed':f.parsed}]; f.covers.side_effect=[False,True]
                result=self.api.tool_vision_inspect_presence(f.payload()); self.assertIs(result,f.result); self.assertTrue(result['ai']['coverage_retry'])
                self.assertEqual(f.tool.call_count,2); self.assertEqual(f.covers.call_count,2); f.normalize.assert_called_once(); f.fail.assert_not_called()

    def test_token_budget_callee_is_captured_before_required_length_without_retry(self):
        for mode in ['success','none','error']:
            with self.subTest(mode=mode), ExitStack() as stack:
                f=PresenceFixture(); f.bind(self.api,stack); events=[]; later=Mock(return_value=999); error=OSError('budget failed')
                class Required(list):
                    def __len__(inner): events.append('len'); self.api.ai_detection_provider_output_token_budget=later; return super().__len__()
                f.required=Required(f.required); first=Mock(return_value=128,side_effect=[error,128] if mode=='error' else None)
                before=Mock(return_value=777); self.api.ai_detection_provider_output_token_budget=before
                f.cache_call.side_effect=lambda *args:setattr(self.api,'ai_detection_provider_output_token_budget',None if mode=='none' else first) or f.cache
                payload=f.payload(); payload.pop('required_accessories')
                if mode=='success':
                    self.api.tool_vision_inspect_presence(payload); self.assertEqual(f.tool.call_args.args[1]['max_tokens'],128)
                else:
                    with self.assertRaises(TypeError if mode=='none' else OSError) as caught: self.api.tool_vision_inspect_presence(payload)
                    if mode=='error': self.assertIs(caught.exception,error)
                    f.tool.assert_not_called(); f.normalize.assert_not_called()
                self.assertEqual(events,['len']); before.assert_not_called(); later.assert_not_called()
                if mode=='none': first.assert_not_called()
                else: first.assert_called_once_with(2,f.settings)


    def test_reference_limit_is_read_per_item_and_duplicate_urls_remain(self):
        f=self.f; self.api.AI_REFERENCE_IMAGES_PER_ACCESSORY=1; events=[]
        class Identity:
            def __str__(inner): events.append('id'); self.api.AI_REFERENCE_IMAGES_PER_ACCESSORY=2; return 'a'
        refs=[{'accessory_id':'a','data_url':'same'},{'accessory_id':Identity(),'data_url':'same'},{'accessory_id':'a','data_url':'third'}]
        self.inspect({**f.payload(),'reference_descriptors':refs}); content=f.tool.call_args.args[1]['user_content']
        self.assertEqual([item['image_url']['url'] for item in content if item['type']=='image_url'],['data:inspection','same','same'])
        self.assertEqual(events,['id']); self.assertEqual(f.result['ai']['reference_images'],2)

    def test_complete_profile_cache_projection_on_success_and_failure_is_shallow(self):
        for ok in [True,False]:
            with self.subTest(ok=ok), ExitStack() as stack:
                f=PresenceFixture(); f.bind(self.api,stack)
                f.cache={'enabled':False,'status':'ready','reference_images':4,'latency_ms':8,'cache_key':'key',
                         'error':'cache error','usage_metadata':{'tokens':7},'provider_call_count':1,'name':'private','unknown':'private'}
                f.response['ok']=ok; result=self.api.tool_vision_inspect_presence(f.payload())
                expected={'enabled':False,'status':'ready','reference_images':4,'latency_ms':8,'cache_key':'key',
                          'error':'cache error','usage_metadata':f.cache['usage_metadata'],'provider_call_count':1,
                          'provider_call_budget':3,'profile_provider_call_count':1,'generate_attempt_budget':2}
                self.assertEqual(result['ai']['profile_cache'],expected); self.assertIs(result['ai']['profile_cache']['usage_metadata'],f.cache['usage_metadata'])


    def test_early_failures_and_second_coverage_error_are_not_retried(self):
        for branch in ('unconfigured','empty_path','missing_image','second_coverage'):
            with self.subTest(branch=branch),ExitStack() as stack:
                f=PresenceFixture();f.bind(self.api,stack);payload=f.payload();error=RuntimeError(branch);calls=0
                if branch=='unconfigured':f.settings['configured']=False
                elif branch=='empty_path':payload.update(inspection_image_data_url='',inspection_image_path='synthetic.png');f.path.side_effect=lambda *a,**k:''
                elif branch=='missing_image':payload.update(inspection_image_data_url='',inspection_image_path='')
                else:f.settings['provider']='qwen'
                port=f.covers if branch=='second_coverage' else f.fail;original=port.side_effect
                def once(*args,**kwargs):
                    nonlocal calls
                    calls+=1
                    if calls==(2 if branch=='second_coverage' else 1):raise error
                    return False if branch=='second_coverage' else original(*args,**kwargs)
                port.side_effect=once
                with self.assertRaises(RuntimeError) as caught:self.api.tool_vision_inspect_presence(payload)
                self.assertIs(caught.exception,error);self.assertEqual(calls,2 if branch=='second_coverage' else 1)
                self.assertEqual(f.tool.call_count,2 if branch=='second_coverage' else 0);f.normalize.assert_not_called()

    def test_independent_getter_and_policy_failures_preserve_attempt_limits(self):
        from local_inspection_service.detection.presence_inspection import PresenceInspection
        from local_inspection_service.detection.presence_inspection_ports import PresenceInput,PresenceGeneration,PresenceOutput,PresencePolicy
        windows=[('normal','attempts',1),('normal','attempts',2),('normal','prompt',1),('normal','schema',1),
                 ('normal','tokens',1),('normal','call',1),('normal','normalize',1),('refs','references',1),
                 ('resolve','resolve',1),('path','path',1),('path','side',1),('path','quality',1),
                 ('bgr','image',1),('bgr','side',1),('bgr','quality',1),('qwen','call',2),
                 ('qwen','covers',1),('qwen','covers',2),('failure','failure',1),
                 ('unconfigured','failure',1),('empty_path','failure',1),('missing','failure',1)]
        for branch,stage,occurrence in windows:
            with self.subTest(branch=branch,stage=stage,occurrence=occurrence):
                f=PresenceFixture();payload=f.payload();error=RuntimeError(stage);counts={}
                if branch=='resolve':payload.pop('required_accessories')
                if branch in ('path','empty_path'):payload.update(inspection_image_data_url='',inspection_image_path='synthetic.png')
                if branch=='empty_path':f.path.side_effect=lambda *a,**k:''
                if branch in ('bgr','missing'):payload.update(inspection_image_data_url='',inspection_image_bgr=f.image if branch=='bgr' else None)
                if branch=='unconfigured':f.settings['configured']=False
                if branch=='failure':f.response['ok']=False
                if branch=='refs':payload['reference_descriptors']=[{'accessory_id':'a','data_url':'data:ref'}]
                if branch=='qwen':f.settings['provider']='qwen';f.covers.side_effect=lambda *args:False
                def provider(name,value):
                    def read():
                        counts[name]=counts.get(name,0)+1
                        if name==stage and counts[name]==occurrence:raise error
                        return value
                    return read
                service=PresenceInspection(PresenceInput(f.settings_call,provider('resolve',f.resolve),provider('path',f.path),provider('image',f.bgr)),
                    PresenceGeneration(f.task_call,f.cache_call,provider('tokens',f.tokens),provider('call',f.tool),provider('covers',f.covers)),
                    PresenceOutput(provider('failure',f.fail),provider('normalize',f.normalize)),
                    PresencePolicy(provider('side',800),provider('quality',81),provider('attempts',3),provider('references',2),provider('prompt','test'),provider('schema',f.schema)),f.clock)
                with self.assertRaises(RuntimeError) as caught:service.tool_vision_inspect_presence(payload)
                self.assertIs(caught.exception,error);self.assertEqual(counts[stage],occurrence);self.assertLessEqual(f.tool.call_count,2 if branch=='qwen' else 1)

    def test_mapping_first_errors_preserve_projection_and_call_boundaries(self):
        windows=[('normal','payload','get','provider_config',1),('normal','payload','get','required_accessories',1),
                 ('resolve','payload','get','required_accessory_refs',1),('normal','payload','get','inspection_image_data_url',1),
                 ('path','payload','get','inspection_image_path',1),('bgr','payload','get','inspection_image_bgr',1),
                 ('normal','payload','get','reference_descriptors',1),('normal','required','get','accessory_id',1),
                 ('normal','required','get','accessory_id',2),('normal','required','get','accessory_id',3),
                 ('normal','cache','get','provider_call_count',1),('cached','cache','get','enabled',1),
                 ('cached','cache','get','enabled',2),('cached','cache','get','name',1),('cached','cache','get','name',2),
                 ('normal','cache','get','reference_images',1),('normal','cache','items','',1),('failure','cache','items','',1),
                 ('refs','ref','get','data_url',1),('refs','ref','get','accessory_id',1),('refs','ref','item','data_url',1),('refs','ref','get','detail',1),
                 ('qwen','provider','get','ok',1),('qwen','provider','get','parsed',1),
                 ('normal','provider','get','ok',1),('normal','provider','get','parsed',1),('normal','provider','get','latency_ms',1),
                 ('normal','provider','get','meta',1),('normal','provider','get','meta',2),
                 ('failure','provider','get','error',1),('failure','provider','get','timed_out',1),('failure','provider','get','latency_ms',1),
                 ('failure','provider','get','meta',1),('failure','provider','get','meta',2),
                 ('qwen','retry','get','meta',1),('qwen','retry','get','meta',2),('qwen','retry','get','ok',1),
                 ('qwen','retry','get','parsed',1),('qwen_fail','retry','get','error',1),
                 *[('normal','result','item','ai',i) for i in range(1,5)],
                 ('failure','failure','item','ai',1),('failure','failure','item','ai',2)]
        for branch,owner,operation,key,occurrence in windows:
            with self.subTest(branch=branch,owner=owner,key=key,occurrence=occurrence),ExitStack() as stack:
                f=PresenceFixture();f.bind(self.api,stack);error=RuntimeError('mapping');reads=[];count=0
                def visit(where,op,field):
                    nonlocal count
                    reads.append((where,op,field))
                    if (where,op,field)==(owner,operation,key):
                        count+=1
                        if count==occurrence:raise error
                class ReadMap(dict):
                    def __init__(inner,where,values):super().__init__(values);inner.where=where
                    def get(inner,field,default=None):visit(inner.where,'get',field);return super().get(field,default)
                    def __getitem__(inner,field):visit(inner.where,'item',field);return super().__getitem__(field)
                    def items(inner):visit(inner.where,'items','');return super().items()
                f.required=[ReadMap('required',{'accessory_id':'a','name':'A'})]
                f.cache=ReadMap('cache',f.cache);f.result=ReadMap('result',f.result);f.failure=ReadMap('failure',f.failure)
                f.response=ReadMap('provider',f.response);retry=ReadMap('retry',dict(f.response));payload=ReadMap('payload',f.payload())
                if branch=='resolve':payload.pop('required_accessories')
                if branch=='path':payload.update(inspection_image_data_url='',inspection_image_path='synthetic.png')
                if branch=='bgr':payload.update(inspection_image_data_url='',inspection_image_bgr=f.image)
                if branch=='cached':f.cache.update(enabled=True,name='cache/synthetic')
                if branch=='refs':payload['reference_descriptors']=[ReadMap('ref',{'accessory_id':'a','data_url':'data:ref'})]
                if branch=='failure':f.response['ok']=False
                if branch.startswith('qwen'):
                    f.settings['provider']='qwen';calls=0;covers=0
                    def generate(*args):
                        nonlocal calls
                        calls+=1;return f.response if calls==1 else retry
                    def covered(*args):
                        nonlocal covers
                        covers+=1;return covers>1 and branch!='qwen_fail'
                    f.tool.side_effect=generate;f.covers.side_effect=covered
                with self.assertRaises(RuntimeError) as caught:self.api.tool_vision_inspect_presence(payload)
                self.assertIs(caught.exception,error);self.assertEqual(count,occurrence);self.assertEqual(reads[-1],(owner,operation,key));self.assertLessEqual(f.tool.call_count,2 if branch.startswith('qwen') else 1)
                if owner=='result':
                    fields=dict.__getitem__(f.result,'ai')
                    self.assertEqual('reference_images' in fields,occurrence>=2);self.assertEqual('profile_cache' in fields,occurrence>=3)
                if owner=='failure':self.assertNotIn('profile_cache',dict.__getitem__(f.failure,'ai'))

    def test_prompt_json_failure_is_not_retried_in_either_cache_branch(self):
        for cached in (False,True):
            with self.subTest(cached=cached),ExitStack() as stack:
                f=PresenceFixture();f.bind(self.api,stack);f.cache.update(enabled=cached,name='cache/synthetic');error=RuntimeError('json');calls=0;original=json.dumps
                def once(*args,**kwargs):
                    nonlocal calls
                    calls+=1
                    if calls==1:raise error
                    return original(*args,**kwargs)
                stack.enter_context(patch.object(json,'dumps',once))
                with self.assertRaises(RuntimeError) as caught:self.api.tool_vision_inspect_presence(f.payload())
                self.assertIs(caught.exception,error);self.assertEqual(calls,1);f.tool.assert_not_called()
                self.assertEqual(f.cache['provider_call_budget'],3);self.assertEqual(f.cache['generate_attempt_budget'],3)


    def test_callback_capture_follows_prior_work_and_precedes_argument_effects(self):
        for stage in ('resolve','disabled','path','path_failure','image','missing_image','call1','call2','covers1','covers2','failure','normalize'):
            for mode in ('prior','missing'):
                with self.subTest(stage=stage,mode=mode):capture_presence_window(self.api,PresenceFixture,stage,mode)

    def test_total_budget_is_refreshed_after_subtracting_cache_calls(self):
        capture_presence_budget_refresh(self.api,PresenceFixture)

    def test_independent_encoders_capture_before_maximum_policy_effect(self):
        for stage in ('path','image'):
            for missing in (False,True):
                with self.subTest(stage=stage,missing=missing):capture_presence_encoder_interface(self.api,PresenceFixture,stage,missing)


if __name__=='__main__': unittest.main()

"""Offline AI inspection orchestration and model-snapshot contracts."""
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def capture_ai_refresh(api, Fixture, mode):
    from contextlib import ExitStack
    from unittest.mock import Mock,patch
    with ExitStack() as stack:
        stack.enter_context(patch.dict(api.__dict__))
        f=Fixture();f.bind(api,stack);events=[]
        if mode=='generate':
            one={'id':'a'};two={'id':'b'};api.AI_REFERENCE_IMAGES_PER_ACCESSORY=0
        else:
            one={'id':'a','ai_profile':{'accessory_id':'a','reference_images':[{}]}}
            two={'id':'b','ai_profile':{'accessory_id':'b','reference_images':[{}]}}
            f.normalize.side_effect=lambda profile,item:profile
        f.items=[(one,1),(two,1)];f.config={'accessories':[one,two]}
        def tool_b(name,args):events.append(('B',name));return f.call_tool(name,args)
        def tool_a(name,args):events.append(('A',name));api.call_ai_mcp_tool=tool_b;return f.call_tool(name,args)
        def settings_b(*args):events.append(('settingsB',args));return f.settings_value
        def settings_a(*args):events.append(('settingsA',args));api.ai_detection_settings=settings_b;return f.settings_value
        api.call_ai_mcp_tool=tool_a;api.ai_detection_settings=settings_a
        result=api.analyze_bgr_ai_detection(f.image,'req',f.spec,f.config)
        expected=[('settingsA',('accessory',)),('A','accessory.profile.generate'),('settingsB',('accessory',)),('B','accessory.profile.generate'),('settingsB',()),('B','vision.inspect.presence')] if mode=='generate' else [('A','accessory.reference.collect'),('B','accessory.reference.collect'),('settingsA',()),('B','vision.inspect.presence')]
        assert events==expected,(events,expected)
        assert result['passed'] is True and f.resolver.current_snapshot() is None
        return events


class BindingResolver:
    def __init__(self): self.version=1; self.value=ContextVar('ai-analysis-snapshot',default=None); self.records=[]; self.scopes=[]
    def current_snapshot(self): return self.value.get()
    def snapshot_for_record(self,record): self.records.append(record); return {'pipeline':{'version':self.version,'secret_ref':'synthetic-ref'}}
    @contextmanager
    def scope(self,value=None):
        self.scopes.append(copy.deepcopy(value)); token=self.value.set(value)
        try: yield
        finally: self.value.reset(token)


class AiAnalysisFixture:
    def __init__(self):
        self.resolver=BindingResolver(); self.events=[]; self.profile={'accessory_id':'a','reference_images':[{'id':'old-ref'}]}
        self.item={'id':'a','ai_profile':self.profile}; self.config={'accessories':[self.item]}; self.spec={'id':'ai','label':'AI'}
        self.items=[(self.item,2)]; self.normalized=self.profile; self.contexts=[]
        self.required_payload={'accessory_id':'a','expected_count':2}; self.references=[{'id':'reference'}]
        self.generated={'profile':{'accessory_id':'a','reference_images':[]},'status':'ready'}
        self.rule={'counts':{'a':2}}; self.detections=[{'accessory_id':'a','present':True}]; self.debug={'provider':'fixture'}
        self.vision={'passed':True,'rule':self.rule,'detections':self.detections,'ai':self.debug}
        self.failure_result={'request_id':'req','passed':False}; self.model_payload={'id':'ai','label':'AI'}
        self.settings_value={'status':'ready'}; self.image=np.zeros((3,4,3),dtype=np.uint8)
        def port(name,result): return Mock(side_effect=lambda *args,**kwargs:self.record(name,*args,**kwargs) or result())
        self.required=port('required',lambda:self.items); self.uid=Mock(side_effect=lambda item:self.record('uid',item) or item['id'])
        self.normalize=port('normalize',lambda:self.normalized); self.refs=port('refs',lambda:self.contexts)
        self.payload=port('payload',lambda:self.required_payload); self.settings=port('settings',lambda:self.settings_value)
        self.save=port('save',lambda:None); self.external=port('external',lambda:False); self.mcp_image=port('mcp-image',lambda:Path('mcp-image.jpg'))
        self.original=port('original',lambda:'/out/original.jpg'); self.model=port('model',lambda:self.model_payload)
        self.failure=port('failure',lambda:self.failure_result); self.persist=port('persist',lambda:None)
        self.tool=Mock(side_effect=self.call_tool)
    def record(self,name,*args,**kwargs): self.events.append((name,args,kwargs,copy.deepcopy(self.resolver.current_snapshot())))
    def call_tool(self,name,arguments):
        self.record('tool:'+name,arguments)
        return {'accessory.profile.generate':self.generated,'accessory.reference.collect':{'references':self.references},'vision.inspect.presence':self.vision}[name]
    def bind(self,api,stack):
        for name,value in {'model_profile_service':self.resolver,'ai_required_accessories':self.required,'accessory_uid':self.uid,
            'normalize_accessory_ai_profile':self.normalize,'accessory_reference_image_contexts':self.refs,
            'required_accessory_profile_payload':self.payload,'ai_detection_settings':self.settings,'save_config':self.save,
            'external_ai_mcp_enabled':self.external,'write_mcp_inspection_image':self.mcp_image,'call_ai_mcp_tool':self.tool,
            'write_ai_original_output':self.original,'ai_model_payload':self.model,'ai_detection_failure_result':self.failure,
            'persist_data_analysis_record_for_ai_detection':self.persist,'AI_REFERENCE_IMAGES_PER_ACCESSORY':2,
            'AI_REFERENCE_IMAGE_MAX_SIDE':512,'AI_REFERENCE_IMAGE_QUALITY':80}.items():stack.enter_context(patch.object(api,name,value))


class AiAnalysisContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ); cls.environment.start(); cls.runtime=tempfile.TemporaryDirectory(prefix='ai-analysis-contract-')
        root=Path(cls.runtime.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        for target in ['requests.sessions.Session.request','subprocess.Popen','os.kill']:
            self.stack.enter_context(patch(target,side_effect=AssertionError('unexpected external operation')))
        self.f=AiAnalysisFixture(); self.f.bind(self.api,self.stack)
    def analyze(self,**kwargs):
        return self.api.analyze_bgr_ai_detection(self.f.image,'req',self.f.spec,self.f.config,image_path=Path('source.png'),**kwargs)

    def test_complete_ai_orchestration_retains_arguments_order_and_references(self):
        f=self.f; result=self.analyze()
        self.assertEqual([e[0] for e in f.events],['required','uid','uid','normalize','payload','tool:accessory.reference.collect','settings','external','tool:vision.inspect.presence','original','model','persist'])
        self.assertEqual(result,{'request_id':'req','passed':True,'model':f.model_payload,'rule':f.rule,'detections':f.detections,'annotated_url':'/out/original.jpg','ai':f.debug})
        for key,value in [('model',f.model_payload),('rule',f.rule),('detections',f.detections),('ai',f.debug)]: self.assertIs(result[key],value)
        f.required.assert_called_once_with(f.config,f.spec); f.normalize.assert_called_once_with(f.profile,f.item)
        f.payload.assert_called_once_with(f.item,2,f.profile); f.save.assert_not_called(); f.refs.assert_not_called(); f.mcp_image.assert_not_called()
        self.assertEqual(f.tool.call_args_list[0],call('accessory.reference.collect',{'accessory':f.item,'max_images':2,'max_side':512,'quality':80}))
        name,arguments=f.tool.call_args_list[1].args; self.assertEqual(name,'vision.inspect.presence'); self.assertIs(arguments['inspection_image_bgr'],f.image)
        self.assertEqual({k:v for k,v in arguments.items() if k!='inspection_image_bgr'}, {'inspection_image_path':'','required_accessories':[f.required_payload],
            'required_accessory_refs':[{'accessory_id':'a','expected_count':2}],'reference_descriptors':f.references,'provider_config':f.settings_value})
        self.assertIs(f.original.call_args.args[0],f.image); self.assertEqual(f.original.call_args.args[1],'req')
        f.model.assert_called_once_with(f.spec,f.settings_value); self.assertIs(f.persist.call_args.args[0],result)
        self.assertEqual(f.persist.call_args.args[1:],('req',)); self.assertEqual(f.persist.call_args.kwargs,{'image_path':Path('source.png')})

    def test_empty_required_writes_original_failure_and_persists_once(self):
        f=self.f; f.items=[]; result=self.analyze(); self.assertIs(result,f.failure_result)
        self.assertEqual([e[0] for e in f.events],['required','original','failure','persist'])
        f.failure.assert_called_once_with('req',f.spec,[],'/out/original.jpg',reason='AI detection task has no required accessories configured.')
        self.assertIs(f.persist.call_args.args[0],result); f.persist.assert_called_once(); f.tool.assert_not_called(); f.settings.assert_not_called()

    def test_profile_generation_saves_only_real_items_before_vision(self):
        for real in [True,False]:
            with self.subTest(real=real), ExitStack() as stack:
                f=AiAnalysisFixture(); f.item.pop('ai_profile'); f.config={'accessories':[f.item] if real else []}; f.bind(self.api,stack)
                result=self.api.analyze_bgr_ai_detection(f.image,'req',f.spec,f.config)
                self.assertIs(f.item['ai_profile'],f.generated['profile']); self.assertEqual(f.item['ai_profile_status'],'ready')
                self.assertEqual(f.tool.call_args_list[0],call('accessory.profile.generate',{'accessory':f.item,'expected_count':2,'allow_provider':False,'provider_config':f.settings_value}))
                self.assertEqual(f.settings.call_args_list,[call('accessory'),call()]); f.payload.assert_called_once_with(f.item,2,f.generated['profile'])
                self.assertEqual(f.save.call_count,int(real)); names=[e[0] for e in f.events]
                if real: self.assertLess(names.index('save'),max(i for i,n in enumerate(names) if n=='settings'))
                self.assertTrue(result['passed'])

    def test_profile_normalization_ref_fallback_and_equal_object_selection(self):
        for mode in ['equal','changed','empty-no-context','empty-with-context']:
            with self.subTest(mode=mode), ExitStack() as stack:
                f=AiAnalysisFixture(); f.normalized=copy.deepcopy(f.profile)
                if mode=='changed': f.normalized['tag']='new'
                if mode.startswith('empty'): f.normalized={'accessory_id':'a','reference_images':[],'tag':'new'}
                if mode=='empty-with-context': f.contexts=[{'id':'context'}]
                f.bind(self.api,stack); self.api.analyze_bgr_ai_detection(f.image,'req',f.spec,f.config)
                changed=mode in ['changed','empty-with-context']; expected=f.normalized if changed else f.profile
                self.assertIs(f.item['ai_profile'],expected); self.assertIs(f.payload.call_args.args[2],expected)
                self.assertEqual(f.save.call_count,int(changed)); self.assertEqual(f.refs.call_count,int(mode.startswith('empty')))
                if mode=='empty-with-context': self.assertIs(f.normalized['reference_images'],f.contexts)

    def test_generation_status_error_preserves_only_prior_profile_assignment(self):
        f=self.f; f.item.pop('ai_profile'); error=OSError('status'); reads=[]
        class Generated(dict):
            def __getitem__(inner,key):
                reads.append(key)
                if key=='status': raise error
                return super().__getitem__(key)
        f.generated=Generated(profile={'accessory_id':'a'},status='ready')
        with self.assertRaises(OSError) as caught: self.analyze()
        self.assertIs(caught.exception,error); self.assertEqual(reads,['profile','status']); self.assertIs(f.item['ai_profile'],dict.__getitem__(f.generated,'profile'))
        self.assertNotIn('ai_profile_status',f.item); f.save.assert_not_called(); f.original.assert_not_called(); f.persist.assert_not_called()

    def test_debug_transport_overlays_copy_only_when_present_and_preserve_result_aliases(self):
        f=self.f
        for key in ['mcp_transport','mcp_runtime','mcp_dispatch_ms','mcp_fallback_from','mcp_fallback_error']: f.vision[key]=None
        self.assertIs(self.analyze()['ai'],f.debug)
        f.vision.update(mcp_transport='',mcp_runtime=False,mcp_dispatch_ms=0,mcp_fallback_from='old',mcp_fallback_error='reason')
        result=self.analyze(); self.assertIsNot(result['ai'],f.debug); self.assertEqual(f.debug,{'provider':'fixture'})
        self.assertEqual(result['ai'],{'provider':'fixture','mcp_transport':'','mcp_runtime':False,'mcp_dispatch_ms':0,'mcp_fallback_from':'old','mcp_fallback_error':'reason'})
        self.assertIs(result['rule'],f.rule); self.assertIs(result['detections'],f.detections)
        f.vision={'passed':'nonempty','rule':[],'detections':{},'ai':[]}; result=self.analyze()
        self.assertTrue(result['passed']); self.assertEqual(result['rule'],{}); self.assertEqual(result['detections'],[]); self.assertEqual(result['ai'],{})

    def test_snapshot_binding_uses_ambient_or_empty_record_and_restores_after_errors(self):
        f=self.f; f.spec['model_profiles']={'pipeline':{'version':99}}
        def required(*args): f.record('required',*args); f.resolver.version=2; return f.items
        f.required.side_effect=required
        self.analyze(); self.assertEqual(f.resolver.records,[{}]); self.assertIsNone(f.resolver.current_snapshot())
        self.assertTrue(all(e[3]['pipeline']['version']==1 for e in f.events))
        ambient={'pipeline':{'version':7,'secret_ref':'historical','prompt_version':'old'}}; f.events.clear()
        with f.resolver.scope(ambient):
            result=self.api.analyze_bgr_ai_detection(image_bgr=f.image,request_id='req',spec=f.spec,config=f.config)
            self.assertIs(f.resolver.current_snapshot(),ambient); self.assertTrue(result['passed'])
            self.assertTrue(all(e[3]==ambient for e in f.events)); self.assertEqual(f.resolver.records,[{}])
            error=OSError('vision'); f.tool.side_effect=error
            with self.assertRaises(OSError) as caught: self.analyze()
            self.assertIs(caught.exception,error); self.assertIs(f.resolver.current_snapshot(),ambient)
        self.assertIsNone(f.resolver.current_snapshot()); self.assertEqual(f.spec['model_profiles']['pipeline']['version'],99)
        f.required.reset_mock()
        with patch.object(self.api,'model_profile_service',None):
            with self.assertRaisesRegex(RuntimeError,'Model profile resolver is not configured'): self.analyze()
        f.required.assert_not_called()

    def test_first_errors_in_empty_and_full_flows_stop_and_restore_scope(self):
        for empty in [True,False]:
            stages=['required','original','failure','persist'] if empty else ['required','uid','normalize','payload','settings','external','original','model','persist']
            for stage in stages:
                with self.subTest(empty=empty,stage=stage), ExitStack() as stack:
                    f=AiAnalysisFixture(); f.bind(self.api,stack)
                    if empty: f.items=[]
                    port=getattr(f,stage); original=port.side_effect; error=OSError(stage); calls=0
                    def fail(*args,**kwargs):
                        nonlocal calls
                        calls+=1
                        if calls==1: f.record(stage,*args,**kwargs); raise error
                        return original(*args,**kwargs)
                    port.side_effect=fail
                    with self.assertRaises(OSError) as caught: self.api.analyze_bgr_ai_detection(f.image,'req',f.spec,f.config)
                    self.assertIs(caught.exception,error); self.assertEqual(calls,1); self.assertEqual(f.events[-1][0],stage)
                    self.assertIsNone(f.resolver.current_snapshot()); self.assertTrue(all(e[3] is not None for e in f.events))
                    if stage!='persist': f.persist.assert_not_called()


    def test_multiple_items_accumulate_profiles_refs_and_save_after_last_unchanged(self):
        f=self.f; first={'id':'a'}; virtual={'id':'v'}; last={'id':'b','ai_profile':{'accessory_id':'b','reference_images':[{'id':'existing'}]}}
        f.items=[(first,2),(virtual,3),(last,4)]; f.config={'accessories':[first,last]}; profiles={}; payloads={}; references={}
        f.normalize.side_effect=lambda profile,item:f.record('normalize',profile,item) or profile
        def payload(item,count,profile):
            f.record('payload',item,count,profile); value={'accessory_id':item['id'],'expected_count':count,'profile':profile}; payloads[item['id']]=value; return value
        f.payload.side_effect=payload
        def tool(name,args):
            f.record('tool:'+name,args)
            if name=='accessory.profile.generate':
                value={'accessory_id':args['accessory']['id'],'reference_images':[]}; profiles[args['accessory']['id']]=value; return {'profile':value,'status':'ready'}
            if name=='accessory.reference.collect':
                identity=args['accessory']['id']; values=[{'id':identity+'-1'},{'id':identity+'-2'}]; references[identity]=values; return {'references':values}
            return f.vision
        f.tool.side_effect=tool; result=self.analyze(); self.assertTrue(result['passed'])
        f.save.assert_called_once_with(f.config); self.assertEqual(f.normalize.call_count,1); self.assertIs(f.normalize.call_args.args[0],last['ai_profile'])
        self.assertIs(first['ai_profile'],profiles['a']); self.assertIs(virtual['ai_profile'],profiles['v'])
        args=f.tool.call_args_list[-1].args[1]
        self.assertEqual(args['required_accessory_refs'],[{'accessory_id':'a','expected_count':2},{'accessory_id':'v','expected_count':3},{'accessory_id':'b','expected_count':4}])
        self.assertEqual([p['accessory_id'] for p in args['required_accessories']],['a','v','b'])
        for value,identity in zip(args['required_accessories'],['a','v','b']): self.assertIs(value,payloads[identity])
        expected=[reference for identity in ['a','v','b'] for reference in references[identity]]
        self.assertEqual(len(args['reference_descriptors']),6)
        for value,reference in zip(args['reference_descriptors'],expected): self.assertIs(value,reference)
        self.assertEqual([entry.args[0] for entry in f.tool.call_args_list],['accessory.profile.generate','accessory.reference.collect','accessory.profile.generate','accessory.reference.collect','accessory.reference.collect','vision.inspect.presence'])
        names=[e[0] for e in f.events]; self.assertGreater(names.index('save'),max(i for i,n in enumerate(names) if n=='tool:accessory.reference.collect'))
        self.assertLess(names.index('save'),max(i for i,n in enumerate(names) if n=='settings'))

    def test_reference_limit_zero_negative_and_changed_after_comparison(self):
        f=self.f
        for limit in [0,-1]:
            with self.subTest(limit=limit), patch.object(self.api,'AI_REFERENCE_IMAGES_PER_ACCESSORY',limit):
                f.tool.reset_mock(); result=self.analyze(); self.assertTrue(result['passed'])
                self.assertEqual([entry.args[0] for entry in f.tool.call_args_list],['vision.inspect.presence'])
                self.assertEqual(f.tool.call_args.args[1]['reference_descriptors'],[])
        class Limit:
            def __gt__(inner,other): self.api.AI_REFERENCE_IMAGES_PER_ACCESSORY=7; return True
        with patch.object(self.api,'AI_REFERENCE_IMAGES_PER_ACCESSORY',Limit()):
            f.tool.reset_mock(); self.analyze(); self.assertEqual(f.tool.call_args_list[0].args[1]['max_images'],7)

    def test_mcp_and_write_stages_fail_once_before_later_work(self):
        for stage in ['generate','collect','vision','save','refs','mcp_image']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=AiAnalysisFixture(); f.bind(self.api,stack); error=OSError(stage); calls=0
                if stage in ['generate','save']: f.item.pop('ai_profile')
                if stage=='refs': f.normalized={'accessory_id':'a','reference_images':[]}
                if stage in ['vision','mcp_image']: f.external.side_effect=lambda:f.record('external') or True
                if stage in ['generate','collect','vision']:
                    target={'generate':'accessory.profile.generate','collect':'accessory.reference.collect','vision':'vision.inspect.presence'}[stage]
                    def tool(name,args):
                        nonlocal calls
                        if name==target:
                            calls+=1
                            if calls==1: f.record('tool:'+name,args); raise error
                        return f.call_tool(name,args)
                    f.tool.side_effect=tool; final='tool:'+target
                else:
                    port=getattr(f,stage); original=port.side_effect
                    def fail(*args,**kwargs):
                        nonlocal calls
                        calls+=1
                        if calls==1: f.record(stage,*args,**kwargs); raise error
                        return original(*args,**kwargs)
                    port.side_effect=fail; final=stage
                with self.assertRaises(OSError) as caught: self.api.analyze_bgr_ai_detection(f.image,'req',f.spec,f.config)
                self.assertIs(caught.exception,error); self.assertEqual(calls,1); self.assertEqual(f.events[-1][0],final)
                f.original.assert_not_called(); f.persist.assert_not_called(); self.assertIsNone(f.resolver.current_snapshot())
                if stage=='save': self.assertIs(f.item['ai_profile'],f.generated['profile']); self.assertEqual(f.item['ai_profile_status'],'ready')

    def test_tool_callee_capture_follows_prior_work_and_precedes_settings_and_path(self):
        f=self.f; f.item.pop('ai_profile'); before=f.tool; captured=Mock(side_effect=f.call_tool); later=Mock(side_effect=f.call_tool)
        f.uid.side_effect=lambda item:setattr(self.api,'call_ai_mcp_tool',captured) or item['id']
        def settings(*args):
            if args==('accessory',): self.api.call_ai_mcp_tool=later
            return f.settings_value
        f.settings.side_effect=settings; self.analyze()
        before.assert_not_called(); self.assertEqual([entry.args[0] for entry in captured.call_args_list],['accessory.profile.generate'])
        self.assertEqual([entry.args[0] for entry in later.call_args_list],['accessory.reference.collect','vision.inspect.presence'])
        f.uid.side_effect=lambda item:item['id']; self.api.call_ai_mcp_tool=f.tool; f.tool.reset_mock(); f.settings.side_effect=lambda *args:f.settings_value
        f.external.side_effect=lambda:True; bool_tool=Mock(side_effect=f.call_tool); string_tool=Mock(side_effect=f.call_tool)
        class ImagePath:
            def __bool__(inner): self.api.call_ai_mcp_tool=bool_tool; return True
            def __str__(inner): self.api.call_ai_mcp_tool=string_tool; return 'mcp-synthetic.jpg'
        f.mcp_image.side_effect=lambda *args:ImagePath(); f.normalized=f.item['ai_profile']; f.normalized['reference_images']=[{'id':'ref'}]
        self.analyze(); bool_tool.assert_not_called(); string_tool.assert_not_called()
        self.assertEqual(f.tool.call_args.args[0],'vision.inspect.presence'); self.assertEqual(f.tool.call_args.args[1]['inspection_image_path'],'mcp-synthetic.jpg')


    def test_independent_compositions_route_through_their_own_pinned_ai_services(self):
        from local_inspection_service.detection.ai_analysis import AiDetectionAnalysis
        from local_inspection_service.detection.analysis import DetectionAnalysis
        from local_inspection_service.detection.analysis_ports import AiProfiles,AiInspectionTools,AiAnalysisEvidence,AnalysisInput,AnalysisRouting,AnalysisInference,AnalysisOutput
        from local_inspection_service.model_profiles.snapshots import pinned
        from scripts.smoke_detection_analysis import AnalysisFixture
        services=[]
        for owner in ['alice','bob']:
            f=AiAnalysisFixture(); f.model_payload={'id':owner}; f.original.side_effect=lambda *args,owner=owner:owner+'/original.jpg'
            call_provider=Mock(return_value=f.tool); settings_provider=Mock(return_value=f.settings)
            ai=AiDetectionAnalysis(AiProfiles(f.required,f.uid,f.normalize,f.refs,f.payload,f.save),
                AiInspectionTools(call_provider,settings_provider,f.external,f.mcp_image,lambda:2,lambda:512,lambda:80),
                AiAnalysisEvidence(f.original,f.failure,f.model,f.persist))
            call_provider.assert_not_called(); settings_provider.assert_not_called(); self.assertEqual(f.events,[])
            bound=pinned(lambda f=f:f.resolver)(ai.analyze_bgr_ai_detection)
            ordinary=AnalysisFixture(Path(self.runtime.name)/owner); ordinary.spec={'id':'ai','is_ai_detection':True}; ordinary.scoped=f.config
            service=DetectionAnalysis(AnalysisInput(ordinary.load,lambda:ordinary.scope,ordinary.selected,lambda:ordinary.sanitize,ordinary.state_load),
                AnalysisRouting(Mock(),bound,ordinary.retired,lambda:ordinary.text),
                AnalysisInference(lambda:ordinary.model,ordinary.device,ordinary.parse,ordinary.ocr,ordinary.apply,ordinary.draw),
                AnalysisOutput(ordinary.directory,lambda:ordinary.resize,lambda:640,lambda:ordinary.backend,lambda:87,ordinary.url))
            services.append((owner,f,ordinary,service,call_provider,settings_provider))
        with ExitStack() as stack:
            for name in ['analyze_bgr','analyze_bgr_ai_detection','resolve_model_profiles','ai_required_accessories','accessory_uid','normalize_accessory_ai_profile',
                         'accessory_reference_image_contexts','required_accessory_profile_payload','ai_detection_settings','save_config','external_ai_mcp_enabled',
                         'write_mcp_inspection_image','call_ai_mcp_tool','write_ai_original_output','ai_model_payload','persist_data_analysis_record_for_ai_detection']:
                stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('root callback')))
            snapshots=[{'pipeline':{'version':7}},{'pipeline':{'version':9}}]
            with services[0][1].resolver.scope(snapshots[0]), services[1][1].resolver.scope(snapshots[1]):
                for repetition in [1,2]:
                    for index,(owner,f,ordinary,service,cp,sp) in enumerate(services):
                        f.events.clear(); result=service.analyze_bgr(f.image,'req','ai',image_path=Path(owner+'.png'))
                        self.assertEqual(result['model']['id'],owner); self.assertEqual(result['annotated_url'],owner+'/original.jpg')
                        self.assertTrue(all(event[3]==snapshots[index] for event in f.events)); self.assertEqual(f.resolver.records,[])
                        self.assertEqual(cp.call_count,2*repetition); self.assertEqual(sp.call_count,repetition); self.assertEqual(f.persist.call_count,repetition)
                        self.assertEqual(f.persist.call_args.kwargs,{'image_path':Path(owner+'.png')}); ordinary.model.assert_not_called()
                        for other,expected in zip(services,snapshots): self.assertIs(other[1].resolver.current_snapshot(),expected)
            for _,f,_,_,_,_ in services: self.assertIsNone(f.resolver.current_snapshot())

    def test_independent_tool_and_settings_provider_failures_stop_before_invocation(self):
        from local_inspection_service.detection.ai_analysis import AiDetectionAnalysis
        from local_inspection_service.detection.analysis_ports import AiProfiles,AiInspectionTools,AiAnalysisEvidence
        from local_inspection_service.model_profiles.snapshots import pinned
        for stage in ['tool','settings','resolver']:
            with self.subTest(stage=stage):
                f=AiAnalysisFixture(); f.item.pop('ai_profile'); error=OSError('provider')
                cp=Mock(return_value=f.tool); sp=Mock(return_value=f.settings)
                if stage=='tool': cp.side_effect=error
                if stage=='settings': sp.side_effect=error
                service=AiDetectionAnalysis(AiProfiles(f.required,f.uid,f.normalize,f.refs,f.payload,f.save),
                    AiInspectionTools(cp,sp,f.external,f.mcp_image,lambda:2,lambda:512,lambda:80),AiAnalysisEvidence(f.original,f.failure,f.model,f.persist))
                cp.assert_not_called(); sp.assert_not_called(); entry=pinned(lambda:None if stage=='resolver' else f.resolver)(service.analyze_bgr_ai_detection)
                with self.assertRaises(RuntimeError if stage=='resolver' else OSError) as caught: entry(f.image,'req',f.spec,f.config)
                if stage!='resolver': self.assertIs(caught.exception,error)
                else: self.assertIn('resolver is not configured',str(caught.exception)); f.required.assert_not_called()
                self.assertEqual(cp.call_count,int(stage!='resolver')); self.assertEqual(sp.call_count,int(stage=='settings'))
                f.settings.assert_not_called(); f.tool.assert_not_called(); f.persist.assert_not_called(); self.assertNotIn('ai_profile',f.item)
                self.assertIsNone(f.resolver.current_snapshot())


    def test_noncallable_tool_still_evaluates_generation_and_vision_arguments(self):
        for stage in ['generate','vision']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=AiAnalysisFixture(); f.bind(self.api,stack); events=[]; replacement=Mock(side_effect=f.call_tool)
                if stage=='generate':
                    f.item.pop('ai_profile'); self.api.call_ai_mcp_tool=None
                    def settings(*args): events.append(('settings',args)); self.api.call_ai_mcp_tool=replacement; return f.settings_value
                    f.settings.side_effect=settings
                else:
                    f.external.side_effect=lambda:True
                    class ImagePath:
                        def __bool__(inner): events.append('bool'); self.api.call_ai_mcp_tool=f.tool; return True
                        def __str__(inner): events.append('str'); self.api.call_ai_mcp_tool=replacement; return 'synthetic.jpg'
                    def image(*args): self.api.call_ai_mcp_tool=None; return ImagePath()
                    f.mcp_image.side_effect=image
                with self.assertRaises(TypeError): self.api.analyze_bgr_ai_detection(f.image,'req',f.spec,f.config)
                self.assertEqual(events,[('settings',('accessory',))] if stage=='generate' else ['bool','str'])
                replacement.assert_not_called(); self.assertEqual([c.args[0] for c in f.tool.call_args_list],[] if stage=='generate' else ['accessory.reference.collect'])
                f.original.assert_not_called(); f.model.assert_not_called(); f.persist.assert_not_called(); self.assertIsNone(f.resolver.current_snapshot())
                if stage=='generate': self.assertNotIn('ai_profile',f.item)

    def test_independent_noncallable_collect_reads_all_constant_arguments(self):
        from local_inspection_service.detection.ai_analysis import AiDetectionAnalysis
        from local_inspection_service.detection.analysis_ports import AiProfiles,AiInspectionTools,AiAnalysisEvidence
        from local_inspection_service.model_profiles.snapshots import pinned
        f=AiAnalysisFixture(); events=[]; cp=Mock(return_value=None); sp=Mock(return_value=f.settings)
        limit=Mock(side_effect=lambda:events.append('limit') or 2); side=Mock(side_effect=lambda:events.append('side') or 512)
        def quality(): events.append('quality'); cp.return_value=f.tool; return 80
        qp=Mock(side_effect=quality)
        service=AiDetectionAnalysis(AiProfiles(f.required,f.uid,f.normalize,f.refs,f.payload,f.save),
            AiInspectionTools(cp,sp,f.external,f.mcp_image,limit,side,qp),AiAnalysisEvidence(f.original,f.failure,f.model,f.persist))
        self.assertEqual(events,[]); cp.assert_not_called()
        with self.assertRaises(TypeError): pinned(lambda:f.resolver)(service.analyze_bgr_ai_detection)(f.image,'req',f.spec,f.config)
        self.assertEqual(events,['limit','limit','side','quality']); cp.assert_called_once(); sp.assert_not_called(); f.tool.assert_not_called()
        f.original.assert_not_called(); f.persist.assert_not_called(); self.assertIsNone(f.resolver.current_snapshot())


    def test_mapping_reads_preserve_first_error_and_partial_profile_state(self):
        windows=[('config','get','accessories',1),('item','get','ai_profile',1),('item','get','ai_profile',2),
                 ('profile','get','accessory_id',1),('normalized','get','reference_images',1),('normalized','get','reference_images',2),
                 ('generated','item','profile',1),('generated','item','profile',2),('generated','item','status',1),
                 ('references','get','references',1),('vision','get','ai',1),('vision','get','ai',2),
                 ('vision','get','rule',1),('vision','get','rule',2),('vision','get','detections',1),('vision','get','detections',2),
                 ('vision','get','mcp_transport',1),('vision','get','mcp_transport',2),('vision','get','passed',1)]
        for owner,operation,key,occurrence in windows:
            with self.subTest(owner=owner,key=key,occurrence=occurrence),ExitStack() as stack:
                f=AiAnalysisFixture();f.bind(self.api,stack);error=RuntimeError('mapping');reads=[];count=0
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
                f.profile=ReadMap('profile',f.profile);f.normalized=ReadMap('normalized',dict(f.profile))
                f.item=ReadMap('item',{'id':'a','ai_profile':f.profile});f.items=[(f.item,2)];f.config=ReadMap('config',{'accessories':[f.item]})
                f.generated=ReadMap('generated',f.generated);f.vision['mcp_transport']='synthetic';f.vision=ReadMap('vision',f.vision)
                if owner=='generated':f.item.pop('ai_profile')
                def tool(name,arguments):
                    if name=='accessory.reference.collect':return ReadMap('references',{'references':f.references})
                    return f.call_tool(name,arguments)
                f.tool.side_effect=tool
                with self.assertRaises(RuntimeError) as caught:self.api.analyze_bgr_ai_detection(f.image,'req',f.spec,f.config)
                self.assertIs(caught.exception,error);self.assertEqual(count,occurrence);self.assertEqual(reads[-1],(owner,operation,key));f.persist.assert_not_called();self.assertIsNone(f.resolver.current_snapshot())
                if owner=='generated':
                    self.assertEqual('ai_profile' in f.item,key=='status' or occurrence==2)
                    self.assertEqual('ai_profile_status' in f.item,key=='profile' and occurrence==2)

    def test_second_uid_and_generation_settings_fail_once(self):
        for stage in ('uid','settings'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=AiAnalysisFixture();f.bind(self.api,stack);f.item.pop('ai_profile');port=getattr(f,stage);original=port.side_effect;calls=0;error=OSError(stage)
                target=2 if stage=='uid' else 1
                def once(*args,**kwargs):
                    nonlocal calls
                    calls+=1
                    if calls==target:raise error
                    return original(*args,**kwargs)
                port.side_effect=once
                with self.assertRaises(OSError) as caught:self.api.analyze_bgr_ai_detection(f.image,'req',f.spec,f.config)
                self.assertIs(caught.exception,error);self.assertEqual(calls,target);f.tool.assert_not_called();f.persist.assert_not_called();self.assertNotIn('ai_profile',f.item);self.assertIsNone(f.resolver.current_snapshot())

    def test_independent_provider_and_reference_policies_fail_once_at_each_read(self):
        from local_inspection_service.detection.ai_analysis import AiDetectionAnalysis
        from local_inspection_service.detection.analysis_ports import AiProfiles,AiInspectionTools,AiAnalysisEvidence
        from local_inspection_service.model_profiles.snapshots import pinned
        for stage,occurrence in [('tool',1),('tool',2),('tool',3),('settings',1),('settings',2),('limit',1),('limit',2),('side',1),('quality',1)]:
            with self.subTest(stage=stage,occurrence=occurrence):
                f=AiAnalysisFixture();f.item.pop('ai_profile');error=OSError(stage);counts={}
                def provider(name,value):
                    def read():
                        counts[name]=counts.get(name,0)+1
                        if name==stage and counts[name]==occurrence:raise error
                        return value
                    return read
                service=AiDetectionAnalysis(AiProfiles(f.required,f.uid,f.normalize,f.refs,f.payload,f.save),
                    AiInspectionTools(provider('tool',f.tool),provider('settings',f.settings),f.external,f.mcp_image,provider('limit',2),provider('side',512),provider('quality',80)),
                    AiAnalysisEvidence(f.original,f.failure,f.model,f.persist))
                entry=pinned(lambda:f.resolver)(service.analyze_bgr_ai_detection)
                with self.assertRaises(OSError) as caught:entry(f.image,'req',f.spec,f.config)
                self.assertIs(caught.exception,error);self.assertEqual(counts[stage],occurrence);f.persist.assert_not_called();self.assertIsNone(f.resolver.current_snapshot())


    def test_tool_and_settings_refresh_between_accessories(self):
        for mode in ('generate','collect'):
            with self.subTest(mode=mode):capture_ai_refresh(self.api,AiAnalysisFixture,mode)


if __name__=='__main__': unittest.main()

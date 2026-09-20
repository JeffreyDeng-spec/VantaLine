"""Draft synthetic contracts for unchanged Agent pose planning."""
import os,sys,tempfile,unittest,hashlib
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path.cwd()))
class AgentPosePlanningContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env=patch.dict(os.environ);cls.env.start();cls.tmp=tempfile.TemporaryDirectory(prefix='pose-planning-');(Path(cls.tmp.name)/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=cls.tmp.name,VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup();cls.env.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for n in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):
            self.stack.enter_context(patch(n,side_effect=AssertionError('external operation forbidden')))
    def patch(self,name,**kw):return self.stack.enter_context(patch.object(self.api,name,**kw))
    def scene(self):
        self.patch('accessory_material_type',return_value='object');self.patch('accessory_uid',return_value='part');self.patch('agent_mcp_now',return_value=123);self.patch('clean_sprite_assets',return_value=[]);self.patch('agent_mcp_object_kind',return_value='generic_object')
    def test_payload_preserves_dimensions_names_bounds_and_cutout_flag(self):
        self.scene();self.patch('object_physical_size_mm',return_value=(12.34,5.67,8.99));self.patch('clean_sprite_assets',return_value=[{}]);item={'name':'part name','description':'x'*300,'ai_profile':{'english_name':'gear','material_type':'steel','top_view_aspect_ratio':2},'physical_size':{}}
        value=self.api.accessory_pose_plan_prompt_payload(item);self.assertEqual(value['physical_dimensions_mm'],{'length_mm':12.3,'width_mm':5.7,'height_mm':9.0});self.assertEqual((value['accessory_id'],value['object_name'],value['english_name'],value['material_type']),('part','part name','gear','object'));self.assertEqual(len(value['description']),240);self.assertTrue(value['has_transparent_cutout']);self.assertTrue(value['single_image_inference_allowed']);self.assertEqual(value['max_poses'],self.api.AGENT_MCP_POSE_PLAN_MAX_POSES)
    def test_system_prompt_exact_baseline(self):
        self.assertEqual(hashlib.sha256(self.api.pose_plan_system_prompt().encode()).hexdigest(),'3d8ab1676216ff2d8ae3fae5f7149219ff497470d6c413a42c49fa3645d5ddd9')
    def test_fallback_preserves_schema_template_order_and_fresh_requests(self):
        self.scene();self.patch('agent_mcp_pose_templates',return_value=[{'pose_id':'a','label':'A','stable_contact':'base'},{'pose_id':'b','label':'B','stable_contact':'side'}]);result=self.api.fallback_accessory_pose_plan({'name':'part name'});self.assertEqual((result['accessory_id'],result['pose_decision_source'],result['pose_count'],result['generated_at']),('part','rules_fallback',2,123));self.assertEqual([p['pose_id'] for p in result['poses']],['a','b']);self.assertEqual(result['poses'][0]['confidence'],0.5);self.assertIsNot(result['poses'][0]['request'],result['poses'][1]['request']);self.assertEqual(result['schema_version'],self.api.AGENT_MCP_POSE_PLAN_VERSION)
    def test_normalization_constructs_and_returns_fallback_for_invalid_or_empty_input(self):
        fallback={'fallback':True};fn=self.patch('fallback_accessory_pose_plan',return_value=fallback)
        for raw in (None,{}, {'poses':[]}):self.assertIs(self.api.normalize_accessory_pose_plan(raw,{}),fallback)
        self.assertEqual(fn.call_count,3)
    def test_normalization_preserves_filter_dedupe_limits_and_review_flag(self):
        self.scene();self.patch('fallback_accessory_pose_plan',return_value={'fallback':True});self.patch('AGENT_MCP_POSE_PLAN_MIN_CONFIDENCE',new=0.3);self.patch('AGENT_MCP_POSE_PLAN_MAX_POSES',new=2)
        def pose(name,**kw):return dict(pose_id=name,generation_prompt='render',stable_contact_surface='flat base',confidence=0.4,**kw)
        raw={'poses':[{'generation_prompt':''},{'generation_prompt':'render','stable_contact_surface':'corner'},pose('one'),pose('one'),pose('two'),pose('three')],'estimated_geometry':{'kind':'gear','symmetry':['axis']}}
        result=self.api.normalize_accessory_pose_plan(raw,{});self.assertEqual([p['pose_id'] for p in result['poses']],['part_one','part_two']);self.assertTrue(result['needs_human_review']);self.assertEqual(result['pose_count'],2);self.assertEqual(result['generated_at'],123);self.assertEqual(result['estimated_geometry']['kind'],'gear')
    def test_generate_text_returns_before_settings_and_provider(self):
        self.patch('accessory_material_type',return_value='text');settings=self.patch('ai_detection_settings');tool=self.patch('call_ai_mcp_tool');self.assertIsNone(self.api.generate_accessory_pose_plan({}));settings.assert_not_called();tool.assert_not_called()
    def test_generate_cache_identity_reused_before_settings(self):
        self.scene();plan={'accessory_id':'part','poses':[{}]};settings=self.patch('ai_detection_settings');tool=self.patch('call_ai_mcp_tool');self.assertIs(self.api.generate_accessory_pose_plan({'agent_mcp_pose_plan':plan}),plan);settings.assert_not_called();tool.assert_not_called()
    def test_disabled_provider_still_reads_settings_then_stores_fallback(self):
        self.scene();settings=self.patch('ai_detection_settings',return_value={'configured':True});plan={'fallback':True};self.patch('fallback_accessory_pose_plan',return_value=plan);tool=self.patch('call_ai_mcp_tool');item={}
        with patch.object(self.api.time,'time',return_value=123.9):self.assertIs(self.api.generate_accessory_pose_plan(item,allow_provider=False),plan)
        settings.assert_called_once_with('training_vision');tool.assert_not_called();self.assertIs(item['agent_mcp_pose_plan'],plan);self.assertEqual(item['agent_mcp_pose_plan_status'],{'source':'rules_fallback','status':'fallback','message':'AI provider not configured; used rule templates.','updated_at':123})
    def test_reference_collection_error_still_generates_once_and_keeps_settings_identity(self):
        self.scene();settings={'configured':True};self.patch('ai_detection_settings',return_value=settings);self.patch('accessory_pose_plan_prompt_payload',return_value={'synthetic':'part'});self.patch('pose_plan_system_prompt',return_value='synthetic prompt');plan={'pose_decision_source':'vision_agent','needs_human_review':False};normal=self.patch('normalize_accessory_pose_plan',return_value=plan);events=[]
        def tool(name,args):
            events.append((name,args))
            if name=='accessory.reference.collect':raise RuntimeError('synthetic collection error')
            return {'ok':True,'parsed':{'poses':[]},'latency_ms':8}
        self.patch('call_ai_mcp_tool',side_effect=tool);item={}
        with patch.object(self.api.time,'time',return_value=123):self.assertIs(self.api.generate_accessory_pose_plan(item),plan)
        self.assertEqual([e[0] for e in events],['accessory.reference.collect','provider.gemini.generate_json']);self.assertIs(events[1][1]['provider_config'],settings);self.assertEqual(events[1][1]['max_tokens'],1400);self.assertEqual(events[1][1]['system_prompt'],'synthetic prompt');self.assertEqual(len(events[1][1]['user_content']),1);normal.assert_called_once();self.assertEqual(item['agent_mcp_pose_plan_status']['latency_ms'],8)
    def test_provider_negative_result_retains_timeout_and_error_status(self):
        self.scene();self.patch('ai_detection_settings',return_value={'configured':True});self.patch('accessory_pose_plan_prompt_payload',return_value={});plan={};self.patch('fallback_accessory_pose_plan',return_value=plan)
        for timed_out,status in ((True,'timeout'),(False,'provider_error')):
            def tool(name,args):return {'references':[]} if name=='accessory.reference.collect' else {'ok':False,'timed_out':timed_out,'error':'e'*300}
            self.patch('call_ai_mcp_tool',side_effect=tool);item={};self.assertIs(self.api.generate_accessory_pose_plan(item),plan);self.assertEqual(item['agent_mcp_pose_plan_status']['status'],status);self.assertEqual(len(item['agent_mcp_pose_plan_status']['message']),240)
    def test_unknown_provider_exception_escapes_without_retry_or_fallback(self):
        self.scene();self.patch('ai_detection_settings',return_value={'configured':True});self.patch('accessory_pose_plan_prompt_payload',return_value={});fallback=self.patch('fallback_accessory_pose_plan');error=RuntimeError('synthetic unknown');calls=[]
        def tool(name,args):
            calls.append(name)
            if name=='accessory.reference.collect':return {'references':[]}
            raise error
        self.patch('call_ai_mcp_tool',side_effect=tool);item={}
        with self.assertRaises(RuntimeError) as caught:self.api.generate_accessory_pose_plan(item)
        self.assertIs(caught.exception,error);self.assertEqual(calls,['accessory.reference.collect','provider.gemini.generate_json']);fallback.assert_not_called();self.assertEqual(item,{})
    def test_force_bypasses_cache_and_clock_error_retains_plan_assignment(self):
        self.scene();self.patch('ai_detection_settings',return_value={'configured':False});new={'new':True};self.patch('fallback_accessory_pose_plan',return_value=new);old={'accessory_id':'part','poses':[{}]};status={'old':True};item={'agent_mcp_pose_plan':old,'agent_mcp_pose_plan_status':status}
        with patch.object(self.api.time,'time',side_effect=RuntimeError('synthetic clock')):
            with self.assertRaises(RuntimeError):self.api.generate_accessory_pose_plan(item,force=True)
        self.assertIs(item['agent_mcp_pose_plan'],new);self.assertIs(item['agent_mcp_pose_plan_status'],status)
    def test_ensure_keeps_text_shortcut_and_force_keyword(self):
        material=self.patch('accessory_material_type',return_value='text');generate=self.patch('generate_accessory_pose_plan',return_value={'plan':True});self.assertIsNone(self.api.ensure_accessory_pose_plan({},force=True));generate.assert_not_called();material.return_value='object';self.assertIs(self.api.ensure_accessory_pose_plan({},force=True),generate.return_value);generate.assert_called_once_with({},force=True)
    def test_task_assembly_skips_unknown_text_and_retains_pose_request_identity(self):
        self.scene();obj={'name':'gear'};text={'text':True};config={};request={'owner':'caller'};plan={'poses':[{'pose_id':'p','label':'P','stable_contact_surface':'base','request':request}],'estimated_geometry':{'kind':'gear'},'needs_human_review':True};self.patch('accessory_lookup_by_id',return_value={'a':obj,'text':text});self.patch('canonical_pipeline_accessory_ids',return_value=['missing','text','a']);self.patch('normalize_pipeline_accessory_counts',return_value={'a':3});self.patch('accessory_material_type',side_effect=lambda item:'text' if item is text else 'object');ensure=self.patch('ensure_accessory_pose_plan',return_value=plan);result=self.api.build_agent_mcp_pose_plan({'id':'task','accessory_ids':['a']},config)
        self.assertEqual(result['pose_count'],1);self.assertEqual(len(result['accessories']),1);entry=result['accessories'][0];self.assertEqual((entry['accessory_id'],entry['count'],entry['object_kind']),('a',3,'gear'));self.assertIs(entry['poses'][0]['request'],request);self.assertTrue(entry['needs_human_review']);ensure.assert_called_once_with(obj)
    def test_task_assembly_missing_plan_uses_template_list_identity(self):
        self.scene();item={'name':'part'};poses=[{'pose_id':'p'}];self.patch('accessory_lookup_by_id',return_value={'a':item});self.patch('canonical_pipeline_accessory_ids',return_value=['a']);self.patch('normalize_pipeline_accessory_counts',return_value={});self.patch('ensure_accessory_pose_plan',return_value=None);templates=self.patch('agent_mcp_pose_templates',return_value=poses);result=self.api.build_agent_mcp_pose_plan({'id':'task','accessory_ids':['a']},{})
        self.assertIs(result['accessories'][0]['poses'],poses);self.assertEqual(result['accessories'][0]['plan_source'],'preview_agent_rules');self.assertEqual(result['generated_at'],123);templates.assert_called_once_with('a','generic_object')
    def test_normalizer_eager_fallback_is_called_even_for_valid_plan(self):
        self.scene();fallback=self.patch('fallback_accessory_pose_plan',return_value={'fallback':True});raw={'poses':[{'pose_id':'p','generation_prompt':'render','stable_contact_surface':'base','confidence':0.9}]};result=self.api.normalize_accessory_pose_plan(raw,{});self.assertEqual(result['pose_decision_source'],'vision_agent');fallback.assert_called_once_with({})
    def test_generation_tool_callback_selected_before_system_prompt(self):
        self.scene();self.patch('ai_detection_settings',return_value={'configured':True});self.patch('accessory_pose_plan_prompt_payload',return_value={});self.patch('normalize_accessory_pose_plan',return_value={'pose_decision_source':'vision_agent'});api=self.api;later=Mock(return_value={'ok':False});events=[]
        def original(name,args):events.append(name);return {'references':[]} if name=='accessory.reference.collect' else {'ok':True,'parsed':{}}
        first=self.patch('call_ai_mcp_tool',side_effect=original)
        def prompt():api.call_ai_mcp_tool=later;return 'synthetic prompt'
        self.patch('pose_plan_system_prompt',side_effect=prompt);self.api.generate_accessory_pose_plan({});self.assertEqual(events,['accessory.reference.collect','provider.gemini.generate_json']);self.assertEqual(first.call_count,2);later.assert_not_called()
    def test_reference_collection_interrupt_escapes_without_generation(self):
        self.scene();self.patch('ai_detection_settings',return_value={'configured':True});self.patch('accessory_pose_plan_prompt_payload',return_value={});self.patch('normalize_accessory_pose_plan',return_value={'pose_decision_source':'vision_agent'});events=[];error=KeyboardInterrupt('synthetic collection interrupt')
        def tool(name,args):
            events.append(name)
            if name=='accessory.reference.collect':raise error
            return {'ok':True,'parsed':{}}
        self.patch('call_ai_mcp_tool',side_effect=tool);item={}
        with self.assertRaises(KeyboardInterrupt) as caught:self.api.generate_accessory_pose_plan(item)
        self.assertIs(caught.exception,error);self.assertEqual(events,['accessory.reference.collect']);self.assertEqual(item,{})
    def test_fallback_status_clock_selected_after_plan_factory(self):
        self.scene();self.patch('ai_detection_settings',return_value={'configured':False});later=Mock(return_value=202.9);old=self.stack.enter_context(patch.object(self.api.time,'time',return_value=101.9));api=self.api
        def fallback(item):api.time.time=later;return {'fallback':True}
        self.patch('fallback_accessory_pose_plan',side_effect=fallback);item={};self.api.generate_accessory_pose_plan(item);self.assertEqual(item['agent_mcp_pose_plan_status']['updated_at'],202);old.assert_not_called();later.assert_called_once()


    def test_planning_constructors_do_not_read_capabilities(self):
        from dataclasses import fields
        from local_inspection_service.agent import pose_plan_ports as p
        from local_inspection_service.agent.pose_plan_policy import PosePlanPolicy
        from local_inspection_service.agent.pose_plan_generation import PosePlanGeneration
        from local_inspection_service.agent.pose_plan_assembly import PosePlanAssembly
        getters=[]
        def group(port_type):
            values={f.name:Mock(return_value=None) for f in fields(port_type)};getters.extend(values.values());return port_type(**values)
        PosePlanPolicy(group(p.PosePlanIdentity),group(p.PosePlanContent),group(p.PosePlanRuntime),group(p.PosePlanTemplates));PosePlanGeneration(group(p.PosePlanIdentity),group(p.PosePlanContent),group(p.PosePlanRuntime),group(p.PosePlanTemplates),group(p.PosePlanProvider),group(p.PosePlanMedia),group(p.PosePlanCalls));PosePlanAssembly(group(p.PosePlanIdentity),group(p.PosePlanRuntime),group(p.PosePlanTemplates),group(p.PosePlanCatalog))
        for getter in getters:getter.assert_not_called()
    def test_two_live_planning_compositions_remain_independent(self):
        from dataclasses import fields
        from local_inspection_service.agent import pose_plan_ports as p
        from local_inspection_service.agent.pose_plan_policy import PosePlanPolicy
        from local_inspection_service.agent.pose_plan_generation import PosePlanGeneration
        from local_inspection_service.agent.pose_plan_assembly import PosePlanAssembly
        def group(port_type,**selected):return port_type(**{f.name:selected.get(f.name,lambda:None) for f in fields(port_type)})
        def make(name):
            identity=group(p.PosePlanIdentity,uid=lambda:lambda item:name,material=lambda:lambda item:'object',kind=lambda:lambda item:'generic_object',sanitize=lambda:lambda raw:raw)
            content=group(p.PosePlanContent,size=lambda:lambda size:(1.,2.,3.),sprites=lambda:lambda item:[],bounded=lambda:lambda value,limit:str(value)[:limit])
            runtime=group(p.PosePlanRuntime,now=lambda:lambda:len(name),clock=lambda:lambda:len(name)+0.9,max_poses=lambda:6)
            templates=group(p.PosePlanTemplates,fallback=lambda:lambda item:{'owner':name})
            policy=PosePlanPolicy(identity,content,runtime,templates)
            generation=PosePlanGeneration(identity,content,runtime,templates,group(p.PosePlanProvider,settings=lambda:lambda purpose:{'configured':False}),group(p.PosePlanMedia),group(p.PosePlanCalls))
            request={'owner':name};catalog=group(p.PosePlanCatalog,lookup=lambda:lambda config:{'part':{'name':name}},counts=lambda:lambda *args:{'part':len(name)},canonical_ids=lambda:lambda *args:['part'],ensure=lambda:lambda item:{'poses':[{'pose_id':'pose','request':request}]})
            assembly=PosePlanAssembly(identity,runtime,templates,catalog)
            return policy,generation,assembly,request
        instances={name:make(name) for name in ('first','second')}
        with patch.object(self.api,'accessory_uid',side_effect=AssertionError('root uid')),patch.object(self.api,'fallback_accessory_pose_plan',side_effect=AssertionError('root fallback')),patch.object(self.api,'ai_detection_settings',side_effect=AssertionError('root settings')),patch.object(self.api,'ensure_accessory_pose_plan',side_effect=AssertionError('root ensure')):
            for name in ('first','second','first'):
                policy,generation,assembly,request=instances[name];self.assertEqual(policy.accessory_pose_plan_prompt_payload({})['accessory_id'],name);self.assertEqual(policy.normalize_accessory_pose_plan(None,{}),{'owner':name});item={};self.assertEqual(generation.generate_accessory_pose_plan(item),{'owner':name});self.assertEqual(item['agent_mcp_pose_plan_status']['updated_at'],len(name));result=assembly.build_agent_mcp_pose_plan({'accessory_ids':['part']},{});self.assertIs(result['accessories'][0]['poses'][0]['request'],request);self.assertEqual(result['accessories'][0]['count'],len(name));self.assertEqual(result['generated_at'],len(name))


if __name__=='__main__':unittest.main()

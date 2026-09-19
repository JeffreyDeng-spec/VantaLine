"""Draft baseline for Agent pipeline decision helpers; all inputs are synthetic."""
import json,os,sys,tempfile,unittest
from contextlib import ExitStack,contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path.cwd()))

class AgentPipelineDecisionContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ);cls.environment.start();cls.root=tempfile.TemporaryDirectory(prefix='agent-pipeline-decision-')
        (Path(cls.root.name)/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=cls.root.name,VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.root.cleanup();cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for name in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):
            self.stack.enter_context(patch(name,side_effect=AssertionError('external operation forbidden')))
    def patch(self,name,**kwargs):return self.stack.enter_context(patch.object(self.api,name,**kwargs))
    def resolver(self):
        events=[]
        @contextmanager
        def scope(snapshot):
            events.append(('enter',snapshot))
            try:yield
            finally:events.append(('exit',snapshot))
        service=SimpleNamespace(current_snapshot=Mock(return_value=None),snapshot_for_record=Mock(return_value={'synthetic':'fresh'}),scope=scope)
        self.patch('model_profile_service',new=service)
        return service,events
    def quality_dependencies(self,orch=None):
        self.patch('agent_mcp_orchestration',return_value=orch or {})
        self.patch('canonical_pipeline_accessory_ids',side_effect=lambda config,ids:ids)
        self.patch('normalize_pipeline_accessory_counts',return_value={'a':2,'b':1})
        self.patch('agent_mcp_gemini_image_config',return_value={'configured':True})
        self.patch('agent_mcp_missing_existing_asset_names',return_value=list('abcdefgh'))
        self.patch('linked_training_job',return_value=None)
    def test_conversation_entry_and_bounded_history(self):
        conversation=[{'id':'prior0'},{'id':'prior1'}];orch={'conversation':conversation}
        self.patch('agent_mcp_orchestration',return_value=orch);self.patch('AGENT_MCP_CONVERSATION_LIMIT',new=2)
        clock_calls=[]
        def now():
            clock_calls.append(None);return 101 if len(clock_calls)==1 else 102
        self.patch('agent_mcp_now',side_effect=now);self.stack.enter_context(patch.object(self.api.uuid,'uuid4',return_value=SimpleNamespace(hex='0123456789abcdef')))
        entry=self.api.agent_mcp_append_conversation({},'assistant','x'*900,action='reply',reason='r'*500,target_stage='samples',source='rules',needs_user=True,agent_error='e'*300)
        self.assertIs(conversation[-1],entry);self.assertEqual(conversation[0],{'id':'prior1'});self.assertIs(orch['conversation'],conversation)
        self.assertEqual(entry,{'id':'msg_0123456789','role':'assistant','message':'x'*800,'created_at':101,'action':'reply','reason':'r'*400,'target_stage':'samples','source':'rules','needs_user':True,'agent_error':'e'*200});self.assertEqual(orch['updated_at'],102)
    def test_conversation_omits_false_optional_fields(self):
        orch={};self.patch('agent_mcp_orchestration',return_value=orch);self.patch('agent_mcp_now',return_value=1)
        entry=self.api.agent_mcp_append_conversation({},'user','hello')
        self.assertEqual(set(entry),{'id','role','message','created_at'});self.assertIs(orch['conversation'][0],entry)
    def test_quality_counts_job_metrics_and_bounded_assets(self):
        orch={'tool_calls':[{'tool':self.api.AGENT_MCP_TOOL_POSE_IMAGE,'status':status} for status in ('completed','failed','running')]+[{'tool':'other','status':'completed'}],'skip_pose_image_generation':True}
        self.quality_dependencies(orch);job={'status':'running','note':'n'*300,'current_epoch':0,'epochs':5,'map50':0,'precision':0.8}
        self.patch('linked_training_job',return_value=job)
        result=self.api.agent_pipeline_quality_signals({'accessory_ids':['a','b'],'params':{'sample_count':100},'last_error':'e'*300},{})
        self.assertEqual(result,{'accessory_count':2,'accessory_unit_total':3,'sample_count':100,'samples_per_accessory_unit':33.3,'pose_images_total':3,'pose_images_completed':1,'pose_images_failed':1,'skip_pose_image_generation':True,'image_generation_configured':True,'missing_assets':list('abcdef'),'linked_job_status':'running','linked_job_note':'n'*200,'current_epoch':0,'total_epochs':5,'map50':0,'precision':0.8,'last_error':'e'*200})
    def test_quality_optional_failures_fall_back_independently(self):
        self.quality_dependencies();self.patch('agent_mcp_missing_existing_asset_names',side_effect=RuntimeError('assets'));self.patch('linked_training_job',side_effect=RuntimeError('job'))
        result=self.api.agent_pipeline_quality_signals({'params':None},{})
        self.assertEqual(result['missing_assets'],[]);self.assertNotIn('linked_job_status',result);self.assertNotIn('samples_per_accessory_unit',result)
    def test_context_projects_only_existing_fields(self):
        orch={'state':'running','active_stage':'training','pause':{'reason':'ask','suggested_actions':['retry'],'private':'hidden'},'conversation':[{'role':'user','message':str(i),'action':'reply','private':'hidden'} for i in range(10)],'stages':[{'key':'training','status':'running','progress':40,'private':'hidden'}]}
        self.patch('agent_mcp_orchestration',return_value=orch);self.patch('accessory_lookup_by_id',return_value={'a':{'name':'synthetic'}});self.patch('canonical_pipeline_accessory_ids',return_value=['a','missing']);self.patch('normalize_pipeline_accessory_counts',return_value={'a':2});self.patch('accessory_material_type',return_value='object');self.patch('normalize_pipeline_detection_method',return_value='yolo');signals={};self.patch('agent_pipeline_quality_signals',return_value=signals)
        result=self.api.agent_pipeline_context({'id':'task','stage':'training','params':{'sample_count':50,'private':'hidden'}},{},None,'auto')
        self.assertEqual(result['accessories'],[{'name':'synthetic','material_type':'object','count':2}]);self.assertEqual([e['message'] for e in result['recent_conversation']],list(map(str,range(2,10))));self.assertEqual(result['orchestration']['pause'],{'reason':'ask','suggested_actions':['retry']});self.assertNotIn('private',json.dumps(result));self.assertIs(result['quality_signals'],signals);self.assertIs(result['stage_order'],self.api.PIPELINE_STAGE_ORDER);self.assertEqual(result['user_message'],'')
    def test_normalize_decision_clamps_and_filters(self):
        source={'action':' SET_PARAMS ','params':{'sample_count':1,'epochs':900,'image_size':'160','train_mode':'yolo_ocr','private':'hidden'},'target_stage':' SAMPLES ','reason':'reason','suggested_actions':['','retry']};before=json.dumps(source)
        result=self.api.normalize_agent_pipeline_decision(source)
        self.assertEqual(result['action'],'set_params');self.assertEqual(result['params'],{'sample_count':50,'epochs':500,'image_size':320,'train_mode':'yolo_ocr'});self.assertEqual(result['target_stage'],'samples');self.assertEqual(result['message_to_user'],'reason');self.assertEqual(result['suggested_actions'],['retry']);self.assertEqual(json.dumps(source),before)
    def test_normalize_unknown_and_invalid_values(self):
        result=self.api.normalize_agent_pipeline_decision({'action':'unknown','params':{'sample_count':'bad','epochs':None,'train_mode':'other'},'target_stage':'library'})
        self.assertEqual(result['action'],'reply');self.assertEqual(result['params'],{});self.assertEqual(result['target_stage'],'');self.assertEqual(result['message_to_user'],'已处理你的请求。');self.assertTrue(self.api.normalize_agent_pipeline_decision({'action':'pause_and_ask'})['needs_user'])
    def test_rule_rerun_stage_mapping(self):
        for stage,expected in [('draft',('advance','')),('samples',('goto_stage','samples')),('training',('goto_stage','samples')),('library',('goto_stage','samples'))]:self.assertEqual(self.api._rule_rerun_failed_stage(stage),expected)
    def test_rule_user_intent_priority_and_failed_stage(self):
        cases=[('取消并继续','samples','failed','cancel',''),('从头重来','samples','failed','goto_stage','draft'),('继续','training','failed','goto_stage','samples'),('train','samples','completed','continue_training',''),('reuse existing asset','draft','ready','continue_existing_assets','')]
        for text,stage,status,action,target in cases:
            with self.subTest(text=text):
                result=self.api.agent_pipeline_rule_decision({'stage':stage,'status':status},text,'chat');self.assertEqual((result['action'],result['target_stage'],result['source']),(action,target,'rules'))
    def test_rule_automatic_progress_failure_and_idle(self):
        for stage,status,action in [('samples','completed','advance'),('training','failed','pause_and_ask'),('draft','ready','reply')]:self.assertEqual(self.api.agent_pipeline_rule_decision({'stage':stage,'status':status},None,'auto')['action'],action)
    def test_decide_uses_bound_snapshot_and_exact_prompt(self):
        service,events=self.resolver();snapshot={'synthetic':'old'};task={'model_profiles':snapshot};config={'profile_id':'bound'};context={'synthetic':'context'};decision={'synthetic':'decision'}
        self.patch('load_agent_config',return_value=config);self.patch('agent_recommendation_supported',return_value=True);self.patch('agent_pipeline_context',return_value=context);chat=self.patch('agent_chat_completion',return_value='synthetic-json');parse=self.patch('parse_agent_json',return_value={'parsed':True});normalize=self.patch('normalize_agent_pipeline_decision',return_value=decision)
        self.assertIs(self.api.agent_pipeline_decide(task,{},user_message='hello'),decision);chat.assert_called_once_with([{'role':'system','content':self.api.AGENT_PIPELINE_SYSTEM_PROMPT},{'role':'user','content':json.dumps(context,ensure_ascii=False)}],config);parse.assert_called_once_with('synthetic-json');normalize.assert_called_once_with({'parsed':True});self.assertEqual(events,[('enter',snapshot),('exit',snapshot)]);service.current_snapshot.assert_not_called();service.snapshot_for_record.assert_not_called()
    def test_decide_disabled_uses_rules_without_context_or_chat(self):
        self.resolver();self.patch('load_agent_config',return_value={});self.patch('agent_recommendation_supported',return_value=False);rules=self.patch('agent_pipeline_rule_decision',return_value={'source':'rules'});context=self.patch('agent_pipeline_context');chat=self.patch('agent_chat_completion')
        self.assertEqual(self.api.agent_pipeline_decide({}, {},trigger='auto'),{'source':'rules'});rules.assert_called_once_with({},None,'auto');context.assert_not_called();chat.assert_not_called()
    def test_decide_transport_failure_keeps_rule_fallback_and_no_retry(self):
        self.resolver();self.patch('load_agent_config',return_value={});self.patch('agent_recommendation_supported',return_value=True);self.patch('agent_pipeline_context',return_value={});calls=[]
        def completion(*args,**kwargs):
            calls.append(None)
            if len(calls)==1:raise RuntimeError('e'*250)
            return '{"action":"reply"}'
        chat=self.patch('agent_chat_completion',side_effect=completion);fallback={'source':'rules'};self.patch('agent_pipeline_rule_decision',return_value=fallback)
        self.assertIs(self.api.agent_pipeline_decide({},{}),fallback);self.assertEqual(fallback['agent_error'],'e'*200);chat.assert_called_once()

    def test_conversation_second_clock_failure_preserves_append_and_trim(self):
        error=RuntimeError('synthetic second clock');calls=[];conversation=[{'id':'prior'}];orch={'conversation':conversation,'updated_at':7}
        def now():
            calls.append(None)
            if len(calls)==2:raise error
            return 101
        self.patch('agent_mcp_orchestration',return_value=orch);self.patch('agent_mcp_now',side_effect=now);self.patch('AGENT_MCP_CONVERSATION_LIMIT',new=1)
        with self.assertRaises(RuntimeError) as caught:self.api.agent_mcp_append_conversation({},'user','new')
        self.assertIs(caught.exception,error);self.assertEqual(len(calls),2);self.assertEqual(len(conversation),1);self.assertIn('message',conversation[0]);self.assertEqual(conversation[0]['message'],'new');self.assertEqual(orch['updated_at'],7)

    def test_normalizer_resolves_formatter_at_each_original_use(self):
        def later(value,limit):return 'later:'+str(value)
        def first(value,limit):self.api.bounded_text=later;return 'first:'+str(value)
        with patch.object(self.api,'bounded_text',side_effect=first):
            result=self.api.normalize_agent_pipeline_decision({'message_to_user':'message','reason':'reason','suggested_actions':['retry']})
        self.assertEqual((result['message_to_user'],result['reason'],result['suggested_actions']),('first:message','later:reason',['later:retry']))

    def test_quality_canonical_callee_selected_before_identifier_conversion(self):
        self.quality_dependencies();selected=Mock(return_value=['a']);late=Mock(return_value=[]);api=self.api
        class Identifier:
            def __str__(self):api.canonical_pipeline_accessory_ids=late;return 'a'
        with patch.object(api,'canonical_pipeline_accessory_ids',selected):
            result=api.agent_pipeline_quality_signals({'accessory_ids':[Identifier()]},{})
        self.assertEqual(result['accessory_count'],1);selected.assert_called_once_with({},['a']);late.assert_not_called()

    def test_decision_chat_callee_selected_before_context_serialization(self):
        self.resolver();self.patch('load_agent_config',return_value={});self.patch('agent_recommendation_supported',return_value=True);self.patch('agent_pipeline_context',return_value={});selected=Mock(return_value='{}');late=Mock(return_value='{}')
        def serialize(*args,**kwargs):self.api.agent_chat_completion=late;return '{}'
        with patch.object(self.api,'agent_chat_completion',selected),patch.object(self.api.json,'dumps',side_effect=serialize):
            result=self.api.agent_pipeline_decide({}, {})
        self.assertEqual(result['action'],'reply');selected.assert_called_once();late.assert_not_called()

    def test_decision_context_failure_stays_outside_rule_fallback(self):
        self.resolver();error=RuntimeError('synthetic context unavailable');self.patch('load_agent_config',return_value={});self.patch('agent_recommendation_supported',return_value=True);self.patch('agent_pipeline_context',side_effect=error);chat=self.patch('agent_chat_completion',return_value='{}');rule=self.patch('agent_pipeline_rule_decision',return_value={'source':'rules'})
        with self.assertRaises(RuntimeError) as caught:self.api.agent_pipeline_decide({}, {})
        self.assertIs(caught.exception,error);chat.assert_not_called();rule.assert_not_called()

    def test_decision_baseexception_is_not_rule_fallback(self):
        _,events=self.resolver();error=KeyboardInterrupt('synthetic interrupt');self.patch('load_agent_config',return_value={});self.patch('agent_recommendation_supported',return_value=True);self.patch('agent_pipeline_context',return_value={});self.patch('agent_chat_completion',side_effect=error);rule=self.patch('agent_pipeline_rule_decision',return_value={'source':'rules'})
        with self.assertRaises(KeyboardInterrupt) as caught:self.api.agent_pipeline_decide({}, {})
        self.assertIs(caught.exception,error);rule.assert_not_called();self.assertEqual([event[0] for event in events],['enter','exit'])


    def test_pipeline_decision_constructors_do_not_read_capabilities(self):
        from dataclasses import fields
        from local_inspection_service.agent import pipeline_decision_ports as p
        from local_inspection_service.agent.conversation import AgentConversation
        from local_inspection_service.agent.decision_context import AgentDecisionContext
        from local_inspection_service.agent.decision_policy import AgentDecisionPolicy
        from local_inspection_service.agent.decision_flow import AgentDecisionFlow
        getters=[]
        def group(kind):
            values={field.name:Mock(return_value=None) for field in fields(kind)}
            getters.extend(values.values());return kind(**values)
        AgentConversation(group(p.AgentConversationRuntime),group(p.AgentDecisionText))
        AgentDecisionContext(group(p.AgentPipelineEvidence),group(p.AgentDecisionAccessories),group(p.AgentDecisionContextCalls),group(p.AgentDecisionText))
        AgentDecisionPolicy(group(p.AgentDecisionPolicyValues),group(p.AgentDecisionRuleCalls),group(p.AgentDecisionText))
        AgentDecisionFlow(group(p.AgentDecisionInvocationSettings),group(p.AgentDecisionCodec),group(p.AgentDecisionFlowCalls))
        for getter in getters:getter.assert_not_called()

    def test_two_live_pipeline_decision_compositions_retain_dependencies(self):
        from dataclasses import fields
        from local_inspection_service.agent import pipeline_decision_ports as p
        from local_inspection_service.agent.conversation import AgentConversation
        from local_inspection_service.agent.decision_context import AgentDecisionContext
        from local_inspection_service.agent.decision_policy import AgentDecisionPolicy
        from local_inspection_service.agent.decision_flow import AgentDecisionFlow
        def group(kind,**selected):return kind(**{f.name:selected.get(f.name,lambda:None) for f in fields(kind)})
        records={};events=[]
        def make(name):
            orch={};records[name]=orch
            text=group(p.AgentDecisionText,bounded=lambda:lambda value,limit:str(value or '')[:limit])
            conversation=AgentConversation(group(p.AgentConversationRuntime,orchestration=lambda:lambda task:orch,now=lambda:lambda:1,uuid=lambda:lambda:SimpleNamespace(hex=name+'0123456789'),limit=lambda:5),text)
            evidence=group(p.AgentPipelineEvidence,orchestration=lambda:lambda task:orch,image_config=lambda:lambda:{},missing_assets=lambda:lambda task,config,orch:[],training_job=lambda:lambda task:None,pose_tool=lambda:'pose')
            accessories=group(p.AgentDecisionAccessories,canonical=lambda:lambda config,ids:[name],counts=lambda:lambda config,ids,raw:{name:1},lookup=lambda:lambda config:{name:{'name':name}},material=lambda:lambda item:'object',detection=lambda:lambda value:'yolo')
            context=AgentDecisionContext(evidence,accessories,group(p.AgentDecisionContextCalls,quality=lambda:lambda task,config:{'instance':name},stage_order=lambda:[name]),text)
            policy=AgentDecisionPolicy(group(p.AgentDecisionPolicyValues,actions=lambda:{name,'reply'},targets=lambda:{name}),group(p.AgentDecisionRuleCalls,rerun=lambda:lambda stage:('advance',''),normalize=lambda:lambda value:{'instance':name}),text)
            settings=group(p.AgentDecisionInvocationSettings,load=lambda:lambda:{'profile_id':name},supported=lambda:lambda config:True,prompt=lambda:'prompt-'+name)
            def chat(messages,config):events.append((name,messages,config));return '{}'
            flow=AgentDecisionFlow(settings,group(p.AgentDecisionCodec,dumps=lambda:json.dumps,parse=lambda:json.loads),group(p.AgentDecisionFlowCalls,context=lambda:lambda task,config,message,trigger:{'instance':name},chat=lambda:chat,normalize=lambda:lambda parsed:{'instance':name},rule=lambda:lambda task,message,trigger:{'fallback':name}))
            return conversation,context,policy,flow
        instances={name:make(name) for name in ('first','second')}
        with patch.object(self.api,'agent_mcp_orchestration',side_effect=AssertionError('root orchestration')),patch.object(self.api,'agent_chat_completion',side_effect=AssertionError('root chat')),patch.object(self.api,'normalize_agent_pipeline_decision',side_effect=AssertionError('root normalize')):
            for name in ('first','second','first'):
                with self.subTest(instance=name):
                    conversation,context,policy,flow=instances[name]
                    entry=conversation.agent_mcp_append_conversation({},'assistant',name)
                    self.assertIs(records[name]['conversation'][-1],entry)
                    self.assertEqual(context.agent_pipeline_context({}, {},None,'chat')['quality_signals'],{'instance':name})
                    self.assertEqual(policy.normalize_agent_pipeline_decision({'action':name})['action'],name)
                    self.assertEqual(policy.agent_pipeline_rule_decision({},None,'auto'),{'instance':name,'source':'rules'})
                    self.assertEqual(flow.agent_pipeline_decide({},{}),{'instance':name})
        self.assertEqual([e['message'] for e in records['first']['conversation']],['first','first']);self.assertEqual([e['message'] for e in records['second']['conversation']],['second'])
        self.assertEqual(events,[(name,[{'role':'system','content':'prompt-'+name},{'role':'user','content':json.dumps({'instance':name},ensure_ascii=False)}],{'profile_id':name}) for name in ('first','second','first')])


if __name__=='__main__':unittest.main()

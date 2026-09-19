"""Synthetic baseline for Agent orchestration state and tool-call records."""
import os,sys,tempfile,unittest,itertools
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path.cwd()))

class AgentStateContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ);cls.environment.start();cls.root=tempfile.TemporaryDirectory(prefix='agent-state-')
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
    def test_clock_truncates_wall_time(self):
        with patch.object(self.api.time,'time',return_value=12.9):self.assertEqual(self.api.agent_mcp_now(),12)
    def test_default_stages_are_fresh_and_ordered(self):
        first=self.api.agent_mcp_default_stages();second=self.api.agent_mcp_default_stages();self.assertEqual([x['key'] for x in first],['agent_pose_planning','pose_image_generation','sample_generation','model_training']);self.assertTrue(all(x['status']=='pending' and x['progress']==0 for x in first));first[0]['status']='changed';self.assertEqual(second[0]['status'],'pending')
    def test_orchestration_replaces_outer_mapping_preserving_nested_aliases(self):
        stages=[];conversation=[];pause={'reason':'old'};raw={'stages':stages,'conversation':conversation,'pause':pause,'created_at':1,'updated_at':2,'tool_config':{'other':'retained'},'unknown':'dropped'};task={'agent_mcp':raw};image={'configured':False};clock=self.patch('agent_mcp_now',return_value=123);self.patch('agent_mcp_gemini_image_config',return_value=image)
        value=self.api.agent_mcp_orchestration(task);self.assertIs(task['agent_mcp'],value);self.assertIsNot(value,raw);self.assertIs(value['stages'],stages);self.assertIs(value['conversation'],conversation);self.assertIs(value['pause'],pause);self.assertIs(value['tool_config']['pose_image_generation'],image);self.assertEqual(value['tool_config']['other'],'retained');self.assertNotIn('unknown',value);clock.assert_not_called()
    def test_orchestration_zero_timestamps_read_clock_twice(self):
        self.patch('agent_mcp_now',side_effect=itertools.chain([101],itertools.repeat(102)));self.patch('agent_mcp_gemini_image_config',return_value={});task={'agent_mcp':{'created_at':0,'updated_at':0}}
        value=self.api.agent_mcp_orchestration(task);self.assertEqual((value['created_at'],value['updated_at']),(101,102));self.assertEqual((value['state'],value['active_stage']),('created','created'))
    def test_orchestration_config_error_leaves_original_task_mapping(self):
        original={'created_at':1,'updated_at':2};task={'agent_mcp':original};error=RuntimeError('synthetic config failure');self.patch('agent_mcp_gemini_image_config',side_effect=itertools.chain([error],itertools.repeat({})))
        with self.assertRaises(RuntimeError) as caught:self.api.agent_mcp_orchestration(task)
        self.assertIs(caught.exception,error);self.assertIs(task['agent_mcp'],original);self.assertEqual(original,{'created_at':1,'updated_at':2})
    def test_stage_preserves_existing_identity_clamps_progress_and_keeps_metadata(self):
        stage={'key':'model_training','label':'kept'};orch={'stages':[stage]};self.patch('agent_mcp_now',return_value=123)
        self.api.set_agent_mcp_stage(orch,'model_training','running',140,detail='synthetic');self.assertIs(orch['stages'][0],stage);self.assertEqual(stage,{'key':'model_training','label':'kept','status':'running','progress':100,'detail':'synthetic'});self.assertEqual(orch['updated_at'],123)
    def test_new_stage_clock_failure_retains_stage_update(self):
        orch={'stages':[],'updated_at':7};error=RuntimeError('synthetic clock failure');self.patch('agent_mcp_now',side_effect=itertools.chain([error],itertools.repeat(123)))
        with self.assertRaises(RuntimeError):self.api.set_agent_mcp_stage(orch,'new_stage','running',-3)
        self.assertEqual(orch,{'stages':[{'key':'new_stage','label':'new stage','status':'running','progress':0}],'updated_at':7})
    def test_new_tool_call_preserves_caller_identity_and_explicit_timestamps(self):
        orch={};call={'call_id':'id','created_at':0,'updated_at':1};self.patch('agent_mcp_now',return_value=123)
        self.assertIs(self.api.upsert_agent_mcp_tool_call(orch,call),call);self.assertIs(orch['tool_calls'][0],call);self.assertEqual((call['created_at'],call['updated_at'],orch['updated_at']),(0,1,123))
    def test_existing_tool_call_updates_in_place_without_touching_orchestration_clock(self):
        old={'call_id':'id','created_at':1,'retained':True};orch={'tool_calls':[old],'updated_at':7};call={'call_id':'id','status':'running'};self.patch('agent_mcp_now',return_value=123)
        self.assertIs(self.api.upsert_agent_mcp_tool_call(orch,call),old);self.assertEqual(old,{'call_id':'id','created_at':1,'retained':True,'status':'running','updated_at':123});self.assertEqual(orch['updated_at'],7);self.assertEqual(call,{'call_id':'id','status':'running'})
    def test_pause_retains_choices_alias_and_full_reason_but_truncates_task_error(self):
        choices=['retry'];reason='synthetic '*40;task={};orch={};self.patch('agent_mcp_now',return_value=123)
        self.api.pause_agent_mcp_task(task,orch,stage='pose_image_generation',reason=reason,suggested_actions=choices)
        self.assertIs(orch['pause']['suggested_actions'],choices);self.assertEqual(orch['pause']['reason'],reason);self.assertEqual((task['progress'],task['last_error'],task['job_note']),(20,reason[:240],reason[:240]));self.assertEqual((orch['state'],task['status']),('needs_user_action','needs_user_action'))
    def test_tool_call_id_joins_only_nonempty_parts_before_sanitizing(self):
        safe=self.patch('safe_record_id',return_value='synthetic-id');self.assertEqual(self.api.agent_mcp_tool_call_id('task','tool','','pose'),'synthetic-id');safe.assert_called_once_with('task__tool__pose')
    def test_sample_log_retains_request_alias_and_updates_stage_after_upsert(self):
        orch={};events=[];ids=['part'];task={'id':'task','accessory_ids':ids,'params':{'sample_count':7,'train_mode':'yolo'}};self.patch('agent_mcp_orchestration',return_value=orch);identity=self.patch('agent_mcp_tool_call_id',return_value='call');upsert=self.patch('upsert_agent_mcp_tool_call',side_effect=lambda o,c:events.append(('upsert',o.copy(),c)));stage=self.patch('set_agent_mcp_stage',side_effect=lambda *args,**kwargs:events.append(('stage',orch.copy())))
        self.api.log_agent_mcp_sample_tool_call(task,{'job_id':'job'});self.assertEqual([x[0] for x in events],['upsert','stage']);self.assertIs(events[0][2]['request']['accessory_ids'],ids);self.assertEqual(events[0][2]['request'],{'accessory_ids':ids,'sample_count':7,'train_mode':'yolo'});self.assertEqual(events[0][1],{});self.assertEqual(orch,{'state':'sample_generation','active_stage':'sample_generation'});identity.assert_called_once_with('task',self.api.AGENT_MCP_TOOL_SAMPLES);self.assertEqual(events[0][2]['artifact_refs'],['job']);stage.assert_called_once_with(orch,'sample_generation','running',0,detail='Sample generation job job started.')
    def test_training_log_retains_dataset_and_training_request_fields(self):
        orch={};task={'id':'task','dataset_id':'data','params':{'epochs':7,'image_size':640,'train_mode':'yolo'}};self.patch('agent_mcp_orchestration',return_value=orch);self.patch('agent_mcp_tool_call_id',return_value='call');upsert=self.patch('upsert_agent_mcp_tool_call');stage=self.patch('set_agent_mcp_stage')
        self.api.log_agent_mcp_training_tool_call(task,{'job_id':'job'});self.assertEqual(upsert.call_args.args[1]['request'],{'accessory_ids':[],'dataset_id':'data','epochs':7,'image_size':640,'train_mode':'yolo'});self.assertEqual(orch,{'state':'model_training','active_stage':'model_training'});stage.assert_called_once_with(orch,'model_training','running',0,detail='Training job job started.')
    def test_quality_ack_returns_before_pause_or_stage(self):
        self.patch('agent_mcp_orchestration',return_value={'training_quality_ack':True,'skip_pose_image_generation':True});pause=self.patch('pause_agent_mcp_task');stage=self.patch('set_agent_mcp_stage');self.assertTrue(self.api.agent_mcp_training_quality_gate({}));pause.assert_not_called();stage.assert_not_called()
    def test_quality_skip_pauses_then_marks_stage_and_returns_false(self):
        orch={'skip_pose_image_generation':True};events=[];self.patch('agent_mcp_orchestration',return_value=orch);pause=self.patch('pause_agent_mcp_task',side_effect=lambda *a,**k:events.append('pause'));stage=self.patch('set_agent_mcp_stage',side_effect=lambda *a,**k:events.append('stage'))
        self.assertFalse(self.api.agent_mcp_training_quality_gate({}));self.assertEqual(events,['pause','stage']);self.assertEqual(pause.call_args.kwargs['suggested_actions'],['continue_training','replan','cancel']);self.assertEqual(stage.call_args.args[1:4],('model_training','needs_user_action',0))

    def test_orchestration_refreshes_now_between_missing_timestamps(self):
        later=Mock(return_value=202)
        def first():self.api.agent_mcp_now=later;return 101
        first_mock=self.patch('agent_mcp_now',side_effect=first);self.patch('agent_mcp_gemini_image_config',return_value={})
        value=self.api.agent_mcp_orchestration({});self.assertEqual((value['created_at'],value['updated_at']),(101,202));first_mock.assert_called_once();later.assert_called_once()
    def test_stage_evaluates_default_even_when_existing_stages_are_present(self):
        stages=[{'key':'sample_generation'}];defaults=self.patch('agent_mcp_default_stages',return_value=[]);self.patch('agent_mcp_now',return_value=123);orch={'stages':stages}
        self.api.set_agent_mcp_stage(orch,'sample_generation','running',7);defaults.assert_called_once();self.assertIs(orch['stages'],stages)
    def test_tool_id_sanitizer_selected_before_task_string_conversion(self):
        later=Mock(return_value='later');first=self.patch('safe_record_id',return_value='first');api=self.api
        class TaskId:
            def __str__(self):api.safe_record_id=later;return 'task'
        self.assertEqual(self.api.agent_mcp_tool_call_id(TaskId(),'tool'),'first');first.assert_called_once_with('task__tool');later.assert_not_called()
    def test_sample_upsert_selected_before_effectful_task_id(self):
        later=Mock();first=self.patch('upsert_agent_mcp_tool_call');api=self.api
        class TaskId:
            def __str__(self):api.upsert_agent_mcp_tool_call=later;return 'task'
        orch={};self.patch('agent_mcp_orchestration',return_value=orch);self.patch('agent_mcp_tool_call_id',return_value='call');self.patch('set_agent_mcp_stage')
        self.api.log_agent_mcp_sample_tool_call({'id':TaskId()},{'job_id':'job'});first.assert_called_once();later.assert_not_called()


    def test_state_constructors_do_not_read_capabilities(self):
        from dataclasses import fields
        from local_inspection_service.agent import state_ports as p
        from local_inspection_service.agent.orchestration_state import AgentOrchestrationState
        from local_inspection_service.agent.tool_call_records import AgentToolCallRecords
        getters=[]
        def group(kind):
            values={f.name:Mock(return_value=None) for f in fields(kind)};getters.extend(values.values());return kind(**values)
        AgentOrchestrationState(group(p.AgentStateRuntime),group(p.AgentStateCalls))
        AgentToolCallRecords(group(p.AgentToolCallIdentity),group(p.AgentToolCallState))
        for getter in getters:getter.assert_not_called()

    def test_two_live_state_compositions_retain_dependencies(self):
        from dataclasses import fields
        from local_inspection_service.agent import state_ports as p
        from local_inspection_service.agent.orchestration_state import AgentOrchestrationState
        from local_inspection_service.agent.tool_call_records import AgentToolCallRecords
        def group(kind,**selected):return kind(**{f.name:selected.get(f.name,lambda:None) for f in fields(kind)})
        events=[];records={}
        def make(name):
            runtime=group(p.AgentStateRuntime,clock=lambda:lambda:len(name)+0.9,now=lambda:lambda:len(name),version=lambda:name,image_config=lambda:lambda:{'instance':name})
            state=AgentOrchestrationState(runtime,group(p.AgentStateCalls,defaults=lambda:lambda:[]))
            orch={};records[name]=orch
            identity=group(p.AgentToolCallIdentity,sanitize=lambda:lambda text:name+':'+text,identifier=lambda:lambda *args:name,samples=lambda:'sample-'+name,training=lambda:'training-'+name)
            calls=group(p.AgentToolCallState,now=lambda:lambda:len(name),orchestration=lambda:lambda task:orch,upsert=lambda:lambda o,c:events.append((name,'call',c['tool'])),stage=lambda:lambda *args,**kwargs:events.append((name,'stage',args[1])))
            return state,AgentToolCallRecords(identity,calls)
        instances={name:make(name) for name in ('first','second')}
        with patch.object(self.api,'agent_mcp_now',side_effect=AssertionError('root clock')),patch.object(self.api,'agent_mcp_gemini_image_config',side_effect=AssertionError('root config')),patch.object(self.api,'upsert_agent_mcp_tool_call',side_effect=AssertionError('root upsert')),patch.object(self.api,'agent_mcp_tool_call_id',side_effect=AssertionError('root identifier')):
            for name in ('first','second','first'):
                state,calls=instances[name];task={};value=state.agent_mcp_orchestration(task);self.assertIs(task['agent_mcp'],value);self.assertEqual((value['version'],value['created_at'],value['tool_config']['pose_image_generation']),(name,len(name),{'instance':name}));self.assertEqual(state.agent_mcp_now(),len(name));self.assertEqual(len(state.agent_mcp_default_stages()),4);state.set_agent_mcp_stage(value,'synthetic_stage','running',9,detail=name);self.assertEqual(value['stages'],[{'key':'synthetic_stage','label':'synthetic stage','status':'running','progress':9,'detail':name}])
                self.assertEqual(calls.agent_mcp_tool_call_id('task','tool'),name+':task__tool');call={'call_id':'call'};orch={};self.assertIs(calls.upsert_agent_mcp_tool_call(orch,call),call);self.assertEqual(orch['updated_at'],len(name));calls.log_agent_mcp_sample_tool_call({'id':'task'},{'job_id':'job'})
        self.assertEqual(events,[(name,event,value) for name in ('first','second','first') for event,value in [('call','sample-'+name),('stage','sample_generation')]]);self.assertIsNot(records['first'],records['second'])


if __name__=='__main__':unittest.main()

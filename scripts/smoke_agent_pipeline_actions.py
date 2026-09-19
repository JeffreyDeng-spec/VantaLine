"""Synthetic baseline for applying Agent decisions to caller-owned pipeline state."""
import os,sys,tempfile,unittest,itertools
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path.cwd()))

class AgentPipelineActionsContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ);cls.environment.start();cls.root=tempfile.TemporaryDirectory(prefix='agent-pipeline-actions-')
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
    def action_dependencies(self,orch=None):
        orch={} if orch is None else orch
        self.patch('normalize_pipeline_detection_method',return_value='yolo');self.patch('pipeline_method_uses_training',return_value=True)
        self.patch('agent_mcp_orchestration',return_value=orch);self.patch('agent_mcp_now',return_value=123)
        return orch
    def test_collector_marks_and_deduplicates_without_inline_work(self):
        task={'id':'task'};pending=['task'];mark=self.patch('mark_pipeline_task_advancing',return_value=None);sync=self.patch('sync_pipeline_task');advance=self.patch('advance_pipeline_task')
        self.api.agent_safe_advance(task,{},pending);self.assertEqual(pending,['task']);mark.assert_called_once_with(task);sync.assert_not_called();advance.assert_not_called()
        pending=[];self.api.agent_safe_advance(task,{},pending);self.assertEqual(pending,['task'])
    def test_inline_advance_orders_sync_before_work(self):
        events=[];task={};self.patch('sync_pipeline_task',side_effect=lambda task:events.append('sync'));self.patch('advance_pipeline_task',side_effect=lambda task:events.append('advance'))
        self.api.agent_safe_advance(task,{});self.assertEqual(events,['sync','advance'])
    def test_inline_http_failure_pauses_with_original_detail(self):
        task={'stage':'samples'};orch={};error=self.api.HTTPException(409,'synthetic blocked');self.patch('sync_pipeline_task',return_value=False);self.patch('advance_pipeline_task',side_effect=error);self.patch('agent_mcp_orchestration',return_value=orch);pause=self.patch('pause_agent_mcp_task')
        self.api.agent_safe_advance(task,{})
        pause.assert_called_once_with(task,orch,stage='samples',reason='synthetic blocked',suggested_actions=['retry_pose_image_generation','replan','cancel'])
    def test_inline_unknown_failure_escapes_without_pause(self):
        error=RuntimeError('synthetic failure');self.patch('sync_pipeline_task',side_effect=itertools.chain([error],itertools.repeat(False)));advance=self.patch('advance_pipeline_task');pause=self.patch('pause_agent_mcp_task')
        with self.assertRaises(RuntimeError) as caught:self.api.agent_safe_advance({}, {})
        self.assertIs(caught.exception,error);advance.assert_not_called();pause.assert_not_called()
    def test_reset_retains_cleanup_order_and_clears_linked_state(self):
        user={'id':'synthetic'};task={'stage':'training','samples_task_id':'sample','training_task_id':'train','dataset_id':'dataset','params':{'keep':True}};orch={'pause':{'reason':'old'},'other':'retained'};calls=[]
        def delete(identity,owner,missing_ok):
            calls.append((identity,owner,missing_ok))
            if identity=='sample':raise RuntimeError('synthetic cleanup failure')
        self.patch('delete_training_task_record',side_effect=delete);self.patch('agent_mcp_orchestration',return_value=orch);self.patch('agent_mcp_now',return_value=123)
        self.api.reset_pipeline_task_to_stage(task,'samples',user)
        self.assertEqual(calls,[('sample',user,True),('train',user,True)]);self.assertEqual(task,{'stage':'draft','params':{'keep':True},'status':'ready','progress':0,'last_error':'','job_note':'','updated_at':123});self.assertEqual(orch,{'pause':None,'other':'retained','state':'created','active_stage':'created','training_quality_ack':False,'last_auto_signature':'','updated_at':123})
    def test_reset_without_user_skips_record_deletion(self):
        task={'samples_task_id':'sample'};delete=self.patch('delete_training_task_record');self.patch('agent_mcp_orchestration',return_value={});self.patch('agent_mcp_now',return_value=123)
        self.api.reset_pipeline_task_to_stage(task,'draft',None);delete.assert_not_called();self.assertNotIn('samples_task_id',task)
    def test_action_nontraining_and_reply_return_before_state_reads(self):
        self.patch('normalize_pipeline_detection_method',return_value='ai');uses=self.patch('pipeline_method_uses_training',return_value=False);orch=self.patch('agent_mcp_orchestration');clock=self.patch('agent_mcp_now')
        self.api.apply_agent_pipeline_decision({}, {},{'action':'cancel'},None);uses.return_value=True;self.api.apply_agent_pipeline_decision({}, {},{'action':'reply'},None);orch.assert_not_called();clock.assert_not_called()
    def test_cancel_updates_existing_task_and_orchestration(self):
        orch=self.action_dependencies({'pause':{'reason':'old'}});task={'stage':'samples'}
        self.api.apply_agent_pipeline_decision(task,{}, {'action':'cancel'},None)
        self.assertEqual(orch,{'pause':None,'state':'cancelled','active_stage':'cancelled','updated_at':123});self.assertEqual(task['stage'],'samples');self.assertEqual((task['status'],task['progress'],task['updated_at']),('stopped',100,123))
    def test_pause_forwards_user_message_and_choices(self):
        orch=self.action_dependencies({'active_stage':'training'});pause=self.patch('pause_agent_mcp_task');task={};choices=['cancel']
        self.api.apply_agent_pipeline_decision(task,{}, {'action':'pause_and_ask','message_to_user':'ask','suggested_actions':choices},None)
        pause.assert_called_once_with(task,orch,stage='training',reason='ask',suggested_actions=choices)
    def test_set_params_copies_shallowly_before_optional_advance(self):
        self.action_dependencies();nested=[];old={'epochs':3,'nested':nested};task={'params':old};pending=[];advance=self.patch('agent_safe_advance')
        self.api.apply_agent_pipeline_decision(task,{}, {'action':'set_params','params':{'epochs':7},'advance_after':True},None,pending_advances=pending)
        self.assertIsNot(task['params'],old);self.assertEqual(old['epochs'],3);self.assertIs(task['params']['nested'],nested);self.assertEqual(task['params']['epochs'],7);advance.assert_called_once_with(task,{},pending)
    def test_goto_samples_resets_then_applies_params_then_queues(self):
        self.action_dependencies();events=[];task={'params':{'epochs':3}};user={'id':'synthetic'};pending=[]
        self.patch('reset_pipeline_task_to_stage',side_effect=lambda task,target,user:events.append(('reset',target,user)))
        self.patch('agent_safe_advance',side_effect=lambda task,config,pending:events.append(('advance',task['params']['epochs'],pending)))
        self.api.apply_agent_pipeline_decision(task,{}, {'action':'goto_stage','target_stage':'samples','params':{'epochs':7}},user,pending_advances=pending)
        self.assertEqual(events,[('reset','samples',user),('advance',7,pending)])
    def test_photo_replan_and_retry_reuse_material_before_advance(self):
        for action in ('replan','retry'):
            with self.subTest(action=action):
                orch=self.action_dependencies();replacement={'pause':{'reason':'old'}};self.patch('pipeline_uses_photo_highlight_sprite_flow',return_value=True);mark=self.patch('mark_legacy_pose_flow_skipped_for_photo_highlight',return_value=replacement);advance=self.patch('agent_safe_advance');execute=self.patch('execute_agent_mcp_pose_tool_calls');task={}
                self.api.apply_agent_pipeline_decision(task,{}, {'action':action},None)
                self.assertIs(task['agent_mcp'],replacement);self.assertIsNone(replacement['pause']);self.assertEqual(task['status'],'ready');mark.assert_called_once_with(task,{},orch);advance.assert_called_once_with(task,{},None);execute.assert_not_called()
    def test_legacy_replan_unconfigured_keeps_plan_and_pauses_without_execution(self):
        self.action_dependencies();plan={};self.patch('pipeline_uses_photo_highlight_sprite_flow',return_value=False);ensure=self.patch('ensure_agent_mcp_pose_plan',return_value=plan);tools=self.patch('ensure_agent_mcp_pose_tool_calls');self.patch('agent_mcp_gemini_image_config',return_value={'configured':False,'message':'synthetic missing'});execute=self.patch('execute_agent_mcp_pose_tool_calls');pause=self.patch('pause_agent_mcp_task');task={}
        self.api.apply_agent_pipeline_decision(task,{}, {'action':'replan'},None)
        self.assertIs(task['agent_mcp'],plan);ensure.assert_called_once_with(task,{},force=True);tools.assert_called_once_with(task,{});execute.assert_not_called();self.assertEqual(pause.call_args.kwargs['reason'],'姿态方案已重规划；synthetic missing')
    def test_legacy_retry_does_not_overwrite_pause_from_execution(self):
        orch=self.action_dependencies({'skip_pose_image_generation':True});self.patch('pipeline_uses_photo_highlight_sprite_flow',return_value=False)
        def execute(task,config):orch['pause']={'reason':'execution uncertain'};return False
        self.patch('execute_agent_mcp_pose_tool_calls',side_effect=execute);pause=self.patch('pause_agent_mcp_task');config=self.patch('agent_mcp_gemini_image_config')
        self.api.apply_agent_pipeline_decision({}, {},{'action':'retry'},None);self.assertFalse(orch['skip_pose_image_generation']);self.assertEqual(orch['pause'],{'reason':'execution uncertain'});pause.assert_not_called();config.assert_not_called()
    def test_continue_assets_and_training_preserve_sample_ack_boundary(self):
        for action in ('continue_existing_assets','continue_training'):
            with self.subTest(action=action):
                orch=self.action_dependencies({'pause':{'reason':'old'}});task={'stage':'samples'};advance=self.patch('agent_safe_advance');pending=[]
                self.api.apply_agent_pipeline_decision(task,{}, {'action':action},None,pending_advances=pending)
                self.assertTrue(orch['training_quality_ack']);self.assertIsNone(orch['pause']);self.assertEqual(task['status'],'completed');advance.assert_called_once_with(task,{},pending)
    def test_commit_orders_user_apply_agent_and_preserves_decision_identity(self):
        events=[];task={};config={};user={'id':'synthetic'};pending=[];decision={'action':'reply','message_to_user':'answer','source':'rules'}
        self.patch('agent_mcp_append_conversation',side_effect=lambda task,role,message,**kwargs:events.append((role,message,kwargs)))
        apply=self.patch('apply_agent_pipeline_decision',side_effect=lambda *args,**kwargs:events.append(('apply',args,kwargs)))
        self.assertIs(self.api.commit_pipeline_agent_turn(task,config,user,'question',decision,'chat',pending),decision)
        self.assertEqual([event[0] for event in events],['user','apply','agent']);apply.assert_called_once_with(task,config,decision,user,trigger='chat',pending_advances=pending);self.assertEqual(events[-1],('agent','answer',{'action':'reply','reason':'','target_stage':'','source':'rules','needs_user':False,'agent_error':''}))
    def test_commit_failure_retains_user_message_without_agent_reply(self):
        error=RuntimeError('synthetic apply failure');append=self.patch('agent_mcp_append_conversation');self.patch('apply_agent_pipeline_decision',side_effect=itertools.chain([error],itertools.repeat(None)))
        with self.assertRaises(RuntimeError) as caught:self.api.commit_pipeline_agent_turn({}, {},None,'question',{},'chat')
        self.assertIs(caught.exception,error);append.assert_called_once_with({},'user','question')

    def test_reset_second_clock_failure_retains_exact_partial_state(self):
        error=RuntimeError('synthetic second clock');task={'samples_task_id':'sample','training_task_id':'train','dataset_id':'dataset'};orch={'pause':{'old':True},'state':'prior'}
        self.patch('agent_mcp_now',side_effect=itertools.chain([101,error],itertools.repeat(102)));self.patch('agent_mcp_orchestration',return_value=orch)
        with self.assertRaises(RuntimeError) as caught:self.api.reset_pipeline_task_to_stage(task,'draft',None)
        self.assertIs(caught.exception,error);self.assertEqual(task,{'stage':'draft','status':'ready','progress':0,'last_error':'','job_note':'','updated_at':101});self.assertEqual(orch,{'pause':{'old':True},'state':'prior'})
    def test_reset_refreshes_delete_callback_between_jobs(self):
        task={'samples_task_id':'sample','training_task_id':'train'};owner={'id':'synthetic'};later=Mock();events=[]
        def first(*args,**kwargs):events.append(args[0]);self.api.delete_training_task_record=later
        self.patch('delete_training_task_record',side_effect=first);self.patch('agent_mcp_orchestration',return_value={});self.patch('agent_mcp_now',return_value=123)
        self.api.reset_pipeline_task_to_stage(task,'draft',owner);self.assertEqual(events,['sample']);later.assert_called_once_with('train',owner,missing_ok=True)
    def test_reset_does_not_swallow_baseexception_or_clear_links(self):
        task={'samples_task_id':'sample','stage':'training'};error=KeyboardInterrupt('synthetic interrupt');self.patch('delete_training_task_record',side_effect=itertools.chain([error],itertools.repeat(None)));clock=self.patch('agent_mcp_now',return_value=123);orch=self.patch('agent_mcp_orchestration',return_value={})
        with self.assertRaises(KeyboardInterrupt) as caught:self.api.reset_pipeline_task_to_stage(task,'draft',{'id':'synthetic'})
        self.assertIs(caught.exception,error);self.assertEqual(task,{'samples_task_id':'sample','stage':'training'});clock.assert_not_called();orch.assert_not_called()
    def test_safe_advance_pause_callable_selected_before_stage_conversion(self):
        later=Mock();first=self.patch('pause_agent_mcp_task');api=self.api
        class Stage:
            def __str__(self):api.pause_agent_mcp_task=later;return 'samples'
        self.patch('sync_pipeline_task',side_effect=self.api.HTTPException(409,'blocked'));self.patch('agent_mcp_orchestration',return_value={'active_stage':Stage()})
        self.api.agent_safe_advance({},{});first.assert_called_once();later.assert_not_called();self.assertEqual(first.call_args.kwargs['stage'],'samples')
    def test_commit_refreshes_append_callback_after_user_message(self):
        later=Mock();events=[]
        def first(*args,**kwargs):events.append(args[1]);self.api.agent_mcp_append_conversation=later
        self.patch('agent_mcp_append_conversation',side_effect=first);self.patch('apply_agent_pipeline_decision');decision={'message_to_user':'answer'}
        self.assertIs(self.api.commit_pipeline_agent_turn({}, {},None,'question',decision,'chat'),decision);self.assertEqual(events,['user']);later.assert_called_once();self.assertEqual(later.call_args.args[1:3],('agent','answer'))
    def test_commit_agent_append_selected_before_decision_reads(self):
        later=Mock();first=self.patch('agent_mcp_append_conversation');self.patch('apply_agent_pipeline_decision');api=self.api
        class Decision(dict):
            def get(self,*args):api.agent_mcp_append_conversation=later;return super().get(*args)
        decision=Decision(message_to_user='answer')
        self.assertIs(self.api.commit_pipeline_agent_turn({}, {},None,None,decision,'chat'),decision);first.assert_called_once();later.assert_not_called()
    def test_inline_exception_matcher_is_read_after_sync_failure(self):
        class Before(Exception):pass
        class After(Exception):
            detail='synthetic rebound error'
        api=self.api;self.patch('HTTPException',new=Before);error=After()
        def sync(task):api.HTTPException=After;raise error
        self.patch('sync_pipeline_task',side_effect=sync);orch={};self.patch('agent_mcp_orchestration',return_value=orch);pause=self.patch('pause_agent_mcp_task');raised=None
        try:self.api.agent_safe_advance({'stage':'samples'}, {})
        except BaseException as exc:raised=exc
        self.assertIsNone(raised);pause.assert_called_once_with({'stage':'samples'},orch,stage='samples',reason='synthetic rebound error',suggested_actions=['retry_pose_image_generation','replan','cancel'])


    def test_action_constructors_do_not_read_capabilities(self):
        from dataclasses import fields
        from local_inspection_service.agent import pipeline_action_ports as p
        from local_inspection_service.agent.pipeline_actions import AgentPipelineActions
        from local_inspection_service.agent.pipeline_turns import AgentPipelineTurns
        getters=[]
        def group(kind):
            values={field.name:Mock(return_value=None) for field in fields(kind)}
            getters.extend(values.values());return kind(**values)
        AgentPipelineActions(group(p.AgentActionState),group(p.AgentActionAdvance),group(p.AgentActionJobs),group(p.AgentActionPolicy),group(p.AgentActionPose),group(p.AgentActionCalls))
        AgentPipelineTurns(group(p.AgentTurnCalls))
        for getter in getters:getter.assert_not_called()

    def test_two_live_action_compositions_preserve_dependencies(self):
        from dataclasses import fields
        from local_inspection_service.agent import pipeline_action_ports as p
        from local_inspection_service.agent.pipeline_actions import AgentPipelineActions
        from local_inspection_service.agent.pipeline_turns import AgentPipelineTurns
        def group(kind,**selected):return kind(**{f.name:selected.get(f.name,lambda:None) for f in fields(kind)})
        records={};events=[]
        def make(name):
            orch={};records[name]=orch
            state=group(p.AgentActionState,orchestration=lambda:lambda task:orch,now=lambda:lambda:len(name))
            advance=group(p.AgentActionAdvance,mark=lambda:lambda task:events.append((name,'mark',task['id'])))
            policy=group(p.AgentActionPolicy,normalize=lambda:lambda value:'yolo',uses_training=lambda:lambda value:True)
            actions=AgentPipelineActions(state,advance,group(p.AgentActionJobs),policy,group(p.AgentActionPose),group(p.AgentActionCalls))
            turn=AgentPipelineTurns(group(p.AgentTurnCalls,append=lambda:lambda task,role,message,**kwargs:events.append((name,role,message)),apply=lambda:lambda *args,**kwargs:events.append((name,'apply',kwargs['trigger']))))
            return actions,turn
        instances={name:make(name) for name in ('first','second')}
        with patch.object(self.api,'agent_mcp_orchestration',side_effect=AssertionError('root orchestration')),patch.object(self.api,'mark_pipeline_task_advancing',side_effect=AssertionError('root mark')),patch.object(self.api,'apply_agent_pipeline_decision',side_effect=AssertionError('root action')),patch.object(self.api,'agent_mcp_append_conversation',side_effect=AssertionError('root append')):
            for name in ('first','second','first'):
                actions,turn=instances[name];task={'id':name};pending=[]
                actions.agent_safe_advance(task,{},pending);self.assertEqual(pending,[name])
                actions.reset_pipeline_task_to_stage(task,'draft',None);self.assertEqual((task['stage'],task['updated_at']),('draft',len(name)))
                actions.apply_agent_pipeline_decision(task,{}, {'action':'cancel'},None);self.assertEqual((task['status'],records[name]['state']),('stopped','cancelled'))
                decision={'message_to_user':name};self.assertIs(turn.commit_pipeline_agent_turn(task,{},None,'question',decision,'chat'),decision)
        self.assertEqual(events,[(name,event,value) for name in ('first','second','first') for event,value in [('mark',name),('user','question'),('apply','chat'),('agent',name)]])
        self.assertIsNot(records['first'],records['second'])


if __name__=='__main__':unittest.main()

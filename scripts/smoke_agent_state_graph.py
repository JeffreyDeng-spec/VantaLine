"""Synthetic behavior tests for the proposed actual state assembly only."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.agent import state_composition as module
from local_inspection_service.agent.pose_render_ports import PoseRenderConfigurationSources,PoseRenderConfigurationDefaults
from unittest.mock import Mock,patch

def build(tag):
    env={'clock':10.9 if tag=='A' else 90.9,'model':tag,'events':[]}
    def settings():
        env['events'].append('configuration')
        if 'failure' in env:raise env['failure']
        return {'configured':True,'api_key_present':True,'provider':'synthetic','model':env['model']}
    sources=PoseRenderConfigurationSources(lambda:settings,lambda:lambda value:'provider-'+tag,lambda:lambda value:'label-'+tag,lambda:lambda value:'default-'+tag,lambda:lambda value:'https://example.invalid',lambda:lambda value:'SYNTHETIC')
    defaults=PoseRenderConfigurationDefaults(lambda:'synthetic',lambda:20,lambda:'SYNTHETIC',lambda:'MODEL',lambda:'TIMEOUT',lambda:'high',lambda:'OLDMODEL',lambda:'OLDTIMEOUT')
    graph=module.AgentStateWorkflows(clock=module.AgentStateClock(lambda:lambda:env['clock'],lambda:tag),tools=module.AgentToolNames(lambda:lambda value:tag+'-'+value,lambda:'samples',lambda:'training'),configuration_sources=sources,configuration_defaults=defaults)
    return graph,env

class StateCompositionTests(unittest.TestCase):
    def test_configuration_refresh_and_two_owners(self):
        a,ea=build('A');b,eb=build('B');ta={};tb={}
        first=a.agent_mcp_orchestration(ta);other=b.agent_mcp_orchestration(tb)
        ea['model']='A-next';ea['clock']=20.2
        second=a.agent_mcp_orchestration(ta)
        self.assertIsNot(first,second);self.assertIs(ta['agent_mcp'],second)
        self.assertEqual(second['tool_config']['pose_image_generation']['model'],'A-next')
        self.assertEqual(other['tool_config']['pose_image_generation']['model'],'B')
        self.assertEqual((a.agent_mcp_now(),b.agent_mcp_now()),(20,90))
        self.assertEqual(ea['events'],['configuration','configuration']);self.assertEqual(eb['events'],['configuration'])
    def test_replacement_preserves_nested_identity(self):
        a,_=build('A');stages=[];calls=[];raw={'stages':stages,'tool_calls':calls,'created_at':1,'updated_at':2,'unknown':'drop'};task={'agent_mcp':raw}
        value=a.agent_mcp_orchestration(task)
        self.assertIsNot(value,raw);self.assertIs(value['stages'],stages);self.assertIs(value['tool_calls'],calls);self.assertNotIn('unknown',value)
    def test_ack_still_refreshes_configuration_before_return(self):
        a,env=build('A');raw={'training_quality_ack':True};task={'agent_mcp':raw}
        self.assertTrue(a.agent_mcp_training_quality_gate(task));self.assertIsNot(task['agent_mcp'],raw);self.assertEqual(env['events'],['configuration'])
    def test_configuration_failure_preserves_original_outer_mapping(self):
        a,env=build('A');failure=RuntimeError('synthetic');env['failure']=failure;raw={'created_at':1,'updated_at':2};task={'agent_mcp':raw}
        with self.assertRaises(RuntimeError) as caught:a.agent_mcp_orchestration(task)
        self.assertIs(caught.exception,failure);self.assertIs(task['agent_mcp'],raw)
    def test_existing_stage_still_evaluates_default_and_keeps_extra(self):
        a,_=build('A');stage={'key':'model_training'};orch={'stages':[stage]}
        with patch.object(a,'agent_mcp_default_stages',wraps=a.agent_mcp_default_stages) as defaults:
            a.set_agent_mcp_stage(orch,'model_training','running',140,detail='kept')
        defaults.assert_called_once();self.assertIs(orch['stages'][0],stage);self.assertEqual(stage['progress'],100);self.assertEqual(stage['detail'],'kept')
    def test_upsert_existing_does_not_touch_outer_updated_time(self):
        a,_=build('A');call={'call_id':'id'};orch={'tool_calls':[call],'updated_at':3}
        self.assertIs(a.upsert_agent_mcp_tool_call(orch,{'call_id':'id','status':'running'}),call);self.assertEqual(orch['updated_at'],3)
        new={'call_id':'next'};self.assertIs(a.upsert_agent_mcp_tool_call(orch,new),new);self.assertEqual(orch['updated_at'],10)
    def test_saved_forwarder_selects_component_after_argument_effect(self):
        a,_=build('A');b,_=build('B');selected=a.tools._state.upsert();old=a.tools;orch={}
        def argument():a.tools=b.tools;return {'call_id':'id'}
        selected(orch,argument())
        self.assertEqual(orch['updated_at'],90);self.assertIs(a.tools,b.tools)
    def test_stage_failure_keeps_prior_call_and_state_effects(self):
        a,_=build('A');task={'id':'task'};error=RuntimeError('stage failed')
        with patch.object(a,'set_agent_mcp_stage',side_effect=error):
            with self.assertRaises(RuntimeError) as caught:a.log_agent_mcp_sample_tool_call(task,{'job_id':'job'})
        self.assertIs(caught.exception,error);orch=task['agent_mcp'];self.assertEqual(len(orch['tool_calls']),1);self.assertEqual(orch['state'],'sample_generation');self.assertEqual(orch['active_stage'],'sample_generation')

if __name__=='__main__':unittest.main()

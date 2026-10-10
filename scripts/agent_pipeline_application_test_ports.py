"""Replace finite external Agent pipeline ports, preserving owned graphs and pinning."""
from dataclasses import replace
from unittest.mock import patch

# Only externally supplied capabilities are replaced. Owned cross-service calls
# and the canonical decision resolver continue to execute the real composition.
EXTERNAL=(
    ('conversation','_conversation',{'orchestration':'agent_mcp_orchestration','now':'agent_mcp_now','limit':'AGENT_MCP_CONVERSATION_LIMIT'}),
    ('conversation','_text',{'bounded':'bounded_text'}),
    ('context','_evidence',{'orchestration':'agent_mcp_orchestration','image_config':'agent_mcp_gemini_image_config','missing_assets':'agent_mcp_missing_existing_asset_names','pose_tool':'AGENT_MCP_TOOL_POSE_IMAGE'}),
    ('context','_accessories',{'lookup':'accessory_lookup_by_id','material':'accessory_material_type'}),
    ('context','_context',{'stage_order':'PIPELINE_STAGE_ORDER'}),
    ('context','_text',{'bounded':'bounded_text'}),
    ('policy','_policy',{'actions':'AGENT_PIPELINE_ACTIONS','targets':'AGENT_PIPELINE_STAGE_TARGETS'}),
    ('policy','_text',{'bounded':'bounded_text'}),
    ('decision','_settings',{'load':'load_agent_config','supported':'agent_recommendation_supported','prompt':'AGENT_PIPELINE_SYSTEM_PROMPT'}),
    ('decision','_codec',{'parse':'parse_agent_json'}),
    ('decision','_calls',{'chat':'agent_chat_completion'}),
    ('actions','_state',{'orchestration':'agent_mcp_orchestration','now':'agent_mcp_now','pause':'pause_agent_mcp_task','bounded':'bounded_text','http_error_type':'HTTPException'}),
    ('actions','_jobs',{'delete':'delete_training_task_record'}),
    ('actions','_pose',{'photo_flow':'pipeline_uses_photo_highlight_sprite_flow','skip_legacy':'mark_legacy_pose_flow_skipped_for_photo_highlight','plan':'ensure_agent_mcp_pose_plan','ensure_calls':'ensure_agent_mcp_pose_tool_calls','config':'agent_mcp_gemini_image_config','execute':'execute_agent_mcp_pose_tool_calls'}),
)


def bind_external_agent_pipeline(api,stack):
    workflows=api._default_application.training_pipeline._agent_pipeline_workflows
    def supplier(name):return lambda:getattr(api,name)
    for component,attribute,fields in EXTERNAL:
        owner=getattr(workflows,component);original=getattr(owner,attribute)
        extra={field:supplier(name) for field,name in fields.items()}
        if component=='conversation' and attribute=='_conversation':extra['uuid']=lambda:api.uuid.uuid4
        if component=='decision' and attribute=='_codec':extra['dumps']=lambda:api.json.dumps
        stack.enter_context(patch.object(owner,attribute,replace(original,**extra)))


def assert_default_external_agent_pipeline(api):
    import unittest
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.agent.pipeline_composition import AgentPipelineWorkflows
    from local_inspection_service.agent.conversation import AgentConversation
    from local_inspection_service.agent.decision_context import AgentDecisionContext
    from local_inspection_service.agent.decision_policy import AgentDecisionPolicy
    from local_inspection_service.agent.decision_flow import AgentDecisionFlow
    from local_inspection_service.agent.pipeline_actions import AgentPipelineActions
    from local_inspection_service.agent.pipeline_turns import AgentPipelineTurns
    from local_inspection_service.runtime.wiring import training_pipeline
    from local_inspection_service.runtime.text_policy import bounded_text
    verify_actual_sources()
    case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;inspection=app.inspection
    owner=graph._agent_pipeline_workflows
    case.assertIs(type(owner),AgentPipelineWorkflows);case.assertIs(api._agent_pipeline_workflows,owner)
    case.assertIs(owner,graph._pipeline_workflows.agent)
    for name,kind in (('conversation',AgentConversation),('context',AgentDecisionContext),('policy',AgentDecisionPolicy),('decision',AgentDecisionFlow),('actions',AgentPipelineActions),('turns',AgentPipelineTurns)):
        case.assertIs(type(getattr(owner,name)),kind)
    case.assertIs(owner.conversation._conversation.uuid(),training_pipeline.uuid.uuid4)
    case.assertIs(owner.decision._codec.dumps(),training_pipeline.json.dumps)
    case.assertIs(owner.actions._state.http_error_type(),training_pipeline.HTTPException)
    for component in (owner.conversation,owner.context,owner.policy):case.assertIs(component._text.bounded(),bounded_text)
    case.assertIs(owner.actions._state.bounded(),bounded_text)
    item,other,third=object(),object(),object()
    selected_job=owner.context._evidence.training_job()
    case.assertIs(selected_job.__self__,graph._pipeline_workflows)
    case.assertIs(selected_job.__func__,type(graph._pipeline_workflows).linked_training_job)
    for selected,target,method,args,keywords,forwarded,forward_keywords in (
        (owner.conversation._conversation.orchestration(),graph._agent_orchestration_state,'agent_mcp_orchestration',(item,),{},(item,),{}),
        (owner.conversation._conversation.now(),graph._agent_orchestration_state,'agent_mcp_now',(),{},(),{}),
        (owner.context._evidence.orchestration(),graph._agent_orchestration_state,'agent_mcp_orchestration',(item,),{},(item,),{}),
        (owner.context._evidence.image_config(),graph._pose_render_configuration,'agent_mcp_gemini_image_config',(),{},(),{}),
        (owner.context._evidence.missing_assets(),graph._agent_pose_assets,'agent_mcp_missing_existing_asset_names',(item,other,third),{},(item,other,third),{}),
        (owner.context._evidence.training_job(),graph._pipeline_stages,'linked_training_job',(item,),{},(item,None),{}),
        (owner.context._accessories.lookup(),inspection._accessory_lookup,'accessory_lookup_by_id',(item,),{},(item,),{}),
        (owner.decision._settings.load(),app.infrastructure._model_profile_configuration,'load_agent_config',(),{},(),{}),
        (owner.decision._settings.supported(),graph._agent_settings_projection,'agent_recommendation_supported',(item,),{},(item,),{}),
        (owner.decision._codec.parse(),graph._agent_recommendation,'parse_agent_json',(item,),{},(item,),{}),
        (owner.decision._calls.chat(),graph._agent_chat_transport,'agent_chat_completion',(item,),{},(item,None),{}),
        (owner.decision._calls.chat(),graph._agent_chat_transport,'agent_chat_completion',(item,other),{},(item,other),{}),
        (owner.actions._state.orchestration(),graph._agent_orchestration_state,'agent_mcp_orchestration',(item,),{},(item,),{}),
        (owner.actions._state.now(),graph._agent_orchestration_state,'agent_mcp_now',(),{},(),{}),
        (owner.actions._state.pause(),graph._agent_orchestration_state,'pause_agent_mcp_task',(item,other),{'stage':'stage','reason':'reason','suggested_actions':[third]},(item,other),{'stage':'stage','reason':'reason','suggested_actions':[third]}),
        (owner.actions._jobs.delete(),graph._training_state_workflows,'delete_training_task_record',('synthetic',other),{},('synthetic',other),{'missing_ok':False}),
        (owner.actions._jobs.delete(),graph._training_state_workflows,'delete_training_task_record',('synthetic',other),{'missing_ok':True},('synthetic',other),{'missing_ok':True}),
        (owner.actions._pose.skip_legacy(),graph._photo_highlight_workflow,'mark_legacy_pose_flow_skipped_for_photo_highlight',(item,other,third),{},(item,other,third),{}),
        (owner.actions._pose.plan(),graph._photo_highlight_workflow,'ensure_agent_mcp_pose_plan',(item,other),{},(item,other),{'force':False}),
        (owner.actions._pose.plan(),graph._photo_highlight_workflow,'ensure_agent_mcp_pose_plan',(item,other),{'force':True},(item,other),{'force':True}),
        (owner.actions._pose.ensure_calls(),graph._pose_call_registration,'ensure_agent_mcp_pose_tool_calls',(item,other),{},(item,other),{}),
        (owner.actions._pose.config(),graph._pose_render_configuration,'agent_mcp_gemini_image_config',(),{},(),{}),
        (owner.actions._pose.execute(),graph._pose_call_execution,'execute_agent_mcp_pose_tool_calls',(item,other),{},(item,other),{}),
    ):
        if method=='pause_agent_mcp_task':forward_keywords=keywords
        assert_native_relay(case,selected,(target,method,args,keywords,forwarded,forward_keywords))
    with patch.object(training_pipeline._accessory_policy,'accessory_material_type',return_value=other) as callee:
        case.assertIs(owner.context._accessories.material()(item),other);callee.assert_called_once_with(item)
    for selected_items,expected in (([],False),([third],True)):
        with patch.object(type(graph._photo_highlight_selection),'pipeline_photo_highlight_object_items',autospec=True,return_value=selected_items) as callee:
            case.assertIs(owner.actions._pose.photo_flow()(item,other),expected)
            callee.assert_called_once_with(graph._photo_highlight_selection,item,other)
            case.assertIs(callee.call_args.args[0],graph._photo_highlight_selection)
            case.assertIs(callee.call_args.args[1],item);case.assertIs(callee.call_args.args[2],other)
    for selected,name in ((owner.conversation._conversation.limit,'AGENT_MCP_CONVERSATION_LIMIT'),(owner.context._evidence.pose_tool,'AGENT_MCP_TOOL_POSE_IMAGE'),
        (owner.context._context.stage_order,'PIPELINE_STAGE_ORDER'),(owner.policy._policy.actions,'AGENT_PIPELINE_ACTIONS'),
        (owner.policy._policy.targets,'AGENT_PIPELINE_STAGE_TARGETS'),(owner.decision._settings.prompt,'AGENT_PIPELINE_SYSTEM_PROMPT')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:
            object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)

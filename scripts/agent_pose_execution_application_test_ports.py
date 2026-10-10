"""Finite external fixtures for unchanged pose task execution contracts."""
from dataclasses import replace
from unittest.mock import patch

MODELS={'settings':'image_generation_settings','provider':'image_generation_provider_from_settings','error':'AiProviderError'}
REGISTRY={'lookup':'accessory_lookup_by_id','cached':'agent_mcp_accessory_pose_images_exist','tool':'AGENT_MCP_TOOL_POSE_IMAGE'}
STEPS={'background':'ensure_pipeline_background_plate','materialize':'materialize_agent_mcp_pose_assets','missing':'agent_mcp_missing_existing_asset_names','save':'save_config'}


def bind_pose_execution(api,stack):
    owner=api._default_application.training_pipeline._photo_pose_workflows
    for selected in (owner.registration,owner.execution,owner.samples):
        stack.enter_context(patch.object(selected,'_models',replace(selected._models,**{field:(lambda _name=name:getattr(api,_name)) for field,name in MODELS.items()})))
    for selected in (owner.registration,owner.execution):stack.enter_context(patch.object(selected,'_registry',replace(selected._registry,**{field:(lambda _name=name:getattr(api,_name)) for field,name in REGISTRY.items()})))
    stack.enter_context(patch.object(owner.execution,'_content',replace(owner.execution._content,chroma=lambda:api.choose_agent_mcp_chroma_screen)))
    stack.enter_context(patch.object(owner.execution,'_presentation',replace(owner.execution._presentation,bounded=lambda:api.bounded_text)))
    stack.enter_context(patch.object(owner.samples,'_steps',replace(owner.samples._steps,**{field:(lambda _name=name:getattr(api,_name)) for field,name in STEPS.items()})))


def assert_default_pose_execution(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.agent.pose_call_registration import PoseCallRegistration
    from local_inspection_service.agent.pose_call_execution import PoseCallExecution
    from local_inspection_service.agent.pose_sample_preparation import PoseSamplePreparation
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;owner=graph._photo_pose_workflows;item,other,third,fourth=object(),object(),object(),object()
    case.assertIs(owner.state,graph._agent_state_workflows);case.assertIs(owner.planning,graph._pose_planning_workflows)
    for selected,kind,name in ((owner.registration,PoseCallRegistration,'_pose_call_registration'),(owner.execution,PoseCallExecution,'_pose_call_execution'),(owner.samples,PoseSamplePreparation,'_pose_sample_preparation')):
        case.assertIs(type(selected),kind);case.assertIs(getattr(graph,name),selected);case.assertIs(getattr(api,name),selected)
        for field,target,method in (('plan',owner,'ensure_agent_mcp_pose_plan'),('current',owner.state,'agent_mcp_orchestration'),('photo_flow',owner,'pipeline_uses_photo_highlight_sprite_flow'),('skip_legacy',owner,'mark_legacy_pose_flow_skipped_for_photo_highlight'),('stage',owner.state,'set_agent_mcp_stage'),('pause',owner.state,'pause_agent_mcp_task')):
            native=getattr(selected._state,field)();case.assertIs(native.__self__,target);case.assertIs(native.__func__,getattr(type(target),method))
        native=selected._models.configuration();case.assertIs(native.__self__,owner.state);case.assertIs(native.__func__,type(owner.state).agent_mcp_gemini_image_config)
        case.assertIs(selected._models.error(),wiring.AiProviderError)
        assert_native_relay(case,selected._models.settings(),(app.infrastructure._model_profile_configuration,'image_generation_settings',(),{},(),{}))
        assert_native_relay(case,selected._models.provider(),(app.inspection._provider_selection,'image_generation_provider_from_settings',(item,),{},(item,),{}))
    for selected in (owner.registration,owner.execution):
        original=app.values.AGENT_MCP_TOOL_POSE_IMAGE;case.assertIs(selected._registry.tool(),original)
        try:object.__setattr__(app.values,'AGENT_MCP_TOOL_POSE_IMAGE',other);case.assertIs(selected._registry.tool(),other)
        finally:object.__setattr__(app.values,'AGENT_MCP_TOOL_POSE_IMAGE',original)
        assert_native_relay(case,selected._registry.lookup(),(app.inspection._accessory_lookup,'accessory_lookup_by_id',(item,),{},(item,),{}))
        assert_native_relay(case,selected._registry.cached(),(graph._agent_pose_assets,'agent_mcp_accessory_pose_images_exist',(item,),{},(item,),{}))
        for field,method in (('identifier','agent_mcp_tool_call_id'),('upsert','upsert_agent_mcp_tool_call')):
            native=getattr(selected._registry,field)();case.assertIs(native.__self__,owner.state);case.assertIs(native.__func__,getattr(type(owner.state),method))
    for getter,method in ((owner.execution._content.references,'agent_mcp_pose_reference_content'),(owner.execution._content.prompt,'agent_mcp_pose_prompt'),(owner.execution._content.artifact,'write_agent_mcp_pose_artifact'),(owner.samples._steps.photos,'prepare_photo_highlight_sprites_for_task'),(owner.samples._steps.register,'ensure_agent_mcp_pose_tool_calls'),(owner.samples._steps.execute,'execute_agent_mcp_pose_tool_calls')):
        native=getter();case.assertIs(native.__self__,owner);case.assertIs(native.__func__,getattr(type(owner),method))
    native=owner.execution._presentation.now();case.assertIs(native.__self__,owner.state);case.assertIs(native.__func__,type(owner.state).agent_mcp_now)
    case.assertIs(owner.execution._presentation.bounded(),wiring.bounded_text);case.assertIs(owner.samples._diagnostics.stderr(),wiring.sys.stderr);case.assertIs(owner.samples._diagnostics.print_exception(),wiring.traceback.print_exc)
    assert_native_relay(case,owner.execution._content.chroma(),(graph._pose_chroma_policy,'choose_agent_mcp_chroma_screen',(item,),{},(item,),{}))
    assert_native_relay(case,owner.samples._steps.materialize(),(graph._pose_asset_materialization,'materialize_agent_mcp_pose_assets',(item,other),{},(item,other),{}))
    assert_native_relay(case,owner.samples._steps.missing(),(graph._agent_pose_assets,'agent_mcp_missing_existing_asset_names',(item,other,third),{},(item,other,third),{}))
    assert_native_relay(case,owner.samples._steps.background(),(graph._pipeline_background_publication,'ensure_pipeline_background_plate',(item,other),{},(item,other),{}))
    assert_native_relay(case,owner.samples._steps.save(),(app.infrastructure._app_configuration,'save_config',(item,),{},(item,),{}))

    pause_kw={'stage':third,'reason':fourth,'suggested_actions':item}
    for selected in (owner.registration,owner.execution,owner.samples):
        for getter,target,name,args,kw,expected_kw in ((selected._state.plan(),owner.photos,'ensure_agent_mcp_pose_plan',(item,other),{}, {'force':False}),(selected._state.current(),owner.state.state,'agent_mcp_orchestration',(item,),{},{}),(selected._state.skip_legacy(),owner.photos,'mark_legacy_pose_flow_skipped_for_photo_highlight',(item,other,third),{},{}),(selected._state.stage(),owner.state.state,'set_agent_mcp_stage',(item,other,third,fourth),{'detail':item},{'detail':item}),(selected._state.pause(),owner.state.state,'pause_agent_mcp_task',(item,other),pause_kw,pause_kw),(selected._models.configuration(),owner.state.configuration,'agent_mcp_gemini_image_config',(),{},{})):
            assert_native_relay(case,getter,(target,name,args,kw,args,expected_kw))
        for result in ([],[item]):
            with patch.object(type(owner.selection),'pipeline_photo_highlight_object_items',autospec=True,return_value=result) as receiver:
                case.assertIs(selected._state.photo_flow()(item,other),bool(result));receiver.assert_called_once_with(owner.selection,item,other)
    for selected in (owner.registration,owner.execution):
        assert_native_relay(case,selected._registry.identifier(),(owner.state.tools,'agent_mcp_tool_call_id',(item,other,third,fourth),{},(item,other,third,fourth),{}))
        assert_native_relay(case,selected._registry.upsert(),(owner.state.tools,'upsert_agent_mcp_tool_call',(item,other),{},(item,other),{}))
    for getter,target,name,args,kw in ((owner.execution._content.references(),owner.render,'agent_mcp_pose_reference_content',(item,),{'max_images':other}),(owner.execution._content.prompt(),owner.render,'agent_mcp_pose_prompt',(item,other,third,fourth),{}),(owner.execution._content.artifact(),owner.artifacts,'write_agent_mcp_pose_artifact',(item,other,third),{'prompt':fourth,'reference_assets':item}),(owner.samples._steps.photos(),owner.photos,'prepare_photo_highlight_sprites_for_task',(item,other,third),{}),(owner.samples._steps.register(),owner.registration,'ensure_agent_mcp_pose_tool_calls',(item,other),{}),(owner.samples._steps.execute(),owner.execution,'execute_agent_mcp_pose_tool_calls',(item,other),{}),(owner.execution._presentation.now(),owner.state.state,'agent_mcp_now',(),{})):
        assert_native_relay(case,getter,(target,name,args,kw,args,kw))

"""Finite external ports for unchanged pose planning; owned call chains remain native."""
from dataclasses import replace
from unittest.mock import patch

IDENTITY={'uid':'accessory_uid','material':'accessory_material_type','sanitize':'safe_record_id'}
CONTENT={'size':'object_physical_size_mm','sprites':'clean_sprite_assets','bounded':'bounded_text','optional_number':'optional_float','strings':'string_list'}
RUNTIME={'version':'AGENT_MCP_POSE_PLAN_VERSION','max_poses':'AGENT_MCP_POSE_PLAN_MAX_POSES','min_confidence':'AGENT_MCP_POSE_PLAN_MIN_CONFIDENCE'}


def bind_pose_planning(api,stack):
    graph=api._default_application.training_pipeline;owner=graph._pose_planning_workflows
    for selected in (owner.policy,owner.generation,owner.assembly):
        stack.enter_context(patch.object(selected,'_identity',replace(selected._identity,**{field:(lambda _name=name:getattr(api,_name)) for field,name in IDENTITY.items()})))
        stack.enter_context(patch.object(selected,'_runtime',replace(selected._runtime,**{field:(lambda _name=name:getattr(api,_name)) for field,name in RUNTIME.items()},clock=lambda:api.time.time)))
    for selected in (owner.policy,owner.generation):stack.enter_context(patch.object(selected,'_content',replace(selected._content,**{field:(lambda _name=name:getattr(api,_name)) for field,name in CONTENT.items()})))
    stack.enter_context(patch.object(owner.templates,'_identity',replace(owner.templates._identity,uid=lambda:api.accessory_uid,kind=lambda:api.accessory_material_type)))
    stack.enter_context(patch.object(owner.generation,'_provider',replace(owner.generation._provider,settings=lambda:api.ai_detection_settings,call=lambda:api.call_ai_mcp_tool)))
    stack.enter_context(patch.object(owner.generation,'_media',replace(owner.generation._media,encode=lambda:api.image_path_data_url,max_side=lambda:api.AI_PROFILE_REFERENCE_IMAGE_MAX_SIDE,quality=lambda:api.AI_PROFILE_REFERENCE_IMAGE_QUALITY)))
    stack.enter_context(patch.object(owner.assembly,'_catalog',replace(owner.assembly._catalog,lookup=lambda:api.accessory_lookup_by_id,counts=lambda:api.normalize_pipeline_accessory_counts,canonical_ids=lambda:api.canonical_pipeline_accessory_ids)))


def assert_default_pose_planning(api):
    import unittest
    from types import CodeType
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.agent.planning_composition import PosePlanningWorkflows
    from local_inspection_service.agent.pose_plan_policy import PosePlanPolicy
    from local_inspection_service.agent.pose_plan_generation import PosePlanGeneration
    from local_inspection_service.agent.pose_plan_assembly import PosePlanAssembly
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;owner=graph._pose_planning_workflows;inspection=app.inspection;item,other,third=object(),object(),object()
    case.assertIs(type(owner),PosePlanningWorkflows);case.assertIs(api._pose_planning_workflows,owner)
    for selected,kind,name in ((owner.policy,PosePlanPolicy,'_pose_plan_policy'),(owner.generation,PosePlanGeneration,'_pose_plan_generation'),(owner.assembly,PosePlanAssembly,'_pose_plan_assembly')):case.assertIs(type(selected),kind);case.assertIs(getattr(api,name),selected);case.assertIs(getattr(graph,name),selected)
    optional_code=next(code for code in wiring.assemble_training_pipeline.__code__.co_consts if isinstance(code,CodeType) and code.co_name=='optional_float')
    for selected in (owner.policy,owner.generation,owner.assembly):
        for field,name in RUNTIME.items():
            getter=getattr(selected._runtime,field);original=getattr(app.values,name);case.assertIs(getter(),original)
            try:object.__setattr__(app.values,name,other);case.assertIs(getter(),other)
            finally:object.__setattr__(app.values,name,original)
        for getter,name in ((selected._identity.uid,'accessory_uid'),(selected._identity.material,'accessory_material_type')):
            with patch.object(wiring._accessory_policy,name,return_value=other) as receiver:case.assertIs(getter()(item),other);receiver.assert_called_once_with(item)
        assert_native_relay(case,selected._identity.sanitize(),(inspection._pose_collection_jobs,'safe_record_id',(item,),{},(item,),{}))
        native=selected._identity.kind();case.assertIs(native.__self__,owner);case.assertIs(native.__func__,type(owner).agent_mcp_object_kind)
        assert_native_relay(case,native,(owner.templates,'agent_mcp_object_kind',(item,),{},(item,),{}))
        native=selected._runtime.now();case.assertIs(native.__self__,graph._agent_state_workflows);case.assertIs(native.__func__,type(graph._agent_state_workflows).agent_mcp_now)
        assert_native_relay(case,native,(graph._agent_state_workflows.state,'agent_mcp_now',(),{},(),{}))
        case.assertIs(selected._runtime.clock(),wiring.time.time)
    for selected in (owner.policy,owner.generation):
        assert_native_relay(case,selected._content.size(),(inspection._sprite_footprint,'object_physical_size_mm',(item,),{},(item,),{}));assert_native_relay(case,selected._content.sprites(),(inspection._sprite_asset_catalog,'clean_sprite_assets',(item,),{},(item,),{}))
        case.assertIs(selected._content.bounded(),wiring.bounded_text);case.assertIs(selected._content.strings(),wiring.string_list);case.assertIs(selected._content.compile(),wiring.re.compile);case.assertIs(selected._content.optional_number().__code__,optional_code)
    generation=owner.generation;case.assertIs(generation._provider.dumps(),wiring.json.dumps);case.assertIs(generation._media.path(),wiring.Path)
    for getter,name in ((generation._media.max_side,'AI_PROFILE_REFERENCE_IMAGE_MAX_SIDE'),(generation._media.quality,'AI_PROFILE_REFERENCE_IMAGE_QUALITY')):
        original=getattr(app.values,name);case.assertIs(getter(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(getter(),other)
        finally:object.__setattr__(app.values,name,original)
    for selected,target,method,args,kw,expected,expected_kw in ((generation._provider.settings(),app.infrastructure._model_profile_configuration,'ai_detection_settings',('training_vision',),{},('training_vision',),{}),(generation._provider.call(),inspection._model_tool_dispatch,'call_ai_mcp_tool',(item,other),{},(item,other),{}),(generation._media.encode(),inspection._image_encoding,'image_path_data_url',(item,),{'max_side':other,'quality':third},(item,),{'max_side':other,'quality':third}),(owner.assembly._catalog.lookup(),inspection._accessory_lookup,'accessory_lookup_by_id',(item,),{},(item,),{}),(owner.assembly._catalog.counts(),graph._pipeline_task_metadata,'normalize_pipeline_accessory_counts',(item,other,third),{},(item,other,third),{}),(owner.assembly._catalog.canonical_ids(),graph._pipeline_candidate_flow,'canonical_pipeline_accessory_ids',(item,other),{},(item,other),{})):
        assert_native_relay(case,selected,(target,method,args,kw,expected,expected_kw))
    for getter,name in ((owner.templates._identity.uid,'accessory_uid'),(owner.templates._identity.kind,'accessory_material_type')):
        with patch.object(wiring._accessory_policy,name,return_value=other) as receiver:case.assertIs(getter()(item),other);receiver.assert_called_once_with(item)

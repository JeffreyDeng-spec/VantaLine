"""Finite external capabilities for the remaining pipeline HTTP controllers."""
from dataclasses import replace
from unittest.mock import patch

ACCESS={'current_user':'current_auth_user','load_config':'load_config','scope_config':'scope_config_for_user','http_error':'HTTPException','require_record_access':'require_record_access'}
EXTERNAL={
 'list':(('listing','access',{'current_user':'current_auth_user','is_admin':'user_is_admin','load_config':'load_config','scope_config':'scope_config_for_user','load_ai_tasks':'load_ai_detection_tasks','visible':'record_visible_to_user','incoming_allowed':'incoming_text_task_access_allowed','has_permission':'user_has_permission'}),('listing','reconciliation',{'save_config':'save_config','sync_ready_ai_tasks':'sync_ready_pipeline_ai_detection_tasks'}),('listing','presentation',{'trained_specs':'list_trained_model_specs','optimize_states':'list_auto_optimize_states','public_agent_config':'public_agent_config','sanitize':'public_path_sanitized'})),
 'accessory':(('accessories','access',{k:v for k,v in ACCESS.items() if k!='require_record_access'}),('accessories','catalog',{'resolve':'resolve_accessory_id','aliases':'accessory_id_aliases'})),
 'advance':(('control','access',ACCESS),),
 'chat':(('chat','access',{**ACCESS,'bounded_text':'bounded_text'}),),
 'feedback':(('feedback','access',ACCESS),('feedback','policy',{'sprite_flow':'pipeline_uses_photo_highlight_sprite_flow'}),('feedback','runtime',{'ensure_plan':'ensure_agent_mcp_pose_plan','now':'agent_mcp_now','skip_legacy':'mark_legacy_pose_flow_skipped_for_photo_highlight','mark_advancing':'mark_pipeline_task_advancing','pose_calls':'ensure_agent_mcp_pose_tool_calls','image_config':'agent_mcp_gemini_image_config','execute_calls':'execute_agent_mcp_pose_tool_calls','pause_task':'pause_agent_mcp_task'})),
}

def bind_external_pipeline_http(api,stack,scope):
    tasks=api._default_application.training_pipeline._pipeline_tasks
    for component,attribute,mapping in EXTERNAL[scope]:
        owner=getattr(tasks,component)
        overrides={field:(lambda name=name:getattr(api,name)) for field,name in mapping.items()}
        if scope=='list' and attribute=='reconciliation':overrides.update(monotonic=lambda:api.time.monotonic,min_interval=lambda:api.PIPELINE_TASKS_SYNC_MIN_INTERVAL_SECONDS)
        stack.enter_context(patch.object(owner,attribute,replace(getattr(owner,attribute),**overrides)))
    if scope=='advance':stack.enter_context(patch.object(tasks.control,'runtime',replace(tasks.control.runtime,now=lambda:api.time.time)))
    if scope=='chat':stack.enter_context(patch.object(tasks.chat,'runtime',replace(tasks.chat.runtime,deepcopy=lambda:api.copy.deepcopy)))


def assert_default_pipeline_http(api,scope):
    import unittest
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    from local_inspection_service.pipeline.task_list import PipelineTaskList
    from local_inspection_service.pipeline.accessory_routes import PipelineAccessoryRoutes
    from local_inspection_service.pipeline.advance_control import PipelineAdvanceController
    from local_inspection_service.pipeline.agent_chat import PipelineAgentChat
    from local_inspection_service.pipeline.agent_feedback import PipelineAgentFeedback
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;infra=app.infrastructure;tasks=graph._pipeline_tasks
    component,kind,alias={'list':('listing',PipelineTaskList,'_pipeline_task_list'),'accessory':('accessories',PipelineAccessoryRoutes,'_pipeline_accessory_routes'),'advance':('control',PipelineAdvanceController,'_pipeline_advance_controller'),'chat':('chat',PipelineAgentChat,'_pipeline_agent_chat'),'feedback':('feedback',PipelineAgentFeedback,'_pipeline_agent_feedback')}[scope]
    owner=getattr(tasks,component);case.assertIs(type(owner),kind);case.assertIs(getattr(api,alias),owner);case.assertIs(api._pipeline_tasks,tasks)
    case.assertIs(owner.access.current_user(),infra.current_auth_user)
    if scope!='list':case.assertIs(owner.access.http_error(),wiring.HTTPException)
    if scope not in ('list','accessory'):case.assertIs(owner.access.require_record_access(),infra.require_record_access)
    item,other,third=object(),object(),object()
    relays=[(owner.access.load_config(),infra._app_configuration,'load_config',(),{},(),{}),(owner.access.scope_config(),infra._account_projections,'scope_config_for_user',(item,other),{},(item,other,None),{})]
    if scope=='list':
        case.assertIs(owner.access.is_admin(),wiring.user_is_admin);case.assertIs(owner.access.visible(),infra.record_visible_to_user);case.assertIs(owner.access.has_permission(),wiring.user_has_permission)
        case.assertIs(owner.reconciliation.task_lock(),tasks.runtime.task_lock);case.assertIs(owner.reconciliation.monotonic(),wiring.time.monotonic)
        for field,name in (('load_tasks','load_pipeline_tasks'),('ensure_accessories','ensure_pipeline_task_accessory_objects'),('sync_ai_tasks','sync_pipeline_ai_detection_tasks'),('normalize_auto_defaults','normalize_pipeline_task_auto_advance_defaults'),('sync_and_advance','sync_and_auto_advance_pipeline'),('save_tasks','save_pipeline_tasks'),('collect_pregen','collect_pipeline_recommendation_pregen')):case.assertEqual(getattr(owner.reconciliation,field)(),getattr(tasks,name))
        for field,name in (('schedule_agent','schedule_pipeline_auto_agent'),('schedule_advance','schedule_pipeline_advance'),('schedule_pregen','schedule_pipeline_recommendation_pregen'),('optimize_by_id','auto_optimize_states_by_task_id'),('public_task','pipeline_task_public'),('accessories_payload','pipeline_accessories_payload')):case.assertEqual(getattr(owner.presentation,field)(),getattr(tasks,name))
        relays += [(owner.access.load_ai_tasks(),app.inspection._detection_task_store,'load_ai_detection_tasks',(),{},(),{}),(owner.reconciliation.save_config(),infra._app_configuration,'save_config',(item,),{},(item,),{}),(owner.presentation.trained_specs(),graph._trained_model_catalog,'list_trained_model_specs',(item,),{},(item,),{}),(owner.presentation.optimize_states(),graph._auto_optimization_state_store,'list_auto_optimize_states',(),{},(),{}),(owner.presentation.public_agent_config(),graph._agent_settings_projection,'public_agent_config',(),{},(None,),{}),(owner.presentation.sanitize(),infra._service_paths,'public_path_sanitized',(item,),{},(item,),{}),(api.get_pipeline_tasks,owner,'list_tasks',(),{},(None,),{}),(api.get_pipeline_tasks,owner,'list_tasks',('selected',),{},('selected',),{})]
        relays.append((owner.access.scope_config(),infra._account_projections,'scope_config_for_user',(item,other,'selected'),{},(item,other,'selected'),{}))
        for args in ((item,other,third),(item,other,third,'selected')):
            case.assertIs(owner.reconciliation.sync_ready_ai_tasks()(*args),False)
        with patch.object(wiring,'_incoming_task_access_allowed',autospec=True,return_value=third) as receiver:
            case.assertIs(owner.access.incoming_allowed()(item,other),third)
            receiver.assert_called_once();case.assertIs(receiver.call_args.args[0],item);case.assertIs(receiver.call_args.args[1],other)
            callbacks=receiver.call_args.kwargs;case.assertEqual(set(callbacks),{'is_admin','owner'})
            with patch.object(wiring,'user_is_admin',return_value=third) as admin:
                case.assertIs(callbacks['is_admin'](other),third);admin.assert_called_once_with(other)
            from unittest.mock import Mock
            original_owner=infra.record_owner_id;record_owner=Mock(return_value=third)
            try:
                object.__setattr__(infra,'record_owner_id',record_owner);case.assertIs(callbacks['owner'](item),third);record_owner.assert_called_once_with(item)
            finally:object.__setattr__(infra,'record_owner_id',original_owner)
        original=app.values.PIPELINE_TASKS_SYNC_MIN_INTERVAL_SECONDS;case.assertIs(owner.reconciliation.min_interval(),original)
        try:object.__setattr__(app.values,'PIPELINE_TASKS_SYNC_MIN_INTERVAL_SECONDS',third);case.assertIs(owner.reconciliation.min_interval(),third)
        finally:object.__setattr__(app.values,'PIPELINE_TASKS_SYNC_MIN_INTERVAL_SECONDS',original)
    elif scope=='accessory':
        relays += [(owner.catalog.resolve(),app.inspection._accessory_selection,'resolve_accessory_id',(item,'synthetic'),{},(item,'synthetic'),{}),(owner.catalog.aliases(),app.inspection._accessory_lookup,'accessory_id_aliases',(item,),{},(item,),{}),(api.add_pipeline_accessory,owner,'add',('synthetic',),{},('synthetic',),{}),(api.remove_pipeline_accessory,owner,'remove',('synthetic',),{},('synthetic',),{})]
        for field,name in (('add_id','add_pipeline_accessory_id'),('remove_id','remove_pipeline_accessory_id'),('public_payload','pipeline_accessories_payload')):case.assertEqual(getattr(owner.catalog,field)(),getattr(tasks,name))
    elif scope=='advance':
        case.assertIs(owner.runtime.now(),wiring.time.time);case.assertIs(owner.runtime.task_lock(),tasks.runtime.task_lock);case.assertIs(owner.runtime.registry_lock(),tasks.runtime.advance_registry_lock);case.assertIs(owner.runtime.inflight(),tasks.runtime.advance_inflight)
        relays += [(api.advance_pipeline_task_endpoint,owner,'advance',('synthetic',),{},('synthetic',),{}),(api.cancel_pipeline_advance_endpoint,owner,'cancel',('synthetic',),{},('synthetic',),{})]
    elif scope=='chat':
        case.assertIs(owner.access.bounded_text(),wiring.bounded_text);case.assertIs(owner.runtime.deepcopy(),wiring.copy.deepcopy);case.assertIs(owner.runtime.task_lock(),tasks.runtime.task_lock)
        relays.append((api.pipeline_agent_chat,owner,'chat',('synthetic',item),{},('synthetic',item),{}))
    else:
        relays.append((owner.runtime.mark_advancing(),graph._pipeline_task_mutations,'mark_pipeline_task_advancing',(item,),{},(item,),{}))
        relays += [(owner.runtime.ensure_plan(),graph._photo_highlight_workflow,'ensure_agent_mcp_pose_plan',(item,other),{},(item,other),{'force':False}),(owner.runtime.ensure_plan(),graph._photo_highlight_workflow,'ensure_agent_mcp_pose_plan',(item,other),{'force':True},(item,other),{'force':True}),(owner.runtime.now(),graph._agent_orchestration_state,'agent_mcp_now',(),{},(),{}),(owner.runtime.skip_legacy(),graph._photo_highlight_workflow,'mark_legacy_pose_flow_skipped_for_photo_highlight',(item,other,third),{},(item,other,third),{}),(owner.runtime.pose_calls(),graph._pose_call_registration,'ensure_agent_mcp_pose_tool_calls',(item,other),{},(item,other),{}),(owner.runtime.image_config(),graph._pose_render_configuration,'agent_mcp_gemini_image_config',(),{},(),{}),(owner.runtime.execute_calls(),graph._pose_call_execution,'execute_agent_mcp_pose_tool_calls',(item,other),{},(item,other),{}),(owner.runtime.pause_task(),graph._agent_orchestration_state,'pause_agent_mcp_task',(item,other),{'stage':'stage','reason':'reason','suggested_actions':[third]},(item,other),{'stage':'stage','reason':'reason','suggested_actions':[third]}),(api.pipeline_agent_feedback,owner,'feedback',('synthetic',item),{},('synthetic',item),{})]
        for items,expected in (([],False),([third],True)):
            with patch.object(type(graph._photo_highlight_selection),'pipeline_photo_highlight_object_items',autospec=True,return_value=items) as receiver:
                case.assertIs(owner.policy.sprite_flow()(item,other),expected);receiver.assert_called_once_with(graph._photo_highlight_selection,item,other)
    for selected,target,method,args,keywords,forwarded,forward_keywords in relays:
        if method=='pause_agent_mcp_task':forward_keywords=keywords
        assert_native_relay(case,selected,(target,method,args,keywords,forwarded,forward_keywords))

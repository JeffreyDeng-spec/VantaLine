"""Finite external test ports for pipeline state and background contracts."""
from dataclasses import replace
from unittest.mock import patch

GROUPS={
 'ai':('_pipeline_stages.ai_sync',{'identity':{'safe_record_id':'safe_record_id','sanitize_ai_detection_task_id':'sanitize_ai_detection_task_id','ai_detection_task_model_id':'ai_detection_task_model_id'},'accessories':{'accessory_lookup_by_id':'accessory_lookup_by_id','accessory_material_type':'accessory_material_type'},'access':{'source':'PIPELINE_DASHBOARD_AI_TASK_SOURCE','record_visible_to_user':'record_visible_to_user','load_ai_detection_tasks':'load_ai_detection_tasks'},'projection':{'clean_ai_detection_task_name':'clean_ai_detection_task_name','now':'time.time'}}),
 'snapshots':('_pipeline_queries.snapshots',{'links':{'load_ai_tasks':'load_ai_detection_tasks','accessory_lookup':'accessory_lookup_by_id'}}),
 'resources':('_pipeline_queries.resources',{'links':{'find_dataset':'find_dataset_resource','load_ai_tasks':'load_ai_detection_tasks','list_trained_specs':'list_trained_model_specs'}}),
 'training':('_pipeline_stages.training',{'lookup':{'load':'load_training_task','path':'training_task_path','public':'public_refreshed_training_task'},'effects':{'orchestration':'agent_mcp_orchestration','set_stage':'set_agent_mcp_stage'}}),
 'reconciliation':('_pipeline_stages.reconciliation',{'registry':{'timeout':'PIPELINE_ADVANCE_ZOMBIE_TIMEOUT_S','now':'time.time'},'calls':{'load_agent_config':'load_agent_config','supported':'agent_recommendation_supported','training_finder':'training_task_finder','orchestration':'agent_mcp_orchestration'}}),
 'recommendation':('_pipeline_execution.recommendation',{'execution':{'identity':'_request_user','recommend':'agent_recommendation','clock':'time.time','traceback':'traceback.print_exc','stderr':'sys.stderr'},'scheduling':{'thread':'threading.Thread'}}),
 'auto':('_pipeline_execution.auto',{'tasks':{'orchestration':'agent_mcp_orchestration','max_steps':'AGENT_MCP_AUTO_MAX_STEPS','pause':'pause_agent_mcp_task','deepcopy':'copy.deepcopy'},'decision':{'scope_config':'scope_config_for_user','load_config':'load_config','now':'agent_mcp_now'},'execution':{'identity':'_request_user','traceback':'traceback.print_exc','stderr':'sys.stderr'},'scheduling':{'thread':'threading.Thread'}}),
 'advance':('_pipeline_execution.advance',{'tasks':{'deepcopy':'copy.deepcopy'},'policy':{'cancelled_error':'PipelineAdvanceCancelled','http_error':'HTTPException','orchestration':'agent_mcp_orchestration','pause':'pause_agent_mcp_task','bounded_text':'bounded_text'},'execution':{'identity':'_request_user','scope_config':'scope_config_for_user','load_config':'load_config','clock':'time.time','traceback':'traceback.print_exc','stderr':'sys.stderr','print':'print'},'scheduling':{'event':'threading.Event','thread':'threading.Thread'}}),
 'stage':('_pipeline_stages.advance',{'policy':{'recommend':'agent_recommendation','orchestration':'agent_mcp_orchestration','pause':'pause_agent_mcp_task','training_quality':'agent_mcp_training_quality_gate','link_model':'link_pipeline_trained_model','http_error':'HTTPException','cancelled_error':'PipelineAdvanceCancelled'},'assets':{'load_config':'load_config','save_config':'save_config','prepare':'prepare_agent_mcp_before_sample_generation','materialize':'materialize_agent_mcp_pose_assets','normalize':'ensure_training_normalized_assets_for_selection'},'jobs':{'request_type':'TrainingStartRequest','sample_generation':'request_sample_generation','training':'request_training','task_name':'task_record_name','log_samples':'log_agent_mcp_sample_tool_call','log_training':'log_agent_mcp_training_tool_call'},'runtime':{'monotonic':'time.monotonic','clock':'time.time','print':'print','persist_progress':'persist_pipeline_task_progress'}}),
}


def _owner(api,path):
    graph=api._default_application.training_pipeline
    for part in path.split('.'):graph=getattr(graph,part)
    return graph


def _supplier(api,name):
    def resolve():
        value=api
        for part in name.split('.'):value=getattr(value,part)
        return value
    return resolve


def bind_external_pipeline_state(api,stack,scope):
    if not hasattr(api,'_default_application'):return
    path,groups=GROUPS[scope];owner=_owner(api,path)
    for attribute,fields in groups.items():
        stack.enter_context(patch.object(owner,attribute,replace(getattr(owner,attribute),**{field:_supplier(api,name) for field,name in fields.items()})))


def assert_default_pipeline_state(api,scope):
    import builtins,unittest
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    from local_inspection_service.detection.task_identity import clean_ai_detection_task_name,sanitize_ai_detection_task_id
    from local_inspection_service.schemas.training import TrainingStartRequest
    if not hasattr(api,'_default_application'):return
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;infra=app.infrastructure;inspection=app.inspection
    path,groups=GROUPS[scope];owner=_owner(api,path)
    module,class_name,alias={
     'ai':('ai_task_sync','PipelineAiTaskSync','_pipeline_ai_task_sync'),
     'snapshots':('task_snapshots','PipelineTaskSnapshots','_pipeline_task_snapshots'),
     'resources':('resource_status','PipelineResourceStatus','_pipeline_resource_status'),
     'training':('training_status','PipelineTrainingStatus','_pipeline_training_status'),
     'reconciliation':('reconciliation','PipelineReconciliation','_pipeline_reconciliation'),
     'recommendation':('recommendation_runtime','PipelineRecommendationRuntime','_pipeline_recommendation_runtime'),
     'auto':('auto_agent_runtime','PipelineAutoAgentRuntime','_pipeline_auto_agent_runtime'),
     'advance':('advance_runtime','PipelineAdvanceRuntime','_pipeline_advance_runtime'),
     'stage':('stage_advance','PipelineStageAdvancer','_pipeline_stage_advancer'),
    }[scope]
    import importlib
    case.assertIs(type(owner),getattr(importlib.import_module('local_inspection_service.pipeline.'+module),class_name))
    case.assertIs(getattr(api,alias),owner)
    item,other,third=object(),object(),object()
    specs={
     'safe_record_id':(inspection._pose_collection_jobs,'safe_record_id',(item,),{},(item,),{}),
     'accessory_lookup_by_id':(inspection._accessory_lookup,'accessory_lookup_by_id',(item,),{},(item,),{}),
     'load_ai_detection_tasks':(inspection._detection_task_store,'load_ai_detection_tasks',(),{},(),{}),
     'find_dataset_resource':(graph._dataset_catalog,'find_dataset_resource',('synthetic',),{},('synthetic',None),{'include_samples':False,'write':False}),
     'list_trained_model_specs':(graph._trained_model_catalog,'list_trained_model_specs',(),{},(None,),{}),
     'load_training_task':(graph._training_state_workflows,'load_training_task',(item,),{},(item,),{}),
     'training_task_path':(graph._training_state_workflows,'training_task_path',('synthetic',),{},('synthetic',),{}),
     'public_refreshed_training_task':(graph._training_state_workflows,'public_refreshed_training_task',(item,),{},(item,),{'allow_remote_refresh':False}),
     'agent_mcp_orchestration':(graph._agent_orchestration_state,'agent_mcp_orchestration',(item,),{},(item,),{}),
     'agent_mcp_now':(graph._agent_orchestration_state,'agent_mcp_now',(),{},(),{}),
     'set_agent_mcp_stage':(graph._agent_orchestration_state,'set_agent_mcp_stage',(item,'stage','running',13),{'extra':third},(item,'stage','running',13),{'extra':third}),
     'load_agent_config':(infra._model_profile_configuration,'load_agent_config',(),{},(),{}),
     'load_config':(infra._app_configuration,'load_config',(),{},(),{}),
     'save_config':(infra._app_configuration,'save_config',(item,),{},(item,),{}),
     'scope_config_for_user':(infra._account_projections,'scope_config_for_user',(item,other),{},(item,other,None),{}),
     'agent_recommendation_supported':(graph._agent_settings_projection,'agent_recommendation_supported',(item,),{},(item,),{}),
     'training_task_finder':(graph._training_task_lookup,'training_task_finder',(),{},(),{}),
     'agent_recommendation':(graph._agent_recommendation,'agent_recommendation',('stage',[item]),{},('stage',[item],None),{}),
     'pause_agent_mcp_task':(graph._agent_orchestration_state,'pause_agent_mcp_task',(item,other),{'stage':'stage','reason':'reason','suggested_actions':[third]},(item,other),{'stage':'stage','reason':'reason','suggested_actions':[third]}),
     'agent_mcp_training_quality_gate':(graph._agent_orchestration_state,'agent_mcp_training_quality_gate',(item,),{},(item,),{}),
     'link_pipeline_trained_model':(graph._pipeline_trained_model_link,'link_pipeline_trained_model',(item,),{},(item,),{}),
     'prepare_agent_mcp_before_sample_generation':(graph._pose_sample_preparation,'prepare_agent_mcp_before_sample_generation',(item,other),{},(item,other),{}),
     'materialize_agent_mcp_pose_assets':(graph._pose_asset_materialization,'materialize_agent_mcp_pose_assets',(item,other),{},(item,other),{}),
     'ensure_training_normalized_assets_for_selection':(graph._training_asset_preparation,'ensure_training_normalized_assets_for_selection',(item,other),{},(item,other),{}),
     'task_record_name':(infra._resource_names,'task_record_name',(item,),{},(item,),{}),
     'log_agent_mcp_sample_tool_call':(graph._agent_tool_call_records,'log_agent_mcp_sample_tool_call',(item,other),{},(item,other),{}),
     'log_agent_mcp_training_tool_call':(graph._agent_tool_call_records,'log_agent_mcp_training_tool_call',(item,other),{},(item,other),{}),
    }
    direct={'record_visible_to_user':infra.record_visible_to_user,'sanitize_ai_detection_task_id':sanitize_ai_detection_task_id,'clean_ai_detection_task_name':clean_ai_detection_task_name,'HTTPException':wiring.HTTPException,'PipelineAdvanceCancelled':wiring.PipelineAdvanceCancelled,'TrainingStartRequest':TrainingStartRequest,'bounded_text':wiring.bounded_text,'_request_user':infra._request_user,'print':builtins.print,'request_sample_generation':app.http.request_sample_generation,'request_training':app.http.request_training}
    for attribute,fields in groups.items():
        port=getattr(owner,attribute)
        for field,name in fields.items():
            selected=getattr(port,field)()
            if name in specs:
                target,method,args,keywords,forwarded,forward_keywords=specs[name]
                if name in ('pause_agent_mcp_task','agent_recommendation'):forward_keywords=keywords;forwarded=args if name=='pause_agent_mcp_task' else (*args,None)
                assert_native_relay(case,selected,(target,method,args,keywords,forwarded,forward_keywords))
                if name=='agent_recommendation':
                    explicit_args=('stage',[item],17)
                    assert_native_relay(case,selected,(target,method,explicit_args,{},explicit_args,{}))
            elif name in direct:case.assertEqual(selected,direct[name])
            elif '.' in name:
                value=wiring
                for part in name.split('.'):value=getattr(value,part)
                case.assertIs(selected,value)
            elif name in ('PIPELINE_DASHBOARD_AI_TASK_SOURCE','PIPELINE_ADVANCE_ZOMBIE_TIMEOUT_S','AGENT_MCP_AUTO_MAX_STEPS'):
                original=getattr(app.values,name);case.assertIs(selected,original)
                try:object.__setattr__(app.values,name,other);case.assertIs(getattr(port,field)(),other)
                finally:object.__setattr__(app.values,name,original)
            elif name=='accessory_material_type':
                with patch.object(wiring._accessory_policy,'accessory_material_type',return_value=other) as receiver:case.assertIs(selected(item),other);receiver.assert_called_once_with(item)
            elif name=='ai_detection_task_model_id':
                with patch.object(wiring,'_detection_task_model_id',return_value=other) as receiver:case.assertIs(selected('synthetic'),other);receiver.assert_called_once_with('synthetic',app.values.AI_DETECTION_TASK_PREFIX)
            elif name=='persist_pipeline_task_progress':
                case.assertEqual(selected,graph._pipeline_workflows.persist_pipeline_task_progress)
            else:raise AssertionError('Missing native witness '+name)

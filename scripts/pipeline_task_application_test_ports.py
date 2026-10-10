"""Finite external HTTP task ports; persistence and runtime remain caller owned."""
from dataclasses import replace
from unittest.mock import patch

EXTERNAL=(
    ('creator','access',{'current_user':'current_auth_user','require_permission':'require_permission','http_error':'HTTPException','is_admin':'user_is_admin','owner_fields':'owner_fields_for_new_record','fallback_owner':'resource_owner_id_for_new_record','scope_config':'scope_config_for_user','load_config':'load_config','accessory_lookup':'accessory_lookup_by_id','load_agent_config':'load_agent_config'}),
    ('creator','policy',{'normalize_expected_count':'normalize_expected_production_count','assert_unique_name':'assert_unique_task_name'}),
    ('creator','runtime',{'initialize_auto_optimize':'initialize_auto_optimize_for_pipeline_task','request_user':'_request_user'}),
    ('updater','access',{'current_user':'current_auth_user','http_error':'HTTPException','load_config':'load_config','scope_config':'scope_config_for_user','require_record_access':'require_record_access','require_permission':'require_permission','assert_unique_name':'assert_unique_task_name','record_owner_id':'record_owner_id'}),
    ('updater','policy',{'detection_methods':'PIPELINE_DETECTION_METHODS','normalize_expected_count':'normalize_expected_production_count'}),
    ('deleter','access',{'current_user':'current_auth_user','require_record_access':'require_record_access','http_error':'HTTPException'}),
    ('deleter','cleanup',{'delete_dataset':'delete_training_dataset_resource','delete_model':'delete_training_model_resource','delete_training_job':'delete_training_task_record','delete_ai_task':'delete_ai_detection_task_record'}),
)


def bind_external_task_http(api,stack):
    tasks=api._default_application.training_pipeline._pipeline_tasks
    def supplier(name):return lambda:getattr(api,name)
    for component,attribute,fields in EXTERNAL:
        owner=getattr(tasks,component);extra={field:supplier(name) for field,name in fields.items()}
        if component=='creator' and attribute=='runtime':
            extra.update(uuid4=lambda:api.uuid.uuid4,now=lambda:api.time.time)
        stack.enter_context(patch.object(owner,attribute,replace(getattr(owner,attribute),**extra)))
    stack.enter_context(patch.object(tasks.updater,'runtime',replace(tasks.updater.runtime,now=lambda:api.time.time)))


def assert_default_task_http(api):
    import unittest
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.pipeline.task_create import PipelineTaskCreator
    from local_inspection_service.pipeline.task_update import PipelineTaskUpdater
    from local_inspection_service.pipeline.task_delete import PipelineTaskDeleter
    from local_inspection_service.runtime.wiring import training_pipeline
    from local_inspection_service.training.auto_optimization_settings import normalize_expected_production_count
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;infra=app.infrastructure
    tasks=graph._pipeline_tasks;case.assertIs(api._pipeline_tasks,tasks)
    for owner,kind in ((tasks.creator,PipelineTaskCreator),(tasks.updater,PipelineTaskUpdater),(tasks.deleter,PipelineTaskDeleter)):
        case.assertIs(type(owner),kind)
    case.assertIs(api._pipeline_task_creator,tasks.creator)
    case.assertIs(api._pipeline_task_updater,tasks.updater)
    case.assertIs(api._pipeline_task_deleter,tasks.deleter)
    for owner in (tasks.creator,tasks.updater,tasks.deleter):
        case.assertIs(owner.access.current_user(),infra.current_auth_user)
        case.assertIs(owner.access.http_error(),training_pipeline.HTTPException)
        case.assertIs(owner.runtime.lock(),tasks.runtime.task_lock)
    case.assertIs(tasks.creator.access.require_permission(),infra.require_permission)
    case.assertIs(tasks.updater.access.require_permission(),infra.require_permission)
    case.assertIs(tasks.creator.access.owner_fields(),infra.owner_fields_for_new_record)
    case.assertIs(tasks.updater.access.record_owner_id(),infra.record_owner_id)
    case.assertIs(tasks.updater.access.require_record_access(),infra.require_record_access)
    case.assertIs(tasks.deleter.access.require_record_access(),infra.require_record_access)
    case.assertIs(tasks.creator.runtime.request_user(),infra._request_user)
    case.assertIs(tasks.creator.runtime.uuid4(),training_pipeline.uuid.uuid4)
    case.assertIs(tasks.creator.runtime.now(),training_pipeline.time.time)
    case.assertIs(tasks.updater.runtime.now(),training_pipeline.time.time)
    case.assertIs(tasks.creator.access.is_admin(),training_pipeline.user_is_admin)
    case.assertIs(tasks.creator.policy.normalize_expected_count(),normalize_expected_production_count)
    case.assertIs(tasks.updater.policy.normalize_expected_count(),normalize_expected_production_count)
    item,other=object(),object()
    for selected,target,method,args,keywords,forwarded,forward_keywords in (
        (tasks.creator.access.load_config(),infra._app_configuration,'load_config',(),{},(),{}),
        (tasks.updater.access.load_config(),infra._app_configuration,'load_config',(),{},(),{}),
        (tasks.creator.access.scope_config(),infra._account_projections,'scope_config_for_user',(item,other),{},(item,other,None),{}),
        (tasks.creator.access.scope_config(),infra._account_projections,'scope_config_for_user',(item,other,'selected-owner'),{},(item,other,'selected-owner'),{}),
        (tasks.updater.access.scope_config(),infra._account_projections,'scope_config_for_user',(item,other),{},(item,other,None),{}),
        (tasks.creator.access.fallback_owner(),infra._resource_names,'resource_owner_id_for_new_record',(item,),{},(item,),{}),
        (tasks.creator.access.accessory_lookup(),app.inspection._accessory_lookup,'accessory_lookup_by_id',(item,),{},(item,),{}),
        (tasks.creator.access.load_agent_config(),infra._model_profile_configuration,'load_agent_config',(),{},(),{}),
        (tasks.creator.runtime.initialize_auto_optimize(),graph._auto_optimization_initialization,'initialize_auto_optimize_for_pipeline_task',(item,other),{},(item,other),{}),
        (api.create_pipeline_task,tasks.creator,'create',(item,),{},(item,None),{}),
        (api.create_pipeline_task,tasks.creator,'create',(item,),{'user_id':'owner-fixture'},(item,'owner-fixture'),{}),
        (api.update_pipeline_task,tasks.updater,'update',('synthetic-task',item),{},('synthetic-task',item),{}),
        (api.delete_pipeline_task,tasks.deleter,'delete',('synthetic-task',),{},('synthetic-task',),{}),
    ):
        assert_native_relay(case,selected,(target,method,args,keywords,forwarded,forward_keywords))
    for selected in (tasks.creator.policy.assert_unique_name(),tasks.updater.access.assert_unique_name()):
        assert_native_relay(case,selected,(infra._resource_names,'assert_unique_task_name',(item,'owner'),{},(item,'owner'),{'exclude_pipeline_task_id':'','exclude_ai_task_id':''}))
        assert_native_relay(case,selected,(infra._resource_names,'assert_unique_task_name',(item,'owner'),{'exclude_pipeline_task_id':'pipeline','exclude_ai_task_id':'ai'},(item,'owner'),{'exclude_pipeline_task_id':'pipeline','exclude_ai_task_id':'ai'}))
    for selected,target,method in ((tasks.deleter.cleanup.delete_dataset(),graph._training_resource_mutations,'delete_training_dataset_resource'),
        (tasks.deleter.cleanup.delete_model(),graph._training_resource_mutations,'delete_training_model_resource'),
        (tasks.deleter.cleanup.delete_training_job(),graph._training_state_workflows,'delete_training_task_record'),
        (tasks.deleter.cleanup.delete_ai_task(),app.inspection._detection_task_requests,'delete_ai_detection_task_record')):
        for keywords in ({},{'missing_ok':True}):
            assert_native_relay(case,selected,(target,method,('synthetic',other),keywords,('synthetic',other),{'missing_ok':bool(keywords)}))
    original=app.values.PIPELINE_DETECTION_METHODS;case.assertIs(tasks.updater.policy.detection_methods(),original)
    try:
        object.__setattr__(app.values,'PIPELINE_DETECTION_METHODS',other);case.assertIs(tasks.updater.policy.detection_methods(),other)
    finally:object.__setattr__(app.values,'PIPELINE_DETECTION_METHODS',original)

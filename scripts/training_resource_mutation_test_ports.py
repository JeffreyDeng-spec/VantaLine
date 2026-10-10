"""Finite resource mutation test edges with original guarded retirement services."""
from dataclasses import replace
from unittest.mock import patch,Mock

DIRECT=(('access',{'current':'current_auth_user','require':'require_record_access','owner':'record_owner_id'}),('catalog',{'find':'find_dataset_resource','models':'list_trained_model_specs','payload':'training_resources_payload'}),('retirement',{'delete_dataset':'delete_training_dataset_resource','delete_model':'delete_training_model_resource','training_dataset':'mark_training_task_dataset_deleted','pipeline_dataset':'mark_pipeline_dataset_deleted','pipeline_model':'mark_pipeline_model_deleted'}))
GETTERS=(('access',{'unique_dataset':'assert_unique_dataset_name','unique_model':'assert_unique_model_name'}),('catalog',{'resolve':'resolve_service_path'}))


def bind_training_resource_mutations(api,stack):
    graph=api._default_application.training_pipeline;owner=graph._training_resource_mutations;training=graph._training_dataset_links;pipeline=graph._pipeline_resource_links
    for attribute,mapping in DIRECT:
        stack.enter_context(patch.object(owner,attribute,replace(getattr(owner,attribute),**{field:(lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)) for field,name in mapping.items()})))
    for attribute,mapping in GETTERS:
        stack.enter_context(patch.object(owner,attribute,replace(getattr(owner,attribute),**{field:(lambda _name=name:getattr(api,_name)) for field,name in mapping.items()})))
    stack.enter_context(patch.object(training,'guard',lambda:api._training_task_lock))
    stack.enter_context(patch.object(training,'records',replace(training.records,load=lambda:api.load_training_task_records(),save=lambda item:api.save_training_task(item),dataset_id=lambda item:api.training_task_dataset_resource_id(item))))
    stack.enter_context(patch.object(training,'mutable',lambda item,user:api.record_mutable_by_user(item,user)));stack.enter_context(patch.object(training,'clean',lambda value:api.clean_training_resource_id(value)))
    stack.enter_context(patch.object(pipeline,'guard',lambda:api._pipeline_tasks_lock));stack.enter_context(patch.object(pipeline,'load',lambda:api.load_pipeline_tasks()));stack.enter_context(patch.object(pipeline,'save_batch',lambda tasks,changed:api.save_pipeline_task_batch_changes(tasks,changed)));stack.enter_context(patch.object(pipeline,'mutable',lambda item,user:api.record_mutable_by_user(item,user)))


def assert_default_training_resource_mutations(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.training_records_application_test_ports import _frozen_slot
    from local_inspection_service.training.resource_mutations import TrainingResourceMutations
    from local_inspection_service.training.dataset_links import TrainingDatasetLinks
    from local_inspection_service.pipeline.resource_links import PipelineResourceLinks
    from local_inspection_service.runtime.wiring import training_pipeline
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;infra=app.infrastructure;owner=graph._training_resource_mutations;training=graph._training_dataset_links;pipeline=graph._pipeline_resource_links;item,other=object(),object()
    for name,kind in (('_training_resource_mutations',TrainingResourceMutations),('_training_dataset_links',TrainingDatasetLinks),('_pipeline_resource_links',PipelineResourceLinks)):
        case.assertIs(type(getattr(graph,name)),kind);case.assertIs(getattr(api,name),getattr(graph,name))
    case.assertIs(owner.files,app.artifacts.files);case.assertIs(training.guard(),graph._training_task_runtime.lock);case.assertIs(pipeline.guard(),graph._pipeline_runtime.task_lock)
    for selected,name,args,kw in ((owner.access.current,'current_auth_user',(),{}),(owner.access.require,'require_record_access',(item,other),{'write':True}),(owner.access.owner,'record_owner_id',(item,),{}),(training.mutable,'record_mutable_by_user',(item,other),{}),(pipeline.mutable,'record_mutable_by_user',(item,other),{})):
        receiver=Mock(return_value=other)
        with _frozen_slot(infra,name,receiver):case.assertIs(selected(*args,**kw),other);receiver.assert_called_once_with(*args,**kw)
    for selected,target,method,args,kw,forwarded,expected_kw in ((owner.access.unique_dataset(),infra._resource_names,'assert_unique_dataset_name',(item,'owner',other),{},(item,'owner',other),{'exclude_dataset_id':''}),(owner.access.unique_model(),infra._resource_names,'assert_unique_model_name',(item,'owner'),{},(item,'owner'),{'exclude_run_id':''}),(owner.catalog.find,graph._dataset_catalog,'find_dataset_resource',(item,),{'user':other,'include_samples':False,'write':True},(item,other),{'include_samples':False,'write':True}),(owner.catalog.models,graph._trained_model_catalog,'list_trained_model_specs',(),{},(None,),{}),(owner.catalog.resolve(),infra._service_paths,'resolve_service_path',(item,),{},(item,),{'for_write':False}),(owner.catalog.payload,graph._training_resources,'training_resources_payload',(),{'user':item},(),{'include_samples':False,'user':item,'target_user_id':None}),(owner.retirement.delete_dataset,owner,'delete_training_dataset_resource',(item,other),{},(item,other),{'missing_ok':False}),(owner.retirement.delete_model,owner,'delete_training_model_resource',(item,other),{'missing_ok':True},(item,other),{'missing_ok':True}),(owner.retirement.training_dataset,training,'mark_training_task_dataset_deleted',(item,other),{},(item,other),{}),(owner.retirement.pipeline_dataset,pipeline,'mark_pipeline_dataset_deleted',(item,other),{},(item,other),{}),(owner.retirement.pipeline_model,pipeline,'mark_pipeline_model_deleted',(item,other),{},(item,other),{}),(training.records.load,graph._training_state_workflows,'load_training_task_records',(),{},(),{}),(training.records.save,graph._training_state_workflows,'save_training_task',(item,),{},(item,),{}),(training.records.dataset_id,graph._dataset_catalog,'training_task_dataset_resource_id',(item,),{},(item,),{}),(pipeline.load,graph._pipeline_task_store,'load_pipeline_tasks',(),{},(),{}),(pipeline.save_batch,graph._pipeline_task_mutations,'save_pipeline_task_batch_changes',(item,other),{},(item,other),{})):
        assert_native_relay(case,selected,(target,method,args,kw,forwarded,expected_kw))
    with patch.object(training_pipeline,'clean_training_resource_id',return_value=other) as receiver:case.assertIs(training.clean(item),other);receiver.assert_called_once_with(item)


    assert_native_relay(case,owner.access.unique_dataset(),(infra._resource_names,'assert_unique_dataset_name',(item,'owner',other),{'exclude_dataset_id':'selected'},(item,'owner',other),{'exclude_dataset_id':'selected'}))
    assert_native_relay(case,owner.access.unique_model(),(infra._resource_names,'assert_unique_model_name',(item,'owner'),{'exclude_run_id':'selected'},(item,'owner'),{'exclude_run_id':'selected'}))
    assert_native_relay(case,owner.retirement.delete_dataset,(owner,'delete_training_dataset_resource',(item,other),{'missing_ok':True},(item,other),{'missing_ok':True}))
    assert_native_relay(case,owner.retirement.delete_model,(owner,'delete_training_model_resource',(item,other),{'missing_ok':False},(item,other),{'missing_ok':False}))
    assert_default_resource_marker_database(api)


def assert_default_resource_marker_database(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.training_records_application_test_ports import assert_default_training_records
    assert_default_training_records(api);case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;infra=app.infrastructure;store=graph._pipeline_task_store;storage=graph._pipeline_task_mutations.storage;item,other=object(),object()
    case.assertIs(store,graph._pipeline_persistence.tasks)
    for selected in (store.repository,storage.runtime_postgres_repository_or_none()):assert_native_relay(case,selected,(infra._runtime_repository_access,'runtime_postgres_repository_or_none',(),{},(),{}))
    assert_native_relay(case,store.resolver(),(infra._model_profile_configuration,'resolve_model_profiles',(),{},(),{}))
    for selected,name in ((store.paths.data,'DATA_DIR'),(store.paths.tasks,'PIPELINE_TASKS_PATH')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)
    for selected,method in ((storage.save_pipeline_task(),'save_pipeline_task'),(storage.save_pipeline_tasks(),'save_pipeline_tasks')):
        case.assertIs(selected.__self__,graph._pipeline_workflows);case.assertIs(selected.__func__,getattr(type(graph._pipeline_workflows),method))
        assert_native_relay(case,selected,(graph._pipeline_persistence,method,(item,),{},(item,),{}))


def bind_resource_marker_database(api,stack):
    from scripts.training_records_application_test_ports import bind_training_records,_frozen_slot
    assert_default_resource_marker_database(api)
    bind_training_records(api,stack)
    graph=api._default_application.training_pipeline;store=graph._pipeline_task_store;mutations=graph._pipeline_task_mutations
    stack.enter_context(patch.object(store,'repository',lambda:api.runtime_postgres_repository_or_none()))
    stack.enter_context(patch.object(store,'paths',replace(store.paths,data=lambda:api.DATA_DIR,tasks=lambda:api.PIPELINE_TASKS_PATH)))
    stack.enter_context(patch.object(store,'resolver',lambda:api.resolve_model_profiles))
    stack.enter_context(_frozen_slot(mutations,'storage',replace(mutations.storage,runtime_postgres_repository_or_none=lambda:api.runtime_postgres_repository_or_none,save_pipeline_task=lambda:api.save_pipeline_task,save_pipeline_tasks=lambda:api.save_pipeline_tasks)))

"""Finite resource query ports, including the existing registered read closures."""
from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import patch,Mock

CATALOG=(('paths',{'roots':'training_dataset_roots','clean':'clean_training_resource_id'}),('audit',{'fields':'record_audit_fields'}),('access',{'visible':'record_visible_to_user','mutable':'record_mutable_by_user'}))
CATALOG_GETTERS=(('paths',{'output':'OUTPUT_DIR','resolve':'resolve_service_path'}),('audit',{'created':'record_created_at','updated':'record_updated_at'}))
RESOURCES=(('datasets',{'roots':'training_dataset_roots','item':'dataset_resource_item','task_id':'training_task_dataset_resource_id'}),('records',{'tasks':'list_training_tasks','models':'list_trained_model_specs','ai':'load_ai_detection_tasks'}),('config',{'load':'load_config','serialize_ai':'serialize_ai_detection_task'}),('access',{'visible':'record_visible_to_user','owner_username':'record_owner_username','sanitize':'public_path_sanitized'}))


def read_cell(function,name):
    return dict(zip(function.__code__.co_freevars,function.__closure__ or ()))[name]


@contextmanager
def replace_read_cell(function,name,value):
    cell=read_cell(function,name);original=cell.cell_contents;cell.cell_contents=value
    try:yield
    finally:cell.cell_contents=original


def bind_training_resources(api,stack):
    graph=api._default_application.training_pipeline;catalog=graph._dataset_catalog;resources=graph._training_resources
    for owner,groups in ((catalog,CATALOG),(resources,RESOURCES)):
        for attribute,mapping in groups:
            stack.enter_context(patch.object(owner,attribute,replace(getattr(owner,attribute),**{field:(lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)) for field,name in mapping.items()})))
    for attribute,mapping in CATALOG_GETTERS:
        stack.enter_context(patch.object(catalog,attribute,replace(getattr(catalog,attribute),**{field:(lambda _name=name:getattr(api,_name)) for field,name in mapping.items()})))
    stack.enter_context(patch.object(catalog,'read',lambda path:api.load_json_file_mtime_cached(path)));stack.enter_context(patch.object(catalog,'item',lambda path,**kw:api.dataset_resource_item(path,**kw)))
    stack.enter_context(patch.object(resources,'config',replace(resources.config,scope=lambda:api.scope_config_for_user)))
    stack.enter_context(patch.object(resources,'access',replace(resources.access,legacy_owner=lambda:api.LEGACY_OWNER_ID)))
    stack.enter_context(patch.object(resources,'resolve',lambda:api.resolve_service_path));stack.enter_context(patch.object(resources,'output',lambda:api.OUTPUT_DIR))
    access=read_cell(api.training_resources,'access').cell_contents
    stack.enter_context(replace_read_cell(api.training_resources,'access',replace(access,current=lambda:api.current_auth_user(),is_admin=lambda user:api.user_is_admin(user),sanitize=lambda value:api.public_path_sanitized(value))))
    stack.enter_context(replace_read_cell(api.training_resources,'payload',lambda:api.training_resources_payload))
    stack.enter_context(replace_read_cell(api.training_dataset_detail,'find',lambda value,**kw:api.find_dataset_resource(value,**kw)))


def assert_default_training_resources(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.training_records_application_test_ports import _frozen_slot
    from local_inspection_service.training.dataset_catalog import DatasetCatalog,clean_training_resource_id
    from local_inspection_service.training.resource_queries import TrainingResources
    from local_inspection_service.runtime.wiring import http_registration
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;infra=app.infrastructure;catalog=graph._dataset_catalog;resources=graph._training_resources;item,other=object(),object()
    case.assertIs(type(catalog),DatasetCatalog);case.assertIs(type(resources),TrainingResources);case.assertIs(api._dataset_catalog,catalog);case.assertIs(api._training_resources,resources)
    case.assertIs(catalog.files,app.artifacts.files);case.assertIs(resources.files,app.artifacts.files)
    for selected,name in ((catalog.paths.output,'OUTPUT_DIR'),(resources.output,'OUTPUT_DIR'),(resources.access.legacy_owner,'LEGACY_OWNER_ID')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)
    for selected,name,args in ((catalog.read,'load_json_file_mtime_cached',(item,)),(catalog.audit.fields,'record_audit_fields',(item,other)),(catalog.access.visible,'record_visible_to_user',(item,other)),(catalog.access.mutable,'record_mutable_by_user',(item,other)),(resources.access.visible,'record_visible_to_user',(item,other,'selected')),(resources.access.owner_username,'record_owner_username',(item,))):
        receiver=Mock(return_value=other)
        with _frozen_slot(infra,name,receiver):case.assertIs(selected(*args),other);receiver.assert_called_once_with(*args)
    for selected,method,args,kw,forwarded,forward_kw in ((catalog.item,'dataset_resource_item',(item,),{},(item,),{'include_samples':True}),(catalog.paths.roots,'training_dataset_roots',(),{},(),{}),(resources.datasets.roots,'training_dataset_roots',(),{},(),{}),(resources.datasets.item,'dataset_resource_item',(item,),{'include_samples':False},(item,),{'include_samples':False}),(resources.datasets.task_id,'training_task_dataset_resource_id',(item,),{},(item,),{})):
        assert_native_relay(case,selected,(catalog,method,args,kw,forwarded,forward_kw))
    for selected,target,method,args,kw,expected,expected_kw in ((resources.records.tasks,graph._training_state_workflows,'list_training_tasks',(),{'user':item,'target_user_id':other},(item,other),{'allow_remote_refresh':False}),(resources.records.models,graph._trained_model_catalog,'list_trained_model_specs',(),{},(None,),{}),(resources.records.ai,app.inspection._detection_task_store,'load_ai_detection_tasks',(),{},(),{}),(resources.config.load,infra._app_configuration,'load_config',(),{},(),{}),(resources.config.scope(),infra._account_projections,'scope_config_for_user',(item,other),{},(item,other,None),{}),(resources.config.serialize_ai,app.inspection._detection_task_projection,'serialize_ai_detection_task',(item,other),{},(item,other),{}),(resources.access.sanitize,infra._service_paths,'public_path_sanitized',(item,),{},(item,),{}),(resources.resolve(),infra._service_paths,'resolve_service_path',(item,),{},(item,),{'for_write':False}),(catalog.paths.resolve(),infra._service_paths,'resolve_service_path',(item,),{},(item,),{'for_write':False})):
        assert_native_relay(case,selected,(target,method,args,kw,expected,expected_kw))
    access=read_cell(api.training_resources,'access').cell_contents;case.assertIs(read_cell(api.training_dataset_detail,'access').cell_contents,access)
    receiver=Mock(return_value=other)
    with _frozen_slot(infra,'current_auth_user',receiver):case.assertIs(access.current(),other);receiver.assert_called_once_with()
    with patch.object(http_registration,'user_is_admin',return_value=other) as receiver:case.assertIs(access.is_admin(item),other);receiver.assert_called_once_with(item)
    assert_native_relay(case,access.sanitize,(infra._service_paths,'public_path_sanitized',(item,),{},(item,),{}))
    assert_native_relay(case,read_cell(api.training_resources,'payload').cell_contents(),(resources,'training_resources_payload',(),{},(),{'include_samples':False,'user':None,'target_user_id':None}))
    assert_native_relay(case,read_cell(api.training_dataset_detail,'find').cell_contents,(catalog,'find_dataset_resource',(item,),{},(item,None),{'include_samples':False,'write':False}))

    from local_inspection_service.runtime.wiring import training_pipeline
    case.assertIs(catalog.audit.created(),training_pipeline.record_created_at);case.assertIs(catalog.audit.updated(),training_pipeline.record_updated_at)
    with patch.object(training_pipeline,'clean_training_resource_id',return_value=other) as receiver:case.assertIs(catalog.paths.clean(item),other);receiver.assert_called_once_with(item)
    assert_native_relay(case,catalog.item,(catalog,'dataset_resource_item',(item,),{'include_samples':False},(item,),{'include_samples':False}))
    assert_native_relay(case,resources.datasets.item,(catalog,'dataset_resource_item',(item,),{'include_samples':True},(item,),{'include_samples':True}))
    assert_native_relay(case,resources.config.scope(),(infra._account_projections,'scope_config_for_user',(item,other,'selected'),{},(item,other,'selected'),{}))
    payload_kw={'include_samples':True,'user':item,'target_user_id':other}
    assert_native_relay(case,read_cell(api.training_resources,'payload').cell_contents(),(resources,'training_resources_payload',(),payload_kw,(),payload_kw))
    assert_native_relay(case,read_cell(api.training_dataset_detail,'find').cell_contents,(catalog,'find_dataset_resource',(item,),{'user':other,'include_samples':True},(item,other),{'include_samples':True,'write':False}))

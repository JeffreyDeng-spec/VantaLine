"""Finite external ports for original trained catalog contracts."""
from dataclasses import replace
from unittest.mock import patch


def bind_trained_catalog(api,stack):
    owner=api._default_application.training_pipeline._model_catalog
    lookup,links,catalog=owner.lookup,owner.links,owner.catalog
    stack.enter_context(patch.object(lookup,'repository',lambda:api.runtime_postgres_repository_or_none()))
    stack.enter_context(patch.object(lookup,'file_loader',lambda:api.load_training_task))
    stack.enter_context(patch.object(lookup,'cache',replace(lookup.cache,get=lambda key:api.store_read_cache_get(key),put=lambda key,value:api.store_read_cache_put(key,value))))
    stack.enter_context(patch.object(lookup,'rows',replace(lookup.rows,decode=lambda rows:api.row_raw_json_list(rows),identifier=lambda path:api.file_stem_identifier(path),matches=lambda task,requested,row:api.training_task_matches_identifier(task,requested,row))))
    stack.enter_context(patch.object(links,'tasks',lambda:api.load_pipeline_tasks()))
    stack.enter_context(patch.object(links,'name',lambda task:api.task_record_name(task)))
    stack.enter_context(patch.object(catalog,'config',lambda:api.load_config()))
    stack.enter_context(patch.object(catalog,'files',replace(catalog.files,roots=lambda:api.training_run_roots(),task_path=lambda:api.training_task_path,read=lambda path:api.load_json_file_mtime_cached(path),output=lambda:api.OUTPUT_DIR,resolve=lambda:api.resolve_service_path)))
    stack.enter_context(patch.object(catalog,'accessories',replace(catalog.accessories,uid=lambda item:api.accessory_uid(item),serialize=lambda item:api.serialize_accessory(item),uses_ocr=lambda:api.accessory_uses_ocr,profiles=lambda:api.build_ocr_accessory_profiles)))
    stack.enter_context(patch.object(catalog,'pipeline',replace(catalog.pipeline,tasks=lambda:api.load_pipeline_tasks(),method=lambda:api.normalize_pipeline_detection_method)))
    stack.enter_context(patch.object(catalog,'access',replace(catalog.access,current_user=lambda:api._request_user.get(),visible=lambda record,user:api.record_visible_to_user(record,user),audit=lambda:api.record_audit_fields)))
    stack.enter_context(patch.object(catalog,'rules',lambda spec,config:api.apply_task_rule_override_to_spec(spec,config)))


def assert_default_trained_catalog(api):
    import unittest
    from canonical_application_source_contract import verify_actual_sources
    from auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.training.catalog_composition import ModelCatalog
    from local_inspection_service.training.model_catalog import TrainedModelCatalog
    from local_inspection_service.training.task_lookup import TrainingTaskLookup
    from local_inspection_service.pipeline.training_links import TrainingLinks
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;g=app.training_pipeline;owner=g._model_catalog;lookup,links,catalog=owner.lookup,owner.links,owner.catalog
    for obj,kind in ((owner,ModelCatalog),(lookup,TrainingTaskLookup),(links,TrainingLinks),(catalog,TrainedModelCatalog)):case.assertIs(type(obj),kind)
    case.assertIs(api._model_catalog,owner);case.assertIs(g._trained_model_catalog,catalog);case.assertIs(catalog.business_files,app.artifacts.files)
    a,b,c=object(),object(),object()
    calls=((lookup.repository,app.infrastructure._runtime_repository_access,'runtime_postgres_repository_or_none',(),{},{}),(lookup.file_loader(),g._training_state_workflows,'load_training_task',(a,),{},{}),(catalog.config,app.infrastructure._app_configuration,'load_config',(),{},{}),(links.tasks,g._pipeline_task_store,'load_pipeline_tasks',(),{},{}),(links.name,app.infrastructure._resource_names,'task_record_name',(a,),{},{}),(catalog.files.roots,g._dataset_catalog,'training_run_roots',(),{},{}),(catalog.files.finder,lookup,'training_task_finder',(),{},{}),(catalog.files.task_path(),g._training_state_workflows,'training_task_path',(a,),{},{}),(catalog.files.resolve(),app.infrastructure._service_paths,'resolve_service_path',(a,),{},{'for_write':False}),(catalog.accessories.serialize,app.inspection._accessory_projection,'serialize_accessory',(a,),{},{}),(catalog.pipeline.tasks,g._pipeline_task_store,'load_pipeline_tasks',(),{},{}),(lambda *args:catalog.pipeline.link()(*args),links,'pipeline_task_link_for_training_run',(a,b),{},{}),(catalog.pipeline.method(),g._pipeline_task_metadata,'normalize_pipeline_detection_method',(a,),{},{}),(catalog.rules,app.http._detection_rule_requests,'apply_task_rule_override_to_spec',(a,b),{},{}))
    for selected,receiver,name,args,kwargs,expected in calls:assert_native_relay(case,selected,(receiver,name,args,kwargs,args,expected))
    for alias,expected in (('_training_task_lookup',lookup),('_training_links',links),('_trained_model_catalog',catalog)):case.assertIs(getattr(api,alias),expected)
    original=app.values.OUTPUT_DIR;case.assertIs(catalog.files.output(),original)
    try:
        object.__setattr__(app.values,'OUTPUT_DIR',b);case.assertIs(catalog.files.output(),b)
    finally:object.__setattr__(app.values,'OUTPUT_DIR',original)
    case.assertIs(catalog.files.output(),original)
    from scripts.training_records_application_test_ports import _frozen_slot
    from unittest.mock import Mock
    for selected,name,args in ((lookup.cache.get,'store_read_cache_get',(a,)),(lookup.cache.put,'store_read_cache_put',(a,b)),(catalog.files.read,'load_json_file_mtime_cached',(a,)),(lambda *args:catalog.access.audit()(*args),'record_audit_fields',(a,b)),(catalog.access.visible,'record_visible_to_user',(a,b))):
        spy=Mock(return_value=c)
        with _frozen_slot(app.infrastructure,name,spy):
            case.assertIs(selected(*args),c);spy.assert_called_once_with(*args)
            for actual,expected in zip(spy.call_args.args,args):case.assertIs(actual,expected)
    spy=Mock(return_value=c)
    with _frozen_slot(app.inspection,'build_ocr_accessory_profiles',spy):case.assertIs(catalog.accessories.profiles()(a,b),c);spy.assert_called_once_with(a,b)
    from local_inspection_service.accessories import policy
    for selected,module,name,args in ((lookup.rows.decode,wiring,'row_raw_json_list',(a,)),(lookup.rows.identifier,wiring,'file_stem_identifier',(a,)),(lookup.rows.matches,wiring,'training_task_matches_identifier',(a,b,c)),(catalog.accessories.uid,policy,'accessory_uid',(a,)),(catalog.accessories.uses_ocr(),policy,'accessory_uses_ocr',(a,))):
        with patch.object(module,name,return_value=c) as spy:
            case.assertIs(selected(*args),c);spy.assert_called_once_with(*args)
            for actual,expected in zip(spy.call_args.args,args):case.assertIs(actual,expected)
    context=api._request_user;token=context.set(a)
    try:case.assertIs(catalog.access.current_user(),a)
    finally:context.reset(token)

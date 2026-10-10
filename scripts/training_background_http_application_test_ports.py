"""Finite background HTTP access, upload and capture fixtures."""
from dataclasses import replace
from unittest.mock import patch,Mock

UPLOAD=(('records',{'unique':'unique_background_set_id','enqueue':'enqueue_background_set_task','payload':'background_set_payload'}),)
CAPTURE=(('identity',{'sanitize':'sanitize_ai_detection_task_id','current':'current_auth_user','public':'public_path_sanitized'}),('paths',{'url':'public_output_url'}),('tasks',{'load':'load_ai_detection_tasks','access':'require_record_access','save':'save_ai_detection_task'}),('background',{'validate':'validate_task_environment_background_image'}),('state',{'load':'load_auto_optimize_state','save':'save_auto_optimize_state','public':'public_auto_optimize_state'}))


def bind_training_background_http(api,stack):
    graph=api._default_application.training_pipeline;query=graph._background_query;upload=graph._background_upload;capture=graph._background_capture;validation=graph._background_validation
    for field,name in (('current','current_auth_user'),('admin','user_is_admin'),('safe','safe_background_set_id'),('list','list_background_sets'),('load','load_background_sets_manifest')):stack.enter_context(patch.object(query,field,lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)))
    for field,name in (('selected','selected_background_set_id'),('sets','BACKGROUND_SETS_DIR'),('suffixes','IMAGE_REFERENCE_SUFFIXES')):stack.enter_context(patch.object(query,field,lambda _name=name:getattr(api,_name)))
    stack.enter_context(patch.object(upload,'paths',replace(upload.paths,sets=lambda:api.BACKGROUND_SETS_DIR,suffixes=lambda:api.IMAGE_REFERENCE_SUFFIXES)))
    for owner,groups in ((upload,UPLOAD),(capture,CAPTURE)):
        for attribute,mapping in groups:stack.enter_context(patch.object(owner,attribute,replace(getattr(owner,attribute),**{field:(lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)) for field,name in mapping.items()})))
    stack.enter_context(patch.object(upload,'records',replace(upload.records,update_provider=lambda:api.update_background_set_manifest)));stack.enter_context(patch.object(upload,'owner',lambda:api.current_owner_fields()));stack.enter_context(patch.object(upload,'catalog',lambda:api.training_background_sets()))
    stack.enter_context(patch.object(capture,'paths',replace(capture.paths,suffixes=lambda:api.IMAGE_REFERENCE_SUFFIXES,output=lambda:api.output_write_dir_for_owner)));stack.enter_context(patch.object(capture,'background',replace(capture.background,save=lambda:api.save_task_environment_background_set)));stack.enter_context(patch.object(capture,'state',replace(capture.state,lock=lambda:api._auto_optimize_lock)))
    for owner in (upload,capture,validation):stack.enter_context(patch.object(owner,'clock',lambda:api.time.time()))
    for owner in (capture,validation):stack.enter_context(patch.object(owner,'uuid',lambda:api.uuid.uuid4()))
    stack.enter_context(patch.object(validation,'sanitize',lambda value:api.sanitize_ai_detection_task_id(value)));stack.enter_context(patch.object(validation,'prefix',lambda:api.AI_DETECTION_TASK_PREFIX));stack.enter_context(patch.object(validation,'analyze',lambda *args,**kw:api.analyze_bgr(*args,**kw)));stack.enter_context(patch.object(validation,'text',lambda:api.bounded_text))


def assert_default_training_background_http(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.training_records_application_test_ports import _frozen_slot
    from local_inspection_service.training.background_query import BackgroundQuery
    from local_inspection_service.training.background_uploads import BackgroundUpload,BackgroundCapture
    from local_inspection_service.training.background_validation import BackgroundValidation
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;infra=app.infrastructure;query=graph._background_query;upload=graph._background_upload;capture=graph._background_capture;validation=graph._background_validation;item,other,third=object(),object(),object()
    for name,kind in (('_background_query',BackgroundQuery),('_background_upload',BackgroundUpload),('_background_capture',BackgroundCapture),('_background_validation',BackgroundValidation)):case.assertIs(type(getattr(graph,name)),kind);case.assertIs(getattr(api,name),getattr(graph,name))
    case.assertIs(query.files(),app.artifacts.files);case.assertIs(upload.files,app.artifacts.files);case.assertIs(capture.files,app.artifacts.files);case.assertIs(validation.images,infra._background_image_io);case.assertIs(validation.images.files,app.artifacts.files)
    case.assertIs(capture.state.lock(),graph._auto_optimization_runtime.lock)
    for selected,name in ((query.sets,'BACKGROUND_SETS_DIR'),(query.suffixes,'IMAGE_REFERENCE_SUFFIXES'),(upload.paths.sets,'BACKGROUND_SETS_DIR'),(upload.paths.suffixes,'IMAGE_REFERENCE_SUFFIXES'),(capture.paths.suffixes,'IMAGE_REFERENCE_SUFFIXES'),(validation.prefix,'AI_DETECTION_TASK_PREFIX')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)
    for selected,name,args,kw in ((query.current,'current_auth_user',(),{}),(capture.identity.current,'current_auth_user',(),{}),(upload.owner,'current_owner_fields',(),{}),(capture.tasks.access,'require_record_access',(item,other),{'write':True})):
        receiver=Mock(return_value=other)
        with _frozen_slot(infra,name,receiver):case.assertIs(selected(*args,**kw),other);receiver.assert_called_once_with(*args,**kw)
    upload_fields={name:object() for name in ('id', 'name', 'description', 'source', 'created_at', 'generation_method', 'status', 'owner_user_id', 'owner_username', 'shared_with_user_ids')}
    for selected,target,method,args,kw,expected,expected_kw in (
        (query.list,graph._background_catalog,'list_background_sets',(item,),{},(item,None),{}),
        (query.list,graph._background_catalog,'list_background_sets',(item,other),{},(item,other),{}),
        (query.load,graph._background_manifest,'load_background_sets_manifest',(),{},(),{}),
        (query.selected(),graph._background_selection,'selected_background_set_id',(item,other,third),{},(item,other,third),{}),
        (upload.records.unique,graph._background_writes,'unique_background_set_id',(item,),{},(item,),{}),
        (upload.records.update_provider(),graph._background_writes,'update_background_set_manifest',(item,),upload_fields,(item,),upload_fields),
        (upload.records.enqueue,graph._background_task_submission,'enqueue_background_set_task',(item,other,third),{},(item,other,third),{}),
        (upload.records.payload,graph._background_catalog,'background_set_payload',(item,other),{},(item,other),{}),
        (capture.identity.public,infra._service_paths,'public_path_sanitized',(item,),{},(item,),{}),
        (capture.paths.output(),infra._service_paths,'output_write_dir_for_owner',(item,other),{},(item,other),{}),
        (capture.paths.url,infra._service_paths,'public_output_url',(item,),{},(item,),{}),
        (capture.tasks.load,app.inspection._detection_task_store,'load_ai_detection_tasks',(),{},(),{}),
        (capture.tasks.save,app.inspection._detection_task_store,'save_ai_detection_task',(item,),{},(item,),{'prepend':False}),
        (capture.background.validate,validation,'validate_task_environment_background_image',(item,other,third),{},(item,other,third),{}),
        (capture.background.save(),graph._task_background_store,'save_task_environment_background_set',(item,other,third),{},(item,other,third,''),{}),
        (capture.background.save(),graph._task_background_store,'save_task_environment_background_set',(item,other,third),{'display_name':item},(item,other,third,item),{}),
        (capture.state.load,graph._auto_optimization_state_store,'load_auto_optimize_state',(item,),{},(item,),{}),
        (capture.state.save,graph._auto_optimization_state_store,'save_auto_optimize_state',(item,),{},(item,),{}),
        (capture.state.public,graph._auto_optimization_status,'public_auto_optimize_state',(item,),{'user':other},(item,),{'user':other}),
        (validation.analyze,app.inspection._detection_analysis,'analyze_bgr',(item,other,third),{'image_path':item},(item,other,third),{'image_path':item})):
        assert_native_relay(case,selected,(target,method,args,kw,expected,expected_kw))
    case.assertIs(validation.text(),wiring.bounded_text)
    for selected,name in ((query.admin,'user_is_admin'),(query.safe,'safe_background_set_id'),(capture.identity.sanitize,'sanitize_ai_detection_task_id'),(validation.sanitize,'sanitize_ai_detection_task_id')):
        with patch.object(wiring,name,return_value=other) as receiver:case.assertIs(selected(item),other);receiver.assert_called_once_with(item)
    for selected,target,name in ((upload.clock,wiring.time,'time'),(capture.clock,wiring.time,'time'),(validation.clock,wiring.time,'time'),(capture.uuid,wiring.uuid,'uuid4'),(validation.uuid,wiring.uuid,'uuid4')):
        with patch.object(target,name,return_value=other) as receiver:case.assertIs(selected(),other);receiver.assert_called_once_with()

    from scripts.training_resource_application_test_ports import read_cell
    case.assertIs(read_cell(app.http.training_background_sets,'query').cell_contents,query)
    assert_native_relay(case,upload.catalog,(query,'training_background_sets',(),{},(None,),{}))

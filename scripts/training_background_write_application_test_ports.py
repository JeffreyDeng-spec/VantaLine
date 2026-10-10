"""Finite background allocation and task environment publication fixtures."""
from dataclasses import replace
from unittest.mock import patch


def bind_training_background_write(api,stack):
    graph=api._default_application.training_pipeline;minimum=graph._background_minimum_images;writes=graph._background_writes;task=graph._task_background_store
    for owner,field,name in ((minimum,'safe','safe_background_set_id'),(minimum,'images','image_file_list'),(writes,'safe','safe_background_set_id'),(writes,'load','load_background_sets_manifest'),(writes,'write','write_background_sets_manifest'),(task,'create','create_background_variants_from_source'),(task,'images','image_file_list')):stack.enter_context(patch.object(owner,field,lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)))
    for owner,field,name in ((minimum,'sets','BACKGROUND_SETS_DIR'),(minimum,'create','create_background_variants_from_source'),(writes,'sets','BACKGROUND_SETS_DIR')):stack.enter_context(patch.object(owner,field,lambda _name=name:getattr(api,_name)))
    stack.enter_context(patch.object(task,'identity',replace(task.identity,sanitize=lambda value:api.sanitize_ai_detection_task_id(value),fallback=lambda value:api.safe_record_id(value),safe=lambda:api.safe_background_set_id,legacy_owner=lambda:api.LEGACY_OWNER_ID)))
    stack.enter_context(patch.object(task,'paths',replace(task.paths,sets=lambda:api.BACKGROUND_SETS_DIR,suffixes=lambda:api.IMAGE_REFERENCE_SUFFIXES)))
    stack.enter_context(patch.object(task,'records',replace(task.records,update_provider=lambda:api.update_background_set_manifest,payload=lambda *args:api.background_set_payload(*args))))


def assert_default_training_background_write(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.training.background_variants import BackgroundVariants,BackgroundMinimumImages
    from local_inspection_service.training.background_writes import BackgroundWrites
    from local_inspection_service.training.task_background_store import TaskBackgroundStore
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;minimum=graph._background_minimum_images;writes=graph._background_writes;task=graph._task_background_store;variant=graph._background_variants;item,other,third=object(),object(),object()
    for name,kind in (('_background_minimum_images',BackgroundMinimumImages),('_background_writes',BackgroundWrites),('_task_background_store',TaskBackgroundStore),('_background_variants',BackgroundVariants)):case.assertIs(type(getattr(graph,name)),kind);case.assertIs(getattr(api,name),getattr(graph,name))
    for owner in (writes,task):case.assertIs(owner.files,app.artifacts.files)
    case.assertIs(variant.images,app.infrastructure._background_image_io);case.assertIs(variant.images.files,app.artifacts.files);case.assertIs(variant.images.files.runtime_provider,app.artifacts.files.runtime_provider)
    for selected,name in ((minimum.sets,'BACKGROUND_SETS_DIR'),(writes.sets,'BACKGROUND_SETS_DIR'),(task.paths.sets,'BACKGROUND_SETS_DIR'),(task.paths.suffixes,'IMAGE_REFERENCE_SUFFIXES'),(task.identity.legacy_owner,'LEGACY_OWNER_ID')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)
    for selected,target,method,args,kw,expected in ((minimum.images,graph._background_image_files,'image_file_list',(item,),{},(item,)),(minimum.create(),variant,'create_background_variants_from_source',(item,other,third),{},(item,other,third)),(writes.load,graph._background_manifest,'load_background_sets_manifest',(),{},()),(writes.write,graph._background_manifest,'write_background_sets_manifest',(item,),{},(item,)),(task.identity.fallback,app.inspection._pose_collection_jobs,'safe_record_id',(item,),{},(item,)),(task.records.update_provider(),writes,'update_background_set_manifest',(item,),{'status':other},(item,)),(task.records.payload,graph._background_catalog,'background_set_payload',(item,other),{},(item,other)),(task.create,variant,'create_background_variants_from_source',(item,other),{'count':third},(item,other,third)),(task.images,graph._background_image_files,'image_file_list',(item,),{},(item,))):
        expected_kw=kw if method=='update_background_set_manifest' else {}
        assert_native_relay(case,selected,(target,method,args,kw,expected,expected_kw))
    case.assertIs(task.identity.safe(),wiring.safe_background_set_id)
    for selected,name in ((minimum.safe,'safe_background_set_id'),(writes.safe,'safe_background_set_id'),(task.identity.sanitize,'sanitize_ai_detection_task_id')):
        with patch.object(wiring,name,return_value=other) as receiver:case.assertIs(selected(item),other);receiver.assert_called_once_with(item)
    for selected in (variant.clock,writes.clock,task.clock):
        with patch.object(wiring.time,'time',return_value=other) as receiver:case.assertIs(selected(),other);receiver.assert_called_once_with()
    with patch.object(wiring.uuid,'uuid4',return_value=other) as receiver:case.assertIs(writes.uuid(),other);receiver.assert_called_once_with()

    updates={name:object() for name in ('id','name','description','source','created_at','updated_at','status','image_count','generation_method','owner_user_id','owner_username','shared_with_user_ids')}
    assert_native_relay(case,task.records.update_provider(),(writes,'update_background_set_manifest',(item,),updates,(item,),updates))

"""Finite preview fingerprint, approved-input and status dependencies."""
from dataclasses import replace
from unittest.mock import patch, Mock

INPUTS={'sprites':'clean_sprite_assets','uid':'accessory_uid','material':'accessory_material_type','alpha_policy':'object_alpha_material_policy'}
ACCESS={'visible':'record_visible_to_user','is_admin':'user_is_admin','owner':'record_owner_id'}


def bind_training_input(api,stack):
    graph=api._default_application.training_pipeline;cache=graph._training_preview_cache;approval=graph._training_preview_approval;dataset=graph._training_dataset_input;status=graph._training_status_projection
    stack.enter_context(patch.object(cache,'inputs',replace(cache.inputs,**{field:(lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)) for field,name in INPUTS.items()})))
    for field,name in (('schema','PREVIEW_CACHE_SCHEMA_VERSION'),('resolve','resolve_service_path')):
        stack.enter_context(patch.object(cache,field,lambda _name=name:getattr(api,_name)))
    stack.enter_context(patch.object(approval,'jobs',lambda:api.TRAINING_JOBS_DIR));stack.enter_context(patch.object(approval,'background',lambda:api.selected_background_set_id))
    stack.enter_context(patch.object(dataset,'find',lambda *args,**kw:api.find_dataset_resource(*args,**kw)))
    stack.enter_context(patch.object(dataset,'require',lambda *args,**kw:api.require_record_access(*args,**kw)))
    stack.enter_context(patch.object(dataset,'sanitize',lambda:api.public_path_sanitized))
    stack.enter_context(patch.object(status,'access',replace(status.access,**{field:(lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)) for field,name in ACCESS.items()})))
    stack.enter_context(patch.object(status,'preview',replace(status.preview,selected=lambda:api.selected_accessories)))


def assert_default_training_input(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.training_records_application_test_ports import _frozen_slot
    from local_inspection_service.training.preview_cache import TrainingPreviewCache
    from local_inspection_service.training.preview_approval import TrainingPreviewApproval
    from local_inspection_service.training.dataset_input import TrainingDatasetInput
    from local_inspection_service.training.status_projection import TrainingStatusProjection
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;infra=app.infrastructure;inspection=app.inspection;cache=graph._training_preview_cache;approval=graph._training_preview_approval;dataset=graph._training_dataset_input;status=graph._training_status_projection;item,other,third=object(),object(),object()
    for name,kind in (('_training_preview_cache',TrainingPreviewCache),('_training_preview_approval',TrainingPreviewApproval),('_training_dataset_input',TrainingDatasetInput),('_training_status_projection',TrainingStatusProjection)):
        case.assertIs(type(getattr(graph,name)),kind);case.assertIs(getattr(api,name),getattr(graph,name))
    for selected in (cache,approval,dataset):case.assertIs(selected.files,app.artifacts.files)
    case.assertIs(approval,graph._training_task_workflows.preview_approval);case.assertIs(dataset,graph._training_task_workflows.dataset_input);case.assertIs(status,graph._training_task_workflows.status_projection)
    for selected,name in ((cache.schema,'PREVIEW_CACHE_SCHEMA_VERSION'),(approval.jobs,'TRAINING_JOBS_DIR')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)
    for selected,name,args in ((dataset.require,'require_record_access',(item,other)),(status.access.visible,'record_visible_to_user',(item,other,third)),(status.access.owner,'record_owner_id',(item,))):
        receiver=Mock(return_value=other)
        with _frozen_slot(infra,name,receiver):case.assertIs(selected(*args),other);receiver.assert_called_once_with(*args)
    with patch.object(wiring,'user_is_admin',return_value=other) as receiver:case.assertIs(status.access.is_admin(item),other);receiver.assert_called_once_with(item)
    for selected,target,method,args,kw,expected,expected_kw in (
        (cache.inputs.sprites,inspection._sprite_asset_catalog,'clean_sprite_assets',(item,),{},(item,),{}),
        (cache.resolve(),infra._service_paths,'resolve_service_path',(item,),{},(item,),{'for_write':False}),
        (cache.version,cache,'accessory_sprite_version',(item,),{},(item,),{}),
        (approval.background(),graph._background_selection,'selected_background_set_id',(item,other),{},(item,other,None),{}),
        (approval.cache,cache,'preview_cache_key',(item,),{},(item,),{}),
        (dataset.find,graph._dataset_catalog,'find_dataset_resource',(item,),{'user':other},(item,other),{'include_samples':False,'write':False}),
        (dataset.sanitize(),infra._service_paths,'public_path_sanitized',(item,),{},(item,),{}),
        (status.tasks.find,graph._training_account_state.records,'find_training_task',(item,),{},(item,),{}),
        (status.tasks.refresh,graph._training_account_state.records,'public_refreshed_training_task',(item,),{},(item,),{}),
        (status.preview.selected(),inspection._accessory_selection,'selected_accessories',(item,other),{},(item,other),{}),
        (status.preview.cache,cache,'preview_cache_key',(item,),{},(item,),{}),
        (status.preview.missing,cache,'training_preview_metadata_missing',(item,other),{},(item,other),{})):
        assert_native_relay(case,selected,(target,method,args,kw,expected,expected_kw))
    for selected,name,args,expected in ((cache.inputs.uid,'accessory_uid',(item,),(item,)),(cache.inputs.material,'accessory_material_type',(item,),(item,)),(cache.inputs.alpha_policy,'object_alpha_material_policy',(item,),(item,None))):
        with patch.object(wiring._accessory_policy,name,return_value=other) as receiver:case.assertIs(selected(*args),other);receiver.assert_called_once_with(*expected)

    assert_native_relay(case,dataset.find,(graph._dataset_catalog,'find_dataset_resource',(item,),{'user':other,'include_samples':False},(item,other),{'include_samples':False,'write':False}))

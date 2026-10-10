"""Finite token, path and upload-limit fixtures on native transfer owners."""
from dataclasses import replace
from unittest.mock import patch


def bind_training_transfer(api,stack):
    graph=api._default_application.training_pipeline;owner=graph._training_transfer
    stack.enter_context(patch.object(owner,'token_hash',lambda token:api.runpod_dataset_token_hash(token)))
    stack.enter_context(patch.object(owner,'paths',replace(owner.paths,resolve=lambda:api.resolve_service_path,output=lambda:api.OUTPUT_DIR)))
    stack.enter_context(patch.object(graph._training_upload_store,'limit',lambda:api.runpod_yolo_artifact_max_bytes()))


def assert_default_training_transfer(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.training.runpod_transfer import RunPodTrainingTransfer
    from local_inspection_service.training.runpod_upload_store import RunPodUploadStore
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;task=graph._training_task_workflows;owner=graph._training_transfer;store=graph._training_upload_store;item,other=object(),object()
    case.assertIs(type(owner),RunPodTrainingTransfer);case.assertIs(type(store),RunPodUploadStore);case.assertIs(api._training_transfer,owner);case.assertIs(api._training_upload_store,store);case.assertIs(owner,task.transfer);case.assertIs(store,task.upload_store);case.assertIs(owner.uploads,store)
    case.assertIs(owner.runtime_provider,app.artifacts.files.runtime_provider);case.assertIs(store.runtime_provider,app.artifacts.files.runtime_provider)
    original=app.values.OUTPUT_DIR;case.assertIs(owner.paths.output(),original)
    try:object.__setattr__(app.values,'OUTPUT_DIR',other);case.assertIs(owner.paths.output(),other)
    finally:object.__setattr__(app.values,'OUTPUT_DIR',original)
    for selected,target,method,args,kw,expected,expected_kw in ((owner.find,task.account.records,'find_training_task',(item,),{},(item,),{}),(owner.paths.resolve(),app.infrastructure._service_paths,'resolve_service_path',(item,),{},(item,),{'for_write':False}),(owner.update_provider(),task.account.records,'update_training_task',(item,),{'status':other},(item,),{'status':other})):
        assert_native_relay(case,selected,(target,method,args,kw,expected,expected_kw))
    case.assertIs(owner.update_provider().__self__,task);case.assertIs(owner.update_provider().__func__,type(task).update_training_task)
    assert_native_relay(case,store.limit,(graph._training_executor_settings,'runpod_yolo_artifact_max_bytes',(),{},(),{}))
    for selected,name,args in ((owner.token_hash,'runpod_dataset_token_hash',(item,)),):
        with patch.object(wiring,name,return_value=other) as receiver:case.assertIs(selected(*args),other);receiver.assert_called_once_with(*args)
    with patch.object(wiring.time,'time',return_value=other) as receiver:case.assertIs(owner.clock(),other);receiver.assert_called_once_with()

    assert_native_relay(case,owner.paths.resolve(),(app.infrastructure._service_paths,'resolve_service_path',(item,),{'for_write':True},(item,),{'for_write':True}))

"""Finite synthetic archive/export/import ports; actual artifact runtime stays native."""
from dataclasses import replace
from unittest.mock import patch,Mock


def bind_training_artifacts(api,stack):
    graph=api._default_application.training_pipeline;archives=graph._training_dataset_archives;exports=graph._runpod_exports;artifacts=graph._runpod_artifacts
    for field,name in (('safe_name','safe_name'),('digest','file_sha256')):stack.enter_context(patch.object(archives,field,lambda *args,_name=name:getattr(api,_name)(*args)))
    for field,name in (('skip_dirs','WORKER_BUNDLE_SKIP_DIRS'),('jpeg_quality','WORKER_BUNDLE_JPEG_QUALITY')):stack.enter_context(patch.object(archives,field,lambda _name=name:getattr(api,_name)))
    stack.enter_context(patch.object(exports,'paths',replace(exports.paths,resolve=lambda:api.resolve_service_path,output=lambda kind,owner:api.output_write_dir_for_owner(kind,owner),safe_name=lambda value:api.safe_name(value))))
    stack.enter_context(patch.object(exports,'policy',replace(exports.policy,token_hash=lambda value:api.runpod_dataset_token_hash(value),ttl=lambda:api.runpod_yolo_dataset_token_ttl_seconds(),public_base=lambda:api.runpod_yolo_public_base_url())))
    for field,name in (('bundle','build_worker_training_bundle'),('digest','file_sha256')):stack.enter_context(patch.object(exports,field,lambda *args,_name=name:getattr(api,_name)(*args)))
    stack.enter_context(patch.object(exports,'update_provider',lambda:api.update_training_task))
    stack.enter_context(patch.object(artifacts,'paths',replace(artifacts.paths,resolve=lambda value:api.resolve_service_path(value),output_root=lambda:api.OUTPUT_DIR,output=lambda:api.output_write_dir_for_owner)))
    stack.enter_context(patch.object(artifacts,'find',lambda value:api.find_training_task(value)));stack.enter_context(patch.object(artifacts,'summary',lambda value:api.runpod_public_response_summary(value)))


def assert_default_training_artifacts(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.training.dataset_archives import DatasetArchives
    from local_inspection_service.training.runpod_exports import RunPodExports
    from local_inspection_service.training.runpod_artifacts import RunPodArtifacts
    from local_inspection_service.runtime.wiring import training_pipeline
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;infra=app.infrastructure;archives=graph._training_dataset_archives;exports=graph._runpod_exports;artifacts=graph._runpod_artifacts;item,other=object(),object()
    for name,kind in (('_training_dataset_archives',DatasetArchives),('_runpod_exports',RunPodExports),('_runpod_artifacts',RunPodArtifacts)):
        case.assertIs(type(getattr(graph,name)),kind);case.assertIs(getattr(api,name),getattr(graph,name))
    case.assertIs(exports.runtime_provider,app.artifacts.files.runtime_provider);case.assertIs(artifacts.runtime_provider,app.artifacts.files.runtime_provider)
    with patch.object(app.artifacts.files,'runtime_provider',return_value=other) as receiver:case.assertIs(archives.runtime_provider(),other);receiver.assert_called_once_with()
    for selected,name in ((archives.skip_dirs,'WORKER_BUNDLE_SKIP_DIRS'),(archives.jpeg_quality,'WORKER_BUNDLE_JPEG_QUALITY'),(artifacts.paths.output_root,'OUTPUT_DIR')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)
    for selected,target,method,args,kw,expected_kw in ((exports.paths.resolve(),infra._service_paths,'resolve_service_path',(item,),{}, {'for_write':False}),(exports.paths.output,infra._service_paths,'output_write_dir_for_owner',(item,other),{},{}),(exports.policy.ttl,graph._training_executor_settings,'runpod_yolo_dataset_token_ttl_seconds',(),{},{}),(exports.policy.public_base,graph._training_executor_settings,'runpod_yolo_public_base_url',(),{},{}),(exports.bundle,archives,'build_worker_training_bundle',(item,other),{},{}),(exports.update_provider(),graph._training_state_workflows,'update_training_task',(item,),{'status':other},{'status':other}),(artifacts.paths.resolve,infra._service_paths,'resolve_service_path',(item,),{}, {'for_write':False}),(artifacts.paths.output(),infra._service_paths,'output_write_dir_for_owner',(item,other),{},{}),(artifacts.find,graph._training_state_workflows,'find_training_task',(item,),{},{}),(artifacts.summary,graph._runpod_client,'runpod_public_response_summary',(item,),{},{})):
        assert_native_relay(case,selected,(target,method,args,kw,args,expected_kw))
    for selected in (archives.digest,exports.digest):
        with patch.object(training_pipeline,'strict_training_file_sha256',return_value=other) as receiver:case.assertIs(selected(item),other);receiver.assert_called_once_with(item,files=app.artifacts.files)
    for selected in (archives.safe_name,exports.paths.safe_name):
        with patch.object(training_pipeline,'safe_name',return_value=other) as receiver:case.assertIs(selected(item),other);receiver.assert_called_once_with(item)
    with patch.object(training_pipeline,'runpod_dataset_token_hash',return_value=other) as receiver:case.assertIs(exports.policy.token_hash(item),other);receiver.assert_called_once_with(item)

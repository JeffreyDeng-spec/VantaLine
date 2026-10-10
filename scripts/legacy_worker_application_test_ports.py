"""Finite restored ports for historical worker transport contracts."""
from dataclasses import replace
from unittest.mock import patch


def bind_remote_training(api,stack):
    graph=api._default_application.training_pipeline;remote=graph._remote_training
    stack.enter_context(patch.object(remote,'settings',replace(remote.settings,endpoint=lambda:api.remote_training_endpoint(),mask=lambda value:api.masked_url_for_status(value),environment=lambda:api.os.environ,timeout=lambda:api.remote_training_timeout_seconds())))
    stack.enter_context(patch.object(remote,'paths',replace(remote.paths,resolve=lambda:api.resolve_service_path,package=lambda *args:api.package_training_dataset(*args))))
    stack.enter_context(patch.object(remote,'update_provider',lambda:api.update_training_task));stack.enter_context(patch.object(remote,'post',lambda:api.requests.post));stack.enter_context(patch.object(remote,'clock',lambda:api.time.time()))
    stack.enter_context(patch.object(graph._worker_artifact_summary,'sanitize',lambda value:api.public_path_sanitized(value)))


def bind_worker_transfers(api,stack):
    graph=api._default_application.training_pipeline;transfers=graph._worker_transfers;progress=graph._transfer_progress
    for field,name in (('base_url','windows_worker_base_url'),('headers','windows_worker_headers')):stack.enter_context(patch.object(transfers,field,lambda _name=name:getattr(api,_name)()))
    stack.enter_context(patch.object(transfers,'post',lambda *args,**kw:api.requests.post(*args,**kw)));stack.enter_context(patch.object(transfers,'get_provider',lambda:api.requests.get));stack.enter_context(patch.object(transfers,'uuid_factory',lambda:api.uuid.uuid4()))
    stack.enter_context(patch.object(progress,'update_provider',lambda:api.update_training_task));stack.enter_context(patch.object(progress,'event_factory',lambda:api.threading.Event()));stack.enter_context(patch.object(progress,'thread_provider',lambda:api.threading.Thread))


def bind_worker_bundle(api,stack):
    graph=api._default_application.training_pipeline;metadata=graph._worker_bundle_metadata;submission=graph._worker_bundle_submission
    stack.enter_context(patch.object(metadata,'digest',lambda path:api.file_sha256(path)));stack.enter_context(patch.object(metadata,'manifest',lambda path:api.dataset_file_manifest(path)))
    stack.enter_context(patch.object(graph._worker_bundle_timeout,'remote_timeout',lambda:api.remote_training_timeout_seconds()))
    stack.enter_context(patch.object(submission,'files',replace(submission.files,resolve=lambda:api.resolve_service_path,build=lambda *args:api.build_worker_training_bundle(*args),metadata=lambda *args:api.worker_training_bundle_metadata(*args))))
    stack.enter_context(patch.object(submission,'transport',replace(submission.transport,timeout=lambda:api.worker_training_upload_timeout_seconds(),progress=lambda *args,**kw:api._start_transfer_progress_thread(*args,**kw),stream=lambda *args,**kw:api.windows_worker_upload_bundle_streamed(*args,**kw),form=lambda:api.windows_worker_form_request)))
    stack.enter_context(patch.object(submission,'update_provider',lambda:api.update_training_task));stack.enter_context(patch.object(submission,'clock',lambda:api.time.time()));stack.enter_context(patch.object(submission,'sleep',lambda seconds:api.time.sleep(seconds)))


def bind_worker_artifacts(api,stack):
    graph=api._default_application.training_pipeline;importer=graph._worker_artifact_import
    stack.enter_context(patch.object(importer,'owner_output',lambda:api.output_write_dir_for_owner));stack.enter_context(patch.object(importer,'safe_name',lambda:api.safe_name));stack.enter_context(patch.object(importer,'clock',lambda:api.time.time()))
    stack.enter_context(patch.object(graph._worker_artifact_summary,'sanitize',lambda value:api.public_path_sanitized(value)))


def bind_worker_watcher(api,stack):
    graph=api._default_application.training_pipeline;settings=graph._worker_watcher_settings;loop=graph._worker_watcher_loop
    stack.enter_context(patch.object(settings,'environment',lambda:api.os.environ));stack.enter_context(patch.object(loop,'interval',lambda:api.worker_training_watcher_interval_seconds()));stack.enter_context(patch.object(loop,'watch',lambda:api._worker_training_watch_once()));stack.enter_context(patch.object(loop,'report_error',lambda:api.traceback.print_exc(file=api.sys.stderr)));stack.enter_context(patch.object(loop,'sleep',lambda seconds:api.time.sleep(seconds)))


def bind_retired_worker_flows(api,stack):
    graph=api._default_application.training_pipeline;owner=graph._legacy_worker_refresh;tasks=graph._legacy_worker_tasks
    stack.enter_context(patch.object(tasks,'update_provider',lambda:api.update_training_task));stack.enter_context(patch.object(tasks,'clock',lambda:api.time.time()))
    stack.enter_context(patch.object(owner,'records',replace(owner.records,public=lambda task:api.public_training_task(task))))


def assert_default_legacy_worker(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.training_resource_application_test_ports import read_cell
    from local_inspection_service.training.remote_training import RemoteTraining
    from local_inspection_service.training.worker_transfers import WorkerTransfers
    from local_inspection_service.training.transfer_progress import TransferProgress
    from local_inspection_service.training.worker_bundle_metadata import WorkerBundleMetadata
    from local_inspection_service.training.worker_bundle_submission import WorkerBundleSubmission,WorkerBundleTimeout
    from local_inspection_service.training.worker_artifacts import WorkerArtifactImport
    from local_inspection_service.training.worker_compatibility import WorkerArtifactSummary
    from local_inspection_service.training.worker_watcher import WorkerWatcherSettings,WorkerWatcherLoop
    from local_inspection_service.training.legacy_worker_tasks import LegacyWorkerTasks
    from local_inspection_service.training.legacy_worker_refresh import LegacyWorkerRefresh
    from local_inspection_service.training.legacy_worker_requests import LegacyWorkerRequests
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;remote=graph._remote_training;bundle=graph._worker_bundle_submission;transfers=graph._worker_transfers;progress=graph._transfer_progress;metadata=graph._worker_bundle_metadata;importer=graph._worker_artifact_import;watch=graph._worker_watcher_loop;item,other,third,fourth,fifth=object(),object(),object(),object(),object()
    for name,kind in (('_remote_training',RemoteTraining),('_worker_transfers',WorkerTransfers),('_transfer_progress',TransferProgress),('_worker_bundle_metadata',WorkerBundleMetadata),('_worker_bundle_submission',WorkerBundleSubmission),('_worker_bundle_timeout',WorkerBundleTimeout),('_worker_artifact_import',WorkerArtifactImport),('_worker_artifact_summary',WorkerArtifactSummary),('_worker_watcher_settings',WorkerWatcherSettings),('_worker_watcher_loop',WorkerWatcherLoop),('_legacy_worker_tasks',LegacyWorkerTasks),('_legacy_worker_refresh',LegacyWorkerRefresh),('_legacy_worker_requests',LegacyWorkerRequests)):
        case.assertIs(type(getattr(graph,name)),kind);case.assertIs(getattr(api,name),getattr(graph,name))
    environment=graph._training_executor_settings.environment();case.assertIs(remote.settings.environment(),environment);case.assertIs(graph._worker_watcher_settings.environment(),environment)
    case.assertIs(progress.runtime.scope.__self__,app.infrastructure._runtime_repositories);case.assertIs(progress.runtime.scope.__func__,type(app.infrastructure._runtime_repositories).thread_scope)
    common=('status','progress','completed_at','note')
    shapes=((remote,common+('remote_training_response','training_executor','remote_training_endpoint','dataset_dir','dataset_yaml','manifest_path','remote_training_status','remote_training_job_id')),
            (bundle,common+('worker_bundle_size_mb','worker_upload_status','worker_upload_started_at','worker_upload_total_bytes','worker_upload_sent_bytes','worker_upload_completed_at')),
            (progress,('worker_upload_sent_bytes','worker_upload_total_bytes','worker_upload_status','worker_download_received_bytes','worker_download_total_bytes','worker_download_status')),
            (graph._legacy_worker_tasks,common+('training_executor','error')))
    for owner,fields in shapes:
        updates={field:object() for field in fields}
        assert_native_relay(case,owner.update_provider(),(graph._training_state_workflows,'update_training_task',(item,),updates,(item,),updates))
    calls=((remote.settings.endpoint,graph._training_executor_settings,'remote_training_endpoint',(),{},{}),(remote.settings.timeout,graph._training_executor_settings,'remote_training_timeout_seconds',(),{},{}),(remote.settings.mask,app.infrastructure._provider_configuration,'masked_url_for_status',(item,),{},{}),(remote.paths.resolve(),app.infrastructure._service_paths,'resolve_service_path',(item,),{}, {'for_write':False}),(remote.paths.package,graph._training_dataset_archives,'package_training_dataset',(item,other),{},{}),(transfers.base_url,graph._training_executor_settings,'windows_worker_base_url',(),{},{}),(transfers.headers,graph._training_executor_settings,'windows_worker_headers',(),{},{}),(metadata.manifest,graph._training_dataset_archives,'dataset_file_manifest',(item,),{},{}),(graph._worker_bundle_timeout.remote_timeout,graph._training_executor_settings,'remote_training_timeout_seconds',(),{},{}),(bundle.files.resolve(),app.infrastructure._service_paths,'resolve_service_path',(item,),{}, {'for_write':False}),(bundle.files.build,graph._training_dataset_archives,'build_worker_training_bundle',(item,other),{},{}),(bundle.files.metadata,metadata,'worker_training_bundle_metadata',(item,other,third,fourth,fifth),{},{}),(bundle.transport.timeout,graph._worker_bundle_timeout,'worker_training_upload_timeout_seconds',(),{},{}),(bundle.transport.progress,progress,'_start_transfer_progress_thread',(item,other),{'done_field':third,'total_field':fourth,'status_field':fifth},{'done_field':third,'total_field':fourth,'status_field':fifth,'interval':1.5}),(bundle.transport.stream,transfers,'windows_worker_upload_bundle_streamed',(item,),{'metadata_json':other,'archive_path':third,'state':fourth,'timeout_seconds':fifth},{'metadata_json':other,'archive_path':third,'state':fourth,'timeout_seconds':fifth}),(bundle.transport.form(),graph._legacy_worker_requests,'windows_worker_form_request',(item,other),{'data':third,'files':fourth,'timeout_seconds':fifth},{'data':third,'files':fourth,'timeout_seconds':fifth}),(importer.owner_output(),app.infrastructure._service_paths,'output_write_dir_for_owner',(item,other),{},{}),(graph._worker_artifact_summary.sanitize,app.infrastructure._service_paths,'public_path_sanitized',(item,),{},{}),(graph._legacy_worker_refresh.records.public,graph._training_state_workflows,'public_training_task',(item,),{},{}),(watch.interval,graph._worker_watcher_settings,'worker_training_watcher_interval_seconds',(),{},{}))
    for callback,receiver,name,args,kw,expected_kw in calls:assert_native_relay(case,callback,(receiver,name,args,kw,args,expected_kw))
    with patch.object(wiring,'strict_training_file_sha256',return_value=other) as receiver:case.assertIs(metadata.digest(item),other);receiver.assert_called_once_with(item,files=app.artifacts.files)
    case.assertIs(importer.safe_name(),wiring.safe_name);case.assertIs(transfers.get_provider(),wiring.requests.get);case.assertIs(remote.post(),wiring.requests.post);case.assertIs(progress.thread_provider(),wiring.threading.Thread)
    for callback,target,name,args,kw in ((transfers.post,wiring.requests,'post',(item,),{'data':other,'headers':third,'timeout':fourth}),(transfers.uuid_factory,wiring.uuid,'uuid4',(),{}),(remote.clock,wiring.time,'time',(),{}),(bundle.clock,wiring.time,'time',(),{}),(importer.clock,wiring.time,'time',(),{}),(graph._legacy_worker_tasks.clock,wiring.time,'time',(),{}),(bundle.sleep,wiring.time,'sleep',(item,),{}),(progress.event_factory,wiring.threading,'Event',(),{}),(watch.sleep,wiring.time,'sleep',(item,),{}),(watch.watch,wiring,'_retired_worker_watch_once',(),{}),(watch.report_error,wiring.traceback,'print_exc',(),{'file':wiring.sys.stderr})):
        with patch.object(target,name,return_value=other) as receiver:case.assertIs(callback(*args,**({} if callback==watch.report_error else kw)),other);receiver.assert_called_once_with(*args,**kw)
    handlers=[hook for hook in app.app.router.on_startup if hook.__name__=='start_worker_training_watcher'];case.assertEqual(len(handlers),1);handler=handlers[0];case.assertIs(handler.__wrapped__,app.http.start_worker_training_watcher);case.assertIs(read_cell(handler,'self').cell_contents,app.lifetime);case.assertIs(read_cell(handler,'hook').cell_contents,app.http.start_worker_training_watcher)

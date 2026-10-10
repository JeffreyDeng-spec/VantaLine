"""Finite warmup test abilities; run the original native worker and lifecycle bodies."""
from dataclasses import replace
from unittest.mock import patch


def bind_yolo_warmup(api,stack):
    graph=api._default_application.inspection;candidates=graph._warmup_candidates;prediction=graph._warmup_prediction;runtime=graph._yolo_warmup_runtime
    stack.enter_context(patch.object(candidates,'pipeline',replace(candidates.pipeline,tasks=lambda:api.load_pipeline_tasks(),method=lambda:api.normalize_pipeline_detection_method,status=lambda item:api.pipeline_task_model_status(item),model_id=lambda item:api.pipeline_task_model_id(item))))
    stack.enter_context(patch.object(candidates,'models',replace(candidates.models,default_id=lambda:api.DEFAULT_MODEL_ID,trained=lambda *args:api.list_trained_model_specs(*args),resolve=lambda:api.resolve_service_path)))
    stack.enter_context(patch.object(candidates,'limit',lambda:api.yolo_warmup_limit()))
    stack.enter_context(patch.object(prediction,'select',lambda identity,config:api.selected_model_spec(identity,config)));stack.enter_context(patch.object(prediction,'load',lambda:api.model));stack.enter_context(patch.object(prediction,'device',lambda:api.yolo_inference_device()))
    stack.enter_context(patch.object(runtime,'operations',replace(runtime.operations,enabled=lambda:api.yolo_warmup_enabled(),config=lambda:api.load_config(),candidates=lambda config:api.yolo_warmup_configured_model_ids(config),warm=lambda identity,config:api.warm_yolo_model_once(identity,config),loaded_ids=lambda config:api.yolo_loaded_model_ids(config),error_text=lambda:api.bounded_text)))
    original=runtime.start_yolo_warmup
    def start(reason='startup',model_ids=None,*,worker):
        return original(reason,model_ids,worker=lambda:api.yolo_warmup_worker)
    stack.enter_context(patch.object(runtime,'start_yolo_warmup',start))


def assert_default_yolo_warmup(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.training_runner_application_test_ports import assert_default_training_warmup
    from local_inspection_service.detection.warmup_policy import WarmupCandidates
    from local_inspection_service.detection.warmup_prediction import WarmupPrediction
    from local_inspection_service.runtime.yolo_warmup import YoloWarmup
    from local_inspection_service.runtime.wiring import inspection
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.inspection;training=app.training_pipeline;candidates=graph._warmup_candidates;prediction=graph._warmup_prediction;runtime=graph._yolo_warmup_runtime;item,other=object(),object()
    for name,kind in (('_warmup_candidates',WarmupCandidates),('_warmup_prediction',WarmupPrediction),('_yolo_warmup_runtime',YoloWarmup)):
        case.assertIs(type(getattr(graph,name)),kind);case.assertIs(getattr(api,name),getattr(graph,name))
    case.assertIs(api._yolo_warmup_state,runtime.state);case.assertIs(api._yolo_warmup_lock,runtime.lock)
    case.assertIs(runtime.scope.__self__,app.infrastructure._runtime_repositories);case.assertIs(runtime.scope.__func__,type(app.infrastructure._runtime_repositories).thread_scope)
    original=app.values.DEFAULT_MODEL_ID;case.assertIs(candidates.models.default_id(),original)
    try:object.__setattr__(app.values,'DEFAULT_MODEL_ID',other);case.assertIs(candidates.models.default_id(),other)
    finally:object.__setattr__(app.values,'DEFAULT_MODEL_ID',original)
    case.assertIs(runtime.operations.error_text(),inspection.bounded_text)
    for selected,target,method,args,kw,expected,expected_kw in ((candidates.pipeline.tasks,training._pipeline_task_store,'load_pipeline_tasks',(),{},(),{}),(candidates.pipeline.method(),training._pipeline_task_metadata,'normalize_pipeline_detection_method',(item,),{},(item,),{}),(candidates.pipeline.status,training._pipeline_resource_status,'pipeline_task_model_status',(item,),{},(item,),{'ai_task_ids':None,'trained_model_specs':None}),(candidates.pipeline.model_id,training._pipeline_task_metadata,'pipeline_task_model_id',(item,),{},(item,),{}),(candidates.models.trained,training._trained_model_catalog,'list_trained_model_specs',(item,),{},(item,),{}),(candidates.models.resolve(),app.infrastructure._service_paths,'resolve_service_path',(item,),{},(item,),{'for_write':False}),(prediction.select,training._model_selection,'selected_model_spec',(item,other),{},(item,other),{}),(prediction.load(),training._local_models,'model',(item,other),{},(item,other),{}),(runtime.operations.config,app.infrastructure._app_configuration,'load_config',(),{},(),{}),(runtime.operations.candidates,candidates,'yolo_warmup_configured_model_ids',(item,),{},(item,),{}),(runtime.operations.warm,prediction,'warm_yolo_model_once',(item,other),{},(item,other),{}),(runtime.operations.loaded_ids,training._local_models,'yolo_loaded_model_ids',(item,),{},(item,),{})):
        assert_native_relay(case,selected,(target,method,args,kw,expected,expected_kw))
    for selected,name in ((candidates.limit,'yolo_warmup_limit'),(runtime.operations.enabled,'yolo_warmup_enabled'),(prediction.device,'yolo_inference_device')):
        with patch.object(inspection,name,return_value=other) as receiver:case.assertIs(selected(),other);receiver.assert_called_once_with()
    assert_default_training_warmup(api,api.start_yolo_warmup)


def native_warmup_start(api):
    owner=api._default_application.inspection._yolo_warmup_runtime
    return patch.object(owner,'start_yolo_warmup',type(owner).start_yolo_warmup.__get__(owner))

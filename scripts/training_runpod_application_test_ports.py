"""Finite native RunPod orchestration dependencies for synthetic regression data."""
from dataclasses import replace
from unittest.mock import patch

FLOW=(('settings',{'endpoint':'runpod_yolo_endpoint_id','timeout':'runpod_yolo_job_timeout_seconds','ttl':'runpod_yolo_dataset_token_ttl_seconds','poll':'runpod_yolo_poll_interval_seconds'}),('records',{'sync':'sync_training_state_from_task'}),('inputs',{'archive':'create_runpod_training_dataset_archive','payload':'runpod_training_input_payload','submit':'submit_runpod_yolo_training'}),('results',{'summary':'runpod_public_response_summary','extract':'extract_runpod_worker_output'}))
GETTERS=(('records',{'update_provider':'update_training_task','warmup':'start_yolo_warmup'}),('results',{'request':'runpod_yolo_http_request','import_artifacts':'import_runpod_yolo_artifacts','terminal':'runpod_terminal_status','bound_text':'bounded_text'}))


def bind_training_runpod(api,stack):
    graph=api._default_application.training_pipeline;flow=graph._runpod_flow
    for attribute,mapping in FLOW:
        stack.enter_context(patch.object(flow,attribute,replace(getattr(flow,attribute),**{field:(lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)) for field,name in mapping.items()})))
    for attribute,mapping in GETTERS:
        stack.enter_context(patch.object(flow,attribute,replace(getattr(flow,attribute),**{field:(lambda _name=name:getattr(api,_name)) for field,name in mapping.items()})))
    for owner,mapping in ((graph._runpod_payload,{'upload':'create_runpod_training_artifact_upload','timeout':'runpod_yolo_job_timeout_seconds','inline_limit':'runpod_yolo_inline_dataset_max_bytes'}),(graph._runpod_submission,{'timeout':'runpod_yolo_job_timeout_seconds','ttl':'runpod_yolo_dataset_token_ttl_seconds','request':'runpod_yolo_http_request'})):
        for field,name in mapping.items():stack.enter_context(patch.object(owner,field,lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)))
    stack.enter_context(patch.object(graph._runpod_payload,'environment',lambda:api.os.environ))
    stack.enter_context(patch.object(graph._runpod_output_parser,'bound_text',lambda:api.bounded_text))


def assert_default_training_runpod(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.training.runpod_flow import RunPodFlow
    from local_inspection_service.training.runpod_submission import RunPodPayload,RunPodSubmission
    from local_inspection_service.training.runpod_outputs import RunPodOutputParser,runpod_terminal_status
    from local_inspection_service.runtime.wiring import training_pipeline
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;flow=graph._runpod_flow;settings=graph._training_executor_settings;item,other,third=object(),object(),object()
    for name,kind in (('_runpod_flow',RunPodFlow),('_runpod_payload',RunPodPayload),('_runpod_submission',RunPodSubmission),('_runpod_output_parser',RunPodOutputParser)):
        case.assertIs(type(getattr(graph,name)),kind);case.assertIs(getattr(api,name),getattr(graph,name))
    from scripts.training_runner_application_test_ports import assert_default_training_warmup
    case.assertIs(flow.runtime_provider,app.artifacts.files.runtime_provider)
    assert_default_training_warmup(api,flow.records.warmup())
    case.assertIs(flow.results.terminal(),runpod_terminal_status);case.assertIs(flow.results.bound_text(),training_pipeline.bounded_text);case.assertIs(graph._runpod_output_parser.bound_text(),training_pipeline.bounded_text)
    case.assertIs(graph._runpod_payload.environment(),graph._training_executor_settings.environment())
    for selected,owner,method,args,kw in ((flow.settings.endpoint,settings,'runpod_yolo_endpoint_id',(),{}),(flow.settings.timeout,settings,'runpod_yolo_job_timeout_seconds',(),{}),(flow.settings.ttl,settings,'runpod_yolo_dataset_token_ttl_seconds',(),{}),(flow.settings.poll,settings,'runpod_yolo_poll_interval_seconds',(),{}),(flow.records.update_provider(),graph._training_state_workflows,'update_training_task',(item,),{'status':other}),(flow.records.sync,graph._training_account_state,'sync_training_state_from_task',(item,),{}),(flow.inputs.archive,graph._runpod_exports,'create_runpod_training_dataset_archive',(item,other,third),{}),(flow.inputs.payload,graph._runpod_payload,'runpod_training_input_payload',(item,other,third),{}),(flow.inputs.submit,graph._runpod_submission,'submit_runpod_yolo_training',(item,),{}),(flow.results.summary,graph._runpod_client,'runpod_public_response_summary',(item,),{}),(flow.results.extract,graph._runpod_output_parser,'extract_runpod_worker_output',(item,),{}),(flow.results.import_artifacts(),graph._runpod_artifacts,'import_runpod_yolo_artifacts',(item,other),{}),(graph._runpod_payload.upload,graph._runpod_exports,'create_runpod_training_artifact_upload',(item,other),{}),(graph._runpod_payload.timeout,settings,'runpod_yolo_job_timeout_seconds',(),{}),(graph._runpod_payload.inline_limit,settings,'runpod_yolo_inline_dataset_max_bytes',(),{}),(graph._runpod_submission.timeout,settings,'runpod_yolo_job_timeout_seconds',(),{}),(graph._runpod_submission.ttl,settings,'runpod_yolo_dataset_token_ttl_seconds',(),{}),(api.run_runpod_training_task,flow,'run_runpod_training_task',(item,other,third),{})):
        assert_native_relay(case,selected,(owner,method,args,kw,args,kw))
    for selected in (flow.results.request(),graph._runpod_submission.request):
        args=('POST','fixture');kw={'json_body':item,'timeout_seconds':17}
        assert_native_relay(case,selected,(graph._runpod_client,'runpod_yolo_http_request',args,kw,args,kw))

    assert_native_relay(case,flow.results.request(),(graph._runpod_client,'runpod_yolo_http_request',('GET','fixture'),{},('GET','fixture'),{'json_body':None,'timeout_seconds':None}))
    assert_native_relay(case,graph._runpod_submission.request,(graph._runpod_client,'runpod_yolo_http_request',('POST','fixture'),{'json_body':item},('POST','fixture'),{'json_body':item,'timeout_seconds':None}))

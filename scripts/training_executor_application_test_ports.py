"""Finite native RunPod transport settings for offline original regressions."""
from dataclasses import replace
from unittest.mock import patch


def bind_training_executor(api,stack):
    owner=api._default_application.training_pipeline._runpod_client
    stack.enter_context(patch.object(owner,'settings',replace(owner.settings,url=lambda path:api.runpod_yolo_url(path),authorization=lambda:api.runpod_yolo_authorization_values(),timeout=lambda:api.runpod_yolo_client_timeout_seconds())))
    stack.enter_context(patch.object(owner,'bound_text',lambda:api.bounded_text))


def assert_default_training_executor(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.training.runpod_client import RunPodClient
    from local_inspection_service.runtime.wiring import training_pipeline
    verify_actual_sources();case=unittest.TestCase();graph=api._default_application.training_pipeline;owner=graph._runpod_client;settings=graph._training_executor_settings;item=object()
    case.assertIs(type(owner),RunPodClient);case.assertIs(api._runpod_client,owner)
    case.assertIs(owner.request(),training_pipeline.requests.request);case.assertIs(owner.bound_text(),training_pipeline.bounded_text)
    for selected,method,args in ((owner.settings.url,'runpod_yolo_url',(item,)),(owner.settings.authorization,'runpod_yolo_authorization_values',()),(owner.settings.timeout,'runpod_yolo_client_timeout_seconds',())):
        assert_native_relay(case,selected,(settings,method,args,{},args,{}))
    for kwargs in ({},{'json_body':item,'timeout_seconds':17}):
        assert_native_relay(case,api.runpod_yolo_http_request,(owner,'runpod_yolo_http_request',('POST','fixture'),kwargs,('POST','fixture'),{'json_body':kwargs.get('json_body'),'timeout_seconds':kwargs.get('timeout_seconds')}))
    assert_native_relay(case,api.runpod_public_response_summary,(owner,'runpod_public_response_summary',(item,),{},(item,),{}))

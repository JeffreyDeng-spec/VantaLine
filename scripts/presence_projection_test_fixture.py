"""Native detection projections with narrow, live contract suppliers."""
from types import SimpleNamespace
from local_inspection_service.detection.failure_projection import FailureProjection
from local_inspection_service.detection.presence_results import PresenceResults


def presence_projection_fixture(server):
    assert_default_projections(server)
    from local_inspection_service.detection.failure_results import DetectionFailureResult
    names=('bounded_text','string_list','coerce_detection_count','AI_DETECTION_LABEL','ai_tool_provider_meta','ai_detection_settings','required_accessory_profile_payload')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    failure=FailureProjection(lambda:api.bounded_text,lambda settings:api.ai_tool_provider_meta(settings),lambda:api.AI_DETECTION_LABEL)
    results=PresenceResults(lambda:api.coerce_detection_count,lambda:api.bounded_text,lambda:api.string_list,
                            lambda settings:api.ai_tool_provider_meta(settings),lambda:api.AI_DETECTION_LABEL)
    api.ai_presence_failure_payload=failure.ai_presence_failure_payload
    api.normalize_ai_detection_result=results.normalize_ai_detection_result
    api.ai_model_payload=failure.ai_model_payload
    assembly=DetectionFailureResult(lambda:api.ai_detection_settings(),lambda item,count:api.required_accessory_profile_payload(item,count),
        lambda required,settings,**kwargs:api.ai_presence_failure_payload(required,settings,**kwargs),lambda spec,settings:api.ai_model_payload(spec,settings))
    api.ai_detection_failure_result=assembly.ai_detection_failure_result
    return api


def assert_default_projections(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    from local_inspection_service.detection.presence_payload import PresencePayload
    verify_actual_sources()
    case=unittest.TestCase()
    application=server._default_application
    graph=application.inspection
    failure,results,payload=graph._failure_projection,graph._presence_results,graph._presence_payload
    for owner,kind,name in ((failure,FailureProjection,'_failure_projection'),(results,PresenceResults,'_presence_results'),(payload,PresencePayload,'_presence_payload')):
        case.assertIs(type(owner),kind)
        case.assertIs(getattr(server,name),owner)
        case.assertIs(owner.text(),inspection.bounded_text)
    case.assertIs(results.strings(),inspection.string_list)
    case.assertIs(payload.strings(),inspection.string_list)
    for owner in (failure,results):
        original=application.values.AI_DETECTION_LABEL
        try:
            for label in (original,'synthetic-first-label','synthetic-second-label'):
                object.__setattr__(application.values,'AI_DETECTION_LABEL',label)
                case.assertIs(owner.label(),label)
        finally:object.__setattr__(application.values,'AI_DETECTION_LABEL',original)
        for settings,expected in (({'provider':'fixture-A','model':'model-A','status':'status-A','api_key':'synthetic-only'},{'provider':'fixture-A','provider_model':'model-A','provider_status':'status-A'}),({}, {'provider':'','provider_model':'','provider_status':''})):
            case.assertEqual(owner.provider_meta(settings),expected)
    from local_inspection_service.detection.failure_results import DetectionFailureResult
    assembly=graph._detection_failure_result
    case.assertIs(type(assembly),DetectionFailureResult)
    case.assertIs(server._detection_failure_result,assembly)
    item,parsed,settings=object(),object(),object()
    for selected,target,method,args,keywords,forwarded in (
        (assembly.settings,application.infrastructure._model_profile_configuration,'ai_detection_settings',(),{},('pipeline',)),
        (assembly.profile,graph._accessory_profile_payloads,'required_accessory_profile_payload',(item,7),{},(item,7,None)),
        (assembly.failure,failure,'ai_presence_failure_payload',(item,settings),{'reason':'fixture','timed_out':True,'latency_ms':731},(item,settings)),
        (assembly.model,failure,'ai_model_payload',(parsed,settings),{},(parsed,settings)),
    ):
        assert_native_relay(case,selected,(target,method,args,keywords,forwarded,keywords))
    for keywords,forwarded in (({'reason':'fixture'},{'reason':'fixture','timed_out':False,'latency_ms':0}),({'reason':'fixture','timed_out':True,'latency_ms':731},{'reason':'fixture','timed_out':True,'latency_ms':731})):
        args=('request-fixture',parsed,item,'/synthetic-output')
        assert_native_relay(case,server.ai_detection_failure_result,(assembly,'ai_detection_failure_result',args,keywords,args,forwarded))
    with patch.object(inspection,'_presence_count',return_value=item) as callee:
        case.assertIs(results.count()(parsed),item)
        callee.assert_called_once_with(parsed)
        case.assertIs(callee.call_args.args[0],parsed)
    for selected,owner,method,args,kwargs in (
        (server.ai_presence_failure_payload,failure,'ai_presence_failure_payload',(item,settings),{'reason':'fixture','timed_out':True,'latency_ms':731}),
        (server.normalize_ai_detection_result,results,'normalize_ai_detection_result',(parsed,item,23,settings),{}),
        (server.ai_model_payload,failure,'ai_model_payload',(parsed,settings),{}),
        (server.ai_detection_task_payload,payload,'ai_detection_task_payload',(item,),{}),
    ):
        assert_native_relay(case,selected,(owner,method,args,kwargs,args,kwargs))

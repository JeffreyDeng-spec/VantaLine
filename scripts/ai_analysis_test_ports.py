"""Replace only the actual typed AI analysis ports; keep snapshot ownership."""
from unittest.mock import patch
from local_inspection_service.detection.analysis_ports import AiProfiles, AiInspectionTools, AiAnalysisEvidence


def bind_ai_analysis_ports(api,stack):
    owner=api._default_application.inspection._ai_detection_analysis
    for name,value in (
        ('profiles',AiProfiles(lambda config,spec:api.ai_required_accessories(config,spec),lambda item:api.accessory_uid(item),
            lambda profile,item:api.normalize_accessory_ai_profile(profile,item),lambda item:api.accessory_reference_image_contexts(item),
            lambda item,count,profile:api.required_accessory_profile_payload(item,count,profile),lambda config:api.save_config(config))),
        ('tools',AiInspectionTools(lambda:api.call_ai_mcp_tool,lambda:api.ai_detection_settings,lambda:api.external_ai_mcp_enabled(),
            lambda image,request_id:api.write_mcp_inspection_image(image,request_id),lambda:api.AI_REFERENCE_IMAGES_PER_ACCESSORY,
            lambda:api.AI_REFERENCE_IMAGE_MAX_SIDE,lambda:api.AI_REFERENCE_IMAGE_QUALITY)),
        ('evidence',AiAnalysisEvidence(lambda image,request_id:api.write_ai_original_output(image,request_id),
            lambda request_id,spec,required,url,**kwargs:api.ai_detection_failure_result(request_id,spec,required,url,**kwargs),
            lambda spec,settings:api.ai_model_payload(spec,settings),
            lambda result,request_id,**kwargs:api.persist_data_analysis_record_for_ai_detection(result,request_id,**kwargs))),
        ('feedback',None),
    ):stack.enter_context(patch.object(owner,name,value))


def assert_default_ai_analysis(api):
    import unittest
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    from local_inspection_service.detection.ai_analysis import AiDetectionAnalysis
    from local_inspection_service.detection.workflow_composition import DetectionWorkflows
    from local_inspection_service.model_providers import mcp_runtime
    verify_actual_sources()
    case=unittest.TestCase()
    application=api._default_application
    graph=application.inspection
    workflows=graph._detection_workflows
    owner=graph._ai_detection_analysis
    case.assertIs(type(owner),AiDetectionAnalysis)
    case.assertIs(type(workflows),DetectionWorkflows)
    case.assertIs(workflows.ai,owner)
    case.assertIs(api._ai_detection_analysis,owner)
    case.assertIs(api._detection_workflows,workflows)
    case.assertIs(workflows.pinned_ai.__wrapped__.__self__,workflows)
    case.assertIs(workflows.pinned_ai.__wrapped__.__func__,DetectionWorkflows.analyze_bgr_ai_detection)
    item,other,profile=object(),object(),object()
    for selected,target,method,args,kwargs,forwarded,forward_kwargs in (
        (owner.tools.call(),graph._model_tool_dispatch,'call_ai_mcp_tool',('fixture-tool',item),{},('fixture-tool',item),{}),
        (owner.profiles.required,graph._required_accessories,'ai_required_accessories',(item,other),{},(item,other),{}),
        (owner.profiles.normalize,graph._accessory_profile_projection,'normalize_accessory_ai_profile',(profile,item),{},(profile,item),{}),
        (owner.profiles.references,graph._reference_evidence,'accessory_reference_image_contexts',(item,),{},(item,),{'max_images':application.values.AI_PROFILE_REFERENCE_IMAGES}),
        (owner.profiles.payload,graph._accessory_profile_payloads,'required_accessory_profile_payload',(item,7,profile),{},(item,7,profile),{}),
        (owner.profiles.save,application.infrastructure._app_configuration,'save_config',(item,),{},(item,),{}),
        (owner.tools.settings(),application.infrastructure._model_profile_configuration,'ai_detection_settings',(),{},('pipeline',),{}),
        (owner.tools.settings(),application.infrastructure._model_profile_configuration,'ai_detection_settings',('accessory',),{},('accessory',),{}),
        (owner.tools.image,graph._inspection_image_store,'write_mcp_inspection_image',(item,'synthetic'),{},(item,'synthetic'),{}),
        (owner.evidence.original,graph._detection_annotation,'write_ai_original_output',(item,'synthetic'),{},(item,'synthetic'),{}),
        (owner.evidence.failure,graph._detection_failure_result,'ai_detection_failure_result',('synthetic',item,other,'/synthetic'),{'reason':'fixture'},('synthetic',item,other,'/synthetic'),{'reason':'fixture','timed_out':False,'latency_ms':0}),
        (owner.evidence.model,graph._failure_projection,'ai_model_payload',(item,other),{},(item,other),{}),
        (owner.evidence.persist,workflows.analysis.publisher,'persist_data_analysis_record_for_ai_detection',(item,'synthetic'),{'image_path':other},(item,'synthetic'),{'image_path':other}),
        (workflows.analyze_bgr_ai_detection,owner,'analyze_bgr_ai_detection',(item,'synthetic',other,profile),{'image_path':item},(item,'synthetic',other,profile),{'image_path':item}),
    ):
        assert_native_relay(case,selected,(target,method,args,kwargs,forwarded,forward_kwargs))
    with patch.object(inspection._accessory_policy,'accessory_uid',return_value=other) as callee:
        case.assertIs(owner.profiles.uid(item),other)
        callee.assert_called_once_with(item)
        case.assertIs(callee.call_args.args[0],item)
    case.assertIs(inspection.external_ai_mcp_enabled,mcp_runtime.external_ai_mcp_enabled)
    with patch.object(inspection,'external_ai_mcp_enabled',return_value=other) as callee:
        case.assertIs(owner.tools.external(),other)
        callee.assert_called_once_with()
    for field,name in (('references_per_accessory','AI_REFERENCE_IMAGES_PER_ACCESSORY'),('reference_max_side','AI_REFERENCE_IMAGE_MAX_SIDE'),('reference_quality','AI_REFERENCE_IMAGE_QUALITY')):
        original=getattr(application.values,name)
        case.assertIs(getattr(owner.tools,field)(),original)
        try:
            object.__setattr__(application.values,name,original+101)
            case.assertEqual(getattr(owner.tools,field)(),original+101)
        finally:object.__setattr__(application.values,name,original)

    # Exercise the actual owned and public pin boundaries with the real
    # resolver supplier, without running inference or persisting evidence.
    from contextlib import contextmanager
    from contextvars import ContextVar
    from types import SimpleNamespace
    from scripts.model_profile_test_ports import patch_profile_service
    from unittest.mock import Mock
    binding=ContextVar('synthetic-default-ai-binding',default=None)
    snapshot={'pipeline':{'version':17,'secret_ref':'synthetic-only'}}
    @contextmanager
    def scope(value):
        token=binding.set(value)
        try:yield
        finally:binding.reset(token)
    resolver=SimpleNamespace(current_snapshot=Mock(side_effect=binding.get),snapshot_for_record=Mock(return_value=snapshot),scope=Mock(side_effect=scope))
    sentinel=object()
    for selected in (workflows.pinned_ai,api.analyze_bgr_ai_detection):
        resolver.current_snapshot.reset_mock();resolver.snapshot_for_record.reset_mock();resolver.scope.reset_mock()
        def received(receiver,image,request_id,spec,config,*,image_path=None):
            case.assertIs(receiver,owner)
            case.assertIs(binding.get(),snapshot)
            case.assertIs(image,item);case.assertIs(spec,other);case.assertIs(config,profile)
            case.assertIs(image_path,item)
            return sentinel
        with patch_profile_service(api,resolver),patch.object(AiDetectionAnalysis,'analyze_bgr_ai_detection',autospec=True,side_effect=received) as callee:
            case.assertIs(selected(item,'synthetic',other,profile,image_path=item),sentinel)
            callee.assert_called_once_with(owner,item,'synthetic',other,profile,image_path=item)
            resolver.current_snapshot.assert_called_once_with()
            resolver.snapshot_for_record.assert_called_once_with({})
            resolver.scope.assert_called_once_with(snapshot)
        case.assertIsNone(binding.get())
    with patch_profile_service(api,None):
        with case.assertRaisesRegex(RuntimeError,'resolver is not configured'):
            workflows.pinned_ai(item,'synthetic',other,profile)

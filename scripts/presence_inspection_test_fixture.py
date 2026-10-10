"""Native presence flow with finite live suppliers and default graph witnesses."""
from local_inspection_service.detection.presence_inspection import PresenceInspection
from local_inspection_service.detection.presence_inspection_ports import PresenceInput, PresenceGeneration, PresenceOutput, PresencePolicy


def presence_inspection_fixture(server):
    from types import SimpleNamespace
    from scripts.detection_media_test_fixture import detection_media_fixture
    api=detection_media_fixture(server)
    assert_default_presence(server)
    names=('ai_detection_settings','resolve_required_accessory_refs','ai_detection_task_payload',
           'ensure_required_profile_cache','ai_detection_provider_output_token_budget','call_ai_mcp_tool',
           'ai_detection_parsed_covers_required','normalize_ai_detection_result','ai_presence_failure_payload',
           'AI_PROVIDER_MAX_ATTEMPTS','AI_DETECTION_SYSTEM_PROMPT','AI_DETECTION_OUTPUT_SCHEMA')
    for name in names:setattr(api,name,getattr(server,name))
    graph=PresenceInspection(PresenceInput(lambda:api.ai_detection_settings(),lambda:api.resolve_required_accessory_refs,lambda:api.image_path_data_url,lambda:api.image_bgr_data_url),PresenceGeneration(lambda required:api.ai_detection_task_payload(required),lambda required,settings:api.ensure_required_profile_cache(required,settings),lambda:api.ai_detection_provider_output_token_budget,lambda:api.call_ai_mcp_tool,lambda:api.ai_detection_parsed_covers_required),PresenceOutput(lambda:api.ai_presence_failure_payload,lambda:api.normalize_ai_detection_result),PresencePolicy(lambda:api.AI_INSPECTION_IMAGE_MAX_SIDE,lambda:api.AI_INSPECTION_IMAGE_QUALITY,lambda:api.AI_PROVIDER_MAX_ATTEMPTS,lambda:api.AI_REFERENCE_IMAGES_PER_ACCESSORY,lambda:api.AI_DETECTION_SYSTEM_PROMPT,lambda:api.AI_DETECTION_OUTPUT_SCHEMA),lambda:api.time.monotonic())
    api._presence_inspection=graph
    # The fixture exposes only this registry view. The real ModelTools owner
    # and dispatch identities are checked separately below before substitution.
    api._model_tools=SimpleNamespace(presence=graph)
    api.tool_vision_inspect_presence=graph.tool_vision_inspect_presence
    api.AI_MCP_TOOL_HANDLERS['vision.inspect.presence']=api.tool_vision_inspect_presence
    return api


def assert_default_presence(server):
    import unittest
    from unittest.mock import patch
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    from local_inspection_service.model_providers.tool_composition import ModelTools
    case=unittest.TestCase()
    application=server._default_application
    owners=application.inspection
    graph=owners._presence_inspection
    tools=owners._model_tools
    case.assertIs(type(graph),PresenceInspection)
    case.assertIs(server._presence_inspection,graph)
    case.assertIs(type(tools),ModelTools)
    case.assertIs(server._model_tools,tools)
    case.assertIs(tools.presence,graph)
    case.assertIs(tools.dispatch,owners._model_tool_dispatch)
    case.assertIs(tools.handlers,server.AI_MCP_TOOL_HANDLERS)
    case.assertIs(graph.generation.call().__self__,tools)
    case.assertIs(graph.generation.call().__func__,ModelTools.call_ai_mcp_tool)
    item,other,parsed,settings=object(),object(),object(),object()
    relays=(
        (graph.input.settings,application.infrastructure._model_profile_configuration,'ai_detection_settings',(),{},('pipeline',),{}),
        (graph.input.resolve(),owners._accessory_profile_payloads,'resolve_required_accessory_refs',(item,),{},(item,),{}),
        (graph.input.path(),owners._image_encoding,'image_path_data_url',(item,),{'max_side':17,'quality':73},(item,),{'max_side':17,'quality':73}),
        (graph.input.image(),owners._image_encoding,'image_bgr_data_url',(item,),{'max_side':17,'quality':73},(item,),{'max_side':17,'quality':73}),
        (graph.generation.task,owners._presence_payload,'ai_detection_task_payload',(item,),{},(item,),{}),
        (graph.generation.cache,owners._profile_cache_flow,'ensure_required_profile_cache',(item,settings),{},(item,settings),{}),
        (graph.output.normalize(),owners._presence_results,'normalize_ai_detection_result',(parsed,item,17,settings),{},(parsed,item,17,settings),{}),
        (graph.output.failure(),owners._failure_projection,'ai_presence_failure_payload',(item,settings),{'reason':'fixture'},(item,settings),{'reason':'fixture','timed_out':False,'latency_ms':0}),
        (graph.output.failure(),owners._failure_projection,'ai_presence_failure_payload',(item,settings),{'reason':'fixture','timed_out':True,'latency_ms':731},(item,settings),{'reason':'fixture','timed_out':True,'latency_ms':731}),
        (server.tool_vision_inspect_presence,graph,'tool_vision_inspect_presence',(item,),{},(item,),{}),
    )
    for selected,owner,method,args,keywords,forwarded,forward_keywords in relays:
        assert_native_relay(case,selected,(owner,method,args,keywords,forwarded,forward_keywords))
    case.assertIs(server.AI_MCP_TOOL_HANDLERS['vision.inspect.presence'].__self__,graph)
    case.assertIs(server.AI_MCP_TOOL_HANDLERS['vision.inspect.presence'].__func__,PresenceInspection.tool_vision_inspect_presence)
    for field,name in (('max_side','AI_INSPECTION_IMAGE_MAX_SIDE'),('quality','AI_INSPECTION_IMAGE_QUALITY'),('max_attempts','AI_PROVIDER_MAX_ATTEMPTS'),('references','AI_REFERENCE_IMAGES_PER_ACCESSORY'),('prompt','AI_DETECTION_SYSTEM_PROMPT'),('schema','AI_DETECTION_OUTPUT_SCHEMA')):
        original=getattr(application.values,name)
        case.assertIs(getattr(graph.policy,field)(),original)
        replacement=original+101 if type(original) is int else {'fixture':True} if type(original) is dict else 'fixture-prompt'
        try:
            object.__setattr__(application.values,name,replacement)
            case.assertIs(getattr(graph.policy,field)(),replacement)
        finally:object.__setattr__(application.values,name,original)
    sentinel=object()
    with patch.object(inspection,'_presence_covers_required',return_value=sentinel) as callee:
        case.assertIs(graph.generation.covers()(parsed,other),sentinel)
        callee.assert_called_once_with(parsed,other)
        case.assertIs(callee.call_args.args[0],parsed)
        case.assertIs(callee.call_args.args[1],other)
    with patch.object(inspection.time,'monotonic',return_value=sentinel) as callee:
        case.assertIs(graph.clock(),sentinel)
        callee.assert_called_once_with()
    for count,gemini,qwen in ((-5,184,368),(0,184,368),(1,184,368),(2,248,496),(3,312,624),(4,376,752),(5,420,800),(100,420,800)):
        case.assertEqual(graph.generation.tokens()(count,{'provider':'gemini'}),gemini)
        case.assertEqual(graph.generation.tokens()(count,{'provider':'qwen'}),qwen)

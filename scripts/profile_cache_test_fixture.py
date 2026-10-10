"""Finite native cache and presence integration contracts with default witnesses."""
from local_inspection_service.detection.profile_cache_policy import ProfileCachePolicy
from local_inspection_service.detection.profile_cache_store import ProfileCacheStore
from local_inspection_service.detection.profile_cache import ProfileCacheFlow, CacheRecords, CacheEvidence, CacheProviders, CacheTiming


def profile_cache_fixture(server):
    from scripts.presence_inspection_test_fixture import presence_inspection_fixture
    api=presence_inspection_fixture(server)
    assert_default_cache(server)
    names=('string_list','AI_PROFILE_CACHE_VERSION','AI_PROFILE_CACHE_TTL_SECONDS','AI_PROFILE_CACHE_PATH',
           'DATA_DIR','GeminiAiProvider','ai_provider_from_settings','os')
    for name in names:setattr(api,name,getattr(server,name))
    policy=ProfileCachePolicy(lambda:api.string_list,lambda:api.AI_PROFILE_CACHE_VERSION,lambda:api.AI_PROFILE_REFERENCE_MODE,lambda:api.AI_DETECTION_SYSTEM_PROMPT,lambda required:api.ai_detection_task_payload(required),lambda required:api.build_reference_sheet_descriptor(required))
    store=ProfileCacheStore(lambda:api.DATA_DIR,lambda:api.AI_PROFILE_CACHE_PATH,lambda:api.os)
    flow=ProfileCacheFlow(CacheRecords(lambda:api.load_ai_profile_cache(),lambda records:api.save_ai_profile_cache(records)),CacheEvidence(lambda required,settings:api.required_accessory_cache_key(required,settings),lambda required:api.profile_reference_descriptors(required),lambda required,references:api.cached_profile_context_content(required,references)),CacheProviders(lambda settings:api.ai_provider_from_settings(settings),lambda:api.GeminiAiProvider,lambda:api.AiProviderError),CacheTiming(lambda:api.time.time(),lambda:api.AI_PROFILE_CACHE_TTL_SECONDS),lambda:api.AI_DETECTION_SYSTEM_PROMPT,lambda:api.bounded_text)
    for name,owner,methods in (('_profile_cache_policy',policy,('required_accessory_cache_key','profile_reference_descriptors','cached_profile_context_content')),('_profile_cache_store',store,('load_ai_profile_cache','save_ai_profile_cache')),('_profile_cache_flow',flow,('ensure_required_profile_cache',))):
        setattr(api,name,owner)
        for method in methods:setattr(api,method,getattr(owner,method))
    return api


def assert_default_cache(server):
    import unittest
    from unittest.mock import patch
    from pathlib import Path
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    case=unittest.TestCase()
    application=server._default_application
    graph=application.inspection
    policy,store,flow=graph._profile_cache_policy,graph._profile_cache_store,graph._profile_cache_flow
    for name,owner,kind in (('_profile_cache_policy',policy,ProfileCachePolicy),('_profile_cache_store',store,ProfileCacheStore),('_profile_cache_flow',flow,ProfileCacheFlow)):
        case.assertIs(type(owner),kind)
        case.assertIs(getattr(server,name),owner)
    case.assertIs(policy.strings(),inspection.string_list)
    case.assertIs(store.files(),inspection.os)
    case.assertIs(server._provider_transports,graph._provider_transports)
    case.assertIs(flow.providers.kind(),graph._provider_transports.gemini)
    case.assertIs(flow.providers.kind(),server.GeminiAiProvider)
    case.assertIs(flow.providers.error(),inspection.AiProviderError)
    case.assertIs(flow.text(),inspection.bounded_text)
    for selected,name in ((policy.version,'AI_PROFILE_CACHE_VERSION'),(policy.reference_mode,'AI_PROFILE_REFERENCE_MODE'),(policy.prompt,'AI_DETECTION_SYSTEM_PROMPT'),(store.data_dir,'DATA_DIR'),(store.path,'AI_PROFILE_CACHE_PATH'),(flow.timing.ttl,'AI_PROFILE_CACHE_TTL_SECONDS'),(flow.prompt,'AI_DETECTION_SYSTEM_PROMPT')):
        original=getattr(application.values,name)
        case.assertIs(selected(),original)
        replacement=original+101 if type(original) is int else Path('synthetic-profile-cache') if isinstance(original,Path) else 'synthetic-cache-policy'
        try:
            object.__setattr__(application.values,name,replacement)
            case.assertIs(selected(),replacement)
        finally:object.__setattr__(application.values,name,original)
    item,settings,refs=object(),object(),object()
    for selected,owner,method,args in (
        (policy.task,graph._presence_payload,'ai_detection_task_payload',(item,)),
        (policy.sheet,graph._reference_sheet,'build_reference_sheet_descriptor',(item,)),
        (flow.records.load,store,'load_ai_profile_cache',()),
        (flow.records.save,store,'save_ai_profile_cache',(item,)),
        (flow.evidence.key,policy,'required_accessory_cache_key',(item,settings)),
        (flow.evidence.references,policy,'profile_reference_descriptors',(item,)),
        (flow.evidence.context,policy,'cached_profile_context_content',(item,refs)),
        (flow.providers.factory,graph._provider_selection,'ai_provider_from_settings',(settings,)),
        (server.ensure_required_profile_cache,flow,'ensure_required_profile_cache',(item,settings)),
    ):
        assert_native_relay(case,selected,(owner,method,args,{},args,{}))
    sentinel=object()
    with patch.object(inspection.time,'time',return_value=sentinel) as callee:
        case.assertIs(flow.timing.now(),sentinel)
        callee.assert_called_once_with()

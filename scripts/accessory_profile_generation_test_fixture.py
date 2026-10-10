"""Native profile generation contracts; model calls remain synthetic."""
from types import SimpleNamespace
from local_inspection_service.accessories.profile_generation import AccessoryProfileGeneration
from local_inspection_service.accessories.profile_generation_ports import GenerationProfiles,GenerationCalls,GenerationReferences,GenerationUpdates

GROUPS=(
    (GenerationProfiles,{'fallback':'fallback_accessory_ai_profile','normalize':'normalize_accessory_ai_profile','prompt':'accessory_profile_prompt_payload','generate':'generate_accessory_ai_profile'}),
    (GenerationCalls,{'settings':'ai_detection_settings','status':'profile_generation_status','invoke':'call_ai_mcp_tool'}),
    (GenerationReferences,{'contexts':'accessory_reference_image_contexts','limit':'AI_PROFILE_REFERENCE_IMAGES','max_side':'AI_PROFILE_REFERENCE_IMAGE_MAX_SIDE','quality':'AI_PROFILE_REFERENCE_IMAGE_QUALITY'}),
    (GenerationUpdates,{'uid':'accessory_uid','rename':'ensure_accessory_english_name','dimensions':'apply_ai_profile_dimensions_to_physical_size'}),
)


def profile_generation_fixture(server):
    assert_default_profile_generation(server)
    api=SimpleNamespace(**{name:getattr(server,name) for _,fields in GROUPS for name in fields.values()})
    api.json=server.json
    def supplier(name):return lambda:getattr(api,name)
    owner=AccessoryProfileGeneration(*(kind(**{field:supplier(name) for field,name in fields.items()}) for kind,fields in GROUPS))
    for name in ('tool_accessory_profile_generate','generate_accessory_ai_profile','ensure_accessory_ai_profile'):
        setattr(api,name,getattr(owner,name))
    return api


def assert_default_profile_generation(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    from local_inspection_service.accessories import profile_generation
    verify_actual_sources()
    case=unittest.TestCase();app=server._default_application;graph=app.inspection
    owner=graph._accessory_profile_generation
    case.assertIs(profile_generation.json,server.json)
    case.assertIs(type(owner),AccessoryProfileGeneration);case.assertIs(server._accessory_profile_generation,owner)
    item,other=object(),object()
    for selected,target,method,args,keywords,forwarded,forward_keywords in (
        (owner._profiles.fallback(),graph._accessory_profile_projection,'fallback_accessory_ai_profile',(item,),{},(item,None),{}),
        (owner._profiles.normalize(),graph._accessory_profile_projection,'normalize_accessory_ai_profile',(item,other),{},(item,other),{}),
        (owner._profiles.prompt(),graph._accessory_profile_payloads,'accessory_profile_prompt_payload',(item,),{},(item,),{}),
        (owner._profiles.generate(),owner,'generate_accessory_ai_profile',(item,),{},(item,),{'allow_provider':True}),
        (owner._profiles.generate(),owner,'generate_accessory_ai_profile',(item,),{'allow_provider':False},(item,),{'allow_provider':False}),
        (owner._calls.settings(),app.infrastructure._model_profile_configuration,'ai_detection_settings',('accessory',),{},('accessory',),{}),
        (owner._calls.invoke(),graph._model_tool_dispatch,'call_ai_mcp_tool',('synthetic-tool',item),{},('synthetic-tool',item),{}),
        (owner._references.contexts(),graph._reference_evidence,'accessory_reference_image_contexts',(item,),{'max_images':2},(item,),{'max_images':2}),
        (owner._references.contexts(),graph._reference_evidence,'accessory_reference_image_contexts',(item,),{},(item,),{'max_images':app.values.AI_PROFILE_REFERENCE_IMAGES}),
        (owner._updates.rename(),graph._accessory_labels,'ensure_accessory_english_name',(item,),{},(item,),{}),
        (owner._updates.dimensions(),graph._accessory_dimensions,'apply_ai_profile_dimensions_to_physical_size',(item,other),{},(item,other),{}),
        (server.tool_accessory_profile_generate,owner,'tool_accessory_profile_generate',(item,),{},(item,),{}),
        (server.generate_accessory_ai_profile,owner,'generate_accessory_ai_profile',(item,),{},(item,),{'allow_provider':True}),
        (server.generate_accessory_ai_profile,owner,'generate_accessory_ai_profile',(item,),{'allow_provider':False},(item,),{'allow_provider':False}),
        (server.ensure_accessory_ai_profile,owner,'ensure_accessory_ai_profile',(item,),{},(item,),{'force':False,'allow_provider':True}),
        (server.ensure_accessory_ai_profile,owner,'ensure_accessory_ai_profile',(item,),{'force':True,'allow_provider':False},(item,),{'force':True,'allow_provider':False}),
    ):
        assert_native_relay(case,selected,(target,method,args,keywords,forwarded,forward_keywords))
    with patch.object(inspection._accessory_policy,'accessory_uid',return_value=other) as callee:
        case.assertIs(owner._updates.uid()(item),other);callee.assert_called_once_with(item)
    settings={'provider':'synthetic','model':'synthetic-model','status':'ready','message':'fixture'}
    with patch.object(inspection.time,'time',return_value=731.9):
        for arguments,source in (({},'fallback'),({'source':'synthetic-source'},'synthetic-source')):
            case.assertEqual(owner._calls.status()(settings,**arguments),dict(source=source,provider='synthetic',provider_model='synthetic-model',status='ready',message='fixture',updated_at=731))
    for selected,name in ((owner._references.limit,'AI_PROFILE_REFERENCE_IMAGES'),(owner._references.max_side,'AI_PROFILE_REFERENCE_IMAGE_MAX_SIDE'),(owner._references.quality,'AI_PROFILE_REFERENCE_IMAGE_QUALITY')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:
            object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)

"""Finite native dimension, display label and profile contract fixtures."""
from types import SimpleNamespace
from local_inspection_service.accessories.physical_dimensions import AccessoryDimensions
from local_inspection_service.accessories.physical_dimension_ports import DimensionValues,DimensionUpdates
from local_inspection_service.accessories.display_labels import AccessoryLabels
from local_inspection_service.accessories.display_label_ports import DisplayLabelPolicy,DisplayLabelText
from local_inspection_service.accessories.profile_projection import AccessoryProfileProjection
from local_inspection_service.accessories.profile_projection_ports import ProfileIdentity,ProfileText,ProfileDimensions,ProfileReferences

DIMENSIONS=(
    (DimensionValues,{'number':'optional_float','papers':'STANDARD_PAPER_SIZES_MM','objects':'DEFAULT_OBJECT_SIZE_MM'}),
    (DimensionUpdates,{'material':'accessory_material_type','payload':'physical_size_payload'}),
)
LABELS=(
    (DisplayLabelPolicy,{'generic_tokens':'GENERIC_ENGLISH_NAME_TOKENS','fields':'ACCESSORY_ENGLISH_NAME_FIELDS','fallbacks':'ACCESSORY_ENGLISH_NAME_FALLBACKS','phrases':'ACCESSORY_ENGLISH_PHRASES'}),
    (DisplayLabelText,{'bounded':'bounded_text','strings':'string_list','compact':'compact_english_accessory_name','preferred':'preferred_english_accessory_name'}),
)
PROFILES=(
    (ProfileIdentity,{'uid':'accessory_uid','material':'accessory_material_type','alpha':'object_alpha_material_policy'}),
    (ProfileText,{'bounded':'bounded_text','strings':'string_list','preferred':'preferred_english_accessory_name','compact':'compact_english_accessory_name','size':'profile_size_text'}),
    (ProfileDimensions,{'physical':'ai_profile_dimensions_from_physical_size','normalize':'normalize_ai_profile_dimensions','ratio':'ai_profile_top_view_aspect_ratio','number':'optional_float'}),
    (ProfileReferences,{'contexts':'accessory_reference_image_contexts','fallback':'fallback_accessory_ai_profile','limit':'AI_PROFILE_REFERENCE_IMAGES'}),
)


def fixture(server,groups,kind,methods):
    assert_default_projections(server)
    names={name for _,fields in groups for name in fields.values()}
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    def supplier(name):return lambda:getattr(api,name)
    owner=kind(*(ports(**{field:supplier(name) for field,name in fields.items()}) for ports,fields in groups))
    for name in methods:setattr(api,name,getattr(owner,name))
    return api


def dimensions_fixture(server):
    return fixture(server,DIMENSIONS,AccessoryDimensions,('physical_size_payload','ai_profile_dimensions_from_physical_size',
        'ai_profile_top_view_aspect_ratio','normalize_ai_profile_dimensions','apply_ai_profile_dimensions_to_physical_size'))


def labels_fixture(server):
    api=fixture(server,LABELS,AccessoryLabels,('compact_english_accessory_name','preferred_english_accessory_name',
        'ensure_accessory_english_name','accessory_display_label'))
    api.profile_size_text=server.profile_size_text
    return api


def profile_fixture(server):
    return fixture(server,PROFILES,AccessoryProfileProjection,('fallback_accessory_ai_profile','normalize_accessory_ai_profile'))


def assert_default_projections(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    from local_inspection_service.compatibility import infrastructure as legacy
    from local_inspection_service.runtime.text_policy import bounded_text
    from local_inspection_service.config.list_policy import string_list
    verify_actual_sources()
    case=unittest.TestCase()
    app=server._default_application;graph=app.inspection
    dimensions,labels,profile=graph._accessory_dimensions,graph._accessory_labels,graph._accessory_profile_projection
    for owner,kind,name in ((dimensions,AccessoryDimensions,'_accessory_dimensions'),(labels,AccessoryLabels,'_accessory_labels'),(profile,AccessoryProfileProjection,'_accessory_profile_projection')):
        case.assertIs(type(owner),kind)
        case.assertIs(getattr(server,name),owner)
    for text in (labels._text,profile._text):
        case.assertIs(text.bounded(),bounded_text)
        case.assertIs(text.strings(),string_list)
    for selected in (dimensions._values.number(),profile._dimensions.number()):
        for value,expected in ((None,None),('',None),('2.5',2.5),(0,None),(-1,None),('bad',None)):
            case.assertEqual(selected(value),expected)
    item,other=object(),object()
    for selected,target,method,args,keywords,forwarded,forward_keywords in (
        (dimensions._updates.payload(),dimensions,'physical_size_payload',('object',),{},('object','A4',None,None,None,None,None),{}),
        (labels._text.compact(),labels,'compact_english_accessory_name',(item,),{},(item,),{'max_words':6}),
        (labels._text.preferred(),labels,'preferred_english_accessory_name',(item,),{},(item,),{}),
        (profile._text.preferred(),labels,'preferred_english_accessory_name',(item,),{},(item,),{}),
        (profile._text.compact(),labels,'compact_english_accessory_name',(item,),{'max_words':3},(item,),{'max_words':3}),
        (profile._dimensions.physical(),dimensions,'ai_profile_dimensions_from_physical_size',(item,),{},(item,),{}),
        (profile._dimensions.normalize(),dimensions,'normalize_ai_profile_dimensions',(item,other),{},(item,other),{}),
        (profile._dimensions.ratio(),dimensions,'ai_profile_top_view_aspect_ratio',(item,),{},(item,),{}),
        (profile._references.contexts(),graph._reference_evidence,'accessory_reference_image_contexts',(item,),{'max_images':2},(item,),{'max_images':2}),
        (profile._references.fallback(),profile,'fallback_accessory_ai_profile',(item,),{},(item,None),{}),
    ):
        assert_native_relay(case,selected,(target,method,args,keywords,forwarded,forward_keywords))
    for target,names in ((dimensions,('physical_size_payload','ai_profile_dimensions_from_physical_size','ai_profile_top_view_aspect_ratio','normalize_ai_profile_dimensions','apply_ai_profile_dimensions_to_physical_size')),
        (labels,('compact_english_accessory_name','preferred_english_accessory_name','ensure_accessory_english_name','accessory_display_label')),
        (profile,('fallback_accessory_ai_profile','normalize_accessory_ai_profile'))):
        for name in names:
            args=(item,other) if name in ('normalize_ai_profile_dimensions','apply_ai_profile_dimensions_to_physical_size','normalize_accessory_ai_profile') else ('object',) if name=='physical_size_payload' else (item,)
            forwarded=args+(None,) if name=='fallback_accessory_ai_profile' else ('object','A4',None,None,None,None,None) if name=='physical_size_payload' else args
            keywords={'max_words':6} if name=='compact_english_accessory_name' else {}
            assert_native_relay(case,getattr(server,name),(target,name,args,{},forwarded,keywords))
    payload_keywords={'paper_preset':'custom','paper_width_mm':101,'paper_height_mm':202,'object_length_mm':303,'object_width_mm':404,'object_height_mm':505}
    for selected in (dimensions._updates.payload(),server.physical_size_payload):
        assert_native_relay(case,selected,(dimensions,'physical_size_payload',('object',),payload_keywords,('object','custom',101,202,303,404,505),{}))
    for selected in (labels._text.compact(),profile._text.compact(),server.compact_english_accessory_name):
        assert_native_relay(case,selected,(labels,'compact_english_accessory_name',(item,),{},(item,),{'max_words':6}))
        assert_native_relay(case,selected,(labels,'compact_english_accessory_name',(item,),{'max_words':2},(item,),{'max_words':2}))
    for selected in (profile._references.fallback(),server.fallback_accessory_ai_profile):
        for references in ([],[other]):
            assert_native_relay(case,selected,(profile,'fallback_accessory_ai_profile',(item,),{'reference_images':references},(item,references),{}))
    assert_native_relay(case,profile._references.contexts(),(graph._reference_evidence,'accessory_reference_image_contexts',(item,),{},(item,),{'max_images':app.values.AI_PROFILE_REFERENCE_IMAGES}))
    for selected,name,args in ((dimensions._updates.material(),'accessory_material_type',(item,)),(profile._identity.uid(),'accessory_uid',(item,)),
        (profile._identity.material(),'accessory_material_type',(item,)),(profile._identity.alpha(),'object_alpha_material_policy',(item,None))):
        sentinel=object()
        with patch.object(inspection._accessory_policy,name,return_value=sentinel) as callee:
            case.assertIs(selected(item),sentinel)
            callee.assert_called_once_with(*args)
    for selected,module in ((profile._text.size(),inspection),(server.profile_size_text,legacy)):
        sentinel=object()
        with patch.object(module,'_profile_size_text_impl',return_value=sentinel) as callee:
            case.assertIs(selected(item),sentinel)
            callee.assert_called_once_with(item)
    for selected,name in ((dimensions._values.papers,'STANDARD_PAPER_SIZES_MM'),(dimensions._values.objects,'DEFAULT_OBJECT_SIZE_MM'),
        (labels._policy.generic_tokens,'GENERIC_ENGLISH_NAME_TOKENS'),(labels._policy.fields,'ACCESSORY_ENGLISH_NAME_FIELDS'),
        (labels._policy.fallbacks,'ACCESSORY_ENGLISH_NAME_FALLBACKS'),(labels._policy.phrases,'ACCESSORY_ENGLISH_PHRASES'),
        (profile._references.limit,'AI_PROFILE_REFERENCE_IMAGES')):
        original=getattr(app.values,name);case.assertIs(selected(),original);sentinel=object()
        try:
            object.__setattr__(app.values,name,sentinel)
            case.assertIs(selected(),sentinel)
        finally:object.__setattr__(app.values,name,original)

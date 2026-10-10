"""Finite native accessory payload contracts and actual composition witnesses."""
from types import SimpleNamespace
from local_inspection_service.accessories.profile_payloads import AccessoryProfilePayloads
from local_inspection_service.accessories.profile_payload_ports import PayloadIdentity, PayloadProfiles, PayloadCatalog


def accessory_profile_payload_fixture(server):
    assert_default_payloads(server)
    names=('accessory_uid','accessory_material_type','fallback_accessory_ai_profile',
           'normalize_accessory_ai_profile','required_accessory_profile_payload',
           'size_reference_payload','load_config','bounded_text')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    owner=AccessoryProfilePayloads(
        PayloadIdentity(lambda:api.accessory_uid,lambda:api.accessory_material_type),
        PayloadProfiles(lambda:api.fallback_accessory_ai_profile,lambda:api.normalize_accessory_ai_profile,
                        lambda:api.required_accessory_profile_payload,lambda:api.size_reference_payload),
        PayloadCatalog(lambda:api.load_config,lambda:api.bounded_text))
    for name in ('accessory_profile_prompt_payload','required_accessory_profile_payload','resolve_required_accessory_refs'):
        setattr(api,name,getattr(owner,name))
    return api


def assert_default_payloads(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    verify_actual_sources()
    case=unittest.TestCase()
    application=server._default_application
    graph=application.inspection
    owner=graph._accessory_profile_payloads
    case.assertIs(type(owner),AccessoryProfilePayloads)
    case.assertIs(server._accessory_profile_payloads,owner)
    case.assertIs(owner._catalog.text(),inspection.bounded_text)
    item,raw,profile,refs=object(),object(),object(),object()
    for selected,method in ((owner._identity.uid(),'accessory_uid'),(owner._identity.material(),'accessory_material_type')):
        sentinel=object()
        with patch.object(inspection._accessory_policy,method,return_value=sentinel) as callee:
            case.assertIs(selected(item),sentinel)
            callee.assert_called_once_with(item)
            case.assertIs(callee.call_args.args[0],item)
    relays=(
        (owner._profiles.fallback(),graph._accessory_profile_projection,'fallback_accessory_ai_profile',(item,),(item,None)),
        (owner._profiles.fallback(),graph._accessory_profile_projection,'fallback_accessory_ai_profile',(item,refs),(item,refs)),
        (owner._profiles.normalize(),graph._accessory_profile_projection,'normalize_accessory_ai_profile',(raw,item),(raw,item)),
        (owner._profiles.required(),owner,'required_accessory_profile_payload',(item,7),(item,7,None)),
        (owner._profiles.required(),owner,'required_accessory_profile_payload',(item,7,profile),(item,7,profile)),
        (owner._profiles.reference(),graph._reference_dimensions,'size_reference_payload',(item,),(item,)),
        (owner._catalog.config(),application.infrastructure._app_configuration,'load_config',(),()),
        (server.accessory_profile_prompt_payload,owner,'accessory_profile_prompt_payload',(item,),(item,)),
        (server.required_accessory_profile_payload,owner,'required_accessory_profile_payload',(item,7,profile),(item,7,profile)),
        (server.resolve_required_accessory_refs,owner,'resolve_required_accessory_refs',(refs,),(refs,)),
    )
    for selected,target,method,args,forwarded in relays:
        assert_native_relay(case,selected,(target,method,args,{},forwarded,{}))

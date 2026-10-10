"""Finite native background selection ports with actual ownership witnesses."""
from types import SimpleNamespace
from local_inspection_service.accessories.background_library_selection import BackgroundCandidateCatalog,BackgroundLibraryMatcher
from local_inspection_service.accessories.background_library_selection_ports import BackgroundOwnership,BackgroundCatalogSources,BackgroundCatalogPolicy,BackgroundMatchSources,BackgroundMatchFeatures
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.images import ImageFiles


def background_library_fixture(server):
    assert_default_background_library(server)
    names=('cv2','SYSTEM_OWNER_ID','LEGACY_OWNER_ID','load_background_sets_manifest','background_set_dirs',
        'safe_background_set_id','image_file_list','resolve_service_path','BACKGROUND_SETS_DIR','IMAGE_REFERENCE_SUFFIXES',
        'PIPELINE_BG_MATCH_MAX_LIBRARY_IMAGES','background_reference_signatures_from_accessory',
        'background_patch_boxes','background_patch_signature','background_signature_distance','PIPELINE_BG_MATCH_DISTANCE_THRESHOLD')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    files=BusinessFiles(lambda:None)
    catalog=BackgroundCandidateCatalog(BackgroundOwnership(lambda:api.SYSTEM_OWNER_ID,lambda:api.LEGACY_OWNER_ID),
        BackgroundCatalogSources(lambda:api.load_background_sets_manifest,lambda:api.background_set_dirs,lambda:api.safe_background_set_id,
            lambda:api.background_set_visible_for_owner,lambda:api.image_file_list,lambda:api.resolve_service_path),
        BackgroundCatalogPolicy(lambda:api.BACKGROUND_SETS_DIR,lambda:api.IMAGE_REFERENCE_SUFFIXES,lambda:api.PIPELINE_BG_MATCH_MAX_LIBRARY_IMAGES),files=files)
    matcher=BackgroundLibraryMatcher(BackgroundMatchSources(lambda:api.background_reference_signatures_from_accessory,lambda:api.background_library_image_candidates),
        BackgroundMatchFeatures(lambda:api.background_patch_boxes,lambda:api.background_patch_signature,lambda:api.background_signature_distance),
        lambda:api.PIPELINE_BG_MATCH_DISTANCE_THRESHOLD,images=ImageFiles(lambda:api.cv2,files=files))
    api.background_set_visible_for_owner=catalog.background_set_visible_for_owner
    api.background_library_image_candidates=catalog.background_library_image_candidates
    api.match_background_library_plate=matcher.match_background_library_plate
    return api


def assert_default_background_library(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    verify_actual_sources()
    case=unittest.TestCase()
    application=server._default_application
    graph,training=application.inspection,application.training_pipeline
    catalog,matcher=graph._background_candidate_catalog,graph._background_library_matcher
    for owner,kind,name in ((catalog,BackgroundCandidateCatalog,'_background_candidate_catalog'),(matcher,BackgroundLibraryMatcher,'_background_library_matcher')):
        case.assertIs(type(owner),kind)
        case.assertIs(getattr(server,name),owner)
    case.assertIs(catalog.files,application.artifacts.files)
    case.assertIs(matcher.images,application.infrastructure._accessory_image_io)
    case.assertIs(type(matcher.images),ImageFiles)
    case.assertIs(matcher.images.files,application.artifacts.files)
    case.assertIs(matcher.images.cv2_provider(),inspection.cv2)
    case.assertIs(catalog._sources.sanitize(),inspection.safe_background_set_id)
    item,other=object(),object()
    for selected,owner,method,args,keywords,forward_keywords in (
        (catalog._sources.manifest(),training._background_manifest,'load_background_sets_manifest',(),{},{}),
        (catalog._sources.directories(),training._background_seeding,'background_set_dirs',(),{},{}),
        (catalog._sources.visible(),catalog,'background_set_visible_for_owner',(item,'synthetic-owner'),{},{}),
        (catalog._sources.images(),training._background_image_files,'image_file_list',(item,),{},{}),
        (catalog._sources.resolve(),application.infrastructure._service_paths,'resolve_service_path',(item,),{}, {'for_write':False}),
        (matcher._sources.references(),graph._background_reference_signatures,'background_reference_signatures_from_accessory',(item,),{},{}),
        (matcher._sources.candidates(),catalog,'background_library_image_candidates',('synthetic-owner',),{},{}),
        (server.background_set_visible_for_owner,catalog,'background_set_visible_for_owner',(item,'synthetic-owner'),{},{}),
        (server.background_library_image_candidates,catalog,'background_library_image_candidates',('synthetic-owner',),{},{}),
        (server.match_background_library_plate,matcher,'match_background_library_plate',(item,'synthetic-owner'),{},{}),
    ):
        assert_native_relay(case,selected,(owner,method,args,keywords,args,forward_keywords))
    for selected,name in ((catalog._ownership.system,'SYSTEM_OWNER_ID'),(catalog._ownership.legacy,'LEGACY_OWNER_ID'),
        (catalog._policy.directory,'BACKGROUND_SETS_DIR'),(catalog._policy.suffixes,'IMAGE_REFERENCE_SUFFIXES'),
        (catalog._policy.limit,'PIPELINE_BG_MATCH_MAX_LIBRARY_IMAGES'),(matcher._threshold,'PIPELINE_BG_MATCH_DISTANCE_THRESHOLD')):
        original=getattr(application.values,name)
        case.assertIs(selected(),original)
        sentinel=object()
        try:
            object.__setattr__(application.values,name,sentinel)
            case.assertIs(selected(),sentinel)
        finally:object.__setattr__(application.values,name,original)
    for selected,name,args in ((matcher._features.boxes(),'_background_patch_boxes_impl',(17,23)),
        (matcher._features.signature(),'_background_patch_signature_impl',(item,)),(matcher._features.distance(),'_background_signature_distance_impl',(item,other))):
        sentinel=object()
        with patch.object(inspection,name,return_value=sentinel) as callee:
            case.assertIs(selected(*args),sentinel)
            callee.assert_called_once_with(*args)
            for actual,expected in zip(callee.call_args.args,args):
                if type(expected) is object:case.assertIs(actual,expected)

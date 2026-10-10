"""Finite native background plate/signature contracts and real graph witnesses."""
from types import SimpleNamespace
from local_inspection_service.accessories.background_evidence import BackgroundPlateDerivation,BackgroundReferenceSignatures
from local_inspection_service.accessories.background_evidence_ports import PlateSources,PlatePolicy,BackgroundMasks,SignatureSources,SignaturePolicy,SignatureProjections
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.images import ImageFiles


def background_evidence_fixture(server):
    assert_default_background_evidence(server)
    names=('cv2','np','time','agent_mcp_pose_reference_assets','accessory_reference_image_contexts','resolve_service_path',
        'IMAGE_REFERENCE_SUFFIXES','PIPELINE_BG_PLATE_TIME_BUDGET_S','PIPELINE_BG_PLATE_MAX_SIDE','PIPELINE_BG_PLATE_MAX_INPAINT_RADIUS',
        'PIPELINE_BG_PLATE_INPAINT_MAX_MASK_FRAC','foreground_mask','object_photo_highlight_source_paths',
        'PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES','PIPELINE_BG_MATCH_MAX_SOURCE_PATCHES','background_patch_boxes','background_patch_signature','background_signature_distance')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    files=BusinessFiles(lambda:None);images=ImageFiles(lambda:api.cv2,files=files)
    masks=BackgroundMasks(lambda:api.foreground_mask)
    plate=BackgroundPlateDerivation(PlateSources(lambda:api.agent_mcp_pose_reference_assets,lambda:api.accessory_reference_image_contexts,
        lambda:api.resolve_service_path,lambda:api.IMAGE_REFERENCE_SUFFIXES),PlatePolicy(lambda:api.PIPELINE_BG_PLATE_TIME_BUDGET_S,
        lambda:api.PIPELINE_BG_PLATE_MAX_SIDE,lambda:api.PIPELINE_BG_PLATE_MAX_INPAINT_RADIUS,lambda:api.PIPELINE_BG_PLATE_INPAINT_MAX_MASK_FRAC),masks,files=files,images=images)
    signatures=BackgroundReferenceSignatures(SignatureSources(lambda:api.object_photo_highlight_source_paths,lambda:api.PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES),
        SignaturePolicy(lambda:api.PIPELINE_BG_MATCH_MAX_SOURCE_PATCHES),masks,SignatureProjections(lambda:api.background_patch_boxes,lambda:api.background_patch_signature),images=images)
    api.derive_background_plate_from_accessory=plate.derive_background_plate_from_accessory
    api.background_reference_signatures_from_accessory=signatures.background_reference_signatures_from_accessory
    return api


def assert_default_background_evidence(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    from local_inspection_service.compatibility import infrastructure as legacy
    verify_actual_sources()
    case=unittest.TestCase()
    application=server._default_application
    graph=application.inspection
    plate,signatures=graph._background_plate_derivation,graph._background_reference_signatures
    for owner,kind,name in ((plate,BackgroundPlateDerivation,'_background_plate_derivation'),(signatures,BackgroundReferenceSignatures,'_background_reference_signatures')):
        case.assertIs(type(owner),kind)
        case.assertIs(getattr(server,name),owner)
        case.assertIs(owner.images,application.infrastructure._accessory_image_io)
        case.assertIs(type(owner.images),ImageFiles)
        case.assertIs(owner.images.files,application.artifacts.files)
        case.assertIs(owner.images.cv2_provider(),inspection.cv2)
    case.assertIs(plate.files,application.artifacts.files)
    item,other=object(),object()
    for selected,owner,method,args,keywords,forward_keywords in (
        (plate._sources.pose_assets(),application.training_pipeline._agent_pose_assets,'agent_mcp_pose_reference_assets',(item,),{},{}),
        (plate._sources.contexts(),graph._reference_evidence,'accessory_reference_image_contexts',(item,),{'max_images':4},{'max_images':4}),
        (plate._sources.resolve(),application.infrastructure._service_paths,'resolve_service_path',(item,),{}, {'for_write':False}),
        (signatures._sources.paths(),application.training_pipeline._photo_highlight_sources,'object_photo_highlight_source_paths',(item,),{'limit':7},{'limit':7}),
        (server.derive_background_plate_from_accessory,plate,'derive_background_plate_from_accessory',(item,other),{},{}),
        (server.background_reference_signatures_from_accessory,signatures,'background_reference_signatures_from_accessory',(item,),{},{}),
    ):
        assert_native_relay(case,selected,(owner,method,args,keywords,args,forward_keywords))
    for selected,name in ((plate._sources.suffixes,'IMAGE_REFERENCE_SUFFIXES'),(plate._policy.time_budget,'PIPELINE_BG_PLATE_TIME_BUDGET_S'),
        (plate._policy.max_side,'PIPELINE_BG_PLATE_MAX_SIDE'),(plate._policy.max_radius,'PIPELINE_BG_PLATE_MAX_INPAINT_RADIUS'),
        (plate._policy.mask_fraction,'PIPELINE_BG_PLATE_INPAINT_MAX_MASK_FRAC'),(signatures._sources.limit,'PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES'),
        (signatures._policy.max_patches,'PIPELINE_BG_MATCH_MAX_SOURCE_PATCHES')):
        original=getattr(application.values,name)
        case.assertIs(selected(),original)
        replacement={'.synthetic'} if isinstance(original,(set,frozenset)) else 101.25 if isinstance(original,float) else 101
        try:
            object.__setattr__(application.values,name,replacement)
            case.assertIs(selected(),replacement)
        finally:object.__setattr__(application.values,name,original)
    for selected,module,name,args in (
        (plate._masks.foreground(),inspection,'_foreground_mask_impl',(item,)),
        (signatures._masks.foreground(),inspection,'_foreground_mask_impl',(item,)),
        (signatures._projections.boxes(),inspection,'_background_patch_boxes_impl',(17,23)),
        (signatures._projections.signature(),inspection,'_background_patch_signature_impl',(item,)),
        (server.background_patch_boxes,legacy,'_background_patch_boxes_impl',(17,23)),
        (server.background_patch_signature,legacy,'_background_patch_signature_impl',(item,)),
        (server.background_signature_distance,legacy,'_background_signature_distance_impl',(item,other)),
    ):
        sentinel=object()
        with patch.object(module,name,return_value=sentinel) as callee:
            case.assertIs(selected(*args),sentinel)
            callee.assert_called_once_with(*args)
            for actual,expected in zip(callee.call_args.args,args):
                if type(expected) is object:case.assertIs(actual,expected)

"""Native reference evidence with finite policy, path and image capabilities."""
from types import SimpleNamespace
from local_inspection_service.accessories.reference_evidence import ReferenceEvidence
from local_inspection_service.accessories.reference_evidence_ports import ReferencePolicy,ReferencePaths,ReferenceContexts,ReferenceChroma
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.images import ImageFiles


def reference_evidence_fixture(server):
    assert_default_reference_evidence(server)
    names=('cv2','IMAGE_REFERENCE_SUFFIXES','CHROMA_SCREEN_OPTIONS','AI_PROFILE_REFERENCE_IMAGES','resolve_service_path',
        'candidate_image_jobs','default_asset_for_accessory','first_source_ai_reference_path','accessory_uid','bounded_text','saturated_chroma_mask','file_sha256')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    files=BusinessFiles(lambda:None);images=ImageFiles(cv2_provider=lambda:api.cv2,files=files)
    owner=ReferenceEvidence(ReferencePolicy(suffixes=lambda:api.IMAGE_REFERENCE_SUFFIXES,screens=lambda:api.CHROMA_SCREEN_OPTIONS),
        ReferencePaths(resolve=lambda:api.resolve_service_path,jobs=lambda:api.candidate_image_jobs,default=lambda:api.default_asset_for_accessory,
            preferred=lambda:api.ai_profile_reference_paths,first_source=lambda:api.first_source_ai_reference_path,inventory=lambda:api.accessory_image_paths),
        ReferenceContexts(uid=lambda:api.accessory_uid,bounded=lambda:api.bounded_text,context=lambda:api.image_reference_context,
            references=lambda:api.accessory_reference_image_contexts),ReferenceChroma(normalize=lambda:api.normalize_chroma_screen,
            mask=lambda:api.saturated_chroma_mask),files=files,images=images)
    for name in ('accessory_image_paths','ai_profile_reference_paths','image_reference_context','normalize_chroma_screen','accessory_reference_chroma_fraction'):
        setattr(api,name,getattr(owner,name))
    def contexts(item,*,max_images=api.AI_PROFILE_REFERENCE_IMAGES):
        return owner.accessory_reference_image_contexts(item,max_images=max_images)
    api.accessory_reference_image_contexts=contexts
    return api


def assert_default_reference_evidence(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    from local_inspection_service.runtime.text_policy import bounded_text
    verify_actual_sources()
    case=unittest.TestCase();app=server._default_application;graph=app.inspection;owner=graph._reference_evidence
    case.assertIs(type(owner),ReferenceEvidence);case.assertIs(server._reference_evidence,owner)
    case.assertIs(owner.files,app.artifacts.files);case.assertIs(owner.images,app.infrastructure._accessory_image_io)
    case.assertIs(type(owner.images),ImageFiles);case.assertIs(owner.images.files,owner.files)
    case.assertIs(owner.images.cv2_provider(),inspection.cv2);case.assertIs(owner._contexts.bounded(),bounded_text)
    selected=owner._paths.first_source()
    case.assertIs(selected.__self__,graph._candidate_artifacts)
    case.assertIs(selected.__func__,type(graph._candidate_artifacts).first_source_ai_reference_path)
    item,other=object(),object()
    for selected,target,method,args,keywords,forwarded,forward_keywords in (
        (owner._paths.resolve(),app.infrastructure._service_paths,'resolve_service_path',(item,),{},(item,),{'for_write':False}),
        (owner._paths.default(),graph._preview_asset_loader,'default_asset_for_accessory',(item,),{},(item,),{}),
        (owner._paths.preferred(),owner,'ai_profile_reference_paths',(item,),{},(item,),{}),
        (owner._paths.inventory(),owner,'accessory_image_paths',(item,),{},(item,),{}),
        (owner._contexts.context(),owner,'image_reference_context',(item,'synthetic-id',7),{},(item,'synthetic-id',7),{}),
        (owner._contexts.references(),owner,'accessory_reference_image_contexts',(item,),{},(item,),{'max_images':app.values.AI_PROFILE_REFERENCE_IMAGES}),
        (owner._contexts.references(),owner,'accessory_reference_image_contexts',(item,),{'max_images':2},(item,),{'max_images':2}),
        (owner._chroma.normalize(),owner,'normalize_chroma_screen',(item,),{},(item,),{}),
    ):
        assert_native_relay(case,selected,(target,method,args,keywords,forwarded,forward_keywords))
    for name,args,keywords,forward_keywords in (
        ('accessory_image_paths',(item,),{},{}),('ai_profile_reference_paths',(item,),{},{}),
        ('image_reference_context',(item,'synthetic-id',7),{},{}),('normalize_chroma_screen',(item,),{},{}),
        ('accessory_reference_image_contexts',(item,),{},{'max_images':app.values.AI_PROFILE_REFERENCE_IMAGES}),
        ('accessory_reference_image_contexts',(item,),{'max_images':2},{'max_images':2}),
        ('accessory_reference_chroma_fraction',(item,'green'),{},{'max_images':3}),
        ('accessory_reference_chroma_fraction',(item,'green'),{'max_images':7},{'max_images':7}),
    ):
        assert_native_relay(case,getattr(server,name),(owner,name,args,keywords,args,forward_keywords))
    for selected,name,args in ((owner._paths.jobs(),'_image_metadata_jobs',(item,)),(owner._chroma.mask(),'_saturated_chroma_mask_impl',(item,other))):
        with patch.object(inspection,name,return_value=other) as callee:
            case.assertIs(selected(*args),other);callee.assert_called_once_with(*args);case.assertIs(callee.call_args.args[0],item)
    with patch.object(inspection._accessory_policy,'accessory_uid',return_value=other) as callee:
        case.assertIs(owner._contexts.uid()(item),other);callee.assert_called_once_with(item)
    for selected,name in ((owner._policy.suffixes,'IMAGE_REFERENCE_SUFFIXES'),(owner._policy.screens,'CHROMA_SCREEN_OPTIONS')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:
            object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)

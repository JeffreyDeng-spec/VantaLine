"""Finite native preview sprite and document media contract fixtures."""
from types import SimpleNamespace
from local_inspection_service.accessories.preview_sprites import PreviewSpriteRenderer,load_clean_sprite
from local_inspection_service.accessories.preview_sprite_ports import PreviewSpriteInventory,PreviewSpritePoses,PreviewSpriteMedia,PreviewSpriteGeometry
from local_inspection_service.accessories.preview_assets import PreviewAssetLoader
from local_inspection_service.accessories.preview_asset_ports import PreviewAssetPolicy,PreviewAssetPaths,PreviewAssetOperations
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.images import ImageFiles


def preview_sprites_fixture(server):
    assert_default_preview_media(server)
    names=('cv2','clean_sprite_assets','preprocess_object_clean_sprites','accessory_sprite_version','canonical_pose_family_name',
        'sprite_pose_family','pose_family_is_top_view','filter_complete_pose_candidates','UPRIGHT_TOP_VIEW_SOURCE_POSITIONS','resolve_service_path','rotate_masked_asset')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    images=ImageFiles(cv2_provider=lambda:api.cv2,files=BusinessFiles(lambda:None))
    api.load_clean_sprite=lambda path:load_clean_sprite(path,images=images)
    owner=PreviewSpriteRenderer(PreviewSpriteInventory(assets=lambda:api.clean_sprite_assets,preprocess=lambda:api.preprocess_object_clean_sprites,
        version=lambda:api.accessory_sprite_version),PreviewSpritePoses(canonical=lambda:api.canonical_pose_family_name,family=lambda:api.sprite_pose_family,
        top_view=lambda:api.pose_family_is_top_view,complete=lambda:api.filter_complete_pose_candidates,upright_positions=lambda:api.UPRIGHT_TOP_VIEW_SOURCE_POSITIONS),
        PreviewSpriteMedia(resolve=lambda:api.resolve_service_path,decode=lambda:api.load_clean_sprite),PreviewSpriteGeometry(rotate=lambda:api.rotate_masked_asset))
    api.load_object_preview_sprite=owner.load_object_preview_sprite
    api.restore_object_sprite_source_orientation_for_render=owner.restore_object_sprite_source_orientation_for_render
    return api


def preview_assets_fixture(server):
    assert_default_preview_media(server)
    names=('cv2','ROOT','IMAGE_REFERENCE_SUFFIXES','resolve_service_path','select_document_image_candidate')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    files=BusinessFiles(lambda:None);images=ImageFiles(cv2_provider=lambda:api.cv2,files=files)
    owner=PreviewAssetLoader(PreviewAssetPolicy(root=lambda:api.ROOT,suffixes=lambda:api.IMAGE_REFERENCE_SUFFIXES),
        PreviewAssetPaths(resolve=lambda:api.resolve_service_path),PreviewAssetOperations(default=lambda:api.default_asset_for_accessory,
            candidate=lambda:api.load_document_image_candidate,select=lambda:api.select_document_image_candidate,preview=lambda:api.load_preview_asset_with_metadata),files=files,images=images)
    for name in ('default_asset_for_accessory','load_preview_asset_with_metadata','load_document_image_candidate','load_rectified_document_asset_with_metadata','load_preview_asset'):
        setattr(api,name,getattr(owner,name))
    return api


def assert_default_preview_media(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    from local_inspection_service.compatibility import infrastructure as legacy
    verify_actual_sources()
    case=unittest.TestCase();app=server._default_application;graph=app.inspection
    sprites,assets=graph._preview_sprite_renderer,graph._preview_asset_loader
    for owner,kind,name in ((sprites,PreviewSpriteRenderer,'_preview_sprite_renderer'),(assets,PreviewAssetLoader,'_preview_asset_loader')):
        case.assertIs(type(owner),kind);case.assertIs(getattr(server,name),owner)
    case.assertIs(assets.files,app.artifacts.files);case.assertIs(assets.images,app.infrastructure._accessory_image_io)
    case.assertIs(type(assets.images),ImageFiles);case.assertIs(assets.images.files,assets.files)
    case.assertIs(assets.images.cv2_provider(),inspection.cv2)
    item,mask,metadata=object(),object(),object()
    for selected,target,method,args,keywords,forwarded,forward_keywords in (
        (sprites._inventory.assets(),graph._sprite_asset_catalog,'clean_sprite_assets',(item,),{},(item,),{}),
        (sprites._inventory.preprocess(),graph._object_sprite_preprocessor,'preprocess_object_clean_sprites',(item,),{'allow_ai_cutout':False},(item,False,False),{}),
        (sprites._inventory.preprocess(),graph._object_sprite_preprocessor,'preprocess_object_clean_sprites',(item,),{'allow_ai_cutout':True,'force':True},(item,True,True),{}),
        (sprites._inventory.preprocess(),graph._object_sprite_preprocessor,'preprocess_object_clean_sprites',(item,),{'allow_ai_cutout':False,'force':True},(item,False,True),{}),
        (sprites._inventory.version(),app.training_pipeline._training_preview_cache,'accessory_sprite_version',(item,),{},(item,),{}),
        (sprites._poses.top_view(),graph._sprite_footprint,'pose_family_is_top_view',('top',mask),{},('top',mask),{}),
        (sprites._poses.top_view(),graph._sprite_footprint,'pose_family_is_top_view',('top',),{},('top',None),{}),
        (sprites._poses.complete(),graph._pose_candidate_policy,'filter_complete_pose_candidates',(item,'top'),{},(item,'top'),{}),
        (sprites._geometry.rotate(),graph._sprite_geometry,'rotate_masked_asset',(item,mask,13),{},(item,mask,13),{}),
        (sprites._media.resolve(),app.infrastructure._service_paths,'resolve_service_path',(item,),{},(item,),{'for_write':False}),
        (assets._paths.resolve(),app.infrastructure._service_paths,'resolve_service_path',(item,),{},(item,),{'for_write':False}),
        (assets._operations.default(),assets,'default_asset_for_accessory',(item,),{},(item,),{}),
        (assets._operations.candidate(),assets,'load_document_image_candidate',(item,metadata),{},(item,metadata),{}),
        (assets._operations.preview(),assets,'load_preview_asset_with_metadata',(item,),{},(item,),{}),
        (server.load_object_preview_sprite,sprites,'load_object_preview_sprite',(item,mask),{},(item,mask,None,None,None),{}),
        (server.load_object_preview_sprite,sprites,'load_object_preview_sprite',(item,mask),{'target_position':'target','pose_family':'pose','source_position':'source'},(item,mask,'target','pose','source'),{}),
        (server.load_rectified_document_asset_with_metadata,assets,'load_rectified_document_asset_with_metadata',(item,),{},(item,None),{}),
        (server.load_rectified_document_asset_with_metadata,assets,'load_rectified_document_asset_with_metadata',(item,),{'rng':mask},(item,mask),{}),
    ):
        assert_native_relay(case,selected,(target,method,args,keywords,forwarded,forward_keywords))
    for flag in (False,True):
        assert_native_relay(case,server.restore_object_sprite_source_orientation_for_render,(sprites,'restore_object_sprite_source_orientation_for_render',
            (item,mask,metadata),{'top_view_pose':flag},(item,mask,metadata),{'top_view_pose':flag}))
    for name in ('default_asset_for_accessory','load_preview_asset_with_metadata','load_preview_asset'):
        assert_native_relay(case,getattr(server,name),(assets,name,(item,),{},(item,),{}))
    assert_native_relay(case,server.load_document_image_candidate,(assets,'load_document_image_candidate',(item,metadata),{},(item,metadata),{}))
    for selected,name,args,keywords in ((sprites._poses.canonical(),'_canonical_pose_family_name_impl',(item,),{}),
        (sprites._poses.family(),'_sprite_pose_family_impl',(item,),{}),
        (sprites._media.decode(),'_load_clean_sprite_impl',(item,),{'images':assets.images}),
        (assets._operations.select(),'_select_document_image_candidate_impl',(item,mask),{'multi_policy':'many','single_policy':'one'})):
        with patch.object(inspection,name,return_value=metadata) as callee:
            call_keywords={} if name=='_load_clean_sprite_impl' else keywords
            case.assertIs(selected(*args,**call_keywords),metadata)
            callee.assert_called_once_with(*args,**keywords)
            case.assertIs(callee.call_args.args[0],item)
    for selected,name in ((sprites._poses.upright_positions,'UPRIGHT_TOP_VIEW_SOURCE_POSITIONS'),(assets._policy.root,'ROOT'),(assets._policy.suffixes,'IMAGE_REFERENCE_SUFFIXES')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:
            object.__setattr__(app.values,name,metadata);case.assertIs(selected(),metadata)
        finally:object.__setattr__(app.values,name,original)
    with patch.object(legacy,'_load_clean_sprite_impl',return_value=metadata) as callee:
        case.assertIs(server.load_clean_sprite(item),metadata)
        callee.assert_called_once_with(item,images=assets.images)
        case.assertIs(callee.call_args.args[0],item);case.assertIs(callee.call_args.kwargs['images'],assets.images)

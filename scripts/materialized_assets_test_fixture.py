"""Native materialized catalogs with finite policies and explicit media adapters."""
from types import SimpleNamespace
from local_inspection_service.accessories.materialized_assets import SpriteAssetCatalog,TextAssetCatalog
from local_inspection_service.accessories.materialized_asset_ports import MaterializedAssetPaths,SpriteCatalogPoseOperations,SpriteCatalogMaterialPolicy,SpriteCatalogReadiness,TextCatalogOperations
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.images import ImageFiles


def materialized_assets_fixture(server):
    assert_default_materialized_assets(server)
    names=('cv2','resolve_service_path','pose_family_is_top_view','pose_render_footprint_metadata',
        'apply_upright_scale_correction_metadata','apply_laying_standard_render_size_hints','object_alpha_material_policy',
        'normalize_object_alpha_material_policy','clean_sprite_metadata_complete','IMAGE_REFERENCE_SUFFIXES','text_accessory_confirm_detail')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    files=BusinessFiles(lambda:None);images=ImageFiles(cv2_provider=lambda:api.cv2,files=files)
    paths=MaterializedAssetPaths(resolve=lambda:api.resolve_service_path)
    sprite=SpriteAssetCatalog(paths,SpriteCatalogPoseOperations(top_view=lambda:api.pose_family_is_top_view,
        footprint=lambda:api.pose_render_footprint_metadata,upright=lambda:api.apply_upright_scale_correction_metadata,
        laying=lambda:api.apply_laying_standard_render_size_hints),SpriteCatalogMaterialPolicy(expected=lambda:api.object_alpha_material_policy,
        normalize=lambda:api.normalize_object_alpha_material_policy),SpriteCatalogReadiness(assets=lambda:api.clean_sprite_assets,
        metadata=lambda:api.clean_sprite_metadata_complete,material=lambda:api.clean_sprite_material_policy_matches),files=files,images=images)
    text=TextAssetCatalog(paths,TextCatalogOperations(suffixes=lambda:api.IMAGE_REFERENCE_SUFFIXES,
        assets=lambda:api.canonical_text_assets),files=files,images=images)
    for owner,names in ((sprite,('clean_sprite_assets','clean_sprite_material_policy_matches','clean_sprites_policy_complete')),
        (text,('canonical_text_assets','canonical_text_assets_complete'))):
        for name in names:setattr(api,name,getattr(owner,name))
    return api


def assert_default_materialized_assets(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    from local_inspection_service.compatibility import infrastructure as legacy
    verify_actual_sources()
    case=unittest.TestCase();app=server._default_application;graph=app.inspection
    sprite,text=graph._sprite_asset_catalog,graph._text_asset_catalog
    for owner,kind,name in ((sprite,SpriteAssetCatalog,'_sprite_asset_catalog'),(text,TextAssetCatalog,'_text_asset_catalog')):
        case.assertIs(type(owner),kind);case.assertIs(getattr(server,name),owner)
        case.assertIs(owner.files,app.artifacts.files)
        case.assertIs(owner.images,app.infrastructure._accessory_image_io)
        case.assertIs(type(owner.images),ImageFiles);case.assertIs(owner.images.files,owner.files)
        case.assertIs(owner.images.cv2_provider(),inspection.cv2)
    item,other=object(),object()
    for selected,target,method,args,forwarded,keywords in (
        (sprite._paths.resolve(),app.infrastructure._service_paths,'resolve_service_path',(item,),(item,),{'for_write':False}),
        (text._paths.resolve(),app.infrastructure._service_paths,'resolve_service_path',(item,),(item,),{'for_write':False}),
        (sprite._pose.top_view(),graph._sprite_footprint,'pose_family_is_top_view',('top',other),('top',other),{}),
        (sprite._pose.footprint(),graph._sprite_footprint,'pose_render_footprint_metadata',('top',item,other),('top',item,other),{}),
        (sprite._pose.upright(),graph._sprite_scale,'apply_upright_scale_correction_metadata',(item,other),(item,other),{}),
        (sprite._pose.laying(),graph._sprite_render_metadata,'apply_laying_standard_render_size_hints',(item,),(item,),{}),
        (sprite._readiness.assets(),sprite,'clean_sprite_assets',(item,),(item,),{}),
        (sprite._readiness.material(),sprite,'clean_sprite_material_policy_matches',(item,other),(item,other),{}),
        (text._operations.assets(),text,'canonical_text_assets',(item,),(item,),{}),
    ):
        assert_native_relay(case,selected,(target,method,args,{},forwarded,keywords))
    for owner,names in ((sprite,('clean_sprite_assets','clean_sprite_material_policy_matches','clean_sprites_policy_complete')),
        (text,('canonical_text_assets','canonical_text_assets_complete'))):
        for name in names:
            args=(item,other) if name=='clean_sprite_material_policy_matches' else (item,)
            forwarded=args+(None,) if name.endswith('_complete') else args
            assert_native_relay(case,getattr(server,name),(owner,name,args,{},forwarded,{}))
            if name.endswith('_complete'):
                assets=[other]
                assert_native_relay(case,getattr(server,name),(owner,name,(item,),{'assets':assets},(item,assets),{}))
    for selected,name,args,forwarded in ((sprite._policy.expected(),'object_alpha_material_policy',(item,),(item,None)),
        (sprite._policy.normalize(),'normalize_object_alpha_material_policy',(item,),(item,))):
        sentinel=object()
        with patch.object(inspection._accessory_policy,name,return_value=sentinel) as callee:
            case.assertIs(selected(*args),sentinel);callee.assert_called_once_with(*forwarded)
            case.assertIs(callee.call_args.args[0],item)
    with patch.object(inspection,'_clean_sprite_metadata_complete_impl',return_value=other) as callee:
        case.assertIs(sprite._readiness.metadata()(item),other);callee.assert_called_once_with(item)
    assets=[other]
    with patch.object(legacy,'_text_accessory_confirm_detail_impl',return_value=other) as callee:
        case.assertIs(server.text_accessory_confirm_detail(item,assets,False,True),other)
        callee.assert_called_once_with(item,assets,False,True)
        case.assertIs(callee.call_args.args[0],item);case.assertIs(callee.call_args.args[1],assets)
    original=app.values.IMAGE_REFERENCE_SUFFIXES;case.assertIs(text._operations.suffixes(),original)
    try:
        object.__setattr__(app.values,'IMAGE_REFERENCE_SUFFIXES',other)
        case.assertIs(text._operations.suffixes(),other)
    finally:object.__setattr__(app.values,'IMAGE_REFERENCE_SUFFIXES',original)

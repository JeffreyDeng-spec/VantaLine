"""Finite rendering fixture ports; original pixels and RNG remain authoritative."""
from dataclasses import replace
from unittest.mock import patch

DIRECT=(('surface',{'background':'render_training_background','public_url':'public_output_url'}),('assets',{'document':'load_rectified_document_asset_with_metadata','generic':'load_preview_asset_with_metadata','sprites':'clean_sprite_assets','paste_document':'paste_rectified_document_asset','paste_object':'paste_physical_object_asset'}),('sizes',{'physical':'physical_render_size_px','sprite':'physical_render_size_for_sprite','visible':'visible_mask_size_px'}),('poses',{'available':'available_object_pose_families','choose':'choose_object_pose_family','policy':'object_render_pose_policy','position':'grid_position_for_center','source':'source_position_for_render_policy','reason':'pose_selection_reason'}),('layout',{'random_center':'random_center_inside_background','choose_center':'choose_object_center_inside_background','box':'placement_box_points','rectangle':'rotated_rect_tuple','polygon':'visible_polygon_from_mask','max_distance':'polygon_max_pair_distance_px'}))
GETTERS=(('assets',{'object_sprite':'load_object_preview_sprite','restore':'restore_object_sprite_source_orientation_for_render'}),('sizes',{'pose':'object_pose_render_size_hint','unified':'long_axis_unified_render_box'}),('poses',{'top_view':'pose_family_is_top_view'}),('layout',{'mask':'mask_from_polygon'}),('thresholds',{'min_visible_area':'DETECTION_MIN_VISIBLE_AREA_PX','max_occlusion':'DETECTION_MAX_OCCLUSION_FRACTION'}))


def bind_training_renderer(api,stack):
    owner=api._default_application.training_pipeline._training_preview_renderer
    stack.enter_context(patch.object(owner,'material',lambda item:api.accessory_material_type(item)))
    for attribute,mapping in DIRECT:
        stack.enter_context(patch.object(owner,attribute,replace(getattr(owner,attribute),**{field:(lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)) for field,name in mapping.items()})))
    for attribute,mapping in GETTERS:
        stack.enter_context(patch.object(owner,attribute,replace(getattr(owner,attribute),**{field:(lambda _name=name:getattr(api,_name)) for field,name in mapping.items()})))


def assert_default_training_renderer(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.training.preview_renderer import PreviewRenderer
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;inspection=app.inspection;owner=graph._training_preview_renderer;item,other,third,fourth,fifth,sixth,seventh=object(),object(),object(),object(),object(),object(),object()
    case.assertIs(type(owner),PreviewRenderer);case.assertIs(api._training_preview_renderer,owner);case.assertIs(owner.images,app.infrastructure._training_image_io);case.assertIs(owner.images.files,app.artifacts.files);case.assertIs(owner.images.files.runtime_provider,app.artifacts.files.runtime_provider)
    for selected,name in ((owner.thresholds.min_visible_area,'DETECTION_MIN_VISIBLE_AREA_PX'),(owner.thresholds.max_occlusion,'DETECTION_MAX_OCCLUSION_FRACTION')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)
    with patch.object(wiring._accessory_policy,'accessory_material_type',return_value=other) as receiver:case.assertIs(owner.material(item),other);receiver.assert_called_once_with(item)
    for selected,target,method,args,kw,expected,expected_kw in (
        (owner.surface.background,graph._training_background_renderer,'render_training_background',(item,other,third),{},(item,other,third),{}),
        (owner.surface.public_url,app.infrastructure._service_paths,'public_output_url',(item,),{},(item,),{}),
        (owner.assets.document,inspection._preview_asset_loader,'load_rectified_document_asset_with_metadata',(item,other),{},(item,other),{}),
        (owner.assets.generic,inspection._preview_asset_loader,'load_preview_asset_with_metadata',(item,),{},(item,),{}),
        (owner.assets.sprites,inspection._sprite_asset_catalog,'clean_sprite_assets',(item,),{},(item,),{}),
        (owner.assets.object_sprite(),inspection._preview_sprite_renderer,'load_object_preview_sprite',(item,other,third),{'pose_family':fourth,'source_position':fifth},(item,other,third,fourth,fifth),{}),
        (owner.assets.restore(),inspection._preview_sprite_renderer,'restore_object_sprite_source_orientation_for_render',(item,other,third),{'top_view_pose':fourth},(item,other,third),{'top_view_pose':fourth}),
        (owner.assets.paste_object,inspection._asset_compositor,'paste_physical_object_asset',(item,other,third,fourth,fifth,sixth,seventh),{'preserve_aspect_ratio':item},(item,other,third,fourth,fifth,sixth,seventh,item),{}),
        (owner.sizes.physical,inspection._reference_dimensions,'physical_render_size_px',(item,other),{},(item,other),{}),
        (owner.sizes.sprite,inspection._sprite_render_metadata,'sprite_render_size_px',(item,other,third),{},(item,third,other),{}),
        (owner.sizes.pose(),inspection._pose_candidate_policy,'object_pose_render_size_hint',(item,other),{},(item,other),{}),
        (owner.sizes.visible,inspection._sprite_geometry,'visible_mask_size_px',(item,),{},(item,),{}),
        (owner.poses.available,inspection._preview_pose_policy,'available_object_pose_families',(item,),{},(item,),{}),
        (owner.poses.choose,inspection._pose_candidate_policy,'choose_object_pose_family',(item,other),{},(item,other),{}),
        (owner.poses.policy,inspection._pose_grid_policy,'object_render_pose_policy',(item,other),{},(item,other),{}),
        (owner.poses.top_view(),inspection._sprite_footprint,'pose_family_is_top_view',(item,),{},(item,None),{}),
        (owner.poses.position,inspection._pose_grid_policy,'grid_position_for_center',(item,),{},(item,app.values.BACKGROUND_ROI_PX),{}),
        (owner.poses.source,inspection._pose_grid_policy,'source_position_for_render_policy',(item,other,third,fourth),{},(item,other,third,fourth),{}),
        (owner.poses.reason,inspection._pose_grid_policy,'pose_selection_reason',(item,other,third),{},(item,other,third),{}),
        (owner.layout.random_center,graph._preview_placement,'random_center_inside_background',(item,other,third),{},(item,other,third,app.values.BACKGROUND_ROI_PX),{}),
        (owner.layout.choose_center,graph._preview_placement,'choose_object_center_inside_background',(item,other,third,fourth),{},(item,other,third,fourth,app.values.BACKGROUND_ROI_PX),{}),
        (owner.layout.box,graph._preview_placement,'placement_box_points',(item,other,third),{},(item,other,third),{}),
        (owner.layout.polygon,graph._preview_masks,'visible_polygon_from_mask',(item,),{},(item,0.0035),{})):
        assert_native_relay(case,selected,(target,method,args,kw,expected,expected_kw))
    case.assertIs(owner.layout.mask(),wiring.mask_from_polygon)
    for selected,name,args in ((owner.assets.paste_document,'_paste_rectified_document_asset_impl',(item,other,third,fourth,fifth)),(owner.sizes.unified(),'_long_axis_unified_render_box_impl',(item,other,third,fourth)),(owner.layout.rectangle,'rotated_rect_tuple',(item,other,third)),(owner.layout.max_distance,'polygon_max_pair_distance_px',(item,))):
        with patch.object(wiring,name,return_value=other) as receiver:case.assertIs(selected(*args),other);receiver.assert_called_once_with(*args)

    assert_native_relay(case,owner.poses.top_view(),(inspection._sprite_footprint,'pose_family_is_top_view',(item,other),{},(item,other),{}))

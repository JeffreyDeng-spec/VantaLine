"""Finite native geometry graphs and real default getter witnesses."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest


def geometry_fixture(server):
    from local_inspection_service.accessories.crop_component_ports import CropGeometry
    from local_inspection_service.accessories.crop_selection import CropSelection
    from local_inspection_service.accessories.sprite_geometry_ports import SpriteTransformOperations, SpriteFootprintOperations
    from local_inspection_service.accessories.sprite_geometry import SpriteGeometry
    assert_default_geometry(server)
    names = ('cv2', 'np', 'normalize_angle_180', 'alpha_bbox', 'alpha_edge_max',
             'alpha_edge_stats', 'alpha_component_count', 'add_sprite_safety_margin',
             'trim_masked_asset', 'alpha_component_cutouts', 'alpha_component_summary')
    api = SimpleNamespace(**{name: getattr(server, name) for name in names})
    sprite = SpriteGeometry(SpriteTransformOperations(
        lambda: api.normalize_angle_180, lambda: api.masked_major_axis_angle,
        lambda: api.rotate_masked_asset, lambda: api.trim_masked_asset,
        lambda: api.add_sprite_safety_margin),
        SpriteFootprintOperations(lambda: api.alpha_bbox, lambda: api.visible_mask_size_px))
    for name in ('masked_major_axis_angle', 'rotate_masked_asset', 'normalize_sprite_upright',
                 'visible_mask_size_px', 'resize_masked_asset_to_visible_footprint'):
        setattr(api, name, getattr(sprite, name))
    crops = CropSelection(CropGeometry(lambda: api.alpha_bbox, lambda: api.trim_masked_asset))
    for name in ('filter_cutout_to_focus_cell', 'usable_object_cutout', 'cleanup_crop_alpha_components'):
        setattr(api, name, getattr(crops, name))
    return api


def assert_default_geometry(server):
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    from local_inspection_service.accessories.sprite_geometry import SpriteGeometry
    from local_inspection_service.accessories.crop_selection import CropSelection
    verify_actual_sources()
    case = unittest.TestCase()
    graph = server._default_application.inspection
    sprite, crops = graph._sprite_geometry, graph._crop_selection
    case.assertIs(server._sprite_geometry, sprite)
    case.assertIs(server._crop_selection, crops)
    case.assertIs(type(sprite), SpriteGeometry)
    case.assertIs(type(crops), CropSelection)
    asset, mask = object(), object()
    for selected, method, args in ((sprite._transform.axis(), 'masked_major_axis_angle', (mask,)),
                                    (sprite._transform.rotate(), 'rotate_masked_asset', (asset, mask, 12.5)),
                                    (sprite._footprint.visible(), 'visible_mask_size_px', (mask,))):
        assert_native_relay(case, selected, (sprite, method, args, {}, args, {}))
    pure = ((sprite._transform.normalize(), '_normalize_angle_180_impl', (12.5,), (12.5,)),
            (sprite._transform.trim(), '_trim_masked_asset_impl', (asset, mask), (asset, mask, 4)),
            (sprite._transform.margin(), '_add_sprite_safety_margin_impl', (asset, mask), (asset, mask, 10)),
            (sprite._footprint.bounds(), '_alpha_bbox_impl', (mask,), (mask, 8)),
            (crops._geometry.bounds(), '_alpha_bbox_impl', (mask,), (mask, 8)),
            (crops._geometry.trim(), '_trim_masked_asset_impl', (asset, mask), (asset, mask, 4)))
    for selected, name, args, forwarded in pure:
        sentinel = object()
        with patch.object(inspection, name, return_value=sentinel) as callee:
            case.assertIs(selected(*args), sentinel)
            callee.assert_called_once_with(*forwarded)
            for actual, expected in zip(callee.call_args.args, forwarded):
                if type(expected) is object:
                    case.assertIs(actual, expected)


def material_alpha_fixture(server):
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.runtime.wiring import inspection
    from local_inspection_service.accessories.material_alpha import MaterialAlphaProcessor
    from local_inspection_service.accessories.material_alpha_ports import MaterialAlphaOperations
    verify_actual_sources()
    case = unittest.TestCase()
    graph = server._default_application.inspection
    owner = graph._material_alpha
    case.assertIs(server._material_alpha, owner)
    case.assertIs(type(owner), MaterialAlphaProcessor)
    asset, mask, item = object(), object(), {}
    for selected, target, name, args in (
            (owner._operations.policy(), inspection._accessory_policy, 'object_alpha_material_policy', (item, None)),
            (owner._operations.transparent(), inspection, '_transparent_object_alpha_impl', (asset, mask)),
            (owner._operations.solid(), inspection, '_solid_object_alpha_impl', (mask,))):
        sentinel = object()
        with patch.object(target, name, return_value=sentinel) as callee:
            case.assertIs(selected(*args), sentinel)
            callee.assert_called_once_with(*args)
            for actual, supplied in zip(callee.call_args.args, args):
                case.assertIs(actual, supplied)
    names = ('cv2', 'np', 'object_alpha_material_policy', 'transparent_object_alpha', 'solid_object_alpha')
    api = SimpleNamespace(**{name: getattr(server, name) for name in names})
    processor = MaterialAlphaProcessor(MaterialAlphaOperations(
        lambda: api.object_alpha_material_policy, lambda: api.transparent_object_alpha,
        lambda: api.solid_object_alpha))
    api.material_aware_object_alpha = processor.material_aware_object_alpha
    return api

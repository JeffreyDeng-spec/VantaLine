"""Native metadata graphs with finite synthetic input and default relay checks."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest


def metadata_fixture(server):
    from local_inspection_service.accessories import sprite_metadata_ports as ports
    from local_inspection_service.accessories.sprite_footprint import SpriteFootprintMetadata
    from local_inspection_service.accessories.sprite_scale import SpriteScaleMetadata
    from local_inspection_service.accessories.sprite_render_metadata import SpriteRenderMetadata
    from local_inspection_service.storage.artifacts.files import BusinessFiles
    assert_default_metadata(server)
    names = ('cv2', 'np', 'Path', 'canonical_sprite_canvas_size_px', 'canonical_pose_family_name', 'source_object_long_short_metadata',
             'source_long_short_oriented_px', 'physical_render_size_px', 'alpha_bbox',
             'DEFAULT_OBJECT_SIZE_MM', 'SOURCE_ASPECT_ELONGATED_MIN_RATIO', 'MM_TO_PREVIEW_PX',
             'UPRIGHT_SCALE_CORRECTION_MIN_RATIO', 'UPRIGHT_SCALE_CORRECTION_MAX_RATIO',
             'UPRIGHT_SCALE_VISUAL_ADJUSTMENT')
    api = SimpleNamespace(**{name: getattr(server, name) for name in names})
    footprint = SpriteFootprintMetadata(ports.SpritePhysicalPolicy(
        lambda: api.DEFAULT_OBJECT_SIZE_MM, lambda: api.SOURCE_ASPECT_ELONGATED_MIN_RATIO,
        lambda: api.MM_TO_PREVIEW_PX), ports.SpriteFootprintMetadataOperations(
        lambda: api.canonical_pose_family_name, lambda: api.object_physical_size_mm,
        lambda: api.source_object_long_short_metadata, lambda: api.oriented_long_short_pair_for_source,
        lambda: api.pose_family_is_top_view))
    scale = SpriteScaleMetadata(ports.SpriteScalePolicy(
        lambda: api.UPRIGHT_SCALE_CORRECTION_MIN_RATIO, lambda: api.UPRIGHT_SCALE_CORRECTION_MAX_RATIO,
        lambda: api.UPRIGHT_SCALE_VISUAL_ADJUSTMENT), ports.SpriteScaleOperations(
        lambda: api.canonical_pose_family_name, lambda: api.median_source_major_axis_px,
        lambda: api.object_physical_size_mm, lambda: api.upright_scale_correction_for_assets))
    render = SpriteRenderMetadata(ports.SpriteRenderOperations(
        lambda: api.alpha_bbox, lambda: api.canonical_pose_family_name, lambda: api.asset_visible_shape_px,
        lambda: api.source_long_short_oriented_px, lambda: api.pose_render_footprint_metadata,
        lambda: api.physical_render_size_px), ports.SpriteImageReads(
        lambda: Path, lambda: api.cv2.imread, lambda: api.cv2.IMREAD_UNCHANGED),
        files=BusinessFiles(lambda: None))
    for owner, names in (
            (footprint, ('object_physical_size_mm', 'pose_family_is_top_view',
                         'oriented_long_short_pair_for_source', 'pose_render_footprint_metadata')),
            (scale, ('median_source_major_axis_px', 'upright_scale_correction_for_assets',
                     'apply_upright_scale_correction_metadata')),
            (render, ('asset_visible_shape_px', 'sprite_render_size_px',
                      'apply_laying_standard_render_size_hints'))):
        for name in names:
            setattr(api, name, getattr(owner, name))
    return api


def assert_default_metadata(server):
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    from local_inspection_service.accessories.sprite_footprint import SpriteFootprintMetadata
    from local_inspection_service.accessories.sprite_scale import SpriteScaleMetadata
    from local_inspection_service.accessories.sprite_render_metadata import SpriteRenderMetadata
    verify_actual_sources()
    case = unittest.TestCase()
    graph = server._default_application.inspection
    footprint, scale, render = graph._sprite_footprint, graph._sprite_scale, graph._sprite_render_metadata
    for name, expected_type in (('_sprite_footprint', SpriteFootprintMetadata),
                               ('_sprite_scale', SpriteScaleMetadata),
                               ('_sprite_render_metadata', SpriteRenderMetadata)):
        case.assertIs(getattr(server, name), getattr(graph, name))
        case.assertIs(type(getattr(graph, name)), expected_type)
    item, assets, size = {}, [], [12, 8]
    for owner, field, expected in (
            (footprint._policy, 'defaults', 'DEFAULT_OBJECT_SIZE_MM'),
            (footprint._policy, 'elongated_min', 'SOURCE_ASPECT_ELONGATED_MIN_RATIO'),
            (footprint._policy, 'pixels_per_mm', 'MM_TO_PREVIEW_PX'),
            (scale._policy, 'minimum', 'UPRIGHT_SCALE_CORRECTION_MIN_RATIO'),
            (scale._policy, 'maximum', 'UPRIGHT_SCALE_CORRECTION_MAX_RATIO'),
            (scale._policy, 'visual', 'UPRIGHT_SCALE_VISUAL_ADJUSTMENT')):
        case.assertIs(getattr(owner, field)(), getattr(server._default_application.values, expected))
    native = (
        (footprint._operations.physical(), footprint, 'object_physical_size_mm', (item,)),
        (footprint._operations.orient(), footprint, 'oriented_long_short_pair_for_source', (size, 12.0, 8.0)),
        (footprint._operations.top_view(), footprint, 'pose_family_is_top_view', ('lying', size)),
        (scale._operations.median(), scale, 'median_source_major_axis_px', (assets, 'lying')),
        (scale._operations.physical(), footprint, 'object_physical_size_mm', (item,)),
        (scale._operations.correction(), scale, 'upright_scale_correction_for_assets', (assets, item)),
        (render._operations.visible(), render, 'asset_visible_shape_px', (item,)),
        (render._operations.footprint(), footprint, 'pose_render_footprint_metadata', ('lying', size, item)),
        (render._operations.physical(), graph._reference_dimensions, 'physical_render_size_px', (item, 'object')))
    for selected, owner, method, args in native:
        assert_native_relay(case, selected, (owner, method, args, {}, args, {}))
    pure = (
        (footprint._operations.family(), '_canonical_pose_family_name_impl', ('lying',), ('lying',)),
        (footprint._operations.source(), '_source_object_long_short_metadata_impl', (size,), (size,)),
        (scale._operations.family(), '_canonical_pose_family_name_impl', ('lying',), ('lying',)),
        (render._operations.bounds(), '_alpha_bbox_impl', (size,), (size, 8)),
        (render._operations.family(), '_canonical_pose_family_name_impl', ('lying',), ('lying',)),
        (render._operations.orient(), '_source_long_short_oriented_px_impl', (12, 8, 'width'), (12, 8, 'width')))
    for selected, name, args, forwarded in pure:
        sentinel = object()
        with patch.object(inspection, name, return_value=sentinel) as callee:
            case.assertIs(selected(*args), sentinel)
            callee.assert_called_once_with(*forwarded)
            for actual, expected in zip(callee.call_args.args, forwarded):
                if isinstance(expected, list):
                    case.assertIs(actual, expected)
    case.assertIs(render.files, server._default_application.artifacts.files)
    case.assertIs(render._images.path(), Path)
    case.assertIs(render._images.decode(), server.cv2.imread)
    case.assertEqual(render._images.unchanged_mode(), server.cv2.IMREAD_UNCHANGED)

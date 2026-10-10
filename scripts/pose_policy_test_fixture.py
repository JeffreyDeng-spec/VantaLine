"""Finite native pose-policy graphs and actual application relay witnesses."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest


def pose_fixture(server):
    from local_inspection_service.accessories import pose_policy_ports as ports
    from local_inspection_service.accessories.pose_policy import PoseGridPolicy, PoseCandidatePolicy, PreviewPosePolicy
    assert_default_pose(server)
    names = ('POSE_COLLECTION_GRID_POSITIONS', 'UPRIGHT_TOP_VIEW_SOURCE_POSITIONS',
             'BACKGROUND_ROI_PX', 'HTTPException', 'pose_collection_regions',
             'normalize_cardinal_rotation_degrees', 'source_object_major_axis_px',
             'canonical_pose_family_name', 'sprite_pose_family', 'clean_sprite_assets',
             'pose_render_footprint_metadata', 'pose_family_is_top_view')
    api = SimpleNamespace(**{name: getattr(server, name) for name in names})
    grid = PoseGridPolicy(ports.PoseLayoutValues(
        lambda: api.POSE_COLLECTION_GRID_POSITIONS, lambda: api.UPRIGHT_TOP_VIEW_SOURCE_POSITIONS),
        ports.PoseRotationOperations(lambda: api.normalize_cardinal_rotation_degrees,
                                     lambda: api.grid_row_col, lambda: api.grid_position_from_row_col),
        ports.PoseRenderOperations(lambda: api.pose_family_is_top_view,
                                   lambda: api.source_position_for_rotated_target))
    candidate = PoseCandidatePolicy(ports.PoseAssetOperations(
        lambda: api.canonical_pose_family_name, lambda: api.clean_sprite_assets,
        lambda: api.pose_render_footprint_metadata), ports.PoseCandidateOperations(
        lambda: api.source_object_major_axis_px, lambda: api.sprite_pose_family))
    preview = PreviewPosePolicy(ports.PreviewPoseAssetOperations(
        lambda: api.clean_sprite_assets, lambda: api.accessory_material_type,
        lambda: api.sprite_pose_family), ports.PreviewPoseSelectionOperations(
        lambda: api.available_object_pose_families, lambda: api.normalize_preview_pose_family_policy,
        lambda: api.preview_pose_families_for_policy, lambda: api.canonical_pose_family_name),
        ports.PreviewPoseErrors(lambda: api.HTTPException))
    api.accessory_material_type = server.accessory_material_type
    for owner, names in (
            (grid, ('grid_row_col', 'grid_position_from_row_col', 'source_position_for_rotated_target',
                    'source_position_for_render_policy', 'object_render_pose_policy', 'pose_selection_reason')),
            (candidate, ('object_pose_render_size_hint', 'filter_complete_pose_candidates', 'choose_object_pose_family')),
            (preview, ('available_object_pose_families', 'normalize_preview_pose_family_policy',
                       'preview_pose_family_for_policy', 'preview_pose_families_for_policy',
                       'preview_pose_family_sequence', 'preview_pose_family_sequence_label'))):
        for name in names:
            setattr(api, name, getattr(owner, name))
    captured_roi = server.grid_position_for_center.__defaults__[0]

    def grid_position_for_center(center, roi=captured_roi):
        return grid.grid_position_for_center(center, roi)

    api.grid_position_for_center = grid_position_for_center
    return api


def assert_default_pose(server):
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    from local_inspection_service.accessories.pose_policy import PoseGridPolicy, PoseCandidatePolicy, PreviewPosePolicy
    verify_actual_sources()
    case = unittest.TestCase()
    graph = server._default_application.inspection
    grid, candidate, preview = graph._pose_grid_policy, graph._pose_candidate_policy, graph._preview_pose_policy
    for name, cls in (('_pose_grid_policy', PoseGridPolicy), ('_pose_candidate_policy', PoseCandidatePolicy),
                      ('_preview_pose_policy', PreviewPosePolicy)):
        case.assertIs(getattr(server, name), getattr(graph, name))
        case.assertIs(type(getattr(graph, name)), cls)
    case.assertIs(grid._layout.grid(), server._default_application.values.POSE_COLLECTION_GRID_POSITIONS)
    case.assertIs(grid._layout.upright(), server._default_application.values.UPRIGHT_TOP_VIEW_SOURCE_POSITIONS)
    case.assertIs(preview._errors.make(), inspection.HTTPException)
    item, size, assets = {}, [12, 8], []
    native = (
        (grid._rotation.row_col(), grid, 'grid_row_col', ('p0',), ('p0',)),
        (grid._rotation.position(), grid, 'grid_position_from_row_col', (1, 2), (1, 2)),
        (grid._render.is_top(), graph._sprite_footprint, 'pose_family_is_top_view', ('lying',), ('lying', None)),
        (grid._render.source(), grid, 'source_position_for_rotated_target', ('p0', 90.0), ('p0', 90.0)),
        (candidate._assets.assets(), graph._sprite_asset_catalog, 'clean_sprite_assets', (item,), (item,)),
        (candidate._assets.footprint(), graph._sprite_footprint, 'pose_render_footprint_metadata', ('lying', size, item), ('lying', size, item)),
        (preview._assets.assets(), graph._sprite_asset_catalog, 'clean_sprite_assets', (item,), (item,)),
        (preview._selection.available(), preview, 'available_object_pose_families', (item,), (item,)),
        (preview._selection.normalize(), preview, 'normalize_preview_pose_family_policy', ('auto',), ('auto',)),
        (preview._selection.many(), preview, 'preview_pose_families_for_policy', (assets, 'auto'), (assets, 'auto')))
    for selected, owner, method, args, forwarded in native:
        assert_native_relay(case, selected, (owner, method, args, {}, forwarded, {}))
    pure = (
        (grid._rotation.normalize(), '_normalize_cardinal_rotation_degrees_impl', (90.0,)),
        (candidate._assets.canonical(), '_canonical_pose_family_name_impl', ('lying',)),
        (candidate._candidates.major_axis(), '_source_object_major_axis_px_impl', (item,)),
        (candidate._candidates.family(), '_sprite_pose_family_impl', (item,)),
        (preview._assets.sprite(), '_sprite_pose_family_impl', (item,)),
        (preview._selection.canonical(), '_canonical_pose_family_name_impl', ('lying',)))
    for selected, name, args in pure:
        sentinel = object()
        with patch.object(inspection, name, return_value=sentinel) as callee:
            case.assertIs(selected(*args), sentinel)
            callee.assert_called_once_with(*args)
            for actual, supplied in zip(callee.call_args.args, args):
                if isinstance(supplied, dict):
                    case.assertIs(actual, supplied)
    sentinel = object()
    with patch.object(inspection._accessory_policy, 'accessory_material_type', return_value=sentinel) as material:
        case.assertIs(preview._assets.material()(item), sentinel)
        material.assert_called_once_with(item)
        case.assertIs(material.call_args.args[0], item)

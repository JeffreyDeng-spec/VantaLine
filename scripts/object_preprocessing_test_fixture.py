"""Native preprocessing graph with explicit, operation-time test suppliers."""
from types import SimpleNamespace
from local_inspection_service.accessories import object_preprocessing_ports as ports
from local_inspection_service.accessories.object_preprocessing import ObjectSpritePreprocessor
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.images import ImageFiles


def object_preprocessing_fixture(server, groups):
    import unittest
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    from unittest.mock import patch
    verify_actual_sources()
    case = unittest.TestCase()
    application = server._default_application
    actual = application.inspection._object_sprite_preprocessor
    case.assertIs(server._object_sprite_preprocessor, actual)
    case.assertIs(type(actual), ObjectSpritePreprocessor)
    case.assertIs(actual.files, application.artifacts.files)
    case.assertIs(actual.images, application.infrastructure._accessory_image_io)
    names = {source.split('.')[0] for _, _, bindings in groups for source in bindings.values()}
    api = SimpleNamespace(**{name: getattr(server, name) for name in names}, cv2=server.cv2)
    capabilities = []
    item, other, image, mask, rng = object(), object(), object(), object(), object()
    native = {
        'clean_sprite_assets': ('_sprite_asset_catalog', (item,), (item,)),
        'clean_sprites_policy_complete': ('_sprite_asset_catalog', (item, other), (item, other)),
        'accessory_image_paths': ('_reference_evidence', (item,), (item,)),
        'ai_background_cutout_with_bbox': ('_background_cutouts', (image,), (image,)),
        'ai_background_cutout': ('_cutout_selection', (image,), (image,)),
        'green_screen_object_cutout_with_bbox': ('_cutout_selection', (image, rng), (image, rng)),
        'object_cutout_from_image': ('_cutout_selection', (image, rng), (image, rng)),
        'usable_object_cutout': ('_crop_selection', (item, other), (item, other)),
        'filter_cutout_to_focus_cell': ('_crop_selection', (image, mask, other), (image, mask, other)),
        'cleanup_crop_alpha_components': ('_crop_selection', (image, mask), (image, mask, None, 35)),
        'pose_render_footprint_metadata': ('_sprite_footprint', ('lying', other, item), ('lying', other, item)),
        'pose_family_is_top_view': ('_sprite_footprint', ('lying', other), ('lying', other)),
        'apply_laying_standard_render_size_hints': ('_sprite_render_metadata', (other,), (other,)),
        'normalize_sprite_family_canvases': ('_sprite_canvas_normalizer', (other,), (other,)),
        'apply_upright_scale_correction_metadata': ('_sprite_scale', (other, item), (other, item)),
        'write_clean_sprite': ('_sprite_artifact_writer', (item, image, mask, other), (item, image, mask, other)),
    }
    pure = {
        'candidate_image_jobs': ('_image_metadata_jobs', (item,), (item,)),
        'deterministic_task_id': ('_image_metadata_task_id', (item, other), (item, other)),
        'pose_collection_regions': ('_pose_collection_regions_impl', (image,), (image, True)),
        'alpha_bbox': ('_alpha_bbox_impl', (mask,), (mask, 8)),
        'alpha_component_cutouts': ('_alpha_component_cutouts_impl', (image,), (image,)),
        'alpha_component_summary': ('_alpha_component_summary_impl', (mask,), (mask, 28)),
    }
    for name, kind, bindings in groups:
        default = getattr(actual, '_' + name)
        case.assertIs(type(default), getattr(ports, kind))
        getters = {}
        for field, source in bindings.items():
            selected = getattr(default, field)()
            if source in ('NORMALIZED_DIR', 'POSE_COLLECTION_GRID_POSITIONS'):
                case.assertIs(selected, getattr(application.values, source))
            elif source in native:
                attribute, args, forwarded = native[source]
                assert_native_relay(case, selected, (getattr(application.inspection, attribute), source, args, {}, forwarded, {}))
            elif source in pure:
                attribute, args, forwarded = pure[source]
                sentinel = object()
                with patch.object(inspection, attribute, return_value=sentinel) as callee:
                    case.assertIs(selected(*args), sentinel)
                    callee.assert_called_once_with(*forwarded)
                    for observed, expected in zip(callee.call_args.args, forwarded):
                        if type(expected) is object:
                            case.assertIs(observed, expected)
            elif source in ('accessory_material_type', 'object_alpha_material_policy', 'accessory_uid'):
                forwarded = (item, None) if source == 'object_alpha_material_policy' else (item,)
                sentinel = object()
                with patch.object(inspection._accessory_policy, source, return_value=sentinel) as callee:
                    case.assertIs(selected(item), sentinel)
                    callee.assert_called_once_with(*forwarded)
                    case.assertIs(callee.call_args.args[0], item)
            else:
                case.assertIn(source, ('time.time', 'np.random.default_rng'))
                original = inspection
                for part in source.split('.'):
                    original = getattr(original, part)
                case.assertIs(selected, original)
            def getter(source=source):
                value = api
                for part in source.split('.'):
                    value = getattr(value, part)
                return value
            getters[field] = getter
        capabilities.append(getattr(ports, kind)(**getters))
    files = BusinessFiles(lambda: None)
    graph = ObjectSpritePreprocessor(*capabilities, files=files,
                                   images=ImageFiles(lambda: api.cv2, files=files))
    api.preprocess_object_clean_sprites = graph.preprocess_object_clean_sprites
    return api

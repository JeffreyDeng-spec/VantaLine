"""Default accessory relay witnesses, run before replacing HTTP test inputs."""
from pathlib import Path
import unittest
from unittest.mock import patch, create_autospec


def assert_default_accessory_dependencies(server):
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    verify_actual_sources()
    from local_inspection_service.runtime.wiring import inspection
    case = unittest.TestCase()
    graph = server._default_application.inspection
    # Compatibility aliases must refer to the application that owns HTTP routes.
    for name in ('_accessory_files', '_accessory_routing', '_accessory_creation',
                 '_accessory_confirmation', '_candidate_factory', '_accessory_refresh',
                 '_accessory_removal', '_candidate_repository', '_accessory_preparation',
                 '_accessory_profile_generation', '_accessory_profile_projection',
                 '_accessory_dimensions', '_accessory_reference_media', '_text_asset_catalog',
                 '_pose_collection_jobs', '_image_worker_runtime', '_detection_task_requests',
                 '_profile_cache_store', '_candidate_store_lock'):
        case.assertIs(getattr(server, name), getattr(graph, name), name)
    item, config, user, assets = {}, {}, {}, []

    def witness(selected, owner, method, args, kwargs=None, forwarded=None, forwarded_kwargs=None):
        kwargs = {} if kwargs is None else kwargs
        assert_native_relay(case, selected, (owner, method, args, kwargs,
                           args if forwarded is None else forwarded,
                           kwargs if forwarded_kwargs is None else forwarded_kwargs))

    files, refresh = graph._accessory_files, graph._accessory_refresh
    creation, confirmation = graph._accessory_creation, graph._accessory_confirmation
    factory, routing = graph._candidate_factory, graph._accessory_routing
    witness(files.profiles.refresh, graph._accessory_refresh,
            'refresh_accessory_assets_after_source_change', (item,), {'force_profile': False})
    for port in (files.profiles, refresh.profiles):
        witness(port.fallback, graph._accessory_profile_projection,
                'fallback_accessory_ai_profile', (item,), forwarded=(item, None))
        witness(port.generate, graph._accessory_profile_generation,
                'generate_accessory_ai_profile', (item,), {'allow_provider': False})
    witness(files.profiles.save_cache, graph._profile_cache_store, 'save_ai_profile_cache', (config,))
    witness(graph._accessory_removal.store.save_app_config,
            server._default_application.infrastructure._app_configuration.store, 'save_app_config', (config,))
    witness(factory.media.default_size, graph._accessory_dimensions, 'physical_size_payload',
            ('object',), forwarded=('object', 'A4', None, None, None, None, None))
    source, output, thumbnail = Path('source.mp4'), Path('output'), Path('thumbnail.png')
    witness(graph._accessory_preparation.media.extract_frames,
            graph._accessory_reference_media, 'extract_video_reference_frames',
            (source, output),
            forwarded=(source, output, server.MAX_VIDEO_REFERENCE_FRAMES))
    witness(factory.media.thumbnail, graph._accessory_reference_media, 'write_thumbnail',
            (item, thumbnail, 12.5), forwarded=(item, thumbnail, 12.5, 360))
    for port in (creation.profiles, confirmation.profiles, factory.preparation, routing.actions):
        witness(port.ensure_profile, graph._accessory_profile_generation, 'ensure_accessory_ai_profile',
                (item,), forwarded_kwargs={'force': False, 'allow_provider': True})
    for port in (creation.profiles, confirmation.profiles, factory.preparation):
        witness(port.ensure_reference, graph._accessory_preparation,
                'ensure_default_ai_profile_reference', (item,))
    for selected in (creation.profiles.ensure_pose_jobs, confirmation.jobs.ensure_pose,
                     factory.preparation.ensure_pose_jobs):
        witness(selected, graph._pose_collection_jobs, 'ensure_pose_collection_image_jobs', (item,))
    for selected in (creation.candidates.save, confirmation.store.save_candidate, factory.storage.save):
        path = Path('candidate.json')
        witness(selected, graph._candidate_repository, 'save_accessory_candidate', (path, item))
    witness(confirmation.media.complete, graph._text_asset_catalog,
            'canonical_text_assets_complete', (item, assets))
    for port in (creation.media, confirmation.media, refresh.preparation):
        witness(port.normalize, graph._accessory_preparation, 'normalize_accessory_assets', (item,))
    for port in (creation.media, confirmation.media, factory.preparation, refresh.preparation):
        sentinel = object()
        with patch.object(inspection, '_preparation_defer', return_value=sentinel) as deferred:
            case.assertIs(port.defer(item), sentinel)
            deferred.assert_called_once_with(item)
            case.assertIs(deferred.call_args.args[0], item)
    captured_relay(case, routing.actions.upsert_task, 'upsert_dashboard_ai_task',
                   graph._detection_task_requests, 'upsert_dashboard_ai_task', ('part', config))
    for port in (creation.pipeline, confirmation.pipeline):
        witness(port.payload, server._default_application.training_pipeline._pipeline_candidate_flow,
                'pipeline_accessories_payload', (config, user), forwarded=(config, user, None))
    for port in (creation.profiles, confirmation.jobs):
        captured_relay(case, port.start_worker, 'start_image_worker', graph._image_worker_runtime, 'start', ())
    for selected in (confirmation.store.lock, graph._candidate_repository.dependencies.lock):
        case.assertIs(selected(), graph._candidate_store_lock)
    witness(graph._accessory_removal.access.current_user,
            server._default_application.infrastructure._access_control.identity, 'get', ())
    with patch.object(inspection, '_image_metadata_jobs', return_value=[{'status': 'running'}]) as jobs:
        case.assertTrue(creation.profiles.has_active_jobs(item))
        jobs.assert_called_once_with(item)
        case.assertIs(jobs.call_args.args[0], item)


def captured_relay(case, selected, name, owner, method, arguments):
    """Witness two intentionally captured methods without starting work.

    Only these literal assembly cells are substituted, after verifying the exact
    receiver and native method. Restoration includes assertion/dispatch errors.
    """
    case.assertIn(name, {'start_image_worker', 'upsert_dashboard_ai_task'})
    cells = dict(zip(selected.__code__.co_freevars, selected.__closure__ or ()))
    case.assertIn(name, cells)
    cell = cells[name]
    original = cell.cell_contents
    case.assertIs(original.__self__, owner)
    case.assertIs(original.__func__, getattr(type(owner), method))
    sentinel = object()
    callee = create_autospec(original, return_value=sentinel)
    try:
        cell.cell_contents = callee
        case.assertIs(selected(*arguments), sentinel)
        callee.assert_called_once_with(*arguments)
        for received, supplied in zip(callee.call_args.args, arguments):
            case.assertIs(received, supplied)
    finally:
        cell.cell_contents = original
    case.assertIs(cell.cell_contents, original)

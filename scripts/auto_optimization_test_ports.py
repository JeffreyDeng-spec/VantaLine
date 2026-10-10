"""Synthetic capability injection shared by auto-optimization contracts."""
from local_inspection_service.training.auto_optimization_dataset_ports import DatasetConfiguration, DatasetLayout, DatasetPublication
from local_inspection_service.training.auto_optimization_initialization_ports import AutoOptimizationAdvisorPorts, AutoOptimizationTaskInitializationPorts
from local_inspection_service.training.auto_optimization_label_generation_ports import LabelGenerationArtifacts, LabelGenerationModels, LabelGenerationPolicy
from local_inspection_service.training.auto_optimization_label_processing_ports import ProcessingArtifacts, ProcessingExecution
from local_inspection_service.training.auto_optimization_mask_ports import AutoOptimizationMaskPromptPorts, AutoOptimizationMaskVisualPorts
from local_inspection_service.training.auto_optimization_mask_verification_ports import AutoOptimizationMaskVerificationPorts
from local_inspection_service.training.auto_optimization_readiness_ports import AutoOptimizationReadinessPorts
from local_inspection_service.training.auto_optimization_rendering_ports import SyntheticGeometry, SyntheticPublication
from local_inspection_service.training.auto_optimization_requests_ports import RequestAccess, RequestActions
from local_inspection_service.training.auto_optimization_shadow_evaluation_ports import ShadowObservation, ShadowPromotion
from local_inspection_service.training.auto_optimization_sprites_ports import SpriteFiles, SpriteGeometry
from local_inspection_service.training.auto_optimization_state_ports import AutoOptimizationStatePolicy, AutoOptimizationStateStorage
from local_inspection_service.training.auto_optimization_status_ports import AutoOptimizationStatusPolicy, AutoOptimizationStatusState
from local_inspection_service.training.auto_optimization_synthetic_batch_ports import SyntheticBatchConfiguration, SyntheticBatchPublication
from local_inspection_service.training.auto_optimization_training_scheduling_ports import SchedulingSubmission

EXECUTION_OWNED_CAPABILITIES = {
    'AutoOptimizationAdvisorPorts': frozenset(('clamp_auto_optimize_initialization_recommendation',)),
    'AutoOptimizationMaskPromptPorts': frozenset(('auto_optimize_mask_owner_user', 'auto_optimize_mask_target_payload')),
    'AutoOptimizationMaskVerificationPorts': frozenset(('auto_optimize_mask_verifier_crop', 'auto_optimize_mask_verifier_overlay', 'clamp_unit_score')),
    'AutoOptimizationMaskVisualPorts': frozenset(('auto_optimize_text_mask_requires_document_gate',)),
    'AutoOptimizationTaskInitializationPorts': frozenset(('agent_auto_optimize_initialization_recommendation', 'auto_optimize_complexity_rule_recommendation', 'load_auto_optimize_state', 'save_auto_optimize_state', 'start_auto_optimize_label_worker')),
    'DatasetSources': frozenset(('auto_optimize_bbox_training_entries', 'auto_optimize_generate_synthetic_batch_for_sample')),
    'LabelGenerationArtifacts': frozenset(('auto_optimize_write_sprite_artifact',)),
    'LabelGenerationModels': frozenset(('auto_optimize_generate_label_for_candidate', 'verify_auto_optimize_mask_sample')),
    'LabelGenerationPolicy': frozenset(('auto_optimize_accessory_lookup_for_sample', 'auto_optimize_mask_target_profile', 'auto_optimize_multicolor_mask_prompt', 'decode_multicolor_mask', 'draw_auto_optimize_review_overlay', 'validate_auto_optimize_text_mask_region')),
    'ProcessingArtifacts': frozenset(('auto_optimize_generate_labels_for_sample', 'auto_optimize_generate_synthetic_batch_for_sample')),
    'ProcessingExecution': frozenset(('auto_optimize_process_label_sample',)),
    'ProcessingState': frozenset(('auto_optimize_completed_model_id', 'auto_optimize_label_worker', 'auto_optimize_stop_capture_for_model_locked', 'load_auto_optimize_state', 'maybe_start_auto_optimize_training_locked', 'save_auto_optimize_state')),
    'RequestActions': frozenset(('auto_optimize_bbox_training_entries', 'start_auto_optimize_training_check_worker')),
    'RequestState': frozenset(('auto_optimize_update_settings', 'load_auto_optimize_state', 'public_auto_optimize_state', 'save_auto_optimize_state')),
    'SchedulingPolicy': frozenset(('auto_optimize_completed_model_id', 'auto_optimize_stop_capture_for_model_locked')),
    'SchedulingState': frozenset(('auto_optimize_training_check_worker', 'load_auto_optimize_state', 'maybe_start_auto_optimize_training_locked', 'save_auto_optimize_state')),
    'SchedulingSubmission': frozenset(('build_auto_optimize_dataset',)),
    'SpriteFiles': frozenset(('auto_optimize_resolve_artifact_path', 'auto_optimize_write_sprite_artifact')),
    'SpriteGeometry': frozenset(('auto_optimize_load_sprite', 'auto_optimize_source_to_canvas_scale', 'auto_optimize_sprite_records_for_sample', 'auto_optimize_sprite_visible_size')),
    'SyntheticBatchPublication': frozenset(('auto_optimize_render_synthetic_sample',)),
    'SyntheticBatchSprites': frozenset(('auto_optimize_backfill_missing_sprites_for_sample', 'auto_optimize_canonical_sprite_sizes', 'auto_optimize_sprite_records_for_sample')),
    'SyntheticGeometry': frozenset(('auto_optimize_load_sprite', 'auto_optimize_sprite_target_size')),
}

SETTINGS_CAPABILITIES = frozenset(('auto_optimize_negative_samples_per_real_image', 'auto_optimize_positive_derivatives_per_real_image', 'auto_optimize_samples_per_real_image', 'auto_optimize_training_parameters', 'auto_optimize_training_requirements', 'default_auto_optimize_settings'))


def test_capability(bindings, name):
    # Stable production callables are replaced here at their actual test port.
    # Mutable fixtures retain their original per-test failure/order probes.
    if name in SETTINGS_CAPABILITIES:
        return lambda *args, **kwargs: bindings[name](*args, **kwargs)
    return lambda: bindings[name]


def assert_capability_owner(test, port, name, server):
    actual = getattr(port, name)
    if name in SETTINGS_CAPABILITIES:
        expected = getattr(server._auto_optimization_settings, name)
        test.assertIs(actual.__self__, server._auto_optimization_settings)
        test.assertIs(actual.__func__, expected.__func__)
    else:
        execution = server._auto_optimization_execution
        expected_execution = EXECUTION_OWNED_CAPABILITIES.get(type(port).__name__, frozenset())
        if name in expected_execution:
            components = ('initialization', 'mask_prompts', 'mask_visuals', 'mask_verification', 'sprite_publication', 'label_generation', 'label_processing', 'training_scheduling', 'sprites', 'rendering', 'synthetic_batch', 'dataset', 'requests')
            test.assertTrue(any(port is candidate for component in components for candidate in vars(getattr(execution, component)).values()), 'capability must belong to this execution graph')
            selected = actual()
            if name in ('auto_optimize_label_worker', 'auto_optimize_training_check_worker'):
                pinned = execution.pinned_label_worker if name == 'auto_optimize_label_worker' else execution.pinned_check_worker
                test.assertIs(selected, pinned)
                test.assertIs(selected.__wrapped__.__self__, execution)
                test.assertIs(selected.__wrapped__.__func__, getattr(type(execution), name))
            else:
                test.assertIs(selected.__self__, execution)
                test.assertIs(selected.__func__, getattr(type(execution), name))
            return
        core = server._auto_optimization_core
        workflows = getattr(server, '_auto_optimization_workflows', None)
        if workflows is not None and ((port is core.status.state and name == 'start_auto_optimize_label_worker') or (port is core.status.policy and name == 'auto_optimize_public_sprite_pool')):
            selected = actual()
            test.assertIs(selected.__self__, workflows)
            test.assertIs(selected.__func__, getattr(type(workflows), name))
            return
        owned = {
            id(core.store.storage): {'auto_optimize_task_path'},
            id(core.readiness.ports): {'auto_optimize_linked_pipeline_model_id', 'auto_optimize_completed_model_id'},
            id(core.status.state): {'load_auto_optimize_state', 'save_auto_optimize_state', 'auto_optimize_completed_model_id', 'auto_optimize_stop_capture_for_model_locked', 'public_auto_optimize_state'},
            id(core.status.policy): {'auto_optimize_phase_name', 'public_auto_optimize_initialization_payload'},
            id(core.shadow.state): {'auto_optimize_shadow_worker', 'load_auto_optimize_state', 'save_auto_optimize_state'},
            id(core.shadow.observation): {'analyze_bgr'},
            id(core.shadow.promotion): {'maybe_promote_auto_optimize_model_locked', 'cleanup_auto_optimize_retired_candidate_locked'},
        }
        if name == 'auto_optimize_shadow_worker' and port is core.shadow.state:
            selected = actual()
            test.assertIs(selected, core.pinned_shadow_worker)
            test.assertIs(selected.__wrapped__.__self__, core)
            test.assertIs(selected.__wrapped__.__func__, type(core).auto_optimize_shadow_worker)
        elif name in owned.get(id(port), set()):
            selected = actual()
            test.assertIs(selected.__self__, core)
            test.assertIs(selected.__func__, getattr(type(core), name))
        else:
            from canonical_application_source_contract import verify_actual_sources
            target = native_relay_targets(server).get((type(port), name))
            selected = actual()
            if target is not None:
                verify_actual_sources()
                assert_native_relay(test, selected, target)
            elif assert_pure_relay(test, port, name, selected, server):
                verify_actual_sources()
            else:
                # Constants, native resources and directly supplied functions
                # retain the original exact identity assertion. An unlisted
                # graph-local relay fails this check; no name/signature fallback.
                test.assertIs(selected, getattr(server, name))


def native_relay_targets(server):
    """Finite current-graph receiver witnesses; unknown relays are not accepted."""
    from pathlib import Path
    def w(owner, method, arguments, keywords=None, *, trailing_defaults=(), forwarded_kwargs=None):
        keywords = {} if keywords is None else keywords
        return (owner, method, arguments, keywords,
                arguments + trailing_defaults,
                keywords if forwarded_kwargs is None else forwarded_kwargs)
    return {
        (AutoOptimizationAdvisorPorts, 'accessory_lookup_by_id'): w(server._accessory_lookup, 'accessory_lookup_by_id', ({},)),
        (AutoOptimizationAdvisorPorts, 'ai_detection_settings'): w(server._model_profile_configuration, 'ai_detection_settings', ('training_vision',)),
        (AutoOptimizationAdvisorPorts, 'generate_provider_json_with_fallback'): w(server._provider_json_retry, 'generate_provider_json_with_fallback', ({}, 'system-A', []), {'max_tokens': 17}, forwarded_kwargs={'max_tokens': 17, 'cached_content': '', 'max_attempts': None, 'overloaded_retry_delay_seconds': None, 'allow_overloaded_model_fallback': True}),
        (AutoOptimizationMaskPromptPorts, 'accessory_lookup_by_id'): w(server._accessory_lookup, 'accessory_lookup_by_id', ({},)),
        (AutoOptimizationMaskPromptPorts, 'load_config'): w(server._app_configuration, 'load_config', ()),
        (AutoOptimizationMaskPromptPorts, 'scope_config_for_user'): w(server._account_projections, 'scope_config_for_user', ({},), trailing_defaults=(None, None)),
        (AutoOptimizationMaskVerificationPorts, 'ai_detection_settings'): w(server._model_profile_configuration, 'ai_detection_settings', ('training_vision',)),
        (AutoOptimizationMaskVerificationPorts, 'generate_provider_json_with_fallback'): w(server._provider_json_retry, 'generate_provider_json_with_fallback', ({}, 'system-A', []), {'max_tokens': 17}, forwarded_kwargs={'max_tokens': 17, 'cached_content': '', 'max_attempts': None, 'overloaded_retry_delay_seconds': None, 'allow_overloaded_model_fallback': True}),
        (AutoOptimizationMaskVerificationPorts, 'image_bgr_data_url'): w(server._image_encoding, 'image_bgr_data_url', (object(),), forwarded_kwargs={'max_side': 1280, 'quality': 82}),
        (AutoOptimizationMaskVisualPorts, 'public_output_url_for_existing'): w(server._service_paths, 'public_output_url_for_existing', (Path('source-A'),)),
        (AutoOptimizationReadinessPorts, 'canonical_pipeline_accessory_ids'): w(server._pipeline_candidate_flow, 'canonical_pipeline_accessory_ids', ({}, ['accessory-A'])),
        (AutoOptimizationReadinessPorts, 'find_training_task'): w(server._training_state_workflows, 'find_training_task', ('task-A',)),
        (AutoOptimizationReadinessPorts, 'load_config'): w(server._app_configuration, 'load_config', ()),
        (AutoOptimizationReadinessPorts, 'load_pipeline_tasks'): w(server._pipeline_task_store, 'load_pipeline_tasks', ()),
        (AutoOptimizationReadinessPorts, 'normalize_pipeline_accessory_counts'): w(server._pipeline_task_metadata, 'normalize_pipeline_accessory_counts', ({}, ['accessory-A']), trailing_defaults=(None,)),
        (AutoOptimizationReadinessPorts, 'normalize_pipeline_detection_method'): w(server._pipeline_task_metadata, 'normalize_pipeline_detection_method', ('yolo',)),
        (AutoOptimizationReadinessPorts, 'pipeline_task_model_id'): w(server._pipeline_task_metadata, 'pipeline_task_model_id', ({},)),
        (AutoOptimizationReadinessPorts, 'pipeline_task_model_status'): w(server._pipeline_resource_status, 'pipeline_task_model_status', ({},), forwarded_kwargs={'ai_task_ids': None, 'trained_model_specs': None}),
        (AutoOptimizationStatePolicy, 'resolve_model_profiles'): w(server._model_profile_configuration, 'resolve_model_profiles', ()),
        (AutoOptimizationStatePolicy, 'safe_record_id'): w(server._pose_collection_jobs, 'safe_record_id', ('task-A',)),
        (AutoOptimizationStateStorage, 'runtime_postgres_repository_or_none'): w(server._runtime_repository_access, 'runtime_postgres_repository_or_none', ()),
        (AutoOptimizationStatusPolicy, 'background_set_payload'): w(server._background_catalog, 'background_set_payload', ('background-A',), trailing_defaults=(None,)),
        (AutoOptimizationStatusPolicy, 'public_path_sanitized'): w(server._service_paths, 'public_path_sanitized', ('source-A',)),
        (AutoOptimizationStatusState, 'find_training_task'): w(server._training_state_workflows, 'find_training_task', ('task-A',)),
        (AutoOptimizationTaskInitializationPorts, 'canonical_pipeline_accessory_ids'): w(server._pipeline_candidate_flow, 'canonical_pipeline_accessory_ids', ({}, ['accessory-A'])),
        (DatasetConfiguration, 'accessory_lookup_by_id'): w(server._accessory_lookup, 'accessory_lookup_by_id', ({},)),
        (DatasetConfiguration, 'load_config'): w(server._app_configuration, 'load_config', ()),
        (DatasetConfiguration, 'scope_config_for_user'): w(server._account_projections, 'scope_config_for_user', ({},), trailing_defaults=(None, None)),
        (DatasetLayout, 'public_training_output_url'): w(server._training_output_links, 'public_training_output_url', (Path('output-A'),)),
        (DatasetLayout, 'render_training_background'): w(server._training_background_renderer, 'render_training_background', (object(),), trailing_defaults=(None, None)),
        (DatasetLayout, 'write_training_annotation_preview'): w(server._training_annotation_preview, 'write_training_annotation_preview', (Path('source-A'), [], Path('output-A'))),
        (DatasetPublication, 'output_write_dir_for_owner'): w(server._service_paths, 'output_write_dir_for_owner', ('kind-A', 'owner-A')),
        (DatasetPublication, 'resolve_service_path'): w(server._service_paths, 'resolve_service_path', ('source-A',), forwarded_kwargs={'for_write': False}),
        (DatasetPublication, 'safe_record_id'): w(server._pose_collection_jobs, 'safe_record_id', ('task-A',)),
        (LabelGenerationArtifacts, 'public_output_url_for_existing'): w(server._service_paths, 'public_output_url_for_existing', (Path('source-A'),)),
        (LabelGenerationArtifacts, 'resolve_service_path'): w(server._service_paths, 'resolve_service_path', ('source-A',), forwarded_kwargs={'for_write': False}),
        (LabelGenerationArtifacts, 'safe_record_id'): w(server._pose_collection_jobs, 'safe_record_id', ('task-A',)),
        (LabelGenerationModels, 'auto_optimize_generate_image_with_retry'): w(server._provider_image_retry, 'auto_optimize_generate_image_with_retry', ({}, 'model-A', 'prompt-A', []), forwarded_kwargs={'system_prompt': ''}),
        (LabelGenerationPolicy, 'photo_highlight_auto_compare'): w(server._photo_highlight_comparison, 'photo_highlight_auto_compare', (object(), object())),
        (LabelGenerationPolicy, 'photo_highlight_input_data_url'): w(server._photo_highlight_image_input, 'photo_highlight_input_data_url', (object(),)),
        (ProcessingArtifacts, 'output_write_dir_for_owner'): w(server._service_paths, 'output_write_dir_for_owner', ('kind-A', 'owner-A'), forwarded_kwargs={}),
        (ProcessingArtifacts, 'safe_record_id'): w(server._pose_collection_jobs, 'safe_record_id', ('task-A',), forwarded_kwargs={}),
        (ProcessingExecution, 'image_generation_settings'): w(server._model_profile_configuration, 'image_generation_settings', (), forwarded_kwargs={}),
        (RequestAccess, 'load_ai_detection_tasks'): w(server._detection_task_store, 'load_ai_detection_tasks', ()),
        (RequestAccess, 'safe_record_id'): w(server._pose_collection_jobs, 'safe_record_id', ('task-A',)),
        (RequestActions, 'analyze_bgr'): w(server._detection_analysis, 'analyze_bgr', (object(), 'request-A'), trailing_defaults=(None,), forwarded_kwargs={'image_path': None}),
        (RequestActions, 'resolve_service_path'): w(server._service_paths, 'resolve_service_path', ('source-A',), forwarded_kwargs={'for_write': False}),
        (SchedulingSubmission, 'enqueue_training_task'): w(server._training_execution, 'enqueue_training_task', (object(), [], 'fixture', None), forwarded_kwargs={}),
        (SchedulingSubmission, 'load_config'): w(server._app_configuration, 'load_config', (), forwarded_kwargs={}),
        (SchedulingSubmission, 'pipeline_ai_task_id'): w(server._pipeline_ai_task_sync, 'pipeline_ai_task_id', ('task-A',), forwarded_kwargs={}),
        (SchedulingSubmission, 'scope_config_for_user'): w(server._account_projections, 'scope_config_for_user', ({'fixture': True}, None, None), forwarded_kwargs={}),
        (SchedulingSubmission, 'selected_accessories'): w(server._accessory_selection, 'selected_accessories', ({}, ['accessory-A']), forwarded_kwargs={}),
        (ShadowObservation, 'resolve_service_path'): w(server._service_paths, 'resolve_service_path', ('source-A',), forwarded_kwargs={'for_write': False}),
        (ShadowObservation, 'safe_record_id'): w(server._pose_collection_jobs, 'safe_record_id', ('task-A',), forwarded_kwargs={}),
        (ShadowPromotion, 'delete_training_task_record'): w(server._training_state_workflows, 'delete_training_task_record', ('task-A', {}), forwarded_kwargs={'missing_ok': False}),
        (ShadowPromotion, 'training_run_roots'): w(server._dataset_catalog, 'training_run_roots', (), forwarded_kwargs={}),
        (SpriteFiles, 'output_write_dir_for_owner'): w(server._service_paths, 'output_write_dir_for_owner', ('kind-A', 'owner-A')),
        (SpriteFiles, 'public_path_sanitized'): w(server._service_paths, 'public_path_sanitized', ('source-A',)),
        (SpriteFiles, 'resolve_service_path'): w(server._service_paths, 'resolve_service_path', ('source-A',), forwarded_kwargs={'for_write': False}),
        (SpriteFiles, 'safe_record_id'): w(server._pose_collection_jobs, 'safe_record_id', ('task-A',)),
        (SyntheticBatchConfiguration, 'accessory_lookup_by_id'): w(server._accessory_lookup, 'accessory_lookup_by_id', ({},)),
        (SyntheticBatchConfiguration, 'load_config'): w(server._app_configuration, 'load_config', ()),
        (SyntheticBatchConfiguration, 'scope_config_for_user'): w(server._account_projections, 'scope_config_for_user', ({},), trailing_defaults=(None, None)),
        (SyntheticBatchPublication, 'output_write_dir_for_owner'): w(server._service_paths, 'output_write_dir_for_owner', ('kind-A', 'owner-A')),
        (SyntheticBatchPublication, 'safe_record_id'): w(server._pose_collection_jobs, 'safe_record_id', ('task-A',)),
        (SyntheticGeometry, 'choose_object_center_inside_background'): w(server._preview_placement, 'choose_object_center_inside_background', (object(), (11, 13), 7.0, []), trailing_defaults=(server.BACKGROUND_ROI_PX,)),
        (SyntheticGeometry, 'paste_masked_asset'): w(server._asset_compositor, 'paste_masked_asset', (object(), object(), object(), (11, 13), (17, 19), 7.0), trailing_defaults=(True, False, True)),
        (SyntheticPublication, 'public_training_output_url'): w(server._training_output_links, 'public_training_output_url', (Path('output-A'),)),
        (SyntheticPublication, 'render_training_background'): w(server._training_background_renderer, 'render_training_background', (object(),), trailing_defaults=(None, None)),
        (SyntheticPublication, 'write_training_annotation_preview'): w(server._training_annotation_preview, 'write_training_annotation_preview', (Path('source-A'), [], Path('output-A'))),
    }


def assert_native_relay(test, selected, target):
    from pathlib import Path
    from unittest.mock import patch
    owner, method, arguments, keywords, forwarded_args, forwarded_kwargs = target
    sentinel = object()
    with patch.object(type(owner), method, autospec=True, return_value=sentinel) as receiver:
        test.assertIs(selected(*arguments, **keywords), sentinel)
        receiver.assert_called_once_with(owner, *forwarded_args, **forwarded_kwargs)
        test.assertIs(receiver.call_args.args[0], owner)
        pairs = list(zip(receiver.call_args.args[1:], forwarded_args))
        pairs.extend((receiver.call_args.kwargs[key], value) for key, value in forwarded_kwargs.items())
        for received, supplied in pairs:
            if isinstance(supplied, (dict, list, set, Path)) or type(supplied) is object:
                test.assertIs(received, supplied)


def assert_pure_relay(test, port, name, selected, server):
    from pathlib import Path
    from unittest.mock import patch
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    from local_inspection_service.accessories.mask_geometry import alpha_bbox
    from local_inspection_service.agent.photo_highlight_masks import decode_photo_highlight_mask, photo_highlight_auto_roi_mask
    from local_inspection_service.detection.task_backgrounds import hydrate_auto_optimize_background_from_ai_task
    from local_inspection_service.training.annotations import write_dataset_yaml
    from local_inspection_service.training.background_catalog import safe_background_set_id
    from local_inspection_service.accessories import policy as accessory_policy
    key = (type(port), name)
    if key in ((AutoOptimizationAdvisorPorts, 'accessory_material_type'),
               (AutoOptimizationMaskPromptPorts, 'accessory_material_type')):
        test.assertIs(wiring._accessory_policy, accessory_policy)
        sentinel, item = object(), {'material_type': 'fixture-A'}
        with patch.object(accessory_policy, 'accessory_material_type', autospec=True, return_value=sentinel) as receiver:
            test.assertIs(selected(item), sentinel)
            receiver.assert_called_once_with(item)
            test.assertIs(receiver.call_args.args[0], item)
        return True
    targets = {
        (LabelGenerationPolicy, 'alpha_bbox'): ('_alpha_bbox_impl', alpha_bbox, (object(), 8), {}),
        (SpriteGeometry, 'alpha_bbox'): ('_alpha_bbox_impl', alpha_bbox, (object(), 8), {}),
        (SyntheticGeometry, 'alpha_bbox'): ('_alpha_bbox_impl', alpha_bbox, (object(), 8), {}),
        (LabelGenerationPolicy, 'decode_photo_highlight_mask'): ('_decode_photo_highlight_mask_impl', decode_photo_highlight_mask, (object(),), {}),
        (LabelGenerationPolicy, 'photo_highlight_auto_roi_mask'): ('_photo_highlight_auto_roi_mask_impl', photo_highlight_auto_roi_mask, (object(), object()), {}),
        (DatasetLayout, 'write_dataset_yaml'): ('_write_dataset_yaml', write_dataset_yaml, (Path('file-A'), Path('dataset-A'), ['label-A']), {'files': server._business_files}),
    }
    if key in targets:
        attribute, original, args, kwargs = targets[key]
        test.assertIs(getattr(wiring, attribute), original)
        sentinel = object()
        with patch.object(wiring, attribute, autospec=True, return_value=sentinel) as receiver:
            test.assertIs(selected(*args), sentinel)
            receiver.assert_called_once_with(*args, **kwargs)
            if key == (DatasetLayout, 'write_dataset_yaml'):
                test.assertIs(receiver.call_args.kwargs['files'], server._business_files)
        return True
    if key != (AutoOptimizationStatusState, 'hydrate_auto_optimize_background_from_ai_task'):
        return False
    test.assertIs(wiring._hydrate_detection_task_background, hydrate_auto_optimize_background_from_ai_task)
    state, sentinel = {'task_id': 'task-A'}, object()
    with patch.object(wiring, '_hydrate_detection_task_background', autospec=True, return_value=sentinel) as receiver:
        test.assertIs(selected(state), sentinel)
        receiver.assert_called_once()
        test.assertEqual(receiver.call_args.args, (state,))
        test.assertIs(receiver.call_args.args[0], state)
        callbacks = receiver.call_args.kwargs
        test.assertEqual(set(callbacks), {'background_record', 'normalize_background'})
        test.assertIs(callbacks['normalize_background'](), safe_background_set_id)
    owner = server._detection_task_store
    record = {'background_set_id': 'background-A'}
    with patch.object(type(owner), 'find_ai_detection_task', autospec=True, return_value=record) as finder:
        test.assertEqual(callbacks['background_record']()('task-A'), ('background-A', {'background_set_id': 'background-A'}))
        finder.assert_called_once_with(owner, 'task-a')
        test.assertIs(finder.call_args.args[0], owner)
    return True

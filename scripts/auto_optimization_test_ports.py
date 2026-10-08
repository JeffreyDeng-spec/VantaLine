"""Synthetic capability injection shared by auto-optimization contracts."""
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
            test.assertIs(actual(), getattr(server, name))

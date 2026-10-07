"""Synthetic capability injection shared by auto-optimization contracts."""
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

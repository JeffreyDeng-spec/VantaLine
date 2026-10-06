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
        test.assertIs(actual(), getattr(server, name))

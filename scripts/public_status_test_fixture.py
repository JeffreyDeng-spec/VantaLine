"""Public projection contracts against a finite native graph and default relays."""
from types import SimpleNamespace
from local_inspection_service.auth.status import PublicStatusProjection
from local_inspection_service.auth.status_ports import StatusPolicy, StatusSources, StatusProjectionCalls


def public_status_fixture(server):
    assert_default_status(server)
    names = ('user_is_admin', 'user_has_permission', 'STATUS_MODEL_PUBLIC_KEYS',
             'public_path_sanitized', 'ai_detection_settings', 'image_generation_settings')
    api = SimpleNamespace(**{name: getattr(server, name) for name in names})
    graph = PublicStatusProjection(
        StatusPolicy(lambda: api.user_is_admin, lambda: api.user_has_permission,
                     lambda: api.STATUS_MODEL_PUBLIC_KEYS, lambda: api.public_path_sanitized),
        StatusSources(lambda: api.ai_detection_settings, lambda: api.image_generation_settings),
        StatusProjectionCalls(lambda: api.public_ai_detection_status,
                              lambda: api.public_image_generation_status,
                              lambda: api.public_status_model_for_user,
                              lambda: api.public_ai_detection_status_for_user))
    for name in ('public_ai_detection_status', 'public_image_generation_status',
                 'public_status_model_for_user', 'public_ai_detection_status_for_user',
                 'public_service_status_for_user', 'public_config_summary_for_user'):
        setattr(api, name, getattr(graph, name))
    return api


def assert_default_status(server):
    import unittest
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.auth import policy
    from local_inspection_service.model_profiles.composition import ModelConfiguration
    from local_inspection_service.runtime.service_paths import ServicePaths
    verify_actual_sources()
    case = unittest.TestCase()
    application = server._default_application
    infrastructure = application.infrastructure
    graph = infrastructure._public_status_projection
    case.assertIs(server._public_status_projection, graph)
    case.assertIs(type(graph), PublicStatusProjection)
    case.assertIs(graph._policy.admin(), policy.user_is_admin)
    case.assertIs(graph._policy.permission(), policy.user_has_permission)
    case.assertIs(graph._policy.model_fields(), application.values.STATUS_MODEL_PUBLIC_KEYS)
    models = infrastructure._model_profile_configuration
    paths = infrastructure._service_paths
    case.assertIs(type(models), ModelConfiguration)
    case.assertIs(type(paths), ServicePaths)
    record, user = object(), object()
    relays = (
        (graph._sources.ai(), models, 'ai_detection_settings', (), ('pipeline',)),
        (graph._sources.image(), models, 'image_generation_settings', (), ()),
        (graph._policy.sanitize(), paths, 'public_path_sanitized', (record,), (record,)),
        (graph._calls.ai(), graph, 'public_ai_detection_status', (), ()),
        (graph._calls.image(), graph, 'public_image_generation_status', (), ()),
        (graph._calls.model(), graph, 'public_status_model_for_user', (record, user), (record, user)),
        (graph._calls.ai_for_user(), graph, 'public_ai_detection_status_for_user', (user,), (user,)),
    )
    for selected, owner, method, args, forwarded in relays:
        assert_native_relay(case, selected, (owner, method, args, {}, forwarded, {}))

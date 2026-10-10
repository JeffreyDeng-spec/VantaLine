"""Temporary, restored replacements for explicit text application test inputs."""
from contextlib import contextmanager


@contextmanager
def text_value(values, name, replacement):
    from local_inspection_service.runtime.application_values import ApplicationValues
    assert type(values) is ApplicationValues
    assert name in {
        'TEXT_INSPECTION_JSON_DIR',
        'TEXT_INSPECTION_PROVIDER_IMAGE_MAX_SIDE',
        'TEXT_INSPECTION_PROVIDER_IMAGE_JPEG_QUALITY',
        'TEXT_INSPECTION_DIAGNOSTIC_LOGGER',
        'INCOMING_TEXT_REFERENCES_PATH',
        'INCOMING_TEXT_INSPECTIONS_PATH',
        'INCOMING_TEXT_AUDIT_PATH',
        'TEXT_INSPECTION_EXTERNAL_VLM_ENABLED',
    }
    original = getattr(values, name)
    try:
        object.__setattr__(values, name, replacement)
        yield
    finally:
        object.__setattr__(values, name, original)


@contextmanager
def text_repository(case, server, **mock_options):
    from unittest.mock import Mock, patch
    from local_inspection_service.runtime.repository_access import RuntimeRepositoryAccess
    owner = server._default_application.infrastructure._runtime_repository_access
    result = mock_options.pop('return_value', None)
    callback = mock_options.pop('side_effect', None)
    assert not mock_options
    capability = Mock(side_effect=callback, return_value=result)

    def selected(receiver):
        case.assertIs(receiver, owner)
        return capability()

    with patch.object(RuntimeRepositoryAccess, 'runtime_postgres_repository_or_none',
                      autospec=True, side_effect=selected) as factory:
        yield capability


def assert_prepared_comparison_defaults(case, server):
    """Verify the actual bound model and connection owners before substitution."""
    from types import SimpleNamespace
    from unittest.mock import Mock, patch
    from scripts.model_profile_test_ports import patch_profile_service
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.text_inspection.comparison_composition import TextComparisonWorkflows
    from local_inspection_service.model_profiles.composition import ModelConfiguration
    from local_inspection_service.runtime.connections import ThreadRepositoryFactory
    verify_actual_sources()
    application = server._default_application
    graph = application.text._text_comparisons
    case.assertIs(server._text_comparisons, graph)
    case.assertIs(type(graph), TextComparisonWorkflows)
    model_owner = application.infrastructure._model_profile_configuration
    case.assertIs(type(model_owner), ModelConfiguration)
    settings = object()
    resolve = Mock(return_value=settings)
    record = Mock(return_value=object())
    for flag in (False, True, False):
        with text_value(application.values, 'TEXT_INSPECTION_EXTERNAL_VLM_ENABLED', flag):
            case.assertIs(graph.prepared_models().external_enabled, flag)
    with patch_profile_service(server, SimpleNamespace(resolve=resolve, record_call=record)):
        models = graph.prepared_models()
        case.assertIs(models.external_enabled, application.values.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED)
        case.assertIs(models.settings('text_comparison'), settings)
        resolve.assert_called_once_with('text_comparison')
        usage = object()
        case.assertIs(models.record_usage(settings, 17, True, usage), record.return_value)
        record.assert_called_once_with(settings, 17, True, usage)
        case.assertIs(record.call_args.args[0], settings)
        case.assertIs(record.call_args.args[3], usage)
    owner = application.infrastructure._runtime_repositories
    case.assertIs(type(owner), ThreadRepositoryFactory)
    def clear(receiver):
        case.assertIs(receiver, owner)
    with patch.object(ThreadRepositoryFactory, 'clear', autospec=True, side_effect=clear) as callee:
        graph.prepared_cleanup()()
        callee.assert_called_once_with(owner)

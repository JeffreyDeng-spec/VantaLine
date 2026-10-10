"""Replace configuration capabilities at their owned boundary in regressions."""
from unittest.mock import patch
from contextlib import contextmanager, ExitStack

PROVIDER_METHODS = frozenset(['_legacy_ai_detection_settings', '_legacy_image_generation_settings', '_legacy_load_agent_config', 'agent_base_url_host', 'agent_keys_for_provider', 'agent_model_options_from_items', 'agent_provider_label', 'ai_key_id', 'ai_keys_for_provider', 'ai_local_config_temp_path', 'ai_provider_label', 'ai_proxy_url_from_config', 'ai_proxy_url_from_environment', 'ai_urlopen', 'default_ai_base_url', 'default_ai_model', 'default_image_generation_api_key_env', 'default_image_generation_base_url', 'default_image_generation_model', 'default_secret_env_name', 'delete_local_secret_env', 'detect_agent_provider_from_base_url', 'env_flag_enabled', 'image_generation_provider_key', 'image_generation_provider_label', 'image_keys_for_provider', 'is_cursor_base_url', 'load_ai_local_config', 'load_local_secret_env', 'local_proxy_available', 'local_secret_env_value', 'mask_secret', 'masked_url_for_status', 'normalize_agent_config', 'normalize_agent_key_items', 'normalize_agent_model_options', 'normalize_agent_provider', 'normalize_ai_key_items', 'normalize_image_key_items', 'persist_secret_key_items', 'public_ai_base_url', 'public_ai_key_items', 'save_agent_config', 'save_ai_local_config', 'save_local_secret_env', 'secret_key_item_id', 'set_local_secret_env', 'validate_ai_base_url', 'validate_ai_key_env', 'validate_ai_model', 'validate_ai_provider', 'validate_ai_proxy_url', 'validate_ai_timeout', 'validate_image_generation_provider', 'validate_image_generation_timeout'])

def provider_capability_target(api, name):
    if getattr(api, '__name__', None) == 'local_inspection_service.server':
        if name in {'DATA_DIR', 'LOCAL_SECRET_ENV_PATH', 'AGENT_LOCAL_CONFIG_PATH',
                    'AI_DEFAULT_PROVIDER', 'AI_SUPPORTED_PROVIDERS', 'DEFAULT_AGENT_CONFIG'}:
            return api._default_application.values, name
        if name in {'bounded_text', 'HTTPException', 'urlsplit', 'urlunsplit'}:
            from local_inspection_service.runtime.wiring import infrastructure
            return infrastructure, name
    transport = getattr(api, '_provider_transports', None)
    resolvers = {'_openai_profile_resolver': 'openai_resolver',
                 '_gemini_profile_resolver': 'gemini_resolver',
                 '_agnes_profile_resolver': 'agnes_resolver',
                 '_qwen_image_profile_resolver': 'qwen_resolver'}
    if transport is not None and name in resolvers:
        return transport, resolvers[name]
    owner = getattr(api, '_provider_configuration', None)
    if owner is not None and name in PROVIDER_METHODS:
        return owner, name
    if owner is None and name in PROVIDER_METHODS and getattr(api, '__name__', None) == 'local_inspection_service.server':
        raise AssertionError('Actual application is missing its provider configuration owner')
    return api, name

def patch_provider_capability(api, name, *args, **kwargs):
    target, attribute = provider_capability_target(api, name)
    from local_inspection_service.runtime.application_values import ApplicationValues
    if type(target) is ApplicationValues:
        kwargs.pop('create', None)
        assert len(args) == 1 and not kwargs
        return frozen_provider_value(target, attribute, args[0])
    return patch.object(target, attribute, *args, **kwargs)

@contextmanager
def frozen_provider_value(target, attribute, replacement):
    original = getattr(target, attribute)
    try:
        object.__setattr__(target, attribute, replacement)
        yield replacement
    finally:
        object.__setattr__(target, attribute, original)

def set_provider_capability(api, name, value):
    target, attribute = provider_capability_target(api, name)
    from local_inspection_service.runtime.application_values import ApplicationValues
    if type(target) is ApplicationValues:
        object.__setattr__(target, attribute, value)
    else:
        setattr(target, attribute, value)

def get_provider_capability(api, name):
    target, attribute = provider_capability_target(api, name)
    return getattr(target, attribute)

@contextmanager
def patch_provider_values(api, values):
    with ExitStack() as stack:
        for name, value in values.items():
            stack.enter_context(patch_provider_capability(api, name, value, create=True))
        yield

@contextmanager
def provider_environment_input(api, domain, supplier):
    """Inject the old test's changing mapping through its explicit native port.

    Applications capture their supplied mapping, not later os.environ objects.
    These contracts test operation-time supplier selection with synthetic maps.
    """
    owner = api._provider_configuration
    from local_inspection_service.model_providers.key_material_ports import SecretEnvironment
    from local_inspection_service.model_providers.legacy_settings_ports import LegacySettingsIO
    if domain == 'secrets':
        port, field = owner.secrets._environment, 'values'
        assert type(port) is SecretEnvironment
    else:
        assert domain in {'legacy_json', 'legacy_image'}
        port, field = getattr(owner, domain)._io, 'environment'
        assert type(port) is LegacySettingsIO
    with frozen_provider_value(port, field, supplier):
        yield

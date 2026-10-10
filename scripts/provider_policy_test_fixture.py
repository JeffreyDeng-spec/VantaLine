"""Finite native policy inputs for pre-extraction callback-capture contracts."""
from types import SimpleNamespace

JSON_FIELDS = dict(models='AI_DEFAULT_MODELS', model='AI_DEFAULT_MODEL',
                   base_urls='AI_DEFAULT_BASE_URLS', provider='AI_DEFAULT_PROVIDER',
                   labels='AI_PROVIDER_LABELS')
IMAGE_FIELDS = dict(models='IMAGE_GENERATION_DEFAULT_MODELS',
                    base_urls='IMAGE_GENERATION_DEFAULT_BASE_URLS',
                    provider='IMAGE_GENERATION_DEFAULT_PROVIDER',
                    key_envs='IMAGE_GENERATION_DEFAULT_API_KEY_ENVS',
                    key_env='IMAGE_GENERATION_API_KEY_ENV',
                    provider_keys='IMAGE_GENERATION_PROVIDER_KEYS',
                    labels='IMAGE_GENERATION_PROVIDER_LABELS')
VALIDATION_FIELDS = dict(json_providers='AI_SUPPORTED_PROVIDERS',
                         image_providers='IMAGE_GENERATION_SUPPORTED_PROVIDERS',
                         http_error='HTTPException', split_url='urlsplit')
URL_FIELDS = dict(split_url='urlsplit', join_url='urlunsplit', text='bounded_text')


def policy_fixture(server):
    from local_inspection_service.model_providers.configuration_ports import (
        JsonDefaults, ImageDefaults, ValidationCapabilities, PublicUrlCapabilities)
    from local_inspection_service.model_providers.configuration_defaults import ProviderDefaults
    from local_inspection_service.model_providers.configuration_validation import ProviderValidation
    from local_inspection_service.model_providers.public_urls import PublicProviderURLs
    names = set(JSON_FIELDS.values()) | set(IMAGE_FIELDS.values()) | set(VALIDATION_FIELDS.values()) | set(URL_FIELDS.values()) | {'re'}
    api = SimpleNamespace(**{name: getattr(server, name) for name in names})

    def port(cls, fields):
        return cls(**{field: (lambda name=name: getattr(api, name))
                      for field, name in fields.items()})

    defaults = ProviderDefaults(port(JsonDefaults, JSON_FIELDS), port(ImageDefaults, IMAGE_FIELDS))
    validation = ProviderValidation(ValidationCapabilities(
        **{field: (lambda name=name: getattr(api, name)) for field, name in VALIDATION_FIELDS.items()},
        fullmatch=lambda: api.re.fullmatch))
    urls = PublicProviderURLs(port(PublicUrlCapabilities, URL_FIELDS))
    for name in ('default_ai_model', 'default_ai_base_url', 'ai_provider_label',
                 'default_image_generation_model', 'default_image_generation_base_url',
                 'default_image_generation_api_key_env', 'image_generation_provider_key',
                 'image_generation_provider_label'):
        setattr(api, name, getattr(defaults, name))
    for name in ('validate_ai_provider', 'validate_image_generation_provider',
                 'validate_ai_model', 'validate_ai_base_url', 'validate_ai_key_env',
                 'validate_ai_proxy_url', 'validate_ai_timeout', 'validate_image_generation_timeout'):
        setattr(api, name, getattr(validation, name))
    api.public_ai_base_url = urls.public_ai_base_url
    api.masked_url_for_status = urls.masked_url_for_status
    return api


def assert_default_policy_inputs(case, server):
    """Fail if the real application's policy reads a stale or different value."""
    from local_inspection_service.model_providers.configuration_defaults import ProviderDefaults
    from local_inspection_service.model_providers.configuration_validation import ProviderValidation
    from local_inspection_service.model_providers.public_urls import PublicProviderURLs
    owner = server._provider_configuration
    case.assertIs(type(owner.defaults), ProviderDefaults)
    case.assertIs(type(owner.validation), ProviderValidation)
    case.assertIs(type(owner.public_urls), PublicProviderURLs)
    for inputs, fields in ((owner.defaults._json, JSON_FIELDS),
                           (owner.defaults._image, IMAGE_FIELDS),
                           (owner.validation._capabilities, VALIDATION_FIELDS),
                           (owner.public_urls._capabilities, URL_FIELDS)):
        for field, name in fields.items():
            case.assertIs(getattr(inputs, field)(), getattr(server, name), (field, name))
    case.assertIs(owner.validation._capabilities.fullmatch(), server.re.fullmatch)

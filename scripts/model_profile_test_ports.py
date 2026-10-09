"""Replace the explicit profile owner while retaining frozen pre-owner baselines."""
from unittest.mock import patch


def profile_service_target(api):
    owner = getattr(api, '_model_profile_configuration', None)
    if owner is not None:
        return owner, 'service'
    if getattr(api, '__name__', None) == 'local_inspection_service.server':
        raise AssertionError('Actual application must expose its model configuration owner')
    # Frozen AST namespaces and independent port fakes retain their old slot.
    return api, 'model_profile_service'


def patch_profile_service(api, value, **kwargs):
    target, name = profile_service_target(api)
    return patch.object(target, name, value, **kwargs)


def set_profile_service(api, value):
    target, name = profile_service_target(api)
    setattr(target, name, value)


def patch_fixture_capability(api, name, value, **kwargs):
    if name == 'model_profile_service':
        return patch_profile_service(api, value, **kwargs)
    return patch.object(api, name, value, **kwargs)

"""Explicit replacement targets for catalog regression tests and old AST baselines."""
from unittest.mock import patch


def target(api, name):
    owner = getattr(api, '_model_catalog', None)
    if owner is not None:
        targets = {
            'training_task_finder': (owner.lookup, 'training_task_finder'),
            'pipeline_task_link_for_training_run': (owner.links, 'pipeline_task_link_for_training_run'),
            'list_trained_model_specs': (owner.catalog, 'list_trained_model_specs'),
            'selected_model_spec': (owner.selection, 'selected_model_spec'),
            'legacy_model_specs': (owner, 'legacy_model_specs'),
        }
        if name in targets: return targets[name]
    return api, name


def patch_model(api, name, *args, **kwargs):
    return patch.object(*target(api, name), *args, **kwargs)


def get_model_callback(api, name, *args):
    return getattr(*target(api, name), *args)


def set_model_callback(api, name, value):
    return setattr(*target(api, name), value)

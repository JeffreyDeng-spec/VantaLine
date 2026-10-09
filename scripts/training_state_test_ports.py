"""Replace migrated training capabilities at their actual owner in regressions."""
from unittest.mock import patch

RUNTIME_FIELDS = {
    '_training_task_lock': 'lock',
    '_training_task_threads': 'threads',
    '_training_task_delete_tombstones': 'tombstones',
}
OWNED_METHODS = frozenset({
    'training_task_path', 'load_training_task', 'save_training_task',
    'find_training_task', 'load_training_task_records',
    'refresh_interrupted_local_training_task',
    'update_training_task', 'list_training_tasks', 'delete_training_task_record',
    'public_training_task', 'public_refreshed_training_task',
})


ACCOUNT_METHODS = frozenset({'default_training_state', 'normalize_training_owner_key', 'training_state_store',
    'sanitize_training_state_for_user', 'training_state_for_user', 'set_training_state_for_user',
    'sync_training_state_from_task'})
API_METHODS = frozenset({'dataset_for_training', 'validate_approved_preview', 'filtered_training_state'})
EXECUTION_METHODS = frozenset({'run_training_task', 'enqueue_training_task'})


def training_port_target(api, name):
    if hasattr(api, '_app_configuration') and name in {'load_config', 'save_config'}:
        return api._app_configuration, name
    if hasattr(api, '_pipeline_persistence'):
        if name == '_pipeline_tasks_lock':
            return api._pipeline_persistence.runtime, 'task_lock'
        if name in {'load_pipeline_task', 'save_pipeline_task'}:
            return api._pipeline_persistence, name
    if hasattr(api, '_training_state_workflows'):
        if name in RUNTIME_FIELDS:
            return api._training_state_workflows.runtime, RUNTIME_FIELDS[name]
        if name in OWNED_METHODS:
            return api._training_state_workflows, name
    if hasattr(api, '_training_account_state') and name in ACCOUNT_METHODS:
        return api._training_account_state, name
    if hasattr(api, '_training_task_workflows') and name in API_METHODS:
        return api._training_task_workflows, name
    if hasattr(api, '_training_execution') and name in EXECUTION_METHODS:
        return api._training_execution, name
    return api, name


def get_training_port(api, name):
    if hasattr(api, "_training_execution") and name in {"load_training_task", "update_training_task"}:
        return getattr(api._training_execution, name)
    owner, field = training_port_target(api, name)
    return getattr(owner, field)


def set_training_port(api, name, value):
    owner, field = training_port_target(api, name)
    setattr(owner, field, value)
    if hasattr(api, "_training_execution") and name in {"load_training_task", "update_training_task"}:
        setattr(api._training_execution, name, value)
    if hasattr(api, "_training_task_workflows") and name == "update_training_task":
        setattr(api._training_task_workflows, name, value)


def patch_training_port(api, name, *args, **kwargs):
    from scripts.provider_configuration_test_ports import PROVIDER_METHODS, patch_provider_capability
    if name in PROVIDER_METHODS:
        return patch_provider_capability(api, name, *args, **kwargs)
    if name == "model_profile_service":
        from scripts.model_profile_test_ports import profile_service_target
        return patch.object(*profile_service_target(api), *args, **kwargs)
    if hasattr(api, '_training_jobs_query') and name == 'training_task_uses_worker':
        from contextlib import contextmanager
        from dataclasses import replace
        from types import SimpleNamespace
        @contextmanager
        def classifier():
            query = api._training_jobs_query
            holder = SimpleNamespace(value=query.training.uses_worker)
            with patch.object(holder, 'value', *args, **kwargs) as replacement:
                with patch.object(query, 'training', replace(query.training, uses_worker=replacement)):
                    yield replacement
        return classifier()
    owner, field = training_port_target(api, name)
    if hasattr(api, '_training_execution') and name in {'load_training_task', 'update_training_task'}:
        from contextlib import contextmanager, ExitStack
        @contextmanager
        def entry_callbacks():
            with ExitStack() as stack:
                replacement = stack.enter_context(patch.object(owner, field, *args, **kwargs))
                stack.enter_context(patch.object(api._training_execution, name, replacement))
                if name == 'update_training_task':
                    stack.enter_context(patch.object(api._training_task_workflows, name, replacement))
                yield replacement
        return entry_callbacks()
    return patch.object(owner, field, *args, **kwargs)

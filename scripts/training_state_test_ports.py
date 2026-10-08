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
})


def patch_training_port(api, name, *args, **kwargs):
    if hasattr(api, '_training_state_workflows') and name in RUNTIME_FIELDS:
        return patch.object(api._training_state_workflows.runtime,
                            RUNTIME_FIELDS[name], *args, **kwargs)
    if hasattr(api, '_training_state_workflows') and name in OWNED_METHODS:
        return patch.object(api._training_state_workflows, name, *args, **kwargs)
    return patch.object(api, name, *args, **kwargs)

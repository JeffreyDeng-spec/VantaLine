"""Replace migrated task capabilities on their actual domain owner in tests."""
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

METHODS = frozenset({
    'load_pipeline_tasks', 'ensure_pipeline_task_accessory_objects',
    'sync_pipeline_ai_detection_tasks', 'normalize_pipeline_task_auto_advance_defaults',
    'sync_and_auto_advance_pipeline', 'save_pipeline_tasks',
    'collect_pipeline_recommendation_pregen', 'schedule_pipeline_auto_agent',
    'schedule_pipeline_advance', 'schedule_pipeline_recommendation_pregen',
    'auto_optimize_states_by_task_id', 'pipeline_task_public', 'pipeline_accessories_payload',
    'canonical_pipeline_accessory_ids', 'normalize_pipeline_detection_method',
    'pipeline_method_uses_training', 'normalize_pipeline_accessory_counts',
    'pipeline_next_recommendation_stage', 'activate_pipeline_ai_detection_task',
    'save_pipeline_task', 'load_pipeline_task', 'pipeline_task_accessory_snapshot',
    'add_pipeline_accessory_id', 'remove_pipeline_accessory_id',
    'cancel_pipeline_advance', 'delete_pipeline_task_row',
    'agent_pipeline_decide', 'commit_pipeline_agent_turn', 'sync_pipeline_task',
})
RUNTIME_FIELDS = {
    '_pipeline_tasks_lock': 'task_lock',
    '_pipeline_advance_registry_lock': 'advance_registry_lock',
    '_pipeline_advance_inflight': 'advance_inflight',
    '_set_pipeline_tasks_sync_last_at': 'set_last_sync_at',
}

def set_pipeline_task_test_port(api, name, value):
    setattr(api, name, value)
    owner = getattr(api, '_pipeline_tasks', None)
    if owner is not None:
        if name in METHODS:
            setattr(owner, name, value)
        elif name in RUNTIME_FIELDS:
            setattr(owner.runtime, RUNTIME_FIELDS[name], value)

@contextmanager
def patch_pipeline_task_test_port(api, name, value):
    with ExitStack() as stack:
        replacement = stack.enter_context(patch.object(api, name, value))
        owner = getattr(api, '_pipeline_tasks', None)
        if owner is not None:
            if name in METHODS:
                stack.enter_context(patch.object(owner, name, replacement))
            elif name in RUNTIME_FIELDS:
                stack.enter_context(patch.object(owner.runtime, RUNTIME_FIELDS[name], replacement))
        yield replacement

"""Replace owned query callbacks without depending on server alias rebinding."""
from contextlib import contextmanager, ExitStack
from unittest.mock import patch

QUERY_METHODS = frozenset({
    'pipeline_task_label_snapshot', 'pipeline_task_accessory_snapshot',
    'normalize_pipeline_detection_method', 'pipeline_method_uses_training',
    'normalize_pipeline_accessory_counts', 'canonical_pipeline_accessory_ids',
    'refresh_pipeline_candidate', 'candidate_confirmed_accessory_id',
    'pipeline_candidate_job_status', 'pipeline_candidate_public',
    'pipeline_task_dataset_status', 'pipeline_task_model_status',
    'public_auto_optimize_link_for_task_id', 'pipeline_task_auto_optimize_link',
    'fast_completed_auto_optimize_model_id', 'auto_optimize_states_by_task_id',
    'load_pipeline_state', 'update_pipeline_state',
})

@contextmanager
def patch_pipeline_query(api, name, **kwargs):
    with ExitStack() as stack:
        replacement = stack.enter_context(patch.object(api, name, **kwargs))
        if name in QUERY_METHODS:
            stack.enter_context(patch.object(api._pipeline_queries, name, replacement))
        yield replacement

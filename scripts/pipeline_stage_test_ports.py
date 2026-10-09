"""Substitute migrated stage abilities on the actual state/transition owner."""
from contextlib import contextmanager, ExitStack
from unittest.mock import DEFAULT, patch
METHODS=frozenset({
 'canonical_pipeline_accessory_ids','normalize_pipeline_accessory_counts','normalize_pipeline_detection_method',
 'pipeline_method_uses_training','upsert_pipeline_ai_detection_task','activate_pipeline_ai_detection_task',
 'pipeline_ai_task_id','pipeline_ai_task_training_route','linked_training_job','sync_pipeline_task',
 'consume_pipeline_recommendation','pipeline_task_decision_signature','pipeline_task_needs_auto_agent',
 'reap_pipeline_advance_zombie','pipeline_recommendation_signature','pipeline_next_recommendation_stage',
 'pipeline_recommendation_ready',
})
RUNTIME_FIELDS={'_pipeline_advance_registry_lock':'advance_registry_lock','_pipeline_advance_inflight':'advance_inflight'}

@contextmanager
def patch_pipeline_stage(api,name,value=DEFAULT,**kwargs):
    with ExitStack() as stack:
        root_patch=patch.object(api,name,**kwargs) if value is DEFAULT else patch.object(api,name,value,**kwargs)
        replacement=stack.enter_context(root_patch)
        owner=getattr(api,'_pipeline_stages',None)
        if owner is not None:
            if name in METHODS:stack.enter_context(patch.object(owner,name,replacement))
            elif name in RUNTIME_FIELDS:stack.enter_context(patch.object(owner.runtime,RUNTIME_FIELDS[name],replacement))
        yield replacement

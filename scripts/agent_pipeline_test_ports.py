"""Replace migrated Agent abilities on their actual workflow owner."""
from contextlib import contextmanager, ExitStack
from unittest.mock import DEFAULT, patch

OWNED=frozenset({
 'canonical_pipeline_accessory_ids','normalize_pipeline_accessory_counts',
 'normalize_pipeline_detection_method','pipeline_method_uses_training',
 'agent_pipeline_quality_signals','agent_pipeline_context',
 'normalize_agent_pipeline_decision','_rule_rerun_failed_stage',
 'agent_pipeline_rule_decision','agent_safe_advance','reset_pipeline_task_to_stage',
 'agent_mcp_append_conversation','apply_agent_pipeline_decision',
})

@contextmanager
def patch_agent_pipeline(api,name,value=DEFAULT,**kwargs):
    with ExitStack() as stack:
        root_patch=patch.object(api,name,**kwargs) if value is DEFAULT else patch.object(api,name,value,**kwargs)
        replacement=stack.enter_context(root_patch)
        if name in OWNED:
            stack.enter_context(patch.object(api._agent_pipeline_workflows,name,replacement))
        yield replacement

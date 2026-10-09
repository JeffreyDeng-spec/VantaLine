"""Replace migrated abilities on explicit connected workflow owners in tests."""
from contextlib import contextmanager,ExitStack
from unittest.mock import patch
OWNERS={
 'save_pipeline_task':('queries.persistence','execution'),
 'save_pipeline_tasks':('queries.persistence',),
 'load_pipeline_tasks':('queries.persistence',),
 'load_pipeline_task':('queries.persistence','execution'),
 # Mutation services are frozen value objects. Their owned callers select the
 # connected forwarders, so substituting those does not mutate a frozen object
 # or patch a class shared by another application graph.
 'save_pipeline_task_batch_changes':(),
 'persist_pipeline_task_progress':(),
 'mark_pipeline_task_advancing':(),
 'linked_training_job':('stages',),'sync_pipeline_task':('stages',),
 'advance_pipeline_task':('stages',),'pipeline_task_needs_auto_agent':('stages',),
 'pipeline_task_decision_signature':('stages',),'agent_mcp_append_conversation':('agent',),
 'agent_pipeline_decide':('agent',),'commit_pipeline_agent_turn':('agent',),
 'pipeline_next_recommendation_stage':('stages',),'pipeline_recommendation_ready':('stages',),
 'pipeline_recommendation_signature':('stages',),
}

@contextmanager
def patch_pipeline_runtime(api,name,value,**kwargs):
    with ExitStack() as stack:
        replacement=stack.enter_context(patch.object(api,name,value,**kwargs))
        owner=api._pipeline_workflows
        stack.enter_context(patch.object(owner,name,replacement))
        for path in OWNERS[name]:
            component=owner
            for part in path.split('.'):component=getattr(component,part)
            stack.enter_context(patch.object(component,name,replacement))
        yield replacement

"""Replace migrated pipeline abilities through their actual execution owner."""
from contextlib import contextmanager, ExitStack
from unittest.mock import patch
RUNTIME_FIELDS={
    '_pipeline_tasks_lock':'task_lock', '_pipeline_auto_agent_lock':'auto_agent_lock',
    '_pipeline_auto_agent_inflight':'auto_agent_inflight',
    '_pipeline_advance_registry_lock':'advance_registry_lock',
    '_pipeline_advance_inflight':'advance_inflight', '_pipeline_advance_cancel':'advance_cancel',
    '_pipeline_recommendation_lock':'recommendation_lock',
    '_pipeline_recommendation_inflight':'recommendation_inflight',
}
METHODS={name:name for name in ('load_pipeline_task','save_pipeline_task',
    'schedule_pipeline_advance','advance_pipeline_task_guarded')}
METHODS.update({'_run_pipeline_auto_agent_step':'run_auto_agent', '_run_pipeline_advance':'run_advance',
    '_run_pipeline_recommendation_pregen':'run_recommendation'})

@contextmanager
def patch_pipeline_capability(api,name,value,**kwargs):
    owner=api._pipeline_execution
    with ExitStack() as stack:
        replacement=stack.enter_context(patch.object(api,name,value,**kwargs))
        if name in RUNTIME_FIELDS:
            stack.enter_context(patch.object(owner.persistence.runtime,RUNTIME_FIELDS[name],replacement))
        else:
            stack.enter_context(patch.object(owner,METHODS[name],replacement))
        yield replacement

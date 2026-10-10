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


def assert_native_query_relay(test, api, port, name):
    """Finite witnesses for external callbacks of links and task projections."""
    targets={
        ('LinkState','load_auto_optimize_state'):(api._auto_optimization_state_store,'load_auto_optimize_state',('task-A',),{}),
        ('LinkState','save_auto_optimize_state'):(api._auto_optimization_state_store,'save_auto_optimize_state',({},),{}),
        ('LinkState','list_auto_optimize_states'):(api._auto_optimization_state_store,'list_auto_optimize_states',(),{}),
        ('LinkState','auto_optimize_completed_model_id'):(api._auto_optimization_readiness,'auto_optimize_completed_model_id',({},),{}),
        ('LinkState','auto_optimize_stop_capture_for_model_locked'):(api._auto_optimization_readiness,'auto_optimize_stop_capture_for_model_locked',({},'model-A'),{'reason':'fixture'}),
        ('LinkProjection','auto_optimize_phase_name'):(api._auto_optimization_readiness,'auto_optimize_phase_name',({},),{}),
        ('ProjectionMetadata','accessory_lookup_by_id'):(api._accessory_lookup,'accessory_lookup_by_id',({},),{}),
        ('ProjectionMetadata','resolve_accessory_id'):(api._accessory_selection,'resolve_accessory_id',({},'accessory-A'),{}),
        ('ProjectionResources','public_path_sanitized'):(api._service_paths,'public_path_sanitized',('fixture',),{}),
    }
    key=(type(port).__name__,name)
    from canonical_application_source_contract import verify_actual_sources
    if key not in targets and key not in {('LinkProjection','ai_detection_task_model_id'),('ProjectionMetadata','accessory_material_type')}:return False
    verify_actual_sources()
    selected=getattr(port,name)()
    result=object()
    if key==('LinkProjection','ai_detection_task_model_id'):
        from local_inspection_service.runtime.wiring import training_pipeline
        with patch.object(training_pipeline,'_detection_task_model_id',autospec=True,return_value=result) as receiver:
            test.assertIs(selected('task-A'),result)
            receiver.assert_called_once_with('task-A',api._default_application.values.AI_DETECTION_TASK_PREFIX)
    elif key==('ProjectionMetadata','accessory_material_type'):
        with patch.object(api._accessory_policy,'accessory_material_type',autospec=True,return_value=result) as receiver:
            test.assertIs(selected({}),result)
            receiver.assert_called_once_with({})
    else:
        owner,method,args,kwargs=targets[key]
        with patch.object(type(owner),method,autospec=True,return_value=result) as receiver:
            test.assertIs(selected(*args,**kwargs),result)
            receiver.assert_called_once_with(owner,*args,**kwargs)
            test.assertIs(receiver.call_args.args[0],owner)
    return True

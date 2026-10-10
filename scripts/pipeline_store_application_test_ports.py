"""Finite external persistence ports for original pipeline store regressions."""
from dataclasses import replace
from unittest.mock import patch


def bind_pipeline_stores(api,stack):
    graph=api._default_application.training_pipeline._pipeline_persistence
    for store in (graph.tasks,graph.state):stack.enter_context(patch.object(store,'repository',lambda:api.runtime_postgres_repository_or_none()))
    stack.enter_context(patch.object(graph.tasks,'resolver',lambda:api.resolve_model_profiles))
    stack.enter_context(patch.object(graph.tasks,'paths',replace(graph.tasks.paths,data=lambda:api.DATA_DIR,tasks=lambda:api.PIPELINE_TASKS_PATH)))
    stack.enter_context(patch.object(graph.state,'paths',replace(graph.state.paths,data=lambda:api.DATA_DIR,state=lambda:api.PIPELINE_STATE_PATH)))
    stack.enter_context(patch.object(graph.tasks,'rows',replace(graph.tasks.rows,encode=lambda task:api.pipeline_task_row(task),decode=lambda:api.row_raw_json_list)))
    stack.enter_context(patch.object(graph.state,'rows',replace(graph.state.rows,encode=lambda:api.pipeline_state_rows,decode=lambda:api.pipeline_state_from_rows)))


def assert_default_pipeline_stores(api):
    import unittest
    from auto_optimization_test_ports import assert_native_relay
    from canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.pipeline.persistence_composition import PipelinePersistence
    from local_inspection_service.pipeline.task_store import PipelineTaskStore
    from local_inspection_service.pipeline.state_store import PipelineStateStore
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    from local_inspection_service.storage import runtime_records
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;g=app.training_pipeline;owner=g._pipeline_persistence;tasks,states=owner.tasks,owner.state;item,other=object(),object()
    for value,kind in ((owner,PipelinePersistence),(tasks,PipelineTaskStore),(states,PipelineStateStore)):case.assertIs(type(value),kind)
    for alias,value in (('_pipeline_persistence',owner),('_pipeline_task_store',tasks),('_pipeline_state_store',states),('_pipeline_runtime',owner.runtime)):case.assertIs(getattr(api,alias),value)
    case.assertIs(states.guard(),owner.runtime.state_lock);case.assertIsNot(owner.runtime.state_lock,owner.runtime.task_lock)
    for store in (tasks,states):assert_native_relay(case,store.repository,(app.infrastructure._runtime_repository_access,'runtime_postgres_repository_or_none',(),{},(),{}))
    assert_native_relay(case,tasks.resolver(),(app.infrastructure._model_profile_configuration,'resolve_model_profiles',(),{},(),{}))
    for selected,name in ((tasks.paths.data,'DATA_DIR'),(states.paths.data,'DATA_DIR'),(tasks.paths.tasks,'PIPELINE_TASKS_PATH'),(states.paths.state,'PIPELINE_STATE_PATH')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)
        case.assertIs(selected(),original)
    for getter,name in ((tasks.rows.decode,'row_raw_json_list'),(states.rows.encode,'pipeline_state_rows'),(states.rows.decode,'pipeline_state_from_rows')):case.assertIs(getter(),getattr(runtime_records,name))
    with patch.object(wiring,'pipeline_task_row',return_value=other) as spy:case.assertIs(tasks.rows.encode(item),other);spy.assert_called_once_with(item);case.assertIs(spy.call_args.args[0],item)
    for getter,name,args,kw in ((tasks.rows.decode,'row_raw_json_list',(item,),{}),(states.rows.encode,'pipeline_state_rows',(item,),{'updated_at':other}),(states.rows.decode,'pipeline_state_from_rows',(item,),{})):
        with patch.object(wiring,name,return_value=other) as spy:
            case.assertIs(getter()(*args,**kw),other);spy.assert_called_once_with(*args,**kw);case.assertIs(spy.call_args.args[0],item)

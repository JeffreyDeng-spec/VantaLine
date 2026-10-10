"""Finite record and lifecycle test dependencies; native runtime remains owned."""
from dataclasses import replace
from unittest.mock import patch,Mock
from contextlib import contextmanager

@contextmanager
def _frozen_slot(owner,name,value):
    previous=getattr(owner,name)
    try:object.__setattr__(owner,name,value);yield
    finally:object.__setattr__(owner,name,previous)


def bind_training_records(api,stack,*,lifecycle=False):
    state=api._default_application.training_pipeline._training_state_workflows;records=state.records
    for field,value in {'repository':lambda:api.runtime_postgres_repository_or_none(),'directory':lambda:api.TRAINING_TASKS_DIR,'resolver':lambda:api.resolve_model_profiles,'invalidate':lambda key:api.store_read_cache_invalidate(key),'enrich':lambda *args:api.enrich_record_audit_fields(*args)}.items():stack.enter_context(patch.object(records,field,value))
    stack.enter_context(patch.object(records,'rows',replace(records.rows,encode=lambda:api.training_task_row,decode=lambda:api.row_raw_json_list,identifier=lambda path:api.file_stem_identifier(path))))
    if lifecycle:
        task=state.lifecycle
        stack.enter_context(patch.object(task,'writes',replace(task.writes,repository=lambda:api.runtime_postgres_repository_or_none(),invalidate=lambda key:api.store_read_cache_invalidate(key),row=lambda *args,**kw:api.training_task_row(*args,**kw))))
        stack.enter_context(patch.object(task,'require_access',lambda *args,**kw:api.require_record_access(*args,**kw)))
        stack.enter_context(patch.object(state.views,'access',replace(state.views.access,enrich=lambda task:api.enrich_record_audit_fields(task),sanitize=lambda:api.public_path_sanitized,visible=lambda record,user,target:api.record_visible_to_user(record,user,target))))


def assert_default_training_records(api,*,lifecycle=False):
    import unittest
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.training.record_store import TrainingRecordStore
    from local_inspection_service.training.task_lifecycle import TrainingTaskLifecycle
    from local_inspection_service.training.task_views import TrainingTaskViews
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;state=app.training_pipeline._training_state_workflows;records=state.records;infra=app.infrastructure;item,other=object(),object()
    case.assertIs(type(records),TrainingRecordStore);case.assertIs(api._training_records,records);case.assertIs(api._training_state_workflows,state);case.assertIs(records.guard(),state.runtime.lock)
    assert_native_relay(case,records.repository,(infra._runtime_repository_access,'runtime_postgres_repository_or_none',(),{},(),{}))
    assert_native_relay(case,records.resolver(),(infra._model_profile_configuration,'resolve_model_profiles',(),{},(),{}))
    for selected,name,args in ((records.invalidate,'store_read_cache_invalidate',('synthetic',)),(records.enrich,'enrich_record_audit_fields',(item,)),(records.enrich,'enrich_record_audit_fields',(item,other))):
        receiver=Mock(return_value=other)
        with _frozen_slot(infra,name,receiver):case.assertIs(selected(*args),other);receiver.assert_called_once_with(*args)
    from local_inspection_service.storage.runtime_records import training_task_row,row_raw_json_list
    from local_inspection_service.runtime.wiring import training_pipeline
    case.assertIs(records.rows.encode(),training_task_row);case.assertIs(records.rows.decode(),row_raw_json_list)
    with patch.object(training_pipeline,'file_stem_identifier',autospec=True,return_value=other) as identifier:
        case.assertIs(records.rows.identifier(item),other);identifier.assert_called_once_with(item)
    original=app.values.TRAINING_TASKS_DIR;case.assertIs(records.directory(),original)
    try:object.__setattr__(app.values,'TRAINING_TASKS_DIR',other);case.assertIs(records.directory(),other)
    finally:object.__setattr__(app.values,'TRAINING_TASKS_DIR',original)
    if lifecycle:
        task=state.lifecycle;case.assertIs(type(task),TrainingTaskLifecycle);case.assertIs(type(state.views),TrainingTaskViews);case.assertIs(api._training_lifecycle,task);case.assertIs(api._training_views,state.views)
        with patch.object(training_pipeline,'training_task_row',autospec=True,return_value=other) as encoder:
            case.assertIs(task.writes.row(item,fallback_id='synthetic'),other);encoder.assert_called_once_with(item,fallback_id='synthetic')
        assert_native_relay(case,task.writes.repository,(infra._runtime_repository_access,'runtime_postgres_repository_or_none',(),{},(),{}))
        for selected,name,args,kw in ((task.writes.invalidate,'store_read_cache_invalidate',('synthetic',),{}),(task.require_access,'require_record_access',(item,other),{'write':True}),(state.views.access.enrich,'enrich_record_audit_fields',(item,),{}),(state.views.access.visible,'record_visible_to_user',(item,other,'selected'),{})):
            receiver=Mock(return_value=other)
            with _frozen_slot(infra,name,receiver):case.assertIs(selected(*args,**kw),other);receiver.assert_called_once_with(*args,**kw)
        assert_native_relay(case,state.views.access.sanitize(),(infra._service_paths,'public_path_sanitized',(item,),{},(item,),{}))

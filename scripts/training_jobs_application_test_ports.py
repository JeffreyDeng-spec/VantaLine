"""Finite task query access and registered image action fixtures."""
from dataclasses import replace
from unittest.mock import patch,Mock
from scripts.training_resource_application_test_ports import read_cell,replace_read_cell


def bind_training_jobs(api,stack):
    graph=api._default_application.training_pipeline;query=graph._training_jobs_query;mutation=graph._training_task_mutations
    stack.enter_context(patch.object(query,'access',replace(query.access,current=lambda:api.current_auth_user(),is_admin=lambda user:api.user_is_admin(user),require=lambda *args,**kw:api.require_record_access(*args,**kw))))
    stack.enter_context(patch.object(query,'image_list',lambda **kw:api.list_codex_image_jobs(**kw)));stack.enter_context(patch.object(query,'active',lambda:api.IMAGE_JOB_ACTIVE_STATUSES))
    stack.enter_context(patch.object(mutation,'current',lambda:api.current_auth_user()));stack.enter_context(patch.object(mutation,'require',lambda *args,**kw:api.require_record_access(*args,**kw)))
    actions=read_cell(api.stop_image_job,'actions').cell_contents
    stack.enter_context(replace_read_cell(api.stop_image_job,'actions',replace(actions,job=lambda job,action:api.update_codex_image_job(job,action),candidate=lambda candidate,action:api.update_codex_image_candidate(candidate,action))))


def assert_default_training_jobs(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.training_records_application_test_ports import _frozen_slot
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.training.jobs_query import TrainingJobsQuery
    from local_inspection_service.training.task_mutations import TrainingTaskMutations
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    from local_inspection_service.runtime.wiring import http_registration
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;infra=app.infrastructure;query=graph._training_jobs_query;mutation=graph._training_task_mutations;state=graph._training_account_state.records;item,other=object(),object()
    case.assertIs(type(query),TrainingJobsQuery);case.assertIs(type(mutation),TrainingTaskMutations);case.assertIs(api._training_jobs_query,query);case.assertIs(api._training_task_mutations,mutation)
    for selected,name,args in ((query.access.current,'current_auth_user',()),(query.access.require,'require_record_access',(item,other)),(mutation.current,'current_auth_user',()),(mutation.require,'require_record_access',(item,other))):
        receiver=Mock(return_value=other)
        with _frozen_slot(infra,name,receiver):case.assertIs(selected(*args),other);receiver.assert_called_once_with(*args)
    with patch.object(wiring,'user_is_admin',return_value=other) as receiver:case.assertIs(query.access.is_admin(item),other);receiver.assert_called_once_with(item)
    original=app.values.IMAGE_JOB_ACTIVE_STATUSES;case.assertIs(query.active(),original)
    try:object.__setattr__(app.values,'IMAGE_JOB_ACTIVE_STATUSES',other);case.assertIs(query.active(),other)
    finally:object.__setattr__(app.values,'IMAGE_JOB_ACTIVE_STATUSES',original)
    from local_inspection_service.training.task_lifecycle import training_task_uses_worker
    case.assertIs(query.training.uses_worker,training_task_uses_worker)
    with patch.object(wiring.time,'time',return_value=other) as receiver:case.assertIs(mutation.clock(),other);receiver.assert_called_once_with()
    for selected,method,args,kw in ((query.training.find,'find_training_task',(item,),{}),(query.training.public,'public_training_task',(item,),{}),(query.training.refresh,'public_refreshed_training_task',(item,),{'allow_remote_refresh':False}),(query.training_list,'list_training_tasks',(),{'user':item,'target_user_id':other}),(mutation.records.find,'find_training_task',(item,),{}),(mutation.records.save,'save_training_task',(item,),{}),(mutation.records.public,'public_training_task',(item,),{}),(mutation.records.delete,'delete_training_task_record',(item,other),{}),(mutation.records.list,'list_training_tasks',(),{'user':item})):
        assert_native_relay(case,selected,(state,method,args,kw,args,kw))
    assert_native_relay(case,query.image_list,(app.inspection._image_job_management,'list_codex_image_jobs',(),{'user':item,'target_user_id':other},(item,other),{}))
    actions=read_cell(api.stop_image_job,'actions').cell_contents
    for name in ('retry_image_job','delete_image_job','stop_image_job_candidate','delete_image_job_candidate'):case.assertIs(read_cell(getattr(api,name),'actions').cell_contents,actions)
    for selected,method in ((actions.job,'update_codex_image_job'),(actions.candidate,'update_codex_image_candidate')):assert_native_relay(case,selected,(app.inspection._image_job_management,method,(item,other),{},(item,other),{}))
    for selected,name,field in ((api.image_jobs,'query',query),(api.image_job,'query',query),(api.update_training_task_endpoint,'mutations',mutation),(api.delete_training_task_endpoint,'mutations',mutation)):case.assertIs(read_cell(selected,name).cell_contents,field)

    receiver=Mock(return_value=other)
    with _frozen_slot(infra,'require_record_access',receiver):case.assertIs(mutation.require(item,other,write=True),other);receiver.assert_called_once_with(item,other,write=True)
    assert_native_relay(case,query.image_list,(app.inspection._image_job_management,'list_codex_image_jobs',(),{'user':item},(item,None),{}))

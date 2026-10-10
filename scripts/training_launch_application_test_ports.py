"""Finite launch and status query external capabilities."""
from dataclasses import replace
from unittest.mock import patch,Mock

DIRECT={'load':'load_config','scope':'scope_config_for_user','merge':'merge_scoped_accessory_updates','save':'save_config'}


def bind_training_launch(api,stack):
    graph=api._default_application.training_pipeline;launch=graph._training_launch_submission;status=graph._training_status_query
    stack.enter_context(patch.object(launch,'current',lambda:api.current_auth_user()))
    stack.enter_context(patch.object(launch,'config',replace(launch.config,**{field:(lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)) for field,name in DIRECT.items()},ensure=lambda:api.ensure_training_assets_for_request)))
    stack.enter_context(patch.object(launch,'inputs',replace(launch.inputs,selected=lambda:api.selected_accessories)))
    stack.enter_context(patch.object(launch,'physical_size',lambda:api.BACKGROUND_SIZE_MM))
    stack.enter_context(patch.object(status,'current',lambda:api.current_auth_user()));stack.enter_context(patch.object(status,'is_admin',lambda user:api.user_is_admin(user)));stack.enter_context(patch.object(status,'scope',lambda:api.scope_config_for_user))


def assert_default_training_launch(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.training_records_application_test_ports import _frozen_slot
    from local_inspection_service.training.launch_submission import TrainingLaunchSubmission
    from local_inspection_service.training.status_query import TrainingStatusQuery
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;infra=app.infrastructure;task=graph._training_task_workflows;launch=task.launch_submission;status=task.status_query;item,other,third=object(),object(),object()
    case.assertIs(type(launch),TrainingLaunchSubmission);case.assertIs(type(status),TrainingStatusQuery)
    case.assertIs(api._training_launch_submission,launch);case.assertIs(api._training_status_query,status);case.assertIs(graph._training_launch_submission,launch);case.assertIs(graph._training_status_query,status)
    original=app.values.BACKGROUND_SIZE_MM;case.assertIs(launch.physical_size(),original)
    try:object.__setattr__(app.values,'BACKGROUND_SIZE_MM',other);case.assertIs(launch.physical_size(),other)
    finally:object.__setattr__(app.values,'BACKGROUND_SIZE_MM',original)
    for selected in (launch.current,status.current):
        receiver=Mock(return_value=other)
        with _frozen_slot(infra,'current_auth_user',receiver):case.assertIs(selected(),other);receiver.assert_called_once_with()
    for selected in (launch.clock,status.is_admin):
        target,name,args=(wiring.time,'time',()) if selected is launch.clock else (wiring,'user_is_admin',(item,))
        with patch.object(target,name,return_value=other) as receiver:case.assertIs(selected(*args),other);receiver.assert_called_once_with(*args)
    for selected,target,method,args,kw,expected,expected_kw in (
        (launch.config.load,infra._app_configuration,'load_config',(),{},(),{}),
        (launch.config.save,infra._app_configuration,'save_config',(item,),{},(item,),{}),
        (launch.config.scope,infra._account_projections,'scope_config_for_user',(item,other),{},(item,other,None),{}),
        (launch.config.ensure(),graph._training_asset_preparation,'ensure_training_assets_for_request',(item,other,third,['selected']),{},None,{}),
        (launch.config.set_state,graph._training_account_state,'set_training_state_for_user',(item,other,third),{},(item,other,third),{}),
        (launch.config.merge,infra._account_projections,'merge_scoped_accessory_updates',(item,other,third),{},(item,other,third),{}),
        (launch.inputs.selected(),app.inspection._accessory_selection,'selected_accessories',(item,other),{},(item,other),{}),
        (launch.inputs.dataset(),task.dataset_input,'dataset_for_training',(item,),{'user':other},(item,other),{}),
        (launch.inputs.approve,task,'validate_approved_preview',(item,other,third),{'user':item},(item,other,third),{'user':item}),
        (launch.enqueue,graph._training_execution,'enqueue_training_task',(item,other,third),{'dataset':item},(item,other,third),{'dataset':item}),
        (status.load,infra._app_configuration,'load_config',(),{},(),{}),
        (status.scope(),infra._account_projections,'scope_config_for_user',(item,other,third),{},(item,other,third),{}),
        (status.filtered,task,'filtered_training_state',(item,other,third),{},(item,other,third),{})):
        if expected is None:expected=args
        assert_native_relay(case,selected,(target,method,args,kw,expected,expected_kw))

    case.assertIs(launch.inputs.dataset().__self__,task);case.assertIs(launch.inputs.dataset().__func__,type(task).dataset_for_training)

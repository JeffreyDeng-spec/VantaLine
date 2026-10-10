"""Native training account and completion edges with finite synthetic ports."""
from dataclasses import replace
from unittest.mock import patch,Mock


def bind_training_account(api,stack):
    graph=api._default_application.training_pipeline._training_persistence_graph
    users=graph.account.users;candidates=graph.candidates
    stack.enter_context(patch.object(users,'defaults',lambda:api.DEFAULT_CONFIG['training']))
    stack.enter_context(patch.object(users,'access',replace(users.access,owner=lambda record:api.record_owner_id(record),visible=lambda record,user,target=None:api.record_visible_to_user(record,user,target),admin=lambda user:api.user_is_admin(user),current_owner=lambda:api.current_owner_fields())))
    stack.enter_context(patch.object(graph.models,'specs',lambda:api.list_trained_model_specs()))
    stack.enter_context(patch.object(graph.pipeline.training,'models',replace(graph.pipeline.training.models,link=lambda task:api.link_pipeline_trained_model(task))))
    stack.enter_context(patch.object(graph.pipeline.training,'clean_id',lambda:api.sanitize_ai_detection_task_id))
    stack.enter_context(patch.object(graph.pipeline.training,'normalize_method',lambda:api.normalize_pipeline_detection_method))
    stack.enter_context(patch.object(candidates,'clean_id',lambda value:api.sanitize_ai_detection_task_id(value)))
    stack.enter_context(patch.object(candidates,'guard',lambda:api._auto_optimize_lock))
    stack.enter_context(patch.object(candidates,'records',replace(candidates.records,load=lambda identity:api.load_auto_optimize_state(identity),save=lambda state:api.save_auto_optimize_state(state))))
    stack.enter_context(patch.object(candidates,'stop_capture',lambda state,model,**kw:api.auto_optimize_stop_capture_for_model_locked(state,model,**kw)))


def assert_default_training_account(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.training_records_application_test_ports import _frozen_slot
    from local_inspection_service.training.user_state import TrainingUserState
    from local_inspection_service.training.task_models import TrainingTaskModels
    from local_inspection_service.detection.training_candidate_sync import TrainingCandidateSync
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;assembly=app.training_pipeline;infra=app.infrastructure;graph=assembly._training_persistence_graph;users=graph.account.users;candidates=graph.candidates;item,other=object(),object()
    case.assertIs(type(users),TrainingUserState);case.assertIs(type(graph.models),TrainingTaskModels);case.assertIs(type(candidates),TrainingCandidateSync)
    case.assertIs(api._training_user_state,users);case.assertIs(api._training_task_models,graph.models);case.assertIs(api._training_candidate_sync,candidates)
    case.assertIs(api._training_account_state,graph.account);case.assertIs(api._training_persistence_graph,graph);case.assertIs(api._pipeline_training_sync,graph.pipeline.training);case.assertIs(candidates.guard(),assembly._auto_optimize_lock)
    original=app.values.DEFAULT_CONFIG;case.assertIs(users.defaults(),original['training'])
    try:object.__setattr__(app.values,'DEFAULT_CONFIG',{'training':other});case.assertIs(users.defaults(),other)
    finally:object.__setattr__(app.values,'DEFAULT_CONFIG',original)
    for selected,name,args in ((users.access.owner,'record_owner_id',(item,)),(users.access.visible,'record_visible_to_user',(item,other,'selected')),(users.access.current_owner,'current_owner_fields',())):
        receiver=Mock(return_value=other)
        with _frozen_slot(infra,name,receiver):case.assertIs(selected(*args),other);receiver.assert_called_once_with(*args)
    receiver=Mock(return_value=other)
    with _frozen_slot(infra,'record_visible_to_user',receiver):case.assertIs(users.access.visible(item,other),other);receiver.assert_called_once_with(item,other,None)
    from local_inspection_service.runtime.wiring import training_pipeline
    from local_inspection_service.detection.task_identity import sanitize_ai_detection_task_id
    case.assertIs(graph.pipeline.training.clean_id(),sanitize_ai_detection_task_id)
    assert_native_relay(case,graph.pipeline.training.normalize_method(),(assembly._pipeline_task_metadata,'normalize_pipeline_detection_method',(item,),{},(item,),{}))
    with patch.object(training_pipeline,'sanitize_ai_detection_task_id',return_value=other) as receiver:case.assertIs(candidates.clean_id(item),other);receiver.assert_called_once_with(item)
    with patch.object(training_pipeline,'user_is_admin',return_value=other) as receiver:case.assertIs(users.access.admin(item),other);receiver.assert_called_once_with(item)
    for selected,target,method,args,kw,forwarded in ((graph.models.specs,assembly._trained_model_catalog,'list_trained_model_specs',(),{},(None,)),(graph.pipeline.training.models.link,assembly._pipeline_trained_model_link,'link_pipeline_trained_model',(item,),{},(item,)),(candidates.records.load,assembly._auto_optimization_state_store,'load_auto_optimize_state',('synthetic',),{},('synthetic',)),(candidates.records.save,assembly._auto_optimization_state_store,'save_auto_optimize_state',(item,),{},(item,)),(candidates.stop_capture,assembly._auto_optimization_readiness,'auto_optimize_stop_capture_for_model_locked',(item,'model'),{'reason':'synthetic'},(item,'model'))):
        assert_native_relay(case,selected,(target,method,args,kw,forwarded,kw))

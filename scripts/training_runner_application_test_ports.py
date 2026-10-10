"""Narrow external runner/submission ports; owned records and model pin stay native."""
from dataclasses import replace
from unittest.mock import patch,Mock

DIRECT=(('datasets',{'mode':'training_executor_mode','generate':'generate_training_dataset','runpod':'run_runpod_training_task','remote':'run_remote_training_task'}),('local',{'base_model':'detect_base_model','device':'yolo_inference_device','cli':'yolo_cli_command','progress':'parse_yolo_epoch_progress'}))
GETTERS=(('paths',{'resolve':'resolve_service_path','tasks':'TRAINING_TASKS_DIR','app':'APP_DIR','output':'output_write_dir_for_owner'}),('local',{'warmup':'start_yolo_warmup'}))


def bind_training_runner(api,stack):
    graph=api._default_application.training_pipeline;runner=graph._training_execution.runner;submission=graph._training_execution.submission
    for attribute,mapping in DIRECT:
        stack.enter_context(patch.object(runner,attribute,replace(getattr(runner,attribute),**{field:(lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)) for field,name in mapping.items()})))
    for attribute,mapping in GETTERS:
        stack.enter_context(patch.object(runner,attribute,replace(getattr(runner,attribute),**{field:(lambda _name=name:getattr(api,_name)) for field,name in mapping.items()})))
    stack.enter_context(patch.object(submission,'policy',replace(submission.policy,estimate=lambda:api.training_estimate,uses_ocr=lambda item:api.accessory_uses_ocr(item))))
    stack.enter_context(patch.object(submission,'identity',replace(submission.identity,user=lambda:api._request_user.get(),owner=lambda:api.current_owner_fields(),background=lambda:api.selected_background_set_id)))


def assert_default_training_runner(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.training.native_execution_composition import TrainingExecution
    from local_inspection_service.training.runner import TrainingRunner
    from local_inspection_service.training.submission import TrainingSubmission
    from local_inspection_service.runtime.wiring import training_pipeline
    from scripts.training_records_application_test_ports import _frozen_slot
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;execution=graph._training_execution;runner=execution.runner;submission=execution.submission;item,other,third=object(),object(),object()
    case.assertIs(type(execution),TrainingExecution);case.assertIs(type(runner),TrainingRunner);case.assertIs(type(submission),TrainingSubmission)
    case.assertIs(runner.files,app.artifacts.files)
    case.assertIs(api._training_execution,execution);case.assertIs(api._training_runner,runner);case.assertIs(api._training_submission,submission);case.assertIs(execution.account,graph._training_account_state);case.assertIs(execution.state,graph._training_state_workflows);case.assertIs(submission.runtime,execution.state.runtime)
    case.assertIs(submission.threads.records(),execution.state.runtime.threads);case.assertIs(submission.policy.estimate(),training_pipeline.training_estimate);case.assertIs(runner.local.start(),training_pipeline.subprocess.Popen)
    assert_native_relay(case,runner.paths.resolve(),(app.infrastructure._service_paths,'resolve_service_path',(item,),{},(item,),{'for_write':False}))
    assert_native_relay(case,runner.paths.resolve(),(app.infrastructure._service_paths,'resolve_service_path',(item,),{'for_write':True},(item,),{'for_write':True}))
    assert_native_relay(case,runner.paths.output(),(app.infrastructure._service_paths,'output_write_dir_for_owner',(item,other),{},(item,other),{}))
    for selected,name in ((runner.paths.tasks,'TRAINING_TASKS_DIR'),(runner.paths.app,'APP_DIR')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)
    receiver=Mock(return_value=other)
    with _frozen_slot(app.infrastructure,'current_owner_fields',receiver):case.assertIs(submission.identity.owner(),other);receiver.assert_called_once_with()
    token=app.infrastructure._request_user.set(item)
    try:case.assertIs(submission.identity.user(),item)
    finally:app.infrastructure._request_user.reset(token)
    for selected,method in ((runner.records.load(),'load_training_task'),(runner.records.update_provider(),'update_training_task'),(submission.threads.target(),'run_training_task')):
        case.assertIs(selected.__self__,execution);case.assertIs(selected.__func__,getattr(TrainingExecution,method))
    with patch.object(runner,'run_training_task',return_value=other) as receiver:case.assertIs(submission.threads.target()(item),other);receiver.assert_called_once_with(item)
    with _frozen_slot(app.inspection,'detect_base_model',Mock(return_value=other)):
        case.assertIs(runner.local.base_model(),other);app.inspection.detect_base_model.assert_called_once_with()
    assert_default_training_warmup(api,runner.local.warmup())
    assert_native_relay(case,runner.datasets.remote,(graph._remote_training,'run_remote_training_task',(item,other,third),{},(item,other,third),{}))
    for selected,target,method,args,kw,forwarded in ((runner.records.find,execution.state,'find_training_task',(item,),{},(item,)),(runner.records.path,execution.state,'training_task_path',(item,),{},(item,)),(runner.records.load(),execution.state,'load_training_task',(item,),{},(item,)),(runner.records.update_provider(),execution.state,'update_training_task',(item,),{'status':other},(item,)),(runner.records.sync,execution.account,'sync_training_state_from_task',(item,),{},(item,)),(runner.datasets.mode,graph._training_executor_settings,'training_executor_mode',(),{},()),(runner.datasets.generate,graph._training_dataset_generator,'generate_training_dataset',(item,),{},(item,)),(runner.datasets.runpod,graph._runpod_flow,'run_runpod_training_task',(item,other,third),{},(item,other,third)),(submission.identity.background(),graph._background_selection,'selected_background_set_id',(item,other),{},(item,other,None)),(submission.records.save,execution.state,'save_training_task',(item,),{},(item,)),(submission.records.public,execution.state,'public_training_task',(item,),{},(item,))):
        assert_native_relay(case,selected,(target,method,args,kw,forwarded,kw))
    with patch.object(training_pipeline._accessory_policy,'accessory_uses_ocr',return_value=other) as receiver:case.assertIs(submission.policy.uses_ocr(item),other);receiver.assert_called_once_with(item)
    for selected,name,args in ((runner.local.device,'yolo_inference_device',()),(runner.local.cli,'yolo_cli_command',()),(runner.local.progress,'parse_yolo_epoch_progress',(item,17))):
        with patch.object(training_pipeline,name,return_value=other) as receiver:case.assertIs(selected(*args),other);receiver.assert_called_once_with(*args)


def assert_default_training_warmup(api,selected):
    import unittest
    case=unittest.TestCase();owner=api._default_application.inspection._yolo_warmup_runtime;item,other=object(),object()
    for args,forwarded in (((),('startup',None)),(('synthetic',item),('synthetic',item))):
        with patch.object(type(owner),'start_yolo_warmup',autospec=True,return_value=other) as receiver:
            case.assertIs(selected(*args),other);case.assertEqual(receiver.call_count,1);actual=receiver.call_args
            case.assertEqual(len(actual.args),3);case.assertIs(actual.args[0],owner)
            for got,wanted in zip(actual.args[1:],forwarded):case.assertIs(got,wanted)
            case.assertEqual(set(actual.kwargs),{'worker'})
            with patch.object(type(owner),'yolo_warmup_worker',autospec=True,return_value=other) as worker:
                case.assertIs(actual.kwargs['worker']()('synthetic',item),other);worker.assert_called_once_with(owner,'synthetic',item)

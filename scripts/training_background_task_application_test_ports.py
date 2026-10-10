"""Finite background execution capabilities; native pin and lifecycle stay active."""
from dataclasses import replace
from unittest.mock import patch,Mock


def bind_training_background_tasks(api,stack):
    graph=api._default_application.training_pipeline;codex=graph._background_codex_generation;thread=graph._background_codex_thread;runner=graph._background_task_runner;submission=graph._background_task_submission
    stack.enter_context(patch.object(codex,'paths',replace(codex.paths,logs=lambda:api.IMAGE_WORKER_LOG_DIR,root=lambda:api.ROOT)))
    for owner in (codex,thread):stack.enter_context(patch.object(owner,'name',lambda identifier:api.safe_name(identifier)))
    stack.enter_context(patch.object(thread,'target',lambda:api.run_codex_background_generation))
    stack.enter_context(patch.object(runner,'records',replace(runner.records,find=lambda identifier:api.find_training_task(identifier),path=lambda identifier:api.training_task_path(identifier),load=lambda:api.load_training_task,update_provider=lambda:api.update_training_task)))
    stack.enter_context(patch.object(graph._training_state_workflows,'find_training_task',lambda identifier:api.find_training_task(identifier)))
    stack.enter_context(patch.object(runner,'generation',replace(runner.generation,sets=lambda:api.BACKGROUND_SETS_DIR,safe=lambda identifier:api.safe_background_set_id(identifier),update_provider=lambda:api.update_background_set_manifest,local=lambda *args:api.create_background_variants_from_source(*args),codex=lambda *args:api.run_codex_background_generation(*args),images=lambda path:api.image_file_list(path))))
    stack.enter_context(patch.object(submission,'records',replace(submission.records,save=lambda task:api.save_training_task(task),public=lambda task:api.public_training_task(task))))
    stack.enter_context(patch.object(submission,'threads',replace(submission.threads,target=lambda:api.run_background_set_task,records=lambda:api._training_task_threads)))
    stack.enter_context(patch.object(submission,'owner',lambda:api.current_owner_fields()))


def assert_default_training_background_tasks(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.training_records_application_test_ports import _frozen_slot
    from local_inspection_service.training.background_codex import CodexBackgroundGeneration,CodexBackgroundThread
    from local_inspection_service.training.background_task_runner import BackgroundTaskRunner
    from local_inspection_service.training.background_task_submission import BackgroundTaskSubmission
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;codex=graph._background_codex_generation;thread=graph._background_codex_thread;runner=graph._background_task_runner;submission=graph._background_task_submission;state=graph._training_state_workflows;item,other,third,fourth=object(),object(),object(),object()
    for name,kind in (('_background_codex_generation',CodexBackgroundGeneration),('_background_codex_thread',CodexBackgroundThread),('_background_task_runner',BackgroundTaskRunner),('_background_task_submission',BackgroundTaskSubmission)):case.assertIs(type(getattr(graph,name)),kind);case.assertIs(getattr(api,name),getattr(graph,name))
    for owner in (codex,runner):case.assertIs(owner.files,app.artifacts.files)
    case.assertIs(submission.runtime,graph._training_task_runtime);case.assertIs(submission.threads.records(),graph._training_task_runtime.threads);case.assertIs(codex.start(),wiring.subprocess.Popen);case.assertIs(thread.create(),wiring.threading.Thread)
    case.assertIs(runner.run_background_set_task.__wrapped__.__self__,runner);case.assertIs(runner.run_background_set_task.__wrapped__.__func__,type(runner).run_background_set_task)
    with patch.object(runner,'run_background_set_task',return_value=other) as receiver:case.assertIs(submission.threads.target()(item),other);receiver.assert_called_once_with(item)
    scope=thread.runtime.scope;case.assertIs(scope.__self__,app.infrastructure._runtime_repositories);case.assertIs(scope.__func__,type(app.infrastructure._runtime_repositories).thread_scope)
    for selected,name in ((codex.paths.logs,'IMAGE_WORKER_LOG_DIR'),(codex.paths.root,'ROOT'),(runner.generation.sets,'BACKGROUND_SETS_DIR')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)
    for selected,target,method,args,kw,expected,expected_kw in ((thread.target(),codex,'run_codex_background_generation',(item,other,third),{'count':fourth},(item,other,third,fourth),{}),(runner.records.find,state,'find_training_task',(item,),{},(item,),{}),(runner.records.path,state,'training_task_path',(item,),{},(item,),{}),(runner.records.load(),state,'load_training_task',(item,),{},(item,),{}),(runner.records.update_provider(),state,'update_training_task',(item,),{'status':other},(item,),{'status':other}),(runner.generation.update_provider(),graph._background_writes,'update_background_set_manifest',(item,),{'status':other},(item,),{'status':other}),(runner.generation.local,graph._background_variants,'create_background_variants_from_source',(item,other,third),{},(item,other,third),{}),(runner.generation.codex,codex,'run_codex_background_generation',(item,other,third,fourth),{},(item,other,third,fourth),{}),(runner.generation.images,graph._background_image_files,'image_file_list',(item,),{},(item,),{}),(submission.records.save,state,'save_training_task',(item,),{},(item,),{}),(submission.records.public,state,'public_training_task',(item,),{},(item,),{})):
        assert_native_relay(case,selected,(target,method,args,kw,expected,expected_kw))
    for selected,target,name,args in ((codex.which,wiring.shutil,'which',(item,)),(codex.name,wiring,'safe_name',(item,)),(thread.name,wiring,'safe_name',(item,)),(runner.generation.safe,wiring,'safe_background_set_id',(item,)),(runner.clock,wiring.time,'time',()),(submission.clock,wiring.time,'time',()),(submission.uuid,wiring.uuid,'uuid4',())):
        with patch.object(target,name,return_value=other) as receiver:case.assertIs(selected(*args),other);receiver.assert_called_once_with(*args)
    with _frozen_slot(app.infrastructure,'current_owner_fields',lambda:other):case.assertIs(submission.owner(),other)

    updates={name:object() for name in ('status','progress','started_at','completed_at','generated_image_count','error','note')}
    assert_native_relay(case,runner.records.update_provider(),(state,'update_training_task',(item,),updates,(item,),updates))
    updates={name:object() for name in ('status','generation_method','image_count','completed_at','updated_at','error')}
    assert_native_relay(case,runner.generation.update_provider(),(graph._background_writes,'update_background_set_manifest',(item,),updates,(item,),updates))

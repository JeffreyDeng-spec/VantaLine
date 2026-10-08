"""Actual combined training task graph contracts; synthetic models/media only."""
import ast
from dataclasses import replace
import json
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
from training_task_graph_fixtures import (ROOT, build, api_for, account_module, module,
    api_module, web_identity, pipeline_events, TrainingStartRequest, TrainingRuntimeClosed,
    TrainingTaskUpdateRequest, HTTPException, asyncio, hashlib)
from training_task_source_contract import verify_training_task_sources, restore_training_task_root


class TrainingTaskWorkflowsContracts(unittest.TestCase):
    def test_early_account_construction_is_inert_and_failure_does_not_close_runtime(self):
        from training_task_graph_fixtures import (TrainingTaskRuntime, TrainingRecordAccess,
            TrainingRows, TrainingTaskWrites, TrainingViewAccess)
        from local_inspection_service.training.user_state import TrainingStateAccess
        poison=Mock(side_effect=AssertionError('early account selected an external supplier'))
        runtime=TrainingTaskRuntime()
        kwargs=dict(runtime=runtime,storage=TrainingRecordAccess(poison,poison,poison,poison,poison),
            rows=TrainingRows(poison,poison,poison),writes=TrainingTaskWrites(poison,poison,poison),
            require_access=poison,view_access=TrainingViewAccess(poison,poison,poison),
            defaults=poison,legacy_owner=poison,access=TrainingStateAccess(poison,poison,poison,poison),
            configuration=account_module.TrainingConfiguration(poison,poison),sync_pipeline=poison)
        account=account_module.TrainingAccountState(**kwargs)
        poison.assert_not_called()
        self.assertIs(account.records.runtime,runtime)
        error=RuntimeError('user state constructor failed')
        with patch.object(account_module,'TrainingUserState',side_effect=error):
            with self.assertRaises(RuntimeError) as caught:
                account_module.TrainingAccountState(**kwargs)
        self.assertIs(caught.exception,error)
        poison.assert_not_called()
        self.assertEqual(runtime.threads,{})
        self.assertEqual(runtime.submit(lambda launch:'still open'),'still open')
        self.assertTrue(runtime.close(1))

    def test_two_registered_asgi_domains_use_call_time_request_identity(self):
        from concurrent.futures import ThreadPoolExecutor
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from local_inspection_service.training.jobs_api import register, ImageJobActions
        from local_inspection_service.training.launch_api import register_status
        from local_inspection_service.training.jobs_query import JobsReadAccess
        with tempfile.TemporaryDirectory(prefix='training-task-asgi-') as temporary:
            graphs=[build(account,Path(temporary))[0] for account in ('A','B')]
            apis=[api_for(graph,account) for graph,account in zip(graphs,('A','B'))]
            def current():
                user=web_identity.get()
                if user is None:raise HTTPException(401,'authentication required')
                return user
            clients=[]
            for graph,api,account in zip(graphs,apis,('A','B')):
                graph.state.save_training_task({'job_id':'shared','owner_user_id':account,'status':'completed','model_profiles':{}})
                api.jobs_query.access=JobsReadAccess(current,lambda user:user.get('role')=='admin',
                    lambda record,user,**kwargs: None if record['owner_user_id']==user['id'] or user.get('role')=='admin' else (_ for _ in ()).throw(HTTPException(403,'denied')))
                app=FastAPI()
                register(app,api.jobs_query,api.task_mutations,ImageJobActions(Mock(),Mock()))
                register_status(app,api.status_query)
                clients.append(TestClient(app))
            def request(pair):
                index,account=pair
                token=web_identity.set({'id':account,'role':'member'})
                try:
                    response=clients[index].get('/api/image-jobs/shared')
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.json()['owner_user_id'],account)
                    denied=clients[1-index].get('/api/image-jobs/shared')
                    self.assertEqual(denied.status_code,403,denied.text)
                finally:web_identity.reset(token)
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(request,enumerate(('A','B'))))
            for client in clients:
                self.assertEqual(client.get('/api/image-jobs/shared').status_code,401)
            token=web_identity.set({'id':'administrator','role':'admin'})
            try:
                for index,client in enumerate(clients):
                    response=client.get('/api/image-jobs/shared')
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.json()['owner_user_id'],('A','B')[index])
            finally:web_identity.reset(token)
            self.assertIsNone(web_identity.get())
            for graph in graphs:self.assertTrue(graph.state.runtime.close(1))

    def test_parent_inverse_and_fifteen_unchanged_business_services(self):
        verify_training_task_sources()

    def test_wrong_owner_shadow_and_route_mutants_are_rejected(self):
        source=(ROOT/'local_inspection_service/server.py').read_text()
        mutations=(
            ('account=_training_account_state,', 'account=_training_user_state,'),
            ('_training_task_runtime = _training_account_state.records.runtime', '_training_task_runtime = TrainingTaskRuntime()'),
            ('_training_transfer = _training_task_workflows.transfer', '_training_transfer = _training_task_workflows.upload_store'),
            ('_training_launch_api.register_start(app, _training_launch_submission)', '_training_launch_api.register_generate(app, _training_launch_submission)'),
        )
        for old,new in mutations:
            self.assertIn(old,source)
            with self.subTest(mutant=old),self.assertRaises(AssertionError):
                restore_training_task_root(source.replace(old,new,1))
        for name in ('TrainingAccountState','TrainingExecution','TrainingTaskWorkflows','_training_account_state','_training_task_runtime'):
            with self.subTest(shadow=name),self.assertRaises(AssertionError):
                restore_training_task_root(source+'\nimport os as '+name+'\n')

    def test_actual_http_services_isolate_accounts_and_keep_upload_partial_effects(self):
        with tempfile.TemporaryDirectory(prefix='training-task-api-private-') as temporary:
            root=Path(temporary)
            a,*rest_a=build('A',root);b,*rest_b=build('B',root)
            aa=api_for(a,'A');bb=api_for(b,'B')
            assert a.account.users.storage.load()['training_by_user_id']=={}
            with patch.object(a.account.users,'sync_training_state_from_task',side_effect=AssertionError('construction synced')):
                assert api_for(a,'A').account is a.account
            try:
                # Different account/execution identity must fail before any operation.
                from inspect import signature
                kwargs={name:Mock(side_effect=AssertionError('dependency selected')) for name in signature(api_module.TrainingTaskWorkflows).parameters}
                kwargs.update(account=a.account,execution=b)
                api_module.TrainingTaskWorkflows(**kwargs)
                raise AssertionError('mismatched account admitted')
            except ValueError:pass
            for graph,api,account in ((a,aa,'A'),(b,bb,'B')):
                graph.state.save_training_task({'job_id':'shared','status':'completed','owner_user_id':account,'model_profiles':{}})
                assert api.jobs_query.image_job('shared')['owner_user_id']==account
                assert api.jobs_query.image_job('shared')['label']!='image-owned'
            aa.task_mutations.update_training_task_endpoint('shared',TrainingTaskUpdateRequest(label='A-edited'))
            assert a.state.find_training_task('shared')['label']=='A-edited'
            assert b.state.find_training_task('shared').get('label') is None
            foreign={'job_id':'foreign','status':'queued','owner_user_id':'other','model_profiles':{}}
            a.state.save_training_task(foreign)
            config={'training':{'status':'running','active_training_task_id':'foreign','owner_user_id':'A'}}
            aa.filtered_training_state(config,{'id':'A'})
            assert a.state.find_training_task('foreign')['status']=='queued'
            assert not pipeline_events['A']
            try:aa.task_mutations.update_training_task_endpoint('foreign',TrainingTaskUpdateRequest(label='bad'));raise AssertionError('unauthorized mutation')
            except HTTPException as exc:assert exc.status_code==403
            assert 'label' not in a.state.find_training_task('foreign')

            target=a.state.records.directory()/'artifact.bin'
            transfer_task={'job_id':'artifact','status':'completed','owner_user_id':'A','model_profiles':{},
                           'runpod_artifact_token_sha256':hashlib.sha256(b'token').hexdigest(),
                           'runpod_artifact_token_expires_at':9999,'runpod_artifact_upload_path':str(target)}
            a.state.save_training_task(transfer_task)
            class Upload:
                def __init__(self):self.calls=0
                async def stream(self):self.calls+=1;yield b'synthetic-artifact'
            upload=Upload()
            try:asyncio.run(aa.transfer.upload_runpod_training_artifact('artifact','wrong',upload));raise AssertionError('bad token admitted')
            except HTTPException as exc:assert exc.status_code==404
            assert upload.calls==0 and not target.exists()
            error=RuntimeError('metadata update failed')
            with patch.object(a.state,'update_training_task',side_effect=error):
                try:asyncio.run(aa.transfer.upload_runpod_training_artifact('artifact','token',upload));raise AssertionError('metadata failure hidden')
                except RuntimeError as exc:assert exc is error
            assert target.read_bytes()==b'synthetic-artifact' and upload.calls==1
            assert 'runpod_artifact_archive_size' not in a.state.find_training_task('artifact')
            assert a.state.runtime.close(1) and b.state.runtime.close(1)

    def test_native_submission_pins_once_and_drains_independently(self):
        with tempfile.TemporaryDirectory(prefix='training-execution-private-') as temporary:
            graphs=[build(account,Path(temporary)) for account in ('A','B')]
            request=TrainingStartRequest(selected_accessory_ids=[],sample_count=1)
            ids=[]
            with patch('time.time',return_value=123),patch('uuid.uuid4',return_value=SimpleNamespace(hex='abcdef123')):
                for account,data in zip(('A','B'),graphs):
                    graph,resolver,events,entered,release,completed,poison=data
                    token=web_identity.set({'id':account})
                    try:result=graph.enqueue_training_task(request,[],'generate_samples')
                    finally:web_identity.reset(token)
                    ids.append(result['job_id'])
                    assert entered.wait(3)
                    assert 'model_profiles' not in result
            assert ids[0]==ids[1]
            a,ar,ae,_,release,_,_=graphs[0]
            b,br,be,_,_,completed,_=graphs[1]
            try:
                assert a.state.runtime.close(0) is False
                assert completed.wait(3) and b.state.runtime.close(3)
                task=b.state.find_training_task(ids[1])
                assert task['status']=='completed' and task['owner_user_id']=='B'
                assert task['model_profiles']['pipeline']['version']==7
                try:a.enqueue_training_task(request,[],'generate_samples');raise AssertionError('closed owner admitted')
                except TrainingRuntimeClosed:pass
            finally:
                release.set();assert a.state.runtime.close(3)
            for account,data,job in zip(('A','B'),graphs,ids):
                graph,resolver,events,entered,release,completed,poison=data
                saved=graph.state.find_training_task(job)
                assert saved['status']=='completed' and saved['owner_user_id']==account
                assert saved['model_profiles']['pipeline']['version']==7
                assert resolver.scopes==[saved['model_profiles']]
                assert resolver.current_snapshot() is None and len(resolver.records)==1
                native=[event[1] for event in events if event[0] in ('open','generate','close')]
                assert len(native)==3 and len(set(native))==1 and native[0]!=threading.get_ident()
                assert [event[0] for event in events].index('invalidate')<[event[0] for event in events].index('construct')
                poison.assert_not_called()
                config=graph.account.users.storage.load()
                assert config['training_by_user_id'][account]['status']=='completed'
                assert config['training_by_user_id'][account]['active_training_task_id']==job
                assert set(config['training_by_user_id'])=={account}
                assert len(pipeline_events[account])==1
                assert pipeline_events[account][0]['owner_user_id']==account
                assert pipeline_events[account][0]['status']=='completed'
                assert pipeline_events[account][0]['job_id']==job

    def test_launch_configuration_failure_keeps_the_started_task(self):
        with tempfile.TemporaryDirectory(prefix='training-task-launch-failure-') as temporary:
            graph, resolver, events, entered, release, completed, poison = build('A', Path(temporary))
            api = api_for(graph, 'A')
            error = RuntimeError('launch configuration save failed')
            estimate = replace(graph.submission.policy, estimate=lambda: lambda *args, **kwargs: {
                'estimated_minutes': 1, 'estimated_gb': 0.001})
            launch_config = replace(api.launch_submission.config, save=lambda config: (_ for _ in ()).throw(error))
            with patch.object(graph.submission, 'policy', estimate), patch.object(api.preview_approval, 'validate_approved_preview'), patch.object(api.launch_submission, 'config', launch_config):
                try:
                    api.launch_submission.request_sample_generation(TrainingStartRequest(selected_accessory_ids=[], sample_count=1))
                    raise AssertionError('launch save failure hidden')
                except RuntimeError as exc:
                    assert exc is error
                assert entered.wait(3)
                assert len(graph.state.runtime.threads) == 1
                job_id = next(iter(graph.state.runtime.threads))
                assert graph.state.find_training_task(job_id)['owner_user_id'] == 'A'
                assert len([e for e in events if e[0] == 'construct']) == 1
                assert len([e for e in events if e[0] == 'generate']) == 1
                assert graph.account.users.storage.load()['training_by_user_id'] == {}
                release.set()
                assert graph.state.runtime.close(3) and completed.wait(1)
            task = graph.state.find_training_task(job_id)
            assert task['status'] == 'completed'
            saved = graph.account.users.storage.load()['training_by_user_id']['A']
            assert saved['status'] == 'completed' and saved['active_training_task_id'] == job_id
            assert len(pipeline_events['A']) == 1
            poison.assert_not_called()


    def test_real_account_save_and_pipeline_failure_keep_second_sync(self):
        for failure in ('save', 'pipeline'):
            with tempfile.TemporaryDirectory(prefix='training-task-sync-failure-') as temporary:
                graph, resolver, events, entered, release, completed, poison = build('B', Path(temporary))
                calls = []
                original_save = graph.account.users.storage.save
                original_pipeline = graph.account.users.sync_pipeline
                def first_save_fails(config):
                    calls.append(config['training_by_user_id']['B']['status'])
                    if len(calls) == 1:
                        raise RuntimeError('first account save failed')
                    return original_save(config)
                def first_pipeline_fails(task):
                    calls.append(task['status'])
                    original_pipeline(task)
                    if len(calls) == 1:
                        raise RuntimeError('first pipeline synchronization failed')
                target = patch.object(graph.account.users, 'storage', replace(graph.account.users.storage, save=first_save_fails)) if failure == 'save' else patch.object(graph.account.users, 'sync_pipeline', first_pipeline_fails)
                with target:
                    result = graph.enqueue_training_task(TrainingStartRequest(selected_accessory_ids=[], sample_count=1), [], 'generate_samples')
                    job_id = result['job_id']
                    assert graph.state.runtime.close(3) and completed.wait(1)
                assert calls == ['completed', 'failed'], calls
                assert graph.state.find_training_task(job_id)['status'] == 'failed'
                saved = graph.account.users.storage.load()['training_by_user_id']['B']
                assert saved['status'] == 'failed' and saved['active_training_task_id'] == job_id
                assert len([e for e in events if e[0] == 'construct']) == 1
                assert len([e for e in events if e[0] == 'generate']) == 1
                assert len(pipeline_events['B']) == (1 if failure == 'save' else 2)
                assert resolver.current_snapshot() is None
                poison.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Actual feedback graph: immutable media, task snapshots, identity and lifetime."""
import ast
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import fields, is_dataclass
from pathlib import Path
import sys
import tempfile
from threading import Event, RLock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, HTTPException
from local_inspection_service.schemas.training import TrainingStartRequest
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.training.real_photo_composition import (
    RealPhotoWorkflows, FeedbackInputs, TrainingInputs, FeedbackArtifacts, LegacyFeedback)
from local_inspection_service.runtime.training_tasks import TrainingRuntimeClosed


class Contracts(unittest.TestCase):
    def fixture(self, owner='a'):
        directory=tempfile.TemporaryDirectory(prefix='real-photo-graph-')
        self.addCleanup(directory.cleanup)
        identity=ContextVar('identity-'+owner,default={'id':'outside'})
        user={'id':owner,'active':True}
        classes=[{'class_id':'one'},{'class_id':'two'}]
        task={'id':'task','owner_user_id':owner,'required_accessory_counts':{'one':2,'two':-3}}
        state={'samples':[],'settings':{'enabled':True,'auto_promote':True,'extra':'preserved'}}
        events=[]
        class Guard:
            def __init__(self):self.lock=RLock();self.depth=0;self.exits=0
            def __enter__(self):self.lock.acquire();self.depth+=1;return self
            def __exit__(self,*args):self.depth-=1;self.exits+=1;self.lock.release()
        guard=Guard()
        def load_legacy(identifier):
            self.assertEqual(guard.depth,1)
            return state
        def save_legacy(record):
            self.assertEqual(guard.depth,1)
            events.append(('save',record.copy()))
        @contextmanager
        def scope():
            events.append(('enter',owner))
            try:yield
            finally:events.append(('exit',owner))
        files=BusinessFiles(runtime_provider=lambda:None)
        def output(kind,identifier):
            self.assertEqual(identifier,owner)
            path=Path(directory.name)/kind;path.mkdir(exist_ok=True)
            return path
        def authorize(record,current,**kwargs):
            if record['owner_user_id']!=current['id']:raise HTTPException(403,'denied')
        enqueue=Mock(side_effect=lambda request,selected,mode,dataset:{'id':owner+'-training'})
        inputs=dict(
            feedback=FeedbackInputs(repository=Mock(side_effect=AssertionError('database forbidden')),
                user=lambda:identity.get(),tasks=lambda:[task],authorize=authorize,
                config=lambda current:{},references=lambda item:[],read=Mock(side_effect=AssertionError('read forbidden')),
                profiles=Mock(side_effect=AssertionError('model forbidden')),
                legacy_state=lambda identifier:state,model_task=lambda model,current:'task'),
            training=TrainingInputs(auth_store=lambda:{'users':[user]},
                find_user=lambda:lambda store,identifier:next((u for u in store['users'] if u['id']==identifier),None),
                identity=identity,load_config=lambda:{'accessories':[{'id':'two'},{'id':'one'}]},
                scope_config=lambda:lambda config,current:config,
                selected_accessories=lambda:lambda config,identifiers:config['accessories'],
                request_type=lambda:TrainingStartRequest,enqueue=lambda:enqueue),
            artifacts=FeedbackArtifacts(files=lambda:files,output=lambda:output),
            legacy=LegacyFeedback(guard=lambda:guard,load=lambda:load_legacy,save=lambda:save_legacy),
            training_record=Mock(side_effect=AssertionError('training read forbidden')),
            configuration=Mock(side_effect=AssertionError('configuration forbidden')),
            image_provider=Mock(side_effect=AssertionError('inference forbidden')),
            scope=scope,accounts=lambda:{owner},training_enabled=lambda:True)
        graph=RealPhotoWorkflows(**inputs)
        graph.feedback.classes=Mock(return_value=classes)
        job={'owner_user_id':owner,'task_id':'task','inputs':{'classes':classes}}
        dataset={'id':'dataset','selected_accessory_ids':['one','two'],'sample_count':10,
            'training_metadata':{'feedback_task_id':'task','required_accessory_counts':{'one':2,'two':0}}}
        return SimpleNamespace(graph=graph,inputs=inputs,identity=identity,user=user,task=task,
            state=state,events=events,files=files,enqueue=enqueue,job=job,dataset=dataset,guard=guard)

    def test_inert_allocation_fresh_owners_and_late_constructor_failure(self):
        a,b=self.fixture('a'),self.fixture('b')
        for name in ('feedback','bridge','dispatcher','mask_dispatcher','runtime'):
            self.assertIsNot(getattr(a.graph,name),getattr(b.graph,name))
        def poison(*args,**kwargs):raise AssertionError('eager external selection')
        def poisoned(value):
            if isinstance(value,ContextVar):return value
            if is_dataclass(value):return type(value)(**{f.name:poisoned(getattr(value,f.name)) for f in fields(value)})
            return poison if callable(value) else value
        inputs={name:poisoned(value) for name,value in a.inputs.items()}
        graph=RealPhotoWorkflows(**inputs)
        self.assertTrue(graph.runtime.close(1))
        import local_inspection_service.training.real_photo_composition as module
        with patch.object(module,'MaskDispatcher',side_effect=ValueError('mask constructor')):
            with self.assertRaisesRegex(ValueError,'mask constructor'):RealPhotoWorkflows(**inputs)
        self.assertEqual(a.events,[]);self.assertEqual(b.events,[])

    def test_metadata_and_submission_keep_nested_identity_snapshot_and_class_order(self):
        for owner in ('a','b'):
            f=self.fixture(owner)
            f.graph.feedback.classes.side_effect=lambda task,current: (
                self.assertIs(f.identity.get(),f.user) or f.job['inputs']['classes'])
            self.assertEqual(f.graph.training_metadata(f.job),f.dataset['training_metadata'])
            self.assertEqual(f.identity.get(),{'id':'outside'})
            self.assertEqual(f.graph.submit_training(f.job,f.dataset),{'id':owner+'-training'})
            request,selected,mode,dataset=f.enqueue.call_args.args
            self.assertEqual([item['id'] for item in selected],['one','two'])
            self.assertEqual((request.train_mode,request.dataset_id,mode),('yolo','dataset','train_model'))
            self.assertIs(dataset,f.dataset);self.assertEqual(f.identity.get(),{'id':'outside'})

    def test_invalid_owner_snapshot_and_submission_failure_restore_identity(self):
        for mode in ('inactive','classes','rules','missing-accessory','enqueue'):
            with self.subTest(mode=mode):
                f=self.fixture()
                if mode=='inactive':f.user['active']=False
                elif mode=='classes':f.graph.feedback.classes.return_value=[]
                elif mode=='rules':f.dataset['training_metadata']={}
                if mode=='missing-accessory':
                    from dataclasses import replace
                    f.graph.bridge.training=replace(f.graph.bridge.training,load_config=lambda:{'accessories':[]})
                if mode=='enqueue':f.enqueue.side_effect=ValueError('enqueue failed')
                with self.assertRaises(ValueError):f.graph.submit_training(f.job,f.dataset)
                self.assertEqual(f.identity.get(),{'id':'outside'})
                self.assertEqual(f.enqueue.call_count,1 if mode=='enqueue' else 0)

    def test_immutable_original_repeat_and_conflict_preserve_bytes(self):
        f=self.fixture()
        path=f.graph.freeze_original(f.user,b'original','synthetic-sha')
        self.assertEqual(f.graph.freeze_original(f.user,b'original','synthetic-sha'),path)
        with self.assertRaisesRegex(ValueError,'immutable real photo conflict'):
            f.graph.freeze_original(f.user,b'different','synthetic-sha')
        self.assertEqual(Path(path).read_bytes(),b'original')

    def test_legacy_busy_state_refuses_switch_and_settled_state_preserves_settings(self):
        for status in ('labeling','rendering'):
            f=self.fixture();f.state['samples']=[{'label_status':status}]
            with self.assertRaises(HTTPException) as caught:f.graph.disable_legacy('task')
            self.assertEqual(caught.exception.status_code,409)
            self.assertTrue(f.state['settings']['enabled']);self.assertEqual(f.events,[])
            self.assertEqual((f.guard.depth,f.guard.exits),(0,1))
        f=self.fixture();f.state['samples']=[{'label_status':'completed'}]
        f.graph.disable_legacy('task')
        self.assertEqual(f.state['settings'],{'enabled':False,'auto_promote':False,'extra':'preserved'})
        self.assertEqual(len(f.events),1)
        self.assertEqual((f.guard.depth,f.guard.exits),(0,1))

    def test_legacy_save_failure_releases_the_original_guard_without_retry(self):
        from dataclasses import replace
        f=self.fixture()
        def fail(record):
            self.assertEqual(f.guard.depth,1)
            raise ValueError('persist failed')
        save=Mock(side_effect=fail)
        f.graph.bridge.legacy=replace(f.graph.bridge.legacy,save=lambda:save)
        with self.assertRaisesRegex(ValueError,'persist failed'):f.graph.disable_legacy('task')
        save.assert_called_once();self.assertEqual((f.guard.depth,f.guard.exits),(0,1))

    def test_saved_graph_callbacks_select_bridge_after_arguments(self):
        f=self.fixture();saved=f.graph.dispatcher.ports.metadata
        old=f.graph.bridge
        new=SimpleNamespace(training_metadata=Mock(return_value={'new':True}))
        def argument():f.graph.bridge=new;return f.job
        self.assertEqual(saved(argument()),{'new':True});new.training_metadata.assert_called_once_with(f.job)
        submit=f.graph.dispatcher.ports.submit
        new.submit_training=Mock(return_value={'submission':'new'})
        f.graph.bridge=old
        self.assertEqual(submit(argument(),f.dataset),{'submission':'new'})
        new.submit_training.assert_called_once_with(f.job,f.dataset)
        freeze=f.graph.feedback.ports.freeze
        new.freeze_original=Mock(return_value='new-original')
        f.graph.bridge=old
        def user_argument():f.graph.bridge=new;return f.user
        self.assertEqual(freeze(user_argument(),b'original','sha'),'new-original')
        new.freeze_original.assert_called_once_with(f.user,b'original','sha')
        f.graph.bridge=old
        f.graph.training_metadata=Mock(return_value=f.dataset['training_metadata'])
        # The bridge captures the named owner forwarder, which remains selected
        # at composition; replacing the instance attribute is not a new port.
        self.assertEqual(old.submit_training(f.job,f.dataset),{'id':'a-training'})
        f.graph.training_metadata.assert_not_called()

    def test_registration_uses_fresh_services_and_task_access_is_account_bound(self):
        a,b=self.fixture('a'),self.fixture('b');app_a,app_b=FastAPI(),FastAPI()
        self.assertIs(a.graph.register(app_a),a.graph.feedback)
        self.assertIs(b.graph.register(app_b),b.graph.feedback)
        routes=lambda app:[(r.path,sorted(r.methods)) for r in app.routes]
        self.assertEqual(routes(app_a),routes(app_b))
        self.assertIsNot(app_a.routes[-1].endpoint,app_b.routes[-1].endpoint)
        token=a.identity.set(a.user)
        try:self.assertEqual(a.graph.feedback.task('task')[1],a.task)
        finally:a.identity.reset(token)
        token=a.identity.set(b.user)
        try:
            with self.assertRaises(HTTPException) as caught:a.graph.feedback.task('task')
            self.assertEqual(caught.exception.status_code,403)
        finally:a.identity.reset(token)

    def test_actual_native_threads_drain_independently_and_cannot_reopen(self):
        a,b=self.fixture('a'),self.fixture('b')
        for f in (a,b):
            f.mask_tick=Event();f.train_tick=Event()
            f.graph.mask_dispatcher.tick=f.mask_tick.set
            f.graph.dispatcher.tick=f.train_tick.set
        a.graph.start();a.graph.start();b.graph.start()
        try:
            for f in (a,b):
                self.assertTrue(f.mask_tick.wait(5));self.assertTrue(f.train_tick.wait(5))
            self.assertTrue(a.graph.runtime.close(2))
            with self.assertRaises(TrainingRuntimeClosed):a.graph.start()
            self.assertEqual(a.events.count(('enter','a')),2)
            self.assertEqual(a.events.count(('exit','a')),2)
            self.assertEqual(b.events.count(('exit','b')),0)
        finally:
            self.assertTrue(a.graph.runtime.close(2));self.assertTrue(b.graph.runtime.close(2))

    def test_startup_selects_current_allowlist_capability_in_both_directions(self):
        for initial,changed,expected in ((set(),{'a'},1),({'a'},set(),0)):
            f=self.fixture();policy=SimpleNamespace(accounts=lambda value=initial:value)
            graph=RealPhotoWorkflows(**dict(f.inputs,accounts=lambda:policy.accounts()))
            policy.accounts=lambda value=changed:value
            with patch.object(graph.runtime,'start') as start:
                graph.start()
            self.assertEqual(start.call_count,expected)
            self.assertTrue(graph.runtime.close(1))

    def test_default_graph_and_ordered_parent_entry_contract(self):
        import application_integration_source_contract as contract
        source=(contract.ROOT/'local_inspection_service/server.py').read_text()
        self.assertEqual(contract.digest(ast.parse(source)),contract.REAL_PHOTO_WORKFLOWS['integrated_ast_sha256'])
        parent=ast.parse(contract.restore_real_photo_workflows_root(source))
        self.assertEqual(contract.digest(parent),contract.PROVIDER_TRANSPORTS['integrated_ast_sha256'])
        actual=ast.parse(source)
        names=lambda tree:[n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
        self.assertEqual(names(actual),names(parent));self.assertEqual(len(names(actual)),983)
        from verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        graph=server._real_photo_workflows
        for alias,member in (('_real_photo_feedback','feedback'),('_real_photo_dispatcher','dispatcher'),
            ('_real_photo_mask_dispatcher','mask_dispatcher'),('_real_photo_dispatch_runtime','runtime')):
            self.assertIs(getattr(server,alias),getattr(graph,member))
        self.assertIs(graph.bridge.training.identity,server._request_user)
        self.assertIs(graph.dispatcher.ports.submit.__self__,graph)


if __name__=='__main__':unittest.main()

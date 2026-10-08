"""Synthetic fixtures for actual account, execution and task API owners."""
from contextlib import contextmanager
from contextvars import ContextVar
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import threading
import typing
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from smoke_training_runner import Resolver
from local_inspection_service.training.state_composition import TrainingStateWorkflows, TrainingRecordAccess
from local_inspection_service.training.record_store import TrainingRows
from local_inspection_service.training.task_lifecycle import TrainingTaskWrites
from local_inspection_service.training.task_views import TrainingViewAccess
from local_inspection_service.training.runner import TrainingRunnerPaths, TrainingDatasetExecution, TrainingLocalExecution
from local_inspection_service.training.submission import TrainingSubmissionPolicy, TrainingSubmissionIdentity
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.model_profiles.snapshots import public_record
from local_inspection_service.runtime.training_tasks import TrainingTaskRuntime, TrainingRuntimeClosed
from local_inspection_service.schemas.training import TrainingStartRequest

from local_inspection_service.training import account_state_composition as account_module
from local_inspection_service.training import native_execution_composition as module
from local_inspection_service.training.user_state import TrainingStateAccess
typing.get_type_hints(module.TrainingExecution.__init__)
web_identity=ContextVar('private-web-account',default=None)
pipeline_events={}

def build(account,root):
    account_root=root/account;account_root.mkdir()
    directory=account_root/'tasks';directory.mkdir()
    events=[];entered=threading.Event();release=threading.Event();completed=threading.Event()
    resolver=Resolver();resolver.version=7
    @contextmanager
    def scope():
        events.append(('open',threading.get_ident()))
        try:yield
        finally:events.append(('close',threading.get_ident()));completed.set()
    runtime=TrainingTaskRuntime(scope=scope)
    configuration=account_root/'config.json';configuration.write_text(json.dumps({'training':{},'training_by_user_id':{}}))
    pipeline_records=[]
    pipeline_events[account]=pipeline_records
    account_owner=account_module.TrainingAccountState(
        runtime=runtime,
        storage=TrainingRecordAccess(lambda:None,lambda:directory,lambda:lambda:resolver,
                                     lambda key:events.append(('invalidate',key)),lambda record,*args:record),
        rows=TrainingRows(lambda:lambda record,**kwargs:record,lambda:lambda rows:rows,lambda path:path.stem),
        writes=TrainingTaskWrites(lambda:None,lambda record,**kwargs:record,lambda key:None),
        require_access=lambda record,user,**kwargs:None,
        view_access=TrainingViewAccess(dict,lambda:public_record,lambda record,user,target:record['owner_user_id']==user['id']),
        defaults=lambda:{'status':'idle'},legacy_owner=lambda:'legacy',
        access=TrainingStateAccess(lambda record:record.get('owner_user_id','') if record else '',
                                   lambda record,user,target=None:record.get('owner_user_id')==user['id'],
                                   lambda user:False,lambda:{'owner_user_id':account}),
        configuration=account_module.TrainingConfiguration(
            lambda:json.loads(configuration.read_text()),
            lambda config:configuration.write_text(json.dumps(config))),
        sync_pipeline=lambda task:pipeline_records.append(dict(task)))
    state=account_owner.records
    poison=Mock(side_effect=AssertionError('unrequested transport or process operation'))
    def generate(task):
        assert web_identity.get() is None
        assert resolver.current_snapshot()['pipeline']['version']==7
        assert task['owner_user_id']==account
        events.append(('generate',threading.get_ident()))
        entered.set()
        if account=='A':assert release.wait(5)
        return {'dataset_yaml':str(directory/'synthetic.yaml'),'dataset_dir':str(directory),'manifest_path':'synthetic'}
    def create(**kwargs):
        # The saved task retains7 even when configuration changes before native start.
        resolver.version=99
        events.append(('construct',threading.get_ident()))
        return threading.Thread(**kwargs)
    graph=module.TrainingExecution(
        account=account_owner,files=BusinessFiles(lambda:None),
        paths=TrainingRunnerPaths(lambda:Path,lambda:directory,lambda:root,lambda:poison),
        datasets=TrainingDatasetExecution(lambda:'runpod',generate,poison,poison),
        local=TrainingLocalExecution(poison,poison,poison,poison,poison,poison),
        resolver=lambda:resolver,
        policy=TrainingSubmissionPolicy(lambda:lambda *args,**kwargs:{'estimated_seconds':1},lambda item:False),
        identity=TrainingSubmissionIdentity(web_identity.get,lambda:{'owner_user_id':account},lambda:lambda *args:None),
        create_thread=create)
    assert events==[] and resolver.scopes==[] and not runtime.threads
    assert graph.submission.runtime is state.runtime is runtime
    return graph,resolver,events,entered,release,completed,poison

from local_inspection_service.training import task_composition as api_module
typing.get_type_hints(api_module.TrainingTaskWorkflows.__init__)
import asyncio
import hashlib
from fastapi import HTTPException
from local_inspection_service.training.jobs_query import JobsReadAccess
from local_inspection_service.training.status_projection import StatusAccess, StatusPreview
from local_inspection_service.training.runpod_transfer import TransferPaths
from local_inspection_service.schemas.training import TrainingTaskUpdateRequest

def api_for(graph, account):
    user={'id':account}
    def require(record, current, *, write=False):
        if record['owner_user_id']!=current['id']:raise HTTPException(403,'denied')
    def scoped(config,current,target=None):
        return {'training':graph.account.training_state_for_user(config,current,set(),target)}
    files=BusinessFiles(lambda:None)
    return api_module.TrainingTaskWorkflows(
        account=graph.account,execution=graph,files=files,
        jobs_access=JobsReadAccess(lambda:user,lambda user:False,require),
        image_jobs=lambda **kwargs:[{'job_id':'shared','label':'image-owned','status':'completed'}],
        image_active=lambda:{'queued','running'},
        mutations=api_module.TrainingMutationAccess(lambda:user,require,lambda:123),
        launch_config=api_module.TrainingLaunchConfiguration(graph.account.users.storage.load,scoped,
                        lambda:lambda *args:False,lambda *args:None,graph.account.users.storage.save),
        launch=api_module.TrainingLaunchAccess(lambda:user,lambda:lambda *args:[],lambda:123,lambda:{}),
        status=api_module.TrainingStatusRead(lambda:user,lambda user:False,graph.account.users.storage.load,lambda:scoped),
        dataset=api_module.TrainingDatasetAccess(lambda *args,**kwargs:(None,None),require,lambda:public_record),
        preview=api_module.TrainingPreviewInputs(lambda:graph.state.records.directory(),lambda:lambda *args:None,lambda selected:'cache'),
        status_access=StatusAccess(lambda record,current,target:record['owner_user_id']==current['id'],lambda user:False,lambda record:record['owner_user_id']),
        status_preview=StatusPreview(lambda:lambda *args:[],lambda selected:'cache',lambda *args:False),
        transfer=api_module.TrainingTransferAccess(lambda:1024,lambda value:hashlib.sha256(value.encode()).hexdigest(),lambda:123,
                                                  TransferPaths(lambda:lambda value,**kwargs:Path(value),graph.state.records.directory)))


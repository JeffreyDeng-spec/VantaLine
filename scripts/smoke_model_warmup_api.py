"""Model warmup HTTP/service contracts; synthetic runtime, no model or worker starts."""
import ast
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from local_inspection_service.schemas.detection import ModelWarmupRequest

BASELINE=os.environ.get('VANTALINE_MODEL_WARMUP_BASELINE_SOURCE')


def fixture(*,app=None,overrides=None):
    events=[]
    user={'id':'alice'}; raw={'raw':True}; scoped={'scope':'alice'}
    status={'status':'idle','selected_model_id':'old','selected_model_ready':'old','skipped':'old','nested':[]}
    values={'current_auth_user':user,'load_config':raw,'scope_config_for_user':scoped,
        'selected_model_spec':{},'yolo_model_ready':False,'public_yolo_warmup_status':status,'start_yolo_warmup':None}
    calls={}
    for name,value in values.items():
        def invoke(*args,_name=name,_value=value):events.append((_name,args));return _value
        calls[name]=Mock(side_effect=invoke)
    calls.update(overrides or {})
    if BASELINE:
        tree=ast.parse(Path(BASELINE).read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='warmup_detection_model')
        node.decorator_list=[]
        namespace={'Any':Any,'ModelWarmupRequest':ModelWarmupRequest,'HTTPException':HTTPException,**calls}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<original-warmup-request>','exec'),namespace)
        operation=namespace['warmup_detection_model']
        if app is not None:app.post('/api/models/warmup')(operation)
        service=None
    else:
        from local_inspection_service.detection.warmup_requests import ModelWarmupAccess, ModelWarmupModels, ModelWarmupRequests
        access=ModelWarmupAccess(*(calls[k] for k in ('current_auth_user','load_config','scope_config_for_user')))
        models=ModelWarmupModels(*(calls[k] for k in ('selected_model_spec','yolo_model_ready')))
        if app is None:
            service=ModelWarmupRequests(access,models,status=calls['public_yolo_warmup_status'],start=calls['start_yolo_warmup'])
        else:
            from local_inspection_service.detection.warmup_api import compose_model_warmup_api
            service=compose_model_warmup_api(app,access=access,models=models,status=calls['public_yolo_warmup_status'],start=calls['start_yolo_warmup'])
        operation=service.warmup_detection_model
    return SimpleNamespace(operation=operation,service=service,calls=calls,events=events,user=user,raw=raw,scoped=scoped,status=status)


class RequestContracts(unittest.TestCase):
    def test_order_scoped_identity_and_two_readiness_reads(self):
        f=fixture();ready=iter([False,True])
        def readiness(*args):f.events.append(('yolo_model_ready',args));return next(ready)
        f.calls['yolo_model_ready'].side_effect=readiness
        result=f.operation(ModelWarmupRequest(model_id=' chosen '))
        self.assertEqual([name for name,_ in f.events],['current_auth_user','load_config','scope_config_for_user','selected_model_spec','yolo_model_ready','start_yolo_warmup','public_yolo_warmup_status','yolo_model_ready'])
        f.calls['scope_config_for_user'].assert_called_once_with(f.raw,f.user)
        f.calls['selected_model_spec'].assert_called_once_with('chosen',f.scoped)
        f.calls['start_yolo_warmup'].assert_called_once_with('selection',['chosen'])
        self.assertEqual(f.calls['yolo_model_ready'].call_count,2)
        self.assertEqual(result,{**f.status,'selected_model_id':'chosen','selected_model_ready':True,'skipped':False})
        self.assertIs(result['nested'],f.status['nested']);self.assertEqual(f.status['selected_model_id'],'old')

    def test_ready_and_remote_skip_short_circuits(self):
        for flags in ({'is_ai_detection':True},{'is_label_sheet_match':True},{'is_ai_detection':True,'is_label_sheet_match':True},{}):
            with self.subTest(flags=flags):
                f=fixture();f.calls['selected_model_spec'].side_effect=None;f.calls['selected_model_spec'].return_value=flags
                f.calls['yolo_model_ready'].side_effect=None;f.calls['yolo_model_ready'].return_value=True
                result=f.operation(ModelWarmupRequest(model_id='m'))
                self.assertEqual(result['skipped'],bool(flags));self.assertTrue(result['selected_model_ready'])
                self.assertEqual(f.calls['yolo_model_ready'].call_count,0 if flags else 2)
                f.calls['start_yolo_warmup'].assert_not_called();f.calls['public_yolo_warmup_status'].assert_called_once_with(f.scoped)

    def test_blank_validation_is_after_identity_and_scope(self):
        f=fixture()
        with self.assertRaises(HTTPException) as error:f.operation(ModelWarmupRequest(model_id='  '))
        self.assertEqual((error.exception.status_code,error.exception.detail),(400,'model_id is required'))
        self.assertEqual([name for name,_ in f.events],['current_auth_user','load_config','scope_config_for_user'])
        f.calls['selected_model_spec'].assert_not_called()

    def test_each_failure_propagates_once_and_stops_later_work(self):
        order=['current_auth_user','load_config','scope_config_for_user','selected_model_spec','yolo_model_ready','start_yolo_warmup','public_yolo_warmup_status']
        for index,target in enumerate(order):
            with self.subTest(target=target):
                f=fixture();error=RuntimeError('synthetic request failure')
                def fail(*args):f.events.append((target,args));raise error
                f.calls[target].side_effect=fail
                with self.assertRaises(RuntimeError) as raised:f.operation(ModelWarmupRequest(model_id='m'))
                self.assertIs(raised.exception,error);self.assertEqual([name for name,_ in f.events],order[:index+1])
                self.assertEqual(f.calls[target].call_count,1)
        f=fixture();error=RuntimeError('second readiness failure')
        f.calls['yolo_model_ready'].side_effect=[False,error]
        with self.assertRaises(RuntimeError) as raised:f.operation(ModelWarmupRequest(model_id='m'))
        self.assertIs(raised.exception,error);f.calls['start_yolo_warmup'].assert_called_once_with('selection',['m'])
        f.calls['public_yolo_warmup_status'].assert_called_once_with(f.scoped)
        self.assertEqual(f.calls['yolo_model_ready'].call_count,2)

    def test_status_effect_precedes_final_readiness_and_is_shallow(self):
        f=fixture();ready=[False]
        f.calls['yolo_model_ready'].side_effect=lambda *args:ready[0]
        def status(config):ready[0]='changed';return f.status
        f.calls['public_yolo_warmup_status'].side_effect=status
        result=f.operation(ModelWarmupRequest(model_id='m'))
        self.assertEqual(result['selected_model_ready'],'changed')
        self.assertIs(result['nested'],f.status['nested'])

    def test_bad_status_mapping_keeps_start_effect_and_does_not_retry(self):
        for remote in (False,True):
            with self.subTest(remote=remote):
                f=fixture()
                f.calls['selected_model_spec'].side_effect=None
                f.calls['selected_model_spec'].return_value={'is_ai_detection':remote}
                f.calls['public_yolo_warmup_status'].side_effect=None
                f.calls['public_yolo_warmup_status'].return_value=None
                with self.assertRaises(TypeError):f.operation(ModelWarmupRequest(model_id='m'))
                self.assertEqual(f.calls['start_yolo_warmup'].call_count,0 if remote else 1)
                self.assertEqual(f.calls['yolo_model_ready'].call_count,0 if remote else 1)
                f.calls['public_yolo_warmup_status'].assert_called_once_with(f.scoped)

    def test_real_http_validation_errors_and_two_apps_use_their_own_ports(self):
        first=FastAPI();second=FastAPI();a=fixture(app=first);b=fixture(app=second)
        b.calls['current_auth_user'].side_effect=HTTPException(403,'forbidden')
        with TestClient(first,raise_server_exceptions=False) as ac,TestClient(second,raise_server_exceptions=False) as bc:
            self.assertEqual(ac.post('/api/models/warmup',json={'model_id':' m '}).json()['selected_model_id'],'m')
            response=bc.post('/api/models/warmup',json={'model_id':'m'})
            self.assertEqual((response.status_code,response.json()),(403,{'detail':'forbidden'}))
            b.calls['load_config'].assert_not_called()
            response=ac.post('/api/models/warmup',json={'model_id':' '})
            self.assertEqual((response.status_code,response.json()),(400,{'detail':'model_id is required'}))
            for payload in ({},{'model_id':None}):self.assertEqual(ac.post('/api/models/warmup',json=payload).status_code,422)
            a.calls['load_config'].side_effect=RuntimeError('synthetic')
            self.assertEqual(ac.post('/api/models/warmup',json={'model_id':'m'}).status_code,500)
        for app in (first,second):
            route=next(r for r in app.routes if getattr(r,'path',None)=='/api/models/warmup')
            self.assertEqual(route.name,'warmup_detection_model');self.assertEqual(route.methods,{'POST'})
            self.assertIn('warmup_detection_model',app.openapi()['paths']['/api/models/warmup']['post']['operationId'])

    @unittest.skipIf(BASELINE,'new composition ownership check')
    def test_lazy_registration_duplicate_preflight_and_runtime_adapter(self):
        from local_inspection_service.detection.warmup_api import bind_warmup_start, compose_model_warmup_api
        app=FastAPI();f=fixture(app=app)
        self.assertEqual(f.events,[])
        before=list(app.routes)
        with self.assertRaisesRegex(ValueError,'already registered'):
            compose_model_warmup_api(app,access=f.service.access,models=f.service.models,status=f.service.status,start=f.service.start)
        self.assertEqual(app.routes,before);self.assertEqual(f.events,[])
        runtime=SimpleNamespace(start_yolo_warmup=Mock(),yolo_warmup_worker=Mock())
        start=bind_warmup_start(runtime);runtime.start_yolo_warmup.assert_not_called()
        ids=['one'];start('selection',ids)
        args=runtime.start_yolo_warmup.call_args
        self.assertEqual(args.args,('selection',ids));self.assertIs(args.args[1],ids)
        self.assertIs(args.kwargs['worker'](),runtime.yolo_warmup_worker)

    @unittest.skipIf(BASELINE,'explicit runtime ownership and late worker lookup')
    def test_two_actual_runtimes_and_worker_selection_after_enable(self):
        from unittest.mock import patch
        from local_inspection_service.runtime import yolo_warmup as module
        from local_inspection_service.detection.warmup_api import bind_warmup_start, compose_model_warmup_api
        first=module.YoloWarmup(module.WarmupOperations(lambda:False,lambda:{},lambda config:[],lambda *args:None,lambda config:[],lambda:str))
        second=module.YoloWarmup(first.operations)
        first.state['reason']='first';second.state['reason']='second'
        for runtime,reason in ((first,'first'),(second,'second')):
            app=FastAPI();f=fixture()
            compose_model_warmup_api(app,access=f.service.access,models=f.service.models,
                status=runtime.public_yolo_warmup_status,start=bind_warmup_start(runtime))
            with TestClient(app) as client:
                result=client.post('/api/models/warmup',json={'model_id':'m'}).json()
            self.assertEqual(result['reason'],reason);self.assertEqual(result['status'],'disabled')
        self.assertIsNot(first.lock,second.lock);self.assertIsNot(first.state,second.state)
        selected=Mock();events=[]
        def enabled():
            events.append('enabled');first.yolo_warmup_worker=selected;return True
        from dataclasses import replace
        first.operations=replace(first.operations,enabled=enabled)
        with patch.object(module.threading,'Thread') as thread:
            bind_warmup_start(first)('selection',['one'])
        self.assertEqual(events,['enabled']);self.assertIs(thread.call_args.kwargs['target'],selected)
        self.assertEqual(thread.call_args.kwargs['args'],('selection',['one']))
        thread.return_value.start.assert_called_once_with();selected.assert_not_called()

    @unittest.skipIf(BASELINE,'new root composition and complete HTTP contract')
    def test_root_exact_contract_and_actual_service_bindings(self):
        from scripts import verify_backend_contract as contract
        self.assertEqual(contract.encoded(contract.capture()),contract.BASELINE.read_text(encoding='utf-8'))
        from local_inspection_service import server
        service=server._model_warmup_requests
        self.assertEqual(service.access.user,server._authentication.access.current_auth_user)
        self.assertEqual(service.models.ready,server._local_models.yolo_model_ready)
        self.assertEqual(service.models.select,server._model_selection.selected_model_spec)
        self.assertEqual(service.status,server._yolo_warmup_runtime.public_yolo_warmup_status)
        self.assertEqual(server.warmup_detection_model,service.warmup_detection_model)
        routes=[r for r in server.app.routes if getattr(r,'path',None)=='/api/models/warmup']
        self.assertEqual(len(routes),1);self.assertEqual(routes[0].endpoint,service.warmup_detection_model)


if __name__=='__main__':unittest.main()

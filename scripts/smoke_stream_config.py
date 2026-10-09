"""Frozen stream behavior and actual HTTP delegation; no streaming or PLC IO."""
import ast
from concurrent.futures import ThreadPoolExecutor
import copy
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_inspection_service.config.stream import StreamConfiguration
from local_inspection_service.schemas.configuration import StreamConfig


def original(bindings):
    namespace = dict(bindings)
    filename = ROOT / 'tests/backend_contract/stream_config_baseline.py'
    exec(compile(filename.read_text(encoding='utf-8'), str(filename), 'exec'), namespace)
    return namespace['update_stream'], namespace


class StreamConfigTests(unittest.TestCase):
    def test_frozen_body_and_defaults(self):
        for request in (StreamConfig(), StreamConfig(enabled=True, source='rtsp', url='synthetic://stream')):
            outcomes=[]
            for frozen in (True, False):
                config={'unrelated':{'value':1}};saved=[]
                bindings={'load_config':lambda:config,'save_config':lambda value:saved.append(value)}
                run,_=original(bindings) if frozen else (StreamConfiguration(bindings['load_config'],bindings['save_config']).update,None)
                result=run(request)
                self.assertIs(saved[0],config);self.assertIs(result['stream'],config['stream'])
                self.assertEqual(config['unrelated'],{'value':1});outcomes.append(result)
            self.assertEqual(*outcomes)
        self.assertEqual(StreamConfig().model_dump(),{'enabled':False,'source':'camera','url':''})

    def test_field_failure_and_evaluation_order(self):
        for failure in ('load','enabled','source','url','save',None):
            observations=[]
            for frozen in (True,False):
                events=[];config={'stream':{'before':True}};error=RuntimeError('synthetic')
                def step(name,value):
                    events.append(name)
                    if name==failure:raise error
                    return value
                class Input:
                    @property
                    def enabled(self):return step('enabled',True)
                    @property
                    def source(self):return step('source','camera')
                    @property
                    def url(self):return step('url','synthetic')
                load=lambda:step('load',config)
                save=lambda value:step('save',None)
                run,_=original({'load_config':load,'save_config':save}) if frozen else (StreamConfiguration(load,save).update,None)
                if failure:
                    with self.assertRaises(RuntimeError) as caught:run(Input())
                    self.assertIs(caught.exception,error)
                    if failure!='save':self.assertEqual(config,{'stream':{'before':True}})
                    else:self.assertEqual(config['stream']['source'],'camera')
                else:run(Input())
                observations.append((events,config))
            self.assertEqual(*observations)

    def test_save_result_ignored_but_mutation_visible(self):
        for remove in (False,True):
            for frozen in (True,False):
                config={}
                def save(value):
                    if remove:del value['stream']
                    else:value['stream']={'saved':'replacement'}
                    return {'ignored':True}
                run,_=original({'load_config':lambda:config,'save_config':save}) if frozen else (StreamConfiguration(lambda:config,save).update,None)
                if remove:
                    with self.assertRaises(KeyError):run(StreamConfig())
                else:self.assertEqual(run(StreamConfig()),{'status':'saved','stream':{'saved':'replacement'}})

    def test_call_time_rebinding_after_load(self):
        for frozen in (True,False):
            saved=[];bindings={}
            def load():
                bindings['save_config']=lambda value:saved.append('new')
                return {}
            bindings.update(load_config=load,save_config=lambda value:saved.append('old'))
            if frozen:
                run,namespace=original(bindings)
                bindings=namespace
            else:run=StreamConfiguration(lambda:bindings['load_config'](),lambda value:bindings['save_config'](value)).update
            run(StreamConfig());self.assertEqual(saved,['new'])

    def test_independent_owners_and_missing_ports(self):
        configs=[{},{}];saved=[[],[]]
        services=[StreamConfiguration(lambda i=i:configs[i],lambda value,i=i:saved[i].append(value)) for i in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda i:services[i].update(StreamConfig(url=str(i))),range(2)))
        for i in range(2):self.assertEqual(results[i]['stream']['url'],str(i));self.assertIs(saved[i][0],configs[i])
        for args in ((None,Mock()),(Mock(),None)):
            with self.assertRaises(TypeError):StreamConfiguration(*args)

    def test_actual_root_delegates_once_and_preserves_http_defaults(self):
        with tempfile.TemporaryDirectory(prefix='stream-config-contract-') as temporary:
            root=Path(temporary);(root/'local_inspection_service/static').mkdir(parents=True)
            with patch.dict(os.environ,{'LOCAL_INSPECTION_ROOT':temporary,'VANTALINE_DATA_STORE':'json','VANTALINE_LABEL_INSPECTION_ENABLED':'false','LOCAL_INSPECTION_AUTO_RESUME_WORKER':'0','VANTALINE_BOOTSTRAP_ADMIN_USERNAME':'','VANTALINE_BOOTSTRAP_ADMIN_PASSWORD':'','INSPECTION_CORS_ORIGINS':''}):
                from local_inspection_service import server
                from fastapi.testclient import TestClient
                with patch.object(server,'load_config',return_value={}) as load, patch.object(server,'save_config') as save:
                    result=server.update_stream(StreamConfig(url='first'))
                    load.assert_called_once_with();save.assert_called_once();self.assertEqual(result['stream']['url'],'first')
                admin=TestClient(server.app,base_url='https://testserver')
                anonymous=TestClient(server.app,base_url='https://testserver')
                try:
                    response=admin.post('/api/auth/bootstrap',json={'username':'stream-admin','password':'synthetic-contract-password'})
                    self.assertEqual(response.status_code,200,response.text)
                    with patch.object(server,'_stream_configuration') as service:
                        service.update.return_value={'status':'saved','stream':{}}
                        response=anonymous.post('/api/stream/config',json={})
                        self.assertEqual(response.status_code,401);service.update.assert_not_called()
                        response=admin.post('/api/stream/config',json={'enabled':[]})
                        self.assertEqual(response.status_code,422);service.update.assert_not_called()
                        response=admin.post('/api/stream/config',json={})
                        self.assertEqual(response.status_code,200,response.text);service.update.assert_called_once()
                        self.assertEqual(service.update.call_args.args[0],StreamConfig())
                finally:admin.close();anonymous.close()

if __name__=='__main__':unittest.main()

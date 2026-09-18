"""Retired worker request guards: no transport, parameter evaluation, retries or probes."""
from contextlib import ExitStack
import inspect
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

RETIRED='Windows Worker execution is retired. Production training uses RunPod.'


class PoisonValue:
    def __bool__(self):raise AssertionError('unexpected truthiness')
    def __str__(self):raise AssertionError('unexpected string conversion')
    def __iter__(self):raise AssertionError('unexpected iteration')
    def __int__(self):raise AssertionError('unexpected numeric conversion')
    def __index__(self):raise AssertionError('unexpected index conversion')
    def __mul__(self,other):raise AssertionError('unexpected multiplication')
    def __rmul__(self,other):raise AssertionError('unexpected multiplication')
    def startswith(self,*args):raise AssertionError('unexpected path read')
    def get(self,*args,**kwargs):raise AssertionError('unexpected mapping read')
    def items(self):raise AssertionError('unexpected mapping iteration')


class TrainingWorkerRetiredRequestContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ);cls.environment.start();cls.runtime=tempfile.TemporaryDirectory(prefix='worker-retired-root-')
        root=Path(cls.runtime.name);(root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.runtime.cleanup();cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close);self.ports=[]
        for name in ['windows_worker_base_url','windows_worker_headers','windows_worker_timeout_seconds']:
            port=self.stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('unexpected configuration read')));self.ports.append(port)
        for target in ['requests.request','requests.get','requests.post','time.sleep','subprocess.Popen','os.kill','threading.Thread']:
            self.ports.append(self.stack.enter_context(patch(target,side_effect=AssertionError('unexpected external operation'))))
    def assert_retired(self,fn,*args,**kwargs):
        with self.assertRaises(RuntimeError) as caught:fn(*args,**kwargs)
        self.assertEqual(str(caught.exception),RETIRED);self.assertIsNone(caught.exception.__cause__);self.assertIsNone(caught.exception.__context__)
        for port in self.ports:port.assert_not_called()
    def test_json_request_fails_before_configuration_or_argument_reads(self):
        self.assert_retired(self.api.windows_worker_request,'GET','/health')
        value=PoisonValue();self.assert_retired(self.api.windows_worker_request,value,value,json_body=value,timeout_seconds=value)
        for timeout in [None,0,-1,1.5,'invalid']:
            self.assert_retired(self.api.windows_worker_request,'POST','training',json_body={'fixture':'value'},timeout_seconds=timeout)
    def test_form_request_fails_before_mapping_file_or_timeout_reads(self):
        self.assert_retired(self.api.windows_worker_form_request,'POST','/training/jobs/import')
        value=PoisonValue();self.assert_retired(self.api.windows_worker_form_request,value,value,data=value,files=value,timeout_seconds=value)
        data={'metadata':'synthetic'};files={'archive':value};self.assert_retired(self.api.windows_worker_form_request,'POST','upload',data=data,files=files,timeout_seconds=0)
        self.assertEqual(data,{'metadata':'synthetic'});self.assertIs(files['archive'],value)
    def test_retry_request_never_reads_attempts_or_calls_json_helper(self):
        with patch.object(self.api,'windows_worker_request',return_value={'would':'succeed'}) as request:
            for attempts in [None,0,-1,1,3,99,'bad',PoisonValue()]:
                value=PoisonValue();self.assert_retired(self.api.windows_worker_request_with_retry,value,value,json_body=value,timeout_seconds=value,attempts=attempts,backoff_seconds=value)
            request.assert_not_called()
    def test_configuration_cannot_enable_requests(self):
        with patch.dict(os.environ,{self.api.WINDOWS_WORKER_BASE_URL_ENV:'https://fixture.invalid',self.api.WINDOWS_WORKER_TOKEN_ENV:'fixture-token','INSPECTION_TRAINING_EXECUTOR':'worker'}):
            for fn in [self.api.windows_worker_request,self.api.windows_worker_form_request,self.api.windows_worker_request_with_retry]:self.assert_retired(fn,'POST','/training/jobs')
    def test_status_is_fresh_exact_retired_dict_without_probing_or_boolean_reads(self):
        expected={'configured':False,'ok':False,'status':'retired','message':RETIRED};first=self.api.windows_worker_status();second=self.api.windows_worker_status(force=True,probe=True,include_services=True)
        self.assertEqual(first,expected);self.assertEqual(second,expected);self.assertIsNot(first,second)
        for body in [first,second]:self.assertIs(body['configured'],False);self.assertIs(body['ok'],False)
        first['configured']=True;first['extra']='mutated'
        value=PoisonValue();self.assertEqual(self.api.windows_worker_status(force=value,probe=value,include_services=value),expected)
        for port in self.ports:port.assert_not_called()
    def test_original_signatures_and_python_argument_binding_remain(self):
        expected={
            'windows_worker_request':(('method','path'),{'json_body':None,'timeout_seconds':None}),
            'windows_worker_form_request':(('method','path'),{'data':None,'files':None,'timeout_seconds':None}),
            'windows_worker_request_with_retry':(('method','path'),{'json_body':None,'timeout_seconds':None,'attempts':3,'backoff_seconds':4.0}),
            'windows_worker_status':((),{'force':False,'probe':True,'include_services':False}),
        }
        for name,(positional,keywords) in expected.items():
            fn=getattr(self.api,name);parameters=inspect.signature(fn).parameters;self.assertEqual(tuple(parameters),positional+tuple(keywords))
            for key in positional:self.assertEqual(parameters[key].kind,inspect.Parameter.POSITIONAL_OR_KEYWORD);self.assertIs(parameters[key].default,inspect.Parameter.empty)
            for key,default in keywords.items():self.assertEqual(parameters[key].kind,inspect.Parameter.KEYWORD_ONLY);self.assertEqual(parameters[key].default,default)
            with self.assertRaises(TypeError):fn(*(['GET','path'] if positional else []),unexpected=True)
            with self.assertRaises(TypeError):fn(*(['GET','path',None] if positional else [True]))
        for port in self.ports:port.assert_not_called()


    def test_independent_instances_never_resolve_capabilities_and_direct_status_is_fresh(self):
        from local_inspection_service.training.legacy_worker_requests import LegacyWorkerSettings, LegacyWorkerRequests, windows_worker_status
        names=['windows_worker_request','windows_worker_form_request','windows_worker_request_with_retry'];signatures={name:inspect.signature(getattr(self.api,name)) for name in names};instances=[]
        for owner in ['alice','bob']:
            ports=[Mock(side_effect=AssertionError('unexpected '+owner+' capability')) for unused in range(6)]
            service=LegacyWorkerRequests(LegacyWorkerSettings(*ports[:3]),*ports[3:]);instances.append((service,ports))
            for port in ports:port.assert_not_called()
            for name in names:self.assertEqual(inspect.signature(getattr(service,name)),signatures[name])
        for name in names+['windows_worker_status']:
            self.stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('unexpected root request dependency')))
        value=PoisonValue()
        for index in [1,0,1,0]:
            service,ports=instances[index]
            self.assert_retired(service.windows_worker_request,'GET','path')
            self.assert_retired(service.windows_worker_request,value,value,json_body=None,timeout_seconds=None)
            self.assert_retired(service.windows_worker_form_request,value,value,data=value,files=value,timeout_seconds=value)
            self.assert_retired(service.windows_worker_form_request,'POST','path',data=None,files=None,timeout_seconds=None)
            self.assert_retired(service.windows_worker_request_with_retry,value,value,json_body=value,timeout_seconds=value,attempts=value,backoff_seconds=value)
            self.assert_retired(service.windows_worker_request_with_retry,'GET','path')
            for port in ports:port.assert_not_called()
        expected={'configured':False,'ok':False,'status':'retired','message':RETIRED};first=windows_worker_status();second=windows_worker_status(force=value,probe=value,include_services=value)
        self.assertEqual(first,expected);self.assertEqual(second,expected);self.assertIsNot(first,second)
        for body in [first,second]:self.assertIs(body['configured'],False);self.assertIs(body['ok'],False)
        first.clear();self.assertEqual(second,expected)


if __name__=='__main__':unittest.main()

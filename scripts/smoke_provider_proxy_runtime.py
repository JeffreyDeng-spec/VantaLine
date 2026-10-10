"""Proxy selection and transport dispatch with no real network I/O."""
from application_integration_source_contract import restore_infrastructure_root
import ast,contextlib,os,sys,unittest
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit
from unittest.mock import Mock
from fastapi import HTTPException
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE=os.environ.get('VANTALINE_PROVIDER_PROXY_BASELINE_SOURCE')
NAMES=('ai_proxy_url_from_environment','local_proxy_available','env_flag_enabled','ai_proxy_url_from_config','ai_urlopen')
def create(b):
 if BASELINE:
  nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==5
  ns=dict(b,Any=Any,urlsplit=urlsplit,HTTPException=HTTPException);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
 from local_inspection_service.model_providers.proxy_runtime import ProviderProxyRuntime
 from local_inspection_service.model_providers.proxy_runtime_ports import ProxySettings,ProxyCalls,ProxyTransports
 def ports(cls):return cls(**{f.name:lambda name=f.name:b[name] for f in fields(cls)})
 service=ProviderProxyRuntime(ports(ProxySettings),ports(ProxyCalls),ports(ProxyTransports))
 for n in NAMES:
  if n not in b:b[n]=getattr(service,n)
 return service,b
class Contracts(unittest.TestCase):
 def setUp(self):
  self.environ={};self.validate=Mock(side_effect=lambda v:'valid:'+v);self.open=Mock(return_value='response');self.opener=SimpleNamespace(open=Mock(return_value='proxied'));self.handler=Mock(side_effect=lambda v:('handler',v));self.connect=Mock(return_value=contextlib.nullcontext(object()));request_api=SimpleNamespace(Request=object,urlopen=self.open,build_opener=Mock(return_value=self.opener),ProxyHandler=self.handler)
  b=dict(AI_PROXY_ENV_NAMES=('FIRST','SECOND'),AI_LOCAL_PROXY_URL='http://127.0.0.1:17890',AI_AUTO_LOCAL_PROXY_ENV='AUTO',os=SimpleNamespace(environ=self.environ),socket=SimpleNamespace(create_connection=self.connect),urllib=SimpleNamespace(request=request_api),validate_ai_proxy_url=self.validate)
  self.s,self.b=create(b)
 def test_environment_priority_blank_invalid_and_no_second_fallback(self):
  self.assertEqual(self.s.ai_proxy_url_from_environment(),('',''));self.environ.update(FIRST='  ',SECOND='proxy');self.assertEqual(self.s.ai_proxy_url_from_environment(),('valid:proxy','SECOND'));self.environ['FIRST']='bad';self.validate.side_effect=HTTPException(400,'invalid');self.assertEqual(self.s.ai_proxy_url_from_environment(),('','FIRST'));self.validate.assert_called_with('bad')
 def test_environment_unexpected_error_propagates(self):
  self.environ['FIRST']='proxy';sentinel=ValueError('validation');self.validate.side_effect=sentinel
  with self.assertRaises(ValueError) as err:self.s.ai_proxy_url_from_environment()
  self.assertIs(err.exception,sentinel)
 def test_environment_flag_existing_permissive_policy(self):
  self.assertTrue(self.s.env_flag_enabled('FLAG'));self.assertFalse(self.s.env_flag_enabled('FLAG',False))
  for value in ('0','FALSE',' no ','off','disabled'):self.environ['FLAG']=value;self.assertFalse(self.s.env_flag_enabled('FLAG'))
  for value in ('','nonsense','yes','1'):self.environ['FLAG']=value;self.assertTrue(self.s.env_flag_enabled('FLAG'))
 def test_socket_defaults_timeout_and_missing_port(self):
  self.assertTrue(self.s.local_proxy_available());self.connect.assert_called_once_with(('127.0.0.1',17890),timeout=.15);self.connect.reset_mock();self.assertFalse(self.s.local_proxy_available('http://example.com'));self.connect.assert_not_called()
  with self.assertRaises(ValueError):self.s.local_proxy_available('http://example.com:bad')
 def test_socket_oserror_caught_other_failure_preserved(self):
  self.connect.side_effect=OSError('closed');self.assertFalse(self.s.local_proxy_available('http://example.com:80'));self.connect.side_effect=RuntimeError('unexpected')
  with self.assertRaisesRegex(RuntimeError,'unexpected'):self.s.local_proxy_available('http://example.com:80')
 def test_configuration_env_then_explicit_and_invalid(self):
  self.environ['FIRST']='env';self.assertEqual(self.s.ai_proxy_url_from_config({'proxy_url':'config'},'gemini'),('valid:env','FIRST',False));self.environ.clear();self.assertEqual(self.s.ai_proxy_url_from_config({'proxy_url':'config'},'openai'),('valid:config','ai_config.local.proxy_url',False));self.validate.side_effect=HTTPException(400,'invalid');self.assertEqual(self.s.ai_proxy_url_from_config({'proxy_url':'bad'},'gemini'),('','ai_config.local.proxy_url_invalid',False));self.connect.assert_not_called()
 def test_invalid_environment_can_use_explicit_config(self):
  self.environ['FIRST']='bad';self.validate.side_effect=lambda v:(_ for _ in ()).throw(HTTPException(400,'bad')) if v=='bad' else v;self.assertEqual(self.s.ai_proxy_url_from_config({'proxy_url':'good'},'gemini'),('good','ai_config.local.proxy_url',False))
 def test_auto_local_only_gemini_and_flags(self):
  self.assertEqual(self.s.ai_proxy_url_from_config({},'openai'),('','',False));self.connect.assert_not_called();self.assertEqual(self.s.ai_proxy_url_from_config({},'gemini'),('http://127.0.0.1:17890','auto_local_mihomo',True));self.environ['AUTO']='off';self.assertEqual(self.s.ai_proxy_url_from_config({},'gemini'),('','',False));self.environ.clear();self.assertEqual(self.s.ai_proxy_url_from_config({'auto_local_proxy':False},'gemini'),('','',False))
 def test_direct_and_proxy_dispatch_return_identity(self):
  request=object();self.assertEqual(self.s.ai_urlopen(request,{},timeout=12),'response');self.open.assert_called_once_with(request,timeout=12)
  self.assertEqual(self.s.ai_urlopen(request,{'proxy_url_raw':' raw ','proxy_url':'display'},timeout=13),'proxied');self.handler.assert_called_once_with({'http':'raw','https':'raw'});self.opener.open.assert_called_once_with(request,timeout=13)
 def test_transport_exception_and_selected_opener_before_handler(self):
  sentinel=OSError('network');self.open.side_effect=sentinel
  with self.assertRaises(OSError) as err:self.s.ai_urlopen(object(),{},timeout=1)
  self.assertIs(err.exception,sentinel)
  original=self.b['urllib'].request.build_opener
  def handler(v):self.b['urllib'].request.build_opener=Mock(side_effect=AssertionError('late'));return 'handler'
  self.b['urllib'].request.ProxyHandler=handler;self.assertEqual(self.s.ai_urlopen(object(),{'proxy_url':'proxy'},timeout=1),'proxied');original.assert_called_once_with('handler')
 @unittest.skipIf(bool(BASELINE),'candidate assembly only')
 def test_actual_wiring(self):
  tree=ast.parse(restore_infrastructure_root(read_checked_application_source(ROOT / 'local_inspection_service/server.py')));alias=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_provider_proxy_runtime' for t in n.targets))
  self.assertEqual(ast.unparse(alias),'_provider_configuration.proxy')
  binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_provider_configuration' for t in n.targets));count=0
  for group in [k for k in binding.keywords if k.arg in ('proxy_settings','proxy_calls','proxy_transports')]:
   for kw in group.value.keywords:self.assertIsInstance(kw.value,ast.Lambda);self.assertEqual(kw.arg,kw.value.body.id);count+=1
  self.assertEqual(count,10)
  from scripts.smoke_model_configuration_composition import provider_inputs
  from local_inspection_service.model_providers.configuration_composition import ProviderConfiguration
  inputs,poison=provider_inputs();owner=ProviderConfiguration(**inputs)
  for name in ('validate_ai_proxy_url','ai_proxy_url_from_environment','env_flag_enabled','local_proxy_available'):
   selected=getattr(owner.proxy.calls,name)();expected=getattr(owner,name)
   self.assertIs(selected.__self__,owner);self.assertIs(selected.__func__,expected.__func__)
  poison.assert_not_called()
if __name__=='__main__':unittest.main()

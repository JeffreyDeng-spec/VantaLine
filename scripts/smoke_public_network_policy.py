"""Existing origin admission and public endpoint/path projection policy."""
import ast,ipaddress,os,re,sys,unittest
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_PUBLIC_NETWORK_BASELINE_SOURCE')
NAMES=('normalize_origin','same_origin','cors_origin_allowed','is_private_or_local_host','sanitize_url_for_public_user','sanitize_path_for_public_user','include_internal_runtime_details')
def create(b):
 if BASELINE:
  nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==7
  ns=dict(b,Any=Any,urlsplit=urlsplit,ipaddress=ipaddress,re=re);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
 from local_inspection_service.auth.public_network import PublicNetworkPolicy
 from local_inspection_service.auth.public_network_ports import OriginPolicy,PublicEndpointPolicy,RuntimeDetailAccess
 def ports(cls):return cls(**{f.name:lambda name=f.name:b[name] for f in fields(cls)})
 service=PublicNetworkPolicy(ports(OriginPolicy),ports(PublicEndpointPolicy),ports(RuntimeDetailAccess))
 for n in NAMES:
  if n not in b:b[n]=getattr(service,n)
 return service,b
class Contracts(unittest.TestCase):
 def setUp(self):
  self.masked=Mock(side_effect=lambda v:'masked:'+v)
  self.s,self.b=create(dict(CORS_ORIGINS=['https://example.com:443/path'],CORS_ORIGIN_REGEX=r'^http://127\.0\.0\.1(?::\d+)?$',masked_url_for_status=self.masked,user_is_admin=lambda u:u.get('admin',False),user_has_permission=lambda u,p:p in u.get('permissions',[])))
 def test_origin_normalization_defaults_credentials_ipv6(self):
  cases={'HTTPS://User:pass@ExAmPlE.com:443/path?q=x':'https://example.com','http://example.com:80':'http://example.com','https://example.com:8443/path':'https://example.com:8443','ftp://example.com:80':'ftp://example.com','http://[::1]:8080':'http://::1:8080','missing':'','https:///missing':''}
  for raw,out in cases.items():self.assertEqual(self.s.normalize_origin(raw),out)
  with self.assertRaises(ValueError):self.s.normalize_origin('https://example.com:bad')
 def test_same_origin_ports_hosts_and_malformed(self):
  for origin,host,expected in [('https://EXAMPLE.com','example.com:443',True),('https://example.com:444','example.com',False),('http://example.com','evil.example.com',False),('bad','example.com',False),('http://[::1]:80','[::1]',True)]:self.assertEqual(self.s.same_origin(origin,host),expected)
  with self.assertRaises(ValueError):self.s.same_origin('https://example.com:bad','example.com')
 def test_cors_list_regex_and_empty_short_circuit(self):
  self.assertTrue(self.s.cors_origin_allowed('https://EXAMPLE.com/path'));self.assertTrue(self.s.cors_origin_allowed('http://127.0.0.1:8080'));self.assertFalse(self.s.cors_origin_allowed('https://other.example'));self.b['CORS_ORIGIN_REGEX']='[';self.assertFalse(self.s.cors_origin_allowed(''))
  with self.assertRaises(re.error):self.s.cors_origin_allowed('https://other.example')
 def test_cors_list_evaluation_and_late_regex(self):
  self.b['CORS_ORIGINS']=['https://example.com','https://example.com:bad']
  with self.assertRaises(ValueError):self.s.cors_origin_allowed('https://example.com')
  self.b['CORS_ORIGINS']=[];self.b['normalize_origin']=lambda v:self.b.__setitem__('CORS_ORIGIN_REGEX','^changed$') or 'changed';self.assertTrue(self.s.cors_origin_allowed('ignored'))
 def test_host_policy_no_dns_and_known_private_values(self):
  for host in ('localhost','  LOCALHOST  ','127.0.0.1','::1','192.168.1.4','10.1.2.3','169.254.1.2','printer.local'):self.assertTrue(self.s.is_private_or_local_host(host))
  for host in ('','example.com','8.8.8.8','not-an-ip'):self.assertFalse(self.s.is_private_or_local_host(host))
 def test_url_invalid_private_and_masker(self):
  for value in (None,'','/relative','http://localhost:8080/private','http://192.168.0.1/x'):self.assertEqual(self.s.sanitize_url_for_public_user(value),'')
  self.masked.assert_not_called();self.assertEqual(self.s.sanitize_url_for_public_user(' https://example.com/path '),'masked:https://example.com/path');self.masked.assert_called_once_with('https://example.com/path')
 def test_url_selected_callback_and_failure(self):
  self.b['is_private_or_local_host']=lambda h:self.b.__setitem__('masked_url_for_status',lambda v:'new') or False;self.assertEqual(self.s.sanitize_url_for_public_user('https://example.com'),'new')
  sentinel=RuntimeError('mask');self.b['is_private_or_local_host']=lambda h:False;self.b['masked_url_for_status']=Mock(side_effect=sentinel)
  with self.assertRaises(RuntimeError) as err:self.s.sanitize_url_for_public_user('https://example.com')
  self.assertIs(err.exception,sentinel)
 def test_path_projection_is_existing_lexical_policy(self):
  for raw in (None,'','/private/root','C:/private/root','d:\\private\\file'):self.assertEqual(self.s.sanitize_path_for_public_user(raw),'')
  for raw in ('relative/path','../parent','https://example.com','\\\\server\\share'):self.assertEqual(self.s.sanitize_path_for_public_user(raw),raw)
 def test_runtime_detail_access_short_circuit_and_identity(self):
  self.b['user_has_permission']=Mock(side_effect=AssertionError('admin bypass'));self.assertTrue(self.s.include_internal_runtime_details({'admin':True}));self.b['user_has_permission']=lambda u,p:p in u.get('permissions',[]);self.assertTrue(self.s.include_internal_runtime_details({'permissions':['system_settings']}));self.assertFalse(self.s.include_internal_runtime_details(None))
 @unittest.skipIf(bool(BASELINE),'candidate assembly only')
 def test_actual_wiring(self):
  tree=ast.parse((ROOT/'local_inspection_service/server.py').read_text());binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_public_network_policy' for t in n.targets));count=0
  from application_integration_source_contract import verify_actual_compositions
  verify_actual_compositions()
  self.assertEqual(len(binding.keywords),3)
  for group in binding.keywords:
   for kw in group.value.keywords:
    self.assertIsInstance(kw.value,ast.Lambda)
    expected='_provider_configuration.masked_url_for_status' if kw.arg=='masked_url_for_status' else kw.arg
    self.assertEqual(ast.dump(kw.value.body),ast.dump(ast.parse(expected,mode='eval').body))
    self.assertFalse(kw.value.args.args);count+=1
  self.assertEqual(count,7)
if __name__=='__main__':unittest.main()

"""Synthetic behavior baseline for provider configuration defaults and validation."""
import os,sys,tempfile,unittest
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path.cwd()))
class ProviderConfigurationPolicyContracts(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.env=patch.dict(os.environ);cls.env.start();cls.tmp=tempfile.TemporaryDirectory(prefix='provider-policy-')
  (Path(cls.tmp.name)/'local_inspection_service/static').mkdir(parents=True)
  os.environ.update(LOCAL_INSPECTION_ROOT=cls.tmp.name,VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
  from local_inspection_service import server
  cls.api=server
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup();cls.env.stop()
 def setUp(self):
  self.stack=ExitStack();self.addCleanup(self.stack.close)
  for name in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):
   self.stack.enter_context(patch(name,side_effect=AssertionError('external operation forbidden')))
 def test_json_defaults_known_unknown_and_empty(self):
  with patch.object(self.api,'AI_DEFAULT_MODELS',{'known':'known-model'}),patch.object(self.api,'AI_DEFAULT_MODEL','default-model'),patch.object(self.api,'AI_DEFAULT_PROVIDER','default'),patch.object(self.api,'AI_DEFAULT_BASE_URLS',{'known':'known-base','default':'default-base'}),patch.object(self.api,'AI_PROVIDER_LABELS',{'known':'known-label'}):
   self.assertEqual([self.api.default_ai_model(v) for v in ('known','unknown','')],['known-model','default-model','default-model'])
   self.assertEqual([self.api.default_ai_base_url(v) for v in ('known','unknown','')],['known-base','default-base','default-base'])
   self.assertEqual([self.api.ai_provider_label(v) for v in ('known','unknown','')],['known-label','unknown','default'])
 def test_image_defaults_known_unknown_and_empty(self):
  values={'IMAGE_GENERATION_DEFAULT_PROVIDER':'default','IMAGE_GENERATION_DEFAULT_MODELS':{'known':'known-model','default':'default-model'},'IMAGE_GENERATION_DEFAULT_BASE_URLS':{'known':'known-base','default':'default-base'},'IMAGE_GENERATION_DEFAULT_API_KEY_ENVS':{'known':'KNOWN_KEY'},'IMAGE_GENERATION_API_KEY_ENV':'DEFAULT_KEY','IMAGE_GENERATION_PROVIDER_KEYS':{'known':'known-key','default':'default-key'},'IMAGE_GENERATION_PROVIDER_LABELS':{'known':'known-label'}}
  with patch.multiple(self.api,**values):
   for method,expected in [(self.api.default_image_generation_model,['known-model','default-model','default-model']),(self.api.default_image_generation_base_url,['known-base','default-base','default-base']),(self.api.default_image_generation_api_key_env,['KNOWN_KEY','DEFAULT_KEY','DEFAULT_KEY']),(self.api.image_generation_provider_key,['known-key','default-key','default-key']),(self.api.image_generation_provider_label,['known-label','unknown','default'])]:
    with self.subTest(method=method.__name__):self.assertEqual([method(v) for v in ('known','unknown','')],expected)
 def test_eager_default_lookup_errors_even_for_known_provider(self):
  cases=[('default_ai_base_url','AI_DEFAULT_BASE_URLS','AI_DEFAULT_PROVIDER'),('default_image_generation_model','IMAGE_GENERATION_DEFAULT_MODELS','IMAGE_GENERATION_DEFAULT_PROVIDER'),('default_image_generation_base_url','IMAGE_GENERATION_DEFAULT_BASE_URLS','IMAGE_GENERATION_DEFAULT_PROVIDER'),('image_generation_provider_key','IMAGE_GENERATION_PROVIDER_KEYS','IMAGE_GENERATION_DEFAULT_PROVIDER')]
  for method,mapping,default in cases:
   with self.subTest(method=method),patch.object(self.api,mapping,{'known':'value'}),patch.object(self.api,default,'missing'):
    with self.assertRaises(KeyError) as caught:getattr(self.api,method)('known')
    self.assertEqual(caught.exception.args,('missing',))
 def assert_http(self,method,value,message):
  with self.assertRaises(self.api.HTTPException) as caught:method(value)
  self.assertEqual(caught.exception.status_code,400);self.assertEqual(caught.exception.detail,message)
 def test_provider_validation_case_and_exact_errors(self):
  self.assertEqual(self.api.validate_ai_provider(' QWEN '),'qwen');self.assertEqual(self.api.validate_image_generation_provider(' QWEN_IMAGE '),'qwen_image')
  self.assert_http(self.api.validate_ai_provider,None,'Unsupported AI provider: (empty)')
  self.assert_http(self.api.validate_ai_provider,'other','Unsupported AI provider: other')
  self.assert_http(self.api.validate_image_generation_provider,'other','Unsupported image generation provider: other')
 def test_model_validation_grammar_and_length(self):
  for value in ('a','a/b:c@d+e_f-g.1','x'*160):self.assertEqual(self.api.validate_ai_model(' '+value+' '),value)
  self.assert_http(self.api.validate_ai_model,'','AI model is required')
  for value in ('x'*161,'a b','a?b','模型'):self.assert_http(self.api.validate_ai_model,value,'AI model contains unsupported characters')
 def test_base_url_scheme_credentials_query_and_loopback(self):
  for value in ('https://synthetic.invalid/v1','http://localhost/v1','http://127.0.0.1:8000','http://[::1]/x'):
   self.assertEqual(self.api.validate_ai_base_url(' '+value+' '),value)
  for value,message in [('ftp://host','AI base_url must be an http(s) URL'),('https://','AI base_url must be an http(s) URL'),('https://user:password@synthetic.invalid','AI base_url must not include credentials'),('https://synthetic.invalid?a=1','AI base_url must not include query strings or fragments'),('https://synthetic.invalid#x','AI base_url must not include query strings or fragments'),('http://synthetic.invalid','AI base_url must use https unless it targets localhost')]:self.assert_http(self.api.validate_ai_base_url,value,message)
 def test_public_url_removes_credentials_query_fragment_and_preserves_ipv6(self):
  self.assertEqual(self.api.public_ai_base_url('https://user:synthetic@[::1]:8443/path?secret=x#private'),'https://[::1]:8443/path')
  self.assertEqual(self.api.masked_url_for_status('https://user:synthetic@[::1]:8443/path?secret=x#private'),'https://****@[::1]:8443/path')
  self.assertEqual(self.api.masked_url_for_status('https://synthetic.invalid:443/x'),'https://synthetic.invalid:443/x')
 def test_public_url_invalid_port_and_relative_truncation(self):
  for method in (self.api.public_ai_base_url,self.api.masked_url_for_status):
   self.assertEqual(method('https://synthetic.invalid:bad/path?a=b'),'https://synthetic.invalid/path')
   self.assertEqual(method('relative/path?secret=x#private'),'relative/path')
   self.assertEqual(method('x'*400+'?secret=x'),'x'*300)
 def test_proxy_allows_credentials_remote_http_and_empty(self):
  for value in ('','http://user:synthetic@proxy.invalid:8080','https://proxy.invalid'):
   self.assertEqual(self.api.validate_ai_proxy_url(' '+value+' '),value)
  self.assert_http(self.api.validate_ai_proxy_url,'ftp://host','AI proxy URL must be an http(s) URL')
  self.assert_http(self.api.validate_ai_proxy_url,'https://host?q=1','AI proxy URL must not include query strings or fragments')
 def test_timeout_bounds_rounding_nan_and_numeric_error(self):
  cases=[(self.api.validate_ai_timeout,0.5,30.0,'AI timeout must be a number','AI timeout must be between 0.5 and 30 seconds'),(self.api.validate_image_generation_timeout,10.0,300.0,'Image generation timeout must be a number','Image generation timeout must be between 10 and 300 seconds')]
  for method,minimum,maximum,number,bounds in cases:
   self.assertEqual(method(minimum),minimum);self.assertEqual(method(maximum),maximum);self.assertEqual(method(str(minimum+0.1234)),round(minimum+0.1234,3))
   for value in (None,'bad'):self.assert_http(method,value,number)
   for value in (minimum-0.01,maximum+0.01,float('nan'),float('inf')):self.assert_http(method,value,bounds)
 def test_key_environment_name_validation(self):
  for value in ('','_KEY','A_123'):self.assertEqual(self.api.validate_ai_key_env(' '+value+' '),value)
  for value in ('1KEY','A-B','A B'):self.assert_http(self.api.validate_ai_key_env,value,'AI api_key_env must be a valid environment variable name')
 def test_unknown_url_parser_failure_is_not_retried(self):
  from itertools import chain,repeat
  from urllib.parse import urlsplit
  for method in (self.api.validate_ai_base_url,self.api.public_ai_base_url,self.api.masked_url_for_status,self.api.validate_ai_proxy_url):
   error=RuntimeError('synthetic-parse')
   with patch.object(self.api,'urlsplit',side_effect=chain([error],repeat(urlsplit('https://synthetic.invalid')))) as parser:
    with self.assertRaises(RuntimeError) as caught:method('https://synthetic.invalid')
   self.assertIs(caught.exception,error);parser.assert_called_once_with('https://synthetic.invalid')

 def test_default_mapping_receiver_and_later_fallback_are_selected_separately(self):
  events=[]
  class Later(dict):
   def __getitem__(inner,key):events.append(('later-default',key));self.api.AI_DEFAULT_BASE_URLS={'known':'wrong-late-value','default':'wrong-late-default'};return super().__getitem__(key)
  later=Later(default='later-fallback')
  class First(dict):
   @property
   def get(inner):
    events.append(('select-first-get',));self.api.AI_DEFAULT_BASE_URLS=later
    def chosen(key,default):events.append(('first-get',key,default));return dict.get(inner,key,default)
    return chosen
  with patch.object(self.api,'AI_DEFAULT_PROVIDER','default'),patch.object(self.api,'AI_DEFAULT_BASE_URLS',First(known='first-value',default='stale-fallback')):
   self.assertEqual(self.api.default_ai_base_url('known'),'first-value')
  self.assertEqual(events,[('select-first-get',),('later-default','default'),('first-get','known','later-fallback')])
 def test_provider_policy_refreshes_between_calls(self):
  with patch.object(self.api,'AI_SUPPORTED_PROVIDERS',{'first'}):
   self.assertEqual(self.api.validate_ai_provider('first'),'first');self.api.AI_SUPPORTED_PROVIDERS={'second'}
   result=error=None
   try:result=self.api.validate_ai_provider('second')
   except BaseException as caught:error=caught
   self.assertIsNone(error);self.assertEqual(result,'second');self.assert_http(self.api.validate_ai_provider,'first','Unsupported AI provider: first')
 def test_http_error_constructor_is_selected_after_validation_callback(self):
  class ReplacementError(Exception):
   def __init__(inner,*,status_code,detail):inner.status_code=status_code;inner.detail=detail
  def no_match(pattern,value):self.api.HTTPException=ReplacementError;return None
  with patch.object(self.api,'HTTPException',self.api.HTTPException),patch.object(self.api.re,'fullmatch',no_match):
   error=None
   try:self.api.validate_ai_model('valid-text')
   except BaseException as caught:error=caught
   self.assertIs(type(error),ReplacementError);self.assertEqual(error.status_code,400);self.assertEqual(error.detail,'AI model contains unsupported characters')


 def test_unknown_formatter_join_and_regex_failure_is_not_retried(self):
  from itertools import chain,repeat
  cases=[(self.api.public_ai_base_url,'bounded_text','relative/path','safe'),(self.api.masked_url_for_status,'bounded_text','relative/path','safe'),(self.api.public_ai_base_url,'urlunsplit','https://synthetic.invalid','safe'),(self.api.masked_url_for_status,'urlunsplit','https://synthetic.invalid','safe')]
  for method,name,value,recovery in cases:
   with self.subTest(method=method.__name__,name=name):
    error=RuntimeError('synthetic-first')
    with patch.object(self.api,name,side_effect=chain([error],repeat(recovery))) as dependency:
     with self.assertRaises(RuntimeError) as caught:method(value)
    self.assertIs(caught.exception,error);dependency.assert_called_once()
  error=RuntimeError('synthetic-regex')
  with patch.object(self.api.re,'fullmatch',side_effect=chain([error],repeat(True))) as dependency:
   with self.assertRaises(RuntimeError) as caught:self.api.validate_ai_model('model')
  self.assertIs(caught.exception,error);dependency.assert_called_once()


 def test_independent_services_keep_separate_policy_and_callbacks(self):
  from local_inspection_service.model_providers.configuration_ports import JsonDefaults,ImageDefaults,ValidationCapabilities,PublicUrlCapabilities
  from local_inspection_service.model_providers.configuration_defaults import ProviderDefaults
  from local_inspection_service.model_providers.configuration_validation import ProviderValidation
  from local_inspection_service.model_providers.public_urls import PublicProviderURLs
  from urllib.parse import urlsplit,urlunsplit
  from re import fullmatch
  from fastapi import HTTPException
  from concurrent.futures import ThreadPoolExecutor
  def make(label):
   defaults=ProviderDefaults(JsonDefaults(lambda:{label:label+'-model'},lambda:label+'-fallback',lambda:{label:'https://'+label+'.invalid'},lambda:label,lambda:{label:label+'-label'}),ImageDefaults(lambda:{label:label+'-image'},lambda:{label:'https://'+label+'.invalid'},lambda:label,lambda:{label:label+'_KEY'},lambda:'DEFAULT_KEY',lambda:{label:label+'-key'},lambda:{label:label+'-label'}))
   validation=ProviderValidation(ValidationCapabilities(lambda:{label},lambda:{label},lambda:HTTPException,lambda:fullmatch,lambda:urlsplit))
   urls=PublicProviderURLs(PublicUrlCapabilities(lambda:urlsplit,lambda:urlunsplit,lambda:lambda value,limit:label+':'+str(value)[:limit]))
   return defaults,validation,urls
  a,b=make('a'),make('b')
  for name in ('urlsplit','urlunsplit','bounded_text','HTTPException'):
   self.stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('independent service used root')))
  self.stack.enter_context(patch.object(self.api,'AI_SUPPORTED_PROVIDERS',set()))
  def invoke(item):
   label,services=item;defaults,validation,urls=services
   return defaults.default_ai_model(label),defaults.default_image_generation_model(label),validation.validate_ai_provider(label),urls.public_ai_base_url('relative/path')
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(invoke,[('a',a),('b',b)]))
  self.assertEqual(results,[('a-model','a-image','a','a:relative/path'),('b-model','b-image','b','b:relative/path')])
  with self.assertRaises(HTTPException):a[1].validate_ai_provider('b')
 def test_constructor_reads_no_capabilities_or_request_state(self):
  from dataclasses import fields
  from local_inspection_service.model_providers.configuration_ports import JsonDefaults,ImageDefaults,ValidationCapabilities,PublicUrlCapabilities
  from local_inspection_service.model_providers.configuration_defaults import ProviderDefaults
  from local_inspection_service.model_providers.configuration_validation import ProviderValidation
  from local_inspection_service.model_providers.public_urls import PublicProviderURLs
  forbidden=Mock(side_effect=AssertionError('constructor read capability'))
  def port(cls):return cls(**{f.name:forbidden for f in fields(cls)})
  defaults=ProviderDefaults(port(JsonDefaults),port(ImageDefaults));validation=ProviderValidation(port(ValidationCapabilities));urls=PublicProviderURLs(port(PublicUrlCapabilities))
  forbidden.assert_not_called();self.assertEqual(set(vars(defaults)),{'_json','_image'});self.assertEqual(set(vars(validation)),{'_capabilities'});self.assertEqual(set(vars(urls)),{'_capabilities'})


 def test_public_url_join_capture_preserves_argument_effects(self):
  for method_name in ('public_ai_base_url','masked_url_for_status'):
   for mode in ('ordinary','prior','missing'):
    with self.subTest(method=method_name,mode=mode):capture_provider_policy_url_join(self.api,type(self),method_name,mode)

def capture_provider_policy_url_join(api, Fixture, method_name, mode):
    from unittest.mock import patch
    assert method_name in ('public_ai_base_url', 'masked_url_for_status')
    assert mode in ('ordinary', 'prior', 'missing')
    fixture = Fixture()
    fixture.setUp()
    try:
        ns = api.__dict__
        events = []
        def callback(label):
            def join(parts):
                events.append(['join', label, list(parts)])
                return label + '-joined'
            return join
        first, prior, late = callback('A'), callback('B'), callback('C')
        def choose_prior():
            if mode == 'prior':
                ns['urlunsplit'] = prior
            elif mode == 'missing':
                ns['urlunsplit'] = None
        class Parsed:
            scheme_reads = 0
            port_reads = 0
            netloc = 'user@synthetic.invalid:8443'
            hostname = 'synthetic.invalid'
            password = None
            @property
            def scheme(self):
                self.scheme_reads += 1
                if self.scheme_reads == 1:
                    events.append(['scheme.initial'])
                else:
                    events.append(['scheme.argument'])
                    ns['urlunsplit'] = late
                return 'https'
            @property
            def port(self):
                self.port_reads += 1
                if self.port_reads == 2 and method_name == 'public_ai_base_url':
                    events.append(['port.prior'])
                    choose_prior()
                return 8443
            @property
            def username(self):
                events.append(['username.prior'])
                choose_prior()
                return 'user'
            @property
            def path(self):
                events.append(['path.argument'])
                return '/path'
        parsed = Parsed()
        with patch.dict(ns):
            ns['urlsplit'] = lambda value: parsed
            ns['urlunsplit'] = first
            result = error = None
            try:
                result = getattr(api, method_name)('https://synthetic.invalid/path')
            except BaseException as caught:
                error = caught
            expected = [['scheme.initial'], ['port.prior' if method_name == 'public_ai_base_url' else 'username.prior'], ['scheme.argument'], ['path.argument']]
            if mode == 'missing':
                fixture.assertIs(type(error), TypeError)
                fixture.assertIsNone(result)
            else:
                fixture.assertIsNone(error)
                selected = 'B' if mode == 'prior' else 'A'
                fixture.assertEqual(result, selected + '-joined')
                authority = 'synthetic.invalid:8443' if method_name == 'public_ai_base_url' else '****@synthetic.invalid:8443'
                expected.append(['join', selected, ['https', authority, '/path', '', '']])
            fixture.assertEqual(events, expected)
            fixture.assertEqual(parsed.scheme_reads, 2)
            fixture.assertEqual(parsed.port_reads, 2)
            return {'method': method_name, 'mode': mode, 'events': events, 'exception': None if error is None else type(error).__name__, 'result': result}
    finally:
        fixture.doCleanups()

if __name__=='__main__':unittest.main()

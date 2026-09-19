"""Synthetic pre-extraction contracts for legacy migration provider settings."""
import copy,os,sys,tempfile,unittest
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path.cwd()))
class LegacyProviderSettingsContracts(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.env=patch.dict(os.environ);cls.env.start();cls.tmp=tempfile.TemporaryDirectory(prefix='legacy-provider-settings-')
  (Path(cls.tmp.name)/'local_inspection_service/static').mkdir(parents=True)
  os.environ.update(LOCAL_INSPECTION_ROOT=cls.tmp.name,VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
  from local_inspection_service import server
  cls.api=server
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup();cls.env.stop()
 def setUp(self):
  self.stack=ExitStack();self.addCleanup(self.stack.close);self.stack.enter_context(patch.dict(os.environ,{},clear=True))
  for name in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):
   self.stack.enter_context(patch(name,side_effect=AssertionError('external operation forbidden')))
  self.local={'provider':'qwen','model':'synthetic-json','base_url':'https://synthetic.invalid','timeout_seconds':30,'api_key_env':'SYNTHETIC_JSON_KEY','image_provider':'gemini','image_model':'synthetic-image','image_base_url':'https://synthetic.invalid','image_timeout_seconds':60}
  self.keys=[{'id':'a','key':'local-a','env':'LOCAL_A','label':'A','provider':'qwen'},{'id':'b','key':'local-b','env':'LOCAL_B','label':'B','provider':'qwen'}]
  self.image_keys=[{'id':'i','key':'local-image','env':'LOCAL_IMAGE','label':'I','provider':'gemini'}]
  def install(name,**kwargs):return self.stack.enter_context(patch.object(self.api,name,**kwargs))
  self.load=install('load_ai_local_config',return_value=self.local)
  self.normalize=install('normalize_ai_key_items',side_effect=lambda local,provider:self.keys)
  self.select=install('ai_keys_for_provider',side_effect=lambda keys,provider:keys)
  self.image_normalize=install('normalize_image_key_items',side_effect=lambda local,provider:self.image_keys)
  self.image_select=install('image_keys_for_provider',side_effect=lambda keys,provider:keys)
  self.proxy=install('ai_proxy_url_from_config',return_value=('synthetic-proxy','synthetic-source',False))
  self.timeout=install('validate_ai_timeout',side_effect=float);self.image_timeout=install('validate_image_generation_timeout',side_effect=float)
  self.base=install('validate_ai_base_url',return_value=None)
  install('default_ai_base_url',side_effect=lambda p:'https://default.invalid/'+p)
  install('default_image_generation_model',side_effect=lambda p:'default-'+p)
  install('default_image_generation_base_url',side_effect=lambda p:'https://image.invalid/'+p)
  install('default_image_generation_api_key_env',return_value='SYNTHETIC_IMAGE_KEY')
  install('secret_key_item_id',side_effect=lambda env,key:'id-'+env+'-'+key)
  install('bounded_text',side_effect=lambda value,limit:str(value)[:limit])
  install('ai_provider_label',side_effect=lambda p:'label-'+p)
  install('image_generation_provider_label',side_effect=lambda p:'label-'+p)
  install('image_generation_provider_key',side_effect=lambda p:'key-'+p)
  install('public_ai_key_items',side_effect=lambda keys:[{'id':k['id']} for k in keys])
  install('mask_secret',side_effect=lambda key:'masked' if key else '')
  install('public_ai_base_url',side_effect=lambda value:'public:'+value)
  install('masked_url_for_status',side_effect=lambda value:'masked:'+value)
  install('env_flag_enabled',return_value=True)
 def test_json_key_precedence_and_active_order(self):
  self.local['active_key_id']='b';os.environ.update(INSPECTION_AI_API_KEY='direct',SYNTHETIC_JSON_KEY='named')
  r=self.api._legacy_ai_detection_settings();self.assertEqual(r['api_key'],'direct');self.assertEqual(r['key_source_name'],'INSPECTION_AI_API_KEY');self.assertEqual(r['active_key_id'],'b');self.assertEqual([k['key'] for k in r['api_key_candidates']],['direct','local-a','local-b','named'])
  del os.environ['INSPECTION_AI_API_KEY'];self.assertEqual(self.api._legacy_ai_detection_settings()['api_key'],'named')
  del os.environ['SYNTHETIC_JSON_KEY'];r=self.api._legacy_ai_detection_settings();self.assertEqual(r['api_key'],'local-b');self.assertEqual(r['key_source_name'],'LOCAL_B');self.assertEqual(r['api_key_candidates'][0]['key'],'local-b')
 def test_json_candidates_deduplicate_without_reordering_other_keys(self):
  self.keys.append(dict(self.keys[0]));os.environ.update(INSPECTION_AI_API_KEY='local-a',SYNTHETIC_JSON_KEY='local-b')
  r=self.api._legacy_ai_detection_settings();self.assertEqual([k['key'] for k in r['api_key_candidates']],['local-a','local-b']);self.assertEqual(r['api_key_candidates'][0]['id'],'a')
 def test_json_provider_environment_model_and_default_key_env(self):
  self.local['api_key_env']=''
  for provider,keyenv in [('gemini','GEMINI_API_KEY'),('qwen','DASHSCOPE_API_KEY')]:
   with self.subTest(provider=provider):
    os.environ.update(INSPECTION_AI_PROVIDER=' '+provider.upper()+' ',INSPECTION_AI_MODEL=' synthetic-env ')
    r=self.api._legacy_ai_detection_settings();self.assertEqual(r['provider'],provider);self.assertEqual(r['api_key_env'],keyenv);self.assertEqual(r['model'],'synthetic-env')
 def test_json_status_precedence_unsupported_invalid_missing(self):
  self.local['provider']='unsupported';r=self.api._legacy_ai_detection_settings();self.assertEqual(r['status'],'unsupported_provider');self.assertFalse(r['configured'])
  self.local['provider']='qwen';self.base.side_effect=self.api.HTTPException(400,'synthetic')
  self.assertEqual(self.api._legacy_ai_detection_settings()['status'],'invalid_base_url')
  self.base.side_effect=None;self.keys=[];r=self.api._legacy_ai_detection_settings();self.assertEqual(r['status'],'missing_api_key');self.assertFalse(r['enabled'])
 def test_json_timeout_http_failure_uses_default(self):
  self.timeout.side_effect=self.api.HTTPException(400,'synthetic');r=self.api._legacy_ai_detection_settings();self.assertEqual(r['timeout_seconds'],self.api.AI_DEFAULT_TIMEOUT_SECONDS)
 def test_json_inputs_unmodified_public_fields_and_alias(self):
  before=copy.deepcopy((self.local,self.keys));r=self.api._legacy_ai_detection_settings();self.assertEqual((self.local,self.keys),before)
  self.assertTrue(r['configured']);self.assertEqual(r['status'],'ready');self.assertEqual(r['masked_key'],'masked');self.assertEqual(r['proxy_url_raw'],'synthetic-proxy');self.assertEqual(r['proxy_url'],'masked:synthetic-proxy');self.assertIs(r['model_options'],self.api.AI_MODEL_OPTIONS)
 def test_image_local_key_precedes_direct_and_named(self):
  os.environ[self.api.IMAGE_GENERATION_API_KEY_ENV]='direct-image';os.environ['SYNTHETIC_IMAGE_KEY']='named-image'
  r=self.api._legacy_image_generation_settings();self.assertEqual(r['api_key'],'local-image');self.assertEqual(r['key_source_name'],'LOCAL_IMAGE')
  self.image_keys=[];self.assertEqual(self.api._legacy_image_generation_settings()['api_key'],'direct-image')
  del os.environ[self.api.IMAGE_GENERATION_API_KEY_ENV];self.assertEqual(self.api._legacy_image_generation_settings()['api_key'],'named-image')
 def test_image_provider_fallback_and_legacy_gemini_model(self):
  os.environ[self.api.IMAGE_GENERATION_PROVIDER_ENV]='unsupported';r=self.api._legacy_image_generation_settings();self.assertEqual(r['provider'],self.api.IMAGE_GENERATION_DEFAULT_PROVIDER)
  os.environ[self.api.IMAGE_GENERATION_PROVIDER_ENV]='gemini';os.environ[self.api.AGENT_MCP_GEMINI_IMAGE_MODEL_ENV]='legacy-image'
  self.assertEqual(self.api._legacy_image_generation_settings()['model'],'legacy-image')
  os.environ[self.api.IMAGE_GENERATION_MODEL_ENV]='current-image';self.assertEqual(self.api._legacy_image_generation_settings()['model'],'current-image')
 def test_image_timeout_clamps_and_http_default(self):
  for value,expected in [(1,10.0),(500,300.0),(42,42.0)]:
   self.local['image_timeout_seconds']=value;self.assertEqual(self.api._legacy_image_generation_settings()['timeout_seconds'],expected)
  self.image_timeout.side_effect=self.api.HTTPException(400,'synthetic');self.assertEqual(self.api._legacy_image_generation_settings()['timeout_seconds'],max(10.0,min(300.0,float(self.api.IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS))))
 def test_image_status_invalid_base_then_missing_model_then_key(self):
  self.base.side_effect=self.api.HTTPException(400,'synthetic');self.assertEqual(self.api._legacy_image_generation_settings()['status'],'invalid_base_url')
  self.base.side_effect=None;self.local['image_model']=''
  with patch.object(self.api,'default_image_generation_model',return_value=''):
   self.assertEqual(self.api._legacy_image_generation_settings()['status'],'missing_model')
  self.image_keys=[];self.assertEqual(self.api._legacy_image_generation_settings()['status'],'missing_api_key')
 def test_image_input_unmodified_and_public_aliases(self):
  before=copy.deepcopy((self.local,self.image_keys));r=self.api._legacy_image_generation_settings();self.assertEqual((self.local,self.image_keys),before);self.assertEqual(r['status'],'ready');self.assertTrue(r['configured']);self.assertEqual(r['provider_key'],'key-gemini');self.assertEqual(r['masked_key'],'masked');self.assertIs(r['model_options'],self.api.IMAGE_GENERATION_MODEL_OPTIONS)
 def test_unknown_settings_or_validation_failure_not_retried(self):
  from itertools import chain,repeat
  for method,target,recovery in [(self.api._legacy_ai_detection_settings,self.load,self.local),(self.api._legacy_image_generation_settings,self.load,self.local),(self.api._legacy_ai_detection_settings,self.timeout,30),(self.api._legacy_image_generation_settings,self.image_timeout,60)]:
   with self.subTest(method=method.__name__,target=target):
    error=RuntimeError('synthetic-first');target.reset_mock();saved=target.side_effect;target.side_effect=chain([error],repeat(recovery))
    with self.assertRaises(RuntimeError) as caught:method()
    self.assertIs(caught.exception,error);target.assert_called_once();target.side_effect=saved

 def test_timeout_exception_class_selected_after_validator_failure(self):
  class ReplacementError(Exception):pass
  for method,target,default in [(self.api._legacy_ai_detection_settings,self.timeout,self.api.AI_DEFAULT_TIMEOUT_SECONDS),(self.api._legacy_image_generation_settings,self.image_timeout,max(10.0,min(300.0,float(self.api.IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS))))]:
   with self.subTest(method=method.__name__):
    def invalid(value):self.api.HTTPException=ReplacementError;raise ReplacementError('synthetic')
    original=target.side_effect
    with patch.object(self.api,'HTTPException',self.api.HTTPException):
     target.side_effect=invalid;result=error=None
     try:result=method()
     except BaseException as caught:error=caught
     self.assertIsNone(error);self.assertIsNotNone(result);self.assertEqual(result['timeout_seconds'],default)
    target.side_effect=original
 def test_image_legacy_timeout_only_for_gemini(self):
  os.environ[self.api.AGENT_MCP_GEMINI_IMAGE_TIMEOUT_ENV]='91'
  self.assertEqual(self.api._legacy_image_generation_settings()['timeout_seconds'],91.0)
  self.local['image_provider']='qwen_image';self.assertEqual(self.api._legacy_image_generation_settings()['timeout_seconds'],60.0)
 def test_key_candidates_are_new_for_each_json_call(self):
  first=self.api._legacy_ai_detection_settings();first['api_key_candidates'].append({'key':'synthetic-injected'})
  second=self.api._legacy_ai_detection_settings();self.assertEqual([k['key'] for k in second['api_key_candidates']],['local-a','local-b']);self.assertIsNot(first['api_key_candidates'],second['api_key_candidates'])


 def test_base_exception_class_is_matched_at_failure(self):
  class ReplacementError(Exception):pass
  for method in (self.api._legacy_ai_detection_settings,self.api._legacy_image_generation_settings):
   with self.subTest(method=method.__name__):
    def invalid(value):self.api.HTTPException=ReplacementError;raise ReplacementError('synthetic-base')
    with patch.object(self.api,'HTTPException',self.api.HTTPException):
     self.base.side_effect=invalid;result=error=None
     try:result=method()
     except BaseException as caught:error=caught
     self.assertIsNone(error);self.assertIsNotNone(result);self.assertEqual(result['status'],'invalid_base_url')
  self.base.side_effect=None
 def test_environment_refreshes_after_load_and_proxy_callbacks(self):
  for method,model_env,key_env in [(self.api._legacy_ai_detection_settings,'INSPECTION_AI_MODEL','INSPECTION_AI_API_KEY'),(self.api._legacy_image_generation_settings,self.api.IMAGE_GENERATION_MODEL_ENV,self.api.IMAGE_GENERATION_API_KEY_ENV)]:
   with self.subTest(method=method.__name__):
    events=[]
    def load():events.append('load');os.environ={model_env:'after-load'};return self.local
    def proxy(local,provider):events.append('proxy');os.environ={key_env:'after-proxy'};return ('synthetic-proxy','synthetic-source',False)
    self.image_keys=[]
    with patch.object(os,'environ',{model_env:'before-load'}):
     self.load.side_effect=load;self.proxy.side_effect=proxy;r=method()
    self.assertEqual(r['model'],'after-load');self.assertEqual(r['api_key'],'after-proxy');self.assertEqual(events,['load','proxy'])
    self.load.side_effect=None;self.proxy.side_effect=None
 def test_image_label_callback_refreshes_between_message_and_public_label(self):
  calls=[]
  def replacement(provider):calls.append('second');return 'second-label'
  def first(provider):calls.append('first');self.api.image_generation_provider_label=replacement;return 'first-label'
  with patch.object(self.api,'image_generation_provider_label',first):r=self.api._legacy_image_generation_settings()
  self.assertEqual(r['message'],'first-label image generation is configured.');self.assertEqual(r['provider_label'],'second-label');self.assertEqual(calls,['first','second'])
 def test_unknown_base_failure_is_not_retried(self):
  from itertools import chain,repeat
  for method in (self.api._legacy_ai_detection_settings,self.api._legacy_image_generation_settings):
   error=RuntimeError('synthetic-base-first');self.base.reset_mock();self.base.side_effect=chain([error],repeat(None))
   with self.assertRaises(RuntimeError) as caught:method()
   self.assertIs(caught.exception,error);self.base.assert_called_once()
  self.base.side_effect=None


 def test_independent_settings_compositions_use_own_sources_with_root_poisoned(self):
  from local_inspection_service.model_providers.legacy_json_settings import LegacyJsonSettings
  from local_inspection_service.model_providers.legacy_image_settings import LegacyImageSettings
  from local_inspection_service.model_providers import legacy_settings_ports as ports
  from concurrent.futures import ThreadPoolExecutor
  def make(label):
   config=dict(self.local,model=label,image_model=label+'-image')
   state={'loads':0}
   def load():state['loads']+=1;return config
   def bind(value):return lambda:value
   json_service = LegacyJsonSettings(
    ports.LegacySettingsIO(load=bind(load), environment=bind({}), proxy=bind(self.api.ai_proxy_url_from_config), validate_base=bind(self.api.validate_ai_base_url), http_error=bind(self.api.HTTPException)),
    ports.LegacyPresentation(public_keys=bind(self.api.public_ai_key_items), mask_secret=bind(self.api.mask_secret), public_base=bind(self.api.public_ai_base_url), mask_url=bind(self.api.masked_url_for_status)),
    ports.LegacyJsonPolicy(provider=bind(self.api.AI_DEFAULT_PROVIDER), model=bind(self.api.AI_DEFAULT_MODEL), timeout=bind(self.api.AI_DEFAULT_TIMEOUT_SECONDS), models=bind(self.api.AI_MODEL_OPTIONS), supported=bind(self.api.AI_SUPPORTED_PROVIDERS), proxy_flag=bind(self.api.AI_AUTO_LOCAL_PROXY_ENV)),
    ports.LegacyJsonCallbacks(default_base=bind(self.api.default_ai_base_url), validate_timeout=bind(self.api.validate_ai_timeout), normalize_keys=bind(self.api.normalize_ai_key_items), select_keys=bind(self.api.ai_keys_for_provider), key_id=bind(self.api.secret_key_item_id), text=bind(self.api.bounded_text), label=bind(self.api.ai_provider_label), flag=bind(self.api.env_flag_enabled)),
   )
   image_service = LegacyImageSettings(
    ports.LegacySettingsIO(load=bind(load), environment=bind({}), proxy=bind(self.api.ai_proxy_url_from_config), validate_base=bind(self.api.validate_ai_base_url), http_error=bind(self.api.HTTPException)),
    ports.LegacyPresentation(public_keys=bind(self.api.public_ai_key_items), mask_secret=bind(self.api.mask_secret), public_base=bind(self.api.public_ai_base_url), mask_url=bind(self.api.masked_url_for_status)),
    ports.LegacyImagePolicy(provider=bind(self.api.IMAGE_GENERATION_DEFAULT_PROVIDER), timeout=bind(self.api.IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS), models=bind(self.api.IMAGE_GENERATION_MODEL_OPTIONS), supported=bind(self.api.IMAGE_GENERATION_SUPPORTED_PROVIDERS)),
    ports.LegacyImageEnvironment(provider=bind(self.api.IMAGE_GENERATION_PROVIDER_ENV), model=bind(self.api.IMAGE_GENERATION_MODEL_ENV), base=bind(self.api.IMAGE_GENERATION_BASE_URL_ENV), timeout=bind(self.api.IMAGE_GENERATION_TIMEOUT_ENV), named_key=bind(self.api.IMAGE_GENERATION_NAMED_API_KEY_ENV), direct_key=bind(self.api.IMAGE_GENERATION_API_KEY_ENV), gemini_model=bind(self.api.AGENT_MCP_GEMINI_IMAGE_MODEL_ENV), gemini_timeout=bind(self.api.AGENT_MCP_GEMINI_IMAGE_TIMEOUT_ENV)),
    ports.LegacyImageCallbacks(default_model=bind(self.api.default_image_generation_model), default_base=bind(self.api.default_image_generation_base_url), default_key_env=bind(self.api.default_image_generation_api_key_env), validate_timeout=bind(self.api.validate_image_generation_timeout), normalize_keys=bind(self.api.normalize_image_key_items), select_keys=bind(self.api.image_keys_for_provider), label=bind(self.api.image_generation_provider_label), provider_key=bind(self.api.image_generation_provider_key)),
   )
   self.assertEqual(state['loads'],0)
   return json_service,image_service,state
  aj,ai,sa=make('a');bj,bi,sb=make('b')
  for name in ('ai_keys_for_provider', 'ai_provider_label', 'ai_proxy_url_from_config', 'bounded_text', 'default_ai_base_url', 'default_image_generation_api_key_env', 'default_image_generation_base_url', 'default_image_generation_model', 'env_flag_enabled', 'image_generation_provider_key', 'image_generation_provider_label', 'image_keys_for_provider', 'load_ai_local_config', 'mask_secret', 'masked_url_for_status', 'normalize_ai_key_items', 'normalize_image_key_items', 'public_ai_base_url', 'public_ai_key_items', 'secret_key_item_id', 'validate_ai_base_url', 'validate_ai_timeout', 'validate_image_generation_timeout'):
   self.stack.enter_context(patch.object(self.api,name,side_effect=AssertionError("independent settings used application callback")))
  with ThreadPoolExecutor(max_workers=4) as pool:
   values=list(pool.map(lambda fn:fn(),[aj._legacy_ai_detection_settings,bj._legacy_ai_detection_settings,ai._legacy_image_generation_settings,bi._legacy_image_generation_settings]))
  self.assertEqual([v['model'] for v in values],['a','b','a-image','b-image'])
  self.assertEqual(sa['loads'],2);self.assertEqual(sb['loads'],2)
  self.assertIsNot(values[0]['api_key_candidates'],values[1]['api_key_candidates'])
 def test_independent_constructors_never_read_capabilities(self):
  from dataclasses import fields
  from local_inspection_service.model_providers.legacy_json_settings import LegacyJsonSettings
  from local_inspection_service.model_providers.legacy_image_settings import LegacyImageSettings
  from local_inspection_service.model_providers import legacy_settings_ports as ports
  forbidden=Mock(side_effect=AssertionError('constructor read capability'))
  def port(cls):return cls(**{field.name:forbidden for field in fields(cls)})
  json_service=LegacyJsonSettings(port(ports.LegacySettingsIO),port(ports.LegacyPresentation),port(ports.LegacyJsonPolicy),port(ports.LegacyJsonCallbacks))
  image_service=LegacyImageSettings(port(ports.LegacySettingsIO),port(ports.LegacyPresentation),port(ports.LegacyImagePolicy),port(ports.LegacyImageEnvironment),port(ports.LegacyImageCallbacks))
  forbidden.assert_not_called();self.assertEqual(set(vars(json_service)),{'_io','_presentation','_policy','_callbacks'});self.assertEqual(set(vars(image_service)),{'_io','_presentation','_policy','_environment','_callbacks'})


 def test_nested_key_callbacks_preserve_capture_windows(self):
  for site in ('key_id','text'):
   for mode in ('ordinary','prior','missing'):
    with self.subTest(site=site,mode=mode):capture_legacy_settings_window(self.api,type(self),site,mode)
 def test_key_callbacks_refresh_for_each_candidate(self):
  self.keys=[{'id':'','key':'a','env':'A','label':'first'},{'id':'','key':'b','env':'B','label':'second'}]
  events=[]
  def second_id(env,key):events.append(('id2',env));return 'second-id'
  def first_id(env,key):events.append(('id1',env));self.api.secret_key_item_id=second_id;return 'first-id'
  def second_text(value,limit):events.append(('text2',value));return 'second-text'
  def first_text(value,limit):events.append(('text1',value));self.api.bounded_text=second_text;return 'first-text'
  with patch.object(self.api,'secret_key_item_id',first_id),patch.object(self.api,'bounded_text',first_text):r=self.api._legacy_ai_detection_settings()
  self.assertEqual([(x['id'],x['label']) for x in r['api_key_candidates']],[('first-id','first-text'),('second-id','second-text')])
  self.assertEqual(events,[('id1','A'),('text1','first'),('id2','B'),('text2','second')])

def capture_legacy_settings_window(api, Fixture, site, mode):
    from unittest.mock import patch
    assert site in ('key_id', 'text')
    assert mode in ('ordinary', 'prior', 'missing')
    fixture = Fixture()
    fixture.setUp()
    try:
        events = []
        ns = api.__dict__
        name = 'secret_key_item_id' if site == 'key_id' else 'bounded_text'
        def callback(label):
            def invoke(*args):
                events.append(['call', label, list(args)])
                return label + '-result'
            return invoke
        first, prior, late = callback('A'), callback('B'), callback('C')
        def choose_prior():
            if mode == 'prior':
                ns[name] = prior
            elif mode == 'missing':
                ns[name] = None
        class PriorId:
            def __str__(self):
                events.append(['id.str'])
                choose_prior()
                return 'capture-id'
        class Candidate(dict):
            armed = False
            def get(self, key, default=None):
                if key == 'id':
                    if site == 'text':
                        return PriorId()
                    events.append(['id.get'])
                    choose_prior()
                    self.armed = True
                    return ''
                if site == 'key_id' and key == 'env' and self.armed:
                    self.armed = False
                    events.append(['env.argument'])
                    ns[name] = late
                elif site == 'text' and key == 'label':
                    events.append(['label.argument'])
                    ns[name] = late
                return super().get(key, default)
        fixture.keys = [Candidate(id='capture-id', key='capture-key', env='CAPTURE_ENV', label='capture-label', provider='qwen')]
        with patch.dict(ns):
            ns[name] = first
            result = error = None
            try:
                result = api._legacy_ai_detection_settings()
            except BaseException as caught:
                error = caught
            expected = [['id.get'], ['env.argument']] if site == 'key_id' else [['id.str'], ['label.argument']]
            if mode == 'missing':
                fixture.assertIs(type(error), TypeError)
                fixture.assertIsNone(result)
            else:
                fixture.assertIsNone(error)
                chosen = 'B' if mode == 'prior' else 'A'
                args = ['CAPTURE_ENV', 'capture-key'] if site == 'key_id' else ['capture-label', 80]
                expected.append(['call', chosen, args])
                fixture.assertIn('api_key_candidates', result)
                fixture.assertEqual(len(result['api_key_candidates']), 1)
                fixture.assertEqual(result['api_key_candidates'][0]['id' if site == 'key_id' else 'label'], chosen + '-result')
            fixture.assertEqual(events, expected)
            return {'site': site, 'mode': mode, 'events': events, 'exception': None if error is None else type(error).__name__, 'selected_result': None if result is None else result['api_key_candidates'][0]['id' if site == 'key_id' else 'label']}
    finally:
        fixture.doCleanups()

if __name__=='__main__':unittest.main()

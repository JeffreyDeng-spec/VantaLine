"""Local model configuration parity with private files and provider substitutes."""
import ast
from dataclasses import fields
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock,patch
from fastapi import HTTPException
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE=os.environ.get('VANTALINE_LOCAL_MODEL_CONFIG_BASELINE_SOURCE')
NAMES=('load_ai_local_config','ai_local_config_temp_path','save_ai_local_config')


def create(b):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==3
        b.update(Any=Any,Path=Path,json=json,os=os)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),b)
        return SimpleNamespace(**{n:b[n] for n in NAMES})
    from local_inspection_service.model_providers.local_model_config import LocalModelConfig
    from local_inspection_service.model_providers.local_model_config_ports import LocalModelConfigFiles,LocalJsonModelPolicy,LocalImageModelPolicy
    def ports(cls):return cls(**{f.name:lambda name=f.name:b[name] for f in fields(cls)})
    service=LocalModelConfig(ports(LocalModelConfigFiles),ports(LocalJsonModelPolicy),ports(LocalImageModelPolicy));b['ai_local_config_temp_path']=service.ai_local_config_temp_path;return service


class ConfigurationContract(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory(prefix='vantaline-model-config-contract-');self.addCleanup(tmp.cleanup);root=Path(tmp.name);events=[]
        defaults={'provider':'gemini','model':'default-json','base_url':'https://json.invalid','timeout_seconds':30,'proxy_url':'','auto_local_proxy':True,'api_key_env':'','api_key':'','api_keys':[],'active_key_id':'','image_provider':'image','image_model':'default-image','image_base_url':'https://image.invalid','image_timeout_seconds':40,'image_api_key_env':'','image_api_key':'','image_api_keys':[],'image_active_key_id':''}
        b=dict(ensure_dirs=lambda:events.append('ensure'),_business_files=SimpleNamespace(exists=lambda p:p.exists(),read_text=lambda p,**kw:p.read_text(**kw),write_text=lambda p,v,**kw:p.write_text(v,**kw)),AI_LOCAL_CONFIG_PATH=root/'model.json',DATA_DIR=root,DEFAULT_AI_CONFIG=defaults,HTTPException=HTTPException,
            AI_DEFAULT_PROVIDER='gemini',AI_SUPPORTED_PROVIDERS={'gemini','qwen'},AI_DEFAULT_TIMEOUT_SECONDS=30,
            default_ai_model=lambda p:p+'-json',default_ai_base_url=lambda p:'https://'+p+'.invalid',validate_ai_proxy_url=lambda v:str(v or ''),validate_ai_timeout=lambda v:int(v),normalize_ai_key_items=lambda c,p:c.get('api_keys',[]),ai_keys_for_provider=lambda items,p:[i for i in items if i.get('provider',p)==p],
            IMAGE_GENERATION_DEFAULT_PROVIDER='image',IMAGE_GENERATION_SUPPORTED_PROVIDERS={'image','other'},IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS=40,
            default_image_generation_model=lambda p:p+'-picture',default_image_generation_base_url=lambda p:'https://'+p+'.invalid',validate_ai_base_url=lambda v:str(v),validate_image_generation_timeout=lambda v:int(v),normalize_image_key_items=lambda c,p:c.get('image_api_keys',[]),image_keys_for_provider=lambda items,p:[i for i in items if i.get('provider',p)==p])
        return create(b),b,events

    def put(self,b,value):b['AI_LOCAL_CONFIG_PATH'].write_text(json.dumps(value),encoding='utf-8')

    def test_missing_file_returns_shallow_default_without_normalization(self):
        s,b,e=self.fixture();b['normalize_ai_key_items']=Mock(side_effect=AssertionError('not reached'));result=s.load_ai_local_config()
        self.assertEqual(result,b['DEFAULT_AI_CONFIG']);self.assertIsNot(result,b['DEFAULT_AI_CONFIG']);self.assertIs(result['api_keys'],b['DEFAULT_AI_CONFIG']['api_keys']);self.assertEqual(e,['ensure'])

    def test_malformed_and_non_mapping_fall_back_to_defaults(self):
        for body in ('{broken','[]','null','12','"text"'):
            with self.subTest(body=body):
                s,b,e=self.fixture();b['AI_LOCAL_CONFIG_PATH'].write_text(body);self.assertEqual(s.load_ai_local_config(),b['DEFAULT_AI_CONFIG'])
        s,b,e=self.fixture();self.put(b,{})
        b['_business_files'].read_text=Mock(side_effect=OSError('unreadable'));self.assertEqual(s.load_ai_local_config(),b['DEFAULT_AI_CONFIG'])

    def test_unknown_fields_ignored_and_secrets_cleared_only_when_normalized(self):
        s,b,e=self.fixture();self.put(b,{'extra':'ignore','api_key':'synthetic-value','image_api_key':'synthetic-image','api_key_env':' ENV ','image_api_key_env':' IMAGE '})
        result=s.load_ai_local_config();self.assertNotIn('extra',result);self.assertEqual((result['api_key'],result['image_api_key']),('',''));self.assertEqual((result['api_key_env'],result['image_api_key_env']),('ENV','IMAGE'))

    def test_legacy_and_unknown_provider_use_current_defaults(self):
        for provider in ('openai','openai_compatible','unsupported'):
            s,b,e=self.fixture();self.put(b,{'provider':provider,'model':'legacy','base_url':'https://legacy.invalid'});result=s.load_ai_local_config();self.assertEqual((result['provider'],result['model'],result['base_url']),('gemini','gemini-json','https://gemini.invalid'))

    def test_supported_provider_preserves_settings_and_gemini_openai_path_normalizes(self):
        s,b,e=self.fixture();self.put(b,{'provider':' QWEN ','model':' custom ','base_url':' https://custom.invalid '});result=s.load_ai_local_config();self.assertEqual((result['provider'],result['model'],result['base_url']),('qwen','custom','https://custom.invalid'))
        self.put(b,{'provider':'gemini','base_url':'https://gemini.invalid/openai/v1'});self.assertEqual(s.load_ai_local_config()['base_url'],'https://gemini.invalid')

    def test_validation_http_failures_use_existing_fallbacks(self):
        s,b,e=self.fixture();self.put(b,{'auto_local_proxy':'false','timeout_seconds':-1,'image_timeout_seconds':-1})
        for name in ('validate_ai_proxy_url','validate_ai_timeout','validate_ai_base_url','validate_image_generation_timeout'):b[name]=Mock(side_effect=HTTPException(400,'synthetic invalid'))
        result=s.load_ai_local_config();self.assertEqual((result['proxy_url'],result['timeout_seconds'],result['image_timeout_seconds']),('',30,40));self.assertTrue(result['auto_local_proxy']);self.assertEqual(result['image_base_url'],'https://image.invalid')

    def test_non_http_validator_failure_propagates(self):
        s,b,e=self.fixture();self.put(b,{});error=RuntimeError('validation failed');b['validate_ai_timeout']=Mock(side_effect=error)
        with self.assertRaises(RuntimeError) as caught:s.load_ai_local_config()
        self.assertIs(caught.exception,error)

    def test_active_key_fallback_filters_provider_and_keeps_valid_id(self):
        s,b,e=self.fixture();data={'api_keys':[{'id':'wrong','provider':'qwen'},{'id':'first','provider':'gemini'},{'id':'second','provider':'gemini'}],'active_key_id':'wrong','image_api_keys':[{'id':'i-first'},{'id':'i-second'}],'image_active_key_id':'i-second'};self.put(b,data)
        result=s.load_ai_local_config();self.assertEqual((result['active_key_id'],result['image_active_key_id']),('first','i-second'))
        data['active_key_id']=' second ';self.put(b,data);self.assertEqual(s.load_ai_local_config()['active_key_id'],'second')

    def test_image_provider_and_empty_fields_keep_original_fallback_order(self):
        s,b,e=self.fixture();self.put(b,{'image_provider':'unknown','image_model':'','image_base_url':''});r=s.load_ai_local_config();self.assertEqual((r['image_provider'],r['image_model'],r['image_base_url']),('image','image-picture','https://image.invalid'))

    def test_save_filters_unknowns_fills_defaults_and_uses_atomic_replace(self):
        s,b,e=self.fixture();s.save_ai_local_config({'model':'new','unknown':1});r=json.loads(b['AI_LOCAL_CONFIG_PATH'].read_text());self.assertEqual(r,{**b['DEFAULT_AI_CONFIG'],'model':'new'});self.assertFalse(s.ai_local_config_temp_path().exists())

    def test_replace_failure_keeps_original_and_pending_temp(self):
        s,b,e=self.fixture();self.put(b,{'old':1});error=OSError('replace failed')
        with patch.object(os,'replace',side_effect=error):
            with self.assertRaises(OSError) as caught:s.save_ai_local_config({'model':'new'})
        self.assertIs(caught.exception,error);self.assertEqual(json.loads(b['AI_LOCAL_CONFIG_PATH'].read_text()),{'old':1});self.assertTrue(s.ai_local_config_temp_path().exists())

    def test_chmod_oserror_is_best_effort_but_other_error_propagates(self):
        s,b,e=self.fixture()
        with patch.object(os,'chmod',side_effect=OSError('unsupported')) as chmod:s.save_ai_local_config({})
        self.assertEqual(chmod.call_count,2);self.assertTrue(b['AI_LOCAL_CONFIG_PATH'].exists())
        error=RuntimeError('non-os')
        with patch.object(os,'chmod',side_effect=error):
            with self.assertRaises(RuntimeError):s.save_ai_local_config({'model':'later'})
        self.assertEqual(json.loads(b['AI_LOCAL_CONFIG_PATH'].read_text())['model'],'default-json')

    @unittest.skipIf(bool(BASELINE),'new assembly only')
    def test_root_composition_all_getters_and_instances_are_independent(self):
        from application_integration_source_contract import restore_infrastructure_root
        s,a,ea=self.fixture();t,b,eb=self.fixture();tree=ast.parse(restore_infrastructure_root(read_checked_application_source(ROOT / 'local_inspection_service/server.py', encoding='utf-8')))
        nodes=[n for n in tree.body if (isinstance(n,ast.ImportFrom) and n.module in ('model_providers.local_model_config','model_providers.local_model_config_ports')) or (isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='_local_model_config' for x in n.targets)) or (isinstance(n,ast.FunctionDef) and n.name in NAMES)]
        self.assertEqual(len(nodes),6)
        from dataclasses import replace
        from typing import get_type_hints
        from local_inspection_service.model_providers.configuration_composition import ProviderConfiguration
        from local_inspection_service.model_providers.local_model_config_ports import LocalModelConfigFiles, LocalJsonModelPolicy, LocalImageModelPolicy
        from scripts.provider_configuration_test_ports import PROVIDER_METHODS
        forbidden=Mock(side_effect=AssertionError('unrelated configuration capability'))
        inputs={name:kind(**{field.name:forbidden for field in fields(kind)}) for name,kind in get_type_hints(ProviderConfiguration.__init__).items() if name!='return'}
        for name,kind in [('local_model_config_files',LocalModelConfigFiles),('local_json_model_policy',LocalJsonModelPolicy),('local_image_model_policy',LocalImageModelPolicy)]:
            inputs[name]=kind(**{field.name:lambda name=field.name:a[name] for field in fields(kind)})
        owner=ProviderConfiguration(**inputs)
        for name,value in a.items():
            if name in PROVIDER_METHODS and name!='ai_local_config_temp_path':setattr(owner,name,value)
        ns=dict(a,Any=Any,Path=Path,__package__='local_inspection_service',_provider_configuration=owner)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<assembly>','exec'),ns)
        self.assertIs(ns['_local_model_config'],owner.local)
        forbidden.assert_not_called()
        assembled=ns['_local_model_config']
        for group in (assembled.files,assembled.json_policy,assembled.image_policy):
            for f in fields(group):
                selected=getattr(group,f.name)()
                expected=getattr(owner,f.name) if f.name in PROVIDER_METHODS else ns[f.name]
                if hasattr(expected,'__self__'):
                    self.assertIs(selected.__self__,expected.__self__)
                    self.assertIs(selected.__func__,expected.__func__)
                else:self.assertIs(selected,expected)
        ns['save_ai_local_config']({'model':'A'});t.save_ai_local_config({'model':'B'});self.assertEqual(ns['load_ai_local_config']()['model'],'A');self.assertEqual(t.load_ai_local_config()['model'],'B');self.assertEqual(s.load_ai_local_config()['model'],'A')


if __name__=='__main__':unittest.main()

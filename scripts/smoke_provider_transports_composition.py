"""Exercise actual provider factories with synthetic transports and no network."""
import ast
import io
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields
from pathlib import Path
import sys
from threading import Barrier
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.model_providers.transport_composition import ProviderTransports, TransportInputs
from local_inspection_service.model_providers.openai_ports import OpenAITransportIO, OpenAITransportErrors
from local_inspection_service.model_providers.gemini_ports import GeminiTransportIO, GeminiTransportErrors
from local_inspection_service.model_providers.image_ports import ImageTransportIO, ImageTransportErrors
from local_inspection_service.model_providers import errors


class Contracts(unittest.TestCase):
    def fixture(self, name, ttl=900):
        calls=[]
        record=Mock()
        resolver=SimpleNamespace(record_call=record)
        responses=[]
        def send(request, settings, *, timeout):
            calls.append((name,json.loads(request.data),settings,timeout))
            return io.BytesIO(json.dumps(responses.pop(0)).encode())
        ports=dict(open=lambda:send, parse=lambda:json.loads,
                   text=lambda:lambda value,limit:str(value)[:limit],
                   digest=lambda:lambda value:'synthetic-digest',
                   http_error=lambda:lambda prefix,exc:errors.AiProviderError(prefix),
                   data_url=lambda:lambda value:('image/png','eA=='),
                   decode=lambda:lambda value:b'image:'+name.encode() if value else None,
                   mask_url=lambda:lambda value:'masked:'+name, quote=lambda:quote,
                   download=lambda:Mock(side_effect=AssertionError('unexpected download')))
        error_ports=dict(config=lambda:errors.AiProviderConfigError,
                         timeout=lambda:errors.AiProviderTimeout, error=lambda:errors.AiProviderError,
                         auth=lambda:errors.AiProviderAuthError, overloaded=lambda:errors.AiProviderOverloaded,
                         download_error=lambda:RuntimeError)
        def make(cls, values):return cls(**{f.name:values[f.name] for f in fields(cls)})
        state=SimpleNamespace(openai=make(OpenAITransportIO,ports),gemini=make(GeminiTransportIO,ports),
            image=make(ImageTransportIO,ports), size=name+'-size')
        inputs=TransportInputs(lambda:state.openai,lambda:make(OpenAITransportErrors,error_ports),
            lambda:state.gemini,lambda:make(GeminiTransportErrors,error_ports),
            lambda:state.image,lambda:make(ImageTransportErrors,error_ports),
            lambda:state.size,lambda:state.size,lambda:lambda payload:payload['data'])
        resolve=Mock(return_value=resolver)
        graph=ProviderTransports(inputs,resolve,cache_ttl_seconds=ttl)
        settings=dict(configured=True,model='synthetic',base_url='https://fixture.invalid',
            api_key='synthetic',timeout_seconds=10,profile_id='frozen-'+name)
        return SimpleNamespace(graph=graph,state=state,resolve=resolve,record=record,
            responses=responses,calls=calls,settings=settings)

    def test_construction_is_inert_and_types_are_owned(self):
        def poison(*args,**kwargs):raise AssertionError('eager provider dependency')
        inputs=TransportInputs(**{f.name:poison for f in fields(TransportInputs)})
        a=ProviderTransports(inputs,poison,cache_ttl_seconds=600)
        b=ProviderTransports(inputs,poison,cache_ttl_seconds=1200)
        for kind in ('openai','gemini','agnes','qwen'):
            self.assertIsNot(getattr(a,kind),getattr(b,kind))
        self.assertEqual(a.gemini.create_cached_content.__kwdefaults__['ttl_seconds'],600)
        self.assertEqual(b.gemini.create_cached_content.__kwdefaults__['ttl_seconds'],1200)

    def test_four_native_calls_are_isolated_and_accounted_once(self):
        for kind in ('openai','gemini','agnes','qwen'):
            with self.subTest(kind=kind):
                a,b=self.fixture('a'),self.fixture('b')
                for f in (a,b):
                    if kind=='openai':response={'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}]}
                    elif kind=='gemini':response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"ok":true}'}]}}]}
                    else:response={'data':[{'b64_json':'synthetic'}]}
                    f.responses.append(response)
                    provider=getattr(f.graph,kind)(f.settings)
                    if kind in ('openai','gemini'):
                        result,_=provider.generate_json('system',[])
                        self.assertTrue(result['ok'])
                    else:
                        result=provider.generate_image('prompt',[],model='synthetic')
                        self.assertEqual(result['bytes'],b'image:'+f.calls[0][0].encode())
                    f.resolve.assert_called_once_with()
                    f.record.assert_called_once()
                    self.assertIs(f.record.call_args.args[0],f.settings)
                    self.assertEqual(len(f.calls),1)
                    self.assertIs(f.calls[0][2],f.settings)
                self.assertEqual(a.calls[0][0],'a');self.assertEqual(b.calls[0][0],'b')

    def test_port_objects_selected_at_instance_creation_capabilities_stay_lazy(self):
        f=self.fixture('a');old=f.state.openai
        p=f.graph.openai(f.settings)
        other=self.fixture('b')
        f.state.openai=other.state.openai
        q=f.graph.openai(f.settings)
        self.assertIs(p.io,old);self.assertIs(q.io,other.state.openai)
        for kind in ('agnes','qwen'):
            p=getattr(f.graph,kind)(f.settings)
            f.state.size='changed-after-provider-construction'
            f.responses.append({'data':[{'b64_json':'synthetic'}]})
            p.generate_image('prompt',[],model='synthetic')
            payload=f.calls[-1][1]
            self.assertEqual(payload['size'] if kind=='agnes' else payload['parameters']['size'],f.state.size)

    def test_resolver_callable_is_captured_without_capturing_service(self):
        f=self.fixture('a');provider=f.graph.openai(f.settings)
        original=provider.resolve
        other=Mock(return_value=SimpleNamespace(record_call=Mock()))
        f.graph.openai_resolver=other
        self.assertIs(provider.resolve,original)
        self.assertIs(f.graph.openai(f.settings).resolve,other)
        new_record=Mock();f.resolve.return_value=SimpleNamespace(record_call=new_record)
        f.responses.append({'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]})
        provider.generate_json('system',[])
        f.record.assert_not_called();new_record.assert_called_once();other.assert_not_called()

    def test_missing_resolver_fails_before_all_four_transports(self):
        for kind in ('openai','gemini','agnes','qwen'):
            with self.subTest(kind=kind):
                f=self.fixture('a');f.resolve.return_value=None
                p=getattr(f.graph,kind)(f.settings)
                with self.assertRaisesRegex(RuntimeError,'Model profile resolver is not configured'):
                    if kind in ('openai','gemini'):p.generate_json('system',[])
                    else:p.generate_image('prompt',[],model='synthetic')
                self.assertEqual(f.calls,[]);f.record.assert_not_called()

    def test_cache_ttl_default_is_app_local_and_override_preserved(self):
        for name,ttl in (('a',600),('b',1800)):
            f=self.fixture(name,ttl);p=f.graph.gemini(f.settings)
            for override,expected in (({},ttl),({'ttl_seconds':120},300)):
                f.responses.append({'name':'cachedContents/synthetic'})
                p.create_cached_content('system',[],display_name='fixture',**override)
                self.assertEqual(f.calls[-1][1]['ttl'],str(expected)+'s')
            f.resolve.assert_not_called();f.record.assert_not_called()

    def test_concurrent_same_provider_kind_uses_separate_transport_and_ledger(self):
        a,b=self.fixture('a'),self.fixture('b');barrier=Barrier(2)
        def run(f):
            f.responses.append({'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]})
            p=f.graph.openai(f.settings);barrier.wait(timeout=5)
            return p.generate_json('system',[])
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(run,f) for f in (a,b)]
            for future in futures:self.assertEqual(future.result(timeout=10)[0],{})
        for f in (a,b):f.record.assert_called_once();self.assertEqual(len(f.calls),1)

    def test_default_classes_and_unchanged_entry_functions(self):
        import application_integration_source_contract as contract
        source=(contract.ROOT/'local_inspection_service/server.py').read_text()
        actual=ast.parse(contract.restore_real_photo_workflows_root(source))
        self.assertEqual(contract.digest(actual),contract.PROVIDER_TRANSPORTS['integrated_ast_sha256'])
        parent=ast.parse(contract.restore_provider_transports_root(source))
        functions=lambda tree:[contract.canonical(n) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
        self.assertEqual(functions(actual),functions(parent));self.assertEqual(len(functions(actual)),983)
        from verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        for alias,kind in (('OpenAICompatibleAiProvider','openai'),('GeminiAiProvider','gemini'),
                           ('AgnesImageProvider','agnes'),('QwenImageProvider','qwen')):
            self.assertIs(getattr(server,alias),getattr(server._provider_transports,kind))

    def test_each_type_selects_its_own_resolver_errors_io_and_size(self):
        f=self.fixture('a')
        from dataclasses import replace
        distinct_errors={}
        for name,cls in (('openai',OpenAITransportErrors),('gemini',GeminiTransportErrors),('image',ImageTransportErrors)):
            config_type=type(name+'ConfigError',(errors.AiProviderConfigError,),{})
            original=getattr(f.graph.inputs,name+'_errors')()
            distinct_errors[name]=replace(original,config=lambda value=config_type:value)
        f.graph.inputs=replace(f.graph.inputs,
            openai_errors=lambda:distinct_errors['openai'],gemini_errors=lambda:distinct_errors['gemini'],
            image_errors=lambda:distinct_errors['image'],
            agnes_image_size=lambda:'agnes-size',qwen_image_size=lambda:'qwen-size')
        distinct_resolvers={kind:Mock(return_value=SimpleNamespace(record_call=Mock()))
                            for kind in ('openai','gemini','agnes','qwen')}
        for kind,resolve in distinct_resolvers.items():setattr(f.graph,kind+'_resolver',resolve)
        for kind,group in (('openai','openai'),('gemini','gemini'),('agnes','image'),('qwen','image')):
            with self.subTest(kind=kind):
                p=getattr(f.graph,kind)(f.settings)
                self.assertIs(p.resolve,distinct_resolvers[kind])
                self.assertIs(p.io,getattr(f.state,group))
                self.assertIs(p.errors,distinct_errors[group])
                unbound=getattr(f.graph,kind)({'configured':False})
                with self.assertRaises(distinct_errors[group].config()):
                    if kind in ('openai','gemini'):unbound.generate_json('system',[])
                    else:unbound.generate_image('prompt',[],model='synthetic')
                if kind in ('agnes','qwen'):
                    f.responses.append({'data':[{'b64_json':'synthetic'}]})
                    p.generate_image('prompt',[],model='synthetic')
                    payload=f.calls[-1][1]
                    self.assertEqual(payload['size'] if kind=='agnes' else payload['parameters']['size'],kind+'-size')


if __name__=='__main__':unittest.main()

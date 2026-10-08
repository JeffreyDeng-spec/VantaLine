"""Model tool projection and transport contracts without external inference."""
from contextlib import nullcontext
import ast
from dataclasses import fields
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_MODEL_TOOL_DISPATCH_BASELINE_SOURCE')
NAMES=('provider_generate_json_error_payload','tool_provider_gemini_generate_json','call_ai_mcp_tool')
class ProviderError(Exception):pass
class ProviderTimeout(ProviderError):pass
class ProviderOverloaded(ProviderError):pass


def create(b):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==3
        b.update(Any=Any,time=time);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),b);return SimpleNamespace(**{n:b[n] for n in NAMES})
    from local_inspection_service.model_providers.tool_dispatch import ModelToolDispatch
    from local_inspection_service.model_providers.tool_dispatch_ports import ToolErrorPolicy,JsonToolExecution,McpToolTransport
    def ports(cls):return cls(**{f.name:lambda name=f.name:b[name] for f in fields(cls)})
    service=ModelToolDispatch(ports(ToolErrorPolicy),ports(JsonToolExecution),ports(McpToolTransport));b.update({n:getattr(service,n) for n in NAMES});return service


class ToolContract(unittest.TestCase):
    def fixture(self):
        calls=[]
        b=dict(bounded_text=lambda v,n:str(v)[:n],_text_v2_diagnostic_value=lambda v:'redacted:'+v[:8],AiProviderError=ProviderError,AiProviderTimeout=ProviderTimeout,AiProviderOverloaded=ProviderOverloaded,AI_DEFAULT_TIMEOUT_SECONDS=30,
            ai_detection_settings=lambda:{'configured':True,'timeout_seconds':3},ai_tool_provider_meta=lambda s:{'provider':'synthetic'},generate_provider_json_with_fallback=Mock(return_value=({'ok':1},7,{'attempts':1})),
            admission=nullcontext,ai_mcp_runtime=lambda:'in_process',AI_MCP_RUNTIME_STDIO='stdio',AI_MCP_RUNTIME_IN_PROCESS='in_process',_ai_mcp_client=SimpleNamespace(admission=nullcontext,call_tool=Mock(return_value={'answer':1}),close=Mock()),prepare_ai_mcp_payload=lambda n,p:{**p,'prepared':True},AI_MCP_TOOL_HANDLERS={'known':lambda p:calls.append(p) or {'answer':2}})
        return create(b),b,calls

    def test_not_configured_does_not_invoke_provider(self):
        s,b,e=self.fixture();r=s.tool_provider_gemini_generate_json({'provider_config':{'message':'missing'}});self.assertFalse(r['ok']);self.assertEqual(r['error_type'],'not_configured');self.assertEqual(r['error'],'missing');b['generate_provider_json_with_fallback'].assert_not_called()

    def test_success_defaults_and_explicit_normalization(self):
        s,b,e=self.fixture();r=s.tool_provider_gemini_generate_json({'max_attempts':0,'max_tokens':'42','system_prompt':123,'user_content':'bad','cached_content':456})
        args,kw=b['generate_provider_json_with_fallback'].call_args;self.assertEqual(args[1:],('123',[]));self.assertEqual(kw,{'max_tokens':42,'cached_content':'456','max_attempts':1});self.assertTrue(r['ok']);self.assertEqual(r['parsed'],{'ok':1});self.assertEqual(r['meta'],{'provider':'synthetic','attempts':1})
        s.tool_provider_gemini_generate_json({'max_attempts':'bad'});self.assertEqual(b['generate_provider_json_with_fallback'].call_args.kwargs['max_attempts'],None)

    def test_provider_configuration_copy_and_empty_fallback(self):
        s,b,e=self.fixture();settings={'configured':True};s.tool_provider_gemini_generate_json({'provider_config':settings});actual=b['generate_provider_json_with_fallback'].call_args.args[0];self.assertEqual(actual,settings);self.assertIsNot(actual,settings)
        b['ai_detection_settings']=Mock(return_value={'configured':True,'fallback':1});s.tool_provider_gemini_generate_json({'provider_config':{}});b['ai_detection_settings'].assert_called_once()

    def test_timeout_overload_and_generic_failures_do_not_resubmit(self):
        for exc,timeout,overload in ((ProviderTimeout('slow'),True,False),(ProviderOverloaded('busy'),False,True),(ProviderError('failed'),False,False),(RuntimeError('unexpected'),False,False)):
            with self.subTest(exc=type(exc).__name__):
                s,b,e=self.fixture();b['generate_provider_json_with_fallback'].side_effect=exc;r=s.tool_provider_gemini_generate_json({});self.assertEqual((r['timed_out'],r['overloaded']),(timeout,overload));self.assertFalse(r['ok']);self.assertEqual(r['latency_ms'],3000 if timeout else 0);self.assertEqual(b['generate_provider_json_with_fallback'].call_count,1)

    def test_conversion_boundaries_preserve_propagation(self):
        s,b,e=self.fixture()
        with self.assertRaises(OverflowError):s.tool_provider_gemini_generate_json({'max_attempts':float('inf')})
        r=s.tool_provider_gemini_generate_json({'max_tokens':'bad'});self.assertEqual(r['error_type'],'ValueError');b['generate_provider_json_with_fallback'].assert_not_called()
        b['ai_tool_provider_meta']=Mock(side_effect=RuntimeError('pre-call'))
        with self.assertRaisesRegex(RuntimeError,'pre-call'):s.tool_provider_gemini_generate_json({})

    def test_error_metadata_bounding_selection_and_reference_identity(self):
        s,b,e=self.fixture();error=ProviderError('x'*300);usage={'tokens':2};failed=[{'tokens':1}];error.usage_metadata=usage;error.failed_usage_metadata=failed;error.attempts=2;error.retry_count=1;error.previous_errors=['old','middle','new'];error.http_status=503;error.fallback_model='model';error.fallback_reason='reason';error.response_sha256='hash';error.response_preview='sensitive-preview'
        r=s.provider_generate_json_error_payload({}, {'provider':'synthetic'},error);self.assertEqual(len(r['error']),240);self.assertIs(r['usage_metadata'],usage);self.assertIs(r['failed_usage_metadata'],failed);self.assertEqual(r['previous_errors'],['middle','new']);self.assertEqual(r['response_preview'],'redacted:sensitiv');self.assertEqual(r['meta']['attempts'],2)

    def test_metadata_expansion_precedence_stays_original(self):
        s,b,e=self.fixture();r=s.provider_generate_json_error_payload({}, {'ok':'legacy','error_type':'from-meta','overloaded':'meta'},ProviderError('failed'),overloaded=True)
        self.assertEqual(r['ok'],'legacy');self.assertEqual(r['error_type'],'from-meta');self.assertEqual(r['overloaded'],'meta');self.assertEqual(r['meta']['error_type'],'ProviderError');self.assertIs(r['meta']['overloaded'],True)
        b['generate_provider_json_with_fallback'].return_value=({},0,{'ok':'provider-value','provider':'override'});r=s.tool_provider_gemini_generate_json({});self.assertEqual(r['ok'],'provider-value');self.assertEqual(r['meta']['provider'],'override')

    def test_stdio_success_preserves_existing_transport_metadata(self):
        s,b,e=self.fixture();b['ai_mcp_runtime']=lambda:'stdio';r0={'tool':'custom','mcp_transport':'custom','mcp_runtime':'custom','mcp_dispatch_ms':99};b['_ai_mcp_client'].call_tool.return_value=r0
        with patch.object(time,'monotonic',side_effect=[1,1.05]):r=s.call_ai_mcp_tool('known',{'x':1})
        self.assertIs(r,r0);self.assertEqual(r['mcp_dispatch_ms'],99);self.assertEqual(e,[]);b['_ai_mcp_client'].call_tool.assert_called_once_with('known',{'x':1,'prepared':True});b['_ai_mcp_client'].close.assert_not_called()

    def test_stdio_failure_keeps_existing_single_inprocess_fallback(self):
        s,b,e=self.fixture();b['ai_mcp_runtime']=lambda:'stdio';b['_ai_mcp_client'].call_tool.side_effect=RuntimeError('x'*220)
        r=s.call_ai_mcp_tool('known',{'x':1});self.assertEqual(e,[{'x':1}]);self.assertEqual((r['mcp_transport'],r['mcp_fallback_from']),('in_process','stdio'));self.assertEqual(len(r['mcp_fallback_error']),180);b['_ai_mcp_client'].close.assert_called_once();b['_ai_mcp_client'].call_tool.assert_called_once()

    def test_client_close_failure_prevents_local_fallback(self):
        s,b,e=self.fixture();b['ai_mcp_runtime']=lambda:'stdio';b['_ai_mcp_client'].call_tool.side_effect=ValueError('transport');error=RuntimeError('close');b['_ai_mcp_client'].close.side_effect=error
        with self.assertRaises(RuntimeError) as caught:s.call_ai_mcp_tool('known',{})
        self.assertIs(caught.exception,error);self.assertEqual(e,[])

    def test_unknown_and_nonobject_handlers_raise_and_bad_payload_becomes_empty(self):
        s,b,e=self.fixture()
        with self.assertRaisesRegex(ProviderError,'Unknown AI MCP tool'):s.call_ai_mcp_tool('unknown',{})
        s.call_ai_mcp_tool('known',[]);self.assertEqual(e,[{}]);b['AI_MCP_TOOL_HANDLERS']['bad']=lambda p:[]
        with self.assertRaisesRegex(ProviderError,'non-object result'):s.call_ai_mcp_tool('bad',{})

    def test_late_handler_binding_after_transport_close_and_selected_client(self):
        s,b,e=self.fixture();b['ai_mcp_runtime']=lambda:'stdio';old=b['_ai_mcp_client'];old.call_tool.side_effect=RuntimeError('transport');new=SimpleNamespace(call_tool=Mock(),close=Mock(side_effect=lambda:b['AI_MCP_TOOL_HANDLERS'].update(known=lambda p:{'new':True})))
        def prepare(name,p):b['_ai_mcp_client']=new;return p
        b['prepare_ai_mcp_payload']=prepare;r=s.call_ai_mcp_tool('known',{});self.assertTrue(r['new']);old.call_tool.assert_called_once();old.close.assert_not_called();new.close.assert_called_once();new.call_tool.assert_not_called()

    @unittest.skipIf(bool(BASELINE),'new assembly only')
    def test_root_composition_and_all_getters_independent(self):
        s,a,ea=self.fixture();t,b,eb=self.fixture();tree=ast.parse((ROOT/'local_inspection_service/server.py').read_text(encoding='utf-8'))
        nodes=[n for n in tree.body if (isinstance(n,ast.ImportFrom) and n.module in ('model_providers.tool_dispatch','model_providers.tool_dispatch_ports')) or (isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='_model_tool_dispatch' for x in n.targets)) or (isinstance(n,ast.FunctionDef) and n.name in NAMES)]
        self.assertEqual(len(nodes),6);ns=dict(a,Any=Any,__package__='local_inspection_service');exec(compile(ast.Module(body=nodes,type_ignores=[]),'<assembly>','exec'),ns);assembled=ns['_model_tool_dispatch']
        for group in (assembled.errors,assembled.execution,assembled.transport):
            for f in fields(group):self.assertIs(getattr(group,f.name)(),ns[f.name])
        ns['call_ai_mcp_tool']('known',{'a':1});t.call_ai_mcp_tool('known',{'b':2});s.call_ai_mcp_tool('known',{'a':3});self.assertEqual(ea,[{'a':1},{'a':3}]);self.assertEqual(eb,[{'b':2}])


if __name__=='__main__':unittest.main()

"""Synthetic model tool ownership and admission contracts; no model or PLC I/O."""
from dataclasses import fields
import ast
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.model_providers.tool_composition import (
    ModelTools, JsonProviderCalls, McpRuntimeSelection, AccessoryTools, PresencePreparation,
)
from local_inspection_service.model_providers.tool_dispatch_ports import ToolErrorPolicy
from local_inspection_service.model_providers.mcp_client import McpAdmissionClosed
from local_inspection_service.detection.presence_inspection_ports import PresenceInput, PresenceOutput, PresencePolicy
from smoke_presence_inspection import PresenceFixture
from smoke_model_tool_dispatch import ProviderError, ProviderTimeout, ProviderOverloaded


def owner(f, generate):
    return ModelTools(
        errors=ToolErrorPolicy(lambda: lambda v,n: str(v)[:n], lambda: lambda v:v,
                               lambda:ProviderError, lambda:ProviderTimeout,
                               lambda:ProviderOverloaded, lambda:30),
        provider=JsonProviderCalls(lambda:f.settings_call, lambda:lambda s:{'provider':'synthetic'}, lambda:generate),
        runtime=McpRuntimeSelection(lambda:Path('.'), lambda:lambda:'in_process', lambda:'stdio',
                                    lambda:'in_process', lambda:lambda n,p:p),
        accessories=AccessoryTools(lambda p:{'owner':id(f)}, lambda p:{'owner':id(f)}),
        presence_input=PresenceInput(f.settings_call, lambda:f.resolve, lambda:f.path, lambda:f.bgr),
        presence=PresencePreparation(f.task_call, f.cache_call, lambda:f.tokens, lambda:f.covers),
        presence_output=PresenceOutput(lambda:f.fail, lambda:f.normalize),
        policy=PresencePolicy(lambda:800, lambda:81, lambda:3, lambda:2, lambda:'original test prompt', lambda:f.schema),
        clock=f.clock,
    )


def verify_internal_edges(tree):
    calls={n.func.id:n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ['PresenceGeneration','JsonToolExecution','McpToolTransport']}
    expected={('PresenceGeneration','call'):'lambda: self.call_ai_mcp_tool',('JsonToolExecution','provider_generate_json_error_payload'):'lambda: self.dispatch.provider_generate_json_error_payload',('McpToolTransport','admission'):'lambda: self.client.admission',('McpToolTransport','_ai_mcp_client'):'lambda: self.client',('McpToolTransport','AI_MCP_TOOL_HANDLERS'):'lambda: self.handlers'}
    for (name,key),expression in expected.items():
        value=next(k.value for k in calls[name].keywords if k.arg==key)
        assert ast.dump(value)==ast.dump(ast.parse(expression,mode='eval').body),(name,key)
    assignment=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Attribute) and isinstance(t.value,ast.Name) and t.value.id=='self' and t.attr=='handlers' for t in n.targets))
    expected_handlers=ast.parse('{"accessory.profile.generate": accessories.profile, "accessory.reference.collect": accessories.reference, "vision.inspect.presence": self.presence.tool_vision_inspect_presence, "provider.gemini.generate_json": self._generate_json}',mode='eval').body
    assert ast.dump(assignment.value)==ast.dump(expected_handlers)


class Contracts(unittest.TestCase):
    def test_exact_internal_edges_and_mutation_rejection(self):
        p=Path(__file__).resolve().parents[1]/'local_inspection_service/model_providers/tool_composition.py'
        source=p.read_text();verify_internal_edges(ast.parse(source))
        mutants=[('lambda: self.client.admission','lambda: self.dispatch.call_ai_mcp_tool'),('lambda: self.handlers','lambda: accessories.handlers'),('lambda: self.dispatch.provider_generate_json_error_payload','lambda: self.dispatch.tool_provider_gemini_generate_json'),('self.presence.tool_vision_inspect_presence','accessories.tool_vision_inspect_presence'),('"provider.gemini.generate_json": self._generate_json','"provider.gemini.generate_json": accessories.profile')]
        for old,new in mutants:
            self.assertEqual(source.count(old),1)
            with self.assertRaises(AssertionError):verify_internal_edges(ast.parse(source.replace(old,new)))

    def test_parent_root_contract_rejects_wrong_owner_and_supplier(self):
        from smoke_model_tool_dispatch import ToolContract
        p=Path(__file__).resolve().parents[1]/'local_inspection_service/server.py';source=p.read_text();original=Path.read_text
        for old,new in [('_model_tool_dispatch = _model_tools.dispatch','_model_tool_dispatch = _model_tools.presence'),('stdio=lambda: AI_MCP_RUNTIME_STDIO','stdio=lambda: AI_MCP_RUNTIME_IN_PROCESS'),('profile=tool_accessory_profile_generate','profile=tool_accessory_reference_collect')]:
            self.assertEqual(source.count(old),1);mutant=source.replace(old,new)
            def read(path,*a,**k):return mutant if path==p else original(path,*a,**k)
            with patch.object(Path,'read_text',read),self.assertRaises(AssertionError):ToolContract('test_root_composition_and_all_getters_independent').test_root_composition_and_all_getters_independent()

    def test_constructor_is_inert_and_internal_edges_owned(self):
        def poison(*a,**k):raise AssertionError('construction accessed external supplier')
        def ports(cls):return cls(**{f.name:poison for f in fields(cls)})
        with patch('subprocess.Popen',side_effect=poison):
            a=ModelTools(errors=ports(ToolErrorPolicy),provider=ports(JsonProviderCalls),runtime=ports(McpRuntimeSelection),
                         accessories=ports(AccessoryTools),presence_input=ports(PresenceInput),presence=ports(PresencePreparation),
                         presence_output=ports(PresenceOutput),policy=ports(PresencePolicy),clock=poison)
        self.assertEqual(a.presence.generation.call(),a.call_ai_mcp_tool)
        self.assertEqual(a.dispatch.transport.admission(),a.client.admission)
        self.assertIs(a.dispatch.transport._ai_mcp_client(),a.client)
        self.assertIs(a.dispatch.transport.AI_MCP_TOOL_HANDLERS(),a.handlers)
        self.assertEqual(a.dispatch.execution.provider_generate_json_error_payload(),a.dispatch.provider_generate_json_error_payload)

    def test_actual_presence_to_provider_graph_and_one_closed_owner(self):
        f,g=PresenceFixture(),PresenceFixture()
        pa=Mock(side_effect=lambda *a,**k:f.events.append('provider') or (f.parsed,31,{}))
        pb=Mock(return_value=(g.parsed,31,{}))
        a,b=owner(f,pa),owner(g,pb)
        self.assertIs(a.dispatch.call_ai_mcp_tool('vision.inspect.presence',f.payload()),f.result)
        self.assertEqual(pa.call_count,1);pb.assert_not_called()
        self.assertEqual(f.events,['clock','clock','clock','task','cache','clock','clock','tokens','provider','clock','normalize'])
        self.assertTrue(a.client.shutdown(1))
        with self.assertRaises(McpAdmissionClosed):a.dispatch.call_ai_mcp_tool('vision.inspect.presence',f.payload())
        self.assertEqual(pa.call_count,1)
        self.assertIs(b.dispatch.call_ai_mcp_tool('vision.inspect.presence',g.payload()),g.result)
        self.assertEqual(pb.call_count,1);self.assertIsNot(a.handlers,b.handlers);self.assertIsNot(a.client.lock,b.client.lock)

    def test_native_inflight_drain_does_not_close_other_graph_or_retry(self):
        entered,release=threading.Event(),threading.Event();f,g=PresenceFixture(),PresenceFixture()
        def provider(*args,**kwargs):entered.set();self.assertTrue(release.wait(3));return f.parsed,31,{}
        pa=Mock(side_effect=provider);pb=Mock(return_value=(g.parsed,31,{}));a,b=owner(f,pa),owner(g,pb);errors=[]
        def run():
            try:a.dispatch.call_ai_mcp_tool('vision.inspect.presence',f.payload())
            except BaseException as e:errors.append(e)
        t=threading.Thread(target=run);t.start()
        try:
            self.assertTrue(entered.wait(2));self.assertFalse(a.client.shutdown(0))
            with self.assertRaises(McpAdmissionClosed):a.dispatch.call_ai_mcp_tool('provider.gemini.generate_json',{})
            b.dispatch.call_ai_mcp_tool('vision.inspect.presence',g.payload());self.assertEqual(pb.call_count,1)
        finally:release.set();t.join(3)
        self.assertFalse(t.is_alive());self.assertEqual(errors,[]);self.assertEqual(pa.call_count,1);self.assertTrue(a.client.shutdown(1))

    def test_owned_call_wrapper_selects_dispatch_after_argument_effects(self):
        f=PresenceFixture();provider=Mock(return_value=(f.parsed,31,{}));a=owner(f,provider)
        selected=Mock(return_value=f.response)
        def tokens(*args):
            a.dispatch=SimpleNamespace(call_ai_mcp_tool=selected)
            return 128
        f.tokens.side_effect=tokens
        original=a.dispatch
        result=original.call_ai_mcp_tool('vision.inspect.presence',f.payload())
        self.assertIs(result,f.result);selected.assert_called_once();provider.assert_not_called()
        self.assertEqual(selected.call_args.args[0],'provider.gemini.generate_json')

    def test_actual_owned_error_projection_no_extra_provider_attempt(self):
        f=PresenceFixture();provider=Mock(side_effect=ProviderTimeout('synthetic timeout'));a=owner(f,provider)
        result=a.dispatch.call_ai_mcp_tool('provider.gemini.generate_json',{})
        self.assertFalse(result['ok']);self.assertTrue(result['timed_out']);self.assertEqual(provider.call_count,1)


if __name__=='__main__':unittest.main()

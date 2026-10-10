"""MCP environment, payload ordering and failed warmup contracts with no providers."""
from contextlib import nullcontext
import ast
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from local_inspection_service.model_providers import mcp_runtime as runtime
BASELINE=os.environ.get('VANTALINE_MCP_POLICY_BASELINE_SOURCE')
NAMES={'ai_mcp_runtime','external_ai_mcp_enabled','prepare_ai_mcp_payload','warm_ai_mcp_client'}
CONSTANTS=('AI_MCP_RUNTIME_ENV','AI_MCP_LEGACY_ENABLED_ENV','AI_MCP_RUNTIME_IN_PROCESS','AI_MCP_RUNTIME_STDIO')


def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
        assert len(nodes)==4
        ns=dict(bindings,Any=Any,os=os,np=np,**{n:getattr(runtime,n) for n in CONSTANTS})
        exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns)
        return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
    payload=runtime.McpPayloadPreparation(encoder=lambda:bindings['image_bgr_data_url'],max_side=lambda:bindings['AI_INSPECTION_IMAGE_MAX_SIDE'],quality=lambda:bindings['AI_INSPECTION_IMAGE_QUALITY'])
    warmup=runtime.McpWarmup(admission=nullcontext,enabled=lambda:bindings['external_ai_mcp_enabled'](),client=lambda:bindings['_ai_mcp_client'])
    bindings['external_ai_mcp_enabled']=runtime.external_ai_mcp_enabled
    return SimpleNamespace(ai_mcp_runtime=runtime.ai_mcp_runtime, external_ai_mcp_enabled=runtime.external_ai_mcp_enabled,prepare_ai_mcp_payload=payload.prepare_ai_mcp_payload,warm_ai_mcp_client=warmup.warm_ai_mcp_client),bindings


class Contracts(unittest.TestCase):
    def setUp(self):
        self.client=SimpleNamespace(ensure_started=Mock(),close=Mock())
        self.encoder=Mock(return_value='fixture-data')
        self.s,self.b=create(dict(_ai_mcp_client=self.client,image_bgr_data_url=self.encoder,AI_INSPECTION_IMAGE_MAX_SIDE=640,AI_INSPECTION_IMAGE_QUALITY=75))

    def test_mode_precedence_aliases_and_live_environment(self):
        for server in ('','0','1'):
            for mode in ('','STDIO','external','subprocess','mcp','in-process','inprocess','local','direct',' invalid '):
                for legacy in (None,'','0','true','stdio','yes'):
                    env={'INSPECTION_AI_MCP_SERVER_MODE':server,'INSPECTION_AI_MCP_RUNTIME':mode}
                    if legacy is not None:env['INSPECTION_AI_MCP_ENABLED']=legacy
                    normalized=mode.strip().lower().replace('-','_')
                    expected='in_process' if server or normalized in ('','in_process','inprocess','local','direct') else ('stdio' if normalized in ('stdio','external','subprocess','mcp') or legacy in ('true','stdio','yes') else 'in_process')
                    with self.subTest(server=server,mode=mode,legacy=legacy),patch.dict(os.environ,env,clear=True):
                        self.assertEqual(self.s.ai_mcp_runtime(),expected)
                        self.assertEqual(self.s.external_ai_mcp_enabled(),expected=='stdio')

    def test_path_priority_and_shallow_copy(self):
        array=np.zeros((2,3,3),dtype=np.uint8);nested=[]
        source={'inspection_image_path':'fixture.jpg','inspection_image_bgr':array,'nested':nested}
        result=self.s.prepare_ai_mcp_payload('vision.inspect.presence',source)
        self.assertIsNot(source,result);self.assertIs(result['nested'],nested);self.assertNotIn('inspection_image_bgr',result);self.assertIs(source['inspection_image_bgr'],array);self.encoder.assert_not_called()
        result=self.s.prepare_ai_mcp_payload('other',source);self.assertIs(result['inspection_image_bgr'],array);self.encoder.assert_not_called()

    def test_array_encoding_and_empty_path(self):
        array=np.zeros((1,1,3));source={'inspection_image_path':'','inspection_image_bgr':array}
        result=self.s.prepare_ai_mcp_payload('vision.inspect.presence',source)
        self.encoder.assert_called_once_with(array,max_side=640,quality=75)
        self.assertEqual(result['inspection_image_data_url'],'fixture-data');self.assertNotIn('inspection_image_bgr',result);self.assertIn('inspection_image_bgr',source)
        source={'inspection_image_bgr':[[1,2]]};self.assertEqual(self.s.prepare_ai_mcp_payload('vision.inspect.presence',source),source)

    def test_encoder_failure_does_not_mutate_input_and_bad_copy(self):
        error=ValueError('encode');self.encoder.side_effect=error;source={'inspection_image_bgr':np.zeros((1,1,3))}
        with self.assertRaises(ValueError) as caught:self.s.prepare_ai_mcp_payload('vision.inspect.presence',source)
        self.assertIs(caught.exception,error);self.assertIn('inspection_image_bgr',source)
        with self.assertRaises(TypeError):self.s.prepare_ai_mcp_payload('other',None)

    def test_disabled_and_successful_warmup(self):
        self.b['external_ai_mcp_enabled']=lambda:False;self.s.warm_ai_mcp_client();self.client.ensure_started.assert_not_called();self.client.close.assert_not_called()
        self.b['external_ai_mcp_enabled']=lambda:True;self.s.warm_ai_mcp_client();self.client.ensure_started.assert_called_once();self.client.close.assert_not_called()

    def test_failure_reselects_current_client_for_close(self):
        replacement=SimpleNamespace(ensure_started=Mock(),close=Mock())
        def fail():
            self.b['_ai_mcp_client']=replacement
            raise RuntimeError('start')
        self.b['external_ai_mcp_enabled']=lambda:True;self.client.ensure_started.side_effect=fail
        self.s.warm_ai_mcp_client();self.client.close.assert_not_called();replacement.close.assert_called_once();replacement.ensure_started.assert_not_called()

    def test_enabled_and_close_errors_propagate_and_baseexception_escapes(self):
        enabled_error=ValueError('enabled');self.b['external_ai_mcp_enabled']=Mock(side_effect=enabled_error)
        with self.assertRaises(ValueError) as caught:self.s.warm_ai_mcp_client()
        self.assertIs(caught.exception,enabled_error);self.client.ensure_started.assert_not_called();self.client.close.assert_not_called()
        self.b['external_ai_mcp_enabled']=lambda:True;self.client.ensure_started.side_effect=RuntimeError('start');close_error=LookupError('close');self.client.close.side_effect=close_error
        with self.assertRaises(LookupError) as caught:self.s.warm_ai_mcp_client()
        self.assertIs(caught.exception,close_error)
        self.client.close.reset_mock();self.client.ensure_started.side_effect=KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.s.warm_ai_mcp_client()
        self.client.close.assert_not_called()

    @unittest.skipIf(bool(BASELINE),'explicit port operation order')
    def test_encoder_selected_before_argument_suppliers_and_constructor_no_io(self):
        events=[]
        selected=lambda *args,**kw:events.append('encoded') or 'old'
        bindings={'encoder':selected}
        def encoder():events.append('encoder');return bindings['encoder']
        def size():events.append('size');bindings['encoder']=Mock(side_effect=AssertionError('new'));return 640
        def quality():events.append('quality');return 75
        obj=runtime.McpPayloadPreparation(encoder,size,quality)
        self.assertEqual(events,[])
        self.assertEqual(obj.prepare_ai_mcp_payload('vision.inspect.presence',{'inspection_image_bgr':np.zeros((1,1,3))})['inspection_image_data_url'],'old')
        self.assertEqual(events,['encoder','size','quality','encoded'])
        calls=Mock(side_effect=AssertionError('constructor'));runtime.McpWarmup(calls,calls,calls);calls.assert_not_called()

    @unittest.skipIf(bool(BASELINE),'candidate assembly only')
    def test_actual_root_aliases_and_unchanged_startup(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        self.assertIs(server.ai_mcp_runtime,runtime.ai_mcp_runtime)
        self.assertIs(server.external_ai_mcp_enabled,runtime.external_ai_mcp_enabled)
        self.assertIs(server.prepare_ai_mcp_payload.__self__,server._mcp_payload_preparation)
        self.assertIs(server.warm_ai_mcp_client.__self__,server._mcp_warmup)
        self.assertIs(server._mcp_warmup.client(),server._ai_mcp_client)
        self.assertIs(server._mcp_warmup.enabled,runtime.external_ai_mcp_enabled)
        from inspect import unwrap
        hooks = [hook for hook in server.app.router.on_startup
                 if hook.__name__ == 'start_ai_mcp_warmup']
        self.assertEqual(len(hooks), 1)
        self.assertIsNot(hooks[0], server.start_ai_mcp_warmup)
        self.assertIs(unwrap(hooks[0]), server.start_ai_mcp_warmup)
        self.assertIs(server.start_ai_mcp_warmup, server._default_application.http.start_ai_mcp_warmup)
        with patch.dict(os.environ,{'INSPECTION_AI_MCP_RUNTIME':'','INSPECTION_AI_MCP_SERVER_MODE':''},clear=True),patch.object(server.threading,'Thread',side_effect=AssertionError('thread')):
            server.start_ai_mcp_warmup()
        with patch.dict(os.environ,{'INSPECTION_AI_MCP_RUNTIME':'stdio','INSPECTION_AI_MCP_SERVER_MODE':''},clear=True),patch.object(server._ai_mcp_client,'start_warmup') as start:
            server.start_ai_mcp_warmup()
            start.assert_called_once_with(server.warm_ai_mcp_client, threads=server.threading.Thread)


if __name__=='__main__':unittest.main()

"""MCP client state and wire behavior with fake processes; no subprocess starts."""
import ast
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASELINE = os.environ.get('VANTALINE_MCP_CLIENT_BASELINE_SOURCE')


class ProviderError(RuntimeError):
    pass


def create(bindings):
    if BASELINE:
        node = next(n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body
                    if isinstance(n, ast.ClassDef) and n.name == 'LocalAiMcpClient')
        ns = dict(bindings, Any=Any, subprocess=subprocess, sys=sys, threading=threading, json=json)
        exec(compile(ast.Module(body=[node], type_ignores=[]), BASELINE, 'exec'), ns)
        return ns['LocalAiMcpClient'](), ns
    from local_inspection_service.model_providers.mcp_client import LocalAiMcpClient
    return LocalAiMcpClient(root=lambda: bindings['ROOT'], error=lambda: bindings['AiProviderError'],
                            runtime=lambda: bindings['AI_MCP_RUNTIME_STDIO']), bindings


def process(response):
    return SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO(response),
                           poll=Mock(return_value=None), terminate=Mock())


class Contracts(unittest.TestCase):
    def setUp(self):
        self.client, self.bindings = create(dict(ROOT=Path('/synthetic'), AiProviderError=ProviderError,
                                                AI_MCP_RUNTIME_STDIO='stdio'))

    @unittest.skipIf(bool(BASELINE), 'new explicit client construction')
    def test_actual_entry_constructor_has_only_explicit_dependencies(self):
        tree = ast.parse((ROOT / 'local_inspection_service/server.py').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if
                 (isinstance(n, ast.ImportFrom) and n.module == 'model_providers.mcp_client') or
                 (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_ai_mcp_client' for t in n.targets))]
        self.assertEqual(len(nodes), 2)
        ns = dict(__package__='local_inspection_service', ROOT=Path('/first'), AiProviderError=ProviderError, AI_MCP_RUNTIME_STDIO='stdio')
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('constructor must not spawn')):
            exec(compile(ast.Module(body=nodes, type_ignores=[]), '<entry construction>', 'exec'), ns)
        client = ns['_ai_mcp_client']
        self.assertIsNone(client.process)
        self.assertEqual(client.root(), Path('/first'))
        ns['ROOT'] = Path('/second')
        self.assertEqual(client.root(), Path('/second'))
        self.assertIs(client.error(), ProviderError)
        self.assertEqual(client.runtime(), 'stdio')

    def test_constructor_has_no_process_and_independent_lock_counter(self):
        other, _ = create(self.bindings)
        self.assertIsNone(self.client.process)
        self.assertEqual(self.client.next_id, 1)
        self.assertIsNot(self.client.lock, other.lock)
        self.client.next_id = 9
        self.assertEqual(other.next_id, 1)
        with self.client.lock:
            with self.client.lock:
                pass

    def test_initialize_once_and_exact_spawn_arguments(self):
        child = process('{"result":{}}\n')
        with patch.object(subprocess, 'Popen', return_value=child) as popen:
            self.client.ensure_started()
            self.client.ensure_started()
        popen.assert_called_once_with([sys.executable, '-m', 'local_inspection_service.ai_mcp_server'],
            cwd=str(Path('/synthetic')), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1)
        sent = json.loads(child.stdin.getvalue())
        self.assertEqual(sent, {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2024-11-05', 'clientInfo': {'name': 'local-inspection-service', 'version': '0.1.0'}}})
        self.assertEqual(self.client.next_id, 2)

    def test_failed_initialization_retains_assigned_process_and_consumed_id(self):
        child = process('')
        with patch.object(subprocess, 'Popen', return_value=child):
            with self.assertRaisesRegex(ProviderError, 'closed stdout'):
                self.client.ensure_started()
        self.assertIs(self.client.process, child)
        self.assertEqual(self.client.next_id, 2)
        child.terminate.assert_not_called()

    def test_spawn_failure_does_not_replace_previous_process(self):
        old = process(''); old.poll.return_value = 1; self.client.process = old
        error = OSError('spawn')
        with patch.object(subprocess, 'Popen', side_effect=error):
            with self.assertRaises(OSError) as caught:
                self.client.ensure_started()
        self.assertIs(caught.exception, error)
        self.assertIs(self.client.process, old)
        self.assertEqual(self.client.next_id, 1)

    def test_close_live_dead_and_terminate_failure(self):
        child = process(''); self.client.process = child; self.client.close()
        child.terminate.assert_called_once_with(); self.assertIsNone(self.client.process)
        child.poll.return_value = 0; child.terminate.reset_mock(); self.client.process = child; self.client.close()
        child.terminate.assert_not_called(); self.assertIsNone(self.client.process)
        child.poll.return_value = None; child.terminate.side_effect = OSError('terminate'); self.client.process = child
        with self.assertRaises(OSError): self.client.close()
        self.assertIs(self.client.process, child)

    def test_request_wire_defaults_unicode_and_legacy_response_identity(self):
        child = process('{"id":999,"result":{"value":"ok"}}\n'); self.client.process = child
        self.assertEqual(self.client.request('方法', None), {'value': 'ok'})
        self.assertEqual(child.stdin.getvalue(), '{"jsonrpc":"2.0","id":1,"method":"方法","params":{}}\n')
        self.assertEqual(self.client.next_id, 2)

    def test_protocol_error_boundaries(self):
        for response, message in [('', 'closed stdout'), ('[]', 'non-object'),
                                   ('{"error":{"message":"failure"}}', 'failure'),
                                   ('{"error":true}', 'AI MCP server error'), ('{"result":[]}', 'not an object')]:
            with self.subTest(response=response):
                self.client.process = process(response)
                with self.assertRaisesRegex(ProviderError, message): self.client.request('tool')
        self.client.process = process('not json')
        with self.assertRaises(json.JSONDecodeError): self.client.request('tool')
        self.client.process = None
        before = self.client.next_id
        with self.assertRaisesRegex(ProviderError, 'not started'): self.client.request('tool')
        self.assertEqual(self.client.next_id, before)

    def test_write_and_flush_errors_consume_id_without_retry(self):
        for stage in ('write', 'flush'):
            child = process('{}'); child.stdin = Mock(); error = OSError(stage)
            getattr(child.stdin, stage).side_effect = error; self.client.process = child
            before = self.client.next_id
            with self.assertRaises(OSError) as caught: self.client.request('tool', {})
            self.assertIs(caught.exception, error); self.assertEqual(self.client.next_id, before + 1)
            child.stdin.write.assert_called_once()

    def test_call_tool_payload_selection_and_metadata(self):
        result = {'content': [None, {'type': 'image'}, {'type': 'text', 'text': '[]'},
                              {'type': 'text', 'text': '{"value":1}'}]}
        self.client.ensure_started = Mock()
        self.client.request = Mock(return_value=result)
        self.assertEqual(self.client.call_tool('name', {'x': 2}), {'value': 1, 'mcp_transport': 'stdio', 'mcp_runtime': 'stdio'})
        self.client.request.assert_called_once_with('tools/call', {'name': 'name', 'arguments': {'x': 2}})
        result['content'] = [{'type': 'text', 'text': '{"mcp_transport":"custom","mcp_runtime":"other"}'}]
        self.assertEqual(self.client.call_tool('name', {}), {'mcp_transport': 'custom', 'mcp_runtime': 'other'})
        result['content'] = []
        with self.assertRaisesRegex(ProviderError, 'no JSON text'): self.client.call_tool('name', {})

    def test_invalid_first_text_still_fails_without_scanning_later(self):
        self.client.ensure_started = Mock()
        self.client.request = Mock(return_value={'content': [{'type': 'text', 'text': 'bad'}, {'type': 'text', 'text': '{}'}]})
        with self.assertRaises(json.JSONDecodeError): self.client.call_tool('x', {})

    def test_concurrent_tools_share_one_request_lock(self):
        entered, release, second_attempt = threading.Event(), threading.Event(), threading.Event()
        guard = self.client.lock
        events, failures = [], []
        class TracedLock:
            def __enter__(self):
                if threading.current_thread().name == 'second':
                    second_attempt.set()
                guard.acquire()
            def __exit__(self, *args):
                guard.release()
        self.client.lock = TracedLock()
        self.client.ensure_started = lambda: None
        def request(method, params):
            name = params['name']; events.append(name)
            if name == 'first':
                entered.set()
                if not release.wait(5): raise AssertionError('release timeout')
            return {'content': [{'type': 'text', 'text': '{}'}]}
        self.client.request = request
        def run(name):
            try: self.client.call_tool(name, {})
            except BaseException as exc: failures.append(exc)
        first = threading.Thread(target=run, args=('first',), name='first')
        second = threading.Thread(target=run, args=('second',), name='second')
        first.start()
        try:
            self.assertTrue(entered.wait(5))
            second.start()
            self.assertTrue(second_attempt.wait(5))
            self.assertEqual(events, ['first'])
        finally:
            release.set(); first.join(5)
            if second.ident is not None: second.join(5)
        self.assertFalse(first.is_alive()); self.assertFalse(second.is_alive())
        self.assertEqual(failures, []); self.assertEqual(events, ['first', 'second'])

    def test_selected_error_and_runtime_are_resolved_at_call_time(self):
        class Alternate(ProviderError): pass
        self.bindings['AiProviderError'] = Alternate
        with self.assertRaises(Alternate): self.client.request('x')
        self.client.ensure_started = Mock(); self.client.request = Mock(return_value={'content': [{'type': 'text', 'text': '{}'}]})
        self.bindings['AI_MCP_RUNTIME_STDIO'] = 'selected'
        self.assertEqual(self.client.call_tool('x', {})['mcp_runtime'], 'selected')


if __name__ == '__main__': unittest.main()

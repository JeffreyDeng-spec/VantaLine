"""MCP shutdown races: actual threads, fake transports and one harmless child, zero model calls."""
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_inspection_service.model_providers.mcp_client import LocalAiMcpClient, McpAdmissionClosed
from local_inspection_service.model_providers.mcp_runtime import McpWarmup
import scripts.smoke_model_tool_dispatch as dispatch_contract


def client():
    return LocalAiMcpClient(root=lambda: ROOT, error=lambda: RuntimeError, runtime=lambda: 'stdio')


class Process:
    def __init__(self, response='{"result":{}}\n'):
        self.stdin, self.stdout = io.StringIO(), io.StringIO(response)
        self.terminate = Mock()
        self.wait = Mock(return_value=0)
        self.poll = Mock(return_value=None)


class Drain(unittest.TestCase):
    def wait(self, event): self.assertTrue(event.wait(3), 'bounded rendezvous failed')
    def join(self, thread):
        thread.join(3); self.assertFalse(thread.is_alive())
    def start(self, fn):
        errors = []
        def run():
            try: fn()
            except BaseException as exc: errors.append(exc)
        thread = threading.Thread(target=run); thread.start()
        return thread, errors

    def test_blocked_stdio_is_not_terminated_or_replayed_on_timeout(self):
        c = client(); p = Process(); c.process = p
        entered, release = threading.Event(), threading.Event()
        def readline():
            entered.set(); self.wait(release)
            return json.dumps({'result': {'content': [{'type': 'text', 'text': '{"answer":1}'}]}})
        p.stdout = Mock(readline=readline)
        results = []
        thread, errors = self.start(lambda: results.append(c.call_tool('synthetic', {})))
        try:
            self.wait(entered); self.assertFalse(c.shutdown(0)); p.terminate.assert_not_called()
            with self.assertRaises(McpAdmissionClosed): c.call_tool('synthetic', {})
            self.assertEqual(len(p.stdin.getvalue().splitlines()), 1)
        finally:
            release.set(); self.join(thread)
        self.assertEqual(errors, []); self.assertEqual(results[0]['answer'], 1)
        self.assertTrue(c.shutdown(3)); p.terminate.assert_called_once(); p.wait.assert_called_once()

    def test_two_starters_share_one_initialize_and_shutdown_waits(self):
        c = client(); p = Process(); entered, release = threading.Event(), threading.Event()
        def readline(): entered.set(); self.wait(release); return '{"result":{}}'
        p.stdout = Mock(readline=readline)
        with patch.object(subprocess, 'Popen', return_value=p) as spawn:
            first, errors1 = self.start(c.ensure_started)
            self.wait(entered)
            admitted = threading.Event()
            def second_start():
                with c.admission():
                    admitted.set(); c.ensure_started()
            second, errors2 = self.start(second_start)
            self.wait(admitted)
            try:
                self.assertFalse(c.shutdown(0)); p.terminate.assert_not_called()
            finally:
                release.set(); self.join(first); self.join(second)
        self.assertEqual(errors1, [])
        self.assertEqual(errors2, [])
        spawn.assert_called_once(); self.assertEqual(len(p.stdin.getvalue().splitlines()), 1)
        self.assertTrue(c.shutdown(3))

    def test_closed_dispatch_never_runs_transport_payload_or_fallback(self):
        c = client(); self.assertTrue(c.shutdown(0))
        service, b, calls = dispatch_contract.ToolContract().fixture()
        b['admission'] = c.admission; b['_ai_mcp_client'] = c
        b['ai_mcp_runtime'] = Mock(side_effect=AssertionError('runtime reached'))
        with self.assertRaises(McpAdmissionClosed): service.call_ai_mcp_tool('known', {})
        self.assertEqual(calls, []); b['ai_mcp_runtime'].assert_not_called()

    def test_existing_fallback_remains_admitted_until_handler_finishes(self):
        c = client(); p = Process(''); c.process = p
        service, b, calls = dispatch_contract.ToolContract().fixture()
        b.update(admission=c.admission, _ai_mcp_client=c, ai_mcp_runtime=lambda: 'stdio')
        entered, release = threading.Event(), threading.Event()
        def fallback(payload):
            calls.append(payload); entered.set(); self.wait(release)
            return {'ok': True}
        b['AI_MCP_TOOL_HANDLERS']['known'] = fallback
        results = []
        thread, errors = self.start(lambda: results.append(service.call_ai_mcp_tool('known', {})))
        try:
            self.wait(entered); self.assertFalse(c.shutdown(0))
            p.terminate.assert_called_once(); p.wait.assert_not_called()
            with self.assertRaises(McpAdmissionClosed): service.call_ai_mcp_tool('known', {})
        finally:
            release.set(); self.join(thread)
        self.assertEqual(errors, []); self.assertEqual(len(calls), 1)
        self.assertEqual(results[0]['mcp_fallback_from'], 'stdio')
        self.assertTrue(c.shutdown(3)); p.terminate.assert_called_once(); p.wait.assert_called_once()

    def test_rejected_warmup_never_closes_an_admitted_transport(self):
        c = client(); p = Process(); c.process = p
        entered, release = threading.Event(), threading.Event()
        def active():
            with c.admission(): entered.set(); self.wait(release)
        thread, errors = self.start(active); self.wait(entered)
        try:
            self.assertFalse(c.shutdown(0))
            warmup = McpWarmup(admission=c.admission, enabled=lambda: True, client=lambda: c)
            with self.assertRaises(McpAdmissionClosed): warmup.warm_ai_mcp_client()
            p.terminate.assert_not_called()
        finally:
            release.set(); self.join(thread)
        self.assertEqual(errors, []); self.assertTrue(c.shutdown(3))

    def test_reap_timeout_is_retained_and_retry_does_not_terminate_twice(self):
        c = client(); p = Process(); c.process = p
        p.wait.side_effect = subprocess.TimeoutExpired('synthetic', 0)
        self.assertFalse(c.shutdown(0)); self.assertIs(c.process, p)
        p.terminate.assert_called_once()
        p.wait.side_effect = None
        self.assertTrue(c.shutdown(3)); p.terminate.assert_called_once()
        self.assertIsNone(c.process); self.assertTrue(c.shutdown(0))

    def test_recoverable_close_retains_process_until_final_reap(self):
        c = client(); p = Process(); c.process = p
        c.close(); self.assertIsNone(c.process)
        self.assertTrue(c.shutdown(3)); p.terminate.assert_called_once(); p.wait.assert_called_once()
        self.assertTrue(p.stdin.closed); self.assertTrue(p.stdout.closed)

    def test_dispatch_eof_after_process_exit_still_reaps_and_closes_streams(self):
        c = client(); p = Process(''); c.process = p
        # First poll sees a live initialized transport; recovery sees it exited.
        p.poll.side_effect = [None, 1, 1]
        service, b, calls = dispatch_contract.ToolContract().fixture()
        b.update(admission=c.admission, _ai_mcp_client=c, ai_mcp_runtime=lambda: 'stdio')
        result = service.call_ai_mcp_tool('known', {})
        self.assertEqual(result['mcp_fallback_from'], 'stdio')
        self.assertEqual(len(calls), 1); self.assertIsNone(c.process)
        self.assertTrue(c.shutdown(3))
        p.terminate.assert_not_called(); p.wait.assert_called_once()
        self.assertTrue(p.stdin.closed); self.assertTrue(p.stdout.closed)

    def test_independent_owners_and_exception_release(self):
        a, b = client(), client()
        with self.assertRaises(ValueError):
            with a.admission(): raise ValueError('synthetic')
        self.assertTrue(a.shutdown(0))
        with b.admission():
            self.assertFalse(b.shutdown(0))
            # This is nested work already admitted before shutdown, not a retry.
            with b.admission(): pass
        self.assertTrue(b.shutdown(0))
        with self.assertRaises(McpAdmissionClosed):
            with a.admission(): pass

    def test_actual_harmless_child_is_terminated_reaped_and_streams_closed(self):
        c = client()
        process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        c.process = process
        try:
            self.assertTrue(c.shutdown(3))
            self.assertIsNotNone(process.poll())
            self.assertTrue(process.stdin.closed); self.assertTrue(process.stdout.closed)
            self.assertIsNone(c.process)
        finally:
            if process.poll() is None:
                process.kill(); process.wait(timeout=3)
            for stream in (process.stdin, process.stdout):
                if stream: stream.close()

    def test_failed_warmup_retains_retired_process_for_shutdown(self):
        c = client(); p = Process('')
        warmup = McpWarmup(admission=c.admission, enabled=lambda: True, client=lambda: c)
        with patch.object(subprocess, 'Popen', return_value=p): warmup.warm_ai_mcp_client()
        p.terminate.assert_called_once(); self.assertIsNone(c.process)
        self.assertTrue(c.shutdown(3)); p.wait.assert_called_once()


if __name__ == '__main__': unittest.main()

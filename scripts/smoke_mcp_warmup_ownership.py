"""Startup thread ownership with real threads and synthetic callbacks only."""
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_inspection_service.model_providers.mcp_client import LocalAiMcpClient, McpAdmissionClosed


def client():
    return LocalAiMcpClient(root=lambda: ROOT, error=lambda: RuntimeError, runtime=lambda: 'stdio')


class Ownership(unittest.TestCase):
    def wait(self, event): self.assertTrue(event.wait(3), 'bounded rendezvous failed')
    def join(self, thread):
        thread.join(3); self.assertFalse(thread.is_alive())

    def test_closed_owner_cannot_launch_or_call_target(self):
        c = client(); callback = Mock(); factory = Mock()
        self.assertTrue(c.shutdown(0))
        self.assertFalse(c.start_warmup(callback, threads=factory))
        factory.assert_not_called(); callback.assert_not_called()

    def test_pending_factory_is_drained_and_reserved_operation_can_finish(self):
        c = client()
        constructing, construct, running, finish = [threading.Event() for _ in range(4)]
        errors = []
        def factory(**kwargs):
            self.assertEqual(kwargs['name'], 'ai-mcp-warmup'); self.assertTrue(kwargs['daemon'])
            constructing.set(); self.wait(construct)
            return threading.Thread(**kwargs)
        def callback():
            with c.admission(): running.set(); self.wait(finish)
        def start():
            try: c.start_warmup(callback, threads=factory)
            except BaseException as exc: errors.append(exc)
        caller = threading.Thread(target=start); caller.start()
        try:
            self.wait(constructing); self.assertFalse(c.shutdown(0))
            construct.set(); self.wait(running)
            self.assertFalse(c.shutdown(0)); self.assertFalse(c.start_warmup(Mock()))
        finally:
            construct.set(); finish.set(); self.join(caller)
            self.assertTrue(c.shutdown(3))
        self.assertEqual(errors, []); self.assertFalse(c._warmup_thread.is_alive())

    def test_concurrent_start_does_not_duplicate_live_warmup(self):
        c = client(); running, finish = threading.Event(), threading.Event()
        def callback(): running.set(); self.wait(finish)
        factory = Mock(side_effect=threading.Thread)
        try:
            self.assertTrue(c.start_warmup(callback, threads=factory)); self.wait(running)
            self.assertFalse(c.start_warmup(callback, threads=factory))
            factory.assert_called_once()
        finally:
            finish.set(); self.assertTrue(c.shutdown(3))

    def test_factory_failure_releases_start_and_operation_reservations(self):
        c = client(); error = ValueError('factory')
        with self.assertRaises(ValueError) as caught:
            c.start_warmup(Mock(), threads=Mock(side_effect=error))
        self.assertIs(caught.exception, error); self.assertTrue(c.shutdown(0))

    def test_start_failure_before_launch_releases_reservation(self):
        c = client(); callback = Mock()
        class CannotStart:
            def start(self): raise RuntimeError('start')
            def is_alive(self): return False
            def join(self, timeout): raise RuntimeError('cannot join before start')
        with self.assertRaisesRegex(RuntimeError, 'start'):
            c.start_warmup(callback, threads=lambda **kw: CannotStart())
        callback.assert_not_called(); self.assertFalse(c.shutdown(0))

    def test_start_failure_after_launch_preserves_live_thread(self):
        c = client(); running, finish = threading.Event(), threading.Event()
        class RaisedAfterStart(threading.Thread):
            def start(self):
                super().start()
                raise RuntimeError('post-start')
        def callback(): running.set(); self.wait(finish)
        try:
            with self.assertRaisesRegex(RuntimeError, 'post-start'):
                c.start_warmup(callback, threads=RaisedAfterStart)
            self.wait(running); self.assertFalse(c.shutdown(0))
        finally:
            finish.set(); self.assertTrue(c.shutdown(3))

    def test_start_failure_after_target_finished_does_not_double_release(self):
        c = client(); callback = Mock()
        class RaisedAfterCompletion(threading.Thread):
            def start(self):
                super().start(); self.join(3)
                raise RuntimeError('post-completion')
        with self.assertRaisesRegex(RuntimeError, 'post-completion'):
            c.start_warmup(callback, threads=RaisedAfterCompletion)
        callback.assert_called_once(); self.assertTrue(c.shutdown(0))

    def test_target_failure_is_reported_but_does_not_leak_admission(self):
        c = client(); errors = []
        def callback(): raise ValueError('warmup target')
        with patch.object(threading, 'excepthook', lambda args: errors.append(args.exc_value)):
            c.start_warmup(callback); self.assertTrue(c.shutdown(3))
        self.assertEqual(str(errors[0]), 'warmup target')
        self.assertFalse(c._warmup_thread.is_alive())

    def test_self_shutdown_returns_undrained_and_other_threads_cannot_borrow(self):
        c = client(); outcomes, errors = [], []
        def outsider():
            try:
                with c.admission(): outcomes.append('unexpected')
            except McpAdmissionClosed: outcomes.append('rejected')
        def callback():
            outcomes.append(c.shutdown(0))
            with c.admission(): outcomes.append('nested')
            thread = threading.Thread(target=outsider); thread.start(); self.join(thread)
        c.start_warmup(callback); self.assertTrue(c.shutdown(3))
        self.assertEqual(outcomes, [False, 'nested', 'rejected'])

    def test_interrupted_bootstrap_cannot_run_revoked_target(self):
        c = client(); entered, release = threading.Event(), threading.Event()
        callback = Mock(); captured = []
        class InterruptedBootstrap(threading.Thread):
            def _bootstrap_inner(self):
                entered.set(); release.wait(3)
                super()._bootstrap_inner()
            def start(self):
                original = self._started.wait
                def interrupted(*args, **kwargs):
                    self_outer.wait(entered)
                    raise KeyboardInterrupt('interrupted started wait')
                self._started.wait = interrupted
                try: super().start()
                finally: self._started.wait = original
        self_outer = self
        def factory(**kwargs):
            result = InterruptedBootstrap(**kwargs); captured.append(result); return result
        try:
            with self.assertRaises(KeyboardInterrupt): c.start_warmup(callback, threads=factory)
            self.assertFalse(c.shutdown(0)); callback.assert_not_called()
        finally:
            release.set()
            if captured:
                self.wait(captured[0]._started); self.join(captured[0])
        self.assertTrue(c.shutdown(3)); callback.assert_not_called()

    def test_retry_cannot_erase_uncertain_bootstrap_handle(self):
        c=client();entered,release=threading.Event(),threading.Event();callback=Mock();threads=[]
        outer=self
        class InterruptedBootstrap(threading.Thread):
            def _bootstrap_inner(self):entered.set();release.wait(3);super()._bootstrap_inner()
            def start(self):
                original=self._started.wait
                def interrupted(*args,**kwargs):outer.wait(entered);raise KeyboardInterrupt('bootstrap')
                self._started.wait=interrupted
                try:super().start()
                finally:self._started.wait=original
        def factory(**kwargs):
            thread=InterruptedBootstrap(**kwargs);threads.append(thread);return thread
        try:
            with self.assertRaises(KeyboardInterrupt):c.start_warmup(callback,threads=factory)
            self.assertTrue(c.start_warmup(lambda:None));self.join(c._warmup_thread)
            self.assertFalse(c.shutdown(0));callback.assert_not_called()
        finally:
            release.set()
            if threads:self.wait(threads[0]._started);self.join(threads[0])
        self.assertTrue(c.shutdown(3));callback.assert_not_called()

    def test_separate_owner_stays_open_after_other_owner_closes(self):
        a, b = client(), client(); done = threading.Event()
        self.assertTrue(a.shutdown(0)); self.assertTrue(b.start_warmup(done.set))
        self.wait(done); self.assertTrue(b.shutdown(3))


if __name__ == '__main__': unittest.main()

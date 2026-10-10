"""Exercise ordered Web drain with real native parents and child fan-out."""
import asyncio
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
import copy
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from local_inspection_service.runtime.shutdown import ShutdownStep, WebShutdown, register_web_shutdown
from local_inspection_service.runtime.training_tasks import TrainingThreadLifecycle


class WebShutdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime = ExitStack()
        temporary = cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='web-shutdown-contract-'))
        (Path(temporary) / 'local_inspection_service/static').mkdir(parents=True)
        cls.lifetime.enter_context(patch.dict(os.environ, {'LOCAL_INSPECTION_ROOT': temporary,
            'VANTALINE_DATA_STORE':'json', 'VANTALINE_FILE_STORE':'local',
            'VANTALINE_LABEL_INSPECTION_ENABLED':'false', 'LOCAL_INSPECTION_AUTO_RESUME_WORKER':'0'}))
        from local_inspection_service import server
        cls.server = server

    @classmethod
    def tearDownClass(cls):
        cls.lifetime.close()

    def test_one_budget_includes_existing_hooks_and_native_owners(self):
        now = [100.0]; events = []
        def hook():
            events.append('legacy'); now[0] += 3
        def close(name, elapsed):
            def run(remaining):
                events.append((name, remaining)); now[0] += elapsed; return True
            return run
        owner = WebShutdown((hook,), (ShutdownStep('producer', close('producer', 9)),
                                    ShutdownStep('consumer', close('consumer', 0))))
        with patch('local_inspection_service.runtime.shutdown.time.monotonic', lambda: now[0]):
            self.assertTrue(owner.close(10))
            self.assertTrue(owner.close(0))
        self.assertEqual(events, ['legacy', ('producer', 7.0), ('consumer', 0.0)])

    def test_undrained_parent_can_still_launch_child_and_release_its_thread_scope(self):
        admitted = threading.Event(); release = threading.Event(); child_done = threading.Event()
        events = []; errors = []
        @contextmanager
        def scope():
            identity = threading.get_ident(); events.append(('enter', identity))
            try: yield
            finally: events.append(('exit', identity))
        parent = TrainingThreadLifecycle(scope=scope); child = TrainingThreadLifecycle(scope=scope)
        def run_parent():
            admitted.set()
            try:
                if not release.wait(3): raise AssertionError('parent fixture timed out')
                child.submit(lambda launch: launch(lambda wrap: threading.Thread(target=wrap(child_done.set)), lambda t: None))
            except BaseException as error: errors.append(error)
        parent.submit(lambda launch: launch(lambda wrap: threading.Thread(target=wrap(run_parent)), lambda t: None))
        self.assertTrue(admitted.wait(2))
        owner = WebShutdown((), (ShutdownStep('parent', parent.close), ShutdownStep('child', child.close)))
        try:
            self.assertFalse(owner.close(0))
            self.assertEqual(owner.failed_component, 'parent')
            release.set()
            self.assertTrue(owner.close(3))
            self.assertTrue(child_done.is_set())
            self.assertFalse(errors)
            entered = sorted(value for action, value in events if action == 'enter')
            self.assertEqual(entered, sorted(value for action, value in events if action == 'exit'))
            self.assertEqual(len(entered), 2)
        finally:
            release.set(); parent.close(3); child.close(3)

    def test_callback_failure_is_sanitized_and_completed_prefix_is_not_repeated(self):
        events = []; fail = [True]
        def step(remaining):
            events.append('child')
            if fail[0]: raise RuntimeError('secret-synthetic-value /private/path')
            return True
        owner = WebShutdown((lambda: events.append('legacy'),), (
            ShutdownStep('parent', lambda remaining: events.append('parent') or True),
            ShutdownStep('child', step), ShutdownStep('dependency', lambda remaining: events.append('dependency') or True)))
        with self.assertRaisesRegex(RuntimeError, '^Web shutdown not drained: child$') as result:
            owner.shutdown_application()
        self.assertNotIn('secret-synthetic-value', str(result.exception))
        self.assertEqual(events, ['legacy', 'parent', 'child'])
        fail[0] = False
        self.assertTrue(owner.close(0))
        self.assertEqual(events, ['legacy', 'parent', 'child', 'child', 'dependency'])

    def test_legacy_stop_failure_does_not_close_later_dependencies(self):
        events = []
        def fail(): raise ValueError('private')
        owner = WebShutdown((lambda: events.append('first'), fail),
                            (ShutdownStep('native', lambda remaining: events.append('native') or True),))
        self.assertFalse(owner.close(0)); self.assertFalse(owner.close(0))
        self.assertEqual(events, ['first']); self.assertEqual(owner.failed_component, 'legacy-stop-1')

    def test_pipeline_real_run_fanout_uses_production_shutdown_order(self):
        from local_inspection_service.pipeline.auto_agent_runtime import PipelineAutoAgentRuntime
        from local_inspection_service.pipeline.advance_runtime import PipelineAdvanceRuntime
        deciding = threading.Event(); release = threading.Event(); advanced = threading.Event()
        lock = threading.RLock(); errors = []; calls = []; auto_inflight = set(); advance_inflight = set(); cancelled = {}
        identity = ContextVar('shutdown-pipeline-fixture', default=None)
        user = {'id': 'synthetic'}
        rows = {'auto': {'id':'auto', 'stage':'training', 'orchestration': {}},
                'advance': {'id':'advance', 'stage':'samples'}}
        execution = SimpleNamespace(identity=lambda:identity, traceback=lambda:lambda **kw:errors.append(sys.exc_info()[1]),
            stderr=lambda:None, clock=lambda:lambda:123, print=lambda:lambda *a, **kw:None,
            load_config=lambda:lambda:{}, scope_config=lambda:lambda config,user:config)
        def guarded(snapshot, config, cancel):
            calls.append((snapshot['id'], identity.get())); advanced.set()
        advance = PipelineAdvanceRuntime(
            SimpleNamespace(lock=lambda:lock, load=lambda:rows.get, sync=lambda:lambda task:None,
                save=lambda:lambda task:None, deepcopy=lambda:copy.deepcopy),
            SimpleNamespace(guarded=lambda:guarded, cancelled_error=lambda:RuntimeError), execution,
            SimpleNamespace(registry_lock=lambda:lock, inflight=lambda:advance_inflight,
                cancel_events=lambda:cancelled, event=lambda:threading.Event,
                thread=lambda:threading.Thread, runner=lambda:advance.run))
        def decide(*args, **kwargs):
            deciding.set()
            if not release.wait(3): raise AssertionError('decision fixture timed out')
            return {'action':'advance'}
        def commit(*args, pending_advances, **kwargs): pending_advances.append('advance')
        auto = PipelineAutoAgentRuntime(
            SimpleNamespace(lock=lambda:lock, load=lambda:rows.get, needs_agent=lambda:lambda task:True,
                orchestration=lambda:lambda task:task['orchestration'], signature=lambda:lambda task:'signature',
                max_steps=lambda:5, deepcopy=lambda:copy.deepcopy, save=lambda:lambda task:None),
            SimpleNamespace(load_config=execution.load_config, scope_config=execution.scope_config,
                decide=lambda:decide, commit=lambda:commit, now=lambda:lambda:123,
                schedule_advance=lambda:advance.schedule), execution,
            SimpleNamespace(lock=lambda:lock, inflight=lambda:auto_inflight,
                thread=lambda:threading.Thread, runner=lambda:auto.run))
        bindings = {'pipeline-auto-agent': auto.close, 'pipeline-advance': advance.close}
        order = [step.name for step in self.server.app.state.web_shutdown.steps if step.name in bindings]
        self.assertEqual(set(order), set(bindings))
        owner = WebShutdown((), tuple(ShutdownStep(name, bindings[name]) for name in order))
        auto.schedule(['auto'], user)
        try:
            self.assertTrue(deciding.wait(2)); self.assertFalse(owner.close(0))
            release.set(); self.assertTrue(owner.close(3))
            self.assertTrue(advanced.is_set()); self.assertFalse(errors)
            self.assertEqual(calls, [('advance', user)])
            self.assertFalse(auto_inflight); self.assertFalse(advance_inflight); self.assertFalse(cancelled)
        finally:
            release.set(); auto.close(3); advance.close(3)

    def test_concurrent_and_recursive_drains_cannot_duplicate_callbacks(self):
        entered = threading.Event(); release = threading.Event(); events = []; results = []
        def close(remaining):
            events.append('close'); entered.set()
            self.assertFalse(owner.close(0))
            return release.wait(3)
        owner = WebShutdown((), (ShutdownStep('worker', close),))
        thread = threading.Thread(target=lambda: results.append(owner.close(3)))
        thread.start()
        try:
            self.assertTrue(entered.wait(2)); self.assertFalse(owner.close(0))
        finally:
            release.set(); thread.join(3)
        self.assertFalse(thread.is_alive()); self.assertEqual(results, [True])
        self.assertTrue(owner.close(0)); self.assertEqual(events, ['close'])

    def test_only_explicit_drained_result_advances_and_interrupts_remain_visible(self):
        for value in (None, 1, 'ready', False):
            events = []
            owner = WebShutdown((), (ShutdownStep('first', lambda remaining: value),
                                      ShutdownStep('second', lambda remaining: events.append('second') or True)))
            self.assertFalse(owner.close(0)); self.assertFalse(events)
        interrupted = KeyboardInterrupt('fixture'); failures = [interrupted]
        def close(remaining):
            if failures: raise failures.pop()
            return True
        owner = WebShutdown((), (ShutdownStep('worker', close),))
        with self.assertRaises(KeyboardInterrupt) as result: owner.close(0)
        self.assertIs(result.exception, interrupted); self.assertTrue(owner.close(0))

    def test_validation_and_registration_are_inert_and_apps_are_independent(self):
        events = []; first = FastAPI(); second = FastAPI()
        first.on_event('shutdown')(lambda: events.append('first'))
        second.on_event('shutdown')(lambda: events.append('second'))
        a = register_web_shutdown(first, ()); b = register_web_shutdown(second, ())
        with self.assertRaises(RuntimeError): register_web_shutdown(first, ())
        self.assertEqual(first.router.on_shutdown, [a.shutdown_application])
        for timeout in (-1, math.nan, math.inf, threading.TIMEOUT_MAX * 2):
            with self.assertRaises(ValueError): a.close(timeout)
        self.assertFalse(events)
        async def lifespan(app):
            async with app.router.lifespan_context(app): pass
        asyncio.run(lifespan(first)); self.assertEqual(events, ['first'])
        asyncio.run(lifespan(second)); self.assertEqual(events, ['first', 'second'])
        self.assertIsNot(a, b)
        async def stop(): pass
        app = FastAPI(); app.on_event('shutdown')(stop)
        with self.assertRaises(ValueError): register_web_shutdown(app, ())
        self.assertEqual(app.router.on_shutdown, [stop]); self.assertFalse(hasattr(app.state, 'web_shutdown'))
        for names in (('duplicate', 'duplicate'), ('/private',), ('',)):
            with self.assertRaises(ValueError): WebShutdown((), tuple(ShutdownStep(name, lambda _: True) for name in names))

    def test_real_photo_disabled_start_does_not_create_threads(self):
        from unittest.mock import patch
        with patch("local_inspection_service.training.real_photo_api.accounts", return_value=set()), \
             patch.object(self.server._real_photo_dispatch_runtime, "start") as start:
            self.server.start_real_photo_training_dispatcher()
        start.assert_not_called()

    def test_real_root_composition_drains_idle_owned_resources_without_startup(self):
        server = self.server
        owner = server.app.state.web_shutdown
        self.assertEqual([hook.__name__ for hook in owner.hooks], ['stop_real_photo_training_dispatcher', 'set', 'stop'])
        bindings = [('real-photo-dispatch', server._real_photo_dispatch_runtime.close),
            ('pdf-import', server.app.state.label_pdf_import.close),
            ('pipeline-auto-agent', server._pipeline_auto_agent_runtime.close),
            ('pipeline-advance', server._pipeline_advance_runtime.close),
            ('pipeline-recommendation', server._pipeline_recommendation_runtime.close),
            ('auto-label', server._auto_optimization_label_processing.close),
            ('auto-shadow', server._auto_optimization_shadow_evaluation.close),
            ('auto-training-check', server._auto_optimization_training_scheduling.close),
            ('training', server._training_task_runtime.close),
            ('background-codex', server._background_codex_thread.close),
            ('image-worker', server._image_worker_runtime.close),
            ('document-import', server.document_import_jobs.close),
            ('prepared-comparison', server._prepared_comparison_runtime.close),
            ('standard-preparation', server.standard_preparation_jobs.close),
            ('text-extraction', server._text_extraction_runtime.close),
            ('transfer-progress', server._transfer_progress.close),
            ('yolo-warmup', server._yolo_warmup_runtime.close),
            ('model-mcp', server._ai_mcp_client.shutdown)]
        self.assertEqual([(step.name, step.close) for step in owner.steps], bindings)
        for _ in range(2):
            for shutdown in server.app.router.on_shutdown: shutdown()
        self.assertIsNone(owner.failed_component)


if __name__ == '__main__': unittest.main()

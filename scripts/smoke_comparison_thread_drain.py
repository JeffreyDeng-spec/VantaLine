"""Native comparison/deadline ownership without paid providers or physical I/O."""
from contextlib import contextmanager
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.deadline_tasks import DeadlineTimers
from local_inspection_service.runtime.training_tasks import TrainingRuntimeClosed
from local_inspection_service.text_inspection.comparison_runtime import ComparisonRuntime
from local_inspection_service.text_inspection import comparison_jobs as comparison
from local_inspection_service.text_inspection.comparison_ports import ComparisonRecords, ComparisonMedia
from local_inspection_service import qwen_evidence_jobs as qwen
from scripts import smoke_comparison_dependencies as retained
REAL_THREAD, REAL_TIMER = threading.Thread, threading.Timer


class Ownership(unittest.TestCase):
    def setUp(self):
        patcher = patch('requests.post', side_effect=AssertionError('network forbidden'))
        patcher.start(); self.addCleanup(patcher.stop)

    def submit(self, f, runtime, use_qwen=False):
        ns = f.namespace
        with patch.dict('os.environ', {'VANTALINE_QWEN_OCR_ACCOUNTS': f.owner if use_qwen else ''}):
            return comparison.submit(
                ComparisonRecords(ns['_text_v2_load'], ns['_text_v2_save'], ns['_text_v2_owned'], ns['_text_v2_update_attempt'], ns['_text_v2_public']),
                ComparisonMedia(ns['_text_v2_media_path'], ns['_text_v2_write'], ns['sha256_bytes']), f.model_ports(),
                ns['clear_thread_runtime_repository_selection'], lambda name, default: default,
                f.jobs, f.owner, 'fixture', f.standard, f.asset, {'preparation': f.template}, f.blob, 'request_001', None,
                execution=runtime)

    def test_actual_shipped_manifest_resolves_and_fingerprints(self):
        import json
        from local_inspection_service.model_profiles.service import fingerprint_sources, prompt_source_version
        root = Path(__file__).resolve().parents[1] / 'local_inspection_service'
        manifest = json.loads((root / 'model_profiles/prompt_sources.json').read_text())
        self.assertEqual(len(manifest['sources']), len(set(manifest['sources'])))
        for source in manifest['sources']:
            self.assertTrue((root / source).is_file(), source)
        self.assertIn('runtime/deadline_tasks.py', manifest['sources'])
        self.assertIn('text_inspection/comparison_runtime.py', manifest['sources'])
        self.assertEqual(prompt_source_version(), fingerprint_sources(root, manifest))

    def test_waiting_timer_cancel_joins_and_rejects_new_timers(self):
        owner = DeadlineTimers(); callback = Mock(); timer = owner.start(120, callback)
        self.assertTrue(owner.close(3)); self.assertFalse(timer.is_alive()); callback.assert_not_called()
        with self.assertRaises(TrainingRuntimeClosed): owner.start(0, callback)

    def test_running_timer_retained_through_same_thread_scope_exit(self):
        entered, release = threading.Event(), threading.Event(); ids = []
        @contextmanager
        def scope():
            ids.append(threading.get_ident())
            try: yield
            finally: ids.append(threading.get_ident()); entered.set(); release.wait(3)
        owner = DeadlineTimers(scope=scope); callback = Mock(); timer = owner.start(0, callback)
        try:
            self.assertTrue(entered.wait(3)); self.assertFalse(owner.close(0)); self.assertTrue(timer.is_alive())
        finally: release.set(); self.assertTrue(owner.close(3))
        callback.assert_called_once(); self.assertEqual(ids[0], ids[1]); self.assertNotEqual(ids[0], threading.get_ident())

    def test_pending_timer_constructor_cannot_escape_close_snapshot(self):
        entered, release = threading.Event(), threading.Event(); callback = Mock(); errors = []; timers = []
        owner = DeadlineTimers()
        def factory(*args, **kwargs):
            entered.set(); release.wait(3); return REAL_TIMER(*args, **kwargs)
        def caller():
            try: timers.append(owner.start(120, callback))
            except BaseException as error: errors.append(error)
        with patch.object(threading, 'Timer', factory):
            thread = REAL_THREAD(target=caller); thread.start()
            try: self.assertTrue(entered.wait(3)); self.assertFalse(owner.close(0))
            finally: release.set(); thread.join(3); self.assertTrue(owner.close(3))
        self.assertFalse(thread.is_alive()); self.assertEqual(errors, []); callback.assert_not_called()
        self.assertFalse(timers[0].is_alive()); self.assertTrue(timers[0].finished.is_set())

    def test_interrupted_timer_bootstrap_keeps_late_handle_owned(self):
        entered, release = threading.Event(), threading.Event(); callback = Mock(); threads = []; outer = self
        owner = DeadlineTimers()
        class Interrupted(REAL_TIMER):
            def _bootstrap_inner(self): entered.set(); release.wait(3); super()._bootstrap_inner()
            def start(self):
                original = self._started.wait
                def interrupt(*args, **kwargs):
                    outer.assertTrue(entered.wait(3)); raise KeyboardInterrupt('timer bootstrap')
                self._started.wait = interrupt
                try: super().start()
                finally: self._started.wait = original
        def factory(*args, **kwargs):
            timer = Interrupted(*args, **kwargs); threads.append(timer); return timer
        try:
            with patch.object(threading, 'Timer', factory), self.assertRaises(KeyboardInterrupt): owner.start(0, callback)
            self.assertFalse(owner.close(0)); self.assertTrue(threads[0].finished.is_set())
        finally:
            release.set()
            if threads: self.assertTrue(threads[0]._started.wait(3)); threads[0].join(3)
        self.assertTrue(owner.close(3)); callback.assert_not_called()

    def test_timer_start_error_after_entry_retains_running_callback(self):
        entered, release = threading.Event(), threading.Event(); error = ValueError('started'); calls = []
        def callback(): calls.append(1); entered.set(); release.wait(3)
        class Started(REAL_TIMER):
            def start(self):
                super().start()
                assert entered.wait(3)
                raise error
        owner = DeadlineTimers()
        try:
            with patch.object(threading, 'Timer', Started), self.assertRaises(ValueError) as caught: owner.start(0, callback)
            self.assertIs(caught.exception, error); self.assertFalse(owner.close(0))
        finally: release.set(); self.assertTrue(owner.close(3))
        self.assertEqual(calls, [1])

    def test_failed_parent_drain_keeps_deadline_admission_and_callbacks_active(self):
        runtime = ComparisonRuntime(); entered, release, deadline = threading.Event(), threading.Event(), threading.Event()
        def target(): entered.set(); release.wait(3)
        runtime.threads.submit(lambda launch: launch(lambda wrap: REAL_THREAD(target=wrap(target)), lambda thread: None))
        try:
            self.assertTrue(entered.wait(3)); self.assertFalse(runtime.close(0))
            runtime.deadlines.start(0, deadline.set); self.assertTrue(deadline.wait(3))
            with self.assertRaises(TrainingRuntimeClosed): runtime.threads.submit(lambda launch: None)
        finally: release.set(); self.assertTrue(runtime.close(3))

    def test_actual_local_and_qwen_paths_use_explicit_capacity_and_no_replay(self):
        for use_qwen in (False, True):
            with self.subTest(qwen=use_qwen):
                f = retained.Fixture(self); runtime = ComparisonRuntime()
                poison = Mock(); poison.acquire.side_effect = AssertionError('global slot used')
                with patch.object(comparison, '_slots', poison), patch.object(qwen, '_slots', poison), \
                     patch.object(qwen.ocr, 'recognize', f.recognize), patch.object(qwen, 'llm', f.mapping):
                    record = self.submit(f, runtime, use_qwen)
                    self.assertTrue(runtime.close(3))
                self.assertEqual(f.store['records', record['id']]['status'], 'completed')
                self.assertEqual(len(f.calls), 1 if use_qwen else 0); self.assertEqual(f.clears, 1)
                before = list(f.events)
                with self.assertRaises(TrainingRuntimeClosed): self.submit(f, runtime, use_qwen)
                self.assertEqual(f.events, before)

    def test_parent_finished_does_not_hide_an_active_timeout_callback(self):
        f = retained.Fixture(self); runtime = ComparisonRuntime(); entered, release = threading.Event(), threading.Event()
        original_update = f.namespace['_text_v2_update_attempt']; original_start = runtime.deadlines.start
        def update(kind, value):
            if value.get('diagnostics', {}).get('phase') == 'timeout': entered.set(); release.wait(3)
            return original_update(kind, value)
        f.namespace['_text_v2_update_attempt'] = update
        f.provider_hook = lambda: self.assertTrue(entered.wait(3))
        with patch.object(runtime.deadlines, 'start', lambda interval, callback: original_start(0, callback)), \
             patch.object(qwen.ocr, 'recognize', f.recognize), patch.object(qwen, 'llm', f.mapping):
            record = self.submit(f, runtime, True)
            try:
                self.assertTrue(entered.wait(3)); self.assertTrue(runtime.threads.close(3))
                self.assertFalse(runtime.close(0))
                self.assertEqual(f.store['records', record['id']]['status'], 'completed')
            finally: release.set(); self.assertTrue(runtime.close(3))
        self.assertEqual(f.store['records', record['id']]['status'], 'completed'); self.assertEqual(f.clears, 2)

    def test_actual_capacity_is_held_through_repository_scope_exit(self):
        for use_qwen in (False, True):
            for fail_exit in (False, True):
                with self.subTest(qwen=use_qwen, fail_exit=fail_exit):
                    f = retained.Fixture(self); entered, release = threading.Event(), threading.Event()
                    errors = []; error = RuntimeError('scope exit'); ids = []
                    @contextmanager
                    def scope():
                        ids.append(threading.get_ident())
                        try: yield
                        finally:
                            ids.append(threading.get_ident()); entered.set(); release.wait(3)
                            if fail_exit: raise error
                    runtime = ComparisonRuntime(scope=scope)
                    semaphore = runtime.qwen_slots if use_qwen else runtime.local_slots
                    with patch.object(threading, 'excepthook', lambda event: errors.append(event.exc_value)), \
                         patch.object(qwen.ocr, 'recognize', f.recognize), patch.object(qwen, 'llm', f.mapping):
                        record = self.submit(f, runtime, use_qwen)
                        try:
                            self.assertTrue(entered.wait(3)); self.assertFalse(runtime.close(0))
                            self.assertFalse(semaphore.acquire(blocking=False))
                            self.assertEqual(f.store['records', record['id']]['status'], 'completed')
                        finally: release.set(); self.assertTrue(runtime.close(3))
                    self.assertTrue(semaphore.acquire(blocking=False))
                    self.assertFalse(semaphore.acquire(blocking=False)); semaphore.release()
                    self.assertEqual(errors, [error] if fail_exit else [])
                    self.assertEqual(ids[0], ids[1]); self.assertNotEqual(ids[0], threading.get_ident())

    def test_per_app_slots_and_owners_are_distinct(self):
        first, second = ComparisonRuntime(), ComparisonRuntime()
        self.assertIsNot(first.local_slots, second.local_slots); self.assertIsNot(first.qwen_slots, second.qwen_slots)
        self.assertTrue(first.close(0)); fired = threading.Event()
        second.deadlines.start(0, fired.set); self.assertTrue(fired.wait(3)); self.assertTrue(second.close(3))

    def test_completed_and_failed_timer_registry_does_not_accumulate(self):
        owner = DeadlineTimers(); failures = []
        def fail(): raise RuntimeError('synthetic callback')
        with patch.object(threading, 'excepthook', lambda event: failures.append(event.exc_value)):
            for _ in range(5):
                timer = owner.start(0, fail); timer.join(3)
                self.assertFalse(timer.is_alive())
            waiting = owner.start(120, lambda: None)
            self.assertEqual(len(owner._timers), 1)
            self.assertTrue(owner.close(3)); self.assertFalse(waiting.is_alive())
        self.assertEqual(len(failures), 5)

    def test_timer_scope_failure_still_has_joinable_completion(self):
        for phase in ('enter', 'exit'):
            with self.subTest(phase=phase):
                callback = Mock(); failures = []; error = RuntimeError('scope')
                @contextmanager
                def scope():
                    if phase == 'enter': raise error
                    try: yield
                    finally:
                        if phase == 'exit': raise error
                owner = DeadlineTimers(scope=scope)
                with patch.object(threading, 'excepthook', lambda event: failures.append(event.exc_value)):
                    timer = owner.start(0, callback); timer.join(3); self.assertTrue(owner.close(3))
                self.assertEqual(failures, [error]); self.assertEqual(callback.call_count, 0 if phase == 'enter' else 1)


if __name__ == '__main__': unittest.main()

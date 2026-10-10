"""Native text-job thread and semaphore ownership with no provider calls."""
from contextlib import contextmanager
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.training_tasks import TrainingThreadLifecycle, TrainingRuntimeClosed
from local_inspection_service.text_inspection.document_jobs import DocumentJobs
from local_inspection_service.text_inspection.preparation_jobs import PreparationJobs
REAL_THREAD = threading.Thread
KINDS = ('document', 'preparation')


def fixture(kind, callback, scope=None):
    records = SimpleNamespace(owned=Mock(return_value={'id': 'order'}))
    settings = {'configured': True, 'model': 'synthetic-bound', 'profile_version': 7}
    models = SimpleNamespace(settings=Mock(return_value=settings), external_enabled=lambda: True)
    runtime = TrainingThreadLifecycle(**({'scope': scope} if scope else {}))
    if kind == 'document':
        jobs = DocumentJobs(records, models, Mock(), Mock(), runtime=runtime)
        jobs.settings = Mock(return_value=settings)
        capacity = 2
    else:
        jobs = PreparationJobs(records, None, models, Mock(), runtime=runtime)
        jobs.view = Mock(return_value={'job': {'state': 'processing'}})
        capacity = 1
    jobs.mutate = Mock(return_value=True)
    jobs.run = callback
    def start():
        with patch('local_inspection_service.text_inspection.preparation_jobs.enabled', return_value=True):
            return jobs.start('order', 'owner')
    return SimpleNamespace(jobs=jobs, start=start, records=records, models=models, settings=settings, capacity=capacity)


def available(slots):
    acquired = 0
    try:
        while slots.acquire(blocking=False):
            acquired += 1
        return acquired
    finally:
        for _ in range(acquired):
            slots.release()


class TextJobs(unittest.TestCase):
    def test_close_rejects_before_settings_records_and_durable_claim(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                target = Mock()
                f = fixture(kind, target)
                self.assertTrue(f.jobs.close(0))
                with self.assertRaises(TrainingRuntimeClosed):
                    f.start()
                f.jobs.mutate.assert_not_called()
                f.records.owned.assert_not_called()
                f.models.settings.assert_not_called()
                if kind == 'document':
                    f.jobs.settings.assert_not_called()
                target.assert_not_called()
                self.assertEqual(available(f.jobs.slots), f.capacity)

    def test_slot_retained_through_repository_scope_exit(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                cleanup, release = threading.Event(), threading.Event()
                ids = []
                @contextmanager
                def scope():
                    ids.append(threading.get_ident())
                    try:
                        yield
                    finally:
                        ids.append(threading.get_ident())
                        cleanup.set()
                        release.wait(3)
                callback = Mock()
                f = fixture(kind, callback, scope)
                f.start()
                try:
                    self.assertTrue(cleanup.wait(3))
                    self.assertFalse(f.jobs.close(0))
                    self.assertEqual(available(f.jobs.slots), f.capacity - 1)
                finally:
                    release.set()
                    self.assertTrue(f.jobs.close(3))
                self.assertEqual(available(f.jobs.slots), f.capacity)
                args = callback.call_args.args
                self.assertEqual(args[:2], ('order', 'owner'))
                self.assertTrue(args[2])
                self.assertIs(args[3], f.settings)
                self.assertEqual(ids[0], ids[1])
                self.assertNotEqual(ids[0], threading.get_ident())

    def test_pending_claim_remains_owned_across_close(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                entered, release = threading.Event(), threading.Event()
                callback = Mock()
                f = fixture(kind, callback)
                def claim(*args):
                    entered.set();release.wait(3);return True
                f.jobs.mutate.side_effect = claim
                caller = REAL_THREAD(target=f.start)
                caller.start()
                try:
                    self.assertTrue(entered.wait(3))
                    self.assertFalse(f.jobs.close(0))
                finally:
                    release.set();caller.join(3)
                    self.assertTrue(f.jobs.close(3))
                callback.assert_called_once()
                self.assertEqual(available(f.jobs.slots), f.capacity)

    def test_constructor_failure_restores_slot_and_preserves_exception(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                target = Mock();f = fixture(kind, target);error = RuntimeError('constructor failure')
                with patch.object(threading, 'Thread', side_effect=error), self.assertRaises(RuntimeError) as caught:
                    f.start()
                self.assertIs(caught.exception, error)
                self.assertTrue(f.jobs.close(0))
                self.assertEqual(available(f.jobs.slots), f.capacity)
                f.jobs.mutate.assert_called_once();target.assert_not_called()

    def test_failed_start_revokes_late_target_without_replaying(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                target = Mock();f = fixture(kind, target);captured = [];error = KeyboardInterrupt('uncertain start')
                class Unknown:
                    def __init__(self, **kwargs):captured.append(kwargs)
                    def start(self):raise error
                    def is_alive(self):return False
                    def join(self, timeout):raise RuntimeError('not confirmed started')
                with patch.object(threading, 'Thread', Unknown), self.assertRaises(KeyboardInterrupt) as caught:
                    f.start()
                self.assertIs(caught.exception, error)
                self.assertEqual(available(f.jobs.slots), f.capacity)
                self.assertFalse(f.jobs.close(0))
                captured[0]['target'](*captured[0]['args'])
                target.assert_not_called()
                self.assertEqual(available(f.jobs.slots), f.capacity)

    def test_post_start_error_never_releases_an_active_slot_early(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                entered, release = threading.Event(), threading.Event()
                calls = [];error = RuntimeError('start returned unknown outcome')
                def callback(*args):calls.append(args);entered.set();release.wait(3)
                f = fixture(kind, callback)
                class Started(REAL_THREAD):
                    def start(self):
                        super().start()
                        assert entered.wait(3)
                        raise error
                try:
                    with patch.object(threading, 'Thread', Started), self.assertRaises(RuntimeError) as caught:
                        f.start()
                    self.assertIs(caught.exception, error)
                    self.assertEqual(available(f.jobs.slots), f.capacity - 1)
                    self.assertFalse(f.jobs.close(0))
                finally:
                    release.set()
                    self.assertTrue(f.jobs.close(3))
                self.assertEqual(available(f.jobs.slots), f.capacity)
                self.assertEqual(len(calls), 1)

    def test_scope_entry_and_exit_failure_restore_slot(self):
        for kind in KINDS:
            for phase in ('entry', 'exit'):
                with self.subTest(kind=kind, phase=phase):
                    target = Mock();error = RuntimeError('synthetic scope failure');failures = []
                    @contextmanager
                    def scope():
                        if phase == 'entry':raise error
                        try:yield
                        finally:
                            if phase == 'exit':raise error
                    f = fixture(kind, target, scope)
                    with patch.object(threading, 'excepthook', lambda event: failures.append(event.exc_value)):
                        f.start();self.assertTrue(f.jobs.close(3))
                    self.assertEqual(failures, [error])
                    self.assertEqual(target.call_count, 0 if phase == 'entry' else 1)
                    self.assertEqual(available(f.jobs.slots), f.capacity)

    def test_native_interrupted_bootstrap_revokes_late_work_and_retains_handle(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                entered, release = threading.Event(), threading.Event()
                target = Mock(); scopes = []; threads = []; outer = self
                @contextmanager
                def scope():
                    scopes.append(threading.get_ident())
                    yield
                f = fixture(kind, target, scope)
                class Interrupted(REAL_THREAD):
                    def _bootstrap_inner(self):
                        entered.set(); release.wait(3); super()._bootstrap_inner()
                    def start(self):
                        original = self._started.wait
                        def interrupt(*args, **kwargs):
                            outer.assertTrue(entered.wait(3))
                            raise KeyboardInterrupt('native bootstrap')
                        self._started.wait = interrupt
                        try: super().start()
                        finally: self._started.wait = original
                def factory(**kwargs):
                    thread = Interrupted(**kwargs); threads.append(thread); return thread
                try:
                    with patch.object(threading, 'Thread', factory), self.assertRaises(KeyboardInterrupt):
                        f.start()
                    self.assertEqual(available(f.jobs.slots), f.capacity)
                    self.assertFalse(f.jobs.close(0))
                    target.assert_not_called(); self.assertEqual(scopes, [])
                finally:
                    release.set()
                    if threads:
                        self.assertTrue(threads[0]._started.wait(3)); threads[0].join(3)
                        self.assertFalse(threads[0].is_alive())
                self.assertTrue(f.jobs.close(3))
                self.assertEqual(available(f.jobs.slots), f.capacity)
                target.assert_not_called(); self.assertEqual(scopes, [])

    def test_preparation_duplicate_view_failure_does_not_double_release(self):
        f = fixture('preparation', Mock());error = RuntimeError('view failure')
        f.jobs.mutate.return_value = False
        f.jobs.view.side_effect = error
        with self.assertRaises(RuntimeError) as caught:f.start()
        self.assertIs(caught.exception, error)
        self.assertEqual(available(f.jobs.slots), 1)
        self.assertTrue(f.jobs.close(0))
        f.jobs.run.assert_not_called()


if __name__ == '__main__':
    unittest.main()

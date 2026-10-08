"""Transfer reporting ownership with synthetic counters and actual native threads."""
from contextlib import contextmanager
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.training.transfer_progress import TransferProgress
from local_inspection_service.runtime.training_tasks import TrainingThreadLifecycle, TrainingRuntimeClosed


def start(service, interval=0.01):
    return service._start_transfer_progress_thread('job', {'done': 1, 'total': 2},
        done_field='sent', total_field='size', status_field='status', interval=interval)


class Ownership(unittest.TestCase):
    def test_closed_owner_rejects_before_event_and_dependency_resolution(self):
        dependency = Mock()
        service = TransferProgress(dependency, dependency, dependency)
        self.assertTrue(service.close(0))
        with self.assertRaises(TrainingRuntimeClosed):
            start(service)
        dependency.assert_not_called()

    def test_close_signals_reporter_and_preserves_returned_handles(self):
        updated = threading.Event()
        update = Mock(side_effect=lambda *args, **kwargs: updated.set())
        service = TransferProgress(lambda: update, threading.Event, lambda: threading.Thread)
        stop, thread = start(service)
        try:
            self.assertTrue(updated.wait(3))
            self.assertTrue(service.close(3))
            self.assertTrue(stop.is_set())
            self.assertFalse(thread.is_alive())
            update.assert_called_with('job', sent=1, size=2, status='running')
        finally:
            stop.set()
            thread.join(3)

    def test_pending_event_factory_gets_stop_after_close(self):
        entered, release = threading.Event(), threading.Event()
        returned, errors = [], []
        update = Mock()
        def event_factory():
            entered.set()
            release.wait(3)
            return threading.Event()
        service = TransferProgress(lambda: update, event_factory, lambda: threading.Thread)
        def caller():
            try:
                returned.append(start(service))
            except BaseException as error:
                errors.append(error)
        caller_thread = threading.Thread(target=caller)
        caller_thread.start()
        try:
            self.assertTrue(entered.wait(3))
            self.assertFalse(service.close(0))
        finally:
            release.set()
            caller_thread.join(3)
            self.assertTrue(service.close(3))
        self.assertEqual(errors, [])
        self.assertTrue(returned[0][0].is_set())
        self.assertFalse(returned[0][1].is_alive())
        update.assert_not_called()

    def test_scope_cleanup_must_finish_before_success(self):
        cleaning, release = threading.Event(), threading.Event()
        events = []
        @contextmanager
        def scope():
            events.append(('enter', threading.get_ident()))
            try:
                yield
            finally:
                events.append(('exit', threading.get_ident()))
                cleaning.set()
                release.wait(3)
        service = TransferProgress(lambda: Mock(), threading.Event, lambda: threading.Thread,
            runtime=TrainingThreadLifecycle(scope=scope))
        stop, thread = start(service)
        stop.set()
        try:
            self.assertTrue(cleaning.wait(3))
            self.assertFalse(service.close(0))
        finally:
            release.set()
            self.assertTrue(service.close(3))
        self.assertEqual(events[0][1], events[1][1])
        self.assertFalse(thread.is_alive())

    def test_blocked_update_is_not_cancelled_or_replayed(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def update(*args, **kwargs):
            calls.append((args, kwargs))
            entered.set()
            release.wait(3)
        service = TransferProgress(lambda: update, threading.Event, lambda: threading.Thread)
        stop, thread = start(service)
        try:
            self.assertTrue(entered.wait(3))
            self.assertFalse(service.close(0))
            self.assertTrue(stop.is_set())
        finally:
            release.set()
            self.assertTrue(service.close(3))
        self.assertEqual(len(calls), 1)
        self.assertFalse(thread.is_alive())

    def test_scope_entry_error_releases_reporter_event(self):
        errors = []
        @contextmanager
        def scope():
            raise LookupError('scope refused')
            yield
        service = TransferProgress(lambda: Mock(), threading.Event, lambda: threading.Thread,
            runtime=TrainingThreadLifecycle(scope=scope))
        original = threading.excepthook
        try:
            threading.excepthook = lambda args: errors.append(args.exc_value)
            stop, thread = start(service)
            thread.join(3)
        finally:
            threading.excepthook = original
        self.assertEqual(len(errors), 1)
        self.assertEqual(service._stops, [])
        self.assertTrue(service.close(0))

    def test_provider_and_constructor_errors_remove_events(self):
        for stage in ('provider', 'constructor'):
            with self.subTest(stage=stage):
                error = LookupError(stage)
                provider = Mock(side_effect=error) if stage == 'provider' else lambda: Mock(side_effect=error)
                service = TransferProgress(lambda: Mock(), threading.Event, provider)
                with self.assertRaises(LookupError) as caught:
                    start(service)
                self.assertIs(caught.exception, error)
                self.assertEqual(service._stops, [])
                self.assertTrue(service.close(0))

    def test_interrupted_native_bootstrap_retains_event_until_revoked_target_exits(self):
        entered, release = threading.Event(), threading.Event()
        threads, events = [], []
        update = Mock()
        outer = self
        class InterruptedBootstrap(threading.Thread):
            def _bootstrap_inner(self):
                entered.set()
                release.wait(3)
                super()._bootstrap_inner()
            def start(self):
                original = self._started.wait
                def interrupted(*args, **kwargs):
                    outer.assertTrue(entered.wait(3))
                    raise KeyboardInterrupt('native bootstrap interrupted')
                self._started.wait = interrupted
                try:
                    super().start()
                finally:
                    self._started.wait = original
        def factory(**kwargs):
            thread = InterruptedBootstrap(**kwargs)
            threads.append(thread)
            return thread
        def event_factory():
            event = threading.Event()
            events.append(event)
            return event
        service = TransferProgress(lambda: update, event_factory, lambda: factory)
        try:
            with self.assertRaises(KeyboardInterrupt):
                start(service)
            self.assertFalse(service.close(0))
            self.assertTrue(events[0].is_set())
            self.assertEqual(service._stops, events)
            update.assert_not_called()
        finally:
            release.set()
            if threads:
                self.assertTrue(threads[0]._started.wait(3))
                threads[0].join(3)
        self.assertTrue(service.close(3))
        self.assertEqual(service._stops, [])
        update.assert_not_called()

    def test_closing_one_owner_does_not_stop_another(self):
        first = TransferProgress(lambda: Mock(), threading.Event, lambda: threading.Thread)
        second = TransferProgress(lambda: Mock(), threading.Event, lambda: threading.Thread)
        one, thread_one = start(first, 100)
        two, thread_two = start(second, 100)
        try:
            self.assertTrue(first.close(3))
            self.assertTrue(one.is_set())
            self.assertFalse(two.is_set())
            self.assertTrue(thread_two.is_alive())
        finally:
            self.assertTrue(second.close(3))


if __name__ == '__main__':
    unittest.main()

"""Own auto-optimization starter threads without running optimization algorithms."""
from contextlib import contextmanager
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.training_tasks import TrainingThreadLifecycle, TrainingRuntimeClosed
from local_inspection_service.training.auto_optimization_label_processing import AutoOptimizationLabelProcessing
from local_inspection_service.training.auto_optimization_shadow_evaluation import AutoOptimizationShadowEvaluation
from local_inspection_service.training.auto_optimization_training_scheduling import AutoOptimizationTrainingScheduling
REAL_THREAD = threading.Thread
KINDS = ('label', 'shadow', 'check')


def fixture(kind, target, scope=None):
    lock, slots = threading.RLock(), {}
    sanitize = Mock(side_effect=lambda value: value.strip())
    state = SimpleNamespace(sanitize_ai_detection_task_id=lambda: sanitize,
        _auto_optimize_lock=lambda: lock, _auto_optimize_label_threads=lambda: slots,
        _auto_optimize_shadow_threads=lambda: slots, auto_optimize_label_worker=lambda: target,
        auto_optimize_shadow_worker=lambda: target, auto_optimize_training_check_worker=lambda: target)
    runtime = TrainingThreadLifecycle(**({'scope': scope} if scope else {}))
    if kind == 'label':
        service = AutoOptimizationLabelProcessing(state, None, None, runtime=runtime)
        start = lambda: service.start_auto_optimize_label_worker(' task ')
        expected = ('task',)
    elif kind == 'shadow':
        service = AutoOptimizationShadowEvaluation(state, None, None, runtime=runtime)
        start = lambda: service.start_auto_optimize_shadow_worker(' task ', 'sample')
        expected = ('task', 'sample')
    else:
        service = AutoOptimizationTrainingScheduling(None, None, state, runtime=runtime)
        start = lambda: service.start_auto_optimize_training_check_worker(' task ', 2.5)
        expected = ('task', 2.5)
    return SimpleNamespace(service=service, start=start, expected=expected,
        slots=slots, sanitize=sanitize, runtime=runtime)


class Drain(unittest.TestCase):
    def test_closed_starters_reject_before_sanitization(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                callback = Mock()
                f = fixture(kind, callback)
                self.assertTrue(f.service.close(0))
                with self.assertRaises(TrainingRuntimeClosed):
                    f.start()
                f.sanitize.assert_not_called()
                callback.assert_not_called()
                self.assertEqual(f.slots, {})

    def test_exact_arguments_and_scope_cleanup_before_drain(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
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
                callback = Mock()
                f = fixture(kind, callback, scope)
                f.start()
                try:
                    self.assertTrue(cleaning.wait(3))
                    self.assertFalse(f.service.close(0))
                finally:
                    release.set()
                    self.assertTrue(f.service.close(3))
                callback.assert_called_once_with(*f.expected)
                self.assertEqual(events[0][1], events[1][1])
                self.assertNotEqual(events[0][1], threading.get_ident())

    def test_native_handles_survive_public_registry_replacement(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                entered, release = threading.Event(), threading.Event()
                def work(*args):
                    entered.set()
                    release.wait(3)
                f = fixture(kind, work)
                f.start()
                try:
                    self.assertTrue(entered.wait(3))
                    f.slots.clear()
                    self.assertFalse(f.service.close(0))
                finally:
                    release.set()
                    self.assertTrue(f.service.close(3))

    def test_pending_constructor_remains_admitted_during_close(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                constructing, release = threading.Event(), threading.Event()
                callback = Mock()
                f = fixture(kind, callback)
                errors = []
                def constructor(**kwargs):
                    constructing.set()
                    release.wait(3)
                    return REAL_THREAD(**kwargs)
                def caller():
                    try:
                        f.start()
                    except BaseException as error:
                        errors.append(error)
                thread = REAL_THREAD(target=caller)
                with patch.object(threading, 'Thread', constructor):
                    thread.start()
                    try:
                        self.assertTrue(constructing.wait(3))
                        self.assertFalse(f.service.close(0))
                    finally:
                        release.set()
                        thread.join(3)
                        self.assertTrue(f.service.close(3))
                self.assertEqual(errors, [])
                callback.assert_called_once_with(*f.expected)

    def test_each_service_has_an_independent_owner(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                first = fixture(kind, Mock())
                second_target = Mock()
                second = fixture(kind, second_target)
                self.assertTrue(first.service.close(0))
                second.start()
                self.assertTrue(second.service.close(3))
                second_target.assert_called_once_with(*second.expected)


if __name__ == '__main__':
    unittest.main()

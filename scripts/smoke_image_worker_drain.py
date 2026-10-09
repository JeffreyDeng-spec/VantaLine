"""Real-thread admission/settlement races with synthetic jobs and connections."""
from contextlib import contextmanager
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_inspection_service.runtime.image_worker import ImageWorkerRuntime, ImageWork
from local_inspection_service.runtime.connections import ThreadRepositoryFactory
from local_inspection_service.accessories.image_job_queue import ImageJobQueue


def owner(target=lambda: None, **kwargs):
    return ImageWorkerRuntime(target=lambda: target, threads=lambda: threading.Thread, **kwargs)


class Drain(unittest.TestCase):
    def wait(self, event):
        self.assertTrue(event.wait(3), "bounded test rendezvous failed")

    def join(self, thread):
        thread.join(3)
        self.assertFalse(thread.is_alive())

    def test_closed_owner_rejects_start_lookup_and_restart(self):
        runtime = owner()
        callback = Mock()
        self.assertTrue(runtime.close(0))
        self.assertFalse(runtime.start())
        self.assertFalse(runtime.launch(callback))
        callback.assert_not_called()
        self.assertTrue(runtime.close(0))

    def test_pending_lookup_is_owned_until_child_settles(self):
        entered, release, child_started, finish = [threading.Event() for _ in range(4)]
        runtime = owner()
        def prepare():
            entered.set(); self.wait(release)
            return ImageWork(lambda: (child_started.set(), self.wait(finish)), "pending-child")
        admission = threading.Thread(target=lambda: runtime.launch(prepare))
        admission.start()
        try:
            self.wait(entered)
            self.assertFalse(runtime.close(0))
            release.set(); self.wait(child_started); self.join(admission)
            self.assertFalse(runtime.close(0))
        finally:
            release.set(); finish.set(); self.join(admission)
            self.assertTrue(runtime.close(3))

    def test_start_factory_does_not_hold_close_lock(self):
        entered, release = threading.Event(), threading.Event()
        def factory(**kwargs):
            entered.set(); self.wait(release)
            return threading.Thread(**kwargs)
        runtime = ImageWorkerRuntime(target=lambda: lambda: None, threads=lambda: factory)
        starter = threading.Thread(target=runtime.start); starter.start()
        try:
            self.wait(entered); self.assertFalse(runtime.close(0))
        finally:
            release.set(); self.join(starter)
            self.assertTrue(runtime.close(3))

    def test_coordinator_failure_does_not_lose_live_child(self):
        child_started, finish = threading.Event(), threading.Event()
        errors = []
        def coordinate():
            runtime.launch(lambda: ImageWork(lambda: (child_started.set(), self.wait(finish)), "survivor"))
            raise RuntimeError("coordinator fault")
        runtime = owner(coordinate)
        with patch.object(threading, 'excepthook', lambda args: errors.append(args.exc_value)):
            try:
                runtime.start(); self.wait(child_started); self.join(runtime.thread)
                self.assertEqual(runtime.processes, {})
                self.assertFalse(runtime.close(0))
                self.assertEqual(str(errors[0]), "coordinator fault")
            finally:
                finish.set(); self.assertTrue(runtime.close(3))

    def test_final_persistence_is_part_of_drain_without_store_lock_deadlock(self):
        store_lock = threading.Lock()
        writing, persisted = threading.Event(), threading.Event()
        def final_save():
            writing.set()
            with store_lock:
                persisted.set()
        runtime = owner()
        with store_lock:
            runtime.launch(lambda: ImageWork(final_save, "final-save"))
            self.wait(writing)
            self.assertFalse(runtime.close(0))
            self.assertFalse(persisted.is_set())
        self.assertTrue(runtime.close(3)); self.assertTrue(persisted.is_set())

    def test_start_failure_preserves_running_evidence_without_requeue(self):
        record = {'status': 'queued'}
        error = RuntimeError('start failed')
        class CannotStart:
            def start(self): raise error
            def is_alive(self): return False
            def join(self, timeout): raise RuntimeError('cannot join before start')
        runtime = ImageWorkerRuntime(target=lambda: lambda: None, threads=lambda: lambda **kw: CannotStart())
        run = Mock()
        def prepare():
            record['status'] = 'running'
            return ImageWork(run, 'never-started')
        with self.assertRaises(RuntimeError) as caught:
            runtime.launch(prepare)
        self.assertIs(caught.exception, error)
        self.assertEqual(record['status'], 'running'); run.assert_not_called()
        self.assertFalse(runtime.close(0))

    def test_interrupted_bootstrap_retains_coordinator_and_child_handles(self):
        for child in (False,True):
            with self.subTest(child=child):
                entered,release=threading.Event(),threading.Event();callback=Mock();captured=[]
                class InterruptedBootstrap(threading.Thread):
                    def _bootstrap_inner(thread_self):
                        entered.set();release.wait(3);super()._bootstrap_inner()
                    def start(thread_self):
                        original=thread_self._started.wait
                        def interrupted(*args,**kwargs):self.wait(entered);raise KeyboardInterrupt('bootstrap')
                        thread_self._started.wait=interrupted
                        try:super().start()
                        finally:thread_self._started.wait=original
                def factory(**kwargs):
                    thread=InterruptedBootstrap(**kwargs);captured.append(thread);return thread
                runtime=ImageWorkerRuntime(target=lambda:callback,threads=lambda:factory)
                try:
                    with self.assertRaises(KeyboardInterrupt):
                        if child:runtime.launch(lambda:ImageWork(callback,'child'))
                        else:runtime.start()
                    # Child-pruning or replacing the coordinator must not erase
                    # the uncertain old handle, even though is_alive is false.
                    runtime.active_children()
                    if not child:runtime.threads=lambda:threading.Thread;runtime.target=lambda:lambda:None;runtime.start()
                    self.assertFalse(runtime.close(0));callback.assert_not_called()
                finally:
                    release.set()
                    if captured:self.wait(captured[0]._started);self.join(captured[0])
                self.assertTrue(runtime.close(3));callback.assert_not_called()

    def test_prepare_failure_propagates_and_releases_admission(self):
        runtime = owner()
        error = ValueError('prepare')
        with self.assertRaises(ValueError) as caught:
            runtime.launch(Mock(side_effect=error))
        self.assertIs(caught.exception, error)
        self.assertTrue(runtime.close(0))

    def test_close_a_does_not_close_or_restart_b(self):
        started, finish = threading.Event(), threading.Event()
        a, b = owner(), owner(lambda: (started.set(), self.wait(finish)))
        try:
            b.start(); self.wait(started)
            self.assertTrue(a.close(0)); self.assertFalse(b.closing)
            self.assertTrue(b.thread.is_alive()); self.assertFalse(a.start())
        finally:
            finish.set(); self.assertTrue(b.close(3))

    def test_actual_queue_admits_before_lookup_and_stops_next_claim(self):
        lookup, release, running, finish = [threading.Event() for _ in range(4)]
        reads, marks = [], []
        def next_job():
            reads.append(1); lookup.set(); self.wait(release)
            return Path('/synthetic'), {}, {'job_id': str(len(reads))}
        execution = SimpleNamespace(
            _image_worker_runtime=lambda: runtime,
            next_queued_image_job=lambda: next_job,
            update_image_worker_status=lambda: lambda p, c, j, **kw: marks.append((j['job_id'], kw['status'])),
            run_image_generation_job=lambda: lambda *args: (running.set(), self.wait(finish)),
            MAX_PARALLEL_IMAGE_WORKERS=lambda: 2,
        )
        queue = ImageJobQueue(None, None, execution)
        runtime = owner(queue.image_worker_loop)
        try:
            runtime.start(); self.wait(lookup)
            self.assertFalse(runtime.close(0))
            release.set(); self.wait(running); self.join(runtime.thread)
            self.assertEqual(reads, [1]); self.assertEqual(marks, [('1', 'running')])
            self.assertFalse(runtime.close(0))
        finally:
            release.set(); finish.set(); self.assertTrue(runtime.close(3))

    def test_repository_scope_covers_coordinator_and_child_in_own_threads(self):
        opened, closed = [], []
        done = threading.Event()
        def create():
            identity = threading.get_ident(); opened.append(identity)
            connection = SimpleNamespace(closed=False, close=lambda: closed.append(threading.get_ident()))
            return SimpleNamespace(repository=SimpleNamespace(connection=connection))
        factory = ThreadRepositoryFactory(create, lambda: 'synthetic')
        def child():
            factory.selection(); done.set()
        def coordinate():
            factory.selection()
            runtime.launch(lambda: ImageWork(child, 'repository-child'))
        runtime = owner(coordinate, scope=factory.thread_scope)
        runtime.start(); self.wait(done); self.assertTrue(runtime.close(3))
        self.assertEqual(len(opened), 2); self.assertEqual(sorted(opened), sorted(closed))
        self.assertNotIn(threading.get_ident(), closed)

    def test_child_exception_also_exits_own_scope(self):
        exits, errors = [], []
        @contextmanager
        def scope():
            try: yield
            finally: exits.append(threading.get_ident())
        def fail(): raise ValueError('child fault')
        runtime = owner(scope=scope)
        with patch.object(threading, 'excepthook', lambda args: errors.append(args.exc_value)):
            runtime.launch(lambda: ImageWork(fail, 'failing-child'))
            self.assertTrue(runtime.close(3))
        self.assertEqual(len(exits), 1); self.assertNotEqual(exits[0], threading.get_ident())
        self.assertEqual(str(errors[0]), 'child fault')


if __name__ == '__main__': unittest.main()

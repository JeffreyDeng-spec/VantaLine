"""Real-thread training ownership; synthetic callbacks, no model or database I/O."""
from contextlib import contextmanager
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.training_tasks import TrainingTaskRuntime, TrainingRuntimeClosed
REAL_THREAD=threading.Thread


def owner(scope=None):
    return TrainingTaskRuntime(**({'scope':scope} if scope is not None else {}))


def launch_task(runtime, reason='task', model_ids=None, *, worker):
    def prepare(launch):
        launch(lambda wrap: threading.Thread(target=wrap(worker()), args=(reason, model_ids), name='training-task-'+reason, daemon=True),
               lambda thread: runtime.threads.__setitem__(reason, thread))
    return runtime.submit(prepare)


class Drain(unittest.TestCase):
    def wait(self,event):self.assertTrue(event.wait(3),'bounded rendezvous failed')
    def join(self,thread):thread.join(3);self.assertFalse(thread.is_alive())

    def test_closed_owner_rejects_before_worker_resolution_or_start(self):
        runtime=owner();provider=Mock()
        self.assertTrue(runtime.close(0))
        with patch.object(threading,'Thread') as factory:
            with self.assertRaises(TrainingRuntimeClosed):launch_task(runtime,worker=provider)
        factory.assert_not_called();provider.assert_not_called()

    def test_pending_factory_blocks_close_then_admitted_work_finishes(self):
        runtime=owner();constructing,construct,running,finish=[threading.Event() for _ in range(4)];errors=[]
        def factory(**kwargs):constructing.set();self.wait(construct);return REAL_THREAD(**kwargs)
        def work(*_):running.set();self.wait(finish)
        def start():
            try:launch_task(runtime,worker=lambda:work)
            except BaseException as exc:errors.append(exc)
        caller=REAL_THREAD(target=start)
        with patch.object(threading,'Thread',factory):
            caller.start()
            try:
                self.wait(constructing);self.assertFalse(runtime.close(0))
                construct.set();self.wait(running);self.assertFalse(runtime.close(0))
            finally:construct.set();finish.set();self.join(caller);self.assertTrue(runtime.close(3))
        self.assertEqual(errors,[])

    def test_each_start_owned_and_original_arguments_identity_preserved(self):
        runtime=owner();ready=[threading.Event(),threading.Event()];finish=threading.Event();ids=['one'];calls=[]
        def work(reason,values):calls.append((reason,values));ready[len(calls)-1].set();self.wait(finish)
        try:
            for event in ready:
                launch_task(runtime,'manual',ids,worker=lambda:work);self.wait(event)
            self.assertEqual(len(runtime._owned),2);self.assertFalse(runtime.close(0))
        finally:finish.set();self.assertTrue(runtime.close(3))
        self.assertEqual([x[0] for x in calls],['manual','manual']);self.assertTrue(all(x[1] is ids for x in calls))

    def test_scope_cleanup_runs_in_worker_and_close_waits_for_it(self):
        exited,release=threading.Event(),threading.Event();events=[]
        @contextmanager
        def scope():
            events.append(('open',threading.get_ident()))
            try:yield
            finally:
                events.append(('close',threading.get_ident()));exited.set();self.wait(release)
        runtime=owner(scope)
        launch_task(runtime,worker=lambda:lambda *_:events.append(('work',threading.get_ident())))
        try:self.wait(exited);self.assertFalse(runtime.close(0))
        finally:release.set();self.assertTrue(runtime.close(3))
        self.assertEqual([x[0] for x in events],['open','work','close'])
        self.assertEqual(len({x[1] for x in events}),1);self.assertNotEqual(events[0][1],threading.get_ident())

    def test_worker_error_still_exits_scope_and_drains(self):
        events=[];errors=[]
        @contextmanager
        def scope():
            try:yield
            finally:events.append('released')
        runtime=owner(scope)
        def work(*_):raise ValueError('worker')
        with patch.object(threading,'excepthook',lambda args:errors.append(args.exc_value)):
            launch_task(runtime,worker=lambda:work);self.assertTrue(runtime.close(3))
        self.assertEqual(events,['released']);self.assertEqual(str(errors[0]),'worker')

    def test_scope_entry_error_drains_without_running_target(self):
        callback=Mock();errors=[]
        @contextmanager
        def scope():raise RuntimeError('scope');yield
        runtime=owner(scope)
        with patch.object(threading,'excepthook',lambda args:errors.append(args.exc_value)):
            launch_task(runtime,worker=lambda:callback);self.assertTrue(runtime.close(3))
        callback.assert_not_called();self.assertEqual(str(errors[0]),'scope')

    def test_provider_and_constructor_errors_release_reservation(self):
        for failure in ('provider','constructor'):
            runtime=owner();error=ValueError(failure)
            with patch.object(threading,'Thread',side_effect=error if failure=='constructor' else REAL_THREAD):
                provider=Mock(side_effect=error) if failure=='provider' else lambda:Mock()
                with self.assertRaises(ValueError) as caught:launch_task(runtime,worker=provider)
            self.assertIs(caught.exception,error);self.assertTrue(runtime.close(0))

    def test_failure_before_start_does_not_leak_pending_work(self):
        class FailedStart:
            def start(self):raise ValueError('start')
            def is_alive(self):return False
            def join(self,timeout):raise RuntimeError('cannot join before start')
        runtime=owner();callback=Mock()
        with patch.object(threading,'Thread',return_value=FailedStart()):
            with self.assertRaisesRegex(ValueError,'start'):launch_task(runtime,worker=lambda:callback)
        self.assertFalse(runtime.close(0));callback.assert_not_called()

    def test_failure_after_start_keeps_live_handle(self):
        running,finish=threading.Event(),threading.Event();runtime=owner()
        class FailedAfterStart(REAL_THREAD):
            def start(self):super().start();raise ValueError('post-start')
        def work(*_):running.set();self.wait(finish)
        with patch.object(threading,'Thread',FailedAfterStart):
            try:
                with self.assertRaisesRegex(ValueError,'post-start'):launch_task(runtime,worker=lambda:work)
                self.wait(running);self.assertFalse(runtime.close(0))
            finally:finish.set();self.assertTrue(runtime.close(3))

    def test_interrupted_bootstrap_remains_owned_after_later_start(self):
        runtime=owner();entered,release=threading.Event(),threading.Event();callback=Mock();threads=[]
        outer=self
        class InterruptedBootstrap(REAL_THREAD):
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
            with patch.object(threading,'Thread',factory):
                with self.assertRaises(KeyboardInterrupt):launch_task(runtime,worker=lambda:callback)
            launch_task(runtime,worker=lambda:lambda *_:None)
            self.assertFalse(runtime.close(0));callback.assert_not_called()
        finally:
            release.set()
            if threads:self.wait(threads[0]._started);self.join(threads[0])
        self.assertTrue(runtime.close(3));callback.assert_not_called()

    def test_self_close_reports_undrained_without_deadlock(self):
        runtime=owner();done=threading.Event();results=[]
        def work(*_):results.append(runtime.close(1));done.set()
        launch_task(runtime,worker=lambda:work);self.wait(done)
        self.assertEqual(results,[False]);self.assertTrue(runtime.close(3))

    def test_other_owner_survives_close_and_enabled_gate_stays_unchanged(self):
        a,b=owner(),owner();done=threading.Event();self.assertTrue(a.close(0))
        launch_task(b,worker=lambda:lambda *_:done.set());self.wait(done);self.assertTrue(b.close(3))


    def test_registration_error_retains_unjoinable_handle_and_releases_pending(self):
        runtime=owner();callback=Mock();registered=[]
        def prepare(launch):
            def register(thread):registered.append(thread);raise LookupError("registry")
            launch(lambda wrap:REAL_THREAD(target=wrap(callback)),register)
        with self.assertRaisesRegex(LookupError,'registry'):runtime.submit(prepare)
        self.assertEqual(runtime._pending,0);self.assertEqual(len(registered),1)
        self.assertFalse(runtime.close(0));self.assertFalse(runtime.close(0));callback.assert_not_called()

    def test_public_registry_replacement_cannot_hide_a_running_thread(self):
        runtime=owner();running,finish=threading.Event(),threading.Event()
        def work(*_):running.set();self.wait(finish)
        try:
            launch_task(runtime,'same',worker=lambda:work);self.wait(running)
            launch_task(runtime,'same',worker=lambda:lambda *_:None)
            runtime.threads.clear();self.assertFalse(runtime.close(0))
        finally:finish.set();self.assertTrue(runtime.close(3))

    def test_pending_publication_waits_and_failure_does_not_requeue(self):
        runtime=owner();publishing,finish=threading.Event(),threading.Event();errors=[];calls=[]
        def prepare(launch):
            launch(lambda wrap:REAL_THREAD(target=wrap(lambda:calls.append('work'))),lambda _:None)
            publishing.set();self.wait(finish);raise LookupError('public')
        def submit():
            try:runtime.submit(prepare)
            except BaseException as error:errors.append(error)
        caller=REAL_THREAD(target=submit);caller.start()
        try:self.wait(publishing);self.assertFalse(runtime.close(0))
        finally:finish.set();self.join(caller);self.assertTrue(runtime.close(3))
        self.assertEqual(calls,['work']);self.assertEqual(str(errors[0]),'public')

    def test_two_submission_services_share_admission_before_persistence(self):
        from types import SimpleNamespace
        from local_inspection_service.training.submission import TrainingSubmission,TrainingSubmissionPolicy,TrainingSubmissionIdentity,TrainingSubmissionRecords,TrainingSubmissionThreads
        from local_inspection_service.training.background_task_submission import BackgroundTaskSubmission
        from local_inspection_service.schemas.training import TrainingStartRequest
        runtime=owner();effect=Mock();ports=TrainingSubmissionThreads(effect,effect,effect)
        records=TrainingSubmissionRecords(effect,effect)
        training=TrainingSubmission(TrainingSubmissionPolicy(effect,effect),TrainingSubmissionIdentity(effect,effect,effect),records,ports,runtime=runtime)
        background=BackgroundTaskSubmission(records,ports,effect,effect,effect,runtime=runtime)
        self.assertTrue(runtime.close(0))
        with self.assertRaises(TrainingRuntimeClosed):training.enqueue_training_task(TrainingStartRequest(selected_accessory_ids=[]),[],'train_model')
        with self.assertRaises(TrainingRuntimeClosed):background.enqueue_background_set_task('set','name',Path('synthetic'))
        effect.assert_not_called()

    def test_connections_are_distinct_and_closed_by_their_own_threads(self):
        from types import SimpleNamespace
        from local_inspection_service.runtime.connections import ThreadRepositoryFactory
        connections=[];observed=[];barrier=threading.Barrier(2)
        class Connection:
            closed=False
            def __init__(self):self.creator=threading.get_ident();self.closer=None
            def close(self):self.closer=threading.get_ident();self.closed=True
        def create():
            connection=Connection();connections.append(connection)
            return SimpleNamespace(repository=SimpleNamespace(connection=connection))
        factory=ThreadRepositoryFactory(create,lambda:'stable')
        runtime=owner(factory.thread_scope)
        def work(name,_):
            selected=factory.selection();barrier.wait(3)
            self.assertIs(factory.selection(),selected);observed.append(name)
        for name in ('alice','bob'):launch_task(runtime,name,worker=lambda:work)
        self.assertTrue(runtime.close(3));self.assertEqual(sorted(observed),['alice','bob'])
        self.assertEqual(len(connections),2);self.assertEqual(len({c.creator for c in connections}),2)
        self.assertTrue(all(c.closed and c.closer==c.creator for c in connections))

    def test_deadline_includes_native_thread_tail_after_target_and_scope_exit(self):
        runtime=owner();tail,finish=threading.Event(),threading.Event()
        class Tail(REAL_THREAD):
            def run(self):
                super().run();tail.set();finish.wait(3)
        with patch.object(threading,'Thread',Tail):
            launch_task(runtime,worker=lambda:lambda *_:None)
        try:self.wait(tail);self.assertFalse(runtime.close(0))
        finally:finish.set();self.assertTrue(runtime.close(3))

    def test_launch_capability_expires_after_submission_even_before_close(self):
        runtime=owner();saved=[];constructor=Mock();register=Mock()
        runtime.submit(lambda launch:saved.append(launch))
        with self.assertRaisesRegex(RuntimeError,'synchronous submission'):saved[0](constructor,register)
        constructor.assert_not_called();register.assert_not_called();self.assertTrue(runtime.close(0))

    def test_launch_capability_cannot_escape_to_a_concurrent_thread(self):
        runtime=owner();constructor=Mock();register=Mock();errors=[]
        def prepare(launch):
            def misuse():
                try:launch(constructor,register)
                except BaseException as error:errors.append(error)
            thread=REAL_THREAD(target=misuse);thread.start();self.join(thread)
        runtime.submit(prepare)
        self.assertEqual(len(errors),1);self.assertIn('synchronous submission',str(errors[0]))
        constructor.assert_not_called();register.assert_not_called();self.assertTrue(runtime.close(0))


if __name__=='__main__':unittest.main()

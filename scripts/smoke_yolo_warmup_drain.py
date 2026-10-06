"""Real-thread warmup ownership; synthetic callbacks, no model or database I/O."""
from contextlib import contextmanager
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.yolo_warmup import YoloWarmup, WarmupOperations
REAL_THREAD=threading.Thread


def owner(scope=None):
    operations=WarmupOperations(lambda:True,lambda:{},lambda _:[],lambda *_:None,lambda _:[],lambda:lambda value,_:value)
    return YoloWarmup(operations,**({'scope':scope} if scope is not None else {}))


class Drain(unittest.TestCase):
    def wait(self,event):self.assertTrue(event.wait(3),'bounded rendezvous failed')
    def join(self,thread):thread.join(3);self.assertFalse(thread.is_alive())

    def test_closed_owner_rejects_before_worker_resolution_or_start(self):
        runtime=owner();provider=Mock()
        self.assertTrue(runtime.close(0))
        with patch.object(threading,'Thread') as factory:
            runtime.start_yolo_warmup(worker=provider)
        factory.assert_not_called();provider.assert_not_called()

    def test_pending_factory_blocks_close_then_admitted_work_finishes(self):
        runtime=owner();constructing,construct,running,finish=[threading.Event() for _ in range(4)];errors=[]
        def factory(**kwargs):constructing.set();self.wait(construct);return REAL_THREAD(**kwargs)
        def work(*_):running.set();self.wait(finish)
        def start():
            try:runtime.start_yolo_warmup(worker=lambda:work)
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
                runtime.start_yolo_warmup('manual',ids,worker=lambda:work);self.wait(event)
            self.assertEqual(len(runtime._threads),2);self.assertFalse(runtime.close(0))
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
        runtime.start_yolo_warmup(worker=lambda:lambda *_:events.append(('work',threading.get_ident())))
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
            runtime.start_yolo_warmup(worker=lambda:work);self.assertTrue(runtime.close(3))
        self.assertEqual(events,['released']);self.assertEqual(str(errors[0]),'worker')

    def test_scope_entry_error_drains_without_running_target(self):
        callback=Mock();errors=[]
        @contextmanager
        def scope():raise RuntimeError('scope');yield
        runtime=owner(scope)
        with patch.object(threading,'excepthook',lambda args:errors.append(args.exc_value)):
            runtime.start_yolo_warmup(worker=lambda:callback);self.assertTrue(runtime.close(3))
        callback.assert_not_called();self.assertEqual(str(errors[0]),'scope')

    def test_provider_and_constructor_errors_release_reservation(self):
        for failure in ('provider','constructor'):
            runtime=owner();error=ValueError(failure)
            with patch.object(threading,'Thread',side_effect=error if failure=='constructor' else REAL_THREAD):
                provider=Mock(side_effect=error) if failure=='provider' else lambda:Mock()
                with self.assertRaises(ValueError) as caught:runtime.start_yolo_warmup(worker=provider)
            self.assertIs(caught.exception,error);self.assertTrue(runtime.close(0))

    def test_failure_before_start_does_not_leak_pending_work(self):
        class FailedStart:
            def start(self):raise ValueError('start')
            def is_alive(self):return False
            def join(self,timeout):raise RuntimeError('cannot join before start')
        runtime=owner();callback=Mock()
        with patch.object(threading,'Thread',return_value=FailedStart()):
            with self.assertRaisesRegex(ValueError,'start'):runtime.start_yolo_warmup(worker=lambda:callback)
        self.assertFalse(runtime.close(0));callback.assert_not_called()

    def test_failure_after_start_keeps_live_handle(self):
        running,finish=threading.Event(),threading.Event();runtime=owner()
        class FailedAfterStart(REAL_THREAD):
            def start(self):super().start();raise ValueError('post-start')
        def work(*_):running.set();self.wait(finish)
        with patch.object(threading,'Thread',FailedAfterStart):
            try:
                with self.assertRaisesRegex(ValueError,'post-start'):runtime.start_yolo_warmup(worker=lambda:work)
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
                with self.assertRaises(KeyboardInterrupt):runtime.start_yolo_warmup(worker=lambda:callback)
            runtime.start_yolo_warmup(worker=lambda:lambda *_:None)
            self.assertFalse(runtime.close(0));callback.assert_not_called()
        finally:
            release.set()
            if threads:self.wait(threads[0]._started);self.join(threads[0])
        self.assertTrue(runtime.close(3));callback.assert_not_called()

    def test_self_close_reports_undrained_without_deadlock(self):
        runtime=owner();done=threading.Event();results=[]
        def work(*_):results.append(runtime.close(1));done.set()
        runtime.start_yolo_warmup(worker=lambda:work);self.wait(done)
        self.assertEqual(results,[False]);self.assertTrue(runtime.close(3))

    def test_other_owner_survives_close_and_enabled_gate_stays_unchanged(self):
        a,b=owner(),owner();done=threading.Event();self.assertTrue(a.close(0))
        b.start_yolo_warmup(worker=lambda:lambda *_:done.set());self.wait(done);self.assertTrue(b.close(3))
        disabled=owner();disabled.operations=WarmupOperations(lambda:False,*list(disabled.operations.__dict__.values())[1:])
        provider=Mock();disabled.start_yolo_warmup(worker=provider);provider.assert_not_called()
        self.assertEqual(disabled.state['status'],'disabled');self.assertTrue(disabled.close(0))


if __name__=='__main__':unittest.main()

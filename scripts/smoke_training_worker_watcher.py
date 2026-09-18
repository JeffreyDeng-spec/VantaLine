"""Disabled watcher lifecycle and bounded loop contracts with fake timing and dependencies."""
from contextlib import ExitStack
import io
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, call, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


class StopLoop(BaseException):pass


def _capture_watcher_report(ns,mode):
 events=[];tick=ValueError('original tick');stop=StopLoop('end');stderr=io.StringIO();reports=[]
 def called(label):
  def fn(**kwargs):reports.append((sys.exc_info()[1],kwargs));events.append(label)
  return fn
 a,b,c=called('A'),called('B'),called('C');trace=types.SimpleNamespace(print_exc=a)
 class Stderr:
  @property
  def stderr(self):events.append('argument');trace.print_exc=c;return stderr
 def watch():events.append('prior');trace.print_exc=a if mode=='ordinary' else b if mode=='prior' else None;raise tick
 def sleep(seconds):events.append('sleep');assert seconds==7.5;raise stop
 ns.update(sys=Stderr(),traceback=trace,time=types.SimpleNamespace(sleep=sleep),worker_training_watcher_interval_seconds=lambda:7.5,_worker_training_watch_once=watch)
 caught=None
 try:ns['_worker_training_watcher_loop']()
 except BaseException as error:caught=error
 if mode=='missing':
  assert type(caught)is TypeError,(caught,events);assert caught.__context__ is tick;assert reports==[]
  assert events==['prior','argument'],events
 else:
  assert caught is stop,(caught,events);assert reports==[(tick,{'file':stderr})]
  assert events==['prior','argument','A' if mode=='ordinary' else 'B','sleep'],events
 return events


class WatcherFixture:
    def __init__(self):
        self.events=[];self.error=StopLoop('fixture end');self.stderr=io.StringIO();self.interval=Mock(side_effect=lambda:self.event('interval') or 7.5)
        self.watch=Mock(side_effect=lambda:self.event('watch') or {'ignored':True})
        self.sleep=Mock(side_effect=self.stop);self.report=Mock(side_effect=lambda **kwargs:self.event('report'))
    def event(self,name):self.events.append(name)
    def stop(self,seconds):self.event('sleep');raise self.error
    def bind(self,api,stack):
        stack.enter_context(patch.object(api,'worker_training_watcher_interval_seconds',self.interval));stack.enter_context(patch.object(api,'_worker_training_watch_once',self.watch))
        stack.enter_context(patch('time.sleep',self.sleep));stack.enter_context(patch('traceback.print_exc',self.report));stack.enter_context(patch.object(sys,'stderr',self.stderr))


class TrainingWorkerWatcherContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ);cls.environment.start();cls.runtime=tempfile.TemporaryDirectory(prefix='worker-watcher-root-')
        root=Path(cls.runtime.name);(root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server;cls.interval_fn=staticmethod(server.worker_training_watcher_interval_seconds);cls.once_fn=staticmethod(server._worker_training_watch_once)
    @classmethod
    def tearDownClass(cls):cls.runtime.cleanup();cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close);self.f=WatcherFixture();self.f.bind(self.api,self.stack)
        for target in ['requests.request','requests.get','requests.post','subprocess.Popen','os.kill','threading.Thread','threading.Event']:
            self.stack.enter_context(patch(target,side_effect=AssertionError('unexpected operation')))
    def loop(self):return self.api._worker_training_watcher_loop()
    def test_retired_entry_points_and_registered_startup_remain_noops(self):
        from fastapi import FastAPI
        f=self.f;handler=self.api.start_worker_training_watcher
        handlers=[fn for fn in self.api.app.router.on_startup if fn.__name__=='start_worker_training_watcher'];self.assertEqual(handlers,[handler])
        self.assertIs(self.api.worker_training_watcher_enabled(),False);self.assertEqual(self.once_fn(),0)
        with patch.object(self.api,'worker_training_watcher_enabled',return_value=True) as enabled,patch.object(self.api,'_worker_training_watcher_loop',side_effect=AssertionError('must stay disabled')) as loop:
            for unused in range(2):
                self.assertIsNone(handler());app=FastAPI();app.router.add_event_handler('startup',handler);lifecycle=app.router.lifespan_context(app)
                with self.assertRaises(StopIteration):lifecycle.__aenter__().send(None)
                with self.assertRaises(StopIteration):lifecycle.__aexit__(None,None,None).send(None)
                self.assertEqual(app.router.on_startup,[handler])
            enabled.assert_not_called();loop.assert_not_called()
        self.assertEqual([fn for fn in self.api.app.router.on_startup if fn.__name__=='start_worker_training_watcher'],handlers)
        for callback in [f.interval,f.watch,f.sleep,f.report]:callback.assert_not_called()
    def test_interval_default_clamp_and_nonfinite_values(self):
        key='INSPECTION_WORKER_WATCHER_INTERVAL_SECONDS'
        cases=[({},20),({key:''},20),({key:0},20),({key:'0'},5),({key:' '},20),({key:'bad'},20),({key:4.9},5),({key:5},5),({key:5.1},5.1),({key:599.9},599.9),({key:600},600),({key:600.1},600),({key:'nan'},600),({key:'inf'},600),({key:'-inf'},5),({key:[]},20),({key:[1]},20)]
        for values,expected in cases:
            getter=Mock(wraps=values.get);environment=Mock();environment.get=getter
            with patch.object(os,'environ',environment):self.assertEqual(self.interval_fn(),expected)
            getter.assert_called_once_with(key,'')
    def test_interval_catches_only_type_and_value_errors_without_retry(self):
        for kind,expected in [(TypeError,20),(ValueError,20),(OverflowError,None),(RuntimeError,None),(KeyboardInterrupt,None)]:
            error=kind('environment read');environment=Mock();environment.get.side_effect=[error,'30']
            with patch.object(os,'environ',environment):
                if expected is not None:self.assertEqual(self.interval_fn(),expected)
                else:
                    with self.assertRaises(kind) as caught:self.interval_fn()
                    self.assertIs(caught.exception,error)
            environment.get.assert_called_once()
    def test_loop_success_order_and_ignores_tick_return_value(self):
        f=self.f;f.watch.side_effect=lambda:f.event('watch') or 0;f.sleep.side_effect=[None,f.error]
        with self.assertRaises(StopLoop) as caught:self.loop()
        self.assertIs(caught.exception,f.error);self.assertEqual(f.events,['interval','watch','watch']);f.interval.assert_called_once_with();self.assertEqual(f.watch.call_count,2)
        self.assertEqual(f.sleep.call_args_list,[call(7.5),call(7.5)]);f.report.assert_not_called()
    def test_interval_failure_precedes_loop_and_all_other_dependencies(self):
        f=self.f;error=ValueError('interval');f.interval.side_effect=lambda:error_once()
        hits=[]
        def error_once():
            hits.append(1)
            if len(hits)==1:raise error
            return 5
        with self.assertRaises(BaseException) as caught:self.loop()
        self.assertIs(caught.exception,error);f.interval.assert_called_once();f.watch.assert_not_called();f.report.assert_not_called();f.sleep.assert_not_called()
    def test_watch_exception_reports_original_exception_before_sleep_and_continues(self):
        f=self.f;error=ValueError('tick failed');hits=[];reported=[];sleeps=[]
        def watch():
            hits.append(True);f.event('watch')
            if len(hits)==1:raise error
            return None
        def report(**kwargs):reported.append((sys.exc_info()[1],kwargs));f.event('report')
        def sleep(seconds):
            sleeps.append(seconds);f.event('sleep')
            if len(sleeps)==2:raise f.error
        f.watch.side_effect=watch;f.report.side_effect=report;f.sleep.side_effect=sleep
        with self.assertRaises(StopLoop) as caught:self.loop()
        self.assertIs(caught.exception,f.error);self.assertEqual(f.events,['interval','watch','report','sleep','watch','sleep'])
        self.assertEqual(reported,[(error,{'file':f.stderr})]);self.assertEqual(sleeps,[7.5,7.5]);f.interval.assert_called_once()
    def test_report_failure_propagates_before_sleep_without_retry(self):
        f=self.f;tick=ValueError('tick');error=OSError('report');f.watch.side_effect=tick;hits=[]
        def report(**kwargs):
            hits.append(1)
            if len(hits)==1:raise error
        f.report.side_effect=report
        with self.assertRaises(BaseException) as caught:self.loop()
        self.assertIs(caught.exception,error);self.assertIs(caught.exception.__context__,tick);f.watch.assert_called_once();f.report.assert_called_once_with(file=f.stderr);f.sleep.assert_not_called()
    def test_sleep_failure_is_not_reported_or_retried(self):
        f=self.f;error=ValueError('sleep');hits=[]
        def sleep(seconds):
            hits.append(1)
            if len(hits)==1:raise error
        f.sleep.side_effect=sleep
        watches=[]
        def watch():
            watches.append(1)
            if len(watches)>1:raise f.error
        f.watch.side_effect=watch
        with self.assertRaises(BaseException) as caught:self.loop()
        self.assertIs(caught.exception,error);f.watch.assert_called_once();f.sleep.assert_called_once_with(7.5);f.report.assert_not_called()
    def test_watch_baseexception_is_not_reported_or_followed_by_sleep(self):
        f=self.f;error=KeyboardInterrupt('tick');f.watch.side_effect=[error,0]
        with self.assertRaises(BaseException) as caught:self.loop()
        self.assertIs(caught.exception,error);f.watch.assert_called_once();f.report.assert_not_called();f.sleep.assert_not_called()
    def test_each_iteration_uses_late_watch_and_sleep_but_fixed_interval(self):
        f=self.f;late_interval=Mock(side_effect=AssertionError('interval must stay fixed'));late_watch=Mock(side_effect=lambda:f.event('late-watch'))
        late_sleep=Mock(side_effect=f.stop)
        def first():
            f.event('watch');self.api._worker_training_watch_once=late_watch;self.api.worker_training_watcher_interval_seconds=late_interval
        def first_sleep(seconds):f.event('first-sleep');self.api.time.sleep=late_sleep
        f.watch.side_effect=first;f.sleep.side_effect=first_sleep
        with self.assertRaises(StopLoop) as caught:self.loop()
        self.assertIs(caught.exception,f.error);self.assertEqual(f.events,['interval','watch','first-sleep','late-watch','sleep'])
        f.interval.assert_called_once();late_interval.assert_not_called();f.watch.assert_called_once();late_watch.assert_called_once();f.sleep.assert_called_once_with(7.5);late_sleep.assert_called_once_with(7.5)
    def test_report_uses_latest_traceback_and_stderr_during_original_exception(self):
        f=self.f;error=ValueError('tick');late_stderr=io.StringIO();seen=[]
        late_report=Mock(side_effect=lambda **kwargs:seen.append((sys.exc_info()[1],kwargs)))
        def watch():self.api.traceback.print_exc=late_report;self.api.sys.stderr=late_stderr;raise error
        f.watch.side_effect=watch
        with self.assertRaises(StopLoop):self.loop()
        self.assertEqual(seen,[(error,{'file':late_stderr})]);f.report.assert_not_called();late_report.assert_called_once();f.sleep.assert_called_once_with(7.5)


    def test_independent_settings_and_loops_without_constructor_reads_or_root_dependencies(self):
        from local_inspection_service.training.worker_watcher import WorkerWatcherSettings, WorkerWatcherLoop
        key='INSPECTION_WORKER_WATCHER_INTERVAL_SECONDS';instances=[]
        for index,owner in enumerate(['alice','bob']):
            environment={key:str(8+index)};events=[];state={'ticks':0,'sleeps':0};error=ValueError(owner);stop=StopLoop(owner)
            read=Mock(side_effect=lambda environment=environment:environment);settings=WorkerWatcherSettings(read);interval=Mock(side_effect=settings.worker_training_watcher_interval_seconds)
            def watch(state=state,events=events,environment=environment,error=error,stop=stop):
                state['ticks']+=1;events.append('watch')
                if state['ticks']==1:environment[key]=str(float(environment[key])+100);raise error
                if state['ticks']>2:raise stop
                return {'ignored':True}
            def report(events=events,error=error):self.assertIs(sys.exc_info()[1],error);events.append('report')
            def sleep(seconds,state=state,events=events,stop=stop):
                state['sleeps']+=1;events.append(('sleep',seconds))
                if state['sleeps']>=2:raise stop
            tick=Mock(side_effect=watch);reporter=Mock(side_effect=report);sleeper=Mock(side_effect=sleep);loop=WorkerWatcherLoop(interval,tick,reporter,sleeper)
            for callback in [read,interval,tick,reporter,sleeper]:callback.assert_not_called()
            self.assertEqual(events,[]);instances.append((environment,events,state,stop,read,interval,tick,reporter,sleeper,loop))
        for name in ['worker_training_watcher_interval_seconds','_worker_training_watch_once','_worker_training_watcher_loop']:
            self.stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('unexpected root dependency')))
        for name in ['time.sleep','traceback.print_exc']:self.stack.enter_context(patch(name,side_effect=AssertionError('unexpected global capability')))
        for index in [1,0,1,0]:
            environment,events,state,stop,read,interval,tick,reporter,sleeper,loop=instances[index];state.update(ticks=0,sleeps=0);events.clear();seconds=float(environment[key])
            with self.assertRaises(StopLoop) as caught:loop._worker_training_watcher_loop()
            self.assertIs(caught.exception,stop);self.assertEqual(events,['watch','report',('sleep',seconds),'watch',('sleep',seconds)])
        for environment,events,state,stop,read,interval,tick,reporter,sleeper,loop in instances:
            self.assertEqual(read.call_count,2);self.assertEqual(interval.call_count,2);self.assertEqual(tick.call_count,4);self.assertEqual(reporter.call_count,2);self.assertEqual(sleeper.call_count,4)


    def test_environment_provider_failure_has_original_fallback_without_retry(self):
        from local_inspection_service.training.worker_watcher import WorkerWatcherSettings
        for kind in [TypeError,ValueError,RuntimeError,OverflowError,KeyboardInterrupt]:
            with self.subTest(kind=kind):
                error=kind('provider');hits=[]
                def provider():
                    hits.append(1)
                    if len(hits)==1:raise error
                    return {'INSPECTION_WORKER_WATCHER_INTERVAL_SECONDS':'30'}
                obj=WorkerWatcherSettings(provider)
                if kind in [TypeError,ValueError]:self.assertEqual(obj.worker_training_watcher_interval_seconds(),20)
                else:
                    with self.assertRaises(BaseException) as caught:obj.worker_training_watcher_interval_seconds()
                    self.assertIs(caught.exception,error)
                self.assertEqual(hits,[1])


    def test_report_target_is_selected_before_stderr_read_with_original_exception(self):
        for mode in ('ordinary','prior','missing'):
            with self.subTest(mode=mode),patch.dict(self.api.__dict__):
                _capture_watcher_report(self.api.__dict__,mode)


if __name__=='__main__':unittest.main()

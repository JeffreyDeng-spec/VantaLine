"""Native pipeline thread ownership with synthetic callbacks and repository scopes."""
from contextlib import contextmanager, nullcontext
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.pipeline.advance_runtime import PipelineAdvanceRuntime
from local_inspection_service.pipeline.auto_agent_runtime import PipelineAutoAgentRuntime
from local_inspection_service.pipeline.recommendation_runtime import PipelineRecommendationRuntime
from local_inspection_service.runtime.training_tasks import TrainingRuntimeClosed

KINDS = ('advance', 'auto_agent', 'recommendation')


def fixture(kind, runner, scope=nullcontext, thread=threading.Thread):
    lock, inflight, cancel = threading.RLock(), set(), {}
    scheduling = SimpleNamespace(lock=lambda:lock, registry_lock=lambda:lock,
        inflight=lambda:inflight, cancel_events=lambda:cancel, event=lambda:threading.Event,
        thread=lambda:thread, runner=lambda:runner)
    if kind == 'advance':
        owner = PipelineAdvanceRuntime(None,None,None,scheduling,scope=scope)
        schedule = lambda identity='task',user=None: owner.schedule(identity,user)
    elif kind == 'auto_agent':
        owner = PipelineAutoAgentRuntime(None,None,None,scheduling,scope=scope)
        schedule = lambda identity='task',user=None: owner.schedule([identity],user)
    else:
        owner = PipelineRecommendationRuntime(None,None,scheduling,scope=scope)
        schedule = lambda identity='task',user=None: owner.schedule([(identity,'samples')],user)
    return owner, schedule, inflight, cancel


class PipelineDrainTests(unittest.TestCase):
    def test_closing_rejects_before_registry_or_thread_side_effects(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                poison=Mock(side_effect=AssertionError('post-close side effect'))
                owner,schedule,inflight,cancel=fixture(kind,poison,thread=poison)
                self.assertTrue(owner.close(0))
                with self.assertRaises(TrainingRuntimeClosed): schedule()
                self.assertEqual(inflight,set());self.assertEqual(cancel,{})
                poison.assert_not_called()

    def test_handle_is_owned_through_same_thread_scope_exit(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                entered,release=threading.Event(),threading.Event();events=[];user={'id':'synthetic'}
                @contextmanager
                def scope():
                    events.append(('enter',threading.get_ident()))
                    try: yield
                    finally:
                        events.append(('cleanup',threading.get_ident()));entered.set()
                        release.wait(3);events.append(('exit',threading.get_ident()))
                owner,schedule,_,_=fixture(kind,lambda *args:events.append(('call',threading.get_ident(),args)),scope)
                try:
                    schedule(user=user);self.assertTrue(entered.wait(2));self.assertFalse(owner.close(.01))
                    self.assertEqual([e[0] for e in events],['enter','call','cleanup'])
                finally: release.set();self.assertTrue(owner.close(2))
                self.assertEqual([e[0] for e in events],['enter','call','cleanup','exit'])
                self.assertEqual(len({e[1] for e in events}),1)
                self.assertNotEqual(events[0][1],threading.get_ident())
                self.assertIs(events[1][2][-1],user)
                self.assertEqual(events[1][2][0],'task')

    def test_pending_constructor_crossing_close_remains_admitted(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                constructing,release=threading.Event(),threading.Event();calls=[];errors=[]
                def create(**kwargs):
                    constructing.set();release.wait(3);return threading.Thread(**kwargs)
                owner,schedule,_,_=fixture(kind,lambda *args:calls.append(args),thread=create)
                def submit():
                    try: schedule()
                    except BaseException as exc: errors.append(exc)
                caller=threading.Thread(target=submit);caller.start()
                try:
                    self.assertTrue(constructing.wait(2));self.assertFalse(owner.close(.01))
                finally: release.set();caller.join(2)
                self.assertFalse(caller.is_alive());self.assertTrue(owner.close(2))
                self.assertEqual(errors,[]);self.assertEqual(len(calls),1)

    def test_constructor_failure_retains_original_registry_evidence(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                failure=RuntimeError('synthetic constructor');target=Mock()
                owner,schedule,inflight,cancel=fixture(kind,target,thread=Mock(side_effect=failure))
                with self.assertRaises(RuntimeError) as caught:schedule()
                self.assertIs(caught.exception,failure);self.assertTrue(owner.close(0));target.assert_not_called()
                self.assertEqual(inflight,{'task|samples' if kind=='recommendation' else 'task'})
                self.assertEqual(set(cancel),{'task'} if kind=='advance' else set())

    def test_post_start_error_does_not_lose_running_handle(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                entered,release=threading.Event(),threading.Event();failure=RuntimeError('after native start')
                class PostStart(threading.Thread):
                    def start(self):
                        super().start()
                        if not entered.wait(2):raise AssertionError('target did not enter')
                        raise failure
                def target(*_):entered.set();release.wait(3)
                owner,schedule,_,_=fixture(kind,target,thread=PostStart)
                try:
                    with self.assertRaises(RuntimeError) as caught:schedule()
                    self.assertIs(caught.exception,failure);self.assertFalse(owner.close(.01))
                finally:release.set();self.assertTrue(owner.close(2))

    def test_original_duplicate_gate_and_independent_owners(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                calls=[]
                a,submit_a,_,_=fixture(kind,lambda *args:calls.append(('a',args)))
                b,submit_b,_,_=fixture(kind,lambda *args:calls.append(('b',args)))
                submit_a();submit_a();self.assertTrue(a.close(2))
                submit_b();self.assertTrue(b.close(2))
                self.assertEqual(sorted(x[0] for x in calls),['a','b'])

    def test_target_exception_still_finishes_scope_and_does_not_retry(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                calls=[];failure=RuntimeError('synthetic target');errors=[]
                @contextmanager
                def scope():
                    try:yield
                    except RuntimeError as exc:errors.append(exc)
                    finally:calls.append('cleanup')
                def target(*_):calls.append('target');raise failure
                owner,schedule,_,_=fixture(kind,target,scope)
                schedule();self.assertTrue(owner.close(2))
                self.assertEqual(calls,['target','cleanup']);self.assertEqual(errors,[failure])


    def test_admitted_batch_finishes_preparation_across_close(self):
        for kind in ('auto_agent', 'recommendation'):
            with self.subTest(kind=kind):
                first_entered, second_constructing = threading.Event(), threading.Event()
                release_first, release_constructor = threading.Event(), threading.Event()
                calls, errors = [], []
                def target(*args):
                    calls.append(args[0])
                    if args[0] == 'first':
                        first_entered.set(); release_first.wait(3)
                def create(**kwargs):
                    if kwargs['args'][0] == 'second':
                        second_constructing.set(); release_constructor.wait(3)
                    return threading.Thread(**kwargs)
                owner, schedule, inflight, _ = fixture(kind, target, thread=create)
                items = ['first', 'second', 'third']
                if kind == 'recommendation': items = [(item, 'samples') for item in items]
                def submit():
                    try: owner.schedule(items, None)
                    except BaseException as exc: errors.append(exc)
                caller = threading.Thread(target=submit); caller.start()
                try:
                    self.assertTrue(first_entered.wait(2)); self.assertTrue(second_constructing.wait(2))
                    self.assertFalse(owner.close(.01))
                    with self.assertRaises(TrainingRuntimeClosed): schedule('new')
                    release_constructor.set(); caller.join(2)
                    self.assertFalse(caller.is_alive()); self.assertEqual(errors, [])
                    self.assertFalse(owner.close(.01))
                finally:
                    release_constructor.set(); release_first.set(); caller.join(2)
                    self.assertTrue(owner.close(2))
                self.assertCountEqual(calls, ['first', 'second', 'third'])
                self.assertEqual(inflight, {x + ('|samples' if kind == 'recommendation' else '')
                                            for x in ['first', 'second', 'third']})

    def test_later_batch_failure_retains_earlier_thread_and_partial_registry(self):
        for kind in ('auto_agent', 'recommendation'):
            for failure_point in ('constructor', 'after_start'):
                with self.subTest(kind=kind, failure_point=failure_point):
                    first_entered, second_entered, release = threading.Event(), threading.Event(), threading.Event()
                    calls = []; failure = RuntimeError('synthetic later batch failure')
                    def target(*args):
                        calls.append(args[0])
                        (first_entered if args[0] == 'first' else second_entered).set()
                        release.wait(3)
                    class PostStart(threading.Thread):
                        def start(self):
                            super().start()
                            if not second_entered.wait(2): raise AssertionError('second did not enter')
                            raise failure
                    def create(**kwargs):
                        if kwargs['args'][0] == 'first': return threading.Thread(**kwargs)
                        if not first_entered.wait(2): raise AssertionError('first did not enter')
                        if failure_point == 'constructor': raise failure
                        return PostStart(**kwargs)
                    owner, schedule, inflight, _ = fixture(kind, target, thread=create)
                    items = ['first', 'second', 'third']
                    if kind == 'recommendation': items = [(item, 'samples') for item in items]
                    try:
                        with self.assertRaises(RuntimeError) as caught: owner.schedule(items, None)
                        self.assertIs(caught.exception, failure)
                        self.assertFalse(owner.close(.01))
                        with self.assertRaises(TrainingRuntimeClosed): schedule('new')
                    finally: release.set(); self.assertTrue(owner.close(2))
                    self.assertCountEqual(calls, ['first'] if failure_point == 'constructor' else ['first', 'second'])
                    self.assertEqual(inflight, {x + ('|samples' if kind == 'recommendation' else '')
                                                for x in ['first', 'second']})

    def test_scope_failure_distinguishes_thread_completion_from_business_cleanup(self):
        for kind in KINDS:
            for failure_point in ('enter', 'exit'):
                with self.subTest(kind=kind, failure_point=failure_point):
                    calls, errors = [], []; failure = RuntimeError('synthetic scope failure')
                    @contextmanager
                    def scope():
                        calls.append('enter')
                        if failure_point == 'enter': raise failure
                        try: yield
                        finally: calls.append('exit'); raise failure
                    def target(*args):
                        calls.append('target')
                        inflight.discard('task|samples' if kind == 'recommendation' else 'task')
                        cancel.pop('task', None)
                    owner, schedule, inflight, cancel = fixture(kind, target, scope)
                    with patch('threading.excepthook', lambda args: errors.append(args.exc_value)):
                        schedule(); self.assertTrue(owner.close(2))
                    self.assertEqual(errors, [failure])
                    self.assertEqual(calls, ['enter'] if failure_point == 'enter' else ['enter', 'target', 'exit'])
                    self.assertEqual(inflight, {'task|samples' if kind == 'recommendation' else 'task'}
                                     if failure_point == 'enter' else set())
                    self.assertEqual(set(cancel), {'task'} if kind == 'advance' and failure_point == 'enter' else set())



if __name__=='__main__':unittest.main()

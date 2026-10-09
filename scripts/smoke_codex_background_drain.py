"""Bounded Codex background thread ownership, synthetic targets only."""
from contextlib import contextmanager
from pathlib import Path
import sys,threading,unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.training.background_codex import CodexBackgroundThread
from local_inspection_service.runtime.training_tasks import TrainingThreadLifecycle,TrainingRuntimeClosed

class Drain(unittest.TestCase):
    def test_close_before_start_prevents_all_dependency_resolution(self):
        callback=Mock();service=CodexBackgroundThread(callback,callback,callback)
        self.assertTrue(service.close(0))
        with self.assertRaises(TrainingRuntimeClosed):service.start_codex_background_generation(Path('source'),Path('set'),'id')
        callback.assert_not_called()

    def test_captures_original_target_before_name_and_retains_argument_identity(self):
        selected=Mock();replacement=Mock();current=[selected];captured=[]
        class Deferred:
            def __init__(self,**kwargs):captured.append(kwargs)
            def start(self):pass
        def name(value):current[0]=replacement;return 'safe'
        service=CodexBackgroundThread(lambda:Deferred,lambda:current[0],name)
        source=Path('s');directory=Path('d');service.start_codex_background_generation(source,directory,'raw',3)
        call=captured[0];self.assertEqual(call['name'],'codex-background-worker-safe');self.assertTrue(call['daemon'])
        call['target'](*call['args']);selected.assert_called_once_with(source,directory,'raw',3);replacement.assert_not_called()
        self.assertIs(selected.call_args.args[0],source);self.assertIs(selected.call_args.args[1],directory)

    def test_scope_cleanup_and_native_thread_exit_are_owned(self):
        entered,release=threading.Event(),threading.Event();events=[]
        @contextmanager
        def scope():
            events.append(('scope',threading.get_ident()))
            try:yield
            finally:events.append(('cleanup',threading.get_ident()));entered.set();release.wait(3)
        service=CodexBackgroundThread(lambda:threading.Thread,lambda:lambda *_:events.append(('work',threading.get_ident())),str,runtime=TrainingThreadLifecycle(scope=scope))
        service.start_codex_background_generation(Path('s'),Path('d'),'id')
        try:self.assertTrue(entered.wait(3));self.assertFalse(service.close(0))
        finally:release.set();self.assertTrue(service.close(3))
        self.assertEqual([e[0] for e in events],['scope','work','cleanup']);self.assertEqual(len({e[1] for e in events}),1)

    def test_admitted_factory_finishes_after_close_without_losing_handle(self):
        constructing,release,running,finish=[threading.Event() for _ in range(4)];errors=[]
        def factory(**kwargs):constructing.set();release.wait(3);return threading.Thread(**kwargs)
        def work(*_):running.set();finish.wait(3)
        service=CodexBackgroundThread(lambda:factory,lambda:work,str)
        def start():
            try:service.start_codex_background_generation(Path('s'),Path('d'),'id')
            except BaseException as exc:errors.append(exc)
        caller=threading.Thread(target=start);caller.start()
        try:
            self.assertTrue(constructing.wait(3));self.assertFalse(service.close(0))
            release.set();self.assertTrue(running.wait(3));self.assertFalse(service.close(0))
        finally:release.set();finish.set();caller.join(3);self.assertTrue(service.close(3))
        self.assertFalse(caller.is_alive());self.assertEqual(errors,[])

    def test_separate_owners_and_target_error_preserve_cleanup(self):
        first=CodexBackgroundThread(lambda:threading.Thread,lambda:Mock(),str);self.assertTrue(first.close(0))
        errors=[];released=[]
        @contextmanager
        def scope():
            try:yield
            finally:released.append(True)
        def failed(*_):raise LookupError('unknown outcome')
        other=CodexBackgroundThread(lambda:threading.Thread,lambda:failed,str,runtime=TrainingThreadLifecycle(scope=scope))
        original=threading.excepthook
        try:
            threading.excepthook=lambda args:errors.append(args.exc_value)
            other.start_codex_background_generation(Path('s'),Path('d'),'id');self.assertTrue(other.close(3))
        finally:threading.excepthook=original
        self.assertEqual(released,[True]);self.assertEqual(str(errors[0]),'unknown outcome')

if __name__=='__main__':unittest.main()

"""Real PDF consumer ownership with synthetic repositories and rendering."""
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.storage.artifacts.runtime import get_runtime
from fastapi import FastAPI
from local_inspection_service.label_inspection import pdf_import as pdf
from local_inspection_service.label_inspection.dependencies import RepositoryLifecycle
from local_inspection_service.runtime.training_tasks import TrainingRuntimeClosed
REAL_THREAD = threading.Thread


class PdfDrain(unittest.TestCase):
    def test_repeated_startup_owns_one_thread_and_closed_owner_rejects_restart(self):
        app = FastAPI(); threads = []; cleared = threading.Event()
        owner = pdf.register(app, RepositoryLifecycle(lambda: None, cleared.set), lambda: Path('.'), runtime_provider=get_runtime)
        def factory(**kwargs):
            thread = REAL_THREAD(**kwargs); threads.append(thread); return thread
        with patch.object(pdf.threading, 'Thread', factory):
            app.router.on_startup[0](); app.router.on_startup[0]()
            self.assertTrue(cleared.wait(3)); self.assertTrue(owner.close(3))
        self.assertIs(app.state.label_pdf_import, owner)
        self.assertEqual(len(threads), 1); self.assertFalse(threads[0].is_alive())
        self.assertEqual(threads[0].name, 'pdf-import'); self.assertTrue(threads[0].daemon)
        with self.assertRaises(TrainingRuntimeClosed): app.router.on_startup[0]()

    def test_close_waits_for_process_and_same_thread_repository_cleanup(self):
        app = FastAPI(); processing, processed = threading.Event(), threading.Event()
        clearing, cleared = threading.Event(), threading.Event(); calls = []; ids = []
        task = {'id': 'synthetic'}
        def claim(token): calls.append(token); ids.append(threading.get_ident()); return task
        def process(repo, media, selected, token):
            self.assertIs(selected, task); self.assertEqual(token, calls[0])
            processing.set(); processed.wait(3)
        def clear(): ids.append(threading.get_ident()); clearing.set(); cleared.wait(3)
        owner = pdf.register(app, RepositoryLifecycle(lambda: SimpleNamespace(claim_pdf=claim), clear), lambda: Path('.'), runtime_provider=get_runtime)
        with patch.object(pdf, 'LabelRepository', side_effect=lambda raw: raw), patch.object(pdf, 'process', process), \
             patch.object(pdf, 'MediaStore', return_value=object()):
            app.router.on_startup[0]()
            try:
                self.assertTrue(processing.wait(3)); app.router.on_shutdown[0]()
                self.assertTrue(owner.stop.is_set()); self.assertFalse(owner.close(0))
                processed.set(); self.assertTrue(clearing.wait(3)); self.assertFalse(owner.close(0))
            finally: processed.set(); cleared.set(); self.assertTrue(owner.close(3))
        self.assertEqual(len(calls), 1); self.assertEqual(ids[0], ids[1])
        self.assertNotEqual(ids[0], threading.get_ident())

    def test_pending_constructor_observes_stop_and_cannot_escape_join(self):
        app = FastAPI(); entered, release = threading.Event(), threading.Event(); errors = []; threads = []
        repository = Mock(); clear = Mock()
        owner = pdf.register(app, RepositoryLifecycle(repository, clear), lambda: Path('.'), runtime_provider=get_runtime)
        def factory(**kwargs):
            entered.set(); release.wait(3); thread = REAL_THREAD(**kwargs); threads.append(thread); return thread
        def caller():
            try: app.router.on_startup[0]()
            except BaseException as error: errors.append(error)
        with patch.object(pdf.threading, 'Thread', factory):
            starter = REAL_THREAD(target=caller); starter.start()
            try: self.assertTrue(entered.wait(3)); self.assertFalse(owner.close(0))
            finally: release.set(); starter.join(3); self.assertTrue(owner.close(3))
        self.assertFalse(starter.is_alive()); self.assertEqual(errors, [])
        self.assertFalse(threads[0].is_alive()); repository.assert_not_called(); clear.assert_not_called()

    def test_interrupted_native_bootstrap_retains_uncertain_handle(self):
        entered, release = threading.Event(), threading.Event(); target = Mock(); threads = []; outer = self
        owner = pdf.PdfImportRuntime()
        class Interrupted(REAL_THREAD):
            def _bootstrap_inner(self): entered.set(); release.wait(3); super()._bootstrap_inner()
            def start(self):
                original = self._started.wait
                def interrupt(*args, **kwargs):
                    outer.assertTrue(entered.wait(3)); raise KeyboardInterrupt('bootstrap')
                self._started.wait = interrupt
                try: super().start()
                finally: self._started.wait = original
        def factory(**kwargs):
            thread = Interrupted(**kwargs); threads.append(thread); return thread
        try:
            with patch.object(pdf.threading, 'Thread', factory), self.assertRaises(KeyboardInterrupt): owner.start(target)
            self.assertFalse(owner.close(0))
        finally:
            release.set()
            if threads: self.assertTrue(threads[0]._started.wait(3)); threads[0].join(3)
        self.assertTrue(owner.close(3)); target.assert_not_called()

    def test_post_start_error_keeps_live_target_owned_without_duplicate_start(self):
        entered, release = threading.Event(), threading.Event(); calls = []; error = RuntimeError('start')
        owner = pdf.PdfImportRuntime()
        def target(): calls.append(1); entered.set(); release.wait(3)
        class Started(REAL_THREAD):
            def start(self):
                super().start(); assert entered.wait(3); raise error
        try:
            with patch.object(pdf.threading, 'Thread', Started):
                with self.assertRaises(RuntimeError) as caught: owner.start(target)
                self.assertIs(caught.exception, error); owner.start(target)
            self.assertFalse(owner.close(0))
        finally: release.set(); self.assertTrue(owner.close(3))
        self.assertEqual(calls, [1])

    def test_constructor_failure_does_not_retry_and_no_handle_needs_join(self):
        owner = pdf.PdfImportRuntime(); target = Mock(); error = ValueError('constructor')
        with patch.object(pdf.threading, 'Thread', side_effect=error) as constructor:
            with self.assertRaises(ValueError) as caught: owner.start(target)
            self.assertIs(caught.exception, error); owner.start(target); constructor.assert_called_once()
        self.assertTrue(owner.close(0)); target.assert_not_called()

    def test_independent_owners_and_concurrent_startup(self):
        first, second = pdf.PdfImportRuntime(), pdf.PdfImportRuntime(); calls = []; entered = threading.Event()
        def target(): calls.append(1); entered.set(); second.stop.wait(3)
        starters = [REAL_THREAD(target=lambda: second.start(target)) for _ in range(4)]
        try:
            for thread in starters: thread.start()
            for thread in starters: thread.join(3); self.assertFalse(thread.is_alive())
            self.assertTrue(entered.wait(3)); self.assertTrue(first.close(0)); self.assertFalse(second.stop.is_set())
            self.assertEqual(calls, [1])
        finally: self.assertTrue(second.close(3))


if __name__ == '__main__': unittest.main()

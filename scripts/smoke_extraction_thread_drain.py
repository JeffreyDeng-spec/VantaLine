"""Extraction owner shutdown with native threads and synthetic providers only."""
import asyncio
from contextlib import contextmanager
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import smoke_extraction_dependencies as retained
from local_inspection_service.text_inspection import extraction_api as api
from local_inspection_service.runtime.training_tasks import TrainingThreadLifecycle, TrainingRuntimeClosed
REAL_THREAD = threading.Thread


class Drain(unittest.TestCase):
    def fixture(self, scope=None):
        runtime = TrainingThreadLifecycle(**({'scope': scope} if scope else {}))
        with patch.object(api, 'TrainingThreadLifecycle', return_value=runtime):
            f = retained.ExtractionContracts.fixture(self, 'drain')
        f.runtime = runtime; f.enabled = True; f.image_config['configured'] = True
        return f

    def submit(self, f, request='owned_job_001', method='ai'):
        class Upload:
            async def read(self, limit): return f.image
        with patch.dict('os.environ', {'VANTALINE_LABEL_EXTRACTION_ACCOUNTS': 'alice'}):
            return asyncio.run(f.endpoint(Upload(), '[0.1,0.1,0.8,0.8]', request, method))

    def test_closed_admission_has_no_new_source_claim_or_model_call(self):
        f = self.fixture(); self.assertTrue(f.runtime.close(0))
        with self.assertRaises(TrainingRuntimeClosed): self.submit(f)
        self.assertEqual(f.writes, []); self.assertEqual(f.data, {}); self.assertEqual(f.calls, [])

    def test_native_worker_retained_until_repository_cleanup_exits(self):
        entered, release = threading.Event(), threading.Event(); ids = []
        @contextmanager
        def scope():
            ids.append(threading.get_ident())
            try: yield
            finally:
                ids.append(threading.get_ident()); entered.set(); release.wait(3)
        f = self.fixture(scope)
        self.submit(f)
        try:
            self.assertTrue(entered.wait(3)); self.assertFalse(f.runtime.close(0))
            self.assertEqual(f.clears, 1)
            self.assertEqual([v[0] for v in f.calls], ['provider', 'image'])
        finally:
            release.set(); self.assertTrue(f.runtime.close(3))
        self.assertEqual(ids[0], ids[1]); self.assertNotEqual(ids[0], threading.get_ident())
        self.assertEqual(next(iter(f.data.values()))['status'], 'uncertain')

    def test_pending_source_write_stays_owned_across_close(self):
        entered, release = threading.Event(), threading.Event(); errors = []
        f = self.fixture(); original = Path.write_bytes
        def blocked(path, data):
            entered.set(); release.wait(3); return original(path, data)
        def caller():
            try: self.submit(f)
            except BaseException as error: errors.append(error)
        with patch.object(Path, 'write_bytes', blocked):
            thread = REAL_THREAD(target=caller); thread.start()
            try:
                self.assertTrue(entered.wait(3)); self.assertFalse(f.runtime.close(0))
            finally:
                release.set(); thread.join(3); self.assertFalse(thread.is_alive())
                self.assertTrue(f.runtime.close(3))
        self.assertEqual(errors, []); self.assertEqual(len(f.calls), 2)

    def test_interrupted_native_bootstrap_retains_claim_without_late_model_call(self):
        entered, release = threading.Event(), threading.Event(); threads = []; outer = self
        f = self.fixture()
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
            with patch.object(threading, 'Thread', factory), self.assertRaises(KeyboardInterrupt): self.submit(f)
            self.assertFalse(f.runtime.close(0)); self.assertEqual(f.calls, [])
            self.assertEqual(next(iter(f.data.values()))['status'], 'attempting')
        finally:
            release.set()
            if threads:
                self.assertTrue(threads[0]._started.wait(3)); threads[0].join(3)
        self.assertTrue(f.runtime.close(3)); self.assertEqual(f.calls, []); self.assertEqual(f.clears, 0)

    def test_constructor_failure_preserves_durable_claim_and_original_exception(self):
        f = self.fixture(); error = ValueError('constructor')
        with patch.object(threading, 'Thread', side_effect=error), self.assertRaises(ValueError) as caught:
            self.submit(f)
        self.assertIs(caught.exception, error); self.assertTrue(f.runtime.close(0))
        self.assertEqual(next(iter(f.data.values()))['status'], 'attempting'); self.assertEqual(f.calls, [])

    def test_independent_owner_manual_and_duplicate_request_semantics(self):
        a, b = self.fixture(), self.fixture(); self.assertTrue(a.runtime.close(0))
        value = self.submit(b, method='manual'); duplicate = self.submit(b, method='manual')
        self.assertEqual(value['id'], duplicate['id']); self.assertEqual(len(b.data), 1)
        self.assertEqual(b.calls, []); self.assertTrue(b.runtime.close(0))
        with self.assertRaises(TrainingRuntimeClosed): self.submit(a)


if __name__ == '__main__': unittest.main()

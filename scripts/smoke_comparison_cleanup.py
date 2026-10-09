"""Fault cleanup must return only acquired comparison slots, never replay work."""
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import smoke_comparison_dependencies as retained
from local_inspection_service.text_inspection import comparison_jobs as local
from local_inspection_service import qwen_evidence_jobs as qwen


class Cleanup(unittest.TestCase):
    def setUp(self):
        network = patch('requests.post', side_effect=AssertionError('network forbidden'))
        network.start(); self.addCleanup(network.stop)

    def assert_available_once(self, slot):
        self.assertTrue(slot.acquire(blocking=False))
        try: self.assertFalse(slot.acquire(blocking=False))
        finally: slot.release()

    def test_single_and_combined_failures_keep_evidence_and_return_capacity(self):
        for use_qwen in (False, True):
            for phase in ('settle', 'clear', 'both'):
                with self.subTest(qwen=use_qwen, phase=phase):
                    f = retained.Fixture(self); slot = threading.BoundedSemaphore(1)
                    settle_error, clear_error = RuntimeError('settlement'), RuntimeError('cleanup')
                    key = '_text_v2_update_attempt' if use_qwen else '_text_v2_save'
                    original = f.namespace[key]; settlement_attempts = []
                    def persist(kind, value, **kwargs):
                        if kind == 'records' and value.get('status') == 'completed':
                            settlement_attempts.append(value['id'])
                            if phase in ('settle', 'both'): raise settle_error
                        return original(kind, value, **kwargs)
                    f.namespace[key] = persist
                    clear = f.clear
                    def cleanup():
                        clear()
                        if phase in ('clear', 'both'): raise clear_error
                    f.namespace['clear_thread_runtime_repository_selection'] = cleanup
                    record = f.submit(qwen_enabled=use_qwen)
                    with patch.object(qwen if use_qwen else local, '_slots', slot), self.assertRaises(RuntimeError) as caught:
                        f.run()
                    self.assertIs(caught.exception, settle_error if phase == 'settle' else clear_error)
                    if phase == 'both': self.assertIs(caught.exception.__context__, settle_error)
                    self.assertEqual(settlement_attempts, [record['id']]); self.assertEqual(f.clears, 1)
                    self.assertEqual(f.store['records', record['id']]['status'], 'completed' if phase == 'clear' else 'attempting')
                    self.assertEqual(len(f.calls), 1 if use_qwen else 0)
                    if use_qwen: self.assertTrue(f.timers[0].cancelled)
                    self.assert_available_once(slot)

    def test_timer_cancel_failure_still_clears_and_returns_capacity(self):
        f = retained.Fixture(self); slot = threading.BoundedSemaphore(1); error = RuntimeError('timer cancel')
        def provider():
            f.timers[0].cancel = Mock(side_effect=error)
        f.provider_hook = provider; record = f.submit(qwen_enabled=True)
        with patch.object(qwen, '_slots', slot), self.assertRaises(RuntimeError) as caught: f.run()
        self.assertIs(caught.exception, error); self.assertEqual(f.clears, 1)
        self.assertEqual(len(f.calls), 1); self.assertEqual(f.store['records', record['id']]['status'], 'completed')
        self.assert_available_once(slot)

    def test_no_acquisition_never_releases_capacity(self):
        for use_qwen in (False, True):
            with self.subTest(qwen=use_qwen):
                f = retained.Fixture(self); slot = Mock(); slot.acquire.return_value = False
                f.submit(qwen_enabled=use_qwen)
                with patch.object(qwen if use_qwen else local, '_slots', slot): f.run()
                slot.release.assert_not_called(); self.assertEqual(f.calls, []); self.assertEqual(f.clears, 1)


if __name__ == '__main__': unittest.main()

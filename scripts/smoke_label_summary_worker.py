"""Optional summary work cannot settle/retry a business run or evade drain."""
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.label_inspection.dependencies import RepositoryLifecycle
from local_inspection_service.label_inspection.worker import LabelWorker
from local_inspection_service.label_inspection import worker as module


class WorkerSummaryContract(unittest.TestCase):
    def make(self, *, stopping=lambda:False):
        self.events=[];self.raw=object()
        self.run={'id':'run','owner_user_id':'alice','profile_snapshot':{'version':1}}
        self.repo=SimpleNamespace(claim=lambda:self.run)
        self.models=SimpleNamespace(resolve=lambda *a:{'api_key':'synthetic'},record_call=lambda *a:None)
        return LabelWorker(RepositoryLifecycle(lambda:self.raw,lambda:self.events.append('clear')),
                           lambda:Path(tempfile.gettempdir()),lambda:self.models,stopping=stopping)

    def test_publication_failure_occurs_after_process_and_never_replays(self):
        service=self.make();calls=[]
        def process(*a,**kw):self.events.append('settled')
        def publish(owner,identity):
            self.events.append('projection');calls.append((owner,identity));raise RuntimeError('synthetic secret')
        with patch.dict('os.environ',{'VANTALINE_LABEL_INSPECTION_ENABLED':'true'}), \
             patch.object(module,'LabelRepository',return_value=self.repo), \
             patch.object(module,'process',side_effect=process) as body, \
             patch.object(module,'MediaStore'), \
             patch.object(module,'LabelRunProjection',return_value=SimpleNamespace(publish=publish)), \
             self.assertLogs(module.__name__,level='WARNING') as logs:
            self.assertIs(service._iteration(),self.run)
        self.assertEqual(self.events,['settled','projection'])
        self.assertEqual(body.call_count,1);self.assertEqual(calls,[('alice','run')])
        self.assertNotIn('synthetic secret',' '.join(logs.output))
        self.assertEqual(service.metrics.snapshot()['recent_error']['code'],'summary_publication_failed')

    def test_stop_pause_and_resolution_failure_skip_optional_work(self):
        for state in ('stop','pause','signal','resolution'):
            service=self.make(stopping=lambda:state=='signal')
            if state=='stop':service.request_stop()
            if state=='pause':service.request_pause()
            if state=='resolution':self.models.resolve=lambda *a:(_ for _ in ()).throw(ValueError('synthetic'))
            with patch.dict('os.environ',{'VANTALINE_LABEL_INSPECTION_ENABLED':'true'}), \
                 patch.object(module,'LabelRepository',return_value=self.repo), \
                 patch.object(module,'process'),patch.object(module,'MediaStore'), \
                 patch.object(module,'LabelRunProjection') as factory:
                service._iteration()
            factory.assert_not_called()

    def test_admitted_summary_and_cleanup_remain_inside_drain(self):
        service=self.make();entered=threading.Event();release=threading.Event()
        count=[0];guard=threading.Lock()
        def claim():
            with guard:
                count[0]+=1
                return self.run if count[0]==1 else None
        self.repo.claim=claim
        def publish(*a):entered.set();self.assertTrue(release.wait(5))
        with patch.dict('os.environ',{'VANTALINE_LABEL_INSPECTION_ENABLED':'true'}), \
             patch.object(module,'LabelRepository',return_value=self.repo), \
             patch.object(module,'process'),patch.object(module,'MediaStore'), \
             patch.object(module,'LabelRunProjection',return_value=SimpleNamespace(publish=publish)):
            service.start()
            try:
                self.assertTrue(entered.wait(3))
                service.request_pause()
                self.assertEqual(service.runtime_status()['state'],'draining')
                self.assertFalse(service.drain(.02))
            finally:
                release.set()
                self.assertTrue(service.drain(3))
        self.assertIn('clear',self.events)
        self.assertEqual(service.runtime_status()['active_iterations'],0)


if __name__=='__main__':unittest.main()

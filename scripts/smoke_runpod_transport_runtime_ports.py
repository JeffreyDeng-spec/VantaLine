"""Explicit RunPod transport runtime ownership; all remote callbacks are substitutes."""
import ast
import asyncio
import hashlib
import inspect
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import smoke_detection_artifact_ports as fixtures
from fastapi import HTTPException
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.types import ArtifactConflict,ArtifactUnavailable
from local_inspection_service.training.runpod_flow import RunPodFlow
from local_inspection_service.training.runpod_transfer import RunPodTrainingTransfer,TransferPaths
from local_inspection_service.training.runpod_upload_store import RunPodUploadStore

class Body:
    def __init__(self,*chunks):self.chunks=chunks
    async def stream(self):
        for chunk in self.chunks:
            if isinstance(chunk,BaseException):raise chunk
            yield chunk

class RunPodTransportRuntimeTests(unittest.TestCase):
    def setUp(self):fixtures.DetectionArtifactPortsTests.setUp(self)
    def flow(self,index,submit):
        self.stores[index].budget.limits['upload']=1024**3;self.stores[index].budget.free_bytes=lambda:3*1024**3
        return RunPodFlow(None,None,SimpleNamespace(submit=submit),None,runtime_provider=lambda:self.runtimes[index])
    def test_same_job_claims_are_store_owned_and_not_replayed(self):
        calls=[Mock(return_value={'id':'remote-a'}),Mock(return_value={'id':'remote-b'})]
        flows=[self.flow(i,callback) for i,callback in enumerate(calls)]
        for i,flow in enumerate(flows):
            self.assertEqual(flow._submit_once('same-job',{'synthetic':True})['id'],'remote-'+('a' if i==0 else 'b'))
            with self.assertRaises(ArtifactConflict):flow._submit_once('same-job',{})
            calls[i].assert_called_once()
        self.assertFalse((self.root/'training_tasks/submission_claims').exists())
    def test_unknown_submission_retains_claim_and_releases_reservation(self):
        failure=TimeoutError('synthetic unknown submission');submit=Mock(side_effect=failure);flow=self.flow(0,submit)
        with self.assertRaises(TimeoutError) as caught:flow._submit_once('unknown',{})
        self.assertIs(caught.exception,failure)
        with self.assertRaises(ArtifactConflict):flow._submit_once('unknown',{})
        submit.assert_called_once();self.assertFalse(list((self.stores[0].budget.root/'reservations').iterdir()))
    def test_upload_same_path_stays_in_selected_store_and_failure_keeps_old_bytes(self):
        path=self.root/'outputs/runpod_training_artifacts/job/run.zip';owners=[]
        for i in range(2):
            owner=RunPodUploadStore(lambda:100,runtime_provider=lambda i=i:self.runtimes[i]);owners.append(owner)
            payload=('archive-'+str(i)).encode();result=asyncio.run(owner.receive(path,Body(payload)))
            self.assertEqual(result,(hashlib.sha256(payload).hexdigest(),len(payload)))
        failure=ConnectionError('synthetic disconnected')
        with self.assertRaises(ConnectionError) as caught:asyncio.run(owners[0].receive(path,Body(b'partial',failure)))
        self.assertIs(caught.exception,failure)
        for i in range(2):
            self.assertEqual(BusinessFiles(lambda i=i:self.runtimes[i]).read_bytes(path),('archive-'+str(i)).encode())
        self.assertFalse(path.exists())
    def test_download_auth_precedes_runtime_and_runtime_error_never_falls_back(self):
        path=self.root/'outputs/dataset.zip';path.parent.mkdir(parents=True);path.write_bytes(b'local')
        task=dict(runpod_dataset_token_sha256='expected',runpod_dataset_archive_path=str(path))
        failure=ArtifactUnavailable('synthetic unavailable');provider=Mock(side_effect=failure)
        service=RunPodTrainingTransfer(lambda job:task,lambda token:token,lambda:0,TransferPaths(lambda:Path,lambda:self.root/'outputs'),Mock(),Mock(),runtime_provider=provider)
        with self.assertRaises(HTTPException) as caught:service.download_runpod_training_dataset('job','wrong')
        self.assertEqual(caught.exception.status_code,404);provider.assert_not_called()
        with self.assertRaises(ArtifactUnavailable) as caught:service.download_runpod_training_dataset('job','expected')
        self.assertIs(caught.exception,failure);provider.assert_called_once()
    def test_required_providers_and_three_root_bindings(self):
        class Falsey:
            def __bool__(self):raise AssertionError('provider truthiness')
        provider=Falsey()
        for cls in (RunPodFlow,RunPodTrainingTransfer,RunPodUploadStore):
            kwargs={key:Mock() for key in inspect.signature(cls).parameters if key!='runtime_provider'}
            with self.assertRaises(TypeError):cls(**kwargs)
            with self.assertRaises(TypeError):cls(**kwargs,runtime_provider=None)
            self.assertIs(cls(**kwargs,runtime_provider=provider).runtime_provider,provider)
        tree=ast.parse((Path(__file__).resolve().parents[1]/'local_inspection_service/server.py').read_text(encoding='utf-8'))
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('RunPodFlow','RunPodTrainingTransfer','RunPodUploadStore')]
        self.assertEqual(len(calls),3)
        for call in calls:self.assertEqual(ast.dump(next(k.value for k in call.keywords if k.arg=='runtime_provider')),ast.dump(ast.parse('_business_files.runtime_provider',mode='eval').body))

if __name__=='__main__':unittest.main()

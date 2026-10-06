"""RunPod export/import ownership and retained partial effects; no remote requests."""
import ast
import base64
import hashlib
import inspect
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import smoke_detection_artifact_ports as fixtures
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable
from local_inspection_service.training.runpod_exports import RunPodExports,RunPodExportPaths,RunPodExportPolicy
from local_inspection_service.training.runpod_artifacts import RunPodArtifacts,RunPodArtifactPaths

def digest(data):return hashlib.sha256(data).hexdigest()

class RunPodArtifactRuntimeTests(unittest.TestCase):
    def setUp(self):fixtures.DetectionArtifactPortsTests.setUp(self)
    def graph(self,index):
        runtime=self.runtimes[index];files=BusinessFiles(lambda:runtime);output=lambda kind,owner:self.root/'outputs'/kind
        path=self.root/('archive-'+str(index));path.write_bytes(('archive-'+str(index)).encode());cleanup=Mock()
        exports=RunPodExports(RunPodExportPaths(lambda:Path,output,str),
            RunPodExportPolicy(lambda token:digest(token.encode()),lambda:300,lambda:'https://synthetic.invalid'),
            Mock(return_value=(cleanup,path)),lambda p:digest(p.read_bytes()),lambda:Mock(),runtime_provider=lambda:runtime)
        importer=RunPodArtifacts(RunPodArtifactPaths(Path,lambda:self.root/'outputs',lambda:output),Mock(),lambda x:x,runtime_provider=lambda:runtime)
        return exports,importer,files,cleanup,path
    def inline(self,payload):return {'artifacts':{'best_pt':{'artifact_b64':base64.b64encode(payload).decode(),'sha256':digest(payload)}}}
    def test_export_same_path_different_stores_and_cleanup(self):
        first,second=self.graph(0),self.graph(1);outputs=[]
        for exports,_,files,cleanup,source in (first,second):
            result=exports.create_runpod_training_dataset_archive('job',{'owner_user_id':'alice'},{'dataset_dir':'synthetic'})
            self.assertEqual(files.read_bytes(Path(result['path'])),source.read_bytes());cleanup.cleanup.assert_called_once()
            self.assertFalse(Path(result['path']).exists());outputs.append(result)
        self.assertEqual(outputs[0]['path'],outputs[1]['path']);self.assertNotEqual(outputs[0]['sha256'],outputs[1]['sha256'])
    def test_import_same_model_path_isolated_with_ordered_metadata(self):
        first,second=self.graph(0),self.graph(1);paths=[]
        for i,(_,importer,files,_,_) in enumerate((first,second)):
            payload=('synthetic-model-'+str(i)).encode()
            result=importer.import_runpod_yolo_artifacts({'job_id':'job','owner_user_id':'alice'},self.inline(payload))
            paths.append(Path(result['imported_model_path']))
            self.assertEqual(files.read_bytes(paths[-1]),payload);self.assertFalse(paths[-1].exists())
            self.assertTrue(files.exists(paths[-1].parent.parent/'library_metadata.json'))
        self.assertEqual(paths[0],paths[1]);self.assertEqual(first[2].read_bytes(paths[0]),b'synthetic-model-0')
    def test_export_metadata_failure_keeps_archive_and_cleans_bundle(self):
        exports,_,files,cleanup,source=self.graph(0);failure=ArtifactUnavailable('synthetic metadata failure')
        with patch.object(self.runtimes[0].store,'put_bytes',side_effect=failure):
            with self.assertRaises(ArtifactUnavailable) as caught:exports.create_runpod_training_dataset_archive('job',{}, {'dataset_dir':'synthetic'})
        self.assertIs(caught.exception,failure);cleanup.cleanup.assert_called_once()
        self.assertEqual(files.read_bytes(self.root/'outputs/runpod_training_datasets/job/dataset.zip'),source.read_bytes())
    def test_import_summary_failure_keeps_model_and_metadata(self):
        _,importer,files,_,_=self.graph(0);failure=RuntimeError('synthetic summary')
        importer.summary=Mock(side_effect=failure)
        with self.assertRaises(RuntimeError) as caught:importer.import_runpod_yolo_artifacts({'job_id':'job'},self.inline(b'synthetic-model'))
        self.assertIs(caught.exception,failure);importer.summary.assert_called_once()
        root=self.root/'outputs/training_runs/job';self.assertEqual(files.read_bytes(root/'weights/best.pt'),b'synthetic-model')
        self.assertTrue(files.exists(root/'library_metadata.json'));self.assertFalse(files.exists(root/'runpod_result.json'))
    def test_provider_failure_precedes_export_bundle_and_import_lookup(self):
        exports,importer,_,cleanup,_=self.graph(0);failure=ArtifactUnavailable('synthetic runtime')
        for service in (exports,importer):service.runtime_provider=Mock(side_effect=failure)
        for call in (lambda:exports.create_runpod_training_dataset_archive('job',{},{}),lambda:importer.import_runpod_yolo_artifacts({},{})):
            with self.assertRaises(ArtifactUnavailable) as caught:call()
            self.assertIs(caught.exception,failure)
        exports.bundle.assert_not_called();cleanup.cleanup.assert_not_called();importer.find.assert_not_called()
    def test_required_provider_and_two_root_bindings(self):
        class Falsey:
            def __bool__(self):raise AssertionError('provider truthiness')
        provider=Falsey()
        for cls in (RunPodExports,RunPodArtifacts):
            kwargs={key:Mock() for key in inspect.signature(cls).parameters if key!='runtime_provider'}
            with self.assertRaises(TypeError):cls(**kwargs)
            with self.assertRaises(TypeError):cls(**kwargs,runtime_provider=None)
            self.assertIs(cls(**kwargs,runtime_provider=provider).runtime_provider,provider)
        tree=ast.parse((Path(__file__).resolve().parents[1]/'local_inspection_service/server.py').read_text(encoding='utf-8'))
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('RunPodExports','RunPodArtifacts')]
        self.assertEqual(len(calls),2)
        for call in calls:self.assertEqual(ast.dump(next(k.value for k in call.keywords if k.arg=='runtime_provider')),ast.dump(ast.parse('_business_files.runtime_provider',mode='eval').body))

if __name__=='__main__':unittest.main()

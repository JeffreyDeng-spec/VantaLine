"""Independent lazy artifact compositions with actual file/image adapters."""
import ast
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from PIL import Image
import smoke_detection_artifact_ports as fixtures
from smoke_artifact_runtime_provider import configuration
from local_inspection_service.storage.artifacts.composition import create_artifact_composition
from local_inspection_service.storage.artifacts import runtime as module
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable

class WebArtifactCompositionTests(unittest.TestCase):
    def setUp(self):fixtures.DetectionArtifactPortsTests.setUp(self)
    def test_same_absolute_file_and_image_names_stay_in_each_owner(self):
        graphs=[];builders=[]
        for index in range(2):
            environment=Mock(return_value=configuration());builder=Mock(return_value=self.runtimes[index]);builders.append(builder)
            graph=create_artifact_composition(environment,lambda:cv2,lambda:Image,builder=builder);graphs.append(graph)
            environment.assert_not_called();builder.assert_not_called();self.assertIs(graph.images.files,graph.files)
        def exercise(index):
            graph=graphs[index];path=self.root/'outputs'/'same.png';pixels=np.full((4,5,3),40+100*index,dtype=np.uint8)
            graph.images.imwrite(str(path),pixels);np.testing.assert_array_equal(graph.images.imread(str(path)),pixels)
            with graph.images.open(path) as picture:self.assertEqual(picture.getpixel((0,0)),(40+100*index,)*3)
            self.assertEqual(graph.files.runtime(path),self.runtimes[index]);return graph.files.read_bytes(path)
        with ThreadPoolExecutor(max_workers=2) as pool:values=list(pool.map(exercise,range(2)))
        self.assertNotEqual(values[0],values[1]);self.assertFalse((self.root/'outputs'/'same.png').exists())
        for builder in builders:builder.assert_called_once()
        self.assertIsNot(graphs[0].runtime,graphs[1].runtime)
    def test_concurrent_readers_build_once_per_graph_and_configuration_fences_are_local(self):
        configurations=[configuration(),configuration()];builders=[Mock(return_value=value) for value in self.runtimes]
        graphs=[create_artifact_composition(lambda i=i:configurations[i],lambda:cv2,lambda:Image,builder=builders[i]) for i in range(2)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            values=list(pool.map(lambda index:graphs[index%2].files.runtime_provider(),range(24)))
        for i,value in enumerate(values):self.assertIs(value,self.runtimes[i%2])
        for builder in builders:builder.assert_called_once()
        configurations[0]['VANTALINE_COS_BUCKET']+='changed'
        with self.assertRaisesRegex(RuntimeError,'restart is required'):graphs[0].files.runtime_provider()
        self.assertIs(graphs[1].files.runtime_provider(),self.runtimes[1])
    def test_failure_stays_with_selected_graph_and_image_reads_do_not_fallback(self):
        error=ArtifactUnavailable('synthetic');builder=Mock(side_effect=error)
        failed=create_artifact_composition(configuration,lambda:cv2,lambda:Image,builder=builder)
        with self.assertRaises(ArtifactUnavailable) as caught:failed.files.exists(self.root/'outputs'/'same.png')
        self.assertIs(caught.exception,error)
        graph=create_artifact_composition(configuration,lambda:cv2,lambda:Image,builder=Mock(return_value=self.runtimes[1]))
        path=self.root/'outputs'/'same.png';pixels=np.zeros((3,3,3),dtype=np.uint8);graph.images.imwrite(str(path),pixels)
        with patch.object(self.runtimes[1].store,'read_bytes',side_effect=error):
            with self.assertRaises(ArtifactUnavailable) as caught:graph.images.imread(str(path))
        self.assertIs(caught.exception,error);self.assertFalse(path.exists())
    def test_local_exact_backend_and_no_process_default_selection(self):
        backend=Mock();backend.imread.return_value='local';graph=create_artifact_composition(lambda:{},lambda:backend,lambda:Image)
        with patch.object(module,'get_runtime',side_effect=AssertionError('process default')):
            self.assertIs(graph.images.imread,backend.imread)
            self.assertEqual(graph.images.imread('synthetic',7),'local')
        backend.imread.assert_called_once_with('synthetic',7)
    def test_required_suppliers_and_entry_binding(self):
        for args in ((None,Mock(),Mock()),(Mock(),None,Mock()),(Mock(),Mock(),None)):
            with self.assertRaises(TypeError):create_artifact_composition(*args)
        tree=ast.parse((Path(__file__).resolve().parents[1]/'local_inspection_service/server.py').read_text(encoding='utf-8'))
        assignments={t.id:n.value for n in tree.body if isinstance(n,ast.Assign) for t in n.targets if isinstance(t,ast.Name)}
        expected = {
            '_artifact_composition': 'create_artifact_composition(lambda: os.environ, lambda: cv2, lambda: Image)',
            '_business_files': '_artifact_composition.files',
            '_image_files': '_artifact_composition.images',
        }
        for name, expression in expected.items():
            self.assertEqual(ast.dump(assignments[name]), ast.dump(ast.parse(expression, mode='eval').body))
        # Python 3.10's unparser spaces lambda colons differently. Source spelling
        # must not change this guard; swapping a supplier must still be detected.
        equivalent = 'create_artifact_composition(lambda : os.environ, lambda : cv2, lambda : Image)'
        self.assertEqual(ast.dump(assignments['_artifact_composition']), ast.dump(ast.parse(equivalent, mode='eval').body))
        for incorrect in (
            'create_artifact_composition(lambda: {}, lambda: cv2, lambda: Image)',
            'create_artifact_composition(lambda: os.environ, lambda: Image, lambda: cv2)',
            '_artifact_composition.images',
        ):
            self.assertNotEqual(ast.dump(assignments['_artifact_composition']), ast.dump(ast.parse(incorrect, mode='eval').body))
        self.assertNotEqual(ast.dump(assignments['_business_files']), ast.dump(assignments['_image_files']))

if __name__=='__main__':unittest.main()

"""Background image capabilities preserve pixels and isolate explicitly composed stores."""
import ast
from concurrent.futures import ThreadPoolExecutor
import inspect
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from canonical_application_source_contract import read_checked_application_source
import smoke_detection_artifact_ports as fixtures
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.images import ImageFiles
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable
from local_inspection_service.training import background_rendering, background_validation, background_variants
from local_inspection_service.training.background_rendering import TrainingBackgroundRenderer
from local_inspection_service.training.background_validation import BackgroundValidation
from local_inspection_service.training.background_variants import BackgroundVariants


class BackgroundImagePortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)
        self.default = Mock(side_effect=AssertionError('implicit background image adapter'))
        for module in (background_rendering, background_validation, background_variants):
            p=patch.object(module,'_image_files',self.default,create=True);p.start();self.addCleanup(p.stop)

    def graph(self,index):
        files=BusinessFiles(lambda:self.runtimes[index]);images=ImageFiles(lambda:cv2,files=files)
        pixels=np.full((32,48,3),30+index*150,np.uint8);source=self.root/'backgrounds/source.png'
        files.write_bytes(source,cv2.imencode('.png',pixels)[1].tobytes())
        analyze=Mock(return_value={});fallback=Mock(side_effect=AssertionError('unexpected synthetic fallback'))
        validator=BackgroundValidation(lambda value:value,lambda:'fixture:',lambda:101,lambda:SimpleNamespace(hex='abcdef'),
            analyze,lambda:lambda value,limit:str(value)[:limit],images=images)
        item=dict(path=source,id='same',source='synthetic',source_asset='source.png',background_set_id='same',library_size=1)
        renderer=TrainingBackgroundRenderer(lambda selected:[item],lambda library,split:library,fallback,
            lambda image,rng:(image.copy(),{}),lambda image,rng:(image,{}),images=images)
        return SimpleNamespace(files=files,images=images,pixels=pixels,source=source,analyze=analyze,fallback=fallback,
            validator=validator,renderer=renderer,variants=BackgroundVariants(lambda:101,images=images))

    def test_real_stores_render_validate_and_publish_distinct_pixels_at_identical_paths(self):
        graphs=[self.graph(i) for i in range(2)]
        def run(index):
            f=graphs[index];canvas,meta=f.renderer.render_training_background(np.random.default_rng(7),'train','same')
            np.testing.assert_array_equal(canvas,f.pixels);self.assertEqual(meta['background_id'],'same')
            self.assertEqual(f.validator.validate_task_environment_background_image('task',{},f.source)['status'],'accepted')
            f.analyze.assert_called_once();np.testing.assert_array_equal(f.analyze.call_args.args[0],f.pixels)
            result=f.variants.create_background_variants_from_source(f.source,self.root/'backgrounds/variants',2)
            self.assertEqual(len(result),2);self.assertTrue(all(f.files.exists(p) and not p.exists() for p in result))
            return result,[f.files.read_bytes(p) for p in result]
        with ThreadPoolExecutor(max_workers=2) as pool:a,b=list(pool.map(run,range(2)))
        self.assertEqual(a[0],b[0]);self.assertNotEqual(a[1],b[1]);self.default.assert_not_called();self.poison.assert_not_called()

    def test_remote_read_failure_never_becomes_synthetic_background_or_analysis(self):
        f=self.graph(0);self.stores[0].client.fail=True
        with self.assertRaises(ArtifactUnavailable):f.renderer.render_training_background(np.random.default_rng(7))
        with self.assertRaises(ArtifactUnavailable):f.validator.validate_task_environment_background_image('task',{},f.source)
        with self.assertRaises(ArtifactUnavailable):f.variants.create_background_variants_from_source(f.source,self.root/'backgrounds/variants',1)
        f.fallback.assert_not_called();f.analyze.assert_not_called();self.default.assert_not_called()

    def test_variant_publication_failure_keeps_original_and_does_not_try_next_variant(self):
        f=self.graph(0)
        # Warm only the source read lease; the subsequent remote publication fails.
        np.testing.assert_array_equal(f.images.imread(str(f.source),cv2.IMREAD_COLOR),f.pixels)
        before=set(self.stores[0].locations.rows);self.stores[0].client.fail=True
        with patch.object(self.stores[0].store.objects,'put',wraps=self.stores[0].store.objects.put) as publish:
            with self.assertRaises(ArtifactUnavailable):f.variants.create_background_variants_from_source(f.source,self.root/'backgrounds/variants',3)
            self.assertEqual(publish.call_count,1)
        self.assertEqual(set(self.stores[0].locations.rows),before);self.assertTrue(f.files.exists(f.source))

    def test_callee_is_selected_before_path_conversion_rebinds_images(self):
        f=self.graph(0);first=Mock(return_value=f.pixels);replacement=Mock(side_effect=AssertionError('late image selection'))
        f.validator.images=SimpleNamespace(imread=first)
        class Source:
            def __str__(self):f.validator.images=SimpleNamespace(imread=replacement);return 'selected.png'
        path=Source();self.assertEqual(f.validator.validate_task_environment_background_image('task',{},path)['status'],'accepted')
        first.assert_called_once_with('selected.png',cv2.IMREAD_COLOR);replacement.assert_not_called()

    def test_required_falsey_ports_and_actual_root_graph(self):
        class Falsey:
            def __bool__(self):raise AssertionError('dependency truthiness used')
        classes=(BackgroundVariants,BackgroundValidation,TrainingBackgroundRenderer)
        for cls in classes:
            args={k:Mock() for k in inspect.signature(cls).parameters if k!='images'}
            with self.assertRaises(TypeError):cls(**args)
            with self.assertRaises(TypeError):cls(**args,images=None)
            port=Falsey();self.assertIs(cls(**args,images=port).images,port)
        root=Path(__file__).resolve().parents[1];tree=ast.parse(read_checked_application_source(root / 'local_inspection_service/server.py', encoding='utf-8'));found=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in {cls.__name__ for cls in classes}:
                values=[kw.value for kw in node.keywords if kw.arg=='images'];self.assertEqual(len(values),1)
                self.assertEqual(ast.dump(values[0]),ast.dump(ast.parse('_background_image_io',mode='eval').body));found.append(node.func.id)
        self.assertCountEqual(found,[cls.__name__ for cls in classes])
        nodes=[n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_background_image_io' for t in n.targets)]
        self.assertEqual(len(nodes),1);self.assertEqual(ast.dump(nodes[0].value),ast.dump(ast.parse('ImageFiles(lambda: cv2, files=_business_files)',mode='eval').body))


if __name__=='__main__':unittest.main()

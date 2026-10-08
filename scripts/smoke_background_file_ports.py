"""Background file ownership with real isolated stores and synthetic task callbacks."""
import asyncio
import ast
from concurrent.futures import ThreadPoolExecutor
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import smoke_detection_artifact_ports as fixtures
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.types import ArtifactConflict, ArtifactUnavailable
from local_inspection_service.training import background_catalog, background_manifest, background_writes, background_seeding, background_library, background_uploads
from local_inspection_service.training.background_catalog import BackgroundImageFiles, safe_background_set_id
from local_inspection_service.training.background_manifest import BackgroundManifest
from local_inspection_service.training.background_writes import BackgroundWrites
from local_inspection_service.training.background_seeding import BackgroundSeeding, BackgroundSeedPaths
from local_inspection_service.training.background_library import TrainingBackgroundLibrary, BackgroundPaths, BackgroundSetLookup
from local_inspection_service.training.background_uploads import (
    BackgroundUpload, BackgroundUploadPaths, BackgroundUploadRecords, BackgroundCapture, BackgroundCaptureIdentity,
    BackgroundCapturePaths, BackgroundCaptureTasks, BackgroundCaptureSets, BackgroundCaptureState,
)


class BackgroundFilePortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)
        self.poison_files = Mock(side_effect=AssertionError('implicit background files'))
        for module in (background_catalog, background_manifest, background_writes, background_seeding, background_library, background_uploads):
            p = patch.object(module, '_business_files', self.poison_files, create=True); p.start(); self.addCleanup(p.stop)

    def graph(self, index):
        f = SimpleNamespace(files=BusinessFiles(lambda: self.runtimes[index]), directory=self.root/'backgrounds', events=[])
        f.sets = f.directory/'sets'; f.source=f.directory/'default.png'
        f.manifest = BackgroundManifest(lambda:f.directory, lambda:f.directory/'sets.json', files=f.files)
        f.images = BackgroundImageFiles(lambda:{'.png'}, files=f.files)
        f.writes = BackgroundWrites(safe_background_set_id, f.manifest.load_background_sets_manifest,
            f.manifest.write_background_sets_manifest, lambda:f.sets, lambda:SimpleNamespace(hex='abcdef'), lambda:101, files=f.files)
        def minimum(key):
            f.events.append(('minimum', key)); self.assertEqual(f.files.read_bytes(f.sets/key/'default.png'), ('seed-'+str(index)).encode())
        f.seed = BackgroundSeeding(BackgroundSeedPaths(lambda:f.source, lambda:f.sets), f.manifest.load_background_sets_manifest,
            f.manifest.write_background_sets_manifest, minimum, lambda:f.seed.seed_default_background_set(), lambda:101, files=f.files)
        f.library = TrainingBackgroundLibrary(BackgroundPaths(lambda:f.directory, lambda:f.source, lambda:{'.png'}),
            BackgroundSetLookup(lambda:{}, lambda selected:selected, lambda selected:f.images.image_file_list(f.sets/selected)), files=f.files)
        f.enqueue = Mock(return_value={'job_id':'synthetic-job'})
        f.upload = BackgroundUpload(BackgroundUploadPaths(lambda:f.sets, lambda:{'.png'}),
            BackgroundUploadRecords(f.writes.unique_background_set_id, lambda:f.writes.update_background_set_manifest, f.enqueue, lambda key,meta:meta),
            lambda:{'owner_user_id':'alice'}, lambda:101, lambda:{}, files=f.files)
        return f

    def test_concurrent_seed_manifest_upload_and_library_same_paths_are_isolated(self):
        graphs=[self.graph(i) for i in range(2)]
        def run(index):
            f=graphs[index]; f.files.write_bytes(f.source, ('seed-'+str(index)).encode())
            f.seed.seed_default_background_set()
            self.assertEqual(f.seed.background_set_dirs(), [f.sets/'green_conveyor'])
            self.assertEqual(f.images.image_file_list(f.sets/'green_conveyor'), [f.sets/'green_conveyor/default.png'])
            rows=f.library.training_background_library('green_conveyor')
            self.assertEqual([row['path'] for row in rows], [f.source, f.sets/'green_conveyor/default.png'])
            body=('upload-'+str(index)).encode()
            response=asyncio.run(f.upload.upload_training_background_set('same', SimpleNamespace(filename='same.png',file=io.BytesIO(body))))
            self.assertEqual(response['status'],'queued'); f.enqueue.assert_called_once()
            self.assertEqual(f.files.read_bytes(f.sets/'same/source.png'), body)
            self.assertEqual(f.writes.unique_background_set_id('same'),'same_abcdef')
            self.assertFalse((f.sets/'same/source.png').exists())
            return f.manifest.load_background_sets_manifest()
        with ThreadPoolExecutor(max_workers=2) as pool: result=list(pool.map(run,range(2)))
        self.assertEqual(result[0],result[1])
        graphs[0].writes.update_background_set_manifest('same',name='only-first')
        self.assertEqual(graphs[0].manifest.load_background_sets_manifest()['sets']['same']['name'],'only-first')
        self.assertEqual(graphs[1].manifest.load_background_sets_manifest()['sets']['same']['name'],'same')
        self.poison_files.assert_not_called()

    def test_manifest_conflict_preserves_version_evidence_and_other_graph(self):
        a,b=self.graph(0),self.graph(1)
        for f in (a,b):f.manifest.write_background_sets_manifest({'sets':{}})
        first=a.manifest.load_background_sets_manifest();stale=a.manifest.load_background_sets_manifest()
        first['sets']['one']={};a.manifest.write_background_sets_manifest(first)
        stale['sets']['lost']={}
        with self.assertRaises(ArtifactConflict):a.manifest.write_background_sets_manifest(stale)
        self.assertEqual(a.manifest.load_background_sets_manifest()['sets'],{'one':{}})
        self.assertEqual(b.manifest.load_background_sets_manifest()['sets'],{})

    def test_failed_stream_publication_does_not_enqueue_or_fallback(self):
        a,b=self.graph(0),self.graph(1);self.stores[0].client.fail=True
        with self.assertRaises(ArtifactUnavailable):
            asyncio.run(a.upload.upload_training_background_set('same',SimpleNamespace(filename='a.png',file=io.BytesIO(b'body'))))
        a.enqueue.assert_not_called();self.assertEqual(a.manifest.load_background_sets_manifest(),{})
        self.assertFalse((a.sets/'same/source.png').exists())
        self.assertEqual(asyncio.run(b.upload.upload_training_background_set('same',SimpleNamespace(filename='a.png',file=io.BytesIO(b'body'))))['status'],'queued')

    def test_capture_permission_precedes_publication_and_storage_failure_precedes_validation(self):
        import threading
        events=[];permission=Mock(side_effect=lambda *a,**kw:events.append('permission'));validate=Mock();save=Mock(return_value={'id':'background'})
        files=BusinessFiles(lambda:self.runtimes[0]);f=self.graph(0)
        service=BackgroundCapture(BackgroundCaptureIdentity(lambda value:value,lambda:{'id':'alice'},lambda value:value),
            BackgroundCapturePaths(lambda:{'.png'},lambda:lambda *a:self.root/'outputs',lambda path:path.name),
            BackgroundCaptureTasks(lambda:[{'id':'task','name':'Task'}],permission,Mock()),
            BackgroundCaptureSets(validate,lambda:save),BackgroundCaptureState(lambda:threading.RLock(),lambda key:{},Mock(),Mock(return_value={})),
            lambda:101,lambda:SimpleNamespace(hex='abcdef'),files=files)
        error=RuntimeError('denied');permission.side_effect=error
        with self.assertRaises(RuntimeError) as caught:asyncio.run(service.upload_ai_task_environment_background('task',SimpleNamespace(filename='a.png',file=io.BytesIO(b'body'))))
        self.assertIs(caught.exception,error);validate.assert_not_called();self.assertFalse((self.root/'outputs/task').exists())
        permission.side_effect=None;self.stores[0].client.fail=True
        with self.assertRaises(ArtifactUnavailable):asyncio.run(service.upload_ai_task_environment_background('task',SimpleNamespace(filename='a.png',file=io.BytesIO(b'body'))))
        validate.assert_not_called();save.assert_not_called()

    def test_missing_none_falsey_ports_and_actual_root_bindings(self):
        f=self.graph(0)
        classes={'BackgroundImageFiles','BackgroundManifest','BackgroundWrites','BackgroundSeeding','TrainingBackgroundLibrary','BackgroundUpload','BackgroundCapture'}
        root=Path(__file__).resolve().parents[1];tree=ast.parse((root/'local_inspection_service/server.py').read_text(encoding='utf-8'))
        found=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in classes:
                kw=[x.value for x in node.keywords if x.arg=='files'];self.assertEqual(len(kw),1)
                self.assertEqual(ast.dump(kw[0]),ast.dump(ast.parse('_business_files',mode='eval').body));found.append(node.func.id)
        self.assertCountEqual(found,classes)
        class Falsey:
            def __bool__(self):raise AssertionError('truthiness checked')
        # Constructor bind validation for every root-selected class, without selecting a runtime.
        import inspect
        modules=(background_catalog,background_manifest,background_writes,background_seeding,background_library,background_uploads)
        for name in classes:
            cls=next(getattr(m,name) for m in modules if hasattr(m,name));args={k:Mock() for k in inspect.signature(cls).parameters if k!='files'}
            with self.assertRaises(TypeError):cls(**args)
            with self.assertRaises(TypeError):cls(**args,files=None)
            port=Falsey();self.assertIs(cls(**args,files=port).files,port)
        for module in modules:self.assertNotIn('BusinessFiles()',Path(module.__file__).read_text(encoding='utf-8'))


if __name__=='__main__':unittest.main()

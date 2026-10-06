"""Synthetic background generation keeps explicit artifact and model-snapshot ownership."""
import ast
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import inspect
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import smoke_detection_artifact_ports as fixtures
from smoke_training_background_tasks import BackgroundFixture
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts import native
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable, ArtifactConflict
from local_inspection_service.training import background_codex, background_task_runner
from local_inspection_service.training.background_codex import CodexBackgroundGeneration, CodexBackgroundPaths
from local_inspection_service.training.background_task_runner import BackgroundTaskRunner, BackgroundTaskRecords, BackgroundTaskGeneration


class BackgroundGenerationPortsTests(unittest.TestCase):
    def setUp(self):
        fixtures.DetectionArtifactPortsTests.setUp(self)
        self.default=Mock(side_effect=AssertionError('implicit generation files'))
        for module in (background_codex,background_task_runner):
            p=patch.object(module,'BusinessFiles',self.default,create=True);p.start();self.addCleanup(p.stop)
        self.calls=[];self.code=0;self.before_return=lambda runtime:None

    def graph(self,index):
        files=BusinessFiles(lambda:self.runtimes[index]);source=self.root/'backgrounds/source.png';directory=self.root/'backgrounds/generated'
        body=cv2.imencode('.png',np.full((8,12,3),40+index*120,np.uint8))[1].tobytes();files.write_bytes(source,body)
        external=Mock(side_effect=AssertionError('real process attempted'))
        service=CodexBackgroundGeneration(external,CodexBackgroundPaths(lambda:self.root/'image_worker_logs',lambda:self.root),lambda value:value,external,files=files)
        return files,source,directory,body,service

    @contextmanager
    def image_job(self,runtime,inputs,prompt):
        self.calls.append(runtime)
        with tempfile.TemporaryDirectory(prefix='synthetic-background-generator-') as temporary:
            work=Path(temporary);source=work/'source.png'
            files=BusinessFiles(lambda:runtime);source.write_bytes(files.read_bytes(inputs[0]))
            for line in prompt(None).splitlines():
                if line.startswith('/work/'):(work/Path(line).name).write_bytes(source.read_bytes())
            log=work/'generation.log';log.write_bytes(b'synthetic generation evidence')
            self.before_return(runtime)
            yield source,log,self.code

    def test_two_actual_cos_generation_paths_publish_only_their_selected_store(self):
        graphs=[self.graph(i) for i in range(2)]
        def run(index):
            files,source,directory,body,service=graphs[index]
            result=service.run_codex_background_generation(source,directory,'same',2)
            self.assertEqual([p.name for p in result],['codex_same_01.png','codex_same_02.png'])
            for path in result:self.assertEqual(files.read_bytes(path),body);self.assertFalse(path.exists())
            self.assertEqual(files.read_bytes(self.root/'image_worker_logs/background_same_codexcli.log'),b'synthetic generation evidence')
            return result
        with patch.object(native,'image_job',self.image_job),ThreadPoolExecutor(max_workers=2) as pool:paths=list(pool.map(run,range(2)))
        self.assertEqual(paths[0],paths[1]);self.assertEqual(len(self.calls),2);self.default.assert_not_called()

    def test_nonzero_generation_keeps_log_evidence_and_does_not_retry_or_publish_images(self):
        files,source,directory,body,service=self.graph(0);self.code=1
        with patch.object(native,'image_job',self.image_job):
            with self.assertRaises(ArtifactUnavailable):service.run_codex_background_generation(source,directory,'same',2)
        self.assertEqual(len(self.calls),1);self.assertTrue(files.exists(self.root/'image_worker_logs/background_same_codexcli.log'))
        self.assertFalse(files.exists(directory/'codex_same_01.png'))

    def test_output_generation_conflict_preserves_newer_bytes_without_paid_replay(self):
        files,source,directory,body,service=self.graph(0)
        self.before_return=lambda runtime:files.write_bytes(directory/'codex_same_01.png',b'concurrent newer bytes')
        with patch.object(native,'image_job',self.image_job):
            with self.assertRaises(ArtifactConflict):service.run_codex_background_generation(source,directory,'same',2)
        self.assertEqual(len(self.calls),1);self.assertEqual(files.read_bytes(directory/'codex_same_01.png'),b'concurrent newer bytes')
        self.assertFalse(files.exists(directory/'codex_same_02.png'))

    def test_runner_checks_owned_source_with_bound_snapshot_and_settles_missing_without_generation(self):
        files,source,directory,body,service=self.graph(0)
        temporary=tempfile.TemporaryDirectory(prefix='background-task-ports-');self.addCleanup(temporary.cleanup)
        f=BackgroundFixture(temporary.name);f.task['source_path']=str(source)
        def runner(selected):
            return BackgroundTaskRunner(BackgroundTaskRecords(f.find,f.path,lambda:f.load,lambda:f.update),
                BackgroundTaskGeneration(lambda:directory,f.safe,lambda:f.meta,f.local,f.codex,f.images),f.clock,lambda:f.resolver,files=selected)
        runner(files).run_background_set_task('job');self.assertEqual(f.task_updates[-1]['status'],'completed')
        self.assertEqual(f.resolver.scopes[-1],f.binding['model_profiles']);self.assertIsNone(f.resolver.current_snapshot())
        f.local.reset_mock();f.codex.reset_mock();f.task_updates.clear()
        runner(BusinessFiles(lambda:self.runtimes[1])).run_background_set_task('job')
        self.assertEqual(f.task_updates[-1]['status'],'failed');f.local.assert_not_called();f.codex.assert_not_called()
        self.assertIsNone(f.resolver.current_snapshot());self.default.assert_not_called()

    def test_missing_none_falsey_dependencies_and_actual_root_bindings(self):
        class Falsey:
            def __bool__(self):raise AssertionError('truthiness checked')
        for cls in (CodexBackgroundGeneration,BackgroundTaskRunner):
            args={k:Mock() for k in inspect.signature(cls).parameters if k!='files'}
            with self.assertRaises(TypeError):cls(**args)
            with self.assertRaises(TypeError):cls(**args,files=None)
            port=Falsey();self.assertIs(cls(**args,files=port).files,port)
        root=Path(__file__).resolve().parents[1];tree=ast.parse((root/'local_inspection_service/server.py').read_text(encoding='utf-8'));found=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in {'CodexBackgroundGeneration','BackgroundTaskRunner'}:
                values=[k.value for k in node.keywords if k.arg=='files'];self.assertEqual(len(values),1)
                self.assertEqual(ast.dump(values[0]),ast.dump(ast.parse('_business_files',mode='eval').body));found.append(node.func.id)
        self.assertCountEqual(found,['CodexBackgroundGeneration','BackgroundTaskRunner'])


if __name__=='__main__':unittest.main()

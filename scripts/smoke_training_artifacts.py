"""Synthetic ZIP/byte contracts for training archives and RunPod artifacts."""
from contextlib import ExitStack
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import quote
import zipfile

from PIL import Image

PIL_IMAGE_OPEN = Image.open

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class ArtifactContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ)
        cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='training-artifacts-root-')
        root = Path(cls.runtime.name)
        (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls):
        cls.runtime.cleanup()
        cls.environment.stop()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='training-artifacts-'))).resolve()
        self.output_root = self.root / 'outputs'
        self.output_root.mkdir()
        self.remove = shutil.rmtree
        def checked_remove(path, *args, **kwargs):
            # Validate the absolute target before every actual recursive removal in these tests.
            resolved = Path(path).resolve()
            self.assertTrue(resolved.is_relative_to(self.root), str(resolved))
            self.assertNotEqual(resolved, self.root)
            return self.remove(path, *args, **kwargs)
        self.stack.enter_context(patch.object(shutil, 'rmtree', side_effect=checked_remove))
        self.stack.enter_context(patch('requests.request', side_effect=AssertionError('unexpected network')))
        self.stack.enter_context(patch('subprocess.Popen', side_effect=AssertionError('unexpected process')))
        self.stack.enter_context(patch('os.kill', side_effect=AssertionError('unexpected signal')))
        # The Web/model import can patch Image.open to auto-install a HEIF decoder.
        # Keep this offline archive contract on the native Pillow decoder.
        self.stack.enter_context(patch.object(Image, 'open', PIL_IMAGE_OPEN))
        self.task = {'job_id': ' job ', 'owner_user_id': 'alice', 'label': 'Synthetic model',
                     'pipeline_task_id': 'pipeline', 'pipeline_task_name': 'Synthetic pipeline',
                     'runpod_job_id': 'remote-job'}
        self.output = Mock(side_effect=lambda kind, owner: self.output_root / owner / kind)
        self.resolve = Mock(side_effect=lambda value: self.output_root / value)
        self.find = Mock(return_value=None)
        self.summary = Mock(return_value={'redacted': True})
        self.update = Mock(return_value={})
        self.safe = Mock(return_value='safe-job')
        self.ttl = Mock(return_value=60)
        self.public_base = Mock(return_value='https://fixture.invalid:8443')
        self.token = Mock(return_value='fixture /token?')
        for name, value in {'OUTPUT_DIR': self.output_root, 'output_write_dir_for_owner': self.output,
                            'resolve_service_path': self.resolve, 'find_training_task': self.find,
                            'runpod_public_response_summary': self.summary, 'update_training_task': self.update,
                            'safe_name': self.safe, 'runpod_yolo_dataset_token_ttl_seconds': self.ttl,
                            'runpod_yolo_public_base_url': self.public_base}.items():
            self.stack.enter_context(patch.object(self.api, name, value))
        self.stack.enter_context(patch('secrets.token_urlsafe', self.token))

    def zip(self, path, entries):
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, 'w') as archive:
            for name, data in entries:
                archive.writestr(name, data)
        return path

    def temporary_factory(self):
        original = tempfile.TemporaryDirectory
        created = []
        def factory(*args, **kwargs):
            self.assertNotIn('dir', kwargs)
            directory = original(*args, **kwargs, dir=self.root)
            created.append(directory)
            return directory
        self.stack.enter_context(patch.object(tempfile, 'TemporaryDirectory', side_effect=factory))
        return created

    def bundle_fixture(self):
        directory = self.root / 'bundle'
        directory.mkdir()
        archive = directory / 'dataset.zip'
        archive.write_bytes(b'synthetic-archive')
        cleanup = Mock(side_effect=lambda: self.remove(directory))
        # This closure is also explicitly constrained before the native removal.
        def clean():
            self.assertTrue(directory.resolve().is_relative_to(self.root))
            self.assertNotEqual(directory.resolve(), self.root)
            self.remove(directory)
        cleanup.side_effect = clean
        bundle = Mock(return_value=(SimpleNamespace(cleanup=cleanup), archive))
        self.stack.enter_context(patch.object(self.api, 'build_worker_training_bundle', bundle))
        return bundle, archive, cleanup

    def inline(self, data=b'synthetic-model-bytes', sha=None):
        best = {'artifact_b64': base64.b64encode(data).decode('ascii')}
        if sha is not None:
            best['sha256'] = sha
        return {'artifacts': {'best_pt': best}, 'worker': 'fixture-worker', 'contract_version': 3}

    def test_hash_chunking_and_sorted_manifest_includes_all_files(self):
        directory = self.root / 'data'
        directory.mkdir()
        payload = bytes(range(256)) * 8192 + b'last'
        path = directory / 'large.bin'
        path.write_bytes(payload)
        self.assertEqual(self.api.file_sha256(path), hashlib.sha256(payload).hexdigest())
        (directory / 'previews').mkdir()
        (directory / 'previews/a.txt').write_bytes(b'A')
        (directory / 'z.txt').write_bytes(b'Z')
        with patch.object(self.api, 'file_sha256', wraps=self.api.file_sha256) as digest:
            result = self.api.dataset_file_manifest(directory)
        self.assertEqual([item['path'] for item in result], ['large.bin', 'previews/a.txt', 'z.txt'])
        self.assertEqual([item['size'] for item in result], [len(payload), 1, 1])
        self.assertEqual(digest.call_count, 3)
        self.assertEqual([call.args[0].relative_to(directory).as_posix() for call in digest.call_args_list], [item['path'] for item in result])
        self.assertEqual(self.api.dataset_file_manifest(self.root / 'missing'), [])
        with self.assertRaises(FileNotFoundError):
            self.api.file_sha256(self.root / 'missing')

    def test_plain_package_keeps_every_file_and_missing_checks_before_temporary_creation(self):
        directories = self.temporary_factory()
        dataset = self.root / 'dataset'
        (dataset / 'previews').mkdir(parents=True)
        (dataset / 'previews/a.txt').write_bytes(b'preview')
        (dataset / 'data.txt').write_bytes(b'data')
        temp, archive = self.api.package_training_dataset(dataset, 'job')
        self.assertIs(temp, directories[0])
        self.assertTrue(Path(temp.name).name.startswith('vantaline_safe-job_'))
        with zipfile.ZipFile(archive) as handle:
            self.assertEqual(handle.read('previews/a.txt'), b'preview')
            self.assertEqual(handle.read('data.txt'), b'data')
        temp.cleanup()
        for path in (self.root / 'missing', dataset / 'data.txt'):
            with self.assertRaisesRegex(RuntimeError, 'Training dataset directory is missing'):
                self.api.package_training_dataset(path, 'job')
        self.assertEqual(len(directories), 1)

    def test_optimized_bundle_transcodes_only_images_and_skips_only_top_level_directories(self):
        self.temporary_factory()
        dataset = self.root / 'dataset'
        (dataset / 'images/train').mkdir(parents=True)
        Image.new('RGBA', (13, 9), (20, 80, 160, 100)).save(dataset / 'images/train/sample.png')
        (dataset / 'images/train/broken.png').write_bytes(b'broken-image')
        for name in ('PREVIEWS/skip.txt', 'debug/skip.txt', 'other/debug/keep.txt', 'labels/train/sample.txt', 'outside.png'):
            path = dataset / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
        temp, archive = self.api.build_worker_training_bundle(dataset, 'job')
        try:
            with zipfile.ZipFile(archive) as handle:
                files = {name for name in handle.namelist() if not name.endswith('/')}
                self.assertEqual(files, {'images/train/sample.jpg', 'images/train/broken.png', 'other/debug/keep.txt', 'labels/train/sample.txt', 'outside.png'})
                self.assertEqual(handle.read('images/train/broken.png'), b'broken-image')
                import io
                with Image.open(io.BytesIO(handle.read('images/train/sample.jpg'))) as image:
                    self.assertEqual((image.format, image.mode, image.size), ('JPEG', 'RGB', (13, 9)))
                    self.assertTrue(all(abs(a-b) < 5 for a,b in zip(image.getpixel((6,4)), (20,80,160))))
            self.assertTrue((dataset / 'images/train/sample.png').exists())
            self.assertFalse((dataset / 'images/train/sample.jpg').exists())
        finally:
            temp.cleanup()

    def test_conversion_failure_keeps_partial_jpeg_and_original_fallback(self):
        self.temporary_factory()
        dataset = self.root / 'dataset'
        (dataset / 'images/train').mkdir(parents=True)
        Image.new('RGB', (10, 8)).save(dataset / 'images/train/a.png')
        def fail_save(image, path, **kwargs):
            Path(path).write_bytes(b'partial-jpeg')
            raise OSError('conversion failed')
        with patch.object(Image.Image, 'save', fail_save):
            temp, archive = self.api.build_worker_training_bundle(dataset, 'job')
        try:
            with zipfile.ZipFile(archive) as handle:
                self.assertEqual(handle.read('images/train/a.jpg'), b'partial-jpeg')
                self.assertEqual(handle.read('images/train/a.png'), (dataset / 'images/train/a.png').read_bytes())
        finally:
            temp.cleanup()

    def test_dataset_export_metadata_encoded_url_cleanup_and_existing_directory_replacement(self):
        bundle, archive, cleanup = self.bundle_fixture()
        target = self.output_root / 'alice/runpod_training_datasets/safe-job'
        target.mkdir(parents=True)
        (target / 'old.txt').write_text('old')
        payload = archive.read_bytes()
        with patch('time.time', side_effect=[100, 200]):
            result = self.api.create_runpod_training_dataset_archive('job / raw', self.task, {'dataset_dir': 'relative-data'})
        self.resolve.assert_called_once_with('relative-data')
        bundle.assert_called_once_with(self.output_root / 'relative-data', 'job / raw')
        self.output.assert_called_once_with('runpod_training_datasets', 'alice')
        self.safe.assert_called_once_with('job / raw')
        self.assertFalse((target / 'old.txt').exists())
        self.assertEqual((target / 'dataset.zip').read_bytes(), payload)
        expected_url = 'https://fixture.invalid:8443/api/training/runpod/datasets/' + quote('job / raw', safe='') + '/' + quote('fixture /token?', safe='') + '/dataset.zip'
        self.assertEqual(result, {'url': expected_url, 'sha256': hashlib.sha256(payload).hexdigest(), 'size': len(payload), 'path': str(target / 'dataset.zip')})
        metadata = json.loads((target / 'metadata.json').read_text())
        self.assertEqual(metadata, {'job_id': 'job / raw', 'path': str(target / 'dataset.zip'), 'sha256': result['sha256'],
                                   'size': len(payload), 'token_sha256': hashlib.sha256(b'fixture /token?').hexdigest(), 'expires_at': 160, 'created_at': 200})
        self.assertNotIn('fixture /token?', json.dumps(metadata))
        self.update.assert_called_once()
        self.assertEqual(self.update.call_args.kwargs['runpod_dataset_public_host'], 'fixture.invalid:8443')
        self.assertEqual(self.update.call_args.kwargs['runpod_dataset_token_expires_at'], 160)
        self.token.assert_called_once_with(32)
        cleanup.assert_called_once()
        self.assertFalse(archive.exists())

    def test_export_finally_cleanup_and_failure_residue(self):
        bundle, archive, cleanup = self.bundle_fixture()
        self.update.side_effect = [RuntimeError('update failure'), {}]
        with self.assertRaisesRegex(RuntimeError, 'update failure'):
            self.api.create_runpod_training_dataset_archive('job', self.task, {})
        self.update.assert_called_once()
        cleanup.assert_called_once()
        target = self.output_root / 'alice/runpod_training_datasets/safe-job'
        self.assertTrue((target / 'dataset.zip').exists())
        self.assertTrue((target / 'metadata.json').exists())
        self.assertFalse(archive.exists())
        # Bundle acquisition occurs before try/finally; there is no acquired cleanup on its failure.
        bundle.side_effect = RuntimeError('bundle failure')
        cleanup.reset_mock()
        with self.assertRaisesRegex(RuntimeError, 'bundle failure'):
            self.api.create_runpod_training_dataset_archive('job', self.task, {})
        cleanup.assert_not_called()

    def test_artifact_upload_path_normalization_deletion_and_raw_update_id(self):
        raw = '  .. job/@..  '
        target = self.output_root / 'alice/runpod_training_artifacts/job_@'
        target.mkdir(parents=True)
        (target / 'old.txt').write_text('old')
        with patch('time.time', return_value=50):
            result = self.api.create_runpod_training_artifact_upload(raw, self.task)
        self.assertEqual(result['path'], str(target / 'run.zip'))
        self.assertEqual(result['url'], 'https://fixture.invalid:8443/api/training/runpod/artifacts/' + quote(raw.strip(), safe='') + '/' + quote('fixture /token?', safe='') + '/run.zip')
        self.assertEqual(list(target.iterdir()), [])
        self.assertEqual(self.update.call_args.args, (raw,))
        self.assertEqual(self.update.call_args.kwargs['runpod_artifact_token_expires_at'], 110)
        self.safe.assert_not_called()
        empty = self.api.create_runpod_training_artifact_upload('...', {})
        self.assertEqual(Path(empty['path']).parent.name, 'runpod_training')

    def test_inline_import_skips_finder_validates_hash_and_writes_exact_metadata(self):
        data = b'synthetic-model-bytes'
        sha = hashlib.sha256(data).hexdigest()
        output = self.inline(data, ' ' + sha.upper() + ' ')
        with patch('time.time', side_effect=[100, 200]):
            result = self.api.import_runpod_yolo_artifacts(self.task, output)
        self.find.assert_not_called()
        self.resolve.assert_not_called()
        self.output.assert_called_once_with('training_runs', 'alice')
        directory = self.output_root / 'alice/training_runs/job'
        self.assertEqual((directory / 'weights/best.pt').read_bytes(), data)
        self.assertFalse((directory / 'runpod_artifacts.zip').exists())
        metadata = json.loads((directory / 'library_metadata.json').read_text())
        self.assertEqual(metadata, {'display_name': 'Synthetic model', 'note': 'Imported from RunPod YOLO training worker.',
            'pipeline_task_id': 'pipeline', 'pipeline_task_name': 'Synthetic pipeline', 'runpod_job_id': 'remote-job',
            'runpod_worker': 'fixture-worker', 'runpod_contract_version': 3, 'runpod_best_pt_sha256': sha,
            'runpod_artifact_archive_path': '', 'updated_at': 100})
        self.assertEqual(json.loads((directory / 'runpod_result.json').read_text()), {'redacted': True})
        self.summary.assert_called_once_with(output)
        self.assertEqual(result, {'worker_artifacts_imported_at': 200, 'worker_artifact_import_error': '',
            'training_run_dir': str(directory), 'imported_model_path': str(directory / 'weights/best.pt'),
            'runpod_best_pt_sha256': sha, 'worker_artifact_sha256': sha})

    def test_inline_invalid_or_checksum_mismatch_never_falls_back_or_creates_run(self):
        for output, message in [({'artifacts': {'best_pt': {'artifact_b64': 'not valid%%'}}}, 'not valid base64'),
                                (self.inline(sha='bad-sha'), 'checksum mismatch')]:
            with self.subTest(message=message):
                with self.assertRaisesRegex(RuntimeError, message):
                    self.api.import_runpod_yolo_artifacts(self.task, output)
                self.find.assert_not_called()
                self.output.assert_not_called()
        self.find.return_value = {'truthy': 'record without artifact path'}
        task = {**self.task, 'runpod_artifact_upload_path': 'fallback-ignored.zip'}
        with self.assertRaisesRegex(RuntimeError, 'did not return or upload'):
            self.api.import_runpod_yolo_artifacts(task, {'artifacts': []})
        self.find.assert_called_once_with('job')
        self.resolve.assert_not_called()

    def test_uploaded_archive_path_guard_and_lexicographic_member_without_extraction(self):
        archive = self.zip(self.output_root / 'upload/run.zip', [
            ('z/weights/best.pt', b'Z'), ('a\\weights\\best.pt', b'A'), ('../weights/best.pt', b'PARENT'), ('weights/best.PT', b'wrong-case')])
        self.find.return_value = {'runpod_artifact_archive_path': str(archive)}
        output = {'artifacts': {'best_pt': {'sha256': hashlib.sha256(b'PARENT').hexdigest()}}}
        result = self.api.import_runpod_yolo_artifacts(self.task, output)
        self.resolve.assert_not_called()
        self.find.assert_called_once_with('job')
        self.assertEqual(Path(result['imported_model_path']).read_bytes(), b'PARENT')
        self.assertEqual((Path(result['training_run_dir']) / 'runpod_artifacts.zip').read_bytes(), archive.read_bytes())
        self.assertFalse((self.output_root / 'alice/training_runs/weights').exists())
        outside = self.zip(self.root / 'outputs-sibling/run.zip', [('weights/best.pt', b'outside')])
        self.find.return_value = {'runpod_artifact_upload_path': str(outside)}
        self.output.reset_mock()
        with self.assertRaisesRegex(RuntimeError, 'outside the output directory'):
            self.api.import_runpod_yolo_artifacts(self.task, {})
        self.output.assert_not_called()
        self.find.return_value = {'runpod_artifact_upload_path': 'upload/run.zip'}
        self.api.import_runpod_yolo_artifacts(self.task, {})
        self.resolve.assert_called_once_with('upload/run.zip')

    def test_uploaded_archive_missing_invalid_zip_and_missing_member_fail_before_output(self):
        paths = [(self.output_root / 'missing.zip', 'is missing'), (self.output_root, 'is missing')]
        bad = self.output_root / 'bad.zip'
        bad.write_bytes(b'not a zip')
        paths.append((bad, 'not a valid zip'))
        empty = self.zip(self.output_root / 'empty.zip', [('weights/best.PT', b'wrong-case')])
        paths.append((empty, 'does not contain weights/best.pt'))
        for path, message in paths:
            with self.subTest(message=message):
                self.find.return_value = {'runpod_artifact_upload_path': str(path)}
                with self.assertRaisesRegex(RuntimeError, message):
                    self.api.import_runpod_yolo_artifacts(self.task, {})
                self.output.assert_not_called()

    def test_import_failure_residue_does_not_remove_or_retry_prior_writes(self):
        original_bytes, original_text, original_copy = Path.write_bytes, Path.write_text, shutil.copy2
        for failed in ('best', 'copy', 'metadata', 'summary', 'result'):
            with self.subTest(failed=failed), ExitStack() as stack:
                archive = self.zip(self.output_root / (failed + '/upload.zip'), [('weights/best.pt', b'SYNTHETIC')])
                self.find.return_value = {'runpod_artifact_upload_path': str(archive)}
                self.output.side_effect = lambda kind, owner: self.output_root / failed / kind
                def write_bytes(path, data):
                    if failed == 'best' and path.name == 'best.pt':
                        original_bytes(path, b'partial')
                        raise OSError('best failure')
                    return original_bytes(path, data)
                text_attempts = {}
                def write_text(path, data, *args, **kwargs):
                    kind = 'metadata' if path.name == 'library_metadata.json' else 'result'
                    text_attempts[kind] = text_attempts.get(kind, 0) + 1
                    if kind == failed and text_attempts[kind] == 1:
                        original_text(path, 'partial', encoding='utf-8')
                        raise OSError(failed + ' failure')
                    return original_text(path, data, *args, **kwargs)
                writes = stack.enter_context(patch.object(Path, 'write_bytes', autospec=True, side_effect=write_bytes))
                texts = stack.enter_context(patch.object(Path, 'write_text', autospec=True, side_effect=write_text))
                copies = stack.enter_context(patch.object(shutil, 'copy2', side_effect=OSError('copy failure') if failed == 'copy' else original_copy))
                self.summary.reset_mock()
                self.summary.side_effect = RuntimeError('summary failure') if failed == 'summary' else None
                self.summary.return_value = {'redacted': True}
                with self.assertRaisesRegex((OSError, RuntimeError), failed + ' failure'):
                    self.api.import_runpod_yolo_artifacts(self.task, {})
                directory = self.output_root / failed / 'training_runs/job'
                self.assertEqual((directory / 'weights/best.pt').read_bytes(), b'partial' if failed == 'best' else b'SYNTHETIC')
                self.assertEqual(writes.call_count, 1)
                self.assertEqual(copies.call_count, 0 if failed == 'best' else 1)
                self.assertEqual((directory / 'runpod_artifacts.zip').exists(), failed not in ('best', 'copy'))
                self.assertEqual((directory / 'library_metadata.json').exists(), failed in ('metadata', 'summary', 'result'))
                self.assertEqual((directory / 'runpod_result.json').exists(), failed == 'result')
                self.assertEqual(self.summary.call_count, 1 if failed in ('summary', 'result') else 0)
                names = [call.args[0].name for call in texts.call_args_list]
                self.assertEqual(names.count('library_metadata.json'), 1 if failed in ('metadata', 'summary', 'result') else 0)
                self.assertEqual(names.count('runpod_result.json'), 1 if failed == 'result' else 0)


    def test_bundle_late_quality_skip_policy_and_same_stem_overwrite(self):
        self.temporary_factory()
        dataset = self.root / 'dataset'
        (dataset / 'images').mkdir(parents=True)
        Image.new('RGB', (8, 6), (255, 0, 0)).save(dataset / 'images/a.jpg')
        Image.new('RGB', (8, 6), (0, 255, 0)).save(dataset / 'images/a.png')
        Image.new('RGB', (8, 6), (0, 0, 255)).save(dataset / 'images/b.png')
        (dataset / 'other').mkdir()
        (dataset / 'other/late-skip.txt').write_text('skip after first conversion')
        quality = []
        original_save = Image.Image.save
        def save(image, path, **kwargs):
            quality.append(kwargs['quality'])
            self.api.WORKER_BUNDLE_JPEG_QUALITY = 71
            self.api.WORKER_BUNDLE_SKIP_DIRS = {'other'}
            return original_save(image, path, **kwargs)
        with patch.object(self.api, 'WORKER_BUNDLE_JPEG_QUALITY', 90), patch.object(self.api, 'WORKER_BUNDLE_SKIP_DIRS', set()), patch.object(Image.Image, 'save', save):
            temp, archive = self.api.build_worker_training_bundle(dataset, 'job')
        try:
            self.assertEqual(quality, [90, 71])
            import io
            with zipfile.ZipFile(archive) as handle:
                self.assertNotIn('other/late-skip.txt', handle.namelist())
                with Image.open(io.BytesIO(handle.read('images/a.jpg'))) as image:
                    self.assertGreater(image.getpixel((4, 3))[1], 240)
                    self.assertLess(image.getpixel((4, 3))[0], 10)
        finally:
            temp.cleanup()

    def test_bundle_non_conversion_errors_propagate_and_acquired_temp_is_not_cleaned(self):
        directories = self.temporary_factory()
        dataset = self.root / 'dataset'
        (dataset / 'images').mkdir(parents=True)
        Image.new('RGB', (8, 6)).save(dataset / 'images/a.png')
        with patch.object(Image, 'open', side_effect=RuntimeError('decoder runtime error')):
            with self.assertRaisesRegex(RuntimeError, 'decoder runtime error'):
                self.api.build_worker_training_bundle(dataset, 'job')
        self.assertEqual(len(directories), 1)
        self.assertTrue(Path(directories[0].name).exists())
        directories[0].cleanup()
        with patch.object(shutil, 'make_archive', side_effect=OSError('zip creation failure')) as make:
            with self.assertRaisesRegex(OSError, 'zip creation failure'):
                self.api.package_training_dataset(dataset, 'job')
        make.assert_called_once()
        self.assertTrue(Path(directories[1].name).exists())
        directories[1].cleanup()

    def test_export_stat_reads_order_and_cleanup_override_are_preserved(self):
        bundle, archive, cleanup = self.bundle_fixture()
        original_stat = Path.stat
        events = []
        def stat(path, *args, **kwargs):
            value = original_stat(path, *args, **kwargs)
            if path.name == 'dataset.zip' and path.parent.name == 'safe-job':
                events.append('stat')
            return value
        original_copy = shutil.copy2
        def copy(source, target, *args, **kwargs):
            result = original_copy(source, target, *args, **kwargs)
            events.clear()  # Exclude filesystem internals while copying; measure the explicit later observations.
            return result
        def update(*args, **kwargs):
            events.append('update')
        self.update.side_effect = update
        with patch.object(Path, 'stat', stat), patch.object(shutil, 'copy2', side_effect=copy):
            self.api.create_runpod_training_dataset_archive('job', self.task, {})
        self.assertEqual(events, ['stat', 'stat', 'stat', 'update', 'stat'])
        cleanup.assert_called_once()
        # A cleanup exception supersedes the earlier export failure, with the original as context.
        second = self.root / 'second-bundle'
        second.mkdir()
        archive = second / 'dataset.zip'
        archive.write_bytes(b'synthetic')
        failed_cleanup = Mock(side_effect=ValueError('cleanup failed'))
        bundle.return_value = (SimpleNamespace(cleanup=failed_cleanup), archive)
        self.update.side_effect = RuntimeError('record failed')
        with self.assertRaisesRegex(ValueError, 'cleanup failed') as raised:
            self.api.create_runpod_training_dataset_archive('job', self.task, {})
        self.assertIsInstance(raised.exception.__context__, RuntimeError)
        failed_cleanup.assert_called_once()
        self.assertTrue(archive.exists())

    def test_uploaded_raw_member_order_duplicates_latest_owner_and_empty_payload(self):
        archive = self.zip(self.output_root / 'upload.zip', [
            ('a0/weights/best.pt', b'lexically-first-raw'),
            ('z/weights/best.pt', b'later-member'),
            ('a0/weights/best.pt', b'duplicate-last-value'),
        ])
        self.find.return_value = {'runpod_artifact_upload_path': str(archive), 'owner_user_id': 'bob', 'label': 'ignored-latest'}
        result = self.api.import_runpod_yolo_artifacts(self.task, {})
        self.assertEqual(Path(result['imported_model_path']).read_bytes(), b'duplicate-last-value')
        self.output.assert_called_once_with('training_runs', 'alice')
        metadata = json.loads((Path(result['training_run_dir']) / 'library_metadata.json').read_text())
        self.assertEqual(metadata['display_name'], 'Synthetic model')
        empty = self.zip(self.output_root / 'empty-payload.zip', [('weights/best.pt', b'')])
        self.find.return_value = {}
        result = self.api.import_runpod_yolo_artifacts({**self.task, 'runpod_artifact_upload_path': str(empty)}, {})
        self.assertEqual(Path(result['imported_model_path']).read_bytes(), b'')
        self.assertEqual(result['runpod_best_pt_sha256'], hashlib.sha256(b'').hexdigest())

    def test_uploaded_symlink_cannot_escape_output_directory(self):
        outside = self.zip(self.root / 'outside.zip', [('weights/best.pt', b'outside')])
        link = self.output_root / 'symlink.zip'
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest('symlink unavailable: ' + type(error).__name__)
        self.find.return_value = {'runpod_artifact_upload_path': str(link)}
        with self.assertRaisesRegex(RuntimeError, 'outside the output directory'):
            self.api.import_runpod_yolo_artifacts(self.task, {})
        self.output.assert_not_called()

    def test_member_selection_sorts_names_returned_by_zip_before_normalizing(self):
        archive = self.zip(self.output_root / 'members.zip', [('weights/best.pt', b'synthetic')])
        self.find.return_value = {'runpod_artifact_upload_path': str(archive)}
        # Windows ZipInfo normalizes backslashes itself. Substitute that boundary to
        # test the importer's distinct raw-name sorting rule on every platform.
        with patch.object(zipfile, 'ZipFile') as open_zip:
            handle = open_zip.return_value.__enter__.return_value
            handle.namelist.return_value = ['a\\weights\\best.pt', 'a0/weights/best.pt']
            handle.read.return_value = b'raw-first'
            result = self.api.import_runpod_yolo_artifacts(self.task, {})
            handle.read.assert_called_once_with('a0/weights/best.pt')
            handle.extractall.assert_not_called()
        self.assertEqual(Path(result['imported_model_path']).read_bytes(), b'raw-first')


    def test_independent_archives_exports_importers_and_zero_provider_construction(self):
        from local_inspection_service.training.dataset_archives import DatasetArchives, file_sha256
        from local_inspection_service.training.runpod_exports import RunPodExports, RunPodExportPaths, RunPodExportPolicy
        from local_inspection_service.training.runpod_artifacts import RunPodArtifacts, RunPodArtifactPaths
        directories = self.temporary_factory()
        skips, quality, digest = Mock(return_value=set()), Mock(return_value=80), Mock(side_effect=file_sha256)
        archives = DatasetArchives(self.safe, skips, quality, digest)
        exports = RunPodExports(RunPodExportPaths(lambda:self.resolve, self.output, self.safe),
                               RunPodExportPolicy(lambda token: hashlib.sha256(token.encode()).hexdigest(), self.ttl, self.public_base),
                               archives.build_worker_training_bundle, digest, lambda:self.update)
        for provider in (self.resolve, self.output, self.safe, skips, quality, digest, self.ttl, self.public_base, self.update):
            provider.assert_not_called()
        dataset = self.output_root / 'source'
        dataset.mkdir()
        (dataset / 'dataset.yaml').write_text('synthetic')
        with patch.object(self.api, 'file_sha256', side_effect=AssertionError('root digest dependency')):
            manifest = archives.dataset_file_manifest(dataset)
            result = exports.create_runpod_training_dataset_archive('independent', self.task, {'dataset_dir': 'source'})
        self.assertEqual(manifest[0]['sha256'], hashlib.sha256(b'synthetic').hexdigest())
        self.assertTrue(Path(result['path']).exists())
        self.assertEqual(len(directories), 1)
        self.assertFalse(Path(directories[0].name).exists())
        for owner in ('first', 'second'):
            finder, summary = Mock(return_value=None), Mock(return_value={'owner': owner})
            output_root = Mock(return_value=self.output_root)
            output = Mock(side_effect=lambda kind, user, owner=owner: self.output_root / owner / kind)
            importer = RunPodArtifacts(RunPodArtifactPaths(self.resolve, output_root, lambda:output), finder, summary)
            finder.assert_not_called()
            output_root.assert_not_called()
            output.assert_not_called()
            summary.assert_not_called()
            with patch.object(self.api, 'find_training_task', side_effect=AssertionError('root finder dependency')):
                imported = importer.import_runpod_yolo_artifacts(self.task, self.inline(owner.encode()))
            self.assertEqual(Path(imported['imported_model_path']).read_bytes(), owner.encode())
            self.assertTrue(Path(imported['imported_model_path']).is_relative_to(self.output_root / owner))
            finder.assert_not_called()
            output_root.assert_not_called()
            summary.assert_called_once()

    def test_acquired_bundle_cleanup_covers_output_name_copy_and_hash_failures(self):
        original_copy = shutil.copy2
        for failure in ('output', 'name', 'copy', 'hash'):
            with self.subTest(failure=failure), ExitStack() as stack:
                bundle, archive, cleanup = self.bundle_fixture()
                self.output.reset_mock(side_effect=True)
                self.safe.reset_mock(side_effect=True)
                self.token.reset_mock()
                self.update.reset_mock()
                destination = self.output_root / failure / 'runpod_training_datasets'
                self.output.return_value = destination
                if failure == 'output':
                    self.output.side_effect = [RuntimeError('output failure'), destination]
                if failure == 'name':
                    self.safe.side_effect = [RuntimeError('name failure'), 'safe-job']
                copies = stack.enter_context(patch.object(shutil, 'copy2', wraps=original_copy))
                if failure == 'copy':
                    def copy(source, target, *args, **kwargs):
                        if copies.call_count == 1:
                            raise OSError('copy failure')
                        return original_copy(source, target, *args, **kwargs)
                    copies.side_effect = copy
                digest = stack.enter_context(patch.object(self.api, 'file_sha256', wraps=self.api.file_sha256))
                if failure == 'hash':
                    digest.side_effect = [RuntimeError('hash failure'), 'would-succeed']
                with self.assertRaisesRegex((OSError, RuntimeError), failure + ' failure'):
                    self.api.create_runpod_training_dataset_archive('job', self.task, {})
                bundle.assert_called_once()
                cleanup.assert_called_once()
                self.assertFalse(archive.exists())
                self.output.assert_called_once()
                self.assertEqual(self.safe.call_count, 0 if failure == 'output' else 1)
                self.assertEqual(copies.call_count, 1 if failure in ('copy', 'hash') else 0)
                self.assertEqual(digest.call_count, 1 if failure == 'hash' else 0)
                self.assertEqual(self.token.call_count, 1 if failure == 'hash' else 0)
                self.update.assert_not_called()
                target = destination / 'safe-job'
                self.assertEqual(target.exists(), failure in ('copy', 'hash'))
                self.assertEqual((target / 'dataset.zip').exists(), failure == 'hash')
                self.assertFalse((target / 'metadata.json').exists())


    def test_export_and_import_callbacks_capture_before_arguments(self):
        api=self.api;outer=self.root
        for stage in ('resolve','owner-output','dataset-update','upload-update'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(stage=stage,mode=mode),ExitStack() as stack:
                    root=outer/(stage+'-'+mode);root.mkdir();stack.enter_context(patch.object(self,'root',root));stack.enter_context(patch.object(self,'output_root',root/'outputs'));self.output_root.mkdir();events=[]
                    field={'resolve':'resolve_service_path','owner-output':'output_write_dir_for_owner','dataset-update':'update_training_task','upload-update':'update_training_task'}[stage]
                    original={'resolve':self.resolve,'owner-output':self.output,'dataset-update':self.update,'upload-update':self.update}[stage]
                    def callback(label):
                        def call(*args,**kwargs):events.append(label);return original(*args,**kwargs)
                        return call
                    stack.enter_context(patch.object(api,field,callback('A')))
                    def before():
                        if mode!='ordinary':setattr(api,field,callback('B') if mode=='prior' else None)
                    def argument():events.append('argument');setattr(api,field,callback('C'))
                    task=dict(self.task);dataset={'dataset_dir':'fixture-dataset'}
                    if stage=='resolve':
                        class Dataset(dict):
                            def get(self,key,default=None):argument();return super().get(key,default)
                        dataset=Dataset(dataset);before();self.bundle_fixture()
                    elif stage=='owner-output':
                        class Task(dict):
                            def get(self,key,default=None):
                                if key=='owner_user_id':argument()
                                return super().get(key,default)
                        task=Task(task)
                        class Best(dict):
                            def get(self,key,default=None):
                                if key=='sha256':before()
                                return super().get(key,default)
                        output=self.inline();output['artifacts']['best_pt']=Best(output['artifacts']['best_pt'])
                    elif stage=='dataset-update':
                        self.bundle_fixture();stat=Path.stat;writes=Path.write_text;reads=[]
                        def writing(path,*args,**kwargs):
                            result=writes(path,*args,**kwargs)
                            if path.name=='metadata.json':before()
                            return result
                        def reading(path,*args,**kwargs):
                            if path.name=='dataset.zip':
                                reads.append(True)
                                if len(reads)==2:argument()
                            return stat(path,*args,**kwargs)
                        stack.enter_context(patch.object(Path,'write_text',writing));stack.enter_context(patch.object(Path,'stat',reading))
                    else:
                        class Base(str):
                            def lstrip(self,*args):argument();return super().lstrip(*args)
                        stack.enter_context(patch.object(api,'runpod_yolo_public_base_url',side_effect=lambda:before() or Base('https://fixture.invalid/'+root.name)))
                    caught=None
                    try:
                        if stage=='owner-output':api.import_runpod_yolo_artifacts(task,output)
                        elif stage=='upload-update':api.create_runpod_training_artifact_upload('job',task)
                        else:api.create_runpod_training_dataset_archive('job',task,dataset)
                    except BaseException as error:caught=error
                    self.assertIn('argument',events);after=[x for x in events[events.index('argument')+1:] if x in ('A','B','C')]
                    if mode=='missing':self.assertIsInstance(caught,TypeError);self.assertEqual(after,[])
                    else:self.assertIsNone(caught);self.assertEqual(after[0],'A' if mode=='ordinary' else 'B')


    def test_new_export_and_import_getter_failures(self):
        from dataclasses import replace
        api=self.api;outer=self.root
        for stage in ('resolve','dataset-update','upload-update','import-output','import-root'):
            with self.subTest(stage=stage),ExitStack() as stack:
                root=outer/stage;root.mkdir();stack.enter_context(patch.object(self,'root',root));stack.enter_context(patch.object(self,'output_root',root/'outputs'));self.output_root.mkdir();calls=[];failure=OSError(stage)
                if stage in ('resolve','dataset-update'):bundle,archive,cleanup=self.bundle_fixture()
                if stage=='resolve':service=api._runpod_exports;group='paths';field='resolve'
                elif stage in ('dataset-update','upload-update'):service=api._runpod_exports;group=None;field='update_provider'
                elif stage=='import-output':service=api._runpod_artifacts;group='paths';field='output'
                else:
                    service=api._runpod_artifacts;group='paths';field='output_root';stack.enter_context(patch.object(api,'OUTPUT_DIR',self.output_root));archive=self.zip(self.output_root/'uploaded.zip',[('weights/best.pt',b'fixture')]);stack.enter_context(patch.object(api,'find_training_task',return_value={'runpod_artifact_archive_path':str(archive)}))
                port=getattr(service,group) if group else service;original=getattr(port,field)
                def getter():
                    calls.append(True)
                    if len(calls)==1:raise failure
                    return original()
                if group:stack.enter_context(patch.object(service,group,replace(port,**{field:getter})))
                else:stack.enter_context(patch.object(service,field,getter))
                with self.assertRaises(BaseException) as caught:
                    if stage.startswith('import-'):api.import_runpod_yolo_artifacts(self.task,{} if stage=='import-root' else self.inline())
                    elif stage=='upload-update':api.create_runpod_training_artifact_upload('job',self.task)
                    else:api.create_runpod_training_dataset_archive('job',self.task,{'dataset_dir':'source'})
                self.assertIs(caught.exception,failure);self.assertEqual(calls,[True])
                if stage=='resolve':bundle.assert_not_called();cleanup.assert_not_called()
                if stage=='dataset-update':bundle.assert_called_once();cleanup.assert_called_once()
                if stage.startswith('import-'):self.assertFalse((self.output_root/'alice/training_runs').exists())

    def test_archive_value_getters_keep_conversion_fallback_and_escape_boundary(self):
        api=self.api;outer=self.root
        for stage in ('skip','quality-os','quality-value','quality-base'):
            with self.subTest(stage=stage),ExitStack() as stack:
                root=outer/stage;root.mkdir();stack.enter_context(patch.object(self,'root',root));dataset=root/'input';(dataset/'images').mkdir(parents=True);Image.new('RGB',(8,8),(10,20,30)).save(dataset/'images/sample.png')
                stack.enter_context(patch.object(self,'stack',stack))
                directories=self.temporary_factory();calls=[];failure=KeyboardInterrupt(stage) if stage=='quality-base' else ValueError(stage) if stage=='quality-value' else OSError(stage)
                service=api._training_dataset_archives;field='skip_dirs' if stage=='skip' else 'jpeg_quality';original=getattr(service,field)
                def getter():
                    calls.append(True)
                    if len(calls)==1:raise failure
                    return original()
                stack.enter_context(patch.object(service,field,getter))
                if stage in ('quality-os','quality-value'):
                    temporary,archive=api.build_worker_training_bundle(dataset,'job')
                    with zipfile.ZipFile(archive) as archive_file:self.assertIn('images/sample.png',archive_file.namelist());self.assertNotIn('images/sample.jpg',archive_file.namelist())
                else:
                    with self.assertRaises(BaseException) as caught:api.build_worker_training_bundle(dataset,'job')
                    self.assertIs(caught.exception,failure)
                self.assertEqual(calls,[True]);self.assertEqual(len(directories),1);self.assertTrue(Path(directories[0].name).exists())
                directories[0].cleanup()


    def test_strict_hash_first_errors_do_not_repeat_io(self):
        api=self.api;data=self.root/'hash-source';data.write_bytes(b'synthetic');original_hash=hashlib.sha256;original_open=Path.open
        for stage in ('construct','open','read','update','hexdigest'):
            with self.subTest(stage=stage),ExitStack() as stack:
                calls=[];failure=OSError(stage)
                def first(fn,*args,**kwargs):
                    calls.append(True)
                    if len(calls)==1:raise failure
                    return fn(*args,**kwargs)
                class Digest:
                    def __init__(self,*args,**kwargs):self.value=original_hash(*args,**kwargs)
                    def update(self,value):return first(self.value.update,value) if stage=='update' else self.value.update(value)
                    def hexdigest(self):return first(self.value.hexdigest) if stage=='hexdigest' else self.value.hexdigest()
                class Stream:
                    def __init__(self,value):self.value=value
                    def __enter__(self):self.value.__enter__();return self
                    def __exit__(self,*args):return self.value.__exit__(*args)
                    def read(self,*args):return first(self.value.read,*args)
                def opening(path,*args,**kwargs):
                    if path==data:
                        if stage=='open':return first(original_open,path,*args,**kwargs)
                        if stage=='read':return Stream(original_open(path,*args,**kwargs))
                    return original_open(path,*args,**kwargs)
                stack.enter_context(patch.object(Path,'open',opening))
                stack.enter_context(patch.object(hashlib,'sha256',lambda *a,**kw:first(original_hash,*a,**kw) if stage=='construct' else Digest(*a,**kw)))
                with self.assertRaises(BaseException) as caught:api.file_sha256(data)
                self.assertIs(caught.exception,failure);self.assertEqual(calls,[True])

    def test_packaging_and_manifest_first_errors_keep_acquired_directories(self):
        api=self.api;outer=self.root
        cases=[('plain',s) for s in ('exists','is_dir','name','temporary')]+[('worker',s) for s in ('exists','is_dir','name','temporary','staging-mkdir','target-mkdir','image-mkdir','scan','is_file','relative','copy','archive','image-open','convert')]+[('manifest',s) for s in ('scan','is_file','digest')]
        for kind,stage in cases:
            with self.subTest(kind=kind,stage=stage),ExitStack() as stack:
                root=outer/(kind+'-'+stage);root.mkdir();stack.enter_context(patch.object(self,'root',root));stack.enter_context(patch.object(self,'stack',stack));dataset=root/'input';dataset.mkdir();image_case=stage in ('image-mkdir','image-open','convert')
                if image_case:(dataset/'images').mkdir();source=dataset/'images/sample.png';Image.new('RGB',(8,8)).save(source)
                else:source=dataset/'note.txt';source.write_text('fixture')
                directories=self.temporary_factory();calls=[];failure=RuntimeError(kind+'-'+stage);mkdir_calls=[]
                def first(fn,*args,**kwargs):
                    calls.append(True)
                    if len(calls)==1:raise failure
                    return fn(*args,**kwargs)
                path_method={'exists':'exists','is_dir':'is_dir','scan':'rglob','is_file':'is_file','relative':'relative_to'}.get(stage)
                if path_method:
                    original=getattr(Path,path_method)
                    def method(path,*args,**kwargs):
                        target=source if stage in ('is_file','relative') else dataset
                        return first(original,path,*args,**kwargs) if path==target else original(path,*args,**kwargs)
                    stack.enter_context(patch.object(Path,path_method,method))
                elif 'mkdir' in stage:
                    original=Path.mkdir
                    def mkdir(path,*args,**kwargs):
                        if path!=dataset:
                            mkdir_calls.append(True)
                            target=1 if stage=='staging-mkdir' else 2
                            if len(mkdir_calls)==target:return first(original,path,*args,**kwargs)
                        return original(path,*args,**kwargs)
                    stack.enter_context(patch.object(Path,'mkdir',mkdir))
                elif stage=='convert':
                    original=Image.Image.convert;stack.enter_context(patch.object(Image.Image,'convert',lambda *a,**kw:first(original,*a,**kw)))
                else:
                    target,field={'name':(api,'safe_name'),'temporary':(tempfile,'TemporaryDirectory'),'copy':(shutil,'copy2'),'archive':(shutil,'make_archive'),'image-open':(Image,'open'),'digest':(api,'file_sha256')}[stage];original=getattr(target,field);stack.enter_context(patch.object(target,field,lambda *a,**kw:first(original,*a,**kw)))
                with self.assertRaises(BaseException) as caught:
                    if kind=='plain':api.package_training_dataset(dataset,'job')
                    elif kind=='worker':api.build_worker_training_bundle(dataset,'job')
                    else:api.dataset_file_manifest(dataset)
                self.assertIs(caught.exception,failure);self.assertEqual(calls,[True])
                acquired=kind!='manifest' and stage not in ('exists','is_dir','name','temporary')
                self.assertEqual(len(directories),int(acquired))
                for directory in directories:self.assertTrue(Path(directory.name).exists());directory.cleanup()


    def test_export_first_errors_preserve_cleanup_and_write_order(self):
        import time,secrets
        api=self.api;outer=self.root
        dataset_stages=('bundle','exists','mkdir','token','token-hash','base','write','remove','ttl','json','clock-1','quote-1','quote-2','stat-1','clock-2','stat-4','stat-2','urlsplit','stat-3')
        upload_stages=('exists','mkdir','token','token-hash','base','output','remove','ttl','clock-1','quote-1','quote-2','urlsplit')
        for kind,stage in [('dataset',x) for x in dataset_stages]+[('upload',x) for x in upload_stages]:
            with self.subTest(kind=kind,stage=stage),ExitStack() as stack:
                root=outer/(kind+'-'+stage);root.mkdir();stack.enter_context(patch.object(self,'root',root));stack.enter_context(patch.object(self,'stack',stack));stack.enter_context(patch.object(self,'output_root',root/'outputs'));self.output_root.mkdir();self.update.reset_mock();calls=[];failure=OSError(kind+'-'+stage)
                target_dir=self.output_root/('alice/runpod_training_datasets/safe-job' if kind=='dataset' else 'alice/runpod_training_artifacts/job')
                if stage=='remove':target_dir.mkdir(parents=True);(target_dir/'old.txt').write_text('old')
                if kind=='dataset':bundle,archive,cleanup=self.bundle_fixture()
                fail_at=int(stage[-1]) if stage.startswith(('clock-','quote-','stat-')) else 1
                def first(fn,*args,**kwargs):
                    calls.append(True)
                    if len(calls)==fail_at:raise failure
                    return fn(*args,**kwargs)
                if stage in ('exists','mkdir') or stage.startswith('stat-') or stage=='write':
                    field='stat' if stage.startswith('stat-') else 'write_text' if stage=='write' else stage;original=getattr(Path,field)
                    def method(path,*args,**kwargs):
                        applies=path==target_dir if stage in ('exists','mkdir') else path==target_dir/('metadata.json' if stage=='write' else 'dataset.zip')
                        return first(original,path,*args,**kwargs) if applies else original(path,*args,**kwargs)
                    stack.enter_context(patch.object(Path,field,method))
                else:
                    target,field=(time,'time') if stage.startswith('clock-') else (api,'quote') if stage.startswith('quote-') else {'bundle':(api,'build_worker_training_bundle'),'token':(secrets,'token_urlsafe'),'token-hash':(api,'runpod_dataset_token_hash'),'base':(api,'runpod_yolo_public_base_url'),'remove':(shutil,'rmtree'),'ttl':(api,'runpod_yolo_dataset_token_ttl_seconds'),'json':(json,'dumps'),'urlsplit':(api,'urlsplit'),'output':(api,'output_write_dir_for_owner')}[stage]
                    original=getattr(target,field)
                    def method(*args,**kwargs):return first(original,*args,**kwargs)
                    stack.enter_context(patch.object(target,field,method))
                    if stage.startswith('quote-') or stage=='urlsplit':
                        module=sys.modules.get('local_inspection_service.training.runpod_exports')
                        if module:stack.enter_context(patch.object(module,field,method))
                with self.assertRaises(BaseException) as caught:
                    if kind=='dataset':api.create_runpod_training_dataset_archive('job',self.task,{'dataset_dir':'source'})
                    else:api.create_runpod_training_artifact_upload('job',self.task)
                self.assertIs(caught.exception,failure);self.assertEqual(len(calls),fail_at)
                self.assertEqual(self.update.call_count,int(kind=='dataset' and stage=='stat-4'))
                if kind=='dataset':self.assertEqual(cleanup.call_count,int(stage!='bundle'))
                if stage=='remove':self.assertEqual((target_dir/'old.txt').read_text(),'old')


    def test_import_first_errors_preserve_partial_files_without_retry(self):
        import time
        api=self.api;outer=self.root
        stages=('hash','hexdigest','mkdir','resolve-path','json','base64','find','resolve-service','clock-1','clock-2','exists','is_file','zip','read','namelist')
        for stage in stages:
            with self.subTest(stage=stage),ExitStack() as stack:
                root=outer/stage;root.mkdir();stack.enter_context(patch.object(self,'root',root));stack.enter_context(patch.object(self,'output_root',root/'outputs'));self.output_root.mkdir();stack.enter_context(patch.object(api,'OUTPUT_DIR',self.output_root))
                archive_path=self.zip(self.output_root/'upload.zip',[('model/weights/best.pt',b'synthetic-model-bytes')])
                self.find.return_value={'runpod_artifact_archive_path':'upload.zip' if stage=='resolve-service' else str(archive_path)}
                output=self.inline() if stage=='base64' else {};run_dir=self.output_root/'alice/training_runs/job';calls=[];failure=OSError(stage)
                fail_at=2 if stage=='clock-2' else 1
                def first(fn,*args,**kwargs):
                    calls.append(True)
                    if len(calls)==fail_at:raise failure
                    return fn(*args,**kwargs)
                if stage in ('mkdir','resolve-path','exists','is_file'):
                    field='resolve' if stage=='resolve-path' else stage;original=getattr(Path,field)
                    def method(path,*args,**kwargs):
                        applies=path==run_dir/'weights' if stage=='mkdir' else path==archive_path
                        return first(original,path,*args,**kwargs) if applies else original(path,*args,**kwargs)
                    stack.enter_context(patch.object(Path,field,method))
                elif stage=='hexdigest':
                    original=hashlib.sha256
                    class Digest:
                        def __init__(self,*args,**kwargs):self.value=original(*args,**kwargs)
                        def hexdigest(self):return first(self.value.hexdigest)
                    stack.enter_context(patch.object(hashlib,'sha256',Digest))
                else:
                    target,field=(time,'time') if stage.startswith('clock-') else {'hash':(hashlib,'sha256'),'json':(json,'dumps'),'base64':(base64,'b64decode'),'find':(api,'find_training_task'),'resolve-service':(api,'resolve_service_path'),'zip':(zipfile,'ZipFile'),'read':(zipfile.ZipFile,'read'),'namelist':(zipfile.ZipFile,'namelist')}[stage]
                    original=getattr(target,field)
                    def method(*args,**kwargs):return first(original,*args,**kwargs)
                    stack.enter_context(patch.object(target,field,method))
                with self.assertRaises(BaseException) as caught:api.import_runpod_yolo_artifacts(self.task,output)
                self.assertIs(caught.exception,failure);self.assertEqual(len(calls),fail_at)
                # Before metadata serialization the original importer already wrote the model and ZIP.
                files={p.relative_to(run_dir).as_posix() for p in run_dir.rglob('*') if p.is_file()} if run_dir.exists() else set()
                expected={'weights/best.pt','runpod_artifacts.zip'} if stage in ('clock-1','json','clock-2') else set()
                if stage=='clock-2':expected|={'library_metadata.json','runpod_result.json'}
                self.assertEqual(files,expected)


if __name__ == '__main__':
    unittest.main()

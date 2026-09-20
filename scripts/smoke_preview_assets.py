"""Offline original contracts for preview asset loading."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock,patch,call
sys.path.insert(0,str(Path.cwd()))
class PreviewAssetsContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='preview-assets-')))
        (cls.root/'local_inspection_service/static').mkdir(parents=True)
        for name in ('DATABASE_URL','VANTALINE_POSTGRES_DSN','PGDSN'):os.environ.pop(name,None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(cls.root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false',YOLO_AUTOINSTALL='false')
        for name in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):
            cls.lifetime.enter_context(patch(name,side_effect=AssertionError('External operation forbidden')))
        from types import SimpleNamespace
        cls.import_factory=Mock(side_effect=AssertionError('Eager model load forbidden'));cls.import_remove=Mock(side_effect=AssertionError('Eager inference forbidden'))
        cls.lifetime.enter_context(patch.dict(sys.modules,{'rembg':SimpleNamespace(new_session=cls.import_factory,remove=cls.import_remove)}))
        from local_inspection_service import server
        cls.import_factory.assert_not_called();cls.import_remove.assert_not_called()
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.lifetime.close()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
    def replace(self,name,**kwargs):return self.stack.enter_context(patch.object(self.api,name,**kwargs))
    def image(self):
        import numpy as np
        return np.zeros((3, 5, 3), dtype=np.uint8)

    def asset_path(self, name='sample.PNG'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'synthetic')
        return path

    def decoder(self, **kwargs):
        import cv2
        return self.stack.enter_context(patch.object(cv2, 'imread', **kwargs))

    def test_default_asset_precedence_and_case(self):
        base = Path('/synthetic-root')
        self.replace('ROOT', new=base)
        expected = [('WARRANTY battery', 'manual_from_2_warranty_service_precise_1240x1754.png'),
                    ('BATTERY download', 'manual_from_3_battery_instruction_precise_1240x1754.png'),
                    ('DOWNLOAD service', 'manual_from_4_download_service_precise_1240x1754.png'),
                    ('QR bottle', 'manual_from_6_service_qr_precise_1240x1754.png')]
        for name, filename in expected:
            self.assertEqual(self.api.default_asset_for_accessory({'name': name}), base / 'standardized_manuals' / filename)
        self.assertEqual(self.api.default_asset_for_accessory({'name': 'BOTTLE'}), base / 'generated_bottle_pose_collection' / 'overhead_bottle_pose_collection_image2.png')
        self.assertIsNone(self.api.default_asset_for_accessory({}))

    def test_document_candidate_rejects_missing_and_suffix(self):
        decode = self.decoder(side_effect=AssertionError('decode forbidden'))
        for path in [None, self.root / 'missing.png', self.asset_path('unsupported.txt')]:
            self.replace('resolve_service_path', return_value=path)
            self.assertIsNone(self.api.load_document_image_candidate('input', {}))
        decode.assert_not_called()

    def test_document_candidate_null_decode(self):
        path = self.asset_path()
        self.replace('resolve_service_path', return_value=path)
        decode = self.decoder(return_value=None)
        self.assertIsNone(self.api.load_document_image_candidate('input', {}))
        decode.assert_called_once_with(str(path), self.api.cv2.IMREAD_COLOR)

    def test_document_candidate_dimensions_and_shallow_copy(self):
        path = self.asset_path(); image = self.image(); nested = []
        self.replace('resolve_service_path', return_value=path); self.decoder(return_value=image)
        original = {'width': '9', 'height': 0, 'nested': nested, 'asset_path': 'old', 'source_image_size_px': ['old']}
        actual, metadata = self.api.load_document_image_candidate('input', original)
        self.assertIs(actual, image)
        self.assertEqual(metadata['canonical_asset_dimensions_px'], [9, 3])
        self.assertEqual(metadata['source_image_size_px'], [5, 3])
        self.assertEqual(metadata['asset_path'], str(path))
        self.assertIs(metadata['nested'], nested)
        self.assertEqual(original['asset_path'], 'old')
        self.assertIsNot(metadata, original)

    def test_document_candidate_decode_exception_identity(self):
        path = self.asset_path(); error = RuntimeError('synthetic decode')
        self.replace('resolve_service_path', return_value=path); self.decoder(side_effect=error)
        with self.assertRaises(RuntimeError) as caught:
            self.api.load_document_image_candidate('input', {})
        self.assertIs(caught.exception, error)

    def test_selection_empty_and_single_skip_rng(self):
        rng = Mock(); image = self.image(); original = {'nested': []}
        self.assertIsNone(self.api.select_document_image_candidate([], rng, multi_policy='multi', single_policy='single'))
        actual, metadata = self.api.select_document_image_candidate([(image, original)], rng, multi_policy='multi', single_policy='single')
        self.assertIs(actual, image)
        self.assertEqual(metadata['document_asset_selection_policy'], 'single')
        self.assertEqual([metadata['document_asset_index'], metadata['document_asset_count']], [0, 1])
        self.assertIs(metadata['nested'], original['nested'])
        self.assertIsNot(metadata, original)
        rng.integers.assert_not_called()

    def test_selection_multiple_rng_and_no_rng(self):
        a = self.image(); b = self.image(); candidates = [(a, {'name': 'a'}), (b, {'name': 'b'})]
        rng = Mock(); rng.integers.return_value = 1
        image, metadata = self.api.select_document_image_candidate(candidates, rng, multi_policy='multi', single_policy='single')
        rng.integers.assert_called_once_with(0, 2)
        self.assertIs(image, b)
        self.assertEqual([metadata['document_asset_index'], metadata['document_asset_count'], metadata['document_asset_selection_policy']], [1, 2, 'multi'])
        image, metadata = self.api.select_document_image_candidate(candidates, None, multi_policy='multi', single_policy='single')
        self.assertIs(image, a)
        self.assertEqual(metadata['document_asset_selection_policy'], 'multi')
        self.assertEqual(candidates[1][1], {'name': 'b'})

    def test_preview_normalized_mutates_path_before_decode(self):
        path = self.asset_path(); image = self.image(); asset = {'path': 'old', 'width': '11', 'height': 0, 'kind': 'custom', 'method': 'existing'}
        self.replace('resolve_service_path', return_value=path)
        def decode(value, mode):
            self.assertEqual(asset['path'], str(path))
            return image
        self.decoder(side_effect=decode)
        fallback = self.replace('default_asset_for_accessory', side_effect=AssertionError('fallback forbidden'))
        actual, metadata = self.api.load_preview_asset_with_metadata({'normalized_assets': [asset]})
        self.assertIs(actual, image)
        self.assertEqual(metadata, {'asset_path': str(path), 'asset_kind': 'custom', 'asset_method': 'existing', 'asset_source': 'normalized_assets', 'source_image_size_px': [5, 3], 'canonical_asset_dimensions_px': [11, 3]})
        fallback.assert_not_called()

    def test_preview_null_normalized_falls_back_to_source(self):
        first = self.asset_path('first.png'); second = self.asset_path('second.jpg'); image = self.image(); asset = {'path': 'first'}
        self.replace('resolve_service_path', side_effect=[first, second]); decode = self.decoder(side_effect=[None, image])
        actual, metadata = self.api.load_preview_asset_with_metadata({'normalized_assets': [asset], 'source_files': ['second']})
        self.assertIs(actual, image)
        self.assertEqual(asset['path'], str(first))
        self.assertEqual([metadata['asset_kind'], metadata['asset_method'], metadata['asset_source']], ['source_image', 'source_file_direct', 'source_files'])
        self.assertEqual(decode.call_count, 2)

    def test_preview_default_and_no_result(self):
        path = self.asset_path(); image = self.image(); self.replace('default_asset_for_accessory', return_value=path)
        decode = self.decoder(side_effect=[image, None])
        actual, metadata = self.api.load_preview_asset_with_metadata({})
        self.assertIs(actual, image)
        self.assertEqual([metadata['asset_kind'], metadata['asset_method'], metadata['asset_source']], ['default_image', 'default_asset_direct', 'default_asset'])
        self.assertIsNone(self.api.load_preview_asset_with_metadata({}))
        self.assertEqual(decode.call_count, 2)

    def test_preview_adapter_keeps_image_identity(self):
        image = self.image(); load = self.replace('load_preview_asset_with_metadata', side_effect=[(image, {}), None]); item = {}
        self.assertIs(self.api.load_preview_asset(item), image)
        self.assertIsNone(self.api.load_preview_asset(item))
        self.assertEqual(load.call_args_list, [call(item), call(item)])

    def test_rectified_canonical_priority_preserves_source_index(self):
        image = self.image(); rng = Mock(); loaded = (image, {'width': '7'})
        load = self.replace('load_document_image_candidate', return_value=loaded)
        selected = (image, {'selected': True}); select = self.replace('select_document_image_candidate', return_value=selected)
        item = {'normalized_assets': [{'kind': 'other', 'path': 'skip'}, {'kind': 'canonical_text_image', 'path': 'chosen', 'width': 7, 'height': 8, 'method': 'existing'}]}
        self.assertIs(self.api.load_rectified_document_asset_with_metadata(item, rng), selected)
        load.assert_called_once_with('chosen', {'asset_kind': 'canonical_text_image', 'asset_method': 'existing', 'asset_source': 'normalized_assets', 'document_asset_source_index': 1, 'width': 7, 'height': 8})
        select.assert_called_once_with([loaded], rng, multi_policy='seeded_uniform_canonical_text_image', single_policy='single_canonical_text_image')

    def test_rectified_normalized_fallback_retries_candidate(self):
        image = self.image(); loaded = (image, {}); item = {'normalized_assets': [{'kind': 'canonical_text_image', 'path': 'a'}, {'kind': 'other', 'path': 'b'}]}
        load = self.replace('load_document_image_candidate', side_effect=[None, None, loaded])
        result = (image, {'done': True}); select = self.replace('select_document_image_candidate', side_effect=[None, result])
        self.assertIs(self.api.load_rectified_document_asset_with_metadata(item), result)
        self.assertEqual([c.args[0] for c in load.call_args_list], ['a', 'a', 'b'])
        self.assertEqual(select.call_args_list[1], call([loaded], None, multi_policy='seeded_uniform_normalized_document_image_fallback', single_policy='single_normalized_document_image_fallback'))

    def test_rectified_source_filter_and_policy(self):
        path = self.asset_path('page_rectified.png'); ignored = self.asset_path('page_Rectified.png'); loaded = (self.image(), {})
        self.replace('resolve_service_path', side_effect=[ignored, path]); load = self.replace('load_document_image_candidate', return_value=loaded)
        select = self.replace('select_document_image_candidate', side_effect=[None, None, loaded])
        self.assertIs(self.api.load_rectified_document_asset_with_metadata({'source_files': ['ignored', 'chosen']}), loaded)
        load.assert_called_once_with(path, {'asset_kind': 'rectified_source_image', 'asset_method': 'manual_rectified_source_direct', 'asset_source': 'source_files_rectified'})
        self.assertEqual(select.call_args_list[2], call([loaded], None, multi_policy='seeded_uniform_rectified_source_image', single_policy='single_rectified_source_image'))

    def test_rectified_default_requires_manual_directory(self):
        image = self.image(); path = self.asset_path('standardized_manuals/default.png')
        self.replace('select_document_image_candidate', return_value=None); default = self.replace('default_asset_for_accessory', side_effect=[self.asset_path('elsewhere/default.png'), path]); decode = self.decoder(return_value=image)
        self.assertIsNone(self.api.load_rectified_document_asset_with_metadata({}))
        decode.assert_not_called()
        actual, metadata = self.api.load_rectified_document_asset_with_metadata({})
        self.assertIs(actual, image)
        self.assertEqual(metadata, {'asset_path': str(path), 'asset_kind': 'standardized_document_default', 'asset_method': 'standardized_rectified_default_direct', 'asset_source': 'standardized_default_asset', 'source_image_size_px': [5, 3], 'canonical_asset_dimensions_px': [5, 3], 'document_asset_index': 0, 'document_asset_count': 1, 'document_asset_selection_policy': 'standardized_document_default'})
        self.assertEqual(default.call_count, 2)

    def test_document_suffix_is_read_after_path_exists(self):
        image = self.image(); path = Mock(); path.suffix = '.special'
        self.replace('IMAGE_REFERENCE_SUFFIXES', new={'.png'})
        def exists():
            self.api.IMAGE_REFERENCE_SUFFIXES = {'.special'}
            return True
        path.exists.side_effect = exists
        self.replace('resolve_service_path', return_value=path); self.decoder(return_value=image)
        actual, metadata = self.api.load_document_image_candidate('input', {})
        self.assertIs(actual, image)
        self.assertEqual(metadata['asset_path'], str(path))
        path.exists.assert_called_once_with()

    def test_rectified_loader_selected_before_asset_get_effect(self):
        loaded = (self.image(), {})
        old = self.replace('load_document_image_candidate', return_value=loaded)
        late = Mock(return_value=loaded)
        api = self.api
        class Asset(dict):
            def get(self, key, default=None):
                if key == 'path':
                    api.load_document_image_candidate = late
                return super().get(key, default)
        select = self.replace('select_document_image_candidate', return_value=loaded)
        asset = Asset(kind='canonical_text_image', path='synthetic')
        self.assertIs(self.api.load_rectified_document_asset_with_metadata({'normalized_assets': [asset]}), loaded)
        old.assert_called_once_with('synthetic', {'asset_kind': 'canonical_text_image', 'asset_method': None, 'asset_source': 'normalized_assets', 'document_asset_source_index': 0, 'width': None, 'height': None})
        late.assert_not_called()
        select.assert_called_once_with([loaded], None, multi_policy='seeded_uniform_canonical_text_image', single_policy='single_canonical_text_image')

    def test_preview_failed_decode_refreshes_default_lookup(self):
        first = self.asset_path('failed.png'); fallback = self.asset_path('fallback.png'); image = self.image()
        self.replace('resolve_service_path', return_value=first)
        old = self.replace('default_asset_for_accessory', side_effect=AssertionError('stale lookup'))
        late = Mock(return_value=fallback)
        def decode(path, mode):
            if path == str(first):
                self.api.default_asset_for_accessory = late
                return None
            return image
        self.decoder(side_effect=decode)
        item = {'normalized_assets': [{'path': 'failed'}]}
        actual, metadata = self.api.load_preview_asset_with_metadata(item)
        self.assertIs(actual, image)
        self.assertEqual(metadata['asset_path'], str(fallback))
        old.assert_not_called()
        late.assert_called_once_with(item)

    def test_two_asset_loaders_keep_dependencies_separate(self):
        from local_inspection_service.accessories.preview_assets import PreviewAssetLoader
        from local_inspection_service.accessories.preview_asset_ports import PreviewAssetPolicy, PreviewAssetPaths, PreviewAssetOperations
        import numpy as np
        names = ['ROOT', 'IMAGE_REFERENCE_SUFFIXES', 'resolve_service_path', 'default_asset_for_accessory', 'load_document_image_candidate', 'select_document_image_candidate', 'load_preview_asset_with_metadata']
        poisons = {name: self.replace(name, new=Mock(side_effect=AssertionError('root ' + name))) for name in names}
        def build(tag, value):
            root = self.root / tag
            path = root / 'standardized_manuals' / 'manual_from_2_warranty_service_precise_1240x1754.png'
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'synthetic')
            image = np.full((3, 5, 3), value, dtype=np.uint8)
            loaded = (image, {'tag': tag})
            ops = {'resolve': Mock(return_value=path), 'default': Mock(return_value=path), 'candidate': Mock(return_value=loaded), 'select': Mock(side_effect=lambda values, rng, **kwargs: values[0] if values else None), 'preview': Mock(return_value=loaded)}
            getters = {name: Mock(return_value=value) for name, value in {'root': root, 'suffixes': {'.png'}, **ops}.items()}
            service = PreviewAssetLoader(PreviewAssetPolicy(getters['root'], getters['suffixes']), PreviewAssetPaths(getters['resolve']), PreviewAssetOperations(getters['default'], getters['candidate'], getters['select'], getters['preview']))
            for getter in getters.values(): getter.assert_not_called()
            return service, ops, path, image, loaded
        a = build('asset-a', 30); b = build('asset-b', 70)
        images = {str(a[2]): a[3], str(b[2]): b[3]}
        decode = self.decoder(side_effect=lambda path, mode: images[path])
        for service, ops, path, image, loaded in (a, b, a):
            self.assertEqual(service.default_asset_for_accessory({'name': 'warranty'}), path)
            actual, metadata = service.load_preview_asset_with_metadata({'normalized_assets': [{'path': 'synthetic'}]})
            self.assertIs(actual, image); self.assertEqual(metadata['asset_path'], str(path))
            actual, metadata = service.load_document_image_candidate('synthetic', {'width': 8})
            self.assertIs(actual, image); self.assertEqual(metadata['canonical_asset_dimensions_px'], [8, 3])
            actual, metadata = service.load_preview_asset_with_metadata({})
            self.assertIs(actual, image); self.assertEqual(metadata['asset_source'], 'default_asset')
            self.assertIs(service.load_rectified_document_asset_with_metadata({'normalized_assets': [{'kind': 'canonical_text_image', 'path': 'synthetic'}]}), loaded)
            self.assertIs(service.load_preview_asset({}), image)
            ops['default'].assert_called_with({}); ops['preview'].assert_called_with({})
        self.assertEqual([a[1]['resolve'].call_count, b[1]['resolve'].call_count], [4, 2])
        self.assertEqual([a[1]['candidate'].call_count, b[1]['candidate'].call_count], [2, 1])
        self.assertEqual([a[1]['select'].call_count, b[1]['select'].call_count], [2, 1])
        self.assertEqual(decode.call_count, 9)
        for poison in poisons.values(): poison.assert_not_called()

if __name__=='__main__': unittest.main()

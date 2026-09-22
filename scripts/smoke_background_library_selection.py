"""Offline original contracts for background-library selection."""

import os

from pathlib import Path

import sys

import tempfile

import unittest
import numpy as np
import cv2

from contextlib import ExitStack

from unittest.mock import Mock,patch,call

sys.path.insert(0,str(Path.cwd()))

class BackgroundLibrarySelectionContracts(unittest.TestCase):

    @classmethod

    def setUpClass(cls):

        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))

        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='background-library-selection-')))

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

    def catalog_fixture(self, sets=None, directory_names=()):
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory(dir=self.root)))
        self.meta = {'owner_user_id': 'owner'}
        self.manifest = {'sets': {'one': self.meta} if sets is None else sets}
        self.load = self.replace('load_background_sets_manifest', return_value=self.manifest)
        self.dirs = self.replace('background_set_dirs', return_value=[self.directory / n for n in directory_names])
        self.safe = self.replace('safe_background_set_id', side_effect=lambda value: str(value).replace(' ', '_'))
        self.original_visibility = self.api.background_set_visible_for_owner
        self.visible = self.replace('background_set_visible_for_owner', return_value=True)
        self.images = self.replace('image_file_list', side_effect=lambda path: [path / 'first.png', path / 'second.png'])
        self.resolve = self.replace('resolve_service_path', side_effect=lambda value: Path(value) if value else self.directory / 'missing')
        self.replace('BACKGROUND_SETS_DIR', new=self.directory)
        self.replace('IMAGE_REFERENCE_SUFFIXES', new={'.png'})
        self.replace('PIPELINE_BG_MATCH_MAX_LIBRARY_IMAGES', new=48)

    def matcher_fixture(self, candidates=None):
        self.item = {'id': 'synthetic'}
        self.box = [1, 2, 3, 4]
        self.source = {'source_path': 'capture.png', 'box_xyxy': self.box}
        self.references = self.replace('background_reference_signatures_from_accessory', return_value=[self.source])
        self.candidates = self.replace('background_library_image_candidates', return_value=(candidates if candidates is not None else [('one', Path('one.png'), {'generation_method': 'synthetic'})]))
        self.image = np.zeros((4, 4, 3), dtype=np.uint8)
        self.read = self.stack.enter_context(patch.object(self.api.cv2, 'imread', return_value=self.image))
        self.boxes = self.replace('background_patch_boxes', return_value=[(0, 0, 2, 2)])
        self.signature = self.replace('background_patch_signature', side_effect=lambda image: {'shape': image.shape})
        self.distance = self.replace('background_signature_distance', return_value=0.1)
        self.replace('PIPELINE_BG_MATCH_DISTANCE_THRESHOLD', new=0.2)

    def test_visibility_owners_and_list_only_sharing(self):
        self.replace('SYSTEM_OWNER_ID', new='system-test')
        self.replace('LEGACY_OWNER_ID', new='legacy-test')
        for owner in ('', None, 'owner', 'system-test', 'legacy-test'):
            with self.subTest(owner=owner):
                self.assertTrue(self.api.background_set_visible_for_owner({'owner_user_id': owner}, 'owner'))
        for shared in (['*'], ['owner']):
            self.assertTrue(self.api.background_set_visible_for_owner({'owner_user_id': 'other', 'shared_with_user_ids': shared}, 'owner'))
        for shared in ('*', ('owner',), {'owner'}, [], None):
            with self.subTest(shared=repr(shared)):
                self.assertFalse(self.api.background_set_visible_for_owner({'owner_user_id': 'other', 'shared_with_user_ids': shared}, 'owner'))

    def test_visibility_repeated_metadata_gets_and_error(self):
        class Metadata(dict):
            def __init__(self): super().__init__(); self.reads=[]
            def get(self, name):
                self.reads.append(name)
                return 'other' if name == 'owner_user_id' else ['owner']
        meta=Metadata()
        self.assertTrue(self.api.background_set_visible_for_owner(meta, 'owner'))
        self.assertEqual(meta.reads, ['owner_user_id', 'shared_with_user_ids', 'shared_with_user_ids'])
        with self.assertRaises(AttributeError): self.api.background_set_visible_for_owner(None, 'owner')

    def test_catalog_sorted_union_task_skip_and_metadata_alias(self):
        a={'marker':'a'};z={'marker':'z'}
        self.catalog_fixture({'z':z,'a':a,'task_plate_private':{}}, ('b','a'))
        rows=self.api.background_library_image_candidates('owner')
        self.assertEqual([r[0] for r in rows], ['a','a','b','b','z','z'])
        self.assertIs(rows[0][2], a);self.assertIs(rows[-1][2], z)
        self.assertEqual([c.args[0].name for c in self.images.call_args_list], ['a','b','z'])
        self.assertEqual([c.args[1] for c in self.visible.call_args_list], ['owner']*3)

    def test_catalog_sanitized_collision_and_non_mapping_sets(self):
        meta={'marker':'raw'}
        self.catalog_fixture({'raw bad':meta}, ('raw bad',))
        rows=self.api.background_library_image_candidates('owner')
        self.assertEqual([r[0] for r in rows], ['raw_bad']*4)
        self.assertIs(rows[0][2],meta);self.assertEqual(rows[2][2],{})
        self.manifest['sets']=['ignored']
        rows=self.api.background_library_image_candidates('owner')
        self.assertEqual(len(rows),2);self.assertEqual(rows[0][2],{})

    def test_catalog_denied_set_avoids_images_and_source_resolution(self):
        self.catalog_fixture();self.visible.return_value=False
        self.assertEqual(self.api.background_library_image_candidates('owner'),[])
        self.images.assert_not_called();self.resolve.assert_not_called()

    def test_catalog_source_prepend_resolved_dedup_and_slice_eight(self):
        self.catalog_fixture()
        source=self.directory/'source.PNG';source.touch();self.meta['source']=str(source)
        original=[self.directory/'.'/'source.PNG']+[self.directory/f'{i}.png' for i in range(10)]
        self.images.side_effect=None;self.images.return_value=original
        rows=self.api.background_library_image_candidates('owner')
        self.assertEqual([r[1] for r in rows],[source]+original[1:8])
        self.assertEqual(len(rows),8);self.assertEqual(len(original),11)
        self.assertIs(rows[0][2],self.meta)

    def test_catalog_missing_or_bad_suffix_not_prepended(self):
        self.catalog_fixture();source=self.directory/'source.jpg';source.touch()
        self.meta['source']=str(source)
        self.assertEqual(len(self.api.background_library_image_candidates('owner')),2)
        self.meta['source']=str(self.directory/'absent.png')
        self.assertEqual(len(self.api.background_library_image_candidates('owner')),2)

    def test_catalog_global_cap_zero_one_and_boundary(self):
        self.catalog_fixture({'a':{},'b':{}})
        for limit,expected in ((0,1),(1,1),(2,2),(3,3)):
            with patch.object(self.api,'PIPELINE_BG_MATCH_MAX_LIBRARY_IMAGES',limit):
                rows=self.api.background_library_image_candidates('owner')
            self.assertEqual(len(rows),expected)
            self.assertEqual(rows[0][0],'a')

    def test_catalog_errors_escape_and_late_policy_lookup(self):
        self.catalog_fixture()
        def images(path):
            self.api.PIPELINE_BG_MATCH_MAX_LIBRARY_IMAGES=1
            return [path/'a.png',path/'b.png']
        self.images.side_effect=images
        self.assertEqual(len(self.api.background_library_image_candidates('owner')),1)
        error=RuntimeError('synthetic source failure');self.resolve.side_effect=error
        with self.assertRaises(RuntimeError) as caught:self.api.background_library_image_candidates('owner')
        self.assertIs(caught.exception,error)

    def test_match_no_sources_avoids_candidates(self):
        self.matcher_fixture();self.references.return_value=[]
        self.assertIsNone(self.api.match_background_library_plate(self.item,'owner'))
        self.candidates.assert_not_called();self.read.assert_not_called()

    def test_match_unreadable_and_empty_signatures(self):
        self.matcher_fixture();self.read.return_value=None
        self.assertIsNone(self.api.match_background_library_plate(self.item,'owner'))
        self.boxes.assert_not_called()
        self.read.return_value=self.image;self.signature.side_effect=None;self.signature.return_value=None
        self.assertIsNone(self.api.match_background_library_plate(self.item,'owner'))
        self.assertEqual(self.signature.call_count,2);self.distance.assert_not_called()

    def test_match_patch_then_whole_projection_and_result_aliases(self):
        self.matcher_fixture();self.distance.side_effect=[0.15,0.1]
        result=self.api.match_background_library_plate(self.item,'owner')
        self.assertEqual([c.args[0].shape for c in self.signature.call_args_list],[(2,2,3),(4,4,3)])
        self.assertEqual(result,{'background_set_id':'one','image_path':'one.png','distance':0.1,'threshold':0.2,'source_path':'capture.png','source_box_xyxy':self.box,'generation_method':'synthetic'})
        self.assertIs(result['source_box_xyxy'],self.box)
        self.boxes.assert_called_once_with(4,4)
        self.assertIs(self.references.call_args.args[0],self.item)
        self.candidates.assert_called_once_with('owner')

    def test_match_strict_tie_and_rounded_previous_comparison(self):
        self.matcher_fixture([('first',Path('first.png'),{}),('second',Path('second.png'),{})])
        self.boxes.return_value=[];self.distance.side_effect=[0.1,0.1]
        self.assertEqual(self.api.match_background_library_plate(self.item,'owner')['background_set_id'],'first')
        self.distance.side_effect=[0.1000004,0.1000001]
        result=self.api.match_background_library_plate(self.item,'owner')
        self.assertEqual(result['background_set_id'],'first');self.assertEqual(result['distance'],0.1)

    def test_match_threshold_equality_and_current_zero_fallback(self):
        self.matcher_fixture();self.boxes.return_value=[]
        self.distance.return_value=0.2
        boundary=self.api.match_background_library_plate(self.item,'owner')
        self.assertIsNotNone(boundary)
        self.assertEqual(boundary['distance'],0.2)
        self.distance.return_value=0.200001
        self.assertIsNone(self.api.match_background_library_plate(self.item,'owner'))
        self.distance.return_value=0.0
        self.assertIsNone(self.api.match_background_library_plate(self.item,'owner'))
        self.candidates.return_value=[('zero',Path('zero.png'),{}),('later',Path('later.png'),{})]
        self.distance.side_effect=[0.0,0.1]
        self.assertEqual(self.api.match_background_library_plate(self.item,'owner')['background_set_id'],'later')

    def test_match_late_threshold_reads_and_exception_identity(self):
        self.matcher_fixture();self.boxes.return_value=[]
        def distance(*args):self.api.PIPELINE_BG_MATCH_DISTANCE_THRESHOLD=0.15;return 0.1
        self.distance.side_effect=distance
        self.assertEqual(self.api.match_background_library_plate(self.item,'owner')['threshold'],0.15)
        error=ValueError('synthetic distance failure');self.distance.side_effect=error
        with self.assertRaises(ValueError) as caught:self.api.match_background_library_plate(self.item,'owner')
        self.assertIs(caught.exception,error)

    def test_catalog_callee_before_metadata_and_eager_owner_ids(self):
        self.catalog_fixture()
        late=Mock(side_effect=AssertionError('late resolver must not be selected'))
        api=self.api;events=[];original_resolve=self.resolve
        class Metadata(dict):
            def get(inner,key,*default):
                if key=='source':api.resolve_service_path=late
                return super().get(key,*default)
        self.manifest['sets']={'one':Metadata(marker='metadata')}
        class Manifest(dict):
            def get(inner,key,*default):events.append(key);return super().get(key,*default)
        self.load.return_value=Manifest(self.manifest)
        rows=self.api.background_library_image_candidates('owner')
        self.assertEqual(len(rows),2);original_resolve.assert_called_once_with(None);late.assert_not_called()
        self.assertEqual(events,['sets','sets'])
        class Owner(str):
            def __hash__(inner):events.append(str(inner));return super().__hash__()
        self.replace('SYSTEM_OWNER_ID',new=Owner('system-probe'));self.replace('LEGACY_OWNER_ID',new=Owner('legacy-probe'))
        # The fixture overrides visibility; call the captured original root function.
        visible=self.visible._mock_wraps if self.visible._mock_wraps else self.original_visibility
        events.clear();self.assertTrue(visible({'owner_user_id':'owner'},'owner'))
        self.assertEqual(events,['system-probe','legacy-probe'])
        events.clear();self.assertTrue(visible({},'owner'));self.assertEqual(events,[])

    def test_match_signature_refresh_loop_order_and_stop_on_error(self):
        self.matcher_fixture([('one',Path('one.png'),{}),('two',Path('two.png'),{})])
        a={'source_path':'a'};b={'source_path':'b'};self.references.return_value=[a,b]
        calls=[];late=Mock(side_effect=lambda image:{'tag':'whole'})
        def initial(image):
            self.api.background_patch_signature=late
            return {'tag':'patch'}
        self.signature.side_effect=initial
        def compare(source,library):calls.append((source['source_path'],library['tag']));return 0.1
        self.distance.side_effect=compare
        self.candidates.return_value=self.candidates.return_value[:1]
        self.assertIsNotNone(self.api.match_background_library_plate(self.item,'owner'))
        self.assertEqual(calls,[('a','patch'),('a','whole'),('b','patch'),('b','whole')])
        self.signature.assert_called_once();late.assert_called_once()
        self.candidates.return_value=[('one',Path('one.png'),{}),('two',Path('two.png'),{})]
        self.read.reset_mock();self.distance.reset_mock();error=RuntimeError('first comparison failed')
        self.distance.side_effect=error
        with self.assertRaises(RuntimeError) as caught:self.api.match_background_library_plate(self.item,'owner')
        self.assertIs(caught.exception,error);self.distance.assert_called_once();self.read.assert_called_once()

    def test_match_snapshot_threshold_differs_from_final_read(self):
        self.matcher_fixture();self.boxes.return_value=[];self.distance.return_value=0.25
        api=self.api;reads=[]
        class Source(dict):
            def get(inner,key,*default):
                reads.append(key)
                if key=='box_xyxy':api.PIPELINE_BG_MATCH_DISTANCE_THRESHOLD=0.3
                return super().get(key,*default)
        self.references.return_value=[Source(self.source)]
        result=self.api.match_background_library_plate(self.item,'owner')
        self.assertEqual(result['distance'],0.25);self.assertEqual(result['threshold'],0.2)
        self.assertEqual(reads,['source_path','box_xyxy'])

    def test_independent_catalog_and_matcher_instances(self):
        from local_inspection_service.accessories.background_library_selection import BackgroundCandidateCatalog, BackgroundLibraryMatcher
        from local_inspection_service.accessories.background_library_selection_ports import BackgroundOwnership, BackgroundCatalogSources, BackgroundCatalogPolicy, BackgroundMatchSources, BackgroundMatchFeatures
        root_names=('SYSTEM_OWNER_ID','LEGACY_OWNER_ID','load_background_sets_manifest','background_set_dirs','safe_background_set_id','background_set_visible_for_owner','image_file_list','resolve_service_path','BACKGROUND_SETS_DIR','IMAGE_REFERENCE_SUFFIXES','PIPELINE_BG_MATCH_MAX_LIBRARY_IMAGES','background_reference_signatures_from_accessory','background_library_image_candidates','background_patch_boxes','background_patch_signature','background_signature_distance','PIPELINE_BG_MATCH_DISTANCE_THRESHOLD')
        poison=Mock(side_effect=AssertionError('root dependency escape'))
        for name in root_names:self.replace(name,new=poison)
        records=[]
        for label,score in (('a',0.1),('b',0.15)):
            events=[];path=self.root/('independent-'+label+'.PNG');path.touch();owner='owner-'+label
            meta={'owner_user_id':owner,'source':str(path),'generation_method':label}
            box=[label];reference={'source_path':label,'box_xyxy':box}
            def getter(name,value,events=events):
                def get():events.append(name);return value
                return get
            holder={}
            def visible(meta,owner,holder=holder):return holder['catalog'].background_set_visible_for_owner(meta,owner)
            catalog=BackgroundCandidateCatalog(
                BackgroundOwnership(getter('system','system-'+label),getter('legacy','legacy-'+label)),
                BackgroundCatalogSources(getter('manifest',lambda meta=meta:{'sets':{'one':meta}}),getter('directories',lambda:[]),getter('sanitize',lambda value:str(value)),getter('visible',visible),getter('images',lambda directory,path=path:[path]),getter('resolve',lambda value:Path(value))),
                BackgroundCatalogPolicy(getter('directory',self.root),getter('suffixes',{'.png'}),getter('limit',1)))
            holder['catalog']=catalog
            # Matcher candidates intentionally injected: this does not prove the complete catalog-to-matcher chain.
            matcher=BackgroundLibraryMatcher(
                BackgroundMatchSources(getter('references',lambda item,reference=reference:[reference]),getter('candidates',lambda owner,path=path,meta=meta:[('one',path,meta)])),
                BackgroundMatchFeatures(getter('boxes',lambda width,height:[]),getter('signature',lambda image:{'shape':image.shape}),getter('distance',lambda source,library,score=score:score)),
                getter('threshold',0.2))
            self.assertEqual(events,[])
            records.append((catalog,matcher,owner,path,meta,box,score,events))
        with patch.object(self.api.cv2,'imread',return_value=np.zeros((4,4,3),np.uint8)):
            output=[]
            for catalog,matcher,owner,path,meta,box,score,events in (records[0],records[1],records[0]):
                self.assertTrue(catalog.background_set_visible_for_owner(meta,owner))
                candidates=catalog.background_library_image_candidates(owner)
                self.assertEqual([(row[0],row[1]) for row in candidates],[('one',path)])
                self.assertIs(candidates[0][2],meta)
                result=matcher.match_background_library_plate({'id':'synthetic'},owner)
                self.assertEqual((result['image_path'],result['distance'],result['generation_method']),(str(path),score,meta['generation_method']))
                self.assertIs(result['source_box_xyxy'],box)
                output.append(result['source_path'])
            self.assertEqual(output,['a','b','a'])
        for *_,events in records:
            self.assertEqual(set(events),{'system','legacy','manifest','directories','sanitize','visible','images','resolve','directory','suffixes','limit','references','candidates','boxes','signature','distance','threshold'})
        poison.assert_not_called()

if __name__=='__main__':unittest.main()

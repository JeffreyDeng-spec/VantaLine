"""Offline original contracts for background evidence."""

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

class BackgroundEvidenceContracts(unittest.TestCase):

    @classmethod

    def setUpClass(cls):

        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))

        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='background-evidence-')))

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

    def plate_fixture(self, mask=None, image=None, paths=None):
        self.item={'id':'synthetic'}
        self.paths=paths or [self.root/'capture.PNG']
        for p in self.paths:
            p.parent.mkdir(parents=True,exist_ok=True);p.touch()
        self.pose=self.replace('agent_mcp_pose_reference_assets',return_value=[{'path':p} for p in self.paths])
        self.contexts=self.replace('accessory_reference_image_contexts',return_value=[])
        self.resolve=self.replace('resolve_service_path',side_effect=lambda value:Path(value))
        self.replace('IMAGE_REFERENCE_SUFFIXES',new={'.png'})
        self.replace('PIPELINE_BG_PLATE_TIME_BUDGET_S',new=2.0)
        self.replace('PIPELINE_BG_PLATE_MAX_SIDE',new=100)
        self.replace('PIPELINE_BG_PLATE_MAX_INPAINT_RADIUS',new=8)
        self.replace('PIPELINE_BG_PLATE_INPAINT_MAX_MASK_FRAC',new=0.0)
        self.clock=self.stack.enter_context(patch.object(self.api.time,'monotonic',return_value=10.0))
        self.image=image if image is not None else np.repeat(np.arange(100,dtype=np.uint8)[None,:,None],100,axis=0).repeat(3,axis=2)
        self.mask=np.zeros((100,100),np.uint8) if mask is None else mask
        if mask is None:self.mask[35:65,35:65]=255
        self.read_image=self.stack.enter_context(patch.object(self.api.cv2,'imread',return_value=self.image))
        self.foreground=self.replace('foreground_mask',return_value=self.mask)
        self.written=[]
        def write(path,image):self.written.append((path,image.copy()));return True
        self.write_image=self.stack.enter_context(patch.object(self.api.cv2,'imwrite',side_effect=write))
        self.out=self.root/'plates'/'plate.png'

    def signature_fixture(self, paths=None, image=None):
        self.item={'id':'reference'};self.paths=paths or [Path('first.png'),Path('second.png')]
        self.source_paths=self.replace('object_photo_highlight_source_paths',return_value=self.paths)
        self.replace('PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES',new=3)
        self.replace('PIPELINE_BG_MATCH_MAX_SOURCE_PATCHES',new=2)
        self.image=np.zeros((100,100,3),np.uint8) if image is None else image
        self.read_image=self.stack.enter_context(patch.object(self.api.cv2,'imread',return_value=self.image))
        self.foreground=self.replace('foreground_mask',return_value=np.zeros((0,0),np.uint8))
        self.boxes=self.replace('background_patch_boxes',return_value=[(0,0,20,20)])
        self.project=self.replace('background_patch_signature',side_effect=lambda image:{'feature':'synthetic'})

    def test_patch_boxes_bounds_order_and_duplicate_collapse(self):
        self.assertEqual(self.api.background_patch_boxes(0,100),[])
        self.assertEqual(self.api.background_patch_boxes(100,-1),[])
        self.assertEqual(self.api.background_patch_boxes(10,10),[(0,0,10,10)])
        self.assertEqual(self.api.background_patch_boxes(100,100),[(0,0,48,48),(52,0,100,48),(0,52,48,100),(52,52,100,100),(26,0,74,48),(26,52,74,100),(0,26,48,74),(52,26,100,74)])
        large=self.api.background_patch_boxes(2000,1800)
        self.assertEqual(large[0],(0,0,256,256));self.assertEqual(len(large),8)

    def test_patch_signature_invalid_inputs_and_uniform_black(self):
        for image in (None,np.zeros((16,16),np.uint8),np.zeros((15,20,3),np.uint8),np.zeros((20,15,3),np.uint8)):
            self.assertIsNone(self.api.background_patch_signature(image))
        image=np.zeros((16,16,3),np.uint8);result=self.api.background_patch_signature(image)
        self.assertEqual(set(result),{'lab_mean','lab_std','texture','hist'})
        np.testing.assert_allclose(result['lab_mean'],[0,128/255,128/255],atol=3e-5)
        np.testing.assert_allclose(result['lab_std'],0,atol=3e-5)
        self.assertEqual(result['texture'],0);self.assertEqual(result['hist'],[1.0]+[0.0]*31)
        self.assertFalse(image.any())

    def test_signature_distance_weights_missing_and_unequal_histograms(self):
        base={'lab_mean':[0,0,0],'lab_std':[0,0,0],'texture':0,'hist':[1,0]}
        self.assertEqual(self.api.background_signature_distance(base,base),0)
        for changed,expected in (({'lab_mean':[1,1,1]},.55),({'lab_std':[1,1,1]},.15),({'texture':1},.10),({'hist':[0,1]},.20)):
            self.assertAlmostEqual(self.api.background_signature_distance(base,dict(base,**changed)),expected,places=6)
        self.assertAlmostEqual(self.api.background_signature_distance({},{}),.2)
        self.assertAlmostEqual(self.api.background_signature_distance(base,dict(base,hist=[1])),.2)

    def test_plate_sources_filter_preserve_duplicates_and_decode_order(self):
        good=self.root/'same.PNG';bad=self.root/'ignored.jpg';missing=self.root/'missing.png'
        self.plate_fixture(paths=[good,bad]);self.pose.return_value=[{'path':missing},{'path':good},{'path':bad}]
        self.contexts.return_value=[{'source_path':good}];self.read_image.return_value=None
        self.assertIsNone(self.api.derive_background_plate_from_accessory(self.item,self.out))
        self.contexts.assert_called_once_with(self.item,max_images=4)
        self.assertEqual(self.resolve.call_args_list,[call(missing),call(good),call(bad),call(good)])
        self.assertEqual(self.read_image.call_args_list,[call(str(good),cv2.IMREAD_COLOR)]*2)
        self.foreground.assert_not_called();self.write_image.assert_not_called()

    def test_plate_deadline_is_strict_and_starts_after_source_collection(self):
        self.plate_fixture(paths=[self.root/'a.png',self.root/'b.png']);events=[]
        self.contexts.side_effect=lambda *a,**k:(events.append('contexts'),[])[1]
        times=iter([10.0,12.0,12.01])
        self.clock.side_effect=lambda:(events.append('clock'),next(times))[1]
        self.read_image.return_value=None
        self.assertIsNone(self.api.derive_background_plate_from_accessory(self.item,self.out))
        self.assertEqual(events,['contexts','clock','clock','clock'])
        self.read_image.assert_called_once_with(str(self.paths[0]),cv2.IMREAD_COLOR)

    def test_plate_component_area_boundaries_and_no_object(self):
        self.plate_fixture()
        for mask,allowed in ((np.zeros((100,100),np.uint8),False),):
            self.foreground.return_value=mask;self.assertIsNone(self.api.derive_background_plate_from_accessory(self.item,self.out))
        for count,allowed in ((499,False),(500,True),(7500,True),(7501,False)):
            mask=np.zeros((100,100),np.uint8);mask.flat[:count]=255;self.foreground.return_value=mask
            self.write_image.reset_mock();result=self.api.derive_background_plate_from_accessory(self.item,self.out)
            self.assertEqual(result,self.out if allowed else None,count)
            self.assertEqual(self.write_image.call_count,int(allowed),count)

    def test_plate_column_tie_prefers_first_clean_strip(self):
        self.plate_fixture();result=self.api.derive_background_plate_from_accessory(self.item,self.out)
        self.assertIs(result,self.out);self.assertEqual(self.written[0][0],str(self.out))
        plate=self.written[0][1];self.assertEqual(plate.shape,(100,100,3))
        self.assertEqual(int(plate[50,0,0]),0);self.assertEqual(int(plate[50,-1,0]),29)
        self.assertTrue(np.array_equal(plate[0],plate[-1]))

    def test_plate_row_strip_and_bounded_downscale_upscale(self):
        mask=np.zeros((100,100),np.uint8);mask[40:60,:]=255
        image=np.repeat(np.arange(200,dtype=np.uint8)[:,None,None],200,axis=1).repeat(3,axis=2)
        self.plate_fixture(mask=mask,image=image)
        self.assertEqual(self.api.derive_background_plate_from_accessory(self.item,self.out),self.out)
        self.assertEqual(self.foreground.call_args.args[0].shape,(100,100,3))
        plate=self.written[0][1];self.assertEqual(plate.shape,(200,200,3));self.assertLess(int(plate[-1,0,0]),80)
        self.assertTrue(np.array_equal(plate[:,0],plate[:,-1]))

    def test_plate_median_fallback_skips_inpaint_and_uses_fixed_rng_seed(self):
        mask=np.zeros((100,100),np.uint8);mask[35:65,:]=255;mask[:,35:65]=255
        self.plate_fixture(mask=mask)
        rng=Mock();rng.normal.side_effect=lambda mean,spread,shape:np.zeros(shape)
        factory=self.stack.enter_context(patch.object(self.api.np.random,'default_rng',return_value=rng))
        inpaint=self.stack.enter_context(patch.object(self.api.cv2,'inpaint',side_effect=AssertionError('inpaint gate must reject')))
        self.assertEqual(self.api.derive_background_plate_from_accessory(self.item,self.out),self.out)
        inpaint.assert_not_called();factory.assert_called_once_with(7)
        self.assertEqual(rng.normal.call_args.args[0],0);self.assertEqual(rng.normal.call_args.args[2],(100,100,3))
        self.assertFalse(np.array_equal(self.written[0][1],self.image))

    def test_plate_inpaint_allowed_at_deadline_and_radius_cap(self):
        mask=np.zeros((100,100),np.uint8);mask[35:65,:]=255;mask[:,35:65]=255
        self.plate_fixture(mask=mask);self.replace('PIPELINE_BG_PLATE_INPAINT_MAX_MASK_FRAC',new=1.0)
        self.replace('PIPELINE_BG_PLATE_MAX_INPAINT_RADIUS',new=3)
        self.clock.side_effect=[10,10,10,12,12]
        inpaint=self.stack.enter_context(patch.object(self.api.cv2,'inpaint',return_value=self.image.copy()))
        self.assertEqual(self.api.derive_background_plate_from_accessory(self.item,self.out),self.out)
        self.assertEqual(inpaint.call_args.args[2:],(3,cv2.INPAINT_TELEA))

    def test_plate_write_false_continues_and_write_exception_propagates(self):
        self.plate_fixture(paths=[self.root/'a.png',self.root/'b.png'])
        self.write_image.side_effect=[False,True]
        self.assertEqual(self.api.derive_background_plate_from_accessory(self.item,self.out),self.out)
        self.assertEqual(self.read_image.call_count,2);self.assertEqual(self.write_image.call_count,2)
        error=OSError('synthetic write');self.write_image.side_effect=error
        with self.assertRaises(OSError) as caught:self.api.derive_background_plate_from_accessory(self.item,self.out)
        self.assertIs(caught.exception,error)

    def test_reference_cap_does_not_stop_outer_source_reads(self):
        self.signature_fixture();self.replace('PIPELINE_BG_MATCH_MAX_SOURCE_PATCHES',new=1)
        result=self.api.background_reference_signatures_from_accessory(self.item)
        self.source_paths.assert_called_once_with(self.item,limit=3)
        self.assertEqual(len(result),1);self.assertEqual(self.read_image.call_count,2);self.assertEqual(self.foreground.call_count,2);self.assertEqual(self.boxes.call_count,2);self.assertEqual(self.project.call_count,1)
        self.assertEqual(result[0],{'feature':'synthetic','source_path':'first.png','box_xyxy':[0,0,20,20]})

    def test_reference_unreadable_and_empty_patches_are_skipped(self):
        self.signature_fixture();self.read_image.side_effect=[None,self.image]
        self.boxes.return_value=[(0,0,0,0),(0,0,20,20)];self.project.side_effect=None;self.project.return_value=None
        self.assertEqual(self.api.background_reference_signatures_from_accessory(self.item),[])
        self.foreground.assert_called_once();self.project.assert_called_once()

    def test_reference_free_fraction_boundary(self):
        self.signature_fixture(paths=[Path('first.png')]);self.boxes.return_value=[(0,0,10,10)]
        mask=np.zeros((100,100),np.uint8);mask[30:60,30:60]=255;self.foreground.return_value=mask
        occupied=np.zeros_like(mask);occupied[30:60,30:60]=255
        dilate=self.stack.enter_context(patch.object(self.api.cv2,'dilate',return_value=occupied))
        for count,expected in ((28,1),(29,0)):
            occupied[:10,:10]=0
            for i in range(count):occupied[i//10,i%10]=255
            self.assertEqual(len(self.api.background_reference_signatures_from_accessory(self.item)),expected)
        self.assertEqual(dilate.call_count,2)

    def test_reference_fallback_allows_fully_occupied_patch(self):
        self.signature_fixture(paths=[Path('first.png')])
        mask=np.zeros((100,100),np.uint8);mask[30:60,30:60]=255;self.foreground.return_value=mask
        self.stack.enter_context(patch.object(self.api.cv2,'dilate',return_value=np.full((100,100),255,np.uint8)))
        self.assertEqual(len(self.api.background_reference_signatures_from_accessory(self.item)),1)

    def test_reference_return_alias_and_projection_failure_identity(self):
        self.signature_fixture();shared={'feature':'shared'};self.project.side_effect=None;self.project.return_value=shared
        result=self.api.background_reference_signatures_from_accessory(self.item)
        self.assertEqual(len(result),2);self.assertIs(result[0],shared);self.assertIs(result[1],shared)
        self.assertEqual(shared['source_path'],'second.png');self.assertEqual(shared['box_xyxy'],[0,0,20,20])
        error=ValueError('synthetic projection');self.project.side_effect=error
        with self.assertRaises(ValueError) as caught:self.api.background_reference_signatures_from_accessory(self.item)
        self.assertIs(caught.exception,error)

    def test_plate_repeated_size_policy_and_late_mask_lookup(self):
        image=np.zeros((200,200,3),np.uint8);self.plate_fixture(image=image)
        api=self.api
        class RefreshLimit(int):
            def __lt__(self,other):
                api.PIPELINE_BG_PLATE_MAX_SIDE=100
                return int(self)<other
        self.replace('PIPELINE_BG_PLATE_MAX_SIDE',new=RefreshLimit(50))
        late=Mock(return_value=self.mask)
        def decode(*args):api.foreground_mask=late;return image
        self.read_image.side_effect=decode
        self.assertEqual(api.derive_background_plate_from_accessory(self.item,self.out),self.out)
        self.foreground.assert_not_called();late.assert_called_once()
        self.assertEqual(late.call_args.args[0].shape,(100,100,3))
        self.assertEqual(self.written[0][1].shape,(200,200,3))

    def test_plate_successful_write_survives_late_clock_failure(self):
        self.plate_fixture();error=RuntimeError('synthetic late clock')
        self.clock.side_effect=[10,10,10,error]
        def write(path,image):Path(path).write_bytes(b'synthetic plate evidence');return True
        self.write_image.side_effect=write
        with self.assertRaises(RuntimeError) as caught:self.api.derive_background_plate_from_accessory(self.item,self.out)
        self.assertIs(caught.exception,error);self.write_image.assert_called_once()
        self.assertEqual(self.out.read_bytes(),b'synthetic plate evidence')

    def test_independent_services_keep_two_instance_capabilities_isolated(self):
        from local_inspection_service.accessories.background_evidence import BackgroundPlateDerivation, BackgroundReferenceSignatures
        from local_inspection_service.accessories.background_evidence_ports import PlateSources, PlatePolicy, BackgroundMasks, SignatureSources, SignaturePolicy, SignatureProjections
        mask=np.zeros((100,100),np.uint8);mask[35:65,:]=255;mask[:,35:65]=255
        self.plate_fixture(mask=mask)
        poison=Mock(side_effect=AssertionError('root dependency used by independent service'))
        names=('agent_mcp_pose_reference_assets','accessory_reference_image_contexts','resolve_service_path','IMAGE_REFERENCE_SUFFIXES','PIPELINE_BG_PLATE_TIME_BUDGET_S','PIPELINE_BG_PLATE_MAX_SIDE','PIPELINE_BG_PLATE_MAX_INPAINT_RADIUS','PIPELINE_BG_PLATE_INPAINT_MAX_MASK_FRAC','foreground_mask','object_photo_highlight_source_paths','PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES','PIPELINE_BG_MATCH_MAX_SOURCE_PATCHES','background_patch_boxes','background_patch_signature')
        for name in names:self.replace(name,new=poison)
        reads=[]
        def make(label):
            values={'pose_assets':lambda item:[{'path':self.paths[0]}],'contexts':lambda item,**kw:[],'resolve':lambda value:Path(value),'suffixes':{'.png'},'time_budget':2.0,'max_side':100,'max_radius':8,'mask_fraction':0.0,'foreground':lambda image:mask,'paths':lambda item,**kw:[Path(label+'.png')],'limit':3,'max_patches':1,'boxes':lambda width,height:[(0,0,20,20)],'signature':lambda image:{'label':label}}
            def getter(key):
                def read():reads.append((label,key));return values[key]
                return read
            groups=[PlateSources(**{k:getter(k) for k in ('pose_assets','contexts','resolve','suffixes')}),PlatePolicy(**{k:getter(k) for k in ('time_budget','max_side','max_radius','mask_fraction')}),BackgroundMasks(getter('foreground')),SignatureSources(getter('paths'),getter('limit')),SignaturePolicy(getter('max_patches')),SignatureProjections(getter('boxes'),getter('signature'))]
            return BackgroundPlateDerivation(*groups[:3]),BackgroundReferenceSignatures(groups[3],groups[4],groups[2],groups[5])
        a=make('A');b=make('B');self.assertEqual(reads,[])
        for label,(plate,reference) in (('A',a),('B',b),('A',a)):
            start=len(reads);out=self.root/'independent'/label/'plate.png'
            self.assertIs(plate.derive_background_plate_from_accessory({},out),out)
            result=reference.background_reference_signatures_from_accessory({})
            self.assertEqual(result,[{'label':label,'source_path':label+'.png','box_xyxy':[0,0,20,20]}])
            self.assertEqual({who for who,key in reads[start:]},{label})
            self.assertEqual({key for who,key in reads[start:]},{'pose_assets','contexts','resolve','suffixes','time_budget','max_side','max_radius','mask_fraction','foreground','paths','limit','max_patches','boxes','signature'})
        self.assertIsNot(a[0],b[0]);self.assertIsNot(a[1],b[1]);poison.assert_not_called()


if __name__=='__main__':
    unittest.main()

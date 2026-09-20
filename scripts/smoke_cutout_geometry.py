"""Preliminary original image geometry contracts; synthetic arrays only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from itertools import chain,repeat
from contextlib import ExitStack
from unittest.mock import Mock,patch
import numpy as np
sys.path.insert(0,str(Path.cwd()))
class CutoutGeometryContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='cutout-runtime-')))
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
        image=np.full((100,100,3),(0,255,0),np.uint8);image[35:65,35:65]=(0,0,255);return image
    def test_green_spill_values_copy_and_invalid_identity(self):
        image=np.array([[[10,90,20],[30,10,50],[40,40,40]]],np.uint8);before=image.copy()
        result=self.api.suppress_green_spill(image)
        np.testing.assert_array_equal(result,[[[10,20,20],[30,10,50],[40,40,40]]]);np.testing.assert_array_equal(image,before)
        self.assertFalse(np.shares_memory(result,image));self.assertIsNone(self.api.suppress_green_spill(None))
        bad=np.zeros((2,2),np.uint8);self.assertIs(self.api.suppress_green_spill(bad),bad)
    def test_chroma_spill_three_channels_unknown_and_invalid(self):
        image=np.array([[[90,20,10],[10,90,20],[10,20,90]]],np.uint8)
        normalize=self.replace('normalize_chroma_screen',side_effect=lambda screen:{'name':screen})
        np.testing.assert_array_equal(self.api.suppress_chroma_spill(image,'blue'),[[[20,20,10],[10,90,20],[10,20,90]]])
        np.testing.assert_array_equal(self.api.suppress_chroma_spill(image,'red'),[[[90,20,10],[10,90,20],[10,20,20]]])
        sentinel=np.ones((1,1,3),np.uint8);green=self.replace('suppress_green_spill',return_value=sentinel)
        self.assertIs(self.api.suppress_chroma_spill(image,'green'),sentinel);self.assertIs(green.call_args.args[0],image)
        self.assertIs(self.api.suppress_chroma_spill(image,'other'),image)
        count=normalize.call_count;self.assertIsNone(self.api.suppress_chroma_spill(None,'red'));self.assertEqual(normalize.call_count,count)
    def test_bright_mask_hsv_and_signed_dominance_boundaries(self):
        hsv=np.array([[[35,70,80],[95,70,80],[34,70,80],[96,70,80],[35,69,80],[35,70,79],[35,70,80],[35,70,80]]],np.uint8)
        image=np.array([[[0,26,0],[0,26,0],[0,26,0],[0,26,0],[0,26,0],[0,26,0],[0,25,0],[255,0,255]]],np.uint8)
        with patch.object(self.api.cv2,'cvtColor',return_value=hsv):result=self.api.bright_green_conveyor_mask(image)
        np.testing.assert_array_equal(result,[[True,True,False,False,False,False,False,False]]);self.assertEqual(result.dtype,np.dtype(bool))
    def test_distance_alpha_clips_and_casts_after_float_distance(self):
        screen={'name':'custom','rgb':[0,0,0]};normalize=self.replace('normalize_chroma_screen',return_value=screen)
        image=np.array([[[0,0,0],[24,0,0],[72,0,0],[120,0,0],[255,255,255]]],np.uint8)
        np.testing.assert_array_equal(self.api.chroma_distance_alpha(image,screen),[[0,0,127,255,255]])
        normalize.assert_called_once_with(screen)
    def test_background_near_exact_and_secondary_distance_limits(self):
        screen={'name':'green','rgb':[0,0,0]};self.replace('normalize_chroma_screen',return_value=screen)
        saturated=self.replace('saturated_chroma_mask',return_value=np.zeros((1,6),bool))
        image=np.array([[[42,42,42],[43,43,43],[70,25,25],[70,26,25],[71,0,0],[0,0,0]]],np.uint8)
        with patch.object(self.api.cv2,'cvtColor',return_value=np.zeros((1,6,3),np.uint8)):
            result=self.api.chroma_background_mask(image,screen)
        np.testing.assert_array_equal(result,[[True,False,True,False,False,True]]);self.assertIs(saturated.call_args.args[0],image);self.assertIs(saturated.call_args.args[1],screen)
    def test_background_includes_saturated_collaborator_result(self):
        screen={'name':'green','rgb':[0,0,0]};self.replace('normalize_chroma_screen',return_value=screen)
        self.replace('saturated_chroma_mask',return_value=np.array([[True,False]]));image=np.full((1,2,3),200,np.uint8)
        with patch.object(self.api.cv2,'cvtColor',return_value=np.zeros((1,2,3),np.uint8)):
            np.testing.assert_array_equal(self.api.chroma_background_mask(image,screen),[[True,False]])
    def test_foreground_morphology_order_parameters(self):
        cv=self.api.cv2;image=np.full((40,40,3),(0,255,0),np.uint8)
        with patch.object(cv,'morphologyEx',wraps=cv.morphologyEx) as morph:
            result=self.api.foreground_mask(image)
        self.assertEqual(result.shape,(40,40));self.assertEqual(result.dtype,np.dtype('uint8'));self.assertFalse(result.any())
        self.assertEqual([c.args[1] for c in morph.call_args_list],[cv.MORPH_CLOSE,cv.MORPH_OPEN]);self.assertEqual([c.args[2].shape for c in morph.call_args_list],[(17,17),(3,3)]);self.assertEqual([c.kwargs for c in morph.call_args_list],[{'iterations':2},{'iterations':1}])
    def test_object_component_absence_never_uses_rng(self):
        image=np.zeros((100,100,3),np.uint8);self.replace('foreground_mask',return_value=np.zeros((100,100),np.uint8));rng=Mock()
        self.assertIsNone(self.api.object_cutout_from_image(image,rng));rng.choice.assert_not_called()
    def test_object_component_selection_weight_and_copies(self):
        image=np.full((100,100,3),80,np.uint8);mask=np.zeros((100,100),np.uint8);mask[10:35,10:35]=255;mask[50:80,50:80]=255
        self.replace('foreground_mask',return_value=mask);rng=Mock();rng.choice.return_value=0
        crop,alpha=self.api.object_cutout_from_image(image,rng)
        self.assertEqual(crop.shape,(46,46,3));self.assertEqual(alpha.shape,(46,46));self.assertFalse(np.shares_memory(crop,image));self.assertFalse(np.shares_memory(alpha,mask))
        self.assertEqual(rng.choice.call_args.args,(2,));np.testing.assert_allclose(rng.choice.call_args.kwargs['p'],[900/1525,625/1525])
    def test_projection_helpers_preserve_array_identity_and_none(self):
        image=self.image();rng=Mock();crop=image[:4,:6];alpha=np.ones((4,6),np.uint8)
        ai=self.replace('ai_background_cutout_with_bbox',side_effect=[None,(crop,alpha,(9,8,15,12))])
        self.assertIsNone(self.api.ai_background_cutout(image));result=self.api.ai_background_cutout(image);self.assertIs(result[0],crop);self.assertIs(result[1],alpha);self.assertEqual(ai.call_count,2)
        green=self.replace('green_screen_object_cutout_with_bbox',side_effect=[None,(crop,alpha,(9,8,15,12))])
        self.assertIsNone(self.api.green_screen_object_cutout(image,rng));result=self.api.green_screen_object_cutout(image,rng);self.assertIs(result[0],crop);self.assertIs(result[1],alpha);self.assertIs(green.call_args.args[1],rng)
    def test_green_screen_no_components_fallback_crop_local_bbox(self):
        image=np.zeros((100,100,3),np.uint8);rng=Mock();crop=np.ones((12,17,3),np.uint8);alpha=np.ones((12,17),np.uint8)
        fallback=self.replace('object_cutout_from_image',side_effect=[None,(crop,alpha)])
        with patch.object(self.api.cv2,'connectedComponentsWithStats',return_value=(1,np.zeros((100,100),np.int32),np.zeros((1,5),np.int32),None)):
            self.assertIsNone(self.api.green_screen_object_cutout_with_bbox(image,rng));result=self.api.green_screen_object_cutout_with_bbox(image,rng)
        self.assertIs(result[0],crop);self.assertIs(result[1],alpha);self.assertEqual(result[2],(0,0,17,12));self.assertIs(fallback.call_args.args[0],image);self.assertIs(fallback.call_args.args[1],rng)
    def test_green_screen_success_does_not_call_fallback_or_rng(self):
        image=np.full((200,200,3),(0,255,0),np.uint8);image[70:120,70:120]=(0,0,255);rng=Mock();fallback=self.replace('object_cutout_from_image',side_effect=AssertionError('unexpected fallback'))
        result=self.api.green_screen_object_cutout_with_bbox(image,rng);self.assertIsNotNone(result);crop,alpha,box=result
        self.assertEqual(crop.shape[:2],alpha.shape);self.assertEqual(alpha.dtype,np.dtype('uint8'));self.assertEqual(int(alpha.max()),255);self.assertEqual((box[2]-box[0],box[3]-box[1]),(crop.shape[1],crop.shape[0]));self.assertFalse(np.shares_memory(crop,image));rng.choice.assert_not_called();fallback.assert_not_called()
    def test_single_object_invalid_input_stops_before_dependencies(self):
        background=self.replace('chroma_background_mask');spill=self.replace('suppress_green_spill')
        for callback in (self.api.chroma_screen_object_cutout,self.api.green_conveyor_object_cutout):
            self.assertIsNone(callback(None));self.assertIsNone(callback(np.zeros((4,4),np.uint8)))
        background.assert_not_called();spill.assert_not_called()
    def test_chroma_background_fraction_and_empty_foreground(self):
        image=self.image();background=self.replace('chroma_background_mask',side_effect=[np.zeros((100,100),bool),np.ones((100,100),bool)]);distance=self.replace('chroma_distance_alpha')
        self.assertIsNone(self.api.chroma_screen_object_cutout(image));self.assertIsNone(self.api.chroma_screen_object_cutout(image));self.assertEqual(background.call_count,2);distance.assert_not_called()
    def test_chroma_success_retains_core_and_copies(self):
        image=self.image();original=image.copy();result=self.api.chroma_screen_object_cutout(image,'green');self.assertIsNotNone(result);crop,alpha,box=result
        self.assertEqual(int(alpha[alpha.shape[0]//2,alpha.shape[1]//2]),255);self.assertFalse(np.shares_memory(crop,image));self.assertEqual(crop.shape[:2],alpha.shape);self.assertEqual((box[2]-box[0],box[3]-box[1]),(crop.shape[1],crop.shape[0]));np.testing.assert_array_equal(image,original)
    def test_conveyor_empty_background_and_success(self):
        self.assertIsNone(self.api.green_conveyor_object_cutout(np.full((100,100,3),(0,255,0),np.uint8)))
        image=self.image();original=image.copy();result=self.api.green_conveyor_object_cutout(image);self.assertIsNotNone(result);crop,alpha,box=result
        self.assertEqual(int(alpha.max()),255);self.assertFalse(np.shares_memory(crop,image));self.assertEqual(crop.shape[:2],alpha.shape);self.assertEqual((box[2]-box[0],box[3]-box[1]),(crop.shape[1],crop.shape[0]));np.testing.assert_array_equal(image,original)
    def test_collaborator_failure_is_not_swallowed(self):
        failure=RuntimeError('synthetic geometry failure');self.replace('foreground_mask',side_effect=failure)
        with self.assertRaises(RuntimeError) as seen:self.api.object_cutout_from_image(self.image(),Mock())
        self.assertIs(seen.exception,failure)
        self.replace('chroma_background_mask',side_effect=failure)
        with self.assertRaises(RuntimeError) as seen:self.api.chroma_screen_object_cutout(self.image())
        self.assertIs(seen.exception,failure)

    def test_exact_twenty_percent_background_enters_component_processing(self):
        image=np.zeros((10,10,3),np.uint8);background=np.zeros((10,10),bool);background[:2]=True
        self.replace('chroma_background_mask',return_value=background)
        with patch.object(self.api.cv2,'morphologyEx',side_effect=lambda value,*a,**k:value), patch.object(self.api.cv2,'connectedComponentsWithStats',return_value=(1,None,None,None)) as components:
            self.assertIsNone(self.api.chroma_screen_object_cutout(image))
        components.assert_called_once()
    def test_green_spill_selected_after_normalization(self):
        image=self.image();first=Mock(side_effect=AssertionError('premature green callback'));last=Mock(return_value=image)
        self.replace('suppress_green_spill',new=first)
        def normalize(screen):self.api.suppress_green_spill=last;return {'name':'green'}
        self.replace('normalize_chroma_screen',side_effect=normalize)
        self.assertIs(self.api.suppress_chroma_spill(image),image);first.assert_not_called();last.assert_called_once_with(image)
    def test_green_fallback_selected_after_component_scan(self):
        image=np.zeros((100,100,3),np.uint8);rng=Mock();first=Mock(side_effect=AssertionError('premature fallback'));crop=np.ones((12,17,3),np.uint8);alpha=np.ones((12,17),np.uint8);last=Mock(return_value=(crop,alpha))
        self.replace('object_cutout_from_image',new=first)
        def scan(*a,**k):self.api.object_cutout_from_image=last;return 1,np.zeros((100,100),np.int32),np.zeros((1,5),np.int32),None
        with patch.object(self.api.cv2,'connectedComponentsWithStats',side_effect=scan):result=self.api.green_screen_object_cutout_with_bbox(image,rng)
        self.assertIs(result[0],crop);self.assertEqual(result[2],(0,0,17,12));first.assert_not_called();last.assert_called_once_with(image,rng)
    def test_chroma_distance_selected_after_background_callback(self):
        image=self.image();background=np.ones((100,100),bool);background[35:65,35:65]=False;first=Mock(side_effect=AssertionError('premature distance'));last=Mock(return_value=np.full((100,100),255,np.uint8));self.replace('chroma_distance_alpha',new=first)
        def mask(*a):self.api.chroma_distance_alpha=last;return background
        self.replace('chroma_background_mask',side_effect=mask)
        self.assertIsNotNone(self.api.chroma_screen_object_cutout(image));first.assert_not_called();last.assert_called_once_with(image,None)
    def test_chroma_spill_callee_selected_before_crop_copy(self):
        base=self.image();events=[];last=Mock(return_value=base[:1,:1].copy())
        class Image(np.ndarray):
            def __getitem__(value,key):
                if isinstance(key,tuple) and len(key)==2 and all(isinstance(v,slice) for v in key):
                    events.append('crop');self.api.suppress_chroma_spill=last
                return super().__getitem__(key)
        image=base.view(Image);background=np.ones((100,100),bool);background[35:65,35:65]=False
        self.replace('chroma_background_mask',return_value=background);self.replace('chroma_distance_alpha',return_value=np.full((100,100),255,np.uint8));first=Mock(side_effect=lambda value,screen:value);self.replace('suppress_chroma_spill',new=first)
        result=self.api.chroma_screen_object_cutout(image);self.assertIsNotNone(result);self.assertEqual(events,['crop']);first.assert_called_once();last.assert_not_called();self.assertFalse(np.shares_memory(first.call_args.args[0],image))

    def test_asymmetric_rgb_target_and_blue_red_shadow_branches(self):
        screen={'name':'custom','rgb':[10,40,90]};normalize=self.replace('normalize_chroma_screen',return_value=screen);self.replace('saturated_chroma_mask',return_value=np.zeros((1,2),bool));image=np.array([[[90,40,10],[162,40,10]]],np.uint8)
        np.testing.assert_array_equal(self.api.chroma_distance_alpha(image,'custom'),[[0,127]])
        with patch.object(self.api.cv2,'cvtColor',return_value=np.zeros((1,2,3),np.uint8)):
            np.testing.assert_array_equal(self.api.chroma_background_mask(image,'custom'),[[True,False]])
        for name,pixels,hsv in [('blue',[[90,20,20],[90,63,20]],[96,28,28]),('red',[[20,20,90],[20,63,90]],[168,28,28])]:
            with self.subTest(name=name):
                normalize.return_value={'name':name,'rgb':[255,255,255]}
                with patch.object(self.api.cv2,'cvtColor',return_value=np.array([[hsv,hsv]],np.uint8)):
                    np.testing.assert_array_equal(self.api.chroma_background_mask(np.array([pixels],np.uint8),name),[[True,False]])
    def test_component_eligibility_top_eight_and_green_anchor_priority(self):
        image=np.full((200,200,3),80,np.uint8);mask=np.zeros((200,200),np.uint8);self.replace('foreground_mask',return_value=mask)
        rows=[[0,0,200,200,40000],[10,10,150,150,22000],[10,10,150,150,22001],[10,10,7,100,600],[10,10,100,7,600],[10,10,30,50,499]]+[[10,10,30,50,area] for area in range(500,1400,100)]
        rng=Mock();rng.choice.return_value=0
        with patch.object(self.api.cv2,'connectedComponentsWithStats',return_value=(len(rows),np.zeros((200,200),np.int32),np.array(rows,np.int32),None)):
            crop,alpha=self.api.object_cutout_from_image(image,rng)
        expected=np.array([22000,1300,1200,1100,1000,900,800,700],float);self.assertEqual(rng.choice.call_args.args,(8,));np.testing.assert_allclose(rng.choice.call_args.kwargs['p'],expected/expected.sum());self.assertEqual(crop.shape,(187,187,3));self.assertEqual(alpha.shape,(187,187))
        green=np.full((200,200,3),(0,255,0),np.uint8);green[100:180,100:180]=(255,255,255);green[20,20:50]=(0,0,255)
        first=(3,np.zeros((200,200),np.int32),np.array([[0,0,200,200,40000],[100,100,80,80,6400],[20,20,30,30,900]],np.int32),None)
        second=(1,np.zeros((50,50),np.int32),np.zeros((1,5),np.int32),None);fallback=self.replace('object_cutout_from_image',side_effect=AssertionError('unexpected fallback'));other_rng=Mock()
        with patch.object(self.api.cv2,'connectedComponentsWithStats',side_effect=[first,second]):result=self.api.green_screen_object_cutout_with_bbox(green,other_rng)
        self.assertIsNotNone(result);self.assertEqual(result[2],(10,10,60,60));fallback.assert_not_called();other_rng.choice.assert_not_called()

    def test_independent_selection_constructors_and_first_second_first(self):
        from local_inspection_service.accessories.cutout_selection import ObjectCutoutSelection
        from local_inspection_service.accessories.cutout_geometry_ports import SelectionOperations
        getter_names=('foreground','object_fallback','bounded_ai','bounded_green')
        getters={name:Mock(side_effect=AssertionError('constructor resolved dependency')) for name in getter_names}
        ObjectCutoutSelection(SelectionOperations(**getters))
        for getter in getters.values():getter.assert_not_called()
        poison_names=('foreground_mask','object_cutout_from_image','ai_background_cutout_with_bbox','green_screen_object_cutout_with_bbox')
        poisons=[self.replace(name,side_effect=AssertionError('root selection dependency forbidden')) for name in poison_names]
        instances=[]
        for width,color in ((30,11),(35,22)):
            mask=np.zeros((100,100),np.uint8);mask[20:20+width,20:20+width]=255
            crop=np.full((3,4,3),color,np.uint8);alpha=np.full((3,4),210,np.uint8)
            foreground=Mock(return_value=mask);fallback=Mock(return_value=(crop,alpha));ai=Mock(return_value=(crop,alpha,(0,0,4,3)));green=Mock(return_value=(crop,alpha,(0,0,4,3)))
            service=ObjectCutoutSelection(SelectionOperations(foreground=lambda fn=foreground:fn,object_fallback=lambda fn=fallback:fn,bounded_ai=lambda fn=ai:fn,bounded_green=lambda fn=green:fn))
            instances.append((service,crop,alpha,foreground,fallback,ai,green,width))
        image=np.full((100,100,3),77,np.uint8)
        for index in (0,1,0):
            service,crop,alpha,foreground,fallback,ai,green,width=instances[index];rng=Mock();rng.choice.return_value=0
            selected=service.object_cutout_from_image(image,rng);self.assertIsNotNone(selected);self.assertEqual(selected[0].shape,(width+16,width+16,3));rng.choice.assert_called_once()
            result=service.ai_background_cutout(image);self.assertIs(result[0],crop);self.assertIs(result[1],alpha)
            result=service.green_screen_object_cutout(image,rng);self.assertIs(result[0],crop);self.assertIs(result[1],alpha)
            fallback.assert_not_called()
        self.assertEqual([item[3].call_count for item in instances],[2,1]);self.assertEqual([item[5].call_count for item in instances],[2,1]);self.assertEqual([item[6].call_count for item in instances],[2,1])
        for poison in poisons:poison.assert_not_called()

    def test_independent_chroma_constructors_and_first_second_first(self):
        from local_inspection_service.accessories.chroma_cutouts import ChromaCutoutProcessor
        from local_inspection_service.accessories.cutout_geometry_ports import ChromaPolicyOperations,ChromaMatteOperations
        getters={name:Mock(side_effect=AssertionError('constructor resolved dependency')) for name in ('normalize','saturated','green_spill','background','distance','spill')}
        ChromaCutoutProcessor(ChromaPolicyOperations(**{name:getters[name] for name in ('normalize','saturated','green_spill')}),ChromaMatteOperations(**{name:getters[name] for name in ('background','distance','spill')}))
        for getter in getters.values():getter.assert_not_called()
        poison_names=('normalize_chroma_screen','saturated_chroma_mask','suppress_green_spill','chroma_background_mask','chroma_distance_alpha','suppress_chroma_spill')
        poisons=[self.replace(name,side_effect=AssertionError('root chroma dependency forbidden')) for name in poison_names]
        instances=[]
        for delta in (1,2):
            background=np.ones((100,100),bool);background[35:65,35:65]=False
            normal=Mock(return_value={'name':'green','rgb':[0,255,0]});saturated=Mock(side_effect=lambda value,screen:np.zeros(value.shape[:2],bool));green=Mock(side_effect=lambda value,d=delta:np.full_like(value,d));mask=Mock(return_value=background);distance=Mock(return_value=np.full((100,100),255,np.uint8));spill=Mock(side_effect=lambda value,screen,d=delta:np.full_like(value,d+10))
            service=ChromaCutoutProcessor(ChromaPolicyOperations(normalize=lambda fn=normal:fn,saturated=lambda fn=saturated:fn,green_spill=lambda fn=green:fn),ChromaMatteOperations(background=lambda fn=mask:fn,distance=lambda fn=distance:fn,spill=lambda fn=spill:fn))
            instances.append((service,normal,saturated,green,mask,distance,spill,delta))
        image=self.image()
        for index in (0,1,0):
            service,normal,saturated,green,mask,distance,spill,delta=instances[index]
            result=service.suppress_chroma_spill(image,'green');self.assertTrue(np.all(result==delta))
            result=service.chroma_background_mask(np.array([[[0,255,0]]],np.uint8),'green');np.testing.assert_array_equal(result,[[True]])
            result=service.chroma_distance_alpha(np.array([[[0,255,0]]],np.uint8),'green');np.testing.assert_array_equal(result,[[0]])
            result=service.chroma_screen_object_cutout(image,'green');self.assertIsNotNone(result);self.assertTrue(np.all(result[0]==delta+10));self.assertEqual(int(result[1].max()),255)
            result=service.green_conveyor_object_cutout(image);self.assertIsNotNone(result);self.assertTrue(np.all(result[0]==delta));self.assertEqual(int(result[1].max()),255)
        self.assertEqual([item[1].call_count for item in instances],[6,3]);self.assertEqual([item[4].call_count for item in instances],[2,1]);self.assertEqual([item[5].call_count for item in instances],[2,1]);self.assertEqual([item[6].call_count for item in instances],[2,1])
        for poison in poisons:poison.assert_not_called()

if __name__=='__main__':unittest.main()

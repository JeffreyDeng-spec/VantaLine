"""Offline original contracts for accessory profile projection."""

import os

from pathlib import Path

import sys

import tempfile

import unittest

from contextlib import ExitStack

from unittest.mock import Mock,patch,call

sys.path.insert(0,str(Path.cwd()))

class AccessoryProfileContracts(unittest.TestCase):

    @classmethod

    def setUpClass(cls):

        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))

        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='accessory-profile-')))

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

    def text_dependencies(self):
        self.replace('accessory_uid',return_value='item-1')
        self.replace('bounded_text',side_effect=lambda value,limit:str(value or '')[:limit])
        self.replace('preferred_english_accessory_name',return_value='Cable')
        self.replace('compact_english_accessory_name',side_effect=lambda value,**kw:str(value or ''))
        self.replace('accessory_material_type',return_value='text')
        self.replace('string_list',side_effect=lambda value,fallback=None,**kw:(value if isinstance(value,list) else fallback or [])[:kw.get('max_items',12)])
        self.replace('profile_size_text',return_value='size-label')
        self.replace('ai_profile_dimensions_from_physical_size',return_value={'width':2})
        self.replace('ai_profile_top_view_aspect_ratio',return_value=2.0)
        self.replace('normalize_ai_profile_dimensions',side_effect=lambda raw,fallback:raw or fallback)
        self.replace('optional_float',side_effect=lambda value:None if value is None else float(value))
        self.replace('AI_PROFILE_REFERENCE_IMAGES',new=3)
        return self.replace('accessory_reference_image_contexts',return_value=[])

    def fallback(self):
        return dict(accessory_id='item-1',name='Base',english_name='Cable',material_type='text',description='Base description',tags=['base'],visual_signature='base signature',distinguishing_text=['Base'],negative_cues=['avoid'],dimensions_mm={'width':2},top_view_aspect_ratio=2.0,reference_images=[],provider_cache={},expected_count=2)

    def normalizer_dependencies(self):
        refs=self.text_dependencies();fallback=self.fallback()
        stub=self.replace('fallback_accessory_ai_profile',return_value=fallback)
        return fallback,stub,refs

    def test_fallback_source_order_dedup_and_signature(self):
        refs=self.text_dependencies()
        item={'name':'Manual','source_files':['z_file.png','a_file.png','z_file.jpg',''], 'original_source_files':['b_file.png'],'physical_size':{'kind':'paper'},'expected_count':'3'}
        r=self.api.fallback_accessory_ai_profile(item)
        self.assertEqual(r['tags'],['text','detect_and_classify','paper','a file','b file','z file'])
        self.assertEqual(r['distinguishing_text'],['Manual','a file','b file','z file'])
        self.assertEqual(r['visual_signature'],'name=Manual; material=text; size-label; visual_evidence_images=0')
        self.assertEqual(r['expected_count'],3)
        self.assertEqual(r['negative_cues'],['Do not count a different accessory with only similar size.','Do not infer presence from previous images or configured task state.','If visible printed text does not match this profile, mark missing.'])
        refs.assert_called_once_with(item)

    def test_fallback_explicit_empty_and_reference_alias(self):
        refs=self.text_dependencies();given=[]
        r=self.api.fallback_accessory_ai_profile({'label':'Label'},reference_images=given)
        self.assertIs(r['reference_images'],given)
        self.assertEqual(r['name'],'Label')
        refs.assert_not_called()
        other=[{'source_path':'synthetic'}]
        r=self.api.fallback_accessory_ai_profile({},reference_images=other)
        self.assertIs(r['reference_images'],other)
        self.assertEqual(r['name'],'item-1')
        self.assertIn('visual_evidence_images=1',r['visual_signature'])

    def test_fallback_object_alpha_called_at_both_points(self):
        self.text_dependencies();self.replace('accessory_material_type',return_value='object')
        alpha=self.replace('object_alpha_material_policy',side_effect=['transparent','opaque'])
        r=self.api.fallback_accessory_ai_profile({},reference_images=[])
        self.assertEqual(r['tags'],['object','detect_and_classify','transparent'])
        self.assertTrue(r['visual_signature'].endswith('alpha_policy=opaque'))
        self.assertEqual(alpha.call_count,2)
        self.assertEqual(r['negative_cues'][-1],'If the object shape/material does not match this profile, mark missing.')

    def test_fallback_count_coercion_and_errors(self):
        self.text_dependencies()
        for value in (None,0,-3,'0'):
            self.assertEqual(self.api.fallback_accessory_ai_profile({'expected_count':value},reference_images=[])['expected_count'],1)
        with self.assertRaises(ValueError):self.api.fallback_accessory_ai_profile({'expected_count':'bad'},reference_images=[])
        with self.assertRaises(OverflowError):self.api.fallback_accessory_ai_profile({'expected_count':float('inf')},reference_images=[])

    def test_normalizer_non_dict_uses_fallback(self):
        fallback,stub,refs=self.normalizer_dependencies()
        r=self.api.normalize_accessory_ai_profile(None,{})
        self.assertEqual(r,fallback)
        stub.assert_called_once_with({},reference_images=None)
        refs.assert_not_called()

    def test_normalizer_fallback_always_runs_first(self):
        self.normalizer_dependencies()
        sentinel=ValueError('fallback failure')
        self.replace('fallback_accessory_ai_profile',side_effect=sentinel)
        with self.assertRaises(ValueError) as caught:self.api.normalize_accessory_ai_profile({'name':'Full','expected_count':3,'reference_images':[]},{})
        self.assertIs(caught.exception,sentinel)

    def test_normalizer_count_catches_only_type_and_value(self):
        self.normalizer_dependencies()
        for value in (None,'bad',[],{}):
            self.assertEqual(self.api.normalize_accessory_ai_profile({'expected_count':value},{})['expected_count'],2)
        for value in (0,-2,'0'):
            self.assertEqual(self.api.normalize_accessory_ai_profile({'expected_count':value},{})['expected_count'],1)
        with self.assertRaises(OverflowError):self.api.normalize_accessory_ai_profile({'expected_count':float('inf')},{})

    def test_normalizer_filters_refs_preserving_original_ordinal(self):
        _,stub,_=self.normalizer_dependencies()
        refs=[None,{'source_path':'  '},{'source_path':' image ','width':'4','height':5},{'source_path':'two','ordinal':9}]
        r=self.api.normalize_accessory_ai_profile({'reference_images':refs},{})
        self.assertEqual([x['ordinal'] for x in r['reference_images']],[3,9])
        self.assertEqual(r['reference_images'][0],dict(accessory_id='item-1',source_path=' image ',sha256='',mime_type='image/jpeg',width=4,height=5,ordinal=3))
        self.assertIs(stub.call_args.kwargs['reference_images'],refs)
        self.assertIsNot(r['reference_images'][0],refs[2])

    def test_normalizer_evaluates_full_refs_before_cap(self):
        self.normalizer_dependencies();self.replace('AI_PROFILE_REFERENCE_IMAGES',new=1)
        refs=[{'source_path':'one'},{'source_path':'two','width':'invalid'}]
        with self.assertRaises(ValueError):self.api.normalize_accessory_ai_profile({'reference_images':refs},{})

    def test_normalizer_limit_is_read_after_reference_conversion(self):
        self.normalizer_dependencies();self.replace('AI_PROFILE_REFERENCE_IMAGES',new=1)
        api=self.api
        class Width:
            def __int__(self):api.AI_PROFILE_REFERENCE_IMAGES=2;return 7
        r=self.api.normalize_accessory_ai_profile({'reference_images':[{'source_path':'one','width':Width()},{'source_path':'two'}]}, {})
        self.assertEqual(len(r['reference_images']),2)
        self.assertEqual(r['reference_images'][0]['width'],7)

    def test_normalizer_provider_cache_retains_dict_alias(self):
        self.normalizer_dependencies();cache={'synthetic':1}
        r=self.api.normalize_accessory_ai_profile({'provider_cache':cache},{})
        self.assertIs(r['provider_cache'],cache)
        self.assertEqual(self.api.normalize_accessory_ai_profile({'provider_cache':['invalid']},{})['provider_cache'],{})

    def test_normalizer_ratio_rounding_and_falsy_fallback(self):
        self.normalizer_dependencies()
        self.assertEqual(self.api.normalize_accessory_ai_profile({'top_view_aspect_ratio':1.23456},{})['top_view_aspect_ratio'],1.235)
        self.assertEqual(self.api.normalize_accessory_ai_profile({'top_view_aspect_ratio':0},{})['top_view_aspect_ratio'],2.0)
        self.assertEqual(self.api.normalize_accessory_ai_profile({'top_view_aspect_ratio':-2},{})['top_view_aspect_ratio'],-2.0)
        import math
        self.assertTrue(math.isnan(self.api.normalize_accessory_ai_profile({'top_view_aspect_ratio':float('nan')},{})['top_view_aspect_ratio']))

    def test_normalizer_empty_values_use_fallback_lists_preserved(self):
        fallback,_,_=self.normalizer_dependencies()
        r=self.api.normalize_accessory_ai_profile({'name':'','english_name':'','description':'','visual_signature':'','tags':[],'negative_cues':[]},{})
        for key in ('name','english_name','description','visual_signature'):self.assertEqual(r[key],fallback[key])
        self.assertEqual(r['tags'],[])
        self.assertEqual(r['negative_cues'],[])
        self.assertEqual(r['distinguishing_text'],['Base'])

    def test_normalizer_invalid_reference_list_uses_fallback(self):
        fallback,stub,_=self.normalizer_dependencies()
        fallback['reference_images']=[{'source_path':'fallback'}]
        r=self.api.normalize_accessory_ai_profile({'reference_images':'invalid'}, {})
        self.assertEqual(r['reference_images'][0]['source_path'],'fallback')
        stub.assert_called_once_with({},reference_images=None)

    def test_normalizer_explicit_empty_reference_list_skips_fallback_refs(self):
        fallback,stub,_=self.normalizer_dependencies();fallback['reference_images']=[{'source_path':'fallback'}]
        refs=[];r=self.api.normalize_accessory_ai_profile({'reference_images':refs}, {})
        self.assertEqual(r['reference_images'],[])
        self.assertIs(stub.call_args.kwargs['reference_images'],refs)

    def test_normalizer_reference_conversion_errors_propagate(self):
        self.normalizer_dependencies()
        for field in ('width','height','ordinal'):
            with self.assertRaises(ValueError):self.api.normalize_accessory_ai_profile({'reference_images':[{'source_path':'one',field:'bad'}]}, {})

    def test_normalizer_real_optional_float_rejects_negative_and_nan(self):
        real_number=self.api.optional_float
        self.normalizer_dependencies()
        self.replace('optional_float',new=real_number)
        for value in (0,-2,float('nan')):
            self.assertEqual(self.api.normalize_accessory_ai_profile({'top_view_aspect_ratio':value},{})['top_view_aspect_ratio'],2.0)
        self.assertEqual(self.api.normalize_accessory_ai_profile({'top_view_aspect_ratio':1.23456},{})['top_view_aspect_ratio'],1.235)

    def test_fallback_sorted_sources_cap_only_tag_prefix(self):
        self.text_dependencies()
        item={'name':'Named','source_files':['f.png','e.png','d.png','c.png','b.png','a.png','a.jpg']}
        result=self.api.fallback_accessory_ai_profile(item,reference_images=[])
        self.assertEqual(result['tags'],['text','detect_and_classify','a','b','c','d'])
        self.assertEqual(result['distinguishing_text'],['Named','a','b','c','d','e','f'])

    def test_fallback_alpha_callback_refresh_between_points(self):
        self.text_dependencies();self.replace('accessory_material_type',return_value='object')
        second=Mock(return_value='late')
        def first(item):
            self.api.object_alpha_material_policy=second
            return 'early'
        initial=self.replace('object_alpha_material_policy',side_effect=first)
        item={};result=self.api.fallback_accessory_ai_profile(item,reference_images=[])
        self.assertEqual(result['tags'],['object','detect_and_classify','early'])
        self.assertTrue(result['visual_signature'].endswith('alpha_policy=late'))
        initial.assert_called_once_with(item)
        second.assert_called_once_with(item)

    def test_normalizer_number_callee_selected_before_raw_get(self):
        self.normalizer_dependencies();late=Mock(return_value=9.0)
        early=self.replace('optional_float',return_value=1.23456)
        api=self.api;seen=[]
        class Raw(dict):
            def get(self,key,default=None):
                if key=='top_view_aspect_ratio':
                    seen.append(key);api.optional_float=late
                return super().get(key,default)
        raw=Raw(top_view_aspect_ratio=7)
        result=self.api.normalize_accessory_ai_profile(raw,{})
        self.assertEqual(result['top_view_aspect_ratio'],1.235)
        self.assertEqual(seen,['top_view_aspect_ratio'])
        early.assert_called_once_with(7)
        late.assert_not_called()

    def test_independent_instances_without_root_capabilities(self):
        from local_inspection_service.accessories.profile_projection import AccessoryProfileProjection
        from local_inspection_service.accessories.profile_projection_ports import ProfileIdentity,ProfileText,ProfileDimensions,ProfileReferences
        dependencies=['accessory_uid','accessory_material_type','object_alpha_material_policy','bounded_text','string_list','preferred_english_accessory_name','compact_english_accessory_name','profile_size_text','ai_profile_dimensions_from_physical_size','normalize_ai_profile_dimensions','ai_profile_top_view_aspect_ratio','optional_float','accessory_reference_image_contexts','fallback_accessory_ai_profile','AI_PROFILE_REFERENCE_IMAGES']
        poisons=[self.replace(name,new=Mock(side_effect=AssertionError('root capability forbidden'))) for name in dependencies]
        all_getters=[]
        def build(mark):
            fallback=self.fallback();fallback.update(name=mark,english_name=mark,description=mark,visual_signature=mark,dimensions_mm={'width':3})
            getters=[]
            def getter(value):
                m=Mock(return_value=value);getters.append(m);return m
            service=AccessoryProfileProjection(
                ProfileIdentity(getter(lambda item:mark),getter(lambda item:'object'),getter(lambda item:mark+' alpha')),
                ProfileText(getter(lambda value,limit:str(value or '')[:limit]),getter(lambda value,fallback=None,**kw:(value if isinstance(value,list) else fallback or [])[:kw.get('max_items',12)]),getter(lambda item:mark+' preferred'),getter(lambda value,**kw:str(value or '')),getter(lambda value:mark+' size')),
                ProfileDimensions(getter(lambda value:{'width':3}),getter(lambda raw,default:raw or default),getter(lambda dims:3.0),getter(lambda value:None if value is None else float(value))),
                ProfileReferences(getter(lambda item:[{'source_path':mark}]),getter(lambda item,reference_images=None:fallback),getter(1)))
            self.assertTrue(all(x.call_count==0 for x in getters))
            all_getters.extend(getters);return service
        a=build('A');b=build('B')
        def run(service):
            fallback=service.fallback_accessory_ai_profile({'name':'Named'})
            normalized=service.normalize_accessory_ai_profile({'reference_images':[{'source_path':'one'},{'source_path':'two'}]}, {})
            return fallback,normalized
        first=run(a);second=run(b);again=run(a)
        self.assertEqual(first,again)
        self.assertEqual([first[0]['accessory_id'],second[0]['accessory_id']],['A','B'])
        self.assertEqual([first[0]['english_name'],second[0]['english_name']],['A preferred','B preferred'])
        self.assertEqual([first[0]['reference_images'],second[0]['reference_images']],[[{'source_path':'A'}],[{'source_path':'B'}]])
        self.assertEqual([first[1]['name'],second[1]['name']],['A','B'])
        self.assertEqual([first[1]['accessory_id'],second[1]['accessory_id']],['A','B'])
        self.assertEqual(len(first[1]['reference_images']),1)
        self.assertEqual(first[1]['reference_images'][0]['accessory_id'],'A')
        self.assertEqual(first[1]['top_view_aspect_ratio'],3.0)
        self.assertTrue(all(x.call_count>0 for x in all_getters))
        self.assertTrue(all(x.call_count==0 for x in poisons))

if __name__=='__main__':unittest.main()

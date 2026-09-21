"""Offline original contracts for accessory profile payloads."""

import os

from pathlib import Path

import sys

import tempfile

import unittest

from contextlib import ExitStack

from unittest.mock import Mock,patch,call

sys.path.insert(0,str(Path.cwd()))

class AccessoryProfilePayloadContracts(unittest.TestCase):

    @classmethod

    def setUpClass(cls):

        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))

        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='accessory-profile-payloads-')))

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

    def profile(self, **overrides):
        value=dict(accessory_id='id',name='Name',material_type='object',expected_count=3,description='desc',tags=['tag'],visual_signature=['shape'],distinguishing_text=['text'],negative_cues=['other'],reference_images=[{'id':'ref'}],provider_cache={'key':'value'})
        value.update(overrides);return value

    def prompt_dependencies(self):
        self.replace('fallback_accessory_ai_profile',return_value={'z':1,'a':2})
        self.replace('accessory_uid',return_value='uid')
        self.replace('accessory_material_type',return_value='object')
        self.replace('size_reference_payload',return_value=None)

    def test_prompt_required_keys_and_native_projection(self):
        self.prompt_dependencies();size={'width':2};item={'name':'N','training_role':'r','physical_size':size,'source_files':['a/b.png','a/b.png'],'normalized_assets':[None,{'kind':'image'},{},42],'expected_count':-2}
        result=self.api.accessory_profile_prompt_payload(item)
        self.assertEqual(result['instruction'],'Return only deterministic JSON for an accessory profile with the required keys.')
        self.assertEqual(result['required_keys'],['z','a'])
        self.assertEqual(result['accessory'],{'accessory_id':'uid','name':'N','material_type':'object','training_role':'r','physical_size':size,'source_file_names':['b.png','b.png'],'normalized_asset_kinds':['image',None],'expected_count':-2})
        self.assertIs(result['accessory']['physical_size'],size)

    def test_prompt_size_reference_keys_and_usage(self):
        self.prompt_dependencies();reference={'id':'r','label':'L','kind':'card','long_mm':80,'short_mm':50,'note':'note','private':'excluded'}
        self.replace('size_reference_payload',return_value=reference)
        result=self.api.accessory_profile_prompt_payload({})['size_reference']
        self.assertEqual(set(result),{'id','label','kind','long_mm','short_mm','note','usage'})
        self.assertEqual(result['usage'],'至少有一张参考图里把该配件和这个参照物放在一起拍摄。请用参照物的已知真实尺寸作为比例尺，测量并推断配件的真实 length_mm/width_mm/height_mm。')
        self.assertEqual(result['long_mm'],80)
        self.assertIsNot(result,reference)

    def test_prompt_nonobject_and_false_reference_omission(self):
        self.prompt_dependencies();self.replace('accessory_material_type',return_value='text');reference=self.replace('size_reference_payload',side_effect=AssertionError('forbidden'))
        self.assertNotIn('size_reference',self.api.accessory_profile_prompt_payload({}))
        reference.assert_not_called()
        self.replace('accessory_material_type',return_value='object');self.replace('size_reference_payload',return_value={})
        self.assertNotIn('size_reference',self.api.accessory_profile_prompt_payload({}))

    def test_prompt_material_refresh_and_count_error(self):
        self.prompt_dependencies();self.replace('accessory_material_type',side_effect=['text','object']);self.replace('size_reference_payload',return_value={'id':'late'})
        result=self.api.accessory_profile_prompt_payload({})
        self.assertEqual(result['accessory']['material_type'],'text')
        self.assertEqual(result['size_reference']['id'],'late')
        self.replace('accessory_material_type',return_value='object')
        with self.assertRaises(ValueError):self.api.accessory_profile_prompt_payload({'expected_count':'bad'})

    def test_required_projection_aliases_and_input_unchanged(self):
        profile=self.profile();normalize=self.replace('normalize_accessory_ai_profile',return_value=profile);item={'ai_profile':{'old':True}};supplied={'chosen':True}
        result=self.api.required_accessory_profile_payload(item,5,supplied)
        normalize.assert_called_once_with(supplied,item)
        self.assertEqual(result['expected_count'],5)
        self.assertEqual(profile['expected_count'],3)
        self.assertEqual(result['label'],'Name')
        for key in ('tags','visual_signature','distinguishing_text','negative_cues','reference_images','provider_cache'):self.assertIs(result['profile'][key],profile[key])

    def test_required_profile_truthiness_precedence(self):
        normalize=self.replace('normalize_accessory_ai_profile',return_value=self.profile());existing={'existing':True};item={'ai_profile':existing}
        self.api.required_accessory_profile_payload(item,1,{})
        self.assertIs(normalize.call_args.args[0],existing)
        self.api.required_accessory_profile_payload({},1,None)
        self.assertEqual(normalize.call_args.args[0],{})

    def test_required_count_coercion_fallbacks(self):
        profile=self.profile();self.replace('normalize_accessory_ai_profile',return_value=profile)
        self.assertEqual(self.api.required_accessory_profile_payload({},0)['expected_count'],3)
        self.assertEqual(self.api.required_accessory_profile_payload({},-4)['expected_count'],1)
        self.assertEqual(self.api.required_accessory_profile_payload({},'bad')['expected_count'],3)
        profile['expected_count']='bad'
        self.assertEqual(self.api.required_accessory_profile_payload({},'bad')['expected_count'],1)

    def test_required_overflow_and_missing_keys_propagate(self):
        self.replace('normalize_accessory_ai_profile',return_value=self.profile())
        with self.assertRaises(OverflowError):self.api.required_accessory_profile_payload({},float('inf'))
        self.replace('normalize_accessory_ai_profile',return_value={})
        with self.assertRaises(KeyError):self.api.required_accessory_profile_payload({},1)

    def test_required_falsy_reference_cache_replaced(self):
        profile=self.profile(reference_images=[],provider_cache={});self.replace('normalize_accessory_ai_profile',return_value=profile)
        result=self.api.required_accessory_profile_payload({},1)['profile']
        self.assertEqual(result['reference_images'],[])
        self.assertIsNot(result['reference_images'],profile['reference_images'])
        self.assertEqual(result['provider_cache'],{})
        self.assertIsNot(result['provider_cache'],profile['provider_cache'])

    def test_required_normalizer_selected_before_raw_get(self):
        profile=self.profile();early=self.replace('normalize_accessory_ai_profile',return_value=profile);late=Mock(side_effect=AssertionError('late forbidden'));api=self.api
        class Item(dict):
            def get(self,key,default=None):api.normalize_accessory_ai_profile=late;return super().get(key,default)
        item=Item(ai_profile={'old':True});self.api.required_accessory_profile_payload(item,1)
        early.assert_called_once_with(item['ai_profile'],item)
        late.assert_not_called()

    def resolve_dependencies(self,items):
        self.replace('load_config',return_value={'accessories':items})
        self.replace('accessory_uid',side_effect=lambda item:item['id'])
        self.replace('fallback_accessory_ai_profile',return_value={'fallback':True})
        self.replace('bounded_text',side_effect=lambda value,limit:str(value)[:limit])
        return self.replace('required_accessory_profile_payload',side_effect=lambda item,count,profile:{'item':item,'count':count,'profile':profile})

    def test_resolve_filter_duplicate_order_last_catalog_wins(self):
        first={'id':'id','ai_profile':{'first':True}};last={'id':'id','ai_profile':{'last':True}};build=self.resolve_dependencies([first,None,last]);refs=[None,{},'id',{'id':' '},{'accessory_id':' id ','expected_count':2},{'id':'id','expected_count':-5}]
        result=self.api.resolve_required_accessory_refs(refs)
        self.assertEqual([x['count'] for x in result],[2,1])
        self.assertTrue(all(x['item'] is last for x in result))
        self.assertIs(result[0]['profile'],last['ai_profile'])
        self.assertEqual(build.call_count,2)

    def test_resolve_missing_item_defaults_and_count_errors(self):
        self.resolve_dependencies([]);bounded=self.replace('bounded_text',return_value='bounded')
        result=self.api.resolve_required_accessory_refs([{'id':'missing','name':'Name','expected_count':'bad'}])[0]
        self.assertEqual(result['item'],{'id':'missing','name':'bounded','material_type':'object','source_files':[],'normalized_assets':[]})
        self.assertEqual(result['count'],1)
        self.assertEqual(result['profile'],{'fallback':True})
        bounded.assert_called_once_with('Name',120)

    def test_resolve_empty_dict_profile_does_not_fallback(self):
        profile={};item={'id':'id','ai_profile':profile};self.resolve_dependencies([item]);fallback=self.replace('fallback_accessory_ai_profile',side_effect=AssertionError('forbidden'))
        result=self.api.resolve_required_accessory_refs([{'id':'id'}])
        self.assertIs(result[0]['profile'],profile)
        fallback.assert_not_called()

    def test_resolve_load_once_for_empty_input_and_errors_propagate(self):
        self.resolve_dependencies([]);load=self.replace('load_config',return_value={'accessories':[]})
        self.assertEqual(self.api.resolve_required_accessory_refs([]),[])
        load.assert_called_once_with()
        sentinel=RuntimeError('config');self.replace('load_config',side_effect=sentinel)
        with self.assertRaises(RuntimeError) as caught:self.api.resolve_required_accessory_refs([])
        self.assertIs(caught.exception,sentinel)

    def test_resolve_overflow_propagates_before_payload(self):
        build=self.resolve_dependencies([])
        with self.assertRaises(OverflowError):self.api.resolve_required_accessory_refs([{'id':'id','expected_count':float('inf')}])
        build.assert_not_called()

    def test_prompt_callback_refresh_and_reference_selection(self):
        self.prompt_dependencies();api=self.api;late_material=Mock(return_value='object')
        def first_material(item):api.accessory_material_type=late_material;return 'text'
        early_material=self.replace('accessory_material_type',side_effect=first_material)
        early_reference=self.replace('size_reference_payload',return_value={'id':'early'});late_reference=Mock(side_effect=AssertionError('late reference forbidden'))
        class Item(dict):
            def get(self,key,default=None):
                if key=='size_reference':api.size_reference_payload=late_reference
                return super().get(key,default)
        item=Item(size_reference='key');result=self.api.accessory_profile_prompt_payload(item)
        self.assertEqual(result['accessory']['material_type'],'text')
        self.assertEqual(result['size_reference']['id'],'early')
        early_material.assert_called_once_with(item)
        late_material.assert_called_once_with(item)
        early_reference.assert_called_once_with('key')
        late_reference.assert_not_called()

    def test_resolve_profile_repeated_reads_and_late_required_callback(self):
        second={'second':True};reads=[]
        class Item(dict):
            def get(self,key,default=None):
                if key=='ai_profile':reads.append(key);return {} if len(reads)==1 else second
                return super().get(key,default)
        item=Item(id='id');build=self.resolve_dependencies([item]);result=self.api.resolve_required_accessory_refs([{'id':'id'}])
        self.assertEqual(reads,['ai_profile','ai_profile'])
        self.assertIs(result[0]['profile'],second)
        early=self.resolve_dependencies([{'id':'id'}]);late=Mock(return_value={'late':True});api=self.api
        def fallback(item):api.required_accessory_profile_payload=late;return {'fallback':True}
        self.replace('fallback_accessory_ai_profile',side_effect=fallback)
        self.assertEqual(self.api.resolve_required_accessory_refs([{'id':'id'}]),[{'late':True}])
        early.assert_not_called()
        late.assert_called_once_with({'id':'id'},1,{'fallback':True})

    def test_resolve_partial_failures_and_nested_count_exceptions(self):
        from copy import deepcopy
        refs=[{'id':'one'},{'id':'missing'},{'id':'three'}];before=deepcopy(refs);items=[{'id':'one','ai_profile':{}},{'id':'three','ai_profile':{}}]
        build=self.resolve_dependencies(items);error=RuntimeError('fallback failed');self.replace('fallback_accessory_ai_profile',side_effect=error)
        with self.assertRaises(RuntimeError) as caught:self.api.resolve_required_accessory_refs(refs)
        self.assertIs(caught.exception,error)
        build.assert_called_once_with(items[0],1,items[0]['ai_profile'])
        self.assertEqual(refs,before)
        self.resolve_dependencies([{'id':name,'ai_profile':{}} for name in ('one','missing','three')]);error2=ValueError('required failed');build=self.replace('required_accessory_profile_payload',side_effect=[{'ok':True},error2])
        with self.assertRaises(ValueError) as caught:self.api.resolve_required_accessory_refs(refs)
        self.assertIs(caught.exception,error2)
        self.assertEqual(build.call_count,2)
        self.assertEqual(refs,before)
        self.stack.close();self.stack=ExitStack();self.addCleanup(self.stack.close)
        class Count:
            def __int__(self):raise TypeError('invalid count')
        profile=self.profile(expected_count=7);self.replace('normalize_accessory_ai_profile',return_value=profile)
        self.assertEqual(self.api.required_accessory_profile_payload({},Count())['expected_count'],7)
        profile['expected_count']=float('inf')
        with self.assertRaises(OverflowError):self.api.required_accessory_profile_payload({},Count())

    def test_independent_instances_with_root_callbacks_unused(self):
        from local_inspection_service.accessories.profile_payloads import AccessoryProfilePayloads
        from local_inspection_service.accessories.profile_payload_ports import PayloadIdentity,PayloadProfiles,PayloadCatalog
        names=['accessory_uid','accessory_material_type','fallback_accessory_ai_profile','normalize_accessory_ai_profile','required_accessory_profile_payload','size_reference_payload','load_config','bounded_text']
        poisons=[self.replace(name,side_effect=AssertionError('root callback forbidden')) for name in names]
        reads=[]
        def make(marker):
            def getter(name,value):
                def get():reads.append((marker,name));return value
                return get
            service=AccessoryProfilePayloads(
                PayloadIdentity(getter('accessory_uid',lambda item:marker+'-id'),getter('accessory_material_type',lambda item:'object')),
                PayloadProfiles(getter('fallback_accessory_ai_profile',lambda item,reference_images=None:{'required_key':marker}),getter('normalize_accessory_ai_profile',lambda raw,item:self.profile(name=marker,tags=[marker])),getter('required_accessory_profile_payload',lambda item,expected_count,profile=None:{'marker':marker,'count':expected_count}),getter('size_reference_payload',lambda key:{'id':marker})),
                PayloadCatalog(getter('load_config',lambda:{'accessories':[]}),getter('bounded_text',lambda value,limit=240:marker)))
            self.assertEqual(reads,[])
            return service
        first=make('A');second=make('B')
        self.assertIsNot(first,second)
        for service,marker in [(first,'A'),(second,'B'),(first,'A')]:
            prompt=service.accessory_profile_prompt_payload({'name':marker})
            required=service.required_accessory_profile_payload({},2)
            resolved=service.resolve_required_accessory_refs([{'id':'unknown','expected_count':2}])
            self.assertEqual(prompt['accessory']['accessory_id'],marker+'-id')
            self.assertEqual(prompt['size_reference']['id'],marker)
            self.assertEqual(required['name'],marker)
            self.assertEqual(required['profile']['tags'],[marker])
            self.assertEqual(resolved,[{'marker':marker,'count':2}])
        for marker in ['A','B']:self.assertEqual({name for seen,name in reads if seen==marker},set(names))
        for poison in poisons:poison.assert_not_called()

if __name__=='__main__':
    unittest.main()

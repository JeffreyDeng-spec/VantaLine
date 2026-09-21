"""Offline original contracts for accessory physical dimensions."""

import os

from pathlib import Path

import sys

import tempfile

import unittest

from contextlib import ExitStack

from unittest.mock import Mock,patch,call

sys.path.insert(0,str(Path.cwd()))

class AccessoryDimensionsContracts(unittest.TestCase):

    @classmethod

    def setUpClass(cls):

        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))

        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='accessory-dimensions-')))

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

    def defaults(self):
        self.replace('STANDARD_PAPER_SIZES_MM',new={'A4':(210.0,297.0),'A5':(148.0,210.0)})
        self.replace('DEFAULT_OBJECT_SIZE_MM',new={'length_mm':40.0,'width_mm':30.0,'height_mm':20.0})

    def test_paper_preset_ignores_custom_dimensions(self):
        self.defaults()
        result=self.api.physical_size_payload('text','A5',999,888)
        self.assertEqual(result,{'kind':'paper','preset':'A5','width_mm':148.0,'height_mm':210.0})

    def test_custom_paper_uses_a4_fallback_and_keeps_precision(self):
        self.defaults()
        self.assertEqual(self.api.physical_size_payload('text','unknown',0,-2),{'kind':'paper','preset':'custom','width_mm':210.0,'height_mm':297.0})
        result=self.api.physical_size_payload('text','custom',33.3333,44.4444)
        self.assertEqual((result['width_mm'],result['height_mm']),(33.3333,44.4444))

    def test_object_payload_defaults_and_unrecognized_type(self):
        self.defaults()
        self.assertEqual(self.api.physical_size_payload('other'),{'kind':'object','length_mm':40.0,'width_mm':30.0,'height_mm':20.0})
        result=self.api.physical_size_payload('object',object_length_mm='12.3456',object_width_mm=0,object_height_mm=-1)
        self.assertEqual(result,{'kind':'object','length_mm':12.3456,'width_mm':30.0,'height_mm':20.0})

    def test_paper_profile_projection_sorts_and_rounds(self):
        result=self.api.ai_profile_dimensions_from_physical_size({'kind':'paper','width_mm':90.1234,'height_mm':210.556})
        self.assertEqual(result,{'length_mm':210.56,'width_mm':90.12,'height_mm':0.3})
        self.assertEqual(self.api.ai_profile_dimensions_from_physical_size({'kind':'paper'}),{'length_mm':297.0,'width_mm':210.0,'height_mm':0.3})

    def test_object_projection_defaults_and_rounding(self):
        self.defaults()
        self.assertEqual(self.api.ai_profile_dimensions_from_physical_size(None),{'length_mm':40.0,'width_mm':30.0,'height_mm':20.0})
        result=self.api.ai_profile_dimensions_from_physical_size({'length_mm':12.346,'width_mm':float('nan'),'height_mm':-2})
        self.assertEqual(result,{'length_mm':12.35,'width_mm':30.0,'height_mm':20.0})

    def test_ratio_orientation_missing_and_rounding(self):
        self.assertEqual(self.api.ai_profile_top_view_aspect_ratio({'length_mm':3,'width_mm':10}),3.333)
        self.assertEqual(self.api.ai_profile_top_view_aspect_ratio({'length_mm':10,'width_mm':3}),3.333)
        for dims in (None,{}, {'length_mm':0,'width_mm':3},{'length_mm':-1,'width_mm':3}):
            self.assertEqual(self.api.ai_profile_top_view_aspect_ratio(dims),1.0)

    def test_ratio_epsilon_floor(self):
        self.assertEqual(self.api.ai_profile_top_view_aspect_ratio({'length_mm':2,'width_mm':1e-8}),2000000.0)

    def test_normalization_raw_rounding_and_unrounded_fallback(self):
        result=self.api.normalize_ai_profile_dimensions({'length_mm':2.346,'width_mm':0},{'length_mm':9,'width_mm':'1.23456','height_mm':None})
        self.assertEqual(result,{'length_mm':2.35,'width_mm':1.23456,'height_mm':0.0})
        self.assertEqual(list(result),['length_mm','width_mm','height_mm'])

    def test_normalization_invalid_inputs_and_fallback_error(self):
        self.assertEqual(self.api.normalize_ai_profile_dimensions(None,None),{'length_mm':0.0,'width_mm':0.0,'height_mm':0.0})
        with self.assertRaises(ValueError):self.api.normalize_ai_profile_dimensions({}, {'width_mm':'invalid'})

    def test_apply_nonobject_short_circuits(self):
        material=self.replace('accessory_material_type',return_value='text')
        number=self.replace('optional_float',side_effect=AssertionError('number should not run'))
        payload=self.replace('physical_size_payload',side_effect=AssertionError('payload should not run'))
        item={};self.assertFalse(self.api.apply_ai_profile_dimensions_to_physical_size(item,{}))
        material.assert_called_once_with(item);number.assert_not_called();payload.assert_not_called()
        self.assertEqual(item,{})

    def test_apply_requires_all_three_dimensions(self):
        self.replace('accessory_material_type',return_value='object')
        payload=self.replace('physical_size_payload',side_effect=AssertionError('payload should not run'))
        item={'physical_size':{'existing':True}}
        self.assertFalse(self.api.apply_ai_profile_dimensions_to_physical_size(item,{'length_mm':4,'width_mm':3}))
        self.assertEqual(item,{'physical_size':{'existing':True}})
        payload.assert_not_called()

    def test_apply_equal_size_preserves_identity(self):
        self.replace('accessory_material_type',return_value='object')
        old={'kind':'object','length_mm':4.0,'width_mm':3.0,'height_mm':2.0};item={'physical_size':old}
        self.assertFalse(self.api.apply_ai_profile_dimensions_to_physical_size(item,{'length_mm':4,'width_mm':3,'height_mm':2}))
        self.assertIs(item['physical_size'],old)

    def test_apply_replacement_alias_and_keyword_arguments(self):
        self.replace('accessory_material_type',return_value='object')
        new={'synthetic':True};payload=self.replace('physical_size_payload',return_value=new)
        item={'physical_size':'invalid'}
        self.assertTrue(self.api.apply_ai_profile_dimensions_to_physical_size(item,{'length_mm':4,'width_mm':3,'height_mm':2}))
        self.assertIs(item['physical_size'],new)
        payload.assert_called_once_with('object',object_length_mm=4.0,object_width_mm=3.0,object_height_mm=2.0)

    def test_default_mapping_refresh_after_numeric_callback(self):
        self.defaults()
        def number(value):
            self.api.DEFAULT_OBJECT_SIZE_MM={'length_mm':70.0,'width_mm':60.0,'height_mm':50.0}
            return None
        self.replace('optional_float',side_effect=number)
        self.assertEqual(self.api.ai_profile_dimensions_from_physical_size({}),{'length_mm':70.0,'width_mm':60.0,'height_mm':50.0})

    def test_number_callee_selected_before_mapping_get(self):
        self.defaults();late=Mock(return_value=99.0);early=self.replace('optional_float',return_value=11.0);api=self.api
        class Size(dict):
            def get(self,key,default=None):
                if key=='length_mm':api.optional_float=late
                return super().get(key,default)
        result=self.api.ai_profile_dimensions_from_physical_size(Size(length_mm=4,width_mm=3,height_mm=2))
        self.assertEqual(result,{'length_mm':11.0,'width_mm':99.0,'height_mm':99.0})
        early.assert_called_once_with(4)
        self.assertEqual(late.call_args_list,[call(3),call(2)])

    def test_paper_mapping_reads_and_eager_default_argument(self):
        self.defaults();api=self.api;events=[]
        class First(dict):
            def __contains__(self,key):
                events.append(('first_contains',key));api.STANDARD_PAPER_SIZES_MM=second
                return dict.__contains__(self,key)
        class Second(dict):
            def __getattribute__(self,key):
                if key=='get':
                    events.append('select_second_get');api.STANDARD_PAPER_SIZES_MM=third
                return dict.__getattribute__(self,key)
            def get(self,key,default=None):
                events.append(('second_get',key,default));return dict.get(self,key,default)
        class Third(dict):
            def __getitem__(self,key):
                events.append(('third_default',key));api.STANDARD_PAPER_SIZES_MM=fourth
                return dict.__getitem__(self,key)
        class Fourth(dict):
            def __contains__(self,key):events.append(('fourth_contains',key));return dict.__contains__(self,key)
        second=Second(A5=(148.0,210.0));third=Third(A4=(100.0,200.0));fourth=Fourth(A4=(1.0,2.0))
        self.replace('STANDARD_PAPER_SIZES_MM',new=First(A5=(9.0,10.0)))
        result=self.api.physical_size_payload('text','A5',999,888)
        self.assertEqual(result,{'kind':'paper','preset':'A5','width_mm':999.0,'height_mm':888.0})
        self.assertEqual(events,[('first_contains','A5'),'select_second_get',('third_default','A4'),('second_get','A5',(100.0,200.0)),('fourth_contains','A5')])
        self.replace('STANDARD_PAPER_SIZES_MM',new={'A5':(148.0,210.0)})
        with self.assertRaises(KeyError) as caught:self.api.physical_size_payload('text','A5')
        self.assertEqual(caught.exception.args,('A4',))

    def test_normalization_fallback_lazy_order_and_exception_identity(self):
        class Forbidden(dict):
            def get(self,*args):raise AssertionError('valid raw must skip fallback')
        self.assertEqual(self.api.normalize_ai_profile_dimensions({'length_mm':1,'width_mm':2,'height_mm':3},Forbidden()),{'length_mm':1.0,'width_mm':2.0,'height_mm':3.0})
        events=[];sentinel=ValueError('fallback conversion sentinel')
        class Broken:
            def __float__(self):raise sentinel
        class Fallback(dict):
            def get(self,key,default=None):events.append(key);return dict.get(self,key,default)
        with self.assertRaises(ValueError) as caught:self.api.normalize_ai_profile_dimensions({},Fallback(length_mm=1,width_mm=2,height_mm=Broken()))
        self.assertIs(caught.exception,sentinel)
        self.assertEqual(events,['length_mm','width_mm','height_mm'])

    def test_apply_payload_selected_after_numbers_and_failure_state(self):
        self.replace('accessory_material_type',return_value='object');events=[];new={'synthetic':'new'}
        late=Mock(side_effect=lambda *a,**kw:(events.append('payload'),new)[1])
        initial=self.replace('physical_size_payload',side_effect=AssertionError('old payload forbidden'))
        def number(value):
            events.append(('number',value));self.api.physical_size_payload=late;return float(value)
        self.replace('optional_float',side_effect=number)
        item={};dims={'length_mm':4,'width_mm':3,'height_mm':2}
        self.assertTrue(self.api.apply_ai_profile_dimensions_to_physical_size(item,dims))
        self.assertEqual(events,[('number',4),('number',3),('number',2),'payload'])
        self.assertIs(item['physical_size'],new);initial.assert_not_called()
        old={'original':True};item={'physical_size':old};number_error=RuntimeError('number sentinel')
        with patch.object(self.api,'optional_float',side_effect=[4.0,number_error]),patch.object(self.api,'physical_size_payload') as payload:
            with self.assertRaises(RuntimeError) as caught:self.api.apply_ai_profile_dimensions_to_physical_size(item,dims)
            self.assertIs(caught.exception,number_error);self.assertIs(item['physical_size'],old);payload.assert_not_called()
        payload_error=ValueError('payload sentinel')
        with patch.object(self.api,'optional_float',side_effect=float),patch.object(self.api,'physical_size_payload',side_effect=payload_error):
            with self.assertRaises(ValueError) as caught:self.api.apply_ai_profile_dimensions_to_physical_size(item,dims)
            self.assertIs(caught.exception,payload_error);self.assertIs(item['physical_size'],old)

    def test_independent_instances_without_root_capabilities(self):
        from local_inspection_service.accessories.physical_dimensions import AccessoryDimensions
        from local_inspection_service.accessories.physical_dimension_ports import DimensionValues,DimensionUpdates
        names=['optional_float','STANDARD_PAPER_SIZES_MM','DEFAULT_OBJECT_SIZE_MM','accessory_material_type','physical_size_payload']
        poisons=[self.replace(name,new=Mock(side_effect=AssertionError('root dependency forbidden'))) for name in names]
        getters=[]
        def build(mark,scale):
            own=[]
            def getter(value):
                callback=Mock(return_value=value);own.append(callback);return callback
            service=AccessoryDimensions(
                DimensionValues(getter(lambda value:None if value is None else float(value)),getter({'A4':(10.0*scale,20.0*scale)}),getter({'length_mm':4.0*scale,'width_mm':3.0*scale,'height_mm':2.0*scale})),
                DimensionUpdates(getter(lambda item:'object'),getter(lambda *args,**kwargs:{'kind':'object','marker':mark})))
            self.assertTrue(all(x.call_count==0 for x in own));getters.extend(own);return service
        a=build('A',1);b=build('B',2)
        def run(service):
            paper=service.physical_size_payload('text')
            dims=service.ai_profile_dimensions_from_physical_size(None)
            ratio=service.ai_profile_top_view_aspect_ratio(dims)
            normalized=service.normalize_ai_profile_dimensions({'length_mm':1.2345},dims)
            item={};changed=service.apply_ai_profile_dimensions_to_physical_size(item,dims)
            return paper,dims,ratio,normalized,item,changed
        first=run(a);second=run(b);again=run(a)
        self.assertEqual(first,again)
        self.assertEqual([first[0]['width_mm'],second[0]['width_mm']],[10.0,20.0])
        self.assertEqual([first[1]['length_mm'],second[1]['length_mm']],[4.0,8.0])
        self.assertEqual(first[2],1.333)
        self.assertEqual(first[3],{'length_mm':1.23,'width_mm':3.0,'height_mm':2.0})
        self.assertEqual([first[4]['physical_size']['marker'],second[4]['physical_size']['marker']],['A','B'])
        self.assertTrue(first[5] and second[5])
        self.assertIsNot(first[4],second[4])
        self.assertTrue(all(x.call_count>0 for x in getters))
        self.assertTrue(all(x.call_count==0 for x in poisons))

if __name__=='__main__':unittest.main()

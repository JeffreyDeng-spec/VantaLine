"""Existing accessory selection and reference/render dimensions."""
import ast,os,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_ACCESSORY_SELECTION_BASELINE_SOURCE')
NAMES={'normalize_size_reference','size_reference_payload','physical_render_size_px','selected_accessories','resolve_accessory_id'}
def create(b):
 if BASELINE:
  nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==5;ns=dict(b,Any=Any);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
 from local_inspection_service.accessories.catalog import AccessorySelection, AccessorySelectionDependencies
 from local_inspection_service.accessories.physical_dimensions import ReferenceDimensions
 from local_inspection_service.accessories.physical_dimension_ports import ReferenceDimensionValues
 dimension=ReferenceDimensions(ReferenceDimensionValues(**{n:lambda n=n:b[n] for n in ('SIZE_REFERENCE_OBJECTS','normalize_size_reference','MM_TO_PREVIEW_PX','DEFAULT_OBJECT_SIZE_MM')}));selection=AccessorySelection(AccessorySelectionDependencies(**{n:lambda n=n:b[n] for n in ('accessory_uid','serialize_accessory','accessory_lookup_by_id')}));b['normalize_size_reference']=dimension.normalize_size_reference
 return SimpleNamespace(**{n:getattr(dimension if n in {'normalize_size_reference','size_reference_payload','physical_render_size_px'} else selection,n) for n in NAMES}),b
class Contracts(unittest.TestCase):
 def setUp(self):
  self.items=[{'id':'a','name':'old'},{'id':'b'},{'id':'a','name':'new'}];b={'SIZE_REFERENCE_OBJECTS':{'a4':{'id':'a4','nested':[]},'ruler':{'id':'ruler'}},'MM_TO_PREVIEW_PX':2.,'DEFAULT_OBJECT_SIZE_MM':{'length_mm':170.,'width_mm':38.,'height_mm':38.},'accessory_uid':lambda i:i['id'],'serialize_accessory':lambda i:dict(i),'accessory_lookup_by_id':lambda c:{i['id']:i for i in c.get('accessories',[])}};self.s,self.b=create(b)
 def test_reference_alias_normalization_and_known_key_precedence(self):
  for v in ('',None,'无',' null ','NO'):self.assertEqual(self.s.normalize_size_reference(v),'')
  for v in ('尺子','直尺','卷尺','rule'):self.assertEqual(self.s.normalize_size_reference(v),'ruler')
  self.assertEqual(self.s.normalize_size_reference(' A4纸 '),'a4');self.assertEqual(self.s.normalize_size_reference('unknown'),'');self.b['SIZE_REFERENCE_OBJECTS']['rule']={};self.assertEqual(self.s.normalize_size_reference('rule'),'rule')
 def test_reference_payload_shallow_copy_missing_and_late_normalizer(self):
  original=self.b['SIZE_REFERENCE_OBJECTS']['a4'];p=self.s.size_reference_payload('a4');self.assertEqual(p,original);self.assertIsNot(p,original);self.assertIs(p['nested'],original['nested']);self.assertIsNone(self.s.size_reference_payload('a5纸'));self.b['normalize_size_reference']=lambda v:'ruler';self.assertEqual(self.s.size_reference_payload('a4'),{'id':'ruler'})
 def test_render_defaults_minima_and_old_numeric_failures(self):
  self.assertEqual(self.s.physical_render_size_px({},'text'),(420,594));self.assertEqual(self.s.physical_render_size_px({},'object'),(340,76));self.assertEqual(self.s.physical_render_size_px({'physical_size':{'length_mm':-2,'width_mm':-3,'height_mm':-4}},'object'),(34,16));self.assertEqual(self.s.physical_render_size_px({'physical_size':{'width_mm':1,'height_mm':1}},'text'),(70,90))
  with self.assertRaises(ValueError):self.s.physical_render_size_px({'physical_size':{'width_mm':'bad'}},'text')
 def test_selection_eager_serialization_duplicate_ids_and_requested_order(self):
  calls=[];self.b['serialize_accessory']=lambda i:calls.append(i) or dict(i);result=self.s.selected_accessories({'accessories':self.items},['b','a','a','absent']);self.assertEqual([i['id'] for i in result],['b','a','a']);self.assertEqual(result[1]['name'],'new');self.assertIs(result[1],result[2]);self.assertEqual(calls,self.items)
 def test_selection_fallback_repeats_serialization_in_original_order(self):
  calls=[];self.b['serialize_accessory']=lambda i:calls.append(i) or dict(i);result=self.s.selected_accessories({'accessories':self.items},['unknown']);self.assertEqual(result,self.items);self.assertEqual(calls,self.items+self.items);self.assertEqual(self.s.selected_accessories({},[]),[])
 def test_selection_failure_is_not_hidden_and_partial_calls_preserved(self):
  calls=[]
  def serialize(i):
   calls.append(i)
   if i['id']=='b':raise RuntimeError('serialize')
   return i
  self.b['serialize_accessory']=serialize
  with self.assertRaisesRegex(RuntimeError,'serialize'):self.s.selected_accessories({'accessories':self.items},['a'])
  self.assertEqual(calls,self.items[:2])
 def test_alias_lookup_preserves_canonical_and_item_identity(self):
  item={'id':'canonical'};self.b['accessory_lookup_by_id']=Mock(return_value={'alias':item});result=self.s.resolve_accessory_id({},' alias ');self.assertEqual(result[0],'canonical');self.assertIs(result[1],item);self.assertIsNone(self.s.resolve_accessory_id({},'missing'));self.b['accessory_lookup_by_id']=lambda c:{'alias':{}};self.assertIsNone(self.s.resolve_accessory_id({},'alias'))
 @unittest.skipIf(bool(BASELINE),'new focused services')
 def test_independent_services_follow_own_settings(self):
  b=dict(self.b,MM_TO_PREVIEW_PX=4.);other,_=create(b);self.assertEqual(other.physical_render_size_px({},'text'),(840,1188));self.assertEqual(self.s.physical_render_size_px({},'text'),(420,594))
if __name__=='__main__':unittest.main()

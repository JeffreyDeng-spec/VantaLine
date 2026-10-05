"""Small text, environment and image/box policies; synthetic values only."""
import ast,os,re,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_FOUNDATION_POLICIES_BASELINE_SOURCE')
NAMES={'bounded_text','env_flag','resize_bgr_max_side','bbox_iou_xyxy'}
def functions():
 if BASELINE:
  nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==4
  ns=dict(Any=Any,os=os,re=re,np=np,cv2=cv2);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(**{n:ns[n] for n in NAMES})
 from local_inspection_service.runtime.text_policy import bounded_text
 from local_inspection_service.config.environment import env_flag
 from local_inspection_service.detection.geometry import bbox_iou_xyxy
 from local_inspection_service.detection.image_geometry import resize_bgr_max_side
 return SimpleNamespace(bounded_text=bounded_text,env_flag=env_flag,bbox_iou_xyxy=bbox_iou_xyxy,resize_bgr_max_side=resize_bgr_max_side)
class Contracts(unittest.TestCase):
 def setUp(self):self.f=functions()
 def test_text_whitespace_falsey_and_slice(self):
  self.assertEqual(self.f.bounded_text(' \tAlpha\n中　Beta  '),'Alpha 中 Beta')
  for value in (None,False,0,[],{}):self.assertEqual(self.f.bounded_text(value),'')
  self.assertEqual(self.f.bounded_text('abcdef',-2),'abcd');self.assertEqual(self.f.bounded_text('abcdef',0),'')
 def test_text_conversion_and_limit_errors(self):
  class Value:
   def __str__(self):raise ValueError('conversion')
  with self.assertRaisesRegex(ValueError,'conversion'):self.f.bounded_text(Value())
  with self.assertRaises(TypeError):self.f.bounded_text('text',1.2)
 def test_environment_known_values_and_default(self):
  name='VANTALINE_SYNTHETIC_FLAG_CONTRACT'
  with patch.dict(os.environ,{},clear=True):
   self.assertFalse(self.f.env_flag(name));marker=object();self.assertIs(self.f.env_flag(name,marker),marker)
   for value in ('1',' TRUE ','Yes','on','ENABLED'):os.environ[name]=value;self.assertTrue(self.f.env_flag(name))
   for value in ('','0','false','unknown','no','disabled'):os.environ[name]=value;self.assertFalse(self.f.env_flag(name,True))
 def test_box_geometry_and_integer_coercion(self):
  f=self.f.bbox_iou_xyxy;self.assertEqual(f([0,0,2,2],[1,1,3,3]),1/7);self.assertEqual(f([0,0,2,2],[2,2,3,3]),0);self.assertEqual(f([3,3,0,0],[0,0,1,1]),0);self.assertEqual(f([0,0,1.9,1.9],[0,0,1,1]),1);self.assertEqual(f([0,0],None),0)
  with self.assertRaises(TypeError):f([0,0,1,1],None)
  with self.assertRaises(ValueError):f([0,0,'bad',1],[0,0,1,1])
 def test_box_synthetic_symmetric_and_bounds(self):
  rng=np.random.default_rng(861);f=self.f.bbox_iou_xyxy
  for _ in range(600):
   a=rng.integers(-30,30,size=4).tolist();b=rng.integers(-30,30,size=4).tolist();x=f(a,b);self.assertEqual(x,f(b,a));self.assertGreaterEqual(x,0);self.assertLessEqual(x,1)
 def test_resize_identity_and_rounding(self):
  a=np.zeros((3,5,3),np.uint8);self.assertIs(self.f.resize_bgr_max_side(a,5),a);self.assertIs(self.f.resize_bgr_max_side(a,8),a);self.assertEqual(self.f.resize_bgr_max_side(a,3).shape,(2,3,3));self.assertEqual(self.f.resize_bgr_max_side(a,0).shape,(1,1,3));self.assertEqual(self.f.resize_bgr_max_side(a,-2).shape,(1,1,3))
 def test_resize_backend_arguments_and_error_identity(self):
  a=np.zeros((7,11,3),np.uint8);result=object()
  with patch.object(cv2,'resize',return_value=result) as resize:self.assertIs(self.f.resize_bgr_max_side(a,5),result);resize.assert_called_once_with(a,(5,3),interpolation=cv2.INTER_AREA)
  error=RuntimeError('resize')
  with patch.object(cv2,'resize',side_effect=error),self.assertRaises(RuntimeError) as caught:self.f.resize_bgr_max_side(a,5)
  self.assertIs(caught.exception,error)
 @unittest.skipIf(bool(BASELINE),'candidate direct imports only')
 def test_entry_exports_actual_implementations(self):
  tree=ast.parse((ROOT/'local_inspection_service/server.py').read_text());imports={a.name for n in tree.body if isinstance(n,ast.ImportFrom) and n.module in {'runtime.text_policy','config.environment','detection.geometry','detection.image_geometry'} for a in n.names};self.assertTrue(NAMES<=imports);self.assertFalse(any(isinstance(n,ast.FunctionDef) and n.name in NAMES for n in tree.body))
if __name__=='__main__':unittest.main()

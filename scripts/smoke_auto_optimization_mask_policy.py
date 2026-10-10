"""Synthetic mask prompt, geometry and artifact-adapter behavior contract."""
import ast
from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from typing import Any
import unittest
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_application_test_methods import auto_method
from auto_optimization_test_ports import assert_capability_owner
BASELINE=os.environ.get("VANTALINE_AUTO_MASK_POLICY_BASELINE_SOURCE")
PROMPT_NAMES={"auto_optimize_mask_system_prompt","auto_optimize_mask_owner_user","auto_optimize_accessory_lookup_for_sample","auto_optimize_mask_target_profile","auto_optimize_mask_target_payload","auto_optimize_mask_user_prompt","auto_optimize_multicolor_mask_prompt"}
VISUAL_NAMES={"decode_multicolor_mask","draw_auto_optimize_review_overlay","auto_optimize_text_mask_requires_document_gate","validate_auto_optimize_text_mask_region","auto_optimize_mask_verifier_overlay","auto_optimize_mask_verifier_crop","clamp_unit_score"}
NAMES=PROMPT_NAMES|VISUAL_NAMES

def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding="utf-8-sig")).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==14
        ns=dict(bindings,Any=Any,Path=Path,json=json,cv2=cv2,np=np);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,"exec"),ns)
        return SimpleNamespace(**{n:ns[n] for n in NAMES}),lambda n,v:ns.__setitem__(n,v)
    from local_inspection_service.training.auto_optimization_mask_prompts import AutoOptimizationMaskPrompts
    from local_inspection_service.training.auto_optimization_mask_visuals import AutoOptimizationMaskVisuals
    from local_inspection_service.training.auto_optimization_mask_ports import AutoOptimizationMaskPromptPorts,AutoOptimizationMaskVisualPorts
    def ports(kind):return kind(**{f.name:(lambda name=f.name:bindings[name]) for f in fields(kind)})
    prompts=AutoOptimizationMaskPrompts(ports(AutoOptimizationMaskPromptPorts));visuals=AutoOptimizationMaskVisuals(ports(AutoOptimizationMaskVisualPorts))
    methods={**{n:getattr(prompts,n) for n in PROMPT_NAMES},**{n:getattr(visuals,n) for n in VISUAL_NAMES}};bindings.update(methods)
    return SimpleNamespace(**methods),lambda n,v:bindings.__setitem__(n,v)

class MaskContract(unittest.TestCase):
    def fixture(self):
        writes=[];events=[]
        def write(path,image,params):writes.append((path,image.copy(),params));return False
        def profile(candidate,item,**kw):events.append((candidate,item,kw));return {"profile":"fixture"}
        bindings={"LEGACY_OWNER_ID":"legacy","AUTO_OPTIMIZE_MASK_SYSTEM_PROMPT_VERSION":"structured_profile_v1","DOCUMENT_LIKE_TEXT_HINTS":("manual","paper","说明"),
          "bounded_text":lambda x,n:str(x)[:n],"string_list":lambda v:v if isinstance(v,list) else [],"accessory_material_type":lambda v:"object",
          "load_config":lambda:{"source":"config"},"scope_config_for_user":lambda c,u:{"scoped":u["id"]},"accessory_lookup_by_id":lambda c:c,
          "build_mask_target_profile":profile,"_image_files":SimpleNamespace(imwrite=write),"public_output_url_for_existing":lambda p:"fixture-url"}
        service,replace=create(bindings)
        assignments=[{"candidate":{"accessory_id":"a","label":"配件 A"},"profile":{"description":"sample description","positive_cues":["solid"]},"palette":{"name":"green","hex":"#00ff00","rgb":[0,255,0]}}]
        return SimpleNamespace(service=service,replace=replace,writes=writes,events=events,assignments=assignments)

    def test_prompt_bytes_are_frozen(self):
        f=self.fixture();cases=[(f.service.auto_optimize_mask_system_prompt(),903,"acecd2fd81b2386f4052aa1d212a16c22ed2416e2c6c2fcaf6ecfcd287d66e3e"),(f.service.auto_optimize_mask_user_prompt(f.assignments,input_w=120,input_h=80),1140,"0db42287cba08fbbbcd8f71533221dd2ade74d0aeec71c9bd5b4784bae574455"),(f.service.auto_optimize_multicolor_mask_prompt(f.assignments,input_w=120,input_h=80),1192,"b99d843d07fb119c89b9828943a5b43b5e9ba20d7df8509c03eb1a92d18b8129")]
        for value,size,digest in cases:self.assertEqual(len(value.encode()),size);self.assertEqual(hashlib.sha256(value.encode()).hexdigest(),digest)

    def test_owner_and_original_scoping_fallback(self):
        f=self.fixture();self.assertEqual(f.service.auto_optimize_mask_owner_user({}),{"id":"legacy","username":"legacy","role":"admin"});self.assertEqual(f.service.auto_optimize_accessory_lookup_for_sample({"owner_user_id":"alice"}),{"scoped":"alice"})
        events=[]
        def load():events.append("load");return {"source":"fallback"}
        def fail(*a):events.append("scope");raise ValueError("fixture")
        f.replace("load_config",load);f.replace("scope_config_for_user",fail);self.assertEqual(f.service.auto_optimize_accessory_lookup_for_sample({}),{"source":"fallback"});self.assertEqual(events,["load","scope","load"])

    def test_profile_callbacks_and_payload_identity(self):
        f=self.fixture();candidate={"accessory_id":" a "};item={"id":"a"};self.assertEqual(f.service.auto_optimize_mask_target_profile(candidate,{"a":item}),{"profile":"fixture"});self.assertIs(f.events[0][0],candidate);self.assertIs(f.events[0][1],item);self.assertEqual(set(f.events[0][2]),{"bounded_text","string_list","accessory_material_type"})
        cues=["solid"];payload=f.service.auto_optimize_mask_target_payload({"candidate":{"label":"x"*130},"profile":{"positive_cues":cues,"negative_cues":(),"mask_scope":"body"},"palette":{"rgb":[-1,4.9,999]}},2)
        self.assertEqual(payload["assigned_color"]["rgb"],[0,4,255]);self.assertEqual(len(payload["label"]),120);self.assertIs(payload["ai_profile"]["positive_cues"],cues);self.assertEqual(payload["ai_profile"]["negative_cues"],[]);self.assertEqual(payload["mask_scope"],"body")

    def test_mask_decode_tolerance_component_size_and_duplicate_metadata(self):
        f=self.fixture();image=np.zeros((32,32,3),np.uint8);image[2:6,2:7]=(0,171,0);image[10:13,10:13]=(0,255,0);image[20:24,20:25]=(0,170,0)
        assignment={"candidate":{"accessory_id":"a","label":"A"},"palette":{"name":"green","bgr":(0,255,0)}}
        masks,meta=f.service.decode_multicolor_mask(image,[assignment,assignment]);self.assertEqual(int(np.count_nonzero(masks["a"])),20);self.assertEqual(meta["total_area_px"],40);self.assertEqual(len(meta["colors"]),2);self.assertTrue(np.all(image[2:6,2:7,1]==171))
        self.assertEqual(f.service.decode_multicolor_mask(None,[]),({}, {"ok":False,"reason":"generated_mask_unreadable"}))

    def test_document_gate_and_region_thresholds(self):
        f=self.fixture();fn=f.service.auto_optimize_text_mask_requires_document_gate
        self.assertFalse(fn({"label":"manual"},{"material_type":"object"}));self.assertTrue(fn({"label":"MANUAL"},{"material_type":" Text "}));self.assertFalse(fn({}, {"material_type":"text","positive_cues":("manual",)}))
        image=np.full((10,10,3),255,np.uint8);mask=np.full((10,10),255,np.uint8);candidate={"label":"manual"};profile={"material_type":"text"}
        result=f.service.validate_auto_optimize_text_mask_region(image,mask,[-4,-3,20,20],candidate,profile);self.assertEqual(result,{"ok":True,"visible_pixels":100,"bbox_xyxy":[0,0,10,10],"paper_like_ratio":1.0,"light_ratio":1.0})
        self.assertEqual(f.service.validate_auto_optimize_text_mask_region(image,mask*0,[0,0,10,10],candidate,profile)["reason"],"text_mask_region_empty")
        self.assertEqual(f.service.validate_auto_optimize_text_mask_region(image*0,mask,[0,0,10,10],candidate,profile)["reason"],"text_mask_region_not_document_like")
        self.assertEqual(f.service.validate_auto_optimize_text_mask_region(image,mask,[],{},{}),{"ok":True,"skipped":True})

    def test_crop_copy_and_mask_threshold(self):
        f=self.fixture();image=np.full((8,8,3),80,np.uint8);mask=np.full((8,8),8,np.uint8);mask[2:4,2:4]=9
        crop=f.service.auto_optimize_mask_verifier_crop(image,{"bbox_xyxy":[1,1,5,5],"full_mask":mask});expected=np.zeros((4,4,3),np.uint8);expected[1:3,1:3]=80;np.testing.assert_array_equal(crop,expected);self.assertFalse(np.shares_memory(image,crop));self.assertIsNone(f.service.auto_optimize_mask_verifier_crop(image,{}))
        np.testing.assert_array_equal(f.service.auto_optimize_mask_verifier_overlay(image,[]),image)

    def test_review_writer_false_return_is_retained(self):
        f=self.fixture();image=np.zeros((96,96,3),np.uint8);original=image.copy()
        with tempfile.TemporaryDirectory(prefix="mask-policy-") as tmp:
            target=Path(tmp)/"nested"/"review.jpg";url,meta=f.service.draw_auto_optimize_review_overlay(image,[{"label":"配件","color":"green","bbox_xyxy":[-1,-2,20,30],"color_hex":"#00ff00"}],[],target)
            self.assertTrue(target.parent.is_dir());self.assertFalse(target.exists());self.assertEqual(url,"fixture-url");self.assertEqual(meta,{"boxes":[{"passed":True,"label":"green","bbox_xyxy":[0,0,20,30],"color":"#00ff00"}],"box_count":1});self.assertEqual(f.writes[0][2],[int(cv2.IMWRITE_JPEG_QUALITY),92]);self.assertFalse(np.array_equal(f.writes[0][1],image))
        np.testing.assert_array_equal(image,original)

    def test_score_bounds_and_error_identity(self):
        f=self.fixture();fn=f.service.clamp_unit_score;self.assertEqual([fn(-1),fn(2),fn(".4"),fn("bad",.8)],[0,1,.4,.8]);error=OverflowError("fixture")
        class Bad:
            def __float__(self):raise error
        with self.assertRaises(OverflowError) as raised:fn(Bad())
        self.assertIs(raised.exception,error)

    def test_text_callback_selected_before_argument(self):
        f=self.fixture();events=[];f.replace("bounded_text",lambda value,n:events.append("old") or str(value))
        class Candidate(dict):
            def get(self,key,*a):
                if key=="label":f.replace("bounded_text",lambda value,n:events.append("new") or str(value))
                return super().get(key,*a)
        f.service.auto_optimize_mask_target_payload({"candidate":Candidate(label="x")},1);self.assertEqual(events,["old"])

    @unittest.skipIf(BASELINE,"candidate-only root composition")
    def test_actual_root_getters_and_all_forwarders(self):
        import inspect
        from unittest.mock import Mock,patch
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        for suffix,names in (("prompts",PROMPT_NAMES),("visuals",VISUAL_NAMES)):
            service=getattr(server,"_auto_optimization_mask_"+suffix)
            for field in fields(service.ports): assert_capability_owner(self, service.ports, field.name, server)
            for name in names:
                fn=getattr(server,name);signature=inspect.signature(fn);args=[];kw={}
                for parameter in signature.parameters.values():
                    if parameter.default is not inspect.Parameter.empty:continue
                    if parameter.kind==inspect.Parameter.KEYWORD_ONLY:kw[parameter.name]=object()
                    else:args.append(object())
                bound=signature.bind(*args,**kw);bound.apply_defaults();expected=object();method=Mock(return_value=expected)
                with auto_method(self,service,name,method):
                    self.assertIs(fn(*args,**kw),expected);method.assert_called_once_with(*bound.args,**bound.kwargs)

    @unittest.skipIf(BASELINE,"candidate-only import")
    def test_lightweight_import(self):
        import subprocess
        subprocess.run([sys.executable,"-c","import sys; import local_inspection_service.training.auto_optimization_mask_prompts, local_inspection_service.training.auto_optimization_mask_visuals; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg'))"],cwd=ROOT,check=True)

if __name__=="__main__":unittest.main()

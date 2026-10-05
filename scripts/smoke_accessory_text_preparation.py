"""Legacy text-image preparation contracts with synthetic pixels and I/O substitutes."""
import ast
from dataclasses import fields
import io
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock,patch
import cv2
import numpy as np
from fastapi import HTTPException,UploadFile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_ACCESSORY_TEXT_PREPARATION_BASELINE_SOURCE')
NAMES=('order_points','target_paper_pixel_size','ratio_close','quad_is_axis_aligned','best_document_quad','document_quad_mean_size','detect_document_quad','letterbox_document_onto_paper','resize_document_to_paper','is_text_rectified_path','stable_text_crop_stem','text_raw_crop_prefix','text_raw_has_rectified','text_image_paths_for_upload_limit','text_accessory_source_count','validate_text_accessory_uploads','normalize_text_image')

ORIGINAL_DOCSTRINGS={'document_quad_mean_size': "Mean width / height (px) of an ordered tl,tr,br,bl quad — used to recover\n    the document's true (deskewed) proportions.", 'detect_document_quad': 'Robustly auto-crop the document/manual body. Tries edge contours first, then\n    bright-paper (Otsu) and low-saturation paper segmentation, so a manual shot on\n    a darker tabletop is still found even when its edges are weak. Returns an\n    ordered tl,tr,br,bl quad or None.', 'letterbox_document_onto_paper': 'Place a document image onto a clean paper-sized canvas preserving aspect\n    (white letterbox). Never stretches the content non-uniformly.', 'resize_document_to_paper': 'Resize a document image directly to the chosen paper pixel size.', 'normalize_text_image': 'Lightweight document pipeline (no image generation): auto-crop the document\n    body, deskew/perspective-correct any tilt, then normalize onto the chosen paper\n    page (A4/A5/...). The output is always exactly the paper pixel size.'}

def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==17
        ns=dict(bindings,Any=Any,Path=Path,re=re,cv2=cv2,np=np,UploadFile=UploadFile);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
    from local_inspection_service.accessories.text_preparation import AccessoryTextPreparation
    from local_inspection_service.accessories.text_preparation_ports import TextGeometry,TextSources,TextMedia
    def ports(cls):return cls(**{f.name:lambda name=f.name:bindings[name] for f in fields(cls)})
    service=AccessoryTextPreparation(ports(TextGeometry),ports(TextSources),ports(TextMedia));bindings.update({n:getattr(service,n) for n in NAMES});return service,bindings

class TextPreparationContract(unittest.TestCase):
    def fixture(self):
        image=np.arange(12*8*3,dtype=np.uint8).reshape(12,8,3);files=SimpleNamespace(imread=Mock(return_value=image),imwrite=Mock(return_value=True))
        b={'IMAGE_REFERENCE_SUFFIXES':{'.png','.jpg','.jpeg','.webp','.bmp'},'MAX_TEXT_ACCESSORY_IMAGES':2,'HTTPException':HTTPException,'optional_float':lambda v:float(v) if v is not None else None,'STANDARD_PAPER_SIZES_MM':{'A4':(210,297)},'_image_files':files}
        service,b=create(b);return SimpleNamespace(s=service,b=b,files=files,image=image)

    def test_geometry_order_sizes_ratios_and_strict_tilt(self):
        f=self.fixture();points=np.array([[9,12],[1,2],[1,12],[9,2]],dtype=np.int32);ordered=f.s.order_points(points);np.testing.assert_array_equal(ordered,[[1,2],[9,2],[9,12],[1,12]]);self.assertEqual(ordered.dtype,np.float32);self.assertEqual(f.s.document_quad_mean_size(ordered),(8,10));self.assertTrue(f.s.quad_is_axis_aligned(ordered,(100,100,3)))
        tilted=ordered.copy();tilted[1,1]+=2;self.assertFalse(f.s.quad_is_axis_aligned(tilted,(100,100,3)));self.assertTrue(f.s.ratio_close(108,100));self.assertFalse(f.s.ratio_close(108.01,100));self.assertFalse(f.s.ratio_close(0,1))
        self.assertEqual(f.s.target_paper_pixel_size(None),(848,1200));self.assertEqual(f.s.target_paper_pixel_size({'width_mm':300,'height_mm':100}),(1200,400));self.assertEqual(f.s.target_paper_pixel_size({'width_mm':0,'height_mm':0}),(848,1200))
        with self.assertRaises(ValueError):f.s.order_points(np.zeros((3,2)))

    def test_real_contours_and_segmentation_on_synthetic_paper(self):
        f=self.fixture();empty=np.zeros((120,160,3),dtype=np.uint8);self.assertIsNone(f.s.best_document_quad(empty));paper=empty.copy();cv2.rectangle(paper,(30,15),(125,105),(240,240,240),-1)
        for name in ('best_document_quad','detect_document_quad'):
            quad=getattr(f.s,name)(paper);self.assertIsNotNone(quad);self.assertEqual(quad.shape,(4,2));self.assertEqual(quad.dtype,np.float32);self.assertGreater(float(cv2.contourArea(quad)),7000)
            if name=='best_document_quad':self.assertLess(float(cv2.contourArea(quad)),11000)
            else:np.testing.assert_array_equal(quad,[[0,0],[159,0],[159,119],[0,119]])  # Original Otsu inversion admits this full-frame fallback.
        self.assertEqual(int(empty.sum()),0)

    def test_resize_and_letterbox_pixel_contract(self):
        f=self.fixture();image=np.full((4,8,3),17,dtype=np.uint8);boxed=f.s.letterbox_document_onto_paper(image,8,8);self.assertEqual(boxed.shape,(8,8,3));np.testing.assert_array_equal(boxed[2:6],image);self.assertTrue((boxed[:2]==255).all());self.assertTrue((boxed[6:]==255).all())
        resized=f.s.resize_document_to_paper(image,3,7);self.assertEqual(resized.shape,(7,3,3));self.assertTrue((resized==17).all());self.assertEqual(f.s.resize_document_to_paper(image,0,-2).shape,(1,1,3));self.assertTrue((image==17).all())

    def test_source_names_rectified_matching_and_original_priority(self):
        f=self.fixture();self.assertTrue(f.s.is_text_rectified_path('a_manual_rectified_2.PNG'));self.assertFalse(f.s.is_text_rectified_path('raw.png'));self.assertEqual(f.s.stable_text_crop_stem('中文 .png'),'document');self.assertEqual(f.s.text_raw_crop_prefix('My scan.JPG'),'my_scan_manual_rectified');self.assertTrue(f.s.text_raw_has_rectified('My scan.JPG',[Path('x_my_scan.bin_manual_rectified.png')]));self.assertFalse(f.s.text_raw_has_rectified('raw.jpg',[Path('other_manual_rectified.png')]))
        item={'original_source_files':['raw.JPG','clip.mp4'],'source_files':['manual_rectified.png']};self.assertEqual(f.s.text_image_paths_for_upload_limit(item),[Path('raw.JPG')]);self.assertEqual(f.s.text_accessory_source_count(item),1)
        self.assertEqual(f.s.text_image_paths_for_upload_limit({'source_files':['a_rectified.png','raw.png','clip.mp4']}),[Path('raw.png')]);self.assertEqual(f.s.text_image_paths_for_upload_limit({'source_files':['a_rectified.png']}),[Path('a_rectified.png')])

    def test_upload_suffix_before_limit_and_exact_existing_count(self):
        f=self.fixture();image=UploadFile(io.BytesIO(),filename='a.PNG');bad=UploadFile(io.BytesIO(),filename='a.mp4');f.s.validate_text_accessory_uploads([image],existing_count=1)
        with self.assertRaises(HTTPException) as exc:f.s.validate_text_accessory_uploads([bad],existing_count=3)
        self.assertEqual(exc.exception.status_code,400);self.assertIn('不能上传视频',exc.exception.detail)
        with self.assertRaises(HTTPException) as exc:f.s.validate_text_accessory_uploads([image],existing_count=2)
        self.assertIn('最多上传 2',exc.exception.detail)

    def test_normalize_missing_no_quad_and_manual_resize(self):
        f=self.fixture();f.files.imread.return_value=None;self.assertIsNone(f.s.normalize_text_image(Path('raw.png'),Path('/synthetic')));f.files.imwrite.assert_not_called()
        f=self.fixture();f.b['detect_document_quad']=Mock(return_value=None);f.b['target_paper_pixel_size']=lambda s:(8,12);self.assertIsNone(f.s.normalize_text_image(Path('raw.png'),Path('/synthetic')));f.files.imwrite.assert_not_called()
        f=self.fixture();f.b['detect_document_quad']=Mock(side_effect=AssertionError('skip manual'));f.b['target_paper_pixel_size']=lambda s:(16,24);size={'width_mm':2};result=f.s.normalize_text_image(Path('raw_manual_rectified.png'),Path('/synthetic'),size)
        self.assertEqual(result['method'],'manual_rectified_resize');self.assertEqual((result['width'],result['height']),(16,24));self.assertIs(result['paper_size'],size);self.assertEqual(result['workflow'],['auto_crop','deskew_perspective_correction','paper_size_normalize']);self.assertEqual(Path(result['path']).name,'raw_manual_rectified_canonical.png');self.assertEqual(f.files.imwrite.call_count,1);self.assertEqual(f.files.imwrite.call_args.args[1].shape,(24,16,3));f.b['detect_document_quad'].assert_not_called()

    def test_normalize_both_quad_paths_and_writer_false_preserved(self):
        for near in (True,False):
            f=self.fixture();quad=np.array([[0,0],[7,0],[7,11],[0,11]],dtype=np.float32);f.b['target_paper_pixel_size']=lambda s:(8,12);f.b['detect_document_quad']=lambda i,a:quad;f.b['ratio_close']=lambda *a,**kw:near;f.files.imwrite.return_value=False
            result=f.s.normalize_text_image(Path('raw.png'),Path('/synthetic'));self.assertEqual(result['method'],'paper_quad_perspective' if near else 'paper_quad_deskew_resize');self.assertEqual((result['width'],result['height']),(8,12));self.assertEqual(f.files.imwrite.call_count,1)
        f=self.fixture();f.b['target_paper_pixel_size']=lambda s:(8,12);f.b['is_text_rectified_path']=lambda p:True;f.files.imwrite.side_effect=OSError('write')
        with self.assertRaisesRegex(OSError,'write'):f.s.normalize_text_image(Path('x.png'),Path('/synthetic'))
        self.assertEqual(f.files.imwrite.call_count,1)

    def test_late_geometry_and_media_facade_selection(self):
        f=self.fixture();replacement=SimpleNamespace(imwrite=Mock(return_value=True))
        def read(p):f.b['_image_files']=replacement;f.b['is_text_rectified_path']=lambda p:True;return f.image
        f.files.imread.side_effect=read;f.b['target_paper_pixel_size']=lambda s:(8,12);f.s.normalize_text_image(Path('x.png'),Path('/synthetic'));f.files.imwrite.assert_not_called();replacement.imwrite.assert_called_once()

    @unittest.skipIf(bool(BASELINE),'candidate wiring only')
    def test_wiring_and_light_import(self):
        tree=ast.parse((ROOT/'local_inspection_service/server.py').read_text(encoding='utf-8'));binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_accessory_text_preparation' for t in n.targets));count=0
        for group in binding.keywords:
            for kw in group.value.keywords:self.assertIsInstance(kw.value,ast.Lambda);self.assertEqual(kw.arg,kw.value.body.id);count+=1
        self.assertEqual(count,18)
        for name in NAMES:
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name);body=node.body[1:] if ast.get_docstring(node,clean=False) is not None else node.body;self.assertEqual(len(body),1);self.assertIsInstance(body[0],ast.Return);self.assertEqual(body[0].value.func.attr,name)
            self.assertEqual(ast.get_docstring(node,clean=False),ORIGINAL_DOCSTRINGS.get(name))
        subprocess.run([sys.executable,'-B','-c',"import sys; import local_inspection_service.accessories.text_preparation; assert 'local_inspection_service.server' not in sys.modules"],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()

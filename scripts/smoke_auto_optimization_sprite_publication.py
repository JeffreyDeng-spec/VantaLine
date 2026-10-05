"""Sprite publication parity with synthetic arrays and temporary file adapters."""
import ast
from dataclasses import fields
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_AUTO_SPRITE_PUBLICATION_BASELINE_SOURCE');NAME='auto_optimize_write_sprite_artifact'

def create(bindings):
    if BASELINE:
        node=next(n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name==NAME)
        ns=dict(bindings,Any=Any,Path=Path,cv2=cv2,np=np);exec(compile(ast.Module(body=[node],type_ignores=[]),BASELINE,'exec'),ns);return ns[NAME],ns
    from local_inspection_service.training.auto_optimization_sprite_publication import AutoOptimizationSpritePublication
    from local_inspection_service.training.auto_optimization_sprite_publication_ports import SpritePublication
    service=AutoOptimizationSpritePublication(SpritePublication(**{f.name:lambda name=f.name:bindings[name] for f in fields(SpritePublication)}));return service.auto_optimize_write_sprite_artifact,bindings

class PublicationContract(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name);events=[];image=np.arange(6*8*3,dtype=np.uint8).reshape(6,8,3);mask=np.arange(48,dtype=np.uint8).reshape(6,8)
        def write(path,pixels):events.append(('write',Path(path),pixels.copy()));Path(path).write_bytes(b'raw');return True
        def normalize(path,image,mask,metadata):events.append(('normalize',path,image,mask,metadata));path.write_bytes(b'normalized');return {'path':str(path),'extra':{'value':1}}
        def url(path):events.append(('url',path));return 'public/'+path.name
        b={'safe_record_id':lambda s:s.replace('/','_'),'_image_files':SimpleNamespace(imwrite=write),'write_clean_sprite':normalize,
           'resolve_service_path':lambda p:Path(p),'_business_files':SimpleNamespace(exists=lambda p:Path(p).is_file()),'public_output_url_for_existing':url,'public_path_sanitized':lambda value:events.append(('sanitize',value)) or value}
        fn,b=create(b);return SimpleNamespace(fn=fn,b=b,root=root,events=events,image=image,mask=mask,args={'image_bgr':image,'full_mask':mask,'bbox':[-2,1,99,5],'sample_id':'sample','accessory_id':'a/b','label_name':'Part','artifact_dir':root/'masks','source_image_path':root/'source.png'})

    def test_crop_clamping_copies_alpha_and_metadata(self):
        f=self.fixture();result=f.fn(**f.args);self.assertEqual(result['bbox_xyxy'],[0,1,8,5]);self.assertEqual((result['width'],result['height'],result['status']),(8,4,'available'))
        write,normalize=f.events[:2];np.testing.assert_array_equal(write[2][:,:,:3],f.image[1:5,:]);np.testing.assert_array_equal(write[2][:,:,3],f.mask[1:5,:]);self.assertFalse(np.shares_memory(normalize[2],f.image));self.assertFalse(np.shares_memory(normalize[3],f.mask))
        self.assertEqual(normalize[4],{'task_id':'auto_optimize','source_sample_id':'sample','accessory_id':'a/b','label':'Part','source_image_path':str(f.root/'source.png'),'source_object_bbox_xyxy':[0,1,8,5],'source_object_size_px':[8,4],'source_pose_family':'real_photo_ai_mask','pose_family':'real_photo_ai_mask','source_pose_collection_job_id':'auto_optimize_ai_mask','object_alpha_material_policy':'ai_mask_visible_object','transparent_alpha_policy':'ai_mask_alpha'})
        self.assertEqual([e[0] for e in f.events],['write','normalize','url','url','sanitize']);self.assertTrue(result['path'].endswith('sample_a_b_sprite.png'));self.assertIs(result['normalized'],f.events[-1][1])

    def test_fallback_raw_false_writer_and_label_name_selection(self):
        f=self.fixture();f.args['accessory_id']='';f.b['write_clean_sprite']=lambda *a:None;result=f.fn(**f.args);self.assertEqual(result['path'],result['raw_path']);self.assertEqual(result['status'],'available');self.assertTrue(result['raw_path'].endswith('sample_Part_sprite_raw.png'))
        f=self.fixture();f.b['_image_files'].imwrite=lambda *a:False;f.b['write_clean_sprite']=lambda *a:{};result=f.fn(**f.args);self.assertEqual(result['status'],'failed');self.assertEqual(result['path'],result['raw_path']);self.assertTrue((f.root/'masks/sprites').is_dir())

    def test_reversed_bbox_and_bad_input_order(self):
        f=self.fixture();f.args['bbox']=[100,100,-1,-1];result=f.fn(**f.args);self.assertEqual(result['bbox_xyxy'],[7,5,8,6]);self.assertEqual((result['width'],result['height']),(1,1))
        f=self.fixture();f.args['bbox']=['bad',0,1,1]
        with self.assertRaises(ValueError):f.fn(**f.args)
        self.assertEqual(f.events,[]);self.assertFalse((f.root/'masks').exists())

    def test_normalization_and_url_failure_keep_prior_files(self):
        for phase in ('write_clean_sprite','public_output_url_for_existing','public_path_sanitized'):
            f=self.fixture();error=RuntimeError(phase);f.b[phase]=Mock(side_effect=error)
            with self.assertRaises(RuntimeError) as caught:f.fn(**f.args)
            self.assertIs(caught.exception,error);f.b[phase].assert_called_once();self.assertTrue((f.root/'masks/sprites/sample_a_b_sprite_raw.png').exists());self.assertEqual((f.root/'masks/sprites/sample_a_b_sprite.png').exists(),phase!='write_clean_sprite')

    def test_writer_failure_prevents_normalization_but_keeps_directory(self):
        f=self.fixture();error=OSError('write');f.b['_image_files'].imwrite=Mock(side_effect=error);normalize=Mock();f.b['write_clean_sprite']=normalize
        with self.assertRaises(OSError) as caught:f.fn(**f.args)
        self.assertIs(caught.exception,error);normalize.assert_not_called();self.assertTrue((f.root/'masks/sprites').is_dir())

    def test_chosen_status_uses_later_exists_read_and_url_selected_before_raw(self):
        f=self.fixture();seen=[];f.b['_business_files'].exists=lambda p:seen.append(p) or len(seen)==1
        result=f.fn(**f.args);self.assertEqual(result['status'],'failed');self.assertEqual(len(seen),2);self.assertEqual(seen[0],seen[1]);self.assertTrue(result['path'].endswith('_sprite.png'))
        f=self.fixture();new=Mock(return_value='new')
        def first(path):f.b['public_output_url_for_existing']=new;return 'old'
        f.b['public_output_url_for_existing']=first;result=f.fn(**f.args);self.assertEqual((result['url'],result['raw_url']),('old','new'));new.assert_called_once_with(Path(result['raw_path']))

    @unittest.skipIf(BASELINE,'candidate wiring')
    def test_actual_root_getters_keyword_only_and_light_import(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        ports=server._auto_optimization_sprite_publication.publication
        for f in fields(ports):self.assertIs(getattr(ports,f.name)(),getattr(server,f.name))
        f=self.fixture();mock=Mock(return_value=object())
        with patch.object(server,'_auto_optimization_sprite_publication',SimpleNamespace(auto_optimize_write_sprite_artifact=mock)):self.assertIs(server.auto_optimize_write_sprite_artifact(**f.args),mock.return_value)
        mock.assert_called_once_with(**f.args)
        subprocess.run([sys.executable,'-c',"import sys; import local_inspection_service.training.auto_optimization_sprite_publication; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg'))"],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()

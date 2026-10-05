"""Original-versus-candidate synthetic rendering and publication contracts."""
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
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_AUTO_RENDERING_BASELINE_SOURCE')
NAME='auto_optimize_render_synthetic_sample'

def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name==NAME]
        assert len(nodes)==1
        ns=dict(bindings,Any=Any,Path=Path,np=np)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns)
        return ns[NAME],ns
    from local_inspection_service.training.auto_optimization_rendering import AutoOptimizationRendering
    from local_inspection_service.training.auto_optimization_rendering_ports import SyntheticGeometry,SyntheticPublication
    def ports(cls):return cls(**{f.name:lambda name=f.name:bindings[name] for f in fields(cls)})
    service=AutoOptimizationRendering(ports(SyntheticGeometry),ports(SyntheticPublication))
    return getattr(service,NAME),bindings

class RenderingContract(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name);events=[]
        canvas=np.zeros((6,8,3),np.uint8);mask=np.ones((2,3),np.uint8);rng=Mock();rng.uniform.return_value=12.345
        def emit(name,result):
            def call(*args,**kwargs):events.append(name);return result
            return call
        def text(path,value,*,encoding):events.append('text');path.write_text(value,encoding=encoding)
        bindings={'safe_background_set_id':emit('safe','requested'),
          'render_training_background':emit('background',(canvas,{'background_set_id':'effective'})),
          'auto_optimize_load_sprite':emit('load',(canvas,mask)),
          'auto_optimize_sprite_target_size':emit('size',(20,30)),
          'choose_object_center_inside_background':emit('center',((3,4),{'placement':'inside'})),
          'paste_masked_asset':emit('paste',(canvas,mask)),
          'alpha_bbox':emit('bbox',[1,2,4,5]),'rotated_rect_tuple':emit('rect',((3,4),(20,30),12.345)),
          'AUTO_OPTIMIZE_SYNTHETIC_SIZE_POLICY':'policy',
          '_image_files':SimpleNamespace(imwrite=emit('image',True)),
          'yolo_detection_label_line':emit('label','7 .1 .2 .3 .4'),
          '_business_files':SimpleNamespace(write_text=text),
          'write_training_annotation_preview':emit('preview','annotated'),
          'public_training_output_url':emit('url','public')}
        call,bindings=create(bindings)
        kwargs=dict(sprites=[dict(accessory_id='a',source_sample_id='s',source_record_id='r',path='sprite')],
          class_index={'a':7},accessories_by_id={'a':{'name':'Part'}},output_path=root/'images/a.png',
          label_path=root/'labels/a.txt',annotated_path=root/'preview/a.png',split='train',rng=rng,
          canonical_sizes={'a':{'width':20,'height':30}},background_set_id='choice')
        return SimpleNamespace(root=root,call=call,bindings=bindings,kwargs=kwargs,events=events,canvas=canvas,mask=mask,rng=rng)

    def test_success_values_publication_order_and_rng(self):
        f=self.fixture();r=f.call(**f.kwargs)
        self.assertEqual(f.events,['safe','background','load','size','center','paste','bbox','rect','image','label','text','preview','url'])
        f.rng.uniform.assert_called_once_with(-180.,180.)
        self.assertEqual(f.kwargs['label_path'].read_text(),'7 .1 .2 .3 .4\n')
        self.assertEqual(r['label_count'],1);self.assertEqual(r['source_sample_ids'],['s']);self.assertEqual(r['source_record_ids'],['r'])
        label=r['weak_labels'][0];self.assertEqual(label['angle'],12.35);self.assertEqual(label['render_size_px'],[20,30]);self.assertEqual(label['placement'],'inside')
        self.assertIs(label['canonical_render_size'],f.kwargs['canonical_sizes']['a'])
        self.assertEqual(r['augmentation']['requested_background_set_id'],'requested');self.assertEqual(r['augmentation']['background_set_id'],'effective')
        self.assertEqual(r['url'],'public');self.assertEqual(r['annotated_url'],'annotated')

    def test_skip_unknown_missing_and_non_tuple_or_empty_mask(self):
        for target in ('unknown','missing','non_tuple','empty_mask'):
            with self.subTest(target=target):
                f=self.fixture()
                if target=='unknown':f.kwargs['class_index']={}
                if target=='missing':f.bindings['auto_optimize_load_sprite']=lambda sprite:None
                if target=='non_tuple':f.bindings['paste_masked_asset']=lambda *a,**k:f.canvas
                if target=='empty_mask':f.bindings['alpha_bbox']=lambda *a,**k:[0,0,0,0]
                self.assertIsNone(f.call(**f.kwargs));self.assertFalse(f.kwargs['output_path'].parent.exists());self.assertNotIn('image',f.events)

    def test_falsy_label_line_still_publishes_empty_text_and_preview(self):
        f=self.fixture();f.bindings['yolo_detection_label_line']=lambda *a,**k:''
        r=f.call(**f.kwargs);self.assertEqual(r['label_count'],0);self.assertEqual(len(r['weak_labels']),1)
        self.assertEqual(f.kwargs['label_path'].read_text(),'');self.assertIn('preview',f.events)

    def test_false_image_result_is_originally_ignored(self):
        f=self.fixture();f.bindings['_image_files']=SimpleNamespace(imwrite=lambda *a:False)
        self.assertIsNotNone(f.call(**f.kwargs));self.assertTrue(f.kwargs['label_path'].is_file())

    def test_text_and_preview_failure_retain_prior_publication(self):
        for failing in ('text','preview'):
            with self.subTest(failing=failing):
                f=self.fixture()
                def fail(*a,**k):raise OSError('synthetic publication failure')
                if failing=='text':f.bindings['_business_files']=SimpleNamespace(write_text=fail)
                else:f.bindings['write_training_annotation_preview']=fail
                with self.assertRaises(OSError):f.call(**f.kwargs)
                self.assertIn('image',f.events);self.assertNotIn('url',f.events)
                self.assertEqual(f.kwargs['label_path'].exists(),failing=='preview')

    def test_metadata_overrides_and_source_deduplication(self):
        f=self.fixture();f.kwargs['sprites']*=2
        f.bindings['choose_object_center_inside_background']=lambda *a:((3,4),{'name':'placement override','source_sample_id':'override'})
        r=f.call(**f.kwargs);self.assertEqual(r['source_sample_ids'],['override']);self.assertEqual(r['source_record_ids'],['r']);self.assertEqual(r['weak_labels'][0]['name'],'placement override')
        self.assertEqual(f.rng.uniform.call_count,2)

    def test_callee_selected_before_argument_conversion(self):
        f=self.fixture();old=Mock(return_value='early');late=Mock(return_value='late');f.bindings['yolo_detection_label_line']=old
        class Identity:
            def __str__(self):f.bindings['yolo_detection_label_line']=late;return 'a'
        f.bindings['choose_object_center_inside_background']=lambda *a:((3,4),{'id':Identity()})
        r=f.call(**f.kwargs);old.assert_called_once();late.assert_not_called();self.assertEqual(f.kwargs['label_path'].read_text(),'early\n')

    @unittest.skipIf(BASELINE,'candidate-only application assembly')
    def test_actual_root_getters_forwarder_and_lightweight_import(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service=server._auto_optimization_rendering
        for group in (service.geometry,service.publication):
            for f in fields(group):self.assertIs(getattr(group,f.name)(),getattr(server,f.name))
        f=self.fixture();mock=Mock(return_value=object())
        with patch.object(server,'_auto_optimization_rendering',SimpleNamespace(**{NAME:mock})):
            self.assertIs(getattr(server,NAME)(**f.kwargs),mock.return_value)
        mock.assert_called_once_with(**f.kwargs)
        subprocess.run([sys.executable,'-c',"import sys; import local_inspection_service.training.auto_optimization_rendering; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg'))"],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()

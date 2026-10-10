"""Dataset assembly replay with synthetic images, deterministic order and local files."""
import ast
from contextvars import ContextVar
from dataclasses import fields
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch
import uuid
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_application_test_methods import auto_method
from auto_optimization_test_ports import test_capability, assert_capability_owner
BASELINE=os.environ.get('VANTALINE_AUTO_DATASET_BASELINE_SOURCE')
NAMES=('auto_optimize_bbox_training_entries','build_auto_optimize_dataset')

def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==2
        ns=dict(bindings,Any=Any,Path=Path,time=time,uuid=uuid,cv2=cv2,np=np,json=json,shutil=shutil)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns)
        return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
    from local_inspection_service.training.auto_optimization_dataset import AutoOptimizationDataset
    from local_inspection_service.training.auto_optimization_dataset_ports import DatasetConfiguration,DatasetSources,DatasetPublication,DatasetLayout
    def ports(cls):return cls(**{f.name:test_capability(bindings, f.name) for f in fields(cls)})
    service=AutoOptimizationDataset(ports(DatasetConfiguration),ports(DatasetSources),ports(DatasetPublication),ports(DatasetLayout))
    bindings.update({n:getattr(service,n) for n in NAMES});return service,bindings

class DatasetContract(unittest.TestCase):
    def fixture(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name);events=[];identity=ContextVar('dataset-user',default=None)
        for name in ('real.png','synthetic.png','synthetic.txt','preview.jpg'):(root/name).write_bytes(b'synthetic')
        def resolve(value):return root/str(value or 'missing')
        def write(path,text,*,encoding):events.append(('text',Path(path).name));Path(path).write_text(text,encoding=encoding)
        def copy(source,target,*,local_copy):events.append(('copy',Path(source).name,Path(target).name));return local_copy(source,target)
        def imwrite(path,image,*args):events.append(('image',Path(path).name));Path(path).write_bytes(b'image');return True
        def preview(image,labels,path):events.append(('preview',Path(path).name));path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'preview');return 'public/'+path.name
        def generated(task,state,sample):return [dict(image=str(root/'synthetic.png'),labels=str(root/'synthetic.txt'),annotated_path=str(root/'preview.jpg'),sample_type='synthetic_positive_from_ai_mask_sprite',label_count=1,weak_labels=[]) for _ in range(2)]
        def scoped(config,user):events.append(('scope',user));return config
        bindings={'_request_user':identity,'load_config':lambda:{},'scope_config_for_user':scoped,
          'accessory_lookup_by_id':lambda c:{'a':{'name':'Part A'},'b':{'label':'Part B'}},
          'default_auto_optimize_settings':lambda:{},'auto_optimize_samples_per_real_image':lambda s:3,
          'auto_optimize_positive_derivatives_per_real_image':lambda s:2,'auto_optimize_negative_samples_per_real_image':lambda s:1,
          'auto_optimize_training_requirements':lambda s,real_positive_source_count=0:{'source_count':real_positive_source_count},
          'auto_optimize_generate_synthetic_batch_for_sample':generated,'AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT':2,
          'safe_record_id':lambda s:s.replace('/','_'),'output_write_dir_for_owner':lambda category,owner:root/category/owner,
          'resolve_service_path':resolve,'_image_files':SimpleNamespace(imread=lambda p,flag:np.ones((6,8,3),np.uint8),imwrite=imwrite),
          '_business_files':SimpleNamespace(exists=lambda p:Path(p).is_file(),write_text=write,copy2=copy),
          'safe_background_set_id':lambda s:s,'split_counts':lambda n:{'train':1,'val':1,'test':max(0,n-2)},
          'render_training_background':lambda rng,split,bg:(np.zeros((6,8,3),np.uint8),{'background_set_id':bg}),
          'yolo_detection_label_line':lambda cls,bbox,**kw:f'{cls} .1 .2 .3 .4',
          'write_training_annotation_preview':preview,'public_training_output_url':lambda p:'public/'+p.name,
          'write_dataset_yaml':lambda path,directory,names:path.write_text(json.dumps(names),encoding='utf-8')}
        service,bindings=create(bindings)
        def sample(status,id):return {'label_status':status,'sample_id':id,'record_id':'r'+id,'source_image':{'path':'real.png'},'labels':[] if status=='negative' else [{'accessory_id':'a','bbox_xyxy':[1,2,4,5]}]}
        return SimpleNamespace(root=root,events=events,identity=identity,service=service,bindings=bindings,
          state={'selected_accessory_ids':['b','a'],'owner_user_id':'owner','owner_username':'Owner','task_name':'task'},
          samples=[sample('trainable','p'),sample('trainable_bbox_only','b'),sample('negative','n')])

    def run_dataset(self,f):
        with patch.object(time,'time',return_value=123.9),patch.object(uuid,'uuid4',return_value=SimpleNamespace(hex='abcdef012345')),patch.object(np.random,'default_rng',return_value=SimpleNamespace(shuffle=lambda order:None)):
            return f.service.build_auto_optimize_dataset('t/x',f.state,f.samples)

    def test_bbox_order_dedupe_conversion_and_original_overflow(self):
        f=self.fixture();same={'accessory_id':' a ','bbox_xyxy':[1.1,2.5,4.6,5]};other={'accessory_id':'b','bbox_xyxy':[0,0,2,2],'reason':'manual'}
        rows=f.service.auto_optimize_bbox_training_entries({'label_status':'trainable','bbox_labels':[None,same,{'accessory_id':'a','bbox_xyxy':['bad',0,1,2]}],'labels':[same], 'manual_review':{'previous_label_failures':[other]}})
        self.assertEqual([r['accessory_id'] for r in rows],['a','b']);self.assertEqual(rows[0]['bbox_xyxy'],[1,2,5,5]);self.assertEqual(rows[1]['source_reason'],'manual')
        with self.assertRaises(OverflowError):f.service.auto_optimize_bbox_training_entries({'labels':[{'accessory_id':'a','bbox_xyxy':[float('inf'),0,1,2]}]})

    def test_four_source_kinds_split_weight_and_manifest(self):
        f=self.fixture();result=self.run_dataset(f);manifest=json.loads(Path(result['manifest_path']).read_text(encoding='utf-8'))
        self.assertEqual(result['id'],'autoopt_t_x_123_abcdef');self.assertEqual(manifest['class_names'],['Part B','Part A']);self.assertEqual(manifest['class_accessory_map'],{'b':0,'a':1})
        for key,value in {'sample_count':9,'positive_sample_count':6,'negative_sample_count':3,'synthetic_sample_count':2,'real_bbox_sample_count':4,'real_positive_source_count':2,'real_negative_source_count':1,'generated_negative_sample_count':2}.items():self.assertEqual(manifest[key],value,key)
        rows=manifest['samples'];self.assertEqual([r['split'] for r in rows],['train','val','train','train','train','train','test','test','test'])
        self.assertEqual([r['weight_index'] for r in rows if 'weight_index' in r],[1,2,1,2]);self.assertEqual(manifest['training_requirements'],{'source_count':2})
        self.assertTrue(Path(result['dataset_yaml']).is_file());self.assertEqual(f.events[-1],('text','manifest.json'));self.assertEqual(manifest['owner_user_id'],'owner')

    def test_no_selection_does_not_create_output_or_read_config(self):
        f=self.fixture();f.state['selected_accessory_ids']=[];f.samples=[];f.bindings['load_config']=Mock(side_effect=AssertionError('unexpected'))
        self.assertIsNone(self.run_dataset(f));f.bindings['load_config'].assert_not_called();self.assertFalse((f.root/'training_datasets').exists())

    def test_negative_only_creates_directories_then_records_error(self):
        f=self.fixture();f.samples=[f.samples[-1]];self.assertIsNone(self.run_dataset(f));self.assertEqual(f.state['last_dataset_error'],'no_trainable_ai_mask_sprites_or_bbox_labels')
        dataset=f.root/'training_datasets/owner/autoopt_t_x_123_abcdef';self.assertTrue((dataset/'images/train').is_dir());self.assertFalse((dataset/'manifest.json').exists())

    def test_no_materialized_records_does_not_publish_manifest(self):
        f=self.fixture();f.samples=[f.samples[1]];f.bindings['auto_optimize_negative_samples_per_real_image']=lambda s:0;f.bindings['_image_files'].imread=lambda *a:None
        self.assertIsNone(self.run_dataset(f));self.assertNotIn('last_dataset_error',f.state);self.assertFalse(list((f.root/'training_datasets').rglob('manifest.json')))

    def test_synthetic_annotation_fallback_and_missing_source(self):
        f=self.fixture();f.samples=[f.samples[0]];f.samples[0]['labels']=[];f.bindings['auto_optimize_negative_samples_per_real_image']=lambda s:0
        original=f.bindings['auto_optimize_generate_synthetic_batch_for_sample']
        def generate(*args):
            rows=original(*args);rows[0]['annotated_path']='absent';rows[1]['image']='absent';return rows
        f.bindings['auto_optimize_generate_synthetic_batch_for_sample']=generate
        result=self.run_dataset(f);self.assertEqual(result['sample_count'],1);self.assertTrue(any(e[0]=='preview' for e in f.events))

    def test_partial_copy_and_final_manifest_failure_keep_files(self):
        for phase in ('copy','manifest'):
            with self.subTest(phase=phase):
                f=self.fixture();files=f.bindings['_business_files'];copy=files.copy2;write=files.write_text;calls=[]
                def copy_fail(*a,**kw):
                    calls.append(1)
                    if len(calls)==2:raise OSError('second copy')
                    return copy(*a,**kw)
                def write_fail(path,text,**kw):
                    if path.name=='manifest.json':raise OSError('manifest')
                    return write(path,text,**kw)
                if phase=='copy':files.copy2=copy_fail
                else:files.write_text=write_fail
                with self.assertRaises(OSError):self.run_dataset(f)
                self.assertTrue(list((f.root/'training_datasets').rglob('*.png')));self.assertFalse(list((f.root/'training_datasets').rglob('manifest.json')))
                self.assertEqual(bool(list((f.root/'training_datasets').rglob('dataset.yaml'))),phase=='manifest')

    def test_context_scope_selection_before_config_load_and_owner_fallback(self):
        f=self.fixture();f.identity.set({'id':'request'});f.state.pop('owner_user_id');late=Mock(side_effect=AssertionError('late callback'))
        def load():f.bindings['scope_config_for_user']=late;return {}
        f.bindings['load_config']=load;result=self.run_dataset(f);late.assert_not_called();self.assertIn('/request/',result['dataset_dir'].replace('\\','/'));self.assertEqual(f.events[0],('scope',{'id':'request'}))
        manifest=json.loads(Path(result['manifest_path']).read_text(encoding='utf-8'));self.assertEqual(manifest['owner_user_id'],'')

    @unittest.skipIf(BASELINE,'candidate-only root composition')
    def test_actual_root_getters_and_forwarders(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service=server._auto_optimization_dataset
        for group in (service.configuration,service.sources,service.publication,service.layout):
            for f in fields(group):assert_capability_owner(self, group, f.name, server)
        for name,args in zip(NAMES,(({},),('t',{},[]))):
            mock=Mock(return_value=object())
            with auto_method(self,server._auto_optimization_dataset,name,mock):self.assertIs(getattr(server,name)(*args),mock.return_value)
            mock.assert_called_once_with(*args)
        subprocess.run([sys.executable,"-c","import sys; import local_inspection_service.training.auto_optimization_dataset; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg'))"],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()

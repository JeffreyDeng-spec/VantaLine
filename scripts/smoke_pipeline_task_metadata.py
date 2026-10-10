"""Pipeline metadata parity using synthetic task snapshots and fixed clocks."""
import ast
from dataclasses import fields
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from canonical_application_source_contract import read_checked_application_source
BASELINE=os.environ.get('VANTALINE_PIPELINE_TASK_METADATA_BASELINE_SOURCE')
NAMES=('pipeline_task_model_id','normalize_pipeline_detection_method','pipeline_method_uses_training','ensure_pipeline_task_accessory_objects','normalize_pipeline_accessory_counts','normalize_pipeline_task_auto_advance_defaults')

def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==6
        ns=dict(bindings,Any=Any,re=re,time=time);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
    from local_inspection_service.pipeline.task_metadata import PipelineTaskMetadata
    from local_inspection_service.pipeline.task_metadata_ports import MetadataPolicy,MetadataSnapshots
    def ports(cls):return cls(**{f.name:lambda name=f.name:bindings[name] for f in fields(cls)})
    service=PipelineTaskMetadata(ports(MetadataPolicy),ports(MetadataSnapshots));bindings.update({n:getattr(service,n) for n in NAMES});return service,bindings

class MetadataContract(unittest.TestCase):
    def fixture(self):
        b={'PIPELINE_DETECTION_METHODS':{'yolo','yolo_ocr','ai','label_text_compare'},'PIPELINE_TRAINING_METHODS':{'yolo','yolo_ocr'},
           'accessory_lookup_by_id':lambda c:{i['id']:i for i in c.get('accessories',[])},'pipeline_task_label_snapshot':lambda t:t.get('labels',{}),'LEGACY_OWNER_ID':'legacy','record_owner_username':lambda t:'legacy-name','accessory_id_aliases':lambda i:i.get('aliases',[i['id']])}
        s,b=create(b);return SimpleNamespace(s=s,b=b)

    def test_method_alias_fallback_and_model_id(self):
        f=self.fixture()
        for raw,expected in [(None,'yolo_ocr'),(' UNKNOWN ','yolo_ocr'),(' Gemini ','ai'),('AI_INSPECT','ai'),('ai_detection','ai'),('label_text_compare','label_text_compare'),(' yolo ','yolo')]:self.assertEqual(f.s.normalize_pipeline_detection_method(raw),expected)
        self.assertTrue(f.s.pipeline_method_uses_training('unknown'));self.assertFalse(f.s.pipeline_method_uses_training('gemini'))
        self.assertEqual(f.s.pipeline_task_model_id({'ai_model_id':' custom '}),'custom');self.assertEqual(f.s.pipeline_task_model_id({}),'');self.assertEqual(f.s.pipeline_task_model_id({'model_run_id':'trained_a / 中','detection_method':'ai'}),'trained_a___yolo');self.assertEqual(f.s.pipeline_task_model_id({'training_task_id':' x.y-z '}),'trained_x.y-z__yolo_ocr')

    def test_counts_alias_order_bounds_and_invalid(self):
        f=self.fixture();config={'accessories':[{'id':'a','aliases':['old','a']}]}
        self.assertEqual(f.s.normalize_pipeline_accessory_counts(config,['a','missing'],{'old':3,'a':9,'missing':'100'}),{'a':3,'missing':99})
        for raw,expected in [(None,1),({},1),(0,1),(-5,1),('bad',1),([],1),(True,1),(3.9,3)]:self.assertEqual(f.s.normalize_pipeline_accessory_counts(config,['a'],{'old':raw}),{'a':expected})
        with self.assertRaises(OverflowError):f.s.normalize_pipeline_accessory_counts(config,['a'],{'a':float('inf')})
        self.assertEqual(f.s.normalize_pipeline_accessory_counts(config,['a'],['invalid']),{'a':1})

    def test_snapshot_rebuild_identity_duplicates_defaults(self):
        f=self.fixture();existing={'id':'existing','name':'keep'};config={'accessories':[existing]};task={'id':'task','accessory_ids':['existing','a','a','b',' '],'accessory_names':['Existing','A raw','B raw'],'labels':{'a':'A label'},'created_at':4}
        with patch.object(time,'time',return_value=20):self.assertTrue(f.s.ensure_pipeline_task_accessory_objects(config,[task,{'accessory_ids':['a']}]))
        self.assertIs(config['accessories'][0],existing);a,b=config['accessories'][1:];self.assertEqual((a['name'],b['name']),('A label','B raw'));self.assertEqual(a['owner_user_id'],'legacy');self.assertEqual(a['owner_username'],'legacy-name');self.assertEqual((a['created_at'],a['updated_at']),(4,20));self.assertEqual(a['source'],'task_snapshot');self.assertTrue(a['task_snapshot_only']);self.assertEqual(a['status'],'archived');self.assertEqual(a['archived_from_task_id'],'task');self.assertEqual(a['detection_route'],'ai');self.assertIsNot(a['source_files'],b['source_files'])
        with patch.object(time,'time',return_value=21):self.assertFalse(f.s.ensure_pipeline_task_accessory_objects(config,[task]))

    def test_snapshot_clock_and_owner_failure_partial_effects(self):
        f=self.fixture();config={};f.b['accessory_lookup_by_id']=Mock(return_value={})
        with patch.object(time,'time',side_effect=RuntimeError('clock')):
            with self.assertRaisesRegex(RuntimeError,'clock'):f.s.ensure_pipeline_task_accessory_objects(config,[])
        self.assertEqual(config,{'accessories':[]});f.b['accessory_lookup_by_id'].assert_called_once_with(config)
        f=self.fixture();config={};f.b['record_owner_username']=Mock(side_effect=['first',RuntimeError('owner')])
        with patch.object(time,'time',return_value=20):
            with self.assertRaisesRegex(RuntimeError,'owner'):f.s.ensure_pipeline_task_accessory_objects(config,[{'accessory_ids':['a','b']}])
        self.assertEqual([i['id'] for i in config['accessories']],['a'])

    def test_auto_advance_exact_false_identity_and_partial_clock_error(self):
        f=self.fixture();tasks=[{'detection_method':'ai','auto_advance':False},{'params':{'route':'gemini'},'auto_advance':0},{'detection_method':'yolo','auto_advance':True}]
        with patch.object(time,'time',return_value=9):self.assertTrue(f.s.normalize_pipeline_task_auto_advance_defaults(tasks))
        self.assertNotIn('updated_at',tasks[0]);self.assertIs(tasks[1]['auto_advance'],False);self.assertEqual(tasks[1]['updated_at'],9);self.assertTrue(tasks[2]['auto_advance'])
        task={'detection_method':'ai','auto_advance':True}
        with patch.object(time,'time',side_effect=RuntimeError('clock')):
            with self.assertRaisesRegex(RuntimeError,'clock'):f.s.normalize_pipeline_task_auto_advance_defaults([task])
        self.assertIs(task['auto_advance'],False);self.assertNotIn('updated_at',task)
        with self.assertRaises(AttributeError):f.s.normalize_pipeline_task_auto_advance_defaults([{'params':['bad']}])

    def test_late_policy_and_snapshot_owner_binding(self):
        f=self.fixture()
        def normalize(method):f.b['PIPELINE_TRAINING_METHODS']={'new'};return 'new'
        f.b['normalize_pipeline_detection_method']=normalize;self.assertTrue(f.s.pipeline_method_uses_training('ai'))
        f=self.fixture()
        def labels(task):f.b['LEGACY_OWNER_ID']='updated';return {}
        f.b['pipeline_task_label_snapshot']=labels
        config={}
        with patch.object(time,'time',return_value=5):f.s.ensure_pipeline_task_accessory_objects(config,[{'accessory_ids':['a']}])
        self.assertEqual(config['accessories'][0]['owner_user_id'],'updated')

    @unittest.skipIf(bool(BASELINE),'candidate wiring only')
    def test_wiring_and_import(self):
        from application_integration_source_contract import restore_plc_domain_root
        tree=ast.parse(restore_plc_domain_root(read_checked_application_source(ROOT / 'local_inspection_service/server.py', encoding='utf-8')));binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_pipeline_task_metadata' for t in n.targets));count=0
        for group in binding.keywords:
            for kw in group.value.keywords:self.assertIsInstance(kw.value,ast.Lambda);self.assertEqual(kw.arg,kw.value.body.id);count+=1
        self.assertEqual(count,8)
        for name in NAMES:
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name);self.assertEqual(len(node.body),1);self.assertIsInstance(node.body[0],ast.Return);self.assertEqual(node.body[0].value.func.attr,name)
        subprocess.run([sys.executable,'-B','-c',"import sys; import local_inspection_service.pipeline.task_metadata; assert 'local_inspection_service.server' not in sys.modules"],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()

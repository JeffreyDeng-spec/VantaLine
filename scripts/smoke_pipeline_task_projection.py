"""Pipeline response projection parity with synthetic records and explicit callbacks."""
import ast
from dataclasses import fields
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_PIPELINE_TASK_PROJECTION_BASELINE_SOURCE')

def create(bindings):
    if BASELINE:
        node=next(n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name=='pipeline_task_public');ns=dict(bindings,Any=Any);exec(compile(ast.Module(body=[node],type_ignores=[]),BASELINE,'exec'),ns);return ns['pipeline_task_public'],ns
    from local_inspection_service.pipeline.task_projection import PipelineTaskProjection
    from local_inspection_service.pipeline.task_projection_ports import ProjectionMetadata,ProjectionResources
    def ports(cls):return cls(**{f.name:lambda name=f.name:bindings[name] for f in fields(cls)})
    service=PipelineTaskProjection(ports(ProjectionMetadata),ports(ProjectionResources));return service.pipeline_task_public,bindings

class ProjectionContract(unittest.TestCase):
    def fixture(self):
        events=[];task={'id':'task','model_profiles':{'private':True},'params':{'train_mode':'yolo'},'accessory_ids':['alias','a','missing',' '],'accessory_counts':{'a':2}};config={};item={'id':'a','material_type':'text'};link={'task_id':'linked','ai_model_id':'ai:linked'}
        def trace(name,result):
            def call(*a,**kw):events.append((name,a,kw));return result(*a,**kw) if callable(result) else result
            return call
        b={'accessory_lookup_by_id':trace('lookup',{'a':item}),'enrich_record_audit_fields':trace('audit',lambda t:dict(t,audit=True)),
           'normalize_pipeline_detection_method':trace('method',lambda s:s),'pipeline_method_uses_training':trace('training',lambda s:s=='yolo'),
           'resolve_accessory_id':trace('resolve',lambda c,i:('a',item) if i in ('alias','a') else None),
           'normalize_pipeline_accessory_counts':trace('counts',lambda c,ids,raw:{i:(raw or {}).get(i,1) for i in ids}),
           'pipeline_task_accessory_snapshot':trace('snapshot',lambda c,t,ids:({'a':'Label A'},['Name '+i for i in ids])),
           'accessory_material_type':trace('material',lambda item:item.get('material_type','object')),
           'pipeline_task_dataset_status':trace('dataset','available'),'pipeline_task_model_status':trace('model','unavailable'),
           'pipeline_task_auto_optimize_link':trace('link',link),'public_path_sanitized':trace('sanitize',lambda value:dict(value,sanitized=True))}
        fn,b=create(b);return SimpleNamespace(fn=fn,b=b,events=events,task=task,config=config,item=item,link=link)

    def test_complete_projection_alias_unknown_order_and_private_snapshot(self):
        f=self.fixture();result=f.fn(f.task,f.config)
        self.assertEqual(result['accessory_ids'],['a','missing']);self.assertEqual(result['accessory_labels'],{'a':'Label A','missing':'Name missing'});self.assertEqual(result['accessories'],[{'id':'a','name':'Name a','material_type':'text','count':2},{'id':'missing','name':'Name missing','material_type':'object','count':1}]);self.assertTrue(result['dataset_exists']);self.assertFalse(result['model_exists']);self.assertTrue(result['uses_training_flow']);self.assertTrue(result['sanitized']);self.assertNotIn('model_profiles',result);self.assertIn('model_profiles',f.task);self.assertEqual(f.task['accessory_ids'],['alias','a','missing',' '])
        self.assertIs(result['auto_optimize_link'],f.link);self.assertEqual((result['auto_optimize_task_id'],result['ai_baseline_task_id'],result['ai_baseline_model_id']),('linked','linked','ai:linked'));self.assertIs(next(e for e in f.events if e[0]=='snapshot')[1][1],f.task)

    def test_preloaded_identity_and_unsanitized_result(self):
        f=self.fixture();ids=set();specs=[];states=[];index={};f.b['public_path_sanitized']=Mock(side_effect=AssertionError('unexpected'))
        result=f.fn(f.task,f.config,ai_task_ids=ids,trained_model_specs=specs,auto_optimize_states=states,auto_optimize_states_by_id=index,sanitize=False)
        model=next(e for e in f.events if e[0]=='model');link=next(e for e in f.events if e[0]=='link');self.assertIs(model[2]['ai_task_ids'],ids);self.assertIs(model[2]['trained_model_specs'],specs);self.assertIs(link[2]['auto_optimize_states'],states);self.assertIs(link[2]['auto_optimize_states_by_id'],index);self.assertIs(model[1][0],result);self.assertIs(link[1][0],result);f.b['public_path_sanitized'].assert_not_called()

    def test_detection_fallbacks_resource_flags_and_absent_link_preserves_prior_fields(self):
        for task,expected in [({'detection_method':'explicit','params':{'train_mode':'yolo'}},'explicit'),({'params':{'route':'route'}},'route'),({'params':[]},'')]:
            f=self.fixture();f.task.update(task);f.b['pipeline_task_dataset_status']=lambda s:'missing';f.b['pipeline_task_model_status']=lambda *a,**kw:'available';f.b['pipeline_task_auto_optimize_link']=lambda *a,**kw:None;old={'old':True};f.task['auto_optimize_link']=old
            result=f.fn(f.task,f.config);self.assertEqual(result['detection_method'],expected);self.assertFalse(result['dataset_exists']);self.assertTrue(result['model_exists']);self.assertIs(result['auto_optimize_link'],old)

    def test_projection_failure_keeps_prior_callback_effects_no_replay(self):
        for phase in ('pipeline_task_accessory_snapshot','pipeline_task_model_status','public_path_sanitized'):
            f=self.fixture();error=RuntimeError(phase);f.b[phase]=Mock(side_effect=error)
            with self.assertRaises(RuntimeError) as caught:f.fn(f.task,f.config)
            self.assertIs(caught.exception,error);f.b[phase].assert_called_once();self.assertEqual(sum(e[0]=='audit' for e in f.events),1);self.assertIn('model_profiles',f.task)

    def test_snapshot_name_default_eagerly_indexes_even_existing_label(self):
        f=self.fixture();f.b['pipeline_task_accessory_snapshot']=lambda *a:({'a':'Label A','missing':'Missing'},[])
        with self.assertRaises(IndexError):f.fn(f.task,f.config)
        self.assertFalse(any(e[0]=='dataset' for e in f.events))

    def test_metadata_callee_rebindings_remain_per_use(self):
        f=self.fixture();late=Mock(return_value='new');old=f.b['pipeline_task_dataset_status']
        def dataset(value):f.b['pipeline_task_model_status']=late;return old(value)
        f.b['pipeline_task_dataset_status']=dataset;result=f.fn(f.task,f.config);self.assertEqual(result['model_status'],'new');late.assert_called_once()

    @unittest.skipIf(BASELINE,'candidate wiring')
    def test_root_getters_forwarding_and_light_import(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service=server._task_projection
        for group in (service.metadata,service.resources):
            from pipeline_query_test_ports import QUERY_METHODS, assert_native_query_relay
            for f in fields(group):
                if assert_native_query_relay(self,server,group,f.name):continue
                actual=getattr(group,f.name)(); expected=getattr(server._pipeline_queries if f.name in QUERY_METHODS else server,f.name)
                if f.name in QUERY_METHODS:
                    self.assertIs(actual.__self__,expected.__self__);self.assertIs(actual.__func__,expected.__func__)
                else:self.assertIs(actual,expected)
        task={};config={};kw={'ai_task_ids':set(),'trained_model_specs':[],'auto_optimize_states':[],'auto_optimize_states_by_id':{},'sanitize':False}
        with patch.object(type(service),'pipeline_task_public',autospec=True) as mock:
            mock.return_value=object()
            self.assertIs(server.pipeline_task_public(task,config,**kw),mock.return_value)
            mock.assert_called_once_with(service,task,config,**kw)
            self.assertIs(mock.call_args.args[0],service)
        subprocess.run([sys.executable,'-c',"import sys; import local_inspection_service.pipeline.task_projection; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg'))"],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()

"""Real pipeline stage graph and shared runtime, with synthetic external effects."""
import ast
import copy
from dataclasses import fields
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
from local_inspection_service.pipeline import stage_composition as module
from smoke_pipeline_query_composition import build as query_graph
GROUPS={
 'activation_policy':module.ActivationPolicyInputs,'activation_storage':module.ActivationStorageInputs,
 'pipeline_ai_identity':module.PipelineAiIdentityInputs,'pipeline_ai_accessories':module.PipelineAiAccessoriesInputs,
 'pipeline_ai_access':module.PipelineAiAccessInputs,'pipeline_ai_projection':module.PipelineAiProjectionInputs,
 'training_job_lookup':module.TrainingJobLookupInputs,'training_status_effects':module.TrainingStatusEffectsInputs,
 'stage_advance_policy':module.StageAdvancePolicyInputs,'stage_advance_assets':module.StageAdvanceAssetsInputs,
 'stage_advance_jobs':module.StageAdvanceJobsInputs,'stage_advance_runtime':module.StageAdvanceRuntimeInputs,
 'reconciliation_registry':module.ReconciliationRegistryInputs,'reconciliation_calls':module.ReconciliationCallsInputs,
}
class Cancelled(Exception):pass

def compose(queries,runtime,bindings):
    return module.PipelineStages(queries=queries,runtime=runtime,**{
        name:cls(**{f.name:lambda key=f.name:bindings[key] for f in fields(cls)}) for name,cls in GROUPS.items()})

def build(root,account):
    q=query_graph(root,account);events=[];records={};jobs={}
    def forbidden(*args,**kwargs):raise AssertionError('unplanned paid/process operation')
    def save(row,**kwargs):events.append(('save',row['id']));records[row['id']]=copy.deepcopy(row)
    def public(row,config):events.append(('public',row['id']));return dict(row,model_id='ai:'+row['id'])
    def lookup(config):return {row['id']:row for row in config['accessories']}
    def finder():
        events.append(('finder',));return lambda path:jobs.get(path.name)
    b={
      'HTTPException':HTTPException,'accessory_lookup_by_id':lookup,'clean_ai_detection_task_name':lambda value,default:value or default,
      'sanitize_ai_detection_task_id':lambda value:str(value or '').strip(),'current_owner_fields':lambda:{'owner_user_id':account},
      'find_ai_detection_task':lambda key:records.get(key),'save_ai_detection_task':save,'serialize_ai_detection_task':public,
      'safe_record_id':lambda value:value,'ai_detection_task_model_id':lambda key:'ai:'+key,
      'accessory_material_type':lambda row:'text' if row.get('training_role')=='detect_then_ocr' else 'object',
      'source':'dashboard','record_visible_to_user':lambda row,user,target:row.get('owner_user_id')==user['id'],
      'load_ai_detection_tasks':lambda:list(records.values()),'now':lambda:100,
      'load':lambda path:jobs.get(path.name),'path':lambda key:Path(key),'public':lambda row:dict(row),
      'orchestration':lambda task:task.setdefault('agent_mcp',{}),'set_stage':lambda *args:events.append(('set_stage',args[1])),
      'recommend':forbidden,'pause':forbidden,'training_quality':lambda task:True,'link_model':lambda task:events.append(('link',task['id'])),
      'http_error':HTTPException,'cancelled_error':Cancelled,'load_config':lambda:q.config,'save_config':lambda config:events.append(('save_config',)),
      'prepare':lambda task,config:True,'materialize':lambda task,config:False,'normalize':lambda config,ids:False,
      'request_type':lambda **kwargs:kwargs,'sample_generation':lambda request:events.append(('samples',request)) or {'job_id':'generated'},
      'training':lambda request:events.append(('training',request)) or {'job_id':'trained'},'task_name':lambda task:task.get('name','task'),
      'log_samples':lambda task,job:events.append(('log_samples',)),'log_training':lambda task,job:events.append(('log_training',)),
      'persist_progress':lambda key,**kwargs:events.append(('progress',key,kwargs['progress'])),
      'monotonic':lambda:1,'clock':lambda:100,'print':lambda *args,**kwargs:None,
      'timeout':10,'load_agent_config':lambda:{'enabled':True},'supported':lambda config:True,'training_finder':finder,
    }
    s=compose(q.owner,q.persistence.runtime,b)
    return SimpleNamespace(owner=s,q=q,b=b,events=events,records=records,jobs=jobs,runtime=q.persistence.runtime,account=account)

class StageCompositionContracts(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix='pipeline-stages-');self.addCleanup(self.directory.cleanup)
        self.a=build(Path(self.directory.name)/'a','a');self.b=build(Path(self.directory.name)/'b','b')
    def task(self,**kwargs):return dict(id='same',name='task',owner_user_id='a',accessory_ids=['alias'],params={},stage='draft',status='pending',detection_method='ai',**kwargs)
    def test_inert_constructor_and_forwarder_is_callable(self):
        def poison(*args,**kwargs):raise AssertionError('eager supplier')
        b={f.name:poison for cls in GROUPS.values() for f in fields(cls)}
        runtime=object();queries=SimpleNamespace(persistence=SimpleNamespace(runtime=runtime))
        owner=compose(queries,runtime,b)
        self.assertTrue(callable(owner.advance_pipeline_task));self.assertIsInstance(owner.advance,module.PipelineStageAdvancer)
        self.assertIs(owner.reconciliation.registry.lock.__class__,type(lambda:None))
    def test_mismatched_actual_runtime_rejected_before_components_or_suppliers(self):
        def poison(*args,**kwargs):raise AssertionError('eager supplier')
        bindings={f.name:poison for cls in GROUPS.values() for f in fields(cls)}
        published=self.a.owner
        self.a.runtime.advance_inflight.add('same')
        with patch.object(module,'PipelineAiActivation',side_effect=AssertionError('component constructed')):
            with self.assertRaisesRegex(ValueError,'query persistence runtime'):
                published=compose(self.a.q.owner,self.b.runtime,bindings)
        self.assertIs(published,self.a.owner)
        self.assertIn('same',self.a.runtime.advance_inflight)

    def test_real_query_aliases_and_activation_save_then_projection(self):
        f=self.a;task=self.task()
        f.owner.advance_pipeline_task(task)
        self.assertEqual((task['stage'],task['status'],task['progress']),('library','completed',100))
        row=f.records[task['ai_task_id']]
        self.assertEqual(row['selected_accessory_ids'],['a']);self.assertEqual(row['owner_user_id'],'a')
        self.assertEqual(row['accessory_labels'],{'a':'a'});self.assertEqual([e[0] for e in f.events],['save','public'])
        self.assertEqual(self.b.records,{})
    def test_projection_failure_preserves_saved_evidence_without_advancing_task(self):
        f=self.a;task=self.task();before=copy.deepcopy(task)
        def failed(*args):raise RuntimeError('projection failed')
        f.b['serialize_ai_detection_task']=failed
        with self.assertRaisesRegex(RuntimeError,'projection failed'):f.owner.advance_pipeline_task(task)
        self.assertEqual(task,before);self.assertEqual(len(f.records),1);self.assertEqual(len(f.events),1)
    def test_account_sync_retains_same_ids_and_paused_records_without_duplicates(self):
        for f in (self.a,self.b):
            shared=['observer'];row={'id':'same','owner_user_id':f.account,'selected_accessory_ids':['alias'],'shared_with_user_ids':shared}
            rows=[];f.records['same']=row
            self.assertTrue(f.owner.sync_pipeline_ai_detection_tasks(rows,f.q.config,{'id':f.account}))
            self.assertEqual(rows[0]['owner_user_id'],f.account);self.assertIs(rows[0]['shared_with_user_ids'],shared)
            rows[0].update(status='stopped',pause_requested=True)
            f.owner.sync_pipeline_ai_detection_tasks(rows,f.q.config,{'id':f.account})
            self.assertEqual(len(rows),1);self.assertFalse(rows[0]['auto_advance']);self.assertEqual(rows[0]['status'],'stopped')
            denied=[];f.owner.sync_pipeline_ai_detection_tasks(denied,f.q.config,{'id':'denied'});self.assertEqual(denied,[])
    def test_shared_runtime_keeps_live_task_and_reaps_only_other_graph(self):
        a,b=self.a,self.b
        self.assertIs(a.owner.reconciliation.registry.lock(),a.q.persistence.runtime.advance_registry_lock)
        self.assertIs(a.owner.reconciliation.registry.inflight(),a.q.persistence.runtime.advance_inflight)
        a.runtime.advance_inflight.add('same')
        ta={'id':'same','advancing':True,'advance_started_at':1};tb=dict(ta)
        self.assertFalse(a.owner.reap_pipeline_advance_zombie(ta));self.assertTrue(b.owner.reap_pipeline_advance_zombie(tb))
        self.assertTrue(ta['advancing']);self.assertNotIn('advancing',tb)
        a.runtime.advance_inflight.clear();self.assertTrue(a.owner.reap_pipeline_advance_zombie(ta))
    def test_one_training_finder_syncs_multiple_tasks_and_llm_signature_dedupes(self):
        f=self.a;f.jobs.update(j1={'status':'completed','progress':100},j2={'status':'completed','progress':100})
        tasks=[{'id':str(i),'stage':'samples','status':'running','samples_task_id':'j'+str(i),'auto_advance':True,'detection_method':'yolo'} for i in (1,2)]
        changed,auto,advance=f.owner.sync_and_auto_advance_pipeline(tasks)
        self.assertTrue(changed);self.assertEqual(auto,['1','2']);self.assertEqual(advance,[])
        self.assertEqual(f.events,[('finder',)])
        for task in tasks:task['agent_mcp']['last_auto_signature']=f.owner.pipeline_task_decision_signature(task)
        self.assertEqual(f.owner.sync_and_auto_advance_pipeline(tasks),(False,[],[]))
        f.b['supported']=lambda config:False
        self.assertEqual(f.owner.sync_and_auto_advance_pipeline(tasks),(False,[],['1','2']))
    def test_cached_recommendation_real_consumer_avoids_paid_call_and_keeps_shallow_values(self):
        f=self.a;task=self.task();task['detection_method']='yolo';nested=['retain']
        task['recommended_params']={'stage':'samples','signature':'old','params':{'sample_count':3,'nested':nested},'reason':'cache','source':'saved'}
        f.owner.advance_pipeline_task(task)
        self.assertEqual(task['stage'],'samples');self.assertNotIn('recommended_params',task)
        self.assertIs(task['params']['nested'],nested);self.assertEqual(task['agent_reason'],'cache')
        self.assertEqual([e[0] for e in f.events],['progress','progress','progress','progress','samples','log_samples'])
    def test_cancel_between_steps_preserves_progress_without_creating_job(self):
        f=self.a;task=self.task();task.update(detection_method='yolo',params={'sample_count':3});cancel=threading.Event()
        def prepare(*args):cancel.set();return True
        f.b['prepare']=prepare
        with self.assertRaises(Cancelled):f.owner.advance_pipeline_task(task,cancel)
        self.assertEqual(f.events,[('progress','same',10)]);self.assertNotIn('samples_task_id',task)
    def test_recommendation_receiver_selected_before_argument_effect_and_late_next_item(self):
        f=self.a;old=f.owner.recommendations;late=self.b.owner.recommendations
        getter=old.links.signature
        f.owner.pipeline_recommendation_signature=lambda task,stage:'selected'
        self.assertEqual(getter()({},'samples'),'selected')
        late.pipeline_recommendation_signature=lambda task,stage:'late'
        class Changed(dict):
            def get(self,key,default=None):
                if key=='accessory_ids':f.owner.recommendations=late
                return super().get(key,default)
        task=Changed(accessory_ids=['a'],params={})
        f.owner.pipeline_recommendation_signature=module.PipelineStages.pipeline_recommendation_signature.__get__(f.owner)
        self.assertEqual(f.owner.pipeline_recommendation_signature(task,'samples'),'samples|a|0')
        self.assertEqual(f.owner.pipeline_recommendation_signature({},'samples'),'late')
    def test_source_inverse_preserves_all_business_and_root_functions(self):
        from application_integration_source_contract import ROOT,PIPELINE_STAGES,restore_delta,restore_plc_domain_root
        source=(ROOT/'local_inspection_service/server.py').read_text()
        restored=restore_delta(source,PIPELINE_STAGES)
        self.assertNotIn('_pipeline_stages = PipelineStages',restored)
        restore_plc_domain_root(source)
        with self.assertRaises(AssertionError):restore_plc_domain_root(source.replace('runtime=_pipeline_runtime,','runtime=None,',1))
if __name__=='__main__':unittest.main()

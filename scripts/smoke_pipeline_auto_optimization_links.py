"""Pipeline auto-training links with explicit state/projection/matching substitutes."""
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
BASELINE=os.environ.get('VANTALINE_PIPELINE_AUTO_LINKS_BASELINE_SOURCE')
NAMES=('fast_completed_auto_optimize_model_id','public_auto_optimize_link_for_task_id','auto_optimize_states_by_task_id','pipeline_task_auto_optimize_link')

def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==4
        ns=dict(bindings,Any=Any);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(**{n:ns[n] for n in NAMES}),ns
    from local_inspection_service.pipeline.auto_optimization_links import PipelineAutoOptimizationLinks
    from local_inspection_service.pipeline.auto_optimization_links_ports import LinkState,LinkProjection,LinkMatching
    def ports(cls):return cls(**{f.name:lambda name=f.name:bindings[name] for f in fields(cls)})
    service=PipelineAutoOptimizationLinks(ports(LinkState),ports(LinkProjection),ports(LinkMatching));bindings.update({n:getattr(service,n) for n in NAMES});return service,bindings

class LinkContract(unittest.TestCase):
    def fixture(self):
        events=[];depth=[0];state={'task_id':'task','task_name':'Task','settings':{'enabled':True},'active_model_id':'active','selected_accessory_ids':['a','b'],'required_accessory_counts':{'a':2,'b':1},'owner_user_id':'owner'}
        class Lock:
            def __enter__(self):depth[0]+=1;events.append(('enter',depth[0]))
            def __exit__(self,*a):events.append(('exit',depth[0]));depth[0]-=1
        def stop(s,model,*,reason):events.append(('stop',s,model,reason,depth[0]));s['capture_stop_reason']=reason;return True
        b={'sanitize_ai_detection_task_id':lambda t:str(t or '').strip(),'_auto_optimize_lock':Lock(),'load_auto_optimize_state':lambda t:events.append(('load',t,depth[0])) or state,
           'auto_optimize_completed_model_id':lambda s:'complete','auto_optimize_stop_capture_for_model_locked':stop,'save_auto_optimize_state':lambda s:events.append(('save',s,depth[0])),
           'list_auto_optimize_states':lambda:events.append(('list',)) or [state],'auto_optimize_phase_name':lambda s:'phase','ai_detection_task_model_id':lambda t:'ai:'+t,
           'canonical_pipeline_accessory_ids':lambda config,ids:[config.get('aliases',{}).get(i,i) for i in ids],
           'normalize_pipeline_accessory_counts':lambda config,ids,raw:{i:(raw or {}).get(i,1) for i in ids}}
        service,b=create(b);return SimpleNamespace(service=service,b=b,state=state,events=events,depth=depth)

    def test_fast_completed_order_and_promoted_active(self):
        f=self.fixture();fn=f.service.fast_completed_auto_optimize_model_id
        state={'active_model_id':' active ','candidate_models':[None,{'model_id':'running','status':'running'},{'model_id':' first ','status':' completed '},{'model_id':'second','status':'completed'}]}
        self.assertEqual(fn(state),'first');state['settings']={'serving_mode':'promoted_yolo'};self.assertEqual(fn(state),'active');state['candidate_models']=[];state['settings']={};self.assertEqual(fn(state),'active');self.assertEqual(fn({}),'')

    def test_public_live_lock_stop_save_and_projection(self):
        f=self.fixture();result=f.service.public_auto_optimize_link_for_task_id(' task ',source='direct')
        self.assertEqual(result,{'task_id':'task','task_name':'Task','source':'direct','enabled':True,'serving_mode':'api_primary','phase':'phase','ai_model_id':'ai:task','active_model_id':'active','completed_model_id':'complete','capture_stopped_at':0,'capture_stop_reason':'completed_model_ready'})
        self.assertEqual([e[0] for e in f.events],['enter','load','stop','save','exit']);self.assertEqual(f.depth,[0])
        f=self.fixture();f.b['auto_optimize_stop_capture_for_model_locked']=lambda *a,**kw:False;f.service.public_auto_optimize_link_for_task_id('task',source='direct');self.assertFalse(any(e[0]=='save' for e in f.events))

    def test_supplied_state_shallow_copy_no_storage_and_keyword_arguments(self):
        f=self.fixture();seen=[]
        def phase(s):seen.append(s);s['local']=True;return 'provided'
        f.b['auto_optimize_phase_name']=phase;result=f.service.public_auto_optimize_link_for_task_id('task',source='cached',state=f.state)
        self.assertEqual(result['completed_model_id'],'active');self.assertEqual(result['phase'],'provided');self.assertNotIn('local',f.state);self.assertIsNot(seen[0],f.state);self.assertIs(seen[0]['settings'],f.state['settings']);self.assertEqual(f.events,[])
        self.assertIsNone(f.service.public_auto_optimize_link_for_task_id(' ',source='none'));self.assertEqual(f.events,[])

    def test_state_index_last_duplicate_and_same_record_identity(self):
        f=self.fixture();a={'task_id':' a ','version':1};b={'task_id':'a','version':2};result=f.service.auto_optimize_states_by_task_id([a,{'task_id':' '},b]);self.assertEqual(list(result),['a']);self.assertIs(result['a'],b)

    def test_direct_link_prefers_provided_index_and_absence_does_not_load(self):
        f=self.fixture();link=Mock(return_value={'linked':True});f.b['public_auto_optimize_link_for_task_id']=link
        result=f.service.pipeline_task_auto_optimize_link({'ai_task_id':' task '},{},auto_optimize_states=[],auto_optimize_states_by_id={'task':f.state});self.assertEqual(result,{'linked':True});link.assert_called_once_with('task',source='direct',state=f.state);self.assertEqual(f.events,[])
        link.reset_mock();self.assertIsNone(f.service.pipeline_task_auto_optimize_link({'ai_task_id':'absent'},{},auto_optimize_states=[]));link.assert_not_called()
        f=self.fixture();f.b['list_auto_optimize_states']=lambda:[];link=Mock(return_value={});f.b['public_auto_optimize_link_for_task_id']=link;f.service.pipeline_task_auto_optimize_link({'ai_task_id':'task'},{});link.assert_called_once_with('task',source='direct',state=None)

    def test_matching_counts_owner_aliases_and_stable_newest_tie(self):
        f=self.fixture();rows=[]
        for task,owner,updated,counts in [('old','owner',1,{'a':2,'b':1}),('other','other',100,{'a':2,'b':1}),('wrong','owner',200,{'a':3,'b':1}),('first','owner',10,{'a':2,'b':1}),('tie','owner',10,{'a':2,'b':1})]:rows.append({**f.state,'task_id':task,'owner_user_id':owner,'updated_at':updated,'required_accessory_counts':counts,'selected_accessory_ids':['b','a']})
        task={'accessory_ids':['alias-a','b'],'accessory_counts':{'a':2,'b':1},'owner_user_id':'owner'};config={'aliases':{'alias-a':'a'}};link=Mock(return_value={'ok':True});f.b['public_auto_optimize_link_for_task_id']=link
        self.assertEqual(f.service.pipeline_task_auto_optimize_link(task,config,auto_optimize_states=rows),{'ok':True});link.assert_called_once_with('first',source='accessory_match',state=rows[3]);self.assertEqual(f.events,[])
        link.reset_mock();rows.append({**rows[0],'task_id':'legacy','owner_user_id':'','updated_at':11});f.service.pipeline_task_auto_optimize_link(task,config,auto_optimize_states=rows);self.assertEqual(link.call_args.args,('legacy',))
        link.reset_mock();self.assertIsNone(f.service.pipeline_task_auto_optimize_link({'accessory_ids':[]},config,auto_optimize_states=rows));link.assert_not_called()

    def test_public_save_failure_and_projection_selection_timing(self):
        f=self.fixture();error=RuntimeError('save');f.b['save_auto_optimize_state']=Mock(side_effect=error)
        with self.assertRaises(RuntimeError) as caught:f.service.public_auto_optimize_link_for_task_id('task',source='direct')
        self.assertIs(caught.exception,error);self.assertEqual(f.depth,[0]);self.assertEqual(f.state['capture_stop_reason'],'completed_model_ready')
        f=self.fixture();late=Mock(side_effect=AssertionError('late stop'))
        def completed(s):f.b['auto_optimize_stop_capture_for_model_locked']=lambda *a,**kw:False;return 'ready'
        f.b['auto_optimize_completed_model_id']=completed;f.b['auto_optimize_stop_capture_for_model_locked']=late;f.service.public_auto_optimize_link_for_task_id('task',source='direct');late.assert_not_called()

    @unittest.skipIf(BASELINE,'candidate assembly')
    def test_root_getters_forwarders_and_light_import(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service=server._auto_optimization_links
        for group in (service.state,service.projection,service.matching):
            for f in fields(group):self.assertIs(getattr(group,f.name)(),getattr(server,f.name))
        for name,args,kwargs in zip(NAMES,(({},),('t',),([],),({},{})),({}, {'source':'direct','state':{}},{},{'auto_optimize_states':[],'auto_optimize_states_by_id':{}})):
            mock=Mock(return_value=object())
            with patch.object(server,'_auto_optimization_links',SimpleNamespace(**{name:mock})):self.assertIs(getattr(server,name)(*args,**kwargs),mock.return_value)
            mock.assert_called_once_with(*args,**kwargs)
        subprocess.run([sys.executable,'-c',"import sys; import local_inspection_service.pipeline.auto_optimization_links; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg'))"],cwd=ROOT,check=True)

if __name__=='__main__':unittest.main()

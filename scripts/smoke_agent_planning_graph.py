import dataclasses,json,re,sys,typing,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.agent import planning_composition as module

def build(tag):
    env={'clock':10 if tag=='A' else 20,'configured':False,'settings':[],'calls':[]}
    def settings(scope):env['settings'].append(scope);return {'configured':env['configured']}
    def call(name,payload):
        env['calls'].append(name)
        if name=='accessory.reference.collect':return {'references':[]}
        if 'failure' in env:raise env['failure']
        return {'ok':False,'error':'synthetic failure'}
    uid=lambda item:str(item.get('id','same'))
    material=lambda item:item.get('material','object')
    bindings={'uid':uid,'material':material,'kind':material,'search':re.search,'sanitize':lambda s:tag+'-'+s,'size':lambda x:(1,2,3),'sprites':lambda x:[],'bounded':lambda s,n:str(s)[:n],'optional_number':lambda n:float(n) if n is not None else None,'strings':lambda s,fallback=None,**kwargs:s if isinstance(s,list) else fallback or [],'compile':re.compile,'now':lambda:env['clock'],'clock':lambda:float(env['clock']),'version':1,'max_poses':6,'min_confidence':0.5,'settings':settings,'call':call,'dumps':json.dumps,'path':Path,'encode':lambda *args,**kwargs:None,'max_side':512,'quality':78,'lookup':lambda config:{i['id']:i for i in config['items']},'counts':lambda config,ids,raw:{i:1 for i in ids},'canonical_ids':lambda config,ids:ids}
    kwargs={}
    hints=typing.get_type_hints(module.PosePlanningWorkflows.__init__)
    for name,cls in hints.items():
        kwargs[name]=cls(**{f.name:(lambda key=f.name:bindings[key]) for f in dataclasses.fields(cls)})
    graph=module.PosePlanningWorkflows(**kwargs)
    assert not env['settings'] and not env['calls']
    return graph,env

class PlanningCompositionTests(unittest.TestCase):
    def test_two_actual_graphs_same_ids_and_templates(self):
        a,ea=build('A');b,eb=build('B');ia={'id':'same','name':'cube'};ib=dict(ia)
        pa=a.ensure_accessory_pose_plan(ia);pb=b.ensure_accessory_pose_plan(ib)
        self.assertEqual(pa['poses'][0]['pose_id'],'A-same_face_a_down');self.assertEqual(pb['poses'][0]['pose_id'],'B-same_face_a_down')
        expected={'subject_count':1,'target_paper':False,'grid_layout':False,'background':'solid_chroma_key_tabletop_top_down','camera':'strict_vertical_top_down_90deg','output_contract':'one_accessory_per_image'}
        self.assertEqual(pa['poses'][0]['request'],expected);self.assertEqual(pb['poses'][0]['request'],expected);self.assertIsNot(pa['poses'][0]['request'],pb['poses'][0]['request'])
        self.assertEqual(ea['calls'],[]);self.assertEqual(eb['calls'],[])
    def test_cached_plan_and_text_do_not_reenter_provider(self):
        a,env=build('A');item={'id':'same','name':'cube'};plan=a.generate_accessory_pose_plan(item);count=len(env['settings'])
        self.assertIs(a.ensure_accessory_pose_plan(item),plan);self.assertIsNone(a.ensure_accessory_pose_plan({'id':'text','material':'text'}));self.assertEqual(len(env['settings']),count)
    def test_task_assembly_excludes_text_preserves_input_and_clock(self):
        a,env=build('A');items=[{'id':'same','name':'cube'},{'id':'text','material':'text'}];task={'id':'task','accessory_ids':['same','text']};original=list(task['accessory_ids'])
        result=a.build_agent_mcp_pose_plan(task,{'items':items});self.assertEqual(result['generated_at'],10);self.assertEqual([p['accessory_id'] for p in result['accessories']],['same']);self.assertEqual(task['accessory_ids'],original);self.assertGreater(result['pose_count'],0)
    def test_saved_generation_wrapper_selects_component_after_argument(self):
        a,_=build('A');b,_=build('B');selected=a.generation._calls.generate();old=a.generation
        def argument():a.generation=b.generation;return {'id':'same','name':'cube'}
        with patch.object(old,'generate_accessory_pose_plan',side_effect=AssertionError('stale owner')):
            value=selected(argument())
        self.assertEqual(value['poses'][0]['pose_id'],'B-same_face_a_down')
    def test_provider_failure_is_not_retried(self):
        a,env=build('A');env['configured']=True;error=RuntimeError('synthetic provider error');env['failure']=error;item={'id':'same','name':'cube'}
        with self.assertRaises(RuntimeError) as caught:a.generate_accessory_pose_plan(item)
        self.assertIs(caught.exception,error);self.assertEqual(env['calls'],['accessory.reference.collect','provider.gemini.generate_json']);self.assertNotIn('agent_mcp_pose_plan',item)

if __name__=='__main__':unittest.main()

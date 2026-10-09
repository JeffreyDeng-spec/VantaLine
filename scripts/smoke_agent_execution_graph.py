import dataclasses,hashlib,io,json,sys,tempfile,typing,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.agent import pose_execution_composition as module
import smoke_agent_state_graph as state_probe
import smoke_agent_planning_graph as plan_probe
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.images import ImageFiles

def build(tag,directory,overrides=None):
    state,state_env=state_probe.build(tag);planning,plan_env=plan_probe.build(tag)
    events=[];env={'training':False,'events':events}
    def forbidden(*args,**kwargs):raise AssertionError('unexpected synthetic capability invocation')
    def background(*args):events.append('background');raise RuntimeError('synthetic background failure')
    def trace(*,file):events.append('trace')
    bindings={'normalize':lambda value:value,'training':lambda value:env['training'],'lookup':lambda config:{i['id']:i for i in config.get('items',[])},'canonical':lambda config,ids:ids,'material':lambda item:item.get('material','object'),'identifier':lambda item:item.get('id','same'),'resolve':lambda raw:Path(directory)/tag/str(raw),'suffixes':{'.jpg'},'minimum':3,'version':1,'assets':lambda item:[],'complete':lambda *args:False,'signature':lambda item:tag,'tool':'pose_image','settings':lambda:{},'provider':lambda settings:object(),'error':RuntimeError,'background':background,'print_exception':trace,'stderr':io.StringIO(),'save':lambda config:events.append('save')}
    bindings.update(overrides or {})
    files=BusinessFiles(lambda:None);images=ImageFiles(files=files)
    kwargs={'state':state,'planning':planning,'files':files,'images':images}
    hints=typing.get_type_hints(module.PoseExecutionWorkflows.__init__)
    for name,cls in hints.items():
        if name in kwargs:continue
        kwargs[name]=cls(**{f.name:(lambda key=f.name:bindings.get(key,forbidden)) for f in dataclasses.fields(cls)})
    graph=module.PoseExecutionWorkflows(**kwargs)
    assert not events and not state_env['events'] and not plan_env['settings']
    return graph,env,state_env

class ExecutionCompositionTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory(prefix='pose-execution-prepared-');self.addCleanup(self.tmp.cleanup)
    def test_construction_is_inert_and_no_object_branch_skips_configuration(self):
        graph,env,state_env=build('A',self.tmp.name)
        self.assertEqual(graph.prepare_photo_highlight_sprites_for_task({'detection_method':'ai'},{},{}),(True,False));self.assertEqual(state_env['events'],[]);self.assertEqual(env['events'],[])
    def test_background_failure_logs_and_photo_success_skips_legacy(self):
        graph,env,_=build('A',self.tmp.name);task={'id':'task','detection_method':'ai'}
        with patch.object(graph,'execute_agent_mcp_pose_tool_calls',side_effect=AssertionError('legacy execution')),patch.object(graph,'ensure_agent_mcp_pose_tool_calls',side_effect=AssertionError('legacy registration')):
            self.assertTrue(graph.prepare_agent_mcp_before_sample_generation(task,{}))
        self.assertEqual(env['events'],['background','trace'])
    def test_missing_photos_pause_and_never_fallback_to_legacy(self):
        graph,env,_=build('A',self.tmp.name);env['training']=True;task={'id':'task','accessory_ids':['same'],'detection_method':'local'};config={'items':[{'id':'same','source_files':[]}]}
        with patch.object(graph,'execute_agent_mcp_pose_tool_calls',side_effect=AssertionError('legacy execution')),patch.object(graph,'ensure_agent_mcp_pose_tool_calls',side_effect=AssertionError('legacy registration')):
            self.assertFalse(graph.prepare_agent_mcp_before_sample_generation(task,config))
        self.assertTrue(task['agent_mcp']['skip_pose_image_generation']);self.assertEqual(task['agent_mcp']['pause']['stage'],'pose_image_generation');self.assertEqual(env['events'],['background','trace'])
    def test_configuration_failure_keeps_prior_skip_effects(self):
        graph,env,state_env=build('A',self.tmp.name);env['training']=True;state_env['failure']=RuntimeError('configuration failed');task={'id':'task','accessory_ids':['same'],'detection_method':'local'};orch={};config={'items':[{'id':'same','source_files':[]}]}
        with self.assertRaises(RuntimeError):graph.prepare_photo_highlight_sprites_for_task(task,config,orch)
        self.assertTrue(orch['skip_pose_image_generation']);self.assertEqual(orch['pose_plan']['agent'],'real_photo_highlight_sprite_flow');self.assertNotIn('pause',orch)
    def test_saved_source_wrapper_selects_new_real_owner_after_argument(self):
        a,_,_=build('A',self.tmp.name);b,_,_=build('B',self.tmp.name)
        for tag in ('A','B'):
            folder=Path(self.tmp.name)/tag;folder.mkdir();(folder/'same.jpg').write_bytes(b'synthetic')
        selected=a.photos._objects.sources()
        def argument():a.sources=b.sources;return {'source_files':['same.jpg']}
        paths=selected(argument());self.assertEqual(paths,[Path(self.tmp.name)/'B/same.jpg'])
    def test_two_graphs_resolve_identical_names_to_distinct_files(self):
        a,_,_=build('A',self.tmp.name);b,_,_=build('B',self.tmp.name)
        for tag in ('A','B'):
            folder=Path(self.tmp.name)/tag;folder.mkdir();(folder/'same.jpg').write_bytes(b'synthetic')
        self.assertEqual(a.object_photo_highlight_source_paths({'source_files':['same.jpg']}),[Path(self.tmp.name)/'A/same.jpg']);self.assertEqual(b.object_photo_highlight_source_paths({'source_files':['same.jpg']}),[Path(self.tmp.name)/'B/same.jpg'])

    def run_real_artifact_execution(self, fail_digest=False):
        generated=[]
        class SyntheticProvider:
            def generate_image(self, prompt, references, *, model):
                generated.append((prompt, references, model))
                return {'bytes':b'synthetic image', 'model':model, 'mime_type':'image/png'}
        failure=RuntimeError('synthetic digest failure after image publication')
        def digest(path):
            if fail_digest:raise failure
            return hashlib.sha256(path.read_bytes()).hexdigest()
        graph,env,_=build('A',self.tmp.name,{'owner_root':lambda kind,owner:Path(self.tmp.name)/owner,
            'sanitize':lambda raw:raw,'digest':digest,'public_url':lambda path:'synthetic:'+path.name,
            'bounded':lambda value,size:str(value)[:size],'dumps':json.dumps,
            'screen':lambda value:{'rgb':[0,255,0],'hex':'#00FF00','label':'green'},'contexts':lambda item,**kw:[],
            'chroma':lambda item:{},'provider':lambda settings:SyntheticProvider()})
        call={'call_id':'call','tool':'pose_image','status':'queued','accessory_id':'same','pose_id':'top'}
        orch={'tool_calls':[call], 'pose_plan':{'accessories':[{'accessory_id':'same','poses':[{'pose_id':'top'}]}]}}
        task={'id':'task','owner_user_id':'owner'};config={'items':[{'id':'same'}]}
        bound={'configured':True,'model':'bound-model','timeout_seconds':42,'provider':'synthetic','provider_label':'Synthetic'}
        with patch.object(graph,'ensure_agent_mcp_pose_plan',return_value=orch), patch.object(graph.state,'agent_mcp_gemini_image_config',return_value=bound):
            result=graph.execute_agent_mcp_pose_tool_calls(task,config)
        self.assertEqual(len(generated),1);self.assertEqual(generated[0][2],'bound-model')
        image=Path(self.tmp.name)/'owner/task/same__top.png'
        self.assertEqual(image.read_bytes(),b'synthetic image')
        metadata=image.with_suffix('.png.metadata.json')
        if fail_digest:
            self.assertFalse(result);self.assertEqual(call['status'],'failed');self.assertEqual(call['error'],str(failure))
            self.assertEqual(task['status'],'needs_user_action');self.assertEqual(orch['pause']['stage'],'pose_image_generation')
            self.assertFalse(metadata.exists());self.assertNotIn('output_path',call)
            self.assertEqual(call['model'],'bound-model');self.assertTrue(call['prompt'])
        else:
            self.assertTrue(result);self.assertEqual(call['status'],'completed')
            self.assertEqual(call['output_path'],str(image));self.assertEqual(call['metadata_path'],str(metadata))
            self.assertEqual(json.loads(metadata.read_text())['call_id'],'call')
            self.assertEqual(orch['state'],'pose_image_generation_completed')
        self.assertEqual(len(generated),1)

    def test_actual_execution_provider_and_artifact_store_success(self):
        self.run_real_artifact_execution()

    def test_actual_execution_artifact_second_step_failure_keeps_image_without_retry(self):
        self.run_real_artifact_execution(fail_digest=True)

if __name__=='__main__':unittest.main()

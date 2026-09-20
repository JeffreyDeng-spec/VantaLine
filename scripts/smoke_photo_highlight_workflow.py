"""Draft original photo-highlight workflow contracts; synthetic collaborators only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path.cwd()))

class PhotoHighlightWorkflowContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ)
        cls.environment.start()
        cls.root = tempfile.TemporaryDirectory(prefix='photo-highlight-workflow-')
        (Path(cls.root.name) / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=cls.root.name, VANTALINE_DATA_STORE='json', LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server
    @classmethod
    def tearDownClass(cls):
        cls.root.cleanup()
        cls.environment.stop()
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory(dir=self.root.name)))
        for name in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):
            self.stack.enter_context(patch(name, side_effect=AssertionError('External operation forbidden')))
    def replace(self, name, **kwargs):
        return self.stack.enter_context(patch.object(self.api, name, **kwargs))
    def source_fixture(self):
        self.resolve = self.replace('resolve_service_path', side_effect=lambda value: self.directory / value)
        self.replace('IMAGE_REFERENCE_SUFFIXES', new={'.png'})
        for name in ('first.PNG','second.png','third.png','skip_rectified.png','wrong.txt'):
            (self.directory/name).write_bytes(b'synthetic')
        return {'source_files':['missing.png','wrong.txt','skip_rectified.png','first.PNG','first.PNG','second.png','third.png']}
    def test_source_filter_dedup_order_and_limit(self):
        item = self.source_fixture()
        result = self.api.object_photo_highlight_source_paths(item, limit=2)
        self.assertEqual(result,[self.directory/'first.PNG',self.directory/'second.png'])
        self.assertEqual(self.resolve.call_count,6)
        self.assertEqual(len(item['source_files']),7)
    def test_source_nonpositive_limit_still_accepts_first_valid(self):
        item=self.source_fixture()
        for limit in (0,-1):
            with self.subTest(limit=limit):
                self.assertEqual(self.api.object_photo_highlight_source_paths(item,limit=limit),[self.directory/'first.PNG'])
        self.assertEqual(self.api.object_photo_highlight_source_paths({}),[])
    def test_source_default_is_bound_at_definition_time(self):
        item=self.source_fixture()
        (self.directory/'fourth.png').write_bytes(b'synthetic')
        item['source_files'].append('fourth.png')
        self.replace('PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES',new=0)
        self.assertEqual(len(self.api.object_photo_highlight_source_paths(item)),3)
        self.assertEqual(len(self.api.object_photo_highlight_source_paths(item,limit=4)),4)
    def readiness(self):
        self.replace('PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES',new=2)
        self.replace('PHOTO_HIGHLIGHT_SPRITE_BUILD_VERSION',new=4)
        self.sprites=[{'method':'real_photo_highlight_mask_sprite','photo_highlight_sprite_build':4,'source_photo_path':'a'},{'method':'real_photo_highlight_mask_sprite','photo_highlight_sprite_build':5,'source_path':'b'}]
        self.assets=self.replace('clean_sprite_assets',return_value=self.sprites)
        self.resolve=self.replace('resolve_service_path',side_effect=Path)
        self.complete=self.replace('clean_sprites_policy_complete',return_value=True)
    def test_readiness_requires_distinct_first_sources_before_assets(self):
        self.readiness()
        self.assertFalse(self.api.photo_highlight_clean_sprites_ready({},[Path('a'),Path('a'),Path('b')]))
        self.assets.assert_not_called()
        self.complete.assert_not_called()
    def test_readiness_filters_version_and_shortcircuits_subset(self):
        self.readiness()
        item={}
        self.sprites.append({'method':'old','photo_highlight_sprite_build':9})
        self.assertTrue(self.api.photo_highlight_clean_sprites_ready(item,[Path('a'),Path('b'),Path('ignored')]))
        self.assertIs(self.complete.call_args.args[0],item)
        self.assertIs(self.complete.call_args.args[1][0],self.sprites[0])
        self.complete.reset_mock()
        self.sprites[1]['source_path']='missing'
        self.assertFalse(self.api.photo_highlight_clean_sprites_ready(item,[Path('a'),Path('b')]))
        self.complete.assert_not_called()
        self.sprites[1]['photo_highlight_sprite_build']=3
        self.resolve.reset_mock()
        self.assertFalse(self.api.photo_highlight_clean_sprites_ready(item,[Path('a'),Path('b')]))
        self.resolve.assert_not_called()
    def test_readiness_invalid_version_error_escapes(self):
        self.readiness();self.sprites[0]['photo_highlight_sprite_build']='invalid'
        with self.assertRaises(ValueError):self.api.photo_highlight_clean_sprites_ready({},[Path('a'),Path('b')])
        self.complete.assert_not_called()
    def selection(self):
        self.normalize=self.replace('normalize_pipeline_detection_method',return_value='normalized')
        self.training=self.replace('pipeline_method_uses_training',return_value=True)
        self.first={'id':'one'};self.text={'id':'text'}
        self.lookup=self.replace('accessory_lookup_by_id',return_value={'one':self.first,'text':self.text})
        self.canonical=self.replace('canonical_pipeline_accessory_ids',return_value=['one','missing','text','one'])
        self.material=self.replace('accessory_material_type',side_effect=lambda item:'text' if item is self.text else 'object')
    def test_object_selection_training_early_exit(self):
        self.selection();self.training.return_value=False
        self.assertEqual(self.api.pipeline_photo_highlight_object_items({'params':{'train_mode':'fallback'}},{}),[])
        self.normalize.assert_called_once_with('fallback');self.lookup.assert_not_called();self.canonical.assert_not_called()
    def test_object_selection_precedence_order_and_identity(self):
        self.selection();config={};task={'detection_method':'explicit','params':{'train_mode':'fallback'},'accessory_ids':[1,'text']}
        result=self.api.pipeline_photo_highlight_object_items(task,config)
        self.normalize.assert_called_once_with('explicit');self.canonical.assert_called_once_with(config,['1','text'])
        self.assertEqual(len(result),2);self.assertIs(result[0],self.first);self.assertIs(result[1],self.first)
    def state_fixture(self):
        task={'id':'task'};config={};state={'tool_calls':[]}
        self.items=[{'id':'one','name':'One'}]
        self.objects=self.replace('pipeline_photo_highlight_object_items',return_value=self.items)
        self.uid=self.replace('accessory_uid',side_effect=lambda item:item['id'])
        self.sources=self.replace('object_photo_highlight_source_paths',return_value=[Path('a'),Path('b')])
        self.clock=self.replace('agent_mcp_now',return_value=101)
        self.stage=self.replace('set_agent_mcp_stage')
        self.replace('PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES',new=2)
        return task,config,state
    def test_legacy_skip_no_objects_retains_identity_and_state(self):
        task,config,state=self.state_fixture();self.objects.return_value=[]
        self.assertIs(self.api.mark_legacy_pose_flow_skipped_for_photo_highlight(task,config,state),state)
        self.assertEqual(state,{'tool_calls':[]});self.clock.assert_not_called();self.stage.assert_not_called()
    def test_legacy_skip_existing_policy_clock_and_selective_calls(self):
        task,config,state=self.state_fixture();policy={'existing':True};state['photo_highlight_sprite_policy']=policy
        calls=[{'tool':self.api.AGENT_MCP_TOOL_POSE_IMAGE,'status':status,'error':'old'} for status in ('pending','running','completed','skipped')]
        other={'tool':'other','status':'running'};state['tool_calls']=calls+[other]
        self.assertIs(self.api.mark_legacy_pose_flow_skipped_for_photo_highlight(task,config,state),state)
        self.assertIs(state['photo_highlight_sprite_policy'],policy);self.assertEqual(self.clock.call_count,4)
        self.assertEqual([c['status'] for c in calls],['skipped','skipped','completed','skipped'])
        self.assertEqual(calls[0]['error'],'');self.assertEqual(calls[2]['error'],'old');self.assertEqual(other,{'tool':'other','status':'running'})
        self.assertEqual(state['pose_plan']['accessories'][0]['source_image_count'],2)
        self.assertTrue(state['skip_pose_image_generation']);self.assertEqual(self.stage.call_args.args[1:4],('agent_pose_planning','skipped',100))
    def test_legacy_skip_stage_error_preserves_prior_mutations(self):
        task,config,state=self.state_fixture();self.stage.side_effect=RuntimeError('stage')
        with self.assertRaisesRegex(RuntimeError,'stage'):self.api.mark_legacy_pose_flow_skipped_for_photo_highlight(task,config,state)
        self.assertTrue(state['skip_pose_image_generation']);self.assertEqual(state['pose_plan']['pose_count'],0)
    def plan_fixture(self):
        task,config,state=self.state_fixture()
        self.current=self.replace('agent_mcp_orchestration',return_value=state)
        self.photo=self.replace('pipeline_uses_photo_highlight_sprite_flow',return_value=False)
        self.skip=self.replace('mark_legacy_pose_flow_skipped_for_photo_highlight',return_value=state)
        self.plan={'accessories':[]};self.build=self.replace('build_agent_mcp_pose_plan',return_value=self.plan)
        return task,config,state
    def test_plan_photo_precedes_force_and_cache(self):
        task,config,state=self.plan_fixture();self.photo.return_value=True
        self.assertIs(self.api.ensure_agent_mcp_pose_plan(task,config,force=True),state)
        self.skip.assert_called_once_with(task,config,state);self.build.assert_not_called();self.stage.assert_not_called()
    def test_plan_cache_and_forced_rebuild_identity(self):
        task,config,state=self.plan_fixture();existing={};state['pose_plan']=existing
        self.assertIs(self.api.ensure_agent_mcp_pose_plan(task,config),state);self.build.assert_not_called();self.assertIs(state['pose_plan'],existing)
        self.assertIs(self.api.ensure_agent_mcp_pose_plan(task,config,force=True),state)
        self.assertIs(state['pose_plan'],self.plan);self.assertEqual(state['active_stage'],'agent_pose_planning');self.stage.assert_called_once()
    def preparation(self):
        task,config,state=self.state_fixture()
        self.skip=self.replace('mark_legacy_pose_flow_skipped_for_photo_highlight',return_value=state)
        self.tool={'configured':True,'model':'bound','timeout_seconds':42}
        self.configuration=self.replace('agent_mcp_gemini_image_config',return_value=self.tool)
        self.settings_value={'model':'old'};self.settings=self.replace('image_generation_settings',return_value=self.settings_value)
        self.provider=object();self.factory=self.replace('image_generation_provider_from_settings',return_value=self.provider)
        self.pause=self.replace('pause_agent_mcp_task')
        self.signature=self.replace('accessory_sprite_version',side_effect=['before','after'])
        self.mask=self.replace('build_clean_sprites_from_photo_highlight_masks',return_value=(True,''))
        return task,config,state
    def test_preparation_empty_skips_all_model_access(self):
        task,config,state=self.preparation();self.objects.return_value=[]
        self.assertEqual(self.api.prepare_photo_highlight_sprites_for_task(task,config,state),(True,False))
        self.skip.assert_not_called();self.configuration.assert_not_called();self.factory.assert_not_called()
    def test_preparation_missing_config_pauses_before_settings(self):
        task,config,state=self.preparation();self.tool.update(configured=False,message='configure')
        self.assertEqual(self.api.prepare_photo_highlight_sprites_for_task(task,config,state),(False,False))
        self.skip.assert_called_once();self.settings.assert_not_called();self.factory.assert_not_called()
        self.assertEqual(self.pause.call_args.kwargs['reason'],'configure');self.assertEqual(self.stage.call_args.args[2],'needs_user_action')
    def test_preparation_provider_before_source_validation(self):
        task,config,state=self.preparation();self.sources.return_value=[];events=[]
        self.factory.side_effect=lambda settings:events.append('provider') or self.provider
        self.sources.side_effect=lambda item:events.append('sources') or []
        self.assertEqual(self.api.prepare_photo_highlight_sprites_for_task(task,config,state),(False,False))
        self.assertEqual(events,['provider','sources']);self.assertEqual(self.settings_value,{'model':'bound','timeout_seconds':42})
        self.mask.assert_not_called();self.assertEqual(self.pause.call_args.kwargs['suggested_actions'],['upload_more_reference_photos','cancel'])
    def test_preparation_success_retains_provider_and_signature_order(self):
        task,config,state=self.preparation();events=[]
        self.signature.side_effect=lambda item:events.append('signature') or len(events)
        self.mask.side_effect=lambda *args:events.append('build') or (True,'')
        self.assertEqual(self.api.prepare_photo_highlight_sprites_for_task(task,config,state),(True,True))
        self.assertEqual(events,['signature','build','signature']);self.assertIs(self.mask.call_args.args[2],self.provider)
        self.assertEqual(self.mask.call_args.args[3],'bound');self.assertEqual(state['state'],'photo_highlight_sprites_completed')
        self.assertEqual(state['active_stage'],'sample_generation');self.assertIsNone(state['pause'])
        self.assertEqual([c.args[3] for c in self.stage.call_args_list],[5,99,100])
    def test_preparation_failure_truncates_and_keeps_changed(self):
        task,config,state=self.preparation();self.mask.return_value=(False,'x'*300)
        self.assertEqual(self.api.prepare_photo_highlight_sprites_for_task(task,config,state),(False,True))
        self.assertEqual(self.pause.call_args.kwargs['reason'],'x'*240);self.assertEqual(self.stage.call_args.kwargs['detail'],'x'*240)
        self.assertNotIn('state',state);self.assertEqual(self.signature.call_count,2)
    def test_preparation_exception_keeps_running_and_does_not_pause(self):
        task,config,state=self.preparation();self.mask.side_effect=RuntimeError('builder')
        with self.assertRaisesRegex(RuntimeError,'builder'):self.api.prepare_photo_highlight_sprites_for_task(task,config,state)
        self.assertEqual(self.signature.call_count,1);self.pause.assert_not_called();self.assertEqual(self.stage.call_args.args[2],'running')
    def test_preparation_changed_survives_later_missing_sources(self):
        task,config,state=self.preparation();self.items.append({'id':'two'})
        self.sources.side_effect=[[Path('a'),Path('b')],[]]
        self.assertEqual(self.api.prepare_photo_highlight_sprites_for_task(task,config,state),(False,True))
        self.mask.assert_called_once();self.assertEqual(self.signature.call_count,2);self.assertNotIn('active_stage',state)

    def test_selection_refreshes_material_after_canonicalization(self):
        self.selection();later=Mock(return_value='text')
        def canonical(*args):
            self.api.accessory_material_type=later
            return ['one']
        self.canonical.side_effect=canonical
        self.assertEqual(self.api.pipeline_photo_highlight_object_items({},{}),[])
        later.assert_called_once_with(self.first);self.material.assert_not_called()
    def test_skip_refreshes_clock_for_eager_existing_policy_default(self):
        task,config,state=self.state_fixture();state['photo_highlight_sprite_policy']={};later=Mock(return_value=202)
        def first():
            self.api.agent_mcp_now=later
            return 101
        self.clock.side_effect=first
        self.api.mark_legacy_pose_flow_skipped_for_photo_highlight(task,config,state)
        self.clock.assert_called_once();later.assert_called_once();self.assertEqual(state['pose_plan']['created_at'],101)
    def test_preparation_refreshes_settings_after_configuration(self):
        task,config,state=self.preparation();later=Mock(return_value=self.settings_value)
        def config_getter():
            self.api.image_generation_settings=later
            return self.tool
        self.configuration.side_effect=config_getter
        self.assertEqual(self.api.prepare_photo_highlight_sprites_for_task(task,config,state),(True,True))
        later.assert_called_once();self.settings.assert_not_called()
    def test_preparation_refreshes_signature_after_builder(self):
        task,config,state=self.preparation();self.signature.side_effect=None;self.signature.return_value='same';later=Mock(return_value='changed')
        def build(*args):
            self.api.accessory_sprite_version=later
            return True,''
        self.mask.side_effect=build
        self.assertEqual(self.api.prepare_photo_highlight_sprites_for_task(task,config,state),(True,True))
        self.signature.assert_called_once();later.assert_called_once_with(self.items[0])


    def test_photo_workflow_constructors_do_not_read_dependencies(self):
        from dataclasses import fields
        from local_inspection_service.agent import photo_highlight_ports as ports
        from local_inspection_service.agent.photo_highlight_sources import PhotoHighlightSources
        from local_inspection_service.agent.photo_highlight_selection import PhotoHighlightSelection
        from local_inspection_service.agent.photo_highlight_workflow import PhotoHighlightWorkflow
        getters=[]
        def group(port_type):
            values={f.name:Mock(return_value=None) for f in fields(port_type)}
            getters.extend(values.values())
            return port_type(**values)
        PhotoHighlightSources(group(ports.PhotoSourceMedia),group(ports.PhotoSpriteLimits),group(ports.PhotoSpriteReadiness))
        PhotoHighlightSelection(group(ports.PhotoObjectSelection))
        PhotoHighlightWorkflow(group(ports.PhotoWorkflowObjects),group(ports.PhotoSpriteLimits),group(ports.PhotoWorkflowState),group(ports.PhotoWorkflowModels))
        for getter in getters:getter.assert_not_called()
    def test_photo_workflow_compositions_remain_independent(self):
        from dataclasses import fields
        from local_inspection_service.agent import photo_highlight_ports as ports
        from local_inspection_service.agent.photo_highlight_sources import PhotoHighlightSources
        from local_inspection_service.agent.photo_highlight_selection import PhotoHighlightSelection
        from local_inspection_service.agent.photo_highlight_workflow import PhotoHighlightWorkflow
        def group(port_type,**selected):
            return port_type(**{f.name:selected.get(f.name,lambda:None) for f in fields(port_type)})
        def make(name):
            state={'owner':name};events=[];path=self.directory/(name+'.png');path.write_bytes(b'synthetic')
            media=group(ports.PhotoSourceMedia,resolve=lambda:lambda value:path,suffixes=lambda:{'.png'})
            limits=group(ports.PhotoSpriteLimits,minimum=lambda:2,version=lambda:4)
            sources=PhotoHighlightSources(media,limits,group(ports.PhotoSpriteReadiness))
            selection=PhotoHighlightSelection(group(ports.PhotoObjectSelection,normalize=lambda:lambda value:name,training=lambda:lambda value:events.append(value) or False))
            workflow=PhotoHighlightWorkflow(group(ports.PhotoWorkflowObjects,items=lambda:lambda *args:[]),limits,group(ports.PhotoWorkflowState,current=lambda:lambda task:state,photo_flow=lambda:lambda *args:True,skip_legacy=lambda:lambda *args:state),group(ports.PhotoWorkflowModels))
            return sources,selection,workflow,state,events,path
        instances={name:make(name) for name in ('first','second')}
        with patch.object(self.api,'resolve_service_path',side_effect=AssertionError('root media')),patch.object(self.api,'normalize_pipeline_detection_method',side_effect=AssertionError('root selection')),patch.object(self.api,'agent_mcp_orchestration',side_effect=AssertionError('root state')),patch.object(self.api,'pipeline_photo_highlight_object_items',side_effect=AssertionError('root objects')):
            for name in ('first','second','first'):
                sources,selection,workflow,state,events,path=instances[name]
                self.assertEqual(sources.object_photo_highlight_source_paths({'source_files':['input']},limit=1),[path])
                self.assertFalse(sources.photo_highlight_clean_sprites_ready({},[]))
                self.assertEqual(selection.pipeline_photo_highlight_object_items({},{}),[])
                self.assertIs(workflow.ensure_agent_mcp_pose_plan({},{}),state)
                self.assertIs(workflow.mark_legacy_pose_flow_skipped_for_photo_highlight({},{},state),state)
                self.assertEqual(workflow.prepare_photo_highlight_sprites_for_task({},{},state),(True,False))
            self.assertEqual(instances['first'][4],['first','first'])
            self.assertEqual(instances['second'][4],['second'])


if __name__=='__main__':unittest.main()

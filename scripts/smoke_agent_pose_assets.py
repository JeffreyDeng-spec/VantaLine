"""Synthetic draft baseline for pose assets and template policy."""

import os,sys,tempfile,unittest

from pathlib import Path

from contextlib import ExitStack

from unittest.mock import Mock,patch

sys.path.insert(0,str(Path.cwd()))

class AgentPoseAssetsContracts(unittest.TestCase):

    @classmethod

    def setUpClass(cls):

        cls.env=patch.dict(os.environ);cls.env.start();cls.tmp=tempfile.TemporaryDirectory(prefix='pose-assets-')

        (Path(cls.tmp.name)/'local_inspection_service/static').mkdir(parents=True)

        os.environ.update(LOCAL_INSPECTION_ROOT=cls.tmp.name,VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')

        from local_inspection_service import server

        cls.api=server

    @classmethod

    def tearDownClass(cls):cls.tmp.cleanup();cls.env.stop()

    def setUp(self):

        self.stack=ExitStack();self.addCleanup(self.stack.close)

        for n in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):

            self.stack.enter_context(patch(n,side_effect=AssertionError('external operation forbidden')))

    def patch(self,name,**kw):return self.stack.enter_context(patch.object(self.api,name,**kw))

    def path(self,name,exists=True):

        p=Mock();p.exists.return_value=exists;p.suffix=Path(name).suffix;p.__str__=Mock(return_value=name);return p

    def test_reference_filter_preserves_asset_identity_and_mutates_only_valid_path(self):

        accepted={'kind':'agent_mcp_pose_reference','path':'valid'};missing={'kind':'agent_mcp_pose_reference','path':'missing'};bad={'kind':'agent_mcp_pose_reference','path':'bad'};other={'kind':'other','path':'skip'}

        paths={'valid':self.path('/synthetic/picture.PNG'),'missing':self.path('/synthetic/missing.png',False),'bad':self.path('/synthetic/file.txt')};resolve=self.patch('resolve_service_path',side_effect=paths.__getitem__);self.patch('IMAGE_REFERENCE_SUFFIXES',new={'.png'})

        result=self.api.agent_mcp_pose_reference_assets({'normalized_assets':[other,missing,bad,accepted]});self.assertEqual(result,[accepted]);self.assertIs(result[0],accepted);self.assertEqual(accepted['path'],'/synthetic/picture.PNG');self.assertEqual(missing['path'],'missing');self.assertEqual(resolve.call_count,3)

    def test_invalid_items_return_before_material_lookup(self):

        material=self.patch('accessory_material_type');self.assertFalse(self.api.agent_mcp_accessory_pose_images_exist(None));self.assertFalse(self.api.agent_mcp_accessory_standard_images_ready([]));material.assert_not_called()

    def test_text_pose_existence_uses_canonical_assets_only(self):

        self.patch('accessory_material_type',return_value='text');assets=self.patch('canonical_text_assets',return_value=[{'synthetic':True}]);photo=self.patch('object_photo_highlight_source_paths');self.assertTrue(self.api.agent_mcp_accessory_pose_images_exist({}));assets.assert_called_once_with({});photo.assert_not_called()

    def test_text_standard_requires_nonempty_and_complete_assets(self):

        self.patch('accessory_material_type',return_value='text');assets=self.patch('canonical_text_assets',return_value=[]);complete=self.patch('canonical_text_assets_complete',return_value=True);self.assertFalse(self.api.agent_mcp_accessory_standard_images_ready({}));complete.assert_not_called();value=[{}];assets.return_value=value;self.assertTrue(self.api.agent_mcp_accessory_standard_images_ready({}));self.assertIs(complete.call_args.args[1],value)

    def test_highlight_ready_shortcuts_pose_and_standard_fallbacks(self):

        self.patch('accessory_material_type',return_value='object');sources=[];self.patch('object_photo_highlight_source_paths',return_value=sources);ready=self.patch('photo_highlight_clean_sprites_ready',return_value=True);reference=self.patch('agent_mcp_pose_reference_assets');self.assertTrue(self.api.agent_mcp_accessory_pose_images_exist({}));self.assertTrue(self.api.agent_mcp_accessory_standard_images_ready({}));self.assertIs(ready.call_args.args[1],sources);reference.assert_not_called()

    def test_pose_existence_falls_back_to_reference_assets(self):

        self.patch('accessory_material_type',return_value='object');self.patch('object_photo_highlight_source_paths',return_value=[]);self.patch('photo_highlight_clean_sprites_ready',return_value=False);reference=self.patch('agent_mcp_pose_reference_assets',return_value=[]);self.assertFalse(self.api.agent_mcp_accessory_pose_images_exist({}));reference.return_value=[{}];self.assertTrue(self.api.agent_mcp_accessory_pose_images_exist({}))

    def test_standard_gates_sprites_completion_and_rebuild(self):

        self.patch('accessory_material_type',return_value='object');self.patch('object_photo_highlight_source_paths',return_value=[]);self.patch('photo_highlight_clean_sprites_ready',return_value=False);reference=self.patch('agent_mcp_pose_reference_assets',return_value=[]);sprites=self.patch('clean_sprite_assets',return_value=[{}]);complete=self.patch('clean_sprites_policy_complete',return_value=True);rebuild=self.patch('agent_mcp_clean_sprites_need_rebuild',return_value=False)

        self.assertFalse(self.api.agent_mcp_accessory_standard_images_ready({}));sprites.assert_not_called();reference.return_value=[{}];self.assertTrue(self.api.agent_mcp_accessory_standard_images_ready({}));self.assertIs(complete.call_args.args[1],sprites.return_value);rebuild.return_value=True;self.assertFalse(self.api.agent_mcp_accessory_standard_images_ready({}))

    def test_rebuild_text_and_missing_reference_return_early(self):

        material=self.patch('accessory_material_type',return_value='text');ref=self.patch('agent_mcp_pose_reference_assets',return_value=[]);sprites=self.patch('clean_sprite_assets');self.assertFalse(self.api.agent_mcp_clean_sprites_need_rebuild({}));ref.assert_not_called();material.return_value='object';self.assertFalse(self.api.agent_mcp_clean_sprites_need_rebuild({}));sprites.assert_not_called()

    def test_rebuild_checks_version_sentinel_and_pose_family(self):

        self.patch('accessory_material_type',return_value='object');self.patch('agent_mcp_pose_reference_assets',return_value=[{}]);self.patch('AGENT_MCP_SPRITE_BUILD_VERSION',new=3);family=self.patch('canonical_pose_family_name',side_effect=lambda x:x);asset={'agent_mcp_pose_call_id':'call','agent_mcp_sprite_build':3,'source_pose_collection_job_id':'legacy_clean_sprite','source_pose_family':'upright'};self.patch('clean_sprite_assets',return_value=[{'ignored':True},asset]);self.assertFalse(self.api.agent_mcp_clean_sprites_need_rebuild({}));asset['agent_mcp_sprite_build']=2;self.assertTrue(self.api.agent_mcp_clean_sprites_need_rebuild({}));asset['agent_mcp_sprite_build']=3;asset['source_pose_collection_job_id']='grid';self.assertTrue(self.api.agent_mcp_clean_sprites_need_rebuild({}));asset['source_pose_collection_job_id']='legacy_clean_sprite';asset['source_pose_family']='other';self.assertTrue(self.api.agent_mcp_clean_sprites_need_rebuild({}));asset['source_pose_family']='lying';self.assertFalse(self.api.agent_mcp_clean_sprites_need_rebuild({}))

    def test_existing_text_requires_complete_and_clean_sprite_shortcuts_calls(self):

        material=self.patch('accessory_material_type',return_value='text');complete=self.patch('canonical_text_assets_complete',return_value=False);sprites=self.patch('clean_sprite_assets',return_value=[{}]);self.assertFalse(self.api.agent_mcp_accessory_has_existing_or_pose_asset({},{}));complete.assert_called_once_with({});sprites.assert_not_called();material.return_value='object';uid=self.patch('accessory_uid');self.assertTrue(self.api.agent_mcp_accessory_has_existing_or_pose_asset({},{}));uid.assert_not_called()

    def test_existing_pose_call_filters_tool_status_identity_and_path(self):

        self.patch('accessory_material_type',return_value='object');self.patch('clean_sprite_assets',return_value=[]);self.patch('accessory_uid',return_value='part');self.patch('AGENT_MCP_TOOL_POSE_IMAGE',new='pose');resolve=self.patch('resolve_service_path',return_value=self.path('/synthetic/image.PNG'));self.patch('IMAGE_REFERENCE_SUFFIXES',new={'.png'});calls=[{'tool':'other','status':'completed','accessory_id':'part'},{'tool':'pose','status':'running','accessory_id':'part'},{'tool':'pose','status':'completed','accessory_id':'other'},{'tool':'pose','status':'completed','accessory_id':'part','output_path':'source'}];self.assertTrue(self.api.agent_mcp_accessory_has_existing_or_pose_asset({}, {'tool_calls':calls}));resolve.assert_called_once_with('source');resolve.return_value=self.path('/synthetic/missing.png',False);self.assertFalse(self.api.agent_mcp_accessory_has_existing_or_pose_asset({}, {'tool_calls':calls}))

    def test_missing_names_follow_canonical_order_skip_unknown_and_keep_name_fallback(self):

        first={'name':'first'};second={'name':''};config={};orch={};self.patch('accessory_lookup_by_id',return_value={'a':first,'b':second});canonical=self.patch('canonical_pipeline_accessory_ids',return_value=['b','missing','a']);has=self.patch('agent_mcp_accessory_has_existing_or_pose_asset',return_value=False);self.assertEqual(self.api.agent_mcp_missing_existing_asset_names({'accessory_ids':[2,'a']},config,orch),['b','first']);canonical.assert_called_once_with(config,['2','a']);self.assertEqual(has.call_count,2);self.assertIs(has.call_args.args[1],orch)

    def test_kind_precedence_and_multilingual_matching(self):

        self.patch('accessory_uid',return_value='');material=self.patch('accessory_material_type',return_value='object');self.assertEqual(self.api.agent_mcp_object_kind({'name':'Bottle cube label'}),'bottle');self.assertEqual(self.api.agent_mcp_object_kind({'name':'立方'}),'cube');self.assertEqual(self.api.agent_mcp_object_kind({'name':'说明书'}),'thin_object');self.assertEqual(self.api.agent_mcp_object_kind({'name':'gear'}),'generic_object');material.return_value='text';self.assertEqual(self.api.agent_mcp_object_kind({'name':'gear'}),'thin_object')

    def test_request_returns_fresh_fixed_contract(self):

        a=self.api.agent_mcp_pose_request();b=self.api.agent_mcp_pose_request();self.assertEqual(a,{'subject_count':1,'target_paper':False,'grid_layout':False,'background':'solid_chroma_key_tabletop_top_down','camera':'strict_vertical_top_down_90deg','output_contract':'one_accessory_per_image'});self.assertIsNot(a,b)

    def test_templates_preserve_order_fallback_and_fresh_request_per_pose(self):

        calls=[]

        def request():value={'n':len(calls)};calls.append(value);return value

        self.patch('agent_mcp_pose_request',side_effect=request);items=self.api.agent_mcp_pose_templates('part','cube');self.assertEqual([x['pose_id'] for x in items],['part_face_a_down','part_face_b_down','part_face_c_down']);self.assertIs(items[0]['request'],calls[0]);self.assertIsNot(items[0]['request'],items[1]['request']);self.assertEqual([x['pose_id'] for x in self.api.agent_mcp_pose_templates('part','unknown')],['part_primary_rest','part_side_rest'])

    def test_reference_resolver_refreshes_between_assets(self):

        first_path=self.path('/synthetic/first.png');later_path=self.path('/synthetic/second.png');later=Mock(return_value=later_path);first=self.patch('resolve_service_path',return_value=first_path);self.patch('IMAGE_REFERENCE_SUFFIXES',new={'.png'});api=self.api

        def exists():api.resolve_service_path=later;return True

        first_path.exists.side_effect=exists

        items=[{'kind':'agent_mcp_pose_reference','path':'a'},{'kind':'agent_mcp_pose_reference','path':'b'}];self.assertEqual([x['path'] for x in self.api.agent_mcp_pose_reference_assets({'normalized_assets':items})],['/synthetic/first.png','/synthetic/second.png']);first.assert_called_once_with('a');later.assert_called_once_with('b')

    def test_standard_rebuild_callback_refreshes_after_completeness(self):

        self.patch('accessory_material_type',return_value='object');self.patch('object_photo_highlight_source_paths',return_value=[]);self.patch('photo_highlight_clean_sprites_ready',return_value=False);self.patch('agent_mcp_pose_reference_assets',return_value=[{}]);self.patch('clean_sprite_assets',return_value=[{}]);old=self.patch('agent_mcp_clean_sprites_need_rebuild',return_value=True);later=Mock(return_value=False);api=self.api

        def complete(*args):api.agent_mcp_clean_sprites_need_rebuild=later;return True

        self.patch('clean_sprites_policy_complete',side_effect=complete);self.assertTrue(self.api.agent_mcp_accessory_standard_images_ready({}));old.assert_not_called();later.assert_called_once_with({})

    def test_template_request_selected_after_base_id_formatting(self):

        old=self.patch('agent_mcp_pose_request',return_value={'old':True});later=Mock(side_effect=lambda:{'later':True});api=self.api

        class BaseId:

            def __format__(self,spec):api.agent_mcp_pose_request=later;return 'part'

        result=self.api.agent_mcp_pose_templates(BaseId(),'bottle');self.assertEqual([x['request'] for x in result],[{'later':True},{'later':True}]);old.assert_not_called();self.assertEqual(later.call_count,2)

    def test_canonical_id_callback_selected_before_task_id_conversion(self):

        later=Mock(return_value=[]);first=self.patch('canonical_pipeline_accessory_ids',return_value=['part']);api=self.api

        class ItemId:

            def __str__(self):api.canonical_pipeline_accessory_ids=later;return 'part'

        self.patch('accessory_lookup_by_id',return_value={'part':{'name':'part'}});self.patch('agent_mcp_accessory_has_existing_or_pose_asset',return_value=False)

        self.assertEqual(self.api.agent_mcp_missing_existing_asset_names({'accessory_ids':[ItemId()]},{},{}),['part']);first.assert_called_once_with({},['part']);later.assert_not_called()





    def test_pose_constructors_do_not_read_capabilities(self):

        from dataclasses import fields

        from local_inspection_service.agent import pose_asset_ports as p

        from local_inspection_service.agent.pose_assets import AgentPoseAssets

        from local_inspection_service.agent.pose_templates import AgentPoseTemplates

        getters=[]

        def group(kind):

            values={f.name:Mock(return_value=None) for f in fields(kind)};getters.extend(values.values());return kind(**values)

        AgentPoseAssets(group(p.PoseAssetPaths),group(p.PoseAssetMaterial),group(p.PoseAssetSprites),group(p.PoseAssetCalls),group(p.PoseAssetCatalog));AgentPoseTemplates(group(p.PoseTemplateIdentity),group(p.PoseTemplateCalls))

        for getter in getters:getter.assert_not_called()

    def test_two_live_pose_compositions_keep_dependencies_separate(self):

        import re

        from dataclasses import fields

        from local_inspection_service.agent import pose_asset_ports as p

        from local_inspection_service.agent.pose_assets import AgentPoseAssets

        from local_inspection_service.agent.pose_templates import AgentPoseTemplates

        def group(port_type,**selected):return port_type(**{f.name:selected.get(f.name,lambda:None) for f in fields(port_type)})

        def make(name):

            assets=AgentPoseAssets(group(p.PoseAssetPaths,resolve=lambda:lambda raw:self.path('/synthetic/'+name+'.png'),suffixes=lambda:{'.png'}),group(p.PoseAssetMaterial,kind=lambda:lambda item:'object'),group(p.PoseAssetSprites,source_paths=lambda:lambda item:[],highlight_ready=lambda:lambda item,paths:True),group(p.PoseAssetCalls),group(p.PoseAssetCatalog))

            templates=AgentPoseTemplates(group(p.PoseTemplateIdentity,uid=lambda:lambda item:name,kind=lambda:lambda item:'object',search=lambda:re.search),group(p.PoseTemplateCalls,request=lambda:lambda:{'owner':name}))

            return assets,templates

        instances={name:make(name) for name in ('bottle','cube')}

        with patch.object(self.api,'resolve_service_path',side_effect=AssertionError('root path')),patch.object(self.api,'accessory_uid',side_effect=AssertionError('root uid')),patch.object(self.api,'agent_mcp_pose_request',side_effect=AssertionError('root request')):

            for name in ('bottle','cube','bottle'):

                assets,templates=instances[name];asset={'kind':'agent_mcp_pose_reference','path':'source'};result=assets.agent_mcp_pose_reference_assets({'normalized_assets':[asset]});self.assertIs(result[0],asset);self.assertEqual(asset['path'],'/synthetic/'+name+'.png');self.assertTrue(assets.agent_mcp_accessory_standard_images_ready({}));self.assertEqual(templates.agent_mcp_object_kind({}),name);self.assertTrue(all(x['request']=={'owner':name} for x in templates.agent_mcp_pose_templates('part',name)));self.assertEqual(templates.agent_mcp_pose_request()['subject_count'],1)





if __name__=='__main__':unittest.main()

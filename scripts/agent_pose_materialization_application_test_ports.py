"""Finite external ports for original pose materialization contracts."""
from dataclasses import replace
from unittest.mock import patch

CHROMA={'fraction':'accessory_reference_chroma_fraction','screen':'normalize_chroma_screen','threshold':'CHROMA_SCREEN_REFERENCE_FRACTION_THRESHOLD'}
CUTOUT={'chroma':'chroma_screen_object_cutout','precise':'precise_green_plate_cutout','green':'green_conveyor_object_cutout','background':'ai_background_cutout_with_bbox','generic':'object_cutout_from_image','final_green':'green_screen_object_cutout_with_bbox','usable':'usable_object_cutout'}
POLICY={'material':'accessory_material_type','deduplicate':'dedup_agent_mcp_pose_references','references':'agent_mcp_pose_reference_assets','existing':'clean_sprite_assets','complete':'clean_sprites_policy_complete','alpha':'object_alpha_material_policy'}
METADATA={'footprint':'pose_render_footprint_metadata','normalize':'normalize_sprite_family_canvases','scale':'apply_upright_scale_correction_metadata','laying':'apply_laying_standard_render_size_hints'}
MEDIA={'resolve':'resolve_service_path','public_url':'public_output_url','digest':'file_sha256','suffixes':'IMAGE_REFERENCE_SUFFIXES'}
STATE={'current':'agent_mcp_orchestration','lookup':'accessory_lookup_by_id','now':'agent_mcp_now','tool':'AGENT_MCP_TOOL_POSE_IMAGE'}
SPRITES={'sources':'object_photo_highlight_source_paths','ready':'photo_highlight_clean_sprites_ready','build':'build_clean_sprites_from_agent_mcp_poses'}


def bind_pose_materialization(api,stack):
    graph=api._default_application.training_pipeline
    def bind(owner,attribute,mapping):stack.enter_context(patch.object(owner,attribute,replace(getattr(owner,attribute),**{field:(lambda _name=name:getattr(api,_name)) for field,name in mapping.items()})))
    for owner in (graph._pose_chroma_policy,graph._pose_sprite_builder,graph._pose_asset_materialization):bind(owner,'_chroma',CHROMA)
    bind(graph._pose_cutout_pipeline,'_cutouts',CUTOUT)
    builder=graph._pose_sprite_builder;material=graph._pose_asset_materialization
    bind(builder,'_policy',POLICY);bind(builder,'_metadata',METADATA);bind(builder,'_media',MEDIA)
    bind(builder,'_runtime',{'root':'NORMALIZED_DIR','identifier':'accessory_uid','version':'AGENT_MCP_SPRITE_BUILD_VERSION','safe_id':'safe_record_id'})
    stack.enter_context(patch.object(builder,'_runtime',replace(builder._runtime,now=lambda:api.time.time,rng=lambda:api.np.random.default_rng)))
    bind(builder,'_images',{'segment':'segment_agent_mcp_pose_object','write':'write_clean_sprite'})
    bind(material,'_state',STATE);bind(material,'_media',MEDIA);bind(material,'_sprites',SPRITES)


def assert_default_pose_materialization(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.agent.pose_chroma_policy import PoseChromaPolicy
    from local_inspection_service.agent.pose_cutout_pipeline import PoseCutoutPipeline
    from local_inspection_service.agent.pose_sprite_builder import PoseSpriteBuilder
    from local_inspection_service.agent.pose_asset_materialization import PoseAssetMaterialization
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;inspection=app.inspection;item,other,third,fourth=object(),object(),object(),object();builder=graph._pose_sprite_builder;material=graph._pose_asset_materialization
    for name,kind in (('_pose_chroma_policy',PoseChromaPolicy),('_pose_cutout_pipeline',PoseCutoutPipeline),('_pose_sprite_builder',PoseSpriteBuilder),('_pose_asset_materialization',PoseAssetMaterialization)):case.assertIs(type(getattr(graph,name)),kind);case.assertIs(getattr(api,name),getattr(graph,name))
    case.assertIs(material.files,app.artifacts.files)
    for getter,name in ((graph._pose_chroma_policy._chroma.threshold,'CHROMA_SCREEN_REFERENCE_FRACTION_THRESHOLD'),(builder._chroma.threshold,'CHROMA_SCREEN_REFERENCE_FRACTION_THRESHOLD'),(material._chroma.threshold,'CHROMA_SCREEN_REFERENCE_FRACTION_THRESHOLD'),(builder._runtime.root,'NORMALIZED_DIR'),(builder._runtime.version,'AGENT_MCP_SPRITE_BUILD_VERSION'),(builder._media.suffixes,'IMAGE_REFERENCE_SUFFIXES'),(material._media.suffixes,'IMAGE_REFERENCE_SUFFIXES'),(material._state.tool,'AGENT_MCP_TOOL_POSE_IMAGE')):
        original=getattr(app.values,name);case.assertIs(getter(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(getter(),other)
        finally:object.__setattr__(app.values,name,original)
    for owner in (graph._pose_chroma_policy,builder,material):
        assert_native_relay(case,owner._chroma.fraction(),(inspection._reference_evidence,'accessory_reference_chroma_fraction',(item,other),{},(item,other),{'max_images':3}))
        assert_native_relay(case,owner._chroma.screen(),(inspection._reference_evidence,'normalize_chroma_screen',(item,),{},(item,),{}))
    for field,receiver,method,args in (('chroma',inspection._chroma_cutouts,'chroma_screen_object_cutout',(item,other)),('precise',inspection._background_cutouts,'precise_green_plate_cutout',(item,)),('green',inspection._chroma_cutouts,'green_conveyor_object_cutout',(item,)),('background',inspection._background_cutouts,'ai_background_cutout_with_bbox',(item,)),('generic',inspection._cutout_selection,'object_cutout_from_image',(item,other)),('final_green',inspection._cutout_selection,'green_screen_object_cutout_with_bbox',(item,other)),('usable',inspection._crop_selection,'usable_object_cutout',(item,other))):
        assert_native_relay(case,getattr(graph._pose_cutout_pipeline._cutouts,field)(),(receiver,method,args,{},args,{}))
    for getter,receiver,method,args,kw,expected_kw in ((builder._policy.deduplicate(),builder,'dedup_agent_mcp_pose_references',(item,),{},{}),(builder._policy.references(),graph._agent_pose_assets,'agent_mcp_pose_reference_assets',(item,),{},{}),(builder._policy.existing(),inspection._sprite_asset_catalog,'clean_sprite_assets',(item,),{},{}),(builder._policy.complete(),inspection._sprite_asset_catalog,'clean_sprites_policy_complete',(item,other),{},{}),(builder._runtime.safe_id(),inspection._pose_collection_jobs,'safe_record_id',(item,),{},{}),(builder._images.segment(),graph._pose_cutout_pipeline,'segment_agent_mcp_pose_object',(item,other,third),{},{}),(builder._images.write(),inspection._sprite_artifact_writer,'write_clean_sprite',(item,other,third,fourth),{},{}),(builder._metadata.footprint(),inspection._sprite_footprint,'pose_render_footprint_metadata',(item,other,third),{},{}),(builder._metadata.normalize(),inspection._sprite_canvas_normalizer,'normalize_sprite_family_canvases',(item,),{},{}),(builder._metadata.scale(),inspection._sprite_scale,'apply_upright_scale_correction_metadata',(item,other),{},{}),(builder._metadata.laying(),inspection._sprite_render_metadata,'apply_laying_standard_render_size_hints',(item,),{},{}),(material._state.current(),graph._agent_state_workflows.state,'agent_mcp_orchestration',(item,),{},{}),(material._state.lookup(),inspection._accessory_lookup,'accessory_lookup_by_id',(item,),{},{}),(material._state.now(),graph._agent_state_workflows.state,'agent_mcp_now',(),{},{}),(material._sprites.sources(),graph._photo_highlight_sources,'object_photo_highlight_source_paths',(item,),{}, {'limit':app.values.PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES}),(material._sprites.ready(),graph._photo_highlight_sources,'photo_highlight_clean_sprites_ready',(item,other),{},{}),(material._sprites.build(),builder,'build_clean_sprites_from_agent_mcp_poses',(item,),{'force':True},{'force':True})):
        assert_native_relay(case,getter,(receiver,method,args,kw,args,expected_kw))
    for owner in (builder,material):
        assert_native_relay(case,owner._media.resolve(),(app.infrastructure._service_paths,'resolve_service_path',(item,),{},(item,),{'for_write':False}))
        assert_native_relay(case,owner._media.public_url(),(app.infrastructure._service_paths,'public_output_url',(item,),{},(item,),{}))
        with patch.object(wiring,'strict_training_file_sha256',return_value=other) as receiver:case.assertIs(owner._media.digest()(item),other);receiver.assert_called_once_with(item,files=app.artifacts.files)
    for getter,name,args in ((builder._policy.material(),'accessory_material_type',(item,)),(builder._runtime.identifier(),'accessory_uid',(item,)),(builder._policy.alpha(),'object_alpha_material_policy',(item,other))):
        with patch.object(wiring._accessory_policy,name,return_value=third) as receiver:case.assertIs(getter(*args),third);receiver.assert_called_once_with(*args)
    case.assertIs(builder._runtime.now(),wiring.time.time);case.assertIs(builder._runtime.rng(),wiring.np.random.default_rng);case.assertIs(builder._images.read_mode(),wiring.cv2.IMREAD_COLOR)
    case.assertIsNone(app.artifacts.files.runtime_provider());case.assertIs(builder._images.read(),wiring.cv2.imread)

    with patch.object(wiring._accessory_policy,'object_alpha_material_policy',return_value=other) as receiver:case.assertIs(builder._policy.alpha()(item),other);receiver.assert_called_once_with(item,None)
    for kw in ({},{'force':False}):
        assert_native_relay(case,material._sprites.build(),(builder,'build_clean_sprites_from_agent_mcp_poses',(item,),kw,(item,),{'force':False}))

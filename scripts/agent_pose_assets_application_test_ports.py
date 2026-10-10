"""Finite pose asset and template capability fixtures."""
from dataclasses import replace
from unittest.mock import patch

ASSETS=(('_paths',{'resolve':'resolve_service_path','suffixes':'IMAGE_REFERENCE_SUFFIXES'}),('_material',{'kind':'accessory_material_type','text_assets':'canonical_text_assets','text_complete':'canonical_text_assets_complete'}),('_sprites',{'source_paths':'object_photo_highlight_source_paths','highlight_ready':'photo_highlight_clean_sprites_ready','assets':'clean_sprite_assets','complete':'clean_sprites_policy_complete','family':'canonical_pose_family_name','version':'AGENT_MCP_SPRITE_BUILD_VERSION'}),('_calls',{'references':'agent_mcp_pose_reference_assets','rebuild':'agent_mcp_clean_sprites_need_rebuild'}),('_catalog',{'uid':'accessory_uid','lookup':'accessory_lookup_by_id','canonical_ids':'canonical_pipeline_accessory_ids','has_asset':'agent_mcp_accessory_has_existing_or_pose_asset','pose_tool':'AGENT_MCP_TOOL_POSE_IMAGE'}))


def bind_pose_assets(api,stack):
    graph=api._default_application.training_pipeline;assets=graph._agent_pose_assets;templates=graph._pose_planning_workflows.templates
    for attribute,mapping in ASSETS:stack.enter_context(patch.object(assets,attribute,replace(getattr(assets,attribute),**{field:(lambda _name=name:getattr(api,_name)) for field,name in mapping.items()})))
    stack.enter_context(patch.object(templates,'_identity',replace(templates._identity,uid=lambda:api.accessory_uid,kind=lambda:api.accessory_material_type)))


def assert_default_pose_assets(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.agent.pose_assets import AgentPoseAssets
    from local_inspection_service.agent.pose_templates import AgentPoseTemplates
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;assets=graph._agent_pose_assets;templates=graph._pose_planning_workflows.templates;inspection=app.inspection;item,other=object(),object()
    case.assertIs(type(assets),AgentPoseAssets);case.assertIs(type(templates),AgentPoseTemplates);case.assertIs(api._agent_pose_templates,templates);case.assertIs(api._agent_pose_assets,assets);case.assertIs(assets.files,app.artifacts.files)
    for selected,name in ((assets._paths.suffixes,'IMAGE_REFERENCE_SUFFIXES'),(assets._sprites.version,'AGENT_MCP_SPRITE_BUILD_VERSION'),(assets._catalog.pose_tool,'AGENT_MCP_TOOL_POSE_IMAGE')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)
    for selected,target,method,args,kw,expected,expected_kw in ((assets._paths.resolve(),app.infrastructure._service_paths,'resolve_service_path',(item,),{},(item,),{'for_write':False}),(assets._material.text_assets(),inspection._text_asset_catalog,'canonical_text_assets',(item,),{},(item,),{}),(assets._material.text_complete(),inspection._text_asset_catalog,'canonical_text_assets_complete',(item,other),{},(item,other),{}),(assets._material.text_complete(),inspection._text_asset_catalog,'canonical_text_assets_complete',(item,),{},(item,None),{}),(assets._sprites.source_paths(),graph._photo_highlight_sources,'object_photo_highlight_source_paths',(item,),{},(item,),{'limit':app.values.PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES}),(assets._sprites.highlight_ready(),graph._photo_highlight_sources,'photo_highlight_clean_sprites_ready',(item,other),{},(item,other),{}),(assets._sprites.assets(),inspection._sprite_asset_catalog,'clean_sprite_assets',(item,),{},(item,),{}),(assets._sprites.complete(),inspection._sprite_asset_catalog,'clean_sprites_policy_complete',(item,other),{},(item,other),{}),(assets._calls.references(),assets,'agent_mcp_pose_reference_assets',(item,),{},(item,),{}),(assets._calls.rebuild(),assets,'agent_mcp_clean_sprites_need_rebuild',(item,),{},(item,),{}),(assets._catalog.lookup(),inspection._accessory_lookup,'accessory_lookup_by_id',(item,),{},(item,),{}),(assets._catalog.canonical_ids(),graph._pipeline_candidate_flow,'canonical_pipeline_accessory_ids',(item,other),{},(item,other),{}),(assets._catalog.has_asset(),assets,'agent_mcp_accessory_has_existing_or_pose_asset',(item,other),{},(item,other),{}),(templates._calls.request(),templates,'agent_mcp_pose_request',(),{},(),{})):
        assert_native_relay(case,selected,(target,method,args,kw,expected,expected_kw))
    case.assertIs(templates._identity.search(),wiring.re.search)
    for selected,target,name in ((assets._material.kind(),wiring._accessory_policy,'accessory_material_type'),(assets._catalog.uid(),wiring._accessory_policy,'accessory_uid'),(assets._sprites.family(),wiring,'_canonical_pose_family_name_impl'),(templates._identity.uid(),wiring._accessory_policy,'accessory_uid'),(templates._identity.kind(),wiring._accessory_policy,'accessory_material_type')):
        with patch.object(target,name,return_value=other) as receiver:case.assertIs(selected(item),other);receiver.assert_called_once_with(item)

    case.assertIs(templates._calls.request().__self__,graph._pose_planning_workflows);case.assertIs(templates._calls.request().__func__,type(graph._pose_planning_workflows).agent_mcp_pose_request)

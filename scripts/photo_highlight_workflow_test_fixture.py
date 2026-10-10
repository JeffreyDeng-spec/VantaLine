"""Finite photo task contracts with witnesses for the real default suppliers."""
from types import SimpleNamespace
from local_inspection_service.agent import photo_highlight_ports as ports
from local_inspection_service.agent.photo_highlight_sources import PhotoHighlightSources
from local_inspection_service.agent.photo_highlight_selection import PhotoHighlightSelection
from local_inspection_service.agent.photo_highlight_workflow import PhotoHighlightWorkflow
from local_inspection_service.storage.artifacts.files import BusinessFiles


class PhotoHighlightWorkflowContractFixture(SimpleNamespace):
    pass


GROUPS = (
    ('sources', '_media', ports.PhotoSourceMedia, {'resolve':'resolve_service_path', 'suffixes':'IMAGE_REFERENCE_SUFFIXES'}),
    ('sources', '_limits', ports.PhotoSpriteLimits, {'minimum':'PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES', 'version':'PHOTO_HIGHLIGHT_SPRITE_BUILD_VERSION'}),
    ('sources', '_sprites', ports.PhotoSpriteReadiness, {'assets':'clean_sprite_assets', 'complete':'clean_sprites_policy_complete'}),
    ('selection', '_selection', ports.PhotoObjectSelection, {'normalize':'normalize_pipeline_detection_method','training':'pipeline_method_uses_training','lookup':'accessory_lookup_by_id','canonical':'canonical_pipeline_accessory_ids','material':'accessory_material_type'}),
    ('photos', '_objects', ports.PhotoWorkflowObjects, {'items':'pipeline_photo_highlight_object_items','identifier':'accessory_uid','sources':'object_photo_highlight_source_paths','signature':'accessory_sprite_version'}),
    ('photos', '_limits', ports.PhotoSpriteLimits, {'minimum':'PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES', 'version':'PHOTO_HIGHLIGHT_SPRITE_BUILD_VERSION'}),
    ('photos', '_state', ports.PhotoWorkflowState, {'now':'agent_mcp_now','tool':'AGENT_MCP_TOOL_POSE_IMAGE','stage':'set_agent_mcp_stage','pause':'pause_agent_mcp_task','current':'agent_mcp_orchestration','photo_flow':'pipeline_uses_photo_highlight_sprite_flow','skip_legacy':'mark_legacy_pose_flow_skipped_for_photo_highlight','build_plan':'build_agent_mcp_pose_plan'}),
    ('photos', '_models', ports.PhotoWorkflowModels, {'configuration':'agent_mcp_gemini_image_config','settings':'image_generation_settings','provider':'image_generation_provider_from_settings','build_sprites':'build_clean_sprites_from_photo_highlight_masks'}),
)


def photo_highlight_workflow_fixture(server):
    assert_default_workflow(server)
    names = {name for _, _, _, bindings in GROUPS for name in bindings.values()}
    names.add('PHOTO_HIGHLIGHT_MAX_REFERENCE_IMAGES')
    api = PhotoHighlightWorkflowContractFixture(**{name:getattr(server,name) for name in names})
    def group(kind, bindings):
        return kind(**{field:(lambda name=name:getattr(api,name)) for field,name in bindings.items()})
    capabilities = [group(kind, bindings) for _, _, kind, bindings in GROUPS]
    sources = PhotoHighlightSources(*capabilities[:3], files=BusinessFiles(lambda:None))
    selection = PhotoHighlightSelection(capabilities[3])
    photos = PhotoHighlightWorkflow(*capabilities[4:])
    default_limit = server.object_photo_highlight_source_paths.__kwdefaults__['limit']
    def source_paths(item, *, limit=default_limit):
        return sources.object_photo_highlight_source_paths(item, limit=limit)
    api.object_photo_highlight_source_paths = source_paths
    api.photo_highlight_clean_sprites_ready = sources.photo_highlight_clean_sprites_ready
    api.pipeline_photo_highlight_object_items = selection.pipeline_photo_highlight_object_items
    api.pipeline_uses_photo_highlight_sprite_flow = lambda task,config:bool(api.pipeline_photo_highlight_object_items(task,config))
    for name in ('mark_legacy_pose_flow_skipped_for_photo_highlight','ensure_agent_mcp_pose_plan','prepare_photo_highlight_sprites_for_task'):
        setattr(api,name,getattr(photos,name))
    return api


def assert_default_workflow(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import training_pipeline
    from local_inspection_service.agent.pose_execution_composition import PoseExecutionWorkflows
    from local_inspection_service.agent.state_composition import AgentStateWorkflows
    from local_inspection_service.agent.planning_composition import PosePlanningWorkflows
    verify_actual_sources()
    case = unittest.TestCase()
    application = server._default_application
    graph = application.training_pipeline._photo_pose_workflows
    case.assertIs(type(graph), PoseExecutionWorkflows)
    case.assertIs(graph, application.training_pipeline._photo_pose_workflows)
    case.assertIs(server._photo_pose_workflows, graph)
    case.assertIs(graph.state, application.training_pipeline._agent_state_workflows)
    case.assertIs(server._agent_state_workflows, graph.state)
    case.assertIs(graph.planning, application.training_pipeline._pose_planning_workflows)
    case.assertIs(server._pose_planning_workflows, graph.planning)
    case.assertIs(type(graph.state), AgentStateWorkflows)
    case.assertIs(type(graph.planning), PosePlanningWorkflows)
    for owner, attribute, kind in ((graph.sources,'_photo_highlight_sources',PhotoHighlightSources),
                                    (graph.selection,'_photo_highlight_selection',PhotoHighlightSelection),
                                    (graph.photos,'_photo_highlight_workflow',PhotoHighlightWorkflow)):
        case.assertIs(type(owner),kind)
        case.assertIs(getattr(server,attribute),owner)
    case.assertIs(graph.sources.files,application.artifacts.files)
    item, other = object(), object()
    native = {
        'resolve_service_path':(application.infrastructure._service_paths,(item,),(item,),{'for_write':False}),
        'clean_sprite_assets':(application.inspection._sprite_asset_catalog,(item,),(item,),{}),
        'clean_sprites_policy_complete':(application.inspection._sprite_asset_catalog,(item,other),(item,other),{}),
        'normalize_pipeline_detection_method':(application.training_pipeline._pipeline_task_metadata,('training',),('training',),{}),
        'pipeline_method_uses_training':(application.training_pipeline._pipeline_task_metadata,('training',),('training',),{}),
        'accessory_lookup_by_id':(application.inspection._accessory_lookup,(item,),(item,),{}),
        'canonical_pipeline_accessory_ids':(application.training_pipeline._pipeline_candidate_flow,(item,other),(item,other),{}),
        'accessory_sprite_version':(application.training_pipeline._training_preview_cache,(item,),(item,),{}),
        'image_generation_settings':(application.infrastructure._model_profile_configuration,(),(),{}),
        'image_generation_provider_from_settings':(application.inspection._provider_selection,(item,),(item,),{}),
    }
    bound = {name:graph for name in ('pipeline_photo_highlight_object_items','object_photo_highlight_source_paths','pipeline_uses_photo_highlight_sprite_flow','mark_legacy_pose_flow_skipped_for_photo_highlight','build_clean_sprites_from_photo_highlight_masks')}
    bound.update({name:graph.state for name in ('agent_mcp_now','set_agent_mcp_stage','pause_agent_mcp_task','agent_mcp_orchestration','agent_mcp_gemini_image_config')})
    bound['build_agent_mcp_pose_plan']=graph.planning
    for owner_name, attribute, kind, bindings in GROUPS:
        port = getattr(getattr(graph,owner_name),attribute)
        case.assertIs(type(port),kind)
        for field,name in bindings.items():
            selected = getattr(port,field)()
            if name.isupper():
                case.assertIs(selected,getattr(application.values,name))
            elif name in bound:
                owner=bound[name]
                case.assertIs(selected.__self__,owner)
                case.assertIs(selected.__func__,getattr(type(owner),name))
            elif name in native:
                owner,args,forwarded,keywords=native[name]
                assert_native_relay(case,selected,(owner,name,args,{},forwarded,keywords))
            else:
                case.assertIn(name,('accessory_uid','accessory_material_type'))
                sentinel=object()
                with patch.object(training_pipeline._accessory_policy,name,return_value=sentinel) as callee:
                    case.assertIs(selected(item),sentinel)
                    callee.assert_called_once_with(item)
                    case.assertIs(callee.call_args.args[0],item)

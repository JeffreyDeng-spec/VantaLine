"""Test replacements select named actual Pose owners, never component aliases."""
from unittest.mock import patch
from scripts.provider_configuration_test_ports import provider_capability_target
OWNER_METHODS = {'_agent_state_workflows': ['agent_mcp_now', 'agent_mcp_gemini_image_config', 'agent_mcp_default_stages', 'agent_mcp_orchestration', 'set_agent_mcp_stage', 'agent_mcp_tool_call_id', 'upsert_agent_mcp_tool_call', 'pause_agent_mcp_task', 'log_agent_mcp_sample_tool_call', 'log_agent_mcp_training_tool_call', 'agent_mcp_training_quality_gate'], '_pose_planning_workflows': ['agent_mcp_object_kind', 'agent_mcp_pose_request', 'agent_mcp_pose_templates', 'accessory_pose_plan_prompt_payload', 'pose_plan_system_prompt', 'fallback_accessory_pose_plan', 'normalize_accessory_pose_plan', 'generate_accessory_pose_plan', 'ensure_accessory_pose_plan', 'build_agent_mcp_pose_plan'], '_photo_pose_workflows': ['agent_mcp_pose_reference_content', 'agent_mcp_pose_prompt', 'agent_mcp_pose_output_path', 'write_agent_mcp_pose_artifact', 'object_photo_highlight_source_paths', 'photo_highlight_clean_sprites_ready', 'pipeline_photo_highlight_object_items', 'mark_legacy_pose_flow_skipped_for_photo_highlight', 'photo_highlight_mask_prompt', 'photo_highlight_input_data_url', 'photo_highlight_auto_compare', 'build_clean_sprites_from_photo_highlight_masks', 'prepare_photo_highlight_sprites_for_task', 'execute_agent_mcp_pose_tool_calls', 'ensure_agent_mcp_pose_plan', 'ensure_agent_mcp_pose_tool_calls', 'prepare_agent_mcp_before_sample_generation', 'pipeline_uses_photo_highlight_sprite_flow']}

def pose_capability_target(api, name):
    for attribute, methods in OWNER_METHODS.items():
        if name in methods:
            owner = getattr(api, attribute, None)
            if owner is None:
                raise AssertionError("Actual Pose owner missing: " + attribute)
            return owner, name
    return provider_capability_target(api, name)

def patch_pose_capability(api, name, **kwargs):
    return patch.object(*pose_capability_target(api, name), **kwargs)

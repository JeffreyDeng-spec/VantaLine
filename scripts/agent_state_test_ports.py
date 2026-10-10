"""Replace only the Agent tool identifier port after checking its native owner."""
from dataclasses import replace
from unittest.mock import patch


def bind_state_identifier(api,stack):
    tools=api._default_application.training_pipeline._agent_state_workflows.tools
    stack.enter_context(patch.object(tools,'_identity',replace(tools._identity,sanitize=lambda:api.safe_record_id)))


def assert_default_state_identifier(api):
    import unittest
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.agent.state_composition import AgentStateWorkflows
    from local_inspection_service.agent.orchestration_state import AgentOrchestrationState
    from local_inspection_service.agent.tool_call_records import AgentToolCallRecords
    from local_inspection_service.agent.state_ports import AgentToolCallIdentity
    verify_actual_sources()
    case=unittest.TestCase();app=api._default_application
    workflows=app.training_pipeline._agent_state_workflows;tools=workflows.tools
    case.assertIs(type(workflows),AgentStateWorkflows);case.assertIs(api._agent_state_workflows,workflows)
    case.assertIs(type(workflows.state),AgentOrchestrationState);case.assertIs(type(tools),AgentToolCallRecords)
    case.assertIs(type(tools._identity),AgentToolCallIdentity)
    assert_native_relay(case,tools._identity.sanitize(),(app.inspection._pose_collection_jobs,'safe_record_id',('synthetic-id',),{},('synthetic-id',),{}))
    assert_native_relay(case,tools._identity.identifier(),(tools,'agent_mcp_tool_call_id',('task','tool'),{},('task','tool','',''),{}))
    assert_native_relay(case,api.agent_mcp_tool_call_id,(tools,'agent_mcp_tool_call_id',('task','tool'),{},('task','tool','',''),{}))
    assert_native_relay(case,api.agent_mcp_tool_call_id,(tools,'agent_mcp_tool_call_id',('task','tool','accessory','pose'),{},('task','tool','accessory','pose'),{}))
    for selected,name in ((tools._identity.samples,'AGENT_MCP_TOOL_SAMPLES'),(tools._identity.training,'AGENT_MCP_TOOL_TRAINING'),(workflows.state._runtime.version,'AGENT_MCP_ORCHESTRATION_VERSION')):
        original=getattr(app.values,name);case.assertIs(selected(),original);sentinel=object()
        try:
            object.__setattr__(app.values,name,sentinel);case.assertIs(selected(),sentinel)
        finally:object.__setattr__(app.values,name,original)

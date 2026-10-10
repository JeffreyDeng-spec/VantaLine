"""Replay only the immutable reviewed configuration/main integration delta.

Older domain contracts retain their complete original assembly assertions. The
new graph must match its fixed AST before any delta is reversed; unrelated or
unknown changes cannot be hidden by the replay.
"""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL_PHOTO_WORKFLOWS = json.loads((ROOT / "tests/backend_contract/real_photo_workflows_delta.json").read_text())
PROVIDER_TRANSPORTS = json.loads((ROOT / "tests/backend_contract/provider_transports_delta.json").read_text())
ACCOUNT_VISIBILITY = json.loads((ROOT / "tests/backend_contract/account_visibility_delta.json").read_text())
TRAINING_PERSISTENCE_GRAPH = json.loads((ROOT / "tests/backend_contract/training_persistence_graph_delta.json").read_text())
INFRASTRUCTURE = json.loads((ROOT / "tests/backend_contract/infrastructure_composition_delta.json").read_text())
PATH_CONFIGURATION = json.loads((ROOT / "tests/backend_contract/path_configuration_composition_delta.json").read_text())
FIXTURE = json.loads((ROOT / "tests/backend_contract/application_integration_delta.json").read_text())
BUSINESS = json.loads((ROOT / "tests/backend_contract/application_business_delta.json").read_text())
MAIN_FEEDBACK = json.loads((ROOT / "tests/backend_contract/application_main_feedback_delta.json").read_text())
CODEX_ENVIRONMENT = json.loads((ROOT / "tests/backend_contract/codex_environment_delta.json").read_text())
PIPELINE_RUNTIME = json.loads((ROOT / "tests/backend_contract/pipeline_runtime_composition_delta.json").read_text())
PIPELINE_TASKS = json.loads((ROOT / "tests/backend_contract/pipeline_task_composition_delta.json").read_text())
PIPELINE_STAGES = json.loads((ROOT / "tests/backend_contract/pipeline_stage_composition_delta.json").read_text())
AGENT_PIPELINE = json.loads((ROOT / "tests/backend_contract/agent_pipeline_composition_delta.json").read_text())
PIPELINE_QUERIES = json.loads((ROOT / "tests/backend_contract/pipeline_query_composition_delta.json").read_text())
PIPELINE_EXECUTION = json.loads((ROOT / "tests/backend_contract/pipeline_execution_composition_delta.json").read_text())
PIPELINE_PERSISTENCE = json.loads((ROOT / "tests/backend_contract/pipeline_persistence_composition_delta.json").read_text())
PLC_CAPTURE = json.loads((ROOT / "tests/backend_contract/plc_capture_composition_delta.json").read_text())
PLC_OPERATIONS = json.loads((ROOT / "tests/backend_contract/plc_lease_diagnostic_composition_delta.json").read_text())
PLC_WORKSTATION = json.loads((ROOT / "tests/backend_contract/plc_workstation_composition_delta.json").read_text())
AGENT_STATE = json.loads((ROOT / "tests/backend_contract/agent_state_composition_delta.json").read_text())
POSE_PLANNING = json.loads((ROOT / "tests/backend_contract/pose_planning_composition_delta.json").read_text())
POSE_EXECUTION = json.loads((ROOT / "tests/backend_contract/pose_execution_composition_delta.json").read_text())
COMPOSITIONS = json.loads((ROOT / "tests/backend_contract/application_composition_bindings.json").read_text())
MAIN283_PLC = json.loads((ROOT / "tests/backend_contract/main283_plc_integration_delta.json").read_text())


def canonical(node):
    if isinstance(node, ast.AST):
        return [type(node).__name__, [[name, canonical(value)] for name, value in ast.iter_fields(node)
                                    if name != "type_params"]]
    if isinstance(node, list):
        return [canonical(value) for value in node]
    if node is Ellipsis:
        return ["constant", "Ellipsis"]
    if isinstance(node, (bytes, complex)):
        return ["constant", repr(node)]
    return node


def digest(node):
    return hashlib.sha256(json.dumps(canonical(node), ensure_ascii=False).encode()).hexdigest()


def restore_delta(source, fixture):
    tree = ast.parse(source)
    if digest(tree) == fixture["parent_ast_sha256"]:
        return source
    assert digest(tree) == fixture["integrated_ast_sha256"], "Unreviewed integrated root or routing change"
    for region in reversed(fixture["regions"]):
        actual = tree.body[region["start"]:region["end"]]
        expected = [ast.parse(code).body[0] for code in region["expected"]]
        assert canonical(actual) == canonical(expected), region["start"]
        tree.body[region["start"]:region["end"]] = [ast.parse(code).body[0] for code in region["original"]]
    assert digest(tree) == fixture["parent_ast_sha256"], "Integrated inverse does not match accepted parent"
    return ast.unparse(tree)


def verify_actual_compositions():
    assert MAIN283_PLC["schema"] == 1, "Unknown PLC integration schema"
    assert MAIN283_PLC["upstream_sha"] == "8195c96970c1e41582d4796fe2b23508ea9f837a", "Unreviewed PLC upstream"
    assert MAIN283_PLC["previous_candidate"] == "9b9ca73c6f6d657ab3427409fc9be1835801daea", "Unreviewed PLC parent"
    main_sources = {
        "local_inspection_service/plc/station_service.py": "cd2e99d2c4d7a2d2716fa7ac7e87525317333c43a35bd65bfb70fa13412fe79f",
        "local_inspection_service/plc/lease_acquisition.py": "6f7370ff1fa46acd18108b804be697939eb3d0e0719855e3c04582ca3379393e",
        "local_inspection_service/plc/lease_maintenance.py": "24597c67e4a4a4109b266e7895dc7513714ada7d3e946e45a4f3e4fb951f93ed",
    }
    assert set(MAIN283_PLC["business_sources"]) == set(main_sources), "PLC integration source inventory changed"
    for path, expected in main_sources.items():
        assert MAIN283_PLC["business_sources"][path]["main_sha256"] == expected, "PLC upstream source changed: " + path
        actual_expected = ("a4b8e046f355e9a310bf46507da9f65a18146ee5af9d91f957723fcae4c4ac4c"
                           if path.endswith("/station_service.py") else expected)
        assert MAIN283_PLC["business_sources"][path]["actual_sha256"] == actual_expected, "Unreviewed PLC integration source: " + path
    assert digest(ast.parse((ROOT / "local_inspection_service/runtime/path_configuration_composition.py").read_text())) == PATH_CONFIGURATION["actual_owner_ast_sha256"], "Actual path/configuration composition changed"
    for path, expected in PATH_CONFIGURATION["unchanged_business_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == expected, path
    """Validate real owned constructor edges before using an old-location oracle."""
    assert digest(ast.parse((ROOT / "local_inspection_service/agent/state_composition.py").read_text())) == AGENT_STATE["actual_owner_ast_sha256"], "Actual Agent state composition changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/agent/planning_composition.py").read_text())) == POSE_PLANNING["actual_owner_ast_sha256"], "Actual Pose planning composition changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/agent/pose_execution_composition.py").read_text())) == POSE_EXECUTION["actual_owner_ast_sha256"], "Actual Pose execution composition changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/training/dispatcher_runtime.py").read_text())) == MAIN_FEEDBACK["dispatcher_runtime_ast_sha256"], "Actual dispatcher runtime changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/plc/workstation_composition.py").read_text())) == PLC_WORKSTATION["actual_owner_ast_sha256"], "Actual PLC workstation composition changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/codex_compare/api.py").read_text())) == CODEX_ENVIRONMENT["actual_owner_ast_sha256"], "Actual Codex environment binding changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/codex_compare/worker.py").read_text())) == CODEX_ENVIRONMENT["actual_worker_ast_sha256"], "Actual Codex worker environment binding changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/pipeline/runtime_composition.py").read_text())) == PIPELINE_RUNTIME["actual_owner_ast_sha256"], "Actual pipeline runtime composition changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/pipeline/task_composition.py").read_text())) == PIPELINE_TASKS["actual_owner_ast_sha256"], "Actual pipeline task composition changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/pipeline/stage_composition.py").read_text())) == PIPELINE_STAGES["actual_owner_ast_sha256"], "Actual pipeline stage composition changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/agent/pipeline_composition.py").read_text())) == AGENT_PIPELINE["actual_owner_ast_sha256"], "Actual Agent pipeline composition changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/pipeline/query_composition.py").read_text())) == PIPELINE_QUERIES["actual_owner_ast_sha256"], "Actual pipeline query composition changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/pipeline/execution_composition.py").read_text())) == PIPELINE_EXECUTION["actual_owner_ast_sha256"], "Actual pipeline execution composition changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/pipeline/persistence_composition.py").read_text())) == PIPELINE_PERSISTENCE["actual_owner_ast_sha256"], "Actual pipeline persistence composition changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/plc/capture_composition.py").read_text())) == PLC_CAPTURE["actual_owner_ast_sha256"], "Actual PLC capture composition changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/plc/lease_diagnostic_composition.py").read_text())) == PLC_OPERATIONS["actual_owner_ast_sha256"], "Actual PLC lease/diagnostic composition changed"
    for path, expected in {**AGENT_STATE["unchanged_business_sha256"], **POSE_PLANNING["unchanged_business_sha256"], **POSE_EXECUTION["unchanged_business_sha256"], **PLC_WORKSTATION["unchanged_business_sha256"], **PLC_OPERATIONS["unchanged_business_sha256"], **PLC_CAPTURE["unchanged_business_sha256"], **PIPELINE_PERSISTENCE["unchanged_business_sha256"], **PIPELINE_EXECUTION["unchanged_business_sha256"], **PIPELINE_QUERIES["unchanged_business_sha256"], **AGENT_PIPELINE["unchanged_business_sha256"], **PIPELINE_STAGES["unchanged_business_sha256"], **PIPELINE_TASKS["unchanged_business_sha256"], **PIPELINE_RUNTIME["unchanged_business_sha256"], **CODEX_ENVIRONMENT["unchanged_business_sha256"]}.items():
        if path in MAIN283_PLC["business_sources"]:
            accepted = MAIN283_PLC["business_sources"][path]
            assert expected == accepted["previous_sha256"], "Historical PLC baseline changed: " + path
            expected = accepted["actual_sha256"]
        actual = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(actual).hexdigest() == expected, "PLC business changed with assembly: " + path
    for path, expected in COMPOSITIONS["canonical_ast_sha256"].items():
        assert digest(ast.parse((ROOT / path).read_text(encoding="utf-8"))) == expected, \
            "Actual composition capability changed: " + path


def restore_integrated_root(source):
    from application_configuration_source_contract import restore_application_configuration_root
    return restore_delta(restore_delta(restore_application_configuration_root(restore_plc_domain_root(source)), MAIN_FEEDBACK), FIXTURE)


def restore_business_root(source):
    from application_configuration_source_contract import restore_application_configuration_root
    return restore_delta(restore_delta(restore_delta(restore_application_configuration_root(restore_plc_domain_root(source)), MAIN_FEEDBACK), FIXTURE), BUSINESS)


def restore_plc_domain_root(source):
    """Validate actual builders before the frozen unchanged business oracles."""
    verify_actual_compositions()
    source = restore_path_configuration_root(source)
    fixtures = (POSE_EXECUTION, POSE_PLANNING, AGENT_STATE, CODEX_ENVIRONMENT, PIPELINE_RUNTIME, PIPELINE_TASKS, PIPELINE_STAGES,
                AGENT_PIPELINE, PIPELINE_QUERIES, PIPELINE_EXECUTION,
                PIPELINE_PERSISTENCE, PLC_CAPTURE, PLC_OPERATIONS, PLC_WORKSTATION)
    for index, fixture in enumerate(fixtures):
        # Some unchanged historical oracles already replayed several outer
        # deltas. Only exact immutable descendants may skip those deltas.
        remaining = fixtures[index + 1:]
        accepted_descendants = {item[key] for item in remaining
                                for key in ("integrated_ast_sha256", "parent_ast_sha256")}
        if digest(ast.parse(source)) in accepted_descendants:
            continue
        source = restore_delta(source, fixture)
    assert digest(ast.parse(source)) == PLC_WORKSTATION["parent_ast_sha256"]
    return source


def restore_pose_domain_root(source):
    """Check real Pose owners and fold only the three immutable outer deltas."""
    verify_actual_compositions()
    source = restore_path_configuration_root(source)
    fixtures = (POSE_EXECUTION, POSE_PLANNING, AGENT_STATE)
    older = (CODEX_ENVIRONMENT, PIPELINE_RUNTIME, PIPELINE_TASKS, PIPELINE_STAGES,
             AGENT_PIPELINE, PIPELINE_QUERIES, PIPELINE_EXECUTION,
             PIPELINE_PERSISTENCE, PLC_CAPTURE, PLC_OPERATIONS, PLC_WORKSTATION)
    for index, fixture in enumerate(fixtures):
        accepted = {item[key] for item in (*fixtures[index + 1:], *older)
                    for key in ("integrated_ast_sha256", "parent_ast_sha256")}
        if digest(ast.parse(source)) in accepted:
            continue
        source = restore_delta(source, fixture)
    assert digest(ast.parse(source)) in {item[key] for item in older
                                        for key in ("integrated_ast_sha256", "parent_ast_sha256")}
    return source


MAIN284_REAL_PHOTO = json.loads((ROOT / "tests/backend_contract/main284_real_photo_integration_delta.json").read_text())
MAIN288_REAL_PHOTO = json.loads((ROOT / "tests/backend_contract/main288_real_photo_integration_delta.json").read_text())


def verify_main284_real_photo_sources():
    assert MAIN284_REAL_PHOTO["schema"] == 1, "Unknown real-photo integration schema"
    assert MAIN284_REAL_PHOTO["upstream_sha"] == "e1c7be97b04c0f172a82baad495ecbda88a6481f", "Unreviewed real-photo upstream"
    assert MAIN284_REAL_PHOTO["previous_candidate"] == "9d174642c90aed1b681148a460b1137061b9c7d1", "Unreviewed real-photo parent"
    assert MAIN284_REAL_PHOTO["business_sources"] == {
        "local_inspection_service/training/real_photo_api.py": {
            "previous_sha256": "c8833921d53186366de59fa97e635f5d741a1636c42edc29b4498e3ed26ce6ab",
            "main_sha256": "6afcb92bca9e67606f48c1d30b63c61cd4a3510a5b9bf951d4aaffe14b6a8496",
            "actual_sha256": "6afcb92bca9e67606f48c1d30b63c61cd4a3510a5b9bf951d4aaffe14b6a8496",
        }
    }, "Unreviewed real-photo integration source"


def verify_main288_real_photo_sources():
    assert MAIN288_REAL_PHOTO["schema"] == 1, "Unknown paused-source integration schema"
    assert MAIN288_REAL_PHOTO["upstream_sha"] == "cd57cc7c38d10c37ddf8710bca45303c9ebe22f6", "Unreviewed paused-source upstream"
    assert MAIN288_REAL_PHOTO["previous_candidate"] == "7ddc2c13a6fa02ac62e85efb9be5465ac462841c", "Unreviewed paused-source parent"
    assert MAIN288_REAL_PHOTO["business_sources"] == {
        "local_inspection_service/training/real_photo_api.py": {
            "previous_sha256": "6afcb92bca9e67606f48c1d30b63c61cd4a3510a5b9bf951d4aaffe14b6a8496",
            "main_sha256": "f2807775c14ade2bfa29ed3fbd3e12ed51fd4246bb3069bf7bedbe87da408790",
            "actual_sha256": "f2807775c14ade2bfa29ed3fbd3e12ed51fd4246bb3069bf7bedbe87da408790",
        }
    }, "Unreviewed paused-source integration source"


def restore_real_photo_workflows_root(source):
    """Validate the actual feedback bridge and replay only its reviewed delta."""
    from canonical_application_source_contract import restore_canonical_root
    source = restore_canonical_root(source)
    fixture = REAL_PHOTO_WORKFLOWS
    verify_main284_real_photo_sources()
    verify_main288_real_photo_sources()
    for path, expected in fixture["actual_owner_ast_sha256"].items():
        assert digest(ast.parse((ROOT / path).read_text())) == expected, path
    for path, expected in fixture["unchanged_business_sha256"].items():
        if path in MAIN284_REAL_PHOTO["business_sources"]:
            accepted = MAIN284_REAL_PHOTO["business_sources"][path]
            assert expected == accepted["previous_sha256"], "Historical real-photo baseline changed: " + path
            expected = accepted["actual_sha256"]
        if path in MAIN288_REAL_PHOTO["business_sources"]:
            accepted = MAIN288_REAL_PHOTO["business_sources"][path]
            assert expected == accepted["previous_sha256"], "Historical main284 source changed: " + path
            expected = accepted["actual_sha256"]
        assert hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == expected, path
    if digest(ast.parse(source)) == fixture["integrated_ast_sha256"]:
        return restore_delta(source, fixture)
    return source


def restore_provider_transports_root(source):
    """Check actual app-owned provider types before folding their fixed delta."""
    source = restore_real_photo_workflows_root(source)
    fixture = PROVIDER_TRANSPORTS
    for path, expected in fixture["actual_owner_ast_sha256"].items():
        assert digest(ast.parse((ROOT / path).read_text())) == expected, path
    for path, expected in fixture["unchanged_business_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == expected, path
    if digest(ast.parse(source)) == fixture["integrated_ast_sha256"]:
        return restore_delta(source, fixture)
    return source


def restore_account_visibility_root(source):
    """Verify the real visibility graph before replaying its fixed entry delta."""
    source = restore_provider_transports_root(source)
    fixture = ACCOUNT_VISIBILITY
    for path, expected in fixture["actual_owner_ast_sha256"].items():
        assert digest(ast.parse((ROOT / path).read_text())) == expected, path
    for path, expected in fixture["unchanged_business_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == expected, path
    if digest(ast.parse(source)) == fixture["integrated_ast_sha256"]:
        return restore_delta(source, fixture)
    return source


def restore_training_persistence_graph_root(source):
    """Verify actual completion owners before folding this fixed entry delta."""
    source = restore_account_visibility_root(source)
    fixture = TRAINING_PERSISTENCE_GRAPH
    for path, expected in fixture["actual_owner_ast_sha256"].items():
        assert digest(ast.parse((ROOT / path).read_text())) == expected, path
    for path, expected in fixture["unchanged_business_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == expected, path
    if digest(ast.parse(source)) == fixture["integrated_ast_sha256"]:
        return restore_delta(source, fixture)
    return source


def restore_infrastructure_root(source):
    """Validate real infrastructure edges, then fold only a fixed entry delta."""
    source = restore_training_persistence_graph_root(source)
    for path, expected in INFRASTRUCTURE["actual_owner_ast_sha256"].items():
        assert digest(ast.parse((ROOT / path).read_text())) == expected, path
    for path, expected in INFRASTRUCTURE["unchanged_business_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == expected, path
    actual = digest(ast.parse(source))
    if actual == INFRASTRUCTURE["integrated_ast_sha256"]:
        return restore_delta(source, INFRASTRUCTURE)
    earlier = (INFRASTRUCTURE, PATH_CONFIGURATION, POSE_EXECUTION, POSE_PLANNING, AGENT_STATE,
               CODEX_ENVIRONMENT, PIPELINE_RUNTIME, PIPELINE_TASKS, PIPELINE_STAGES,
               AGENT_PIPELINE, PIPELINE_QUERIES, PIPELINE_EXECUTION,
               PIPELINE_PERSISTENCE, PLC_CAPTURE, PLC_OPERATIONS, PLC_WORKSTATION,
               FIXTURE, BUSINESS, MAIN_FEEDBACK)
    assert actual in {item[key] for item in earlier for key in
                      ("parent_ast_sha256", "integrated_ast_sha256")}, "Unreviewed infrastructure root"
    return source


def restore_path_configuration_root(source):
    """Validate the actual closed graph before preserving older strict oracles."""
    source = restore_infrastructure_root(source)
    assert digest(ast.parse((ROOT / "local_inspection_service/runtime/path_configuration_composition.py").read_text())) == PATH_CONFIGURATION["actual_owner_ast_sha256"]
    for path, expected in PATH_CONFIGURATION["unchanged_business_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == expected, path
    actual = digest(ast.parse(source))
    if actual == PATH_CONFIGURATION["integrated_ast_sha256"]:
        return restore_delta(source, PATH_CONFIGURATION)
    earlier = (PATH_CONFIGURATION, POSE_EXECUTION, POSE_PLANNING, AGENT_STATE,
               CODEX_ENVIRONMENT, PIPELINE_RUNTIME, PIPELINE_TASKS, PIPELINE_STAGES,
               AGENT_PIPELINE, PIPELINE_QUERIES, PIPELINE_EXECUTION,
               PIPELINE_PERSISTENCE, PLC_CAPTURE, PLC_OPERATIONS, PLC_WORKSTATION,
               FIXTURE, BUSINESS, MAIN_FEEDBACK)
    assert actual in {item[key] for item in earlier for key in
                      ("parent_ast_sha256", "integrated_ast_sha256")}, "Unreviewed path/configuration root"
    return source

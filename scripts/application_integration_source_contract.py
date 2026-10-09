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
FIXTURE = json.loads((ROOT / "tests/backend_contract/application_integration_delta.json").read_text())
BUSINESS = json.loads((ROOT / "tests/backend_contract/application_business_delta.json").read_text())
MAIN_FEEDBACK = json.loads((ROOT / "tests/backend_contract/application_main_feedback_delta.json").read_text())
PIPELINE_PERSISTENCE = json.loads((ROOT / "tests/backend_contract/pipeline_persistence_composition_delta.json").read_text())
PLC_CAPTURE = json.loads((ROOT / "tests/backend_contract/plc_capture_composition_delta.json").read_text())
PLC_OPERATIONS = json.loads((ROOT / "tests/backend_contract/plc_lease_diagnostic_composition_delta.json").read_text())
PLC_WORKSTATION = json.loads((ROOT / "tests/backend_contract/plc_workstation_composition_delta.json").read_text())
COMPOSITIONS = json.loads((ROOT / "tests/backend_contract/application_composition_bindings.json").read_text())


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
    """Validate real owned constructor edges before using an old-location oracle."""
    assert digest(ast.parse((ROOT / "local_inspection_service/training/dispatcher_runtime.py").read_text())) == MAIN_FEEDBACK["dispatcher_runtime_ast_sha256"], "Actual dispatcher runtime changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/plc/workstation_composition.py").read_text())) == PLC_WORKSTATION["actual_owner_ast_sha256"], "Actual PLC workstation composition changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/pipeline/persistence_composition.py").read_text())) == PIPELINE_PERSISTENCE["actual_owner_ast_sha256"], "Actual pipeline persistence composition changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/plc/capture_composition.py").read_text())) == PLC_CAPTURE["actual_owner_ast_sha256"], "Actual PLC capture composition changed"
    assert digest(ast.parse((ROOT / "local_inspection_service/plc/lease_diagnostic_composition.py").read_text())) == PLC_OPERATIONS["actual_owner_ast_sha256"], "Actual PLC lease/diagnostic composition changed"
    for path, expected in {**PLC_WORKSTATION["unchanged_business_sha256"], **PLC_OPERATIONS["unchanged_business_sha256"], **PLC_CAPTURE["unchanged_business_sha256"], **PIPELINE_PERSISTENCE["unchanged_business_sha256"]}.items():
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
    return restore_delta(restore_delta(restore_delta(restore_delta(source, PIPELINE_PERSISTENCE), PLC_CAPTURE), PLC_OPERATIONS), PLC_WORKSTATION)

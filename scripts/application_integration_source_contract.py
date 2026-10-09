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
    for path, expected in COMPOSITIONS["canonical_ast_sha256"].items():
        assert digest(ast.parse((ROOT / path).read_text(encoding="utf-8"))) == expected, \
            "Actual composition capability changed: " + path


def restore_integrated_root(source):
    verify_actual_compositions()
    from application_configuration_source_contract import restore_application_configuration_root
    return restore_delta(restore_delta(restore_application_configuration_root(source), MAIN_FEEDBACK), FIXTURE)


def restore_business_root(source):
    verify_actual_compositions()
    from application_configuration_source_contract import restore_application_configuration_root
    return restore_delta(restore_delta(restore_delta(restore_application_configuration_root(source), MAIN_FEEDBACK), FIXTURE), BUSINESS)

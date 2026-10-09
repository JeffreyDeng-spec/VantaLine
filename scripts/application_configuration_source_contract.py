"""Verify the owned configuration increment before replaying older contracts."""
import ast
from collections import Counter
import json
from pathlib import Path
from application_integration_source_contract import digest, canonical

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/backend_contract/application_configuration_ports.json").read_text())


def node_key(node):
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.ImportFrom):
        return "import:" + str(node.module)
    return None


def restore_application_configuration_root(source):
    assert digest(ast.parse((ROOT / "local_inspection_service/config/application_composition.py").read_text())) == FIXTURE["composition_ast_sha256"], "Actual configuration constructor changed"
    tree = ast.parse(source)
    if not any(node_key(node) == "_app_configuration" for node in tree.body):
        return source
    restored, seen = [], Counter()
    for node in tree.body:
        key = node_key(node)
        expected = FIXTURE["extras"].get(key)
        if expected is not None:
            assert canonical(node) == canonical(ast.parse(expected).body[0]), key
            seen[key] += 1
            continue
        change = FIXTURE["changes"].get(key)
        if change is not None:
            assert canonical(node) == canonical(ast.parse(change["expected"]).body[0]), key
            seen[key] += 1
            restored.append(ast.parse(change["original"]).body[0])
        else:
            restored.append(node)
    assert all(seen[key] == 1 for key in (*FIXTURE["extras"], *FIXTURE["changes"])), seen
    for item in sorted(FIXTURE["removed"], key=lambda item: item["index"]):
        restored.insert(item["index"], ast.parse(item["original"]).body[0])
    tree = ast.Module(body=restored, type_ignores=[])
    assert digest(tree) == FIXTURE["parent_ast_sha256"], \
        "Unrelated root, routing or lifetime changed"
    return ast.unparse(tree)

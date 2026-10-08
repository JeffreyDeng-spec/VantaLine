"""Restore the task-domain assembly to its immutable parent for older contracts."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'tests/backend_contract/training_task_workflows_ports.json').read_text())


def canonical_ast(node):
    if isinstance(node, ast.AST):
        return [type(node).__name__, [[name, canonical_ast(value)] for name, value in ast.iter_fields(node) if name != 'type_params']]
    if isinstance(node, list):
        return [canonical_ast(value) for value in node]
    if node is Ellipsis:
        return ['constant', 'Ellipsis']
    if isinstance(node, (bytes, complex)):
        return ['constant', repr(node)]
    return node


def ast_sha256(node):
    return hashlib.sha256(json.dumps(canonical_ast(node), ensure_ascii=False).encode()).hexdigest()


def restore_training_task_root(source):
    tree = ast.parse(source)
    imports = [ast.unparse(node) for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert imports == FIXTURE['expected_imports'], 'Task-domain imports or bindings changed'
    extra = Counter(FIXTURE['extra_imports'])
    seen = Counter()
    restored = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            text = ast.unparse(node)
            if extra[text]:
                extra[text] -= 1
                continue
            restored.append(node)
            continue
        name = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        if name in FIXTURE['owners']:
            seen[name] += 1
            assert canonical_ast(node) == canonical_ast(ast.parse(FIXTURE['owners'][name]).body[0]), name
            continue
        if name in FIXTURE['changes']:
            seen[name] += 1
            change = FIXTURE['changes'][name]
            assert canonical_ast(node) == canonical_ast(ast.parse(change['expected']).body[0]), name
            restored.append(ast.parse(change['original']).body[0])
            continue
        restored.append(node)
    assert not any(extra.values()), 'Missing task-domain imports'
    assert all(seen[name] == 1 for name in (*FIXTURE['owners'], *FIXTURE['changes'])), seen
    nonimports = ast.Module(body=[node for node in restored if not isinstance(node, (ast.Import, ast.ImportFrom))], type_ignores=[])
    assert ast_sha256(nonimports) == FIXTURE['parent_nonimport_ast_sha256'], 'Unrelated root code, route order or shutdown changed'
    return ast.unparse(ast.Module(body=restored, type_ignores=[]))


def verify_training_task_sources():
    restore_training_task_root((ROOT / 'local_inspection_service/server.py').read_text())
    for name, digest in FIXTURE['business_sha256'].items():
        data = (ROOT / 'local_inspection_service/training' / name).read_bytes().replace(b'\r\n', b'\n')
        assert hashlib.sha256(data).hexdigest() == digest, name
    for name, digest in FIXTURE['composition_ast_sha256'].items():
        assert ast_sha256(ast.parse((ROOT / 'local_inspection_service/training' / name).read_text())) == digest, name

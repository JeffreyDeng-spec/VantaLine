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
    # Import-shadow counterexamples need no unrelated domain replay. Retain the
    # complete original import/order/owner/digest checks for valid source below.
    expected_imports=[node for text in FIXTURE['expected_imports'] for node in ast.parse(text).body]
    protected=set(FIXTURE['owners']) | set(FIXTURE['changes']) | {
        alias.asname or alias.name for text in FIXTURE['extra_imports']
        for node in ast.parse(text).body for alias in node.names}
    allowed={(node.module,node.level,alias.name,alias.asname)
             for node in expected_imports if isinstance(node,ast.ImportFrom)
             for alias in node.names if (alias.asname or alias.name) in protected}
    tree=ast.parse(source)
    facade=any(isinstance(node,ast.ImportFrom) and node.module=='runtime.default_application'
               and any(alias.asname=='_default_application' for alias in node.names) for node in tree.body)
    assignments={node.targets[0].id:node for node in tree.body if isinstance(node,ast.Assign)
                 and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)}
    owner=assignments.get('_training_task_workflows')
    if not facade and owner is not None and isinstance(owner.value,ast.Call) and isinstance(owner.value.func,ast.Name) and owner.value.func.id=='TrainingTaskWorkflows':
        expected=ast.parse(FIXTURE['owners']['_training_task_workflows']).body[0].value
        accounts=[part.value for part in owner.value.keywords if part.arg=='account']
        assert len(accounts)==1, 'Task account binding changed'
        account=accounts[0]
        expected_account=next(part.value for part in expected.keywords if part.arg=='account')
        assert canonical_ast(account)==canonical_ast(expected_account), 'Task account owner changed'
        for name in ('_training_task_runtime','_training_transfer'):
            expected_binding=ast.parse(FIXTURE['changes'][name]['expected']).body[0]
            assert canonical_ast(assignments.get(name))==canonical_ast(expected_binding), 'Task alias changed: '+name
    for node in (() if facade else tree.body):
        if isinstance(node,(ast.Import,ast.ImportFrom)):
            for alias in node.names:
                if (alias.asname or alias.name) in protected:
                    assert isinstance(node,ast.ImportFrom)
                    assert (node.module,node.level,alias.name,alias.asname) in allowed, 'Task-domain import shadow'
    from application_integration_source_contract import restore_integrated_root
    source = restore_integrated_root(source)
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

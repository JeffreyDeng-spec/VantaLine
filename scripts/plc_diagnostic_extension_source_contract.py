"""Exact additive diagnostic registration; preserve the canonical parent oracle."""
import ast
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FIXTURE=json.loads((ROOT/'tests/backend_contract/plc_diagnostic_extension.json').read_text())
HTTP='local_inspection_service/runtime/wiring/http_registration.py'
def digest(source):return hashlib.sha256(ast.dump(ast.parse(source),include_attributes=False).encode()).hexdigest()
def diagnostic_parent_source(source):
    assert digest(source)==FIXTURE[HTTP], 'Unknown diagnostic HTTP extension'
    for path,expected in FIXTURE.items():
        from plc_modbus_source_contract import restore_modbus_business
        assert digest(restore_modbus_business(path, (ROOT/path).read_bytes()).decode())==expected, 'Diagnostic owner changed: '+path
    tree=ast.parse(source);removed_import=0;removed_call=0
    for node in list(tree.body):
        if isinstance(node,ast.ImportFrom) and node.module=='local_inspection_service.plc.diagnostic_events_api':
            assert [(a.name,a.asname) for a in node.names]==[('register_diagnostic_events',None)]
            tree.body.remove(node);removed_import+=1
    for node in tree.body:
        if isinstance(node,ast.FunctionDef) and node.name=='register_http':
            for item in list(node.body):
                if isinstance(item,ast.Expr) and isinstance(item.value,ast.Call) and isinstance(item.value.func,ast.Name) and item.value.func.id=='register_diagnostic_events':
                    node.body.remove(item);removed_call+=1
    assert (removed_import,removed_call)==(1,1)
    return ast.unparse(tree)

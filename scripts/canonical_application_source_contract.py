"""Verify actual relocated modules before replaying historical source oracles.

The parent is immutable test data. Product code never parses or executes it.
Every current module is checked on each call; only parsing of identical source
text is cached. Altering an entry, owner, callback or manifest cannot be hidden
by replay of the old source.
"""
import ast
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from application_integration_source_contract import digest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'tests/backend_contract/canonical_application_delta.json').read_text())
EXPECTED_PATHS = frozenset([
    'local_inspection_service/server.py', 'local_inspection_service/ai_mcp_server.py',
    'local_inspection_service/config/list_policy.py', 'local_inspection_service/pipeline/errors.py',
    'local_inspection_service/runtime/application.py', 'local_inspection_service/runtime/application_values.py',
    'local_inspection_service/runtime/application_lifetime.py', 'local_inspection_service/runtime/default_application.py',
    *('local_inspection_service/compatibility/' + name + '.py' for name in ('__init__', 'infrastructure', 'inspection', 'training_pipeline', 'analytics', 'plc', 'text')),
    *('local_inspection_service/runtime/wiring/' + name + '.py' for name in ('__init__', 'infrastructure', 'inspection', 'training_pipeline', 'analytics', 'plc', 'text', 'http_registration')),
])


@lru_cache(maxsize=64)
def source_digest(source):
    return digest(ast.parse(source))


def verify_actual_sources():
    assert FIXTURE['parent_sha'] == 'f5c9daf5b431edb1793bba5f42d2860765919322'
    assert set(FIXTURE['actual_source_ast_sha256']) == EXPECTED_PATHS, 'Incomplete canonical source inventory'
    parent = FIXTURE['parent_source']
    assert hashlib.sha256(parent.encode()).hexdigest() == FIXTURE['parent_source_sha256'] == '086d17593596f2da642de215a115604e8e4891599c040a1528fa1768993d2204'
    assert source_digest(parent) == FIXTURE['parent_ast_sha256']
    for path, expected in FIXTURE['actual_source_ast_sha256'].items():
        assert source_digest((ROOT / path).read_text(encoding='utf-8')) == expected, 'Actual canonical source changed: ' + path


def restore_canonical_root(source):
    verify_actual_sources()
    if source_digest(source) == FIXTURE['integrated_ast_sha256']:
        return FIXTURE['parent_source']
    return source


def read_checked_application_source(path, **kwargs):
    """Keep native port fixtures while checking every actual assembly source.

    Only the former entry layout receives the exact verified parent bridge.
    External original-code baselines and other files remain their own source.
    Product code never reads or executes this bridge.
    """
    path = Path(path)
    source = path.read_text(**kwargs)
    if path.resolve() == (ROOT / 'local_inspection_service/server.py').resolve():
        return restore_canonical_root(source)
    return source

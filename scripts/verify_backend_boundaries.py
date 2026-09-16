"""Enforce dependency direction for modules admitted to the extraction boundary.

Expand PACKAGES in each domain extraction PR. Legacy modules are not silently
declared compliant merely because they have not been migrated yet.
"""
import ast
from importlib.util import resolve_name
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = 'local_inspection_service'
PACKAGES = ('model_profiles', 'runtime')


def inspect_module(source, module, is_package=False):
    tree = ast.parse(source)
    imports, errors = set(), []
    package = module if is_package else module.rsplit('.', 1)[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            target = resolve_name('.' * node.level + (node.module or ''), package) if node.level else node.module
            if target != module:
                imports.add(target)
            if any(alias.name == '*' for alias in node.names):
                errors.append('wildcard import')
            # Include `from package import server` as well as `from server import app`.
            imports.update(target + '.' + alias.name for alias in node.names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {'globals', 'locals'}:
            errors.append('namespace injection')
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'sys' and node.attr == 'modules':
            errors.append('module namespace lookup')
    if any(name == PACKAGE + '.server' or name.startswith(PACKAGE + '.server.') for name in imports):
        errors.append('business module imports application entry point')
    return imports, errors


def cycle_errors(graph):
    errors = []
    done, active = set(), []
    def visit(module):
        if module in active:
            errors.append('dependency cycle: ' + ' -> '.join(active + [module]))
            return
        if module in done:
            return
        active.append(module)
        for dependency in sorted(graph[module] & graph.keys()):
            visit(dependency)
        active.pop()
        done.add(module)
    for module in sorted(graph):
        visit(module)
    return errors


def main():
    graph, errors = {}, []
    for package in PACKAGES:
        for path in (ROOT / PACKAGE / package).rglob('*.py'):
            is_package = path.name == '__init__.py'
            parts = path.relative_to(ROOT).with_suffix('').parts
            module = '.'.join(parts[:-1] if is_package else parts)
            imports, failures = inspect_module(path.read_text(encoding='utf-8'), module, is_package)
            graph[module] = imports
            errors.extend(f'{path.relative_to(ROOT)}: {failure}' for failure in failures)
    errors.extend(cycle_errors(graph))
    fixture_package = PACKAGE + '.runtime'
    parent, _ = inspect_module('from . import child', fixture_package, True)
    child, _ = inspect_module('from . import shared', fixture_package + '.child')
    assert cycle_errors({fixture_package: parent, fixture_package + '.child': child})
    for source in ('from .. import server', 'from ..server import app', 'from .service import *',
                   'register(globals())', 'vars(sys.modules[fn.__module__])'):
        assert inspect_module(source, PACKAGE + '.model_profiles.example')[1], source
    if errors:
        raise SystemExit('\n'.join(errors))
    print('PASS extracted backend boundaries: ' + ', '.join(PACKAGES))


if __name__ == '__main__':
    main()

"""Deterministically bundle trusted stdlib-only runtime code into one installer."""
import argparse
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = ('release_runtime_contract.py', 'release_runtime_client.py', 'release_services.py',
           'release_runtime_configuration.py', 'release_runtime_transition.py', 'release_runtime_main.py')
CONFIGURATION_SOURCE = 'local_inspection_service/runtime/configuration_contract.py'
CONFIGURATION_MODULE = 'local_inspection_service.runtime.configuration_contract'
TEMPLATE = 'install_release.template.sh'
MARKER = '@@VANTALINE_RUNTIME_CONTROLLER@@'


def render():
    blocks = []
    inputs = [(CONFIGURATION_MODULE, ROOT.parent / CONFIGURATION_SOURCE)] + [(name[:-3], ROOT / name) for name in SOURCES]
    bundled = {module for module, path in inputs}
    for module, path in inputs:
        source = path.read_text(encoding='utf-8-sig')
        lines = source.splitlines(keepends=True)
        for node in ast.parse(source).body:
            if isinstance(node, ast.ImportFrom) and node.module in bundled:
                lines[node.lineno-1:node.end_lineno] = ['' for _ in range(node.end_lineno-node.lineno+1)]
        blocks.append('# Source: '+path.relative_to(ROOT.parent).as_posix()+'\n'+''.join(lines).rstrip()+'\n')
    helper = "runtime_controller() {\n  /usr/bin/python3 -I -S - \"$@\" <<'PY_VANTALINE_RUNTIME'\n"+'\n'.join(blocks)+"PY_VANTALINE_RUNTIME\n}\n"
    template = (ROOT/TEMPLATE).read_text(encoding='utf-8')
    if template.count(MARKER) != 1 or any('PY_VANTALINE_RUNTIME' in path.read_text(encoding='utf-8-sig') for module, path in inputs):
        raise ValueError('Invalid installer source boundaries')
    return template.replace(MARKER, helper).encode('utf-8')


def verify():
    if (ROOT/'install_release.sh').read_bytes() != render():
        raise SystemExit('Installer differs from trusted template/modules; regenerate it')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    if args.write:
        (ROOT/'install_release.sh').write_bytes(render())
    else:
        verify()
    print('PASS deterministic standalone installer')

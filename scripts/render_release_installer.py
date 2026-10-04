"""Deterministically bundle trusted stdlib-only runtime code into one installer."""
import argparse
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = ('release_runtime_contract.py', 'release_runtime_client.py', 'release_services.py',
           'release_runtime_transition.py', 'release_runtime_main.py')
TEMPLATE = 'install_release.template.sh'
MARKER = '@@VANTALINE_RUNTIME_CONTROLLER@@'


def render():
    blocks = []
    for name in SOURCES:
        source = (ROOT/name).read_text(encoding='utf-8-sig')
        lines = source.splitlines(keepends=True)
        for node in ast.parse(source).body:
            if isinstance(node, ast.ImportFrom) and node.module in {item[:-3] for item in SOURCES}:
                lines[node.lineno-1:node.end_lineno] = ['' for _ in range(node.end_lineno-node.lineno+1)]
        blocks.append('# Source: scripts/'+name+'\n'+''.join(lines).rstrip()+'\n')
    helper = "runtime_controller() {\n  /usr/bin/python3 -I -S - \"$@\" <<'PY_VANTALINE_RUNTIME'\n"+'\n'.join(blocks)+"PY_VANTALINE_RUNTIME\n}\n"
    template = (ROOT/TEMPLATE).read_text(encoding='utf-8')
    if template.count(MARKER) != 1 or any('PY_VANTALINE_RUNTIME' in (ROOT/name).read_text(encoding='utf-8-sig') for name in SOURCES):
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

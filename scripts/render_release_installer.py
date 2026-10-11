"""Deterministically bundle trusted stdlib-only runtime code into one installer."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = ('release_runtime_contract.py', 'release_runtime_client.py', 'release_services.py',
           'release_runtime_configuration.py', 'release_runtime_transition.py', 'observer_bundle_contract.py',
           'release_observer_snapshot.py', 'release_runtime_main.py')
OBSERVER_SOURCES = (
    'local_inspection_service/runtime/__init__.py',
    'local_inspection_service/runtime/observe_label_runtime.py',
    'local_inspection_service/runtime/configuration.py',
    'local_inspection_service/runtime/configuration_contract.py',
    'local_inspection_service/runtime/label_identity.py',
    'local_inspection_service/runtime/label_observation.py',
    'local_inspection_service/runtime/label_metrics.py',
    'local_inspection_service/storage/__init__.py',
    'local_inspection_service/storage/label_runtime.py',
    'local_inspection_service/storage/postgres_runtime_repository.py',
    'local_inspection_service/storage/schema.py',
)
CONFIGURATION_SOURCE = 'local_inspection_service/runtime/configuration_contract.py'
CONFIGURATION_MODULE = 'local_inspection_service.runtime.configuration_contract'
TEMPLATE = 'install_release.template.sh'
MARKER = '@@VANTALINE_RUNTIME_CONTROLLER@@'


def render():
    blocks = []
    lock = ROOT.parent / 'release/observer-dependencies.json'
    inventory = json.loads((ROOT.parent / 'release/observer-bundle-files.json').read_bytes())
    if (inventory['schema'] != 1 or inventory['lock_sha256'] != hashlib.sha256(lock.read_bytes()).hexdigest()
            or len(inventory['files']) != 126):
        raise ValueError('Observer dependency authorization differs from lock')
    # Python sources are LF in Git archives; Windows checkout conversion must
    # not change the privileged execution authorization embedded in the installer.
    authorization = {name: hashlib.sha256((ROOT.parent / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                     for name in OBSERVER_SOURCES}
    authorization['release/observer-dependencies.json'] = hashlib.sha256(lock.read_bytes()).hexdigest()
    authorization.update({'release/observer_bundle/' + name: digest for name, digest in inventory['files'].items()})
    authorization['release/observer_bundle/manifest.json'] = hashlib.sha256(
        (json.dumps(inventory, sort_keys=True, indent=2) + '\n').encode('utf8')).hexdigest()
    inputs = [(CONFIGURATION_MODULE, ROOT.parent / CONFIGURATION_SOURCE)] + [(name[:-3], ROOT / name) for name in SOURCES]
    bundled = {module for module, path in inputs}
    for module, path in inputs:
        source = path.read_text(encoding='utf-8-sig')
        lines = source.splitlines(keepends=True)
        for node in ast.parse(source).body:
            if isinstance(node, ast.ImportFrom) and node.module in bundled:
                lines[node.lineno-1:node.end_lineno] = ['' for _ in range(node.end_lineno-node.lineno+1)]
            if (module == 'release_observer_snapshot' and isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'OBSERVER_EXECUTION_FILES' for t in node.targets)):
                lines[node.lineno-1:node.end_lineno] = ['OBSERVER_EXECUTION_FILES = ' + repr(authorization) + '\n']
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

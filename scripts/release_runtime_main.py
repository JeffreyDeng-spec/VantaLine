"""Private dispatch embedded into the standalone installer; never imported by Web."""
import sys
import json
import os
import stat
import subprocess
import time
import uuid
import re
import math
from pathlib import Path

from release_runtime_contract import ContractError, Topology, WEB, LABEL, read_object, sync_directory
from release_runtime_transition import RuntimeTransition


RUNTIME_STORAGE = Path('/var/lib/vantaline-release')


def trusted_directory(path, *, private=False):
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o022
            or (private and stat.S_IMODE(info.st_mode) != 0o700)):
        raise ContractError('Untrusted runtime recovery directory')


def runtime_storage(*, create=False):
    # Every ancestor is root-owned and not writable by the application account.
    # Existing paths are checked, never chowned/chmodded or silently replaced.
    if os.geteuid() != 0:
        raise ContractError('Runtime recovery storage requires root')
    for ancestor in reversed(RUNTIME_STORAGE.parents):
        trusted_directory(ancestor)
    if create:
        try:
            RUNTIME_STORAGE.mkdir(mode=0o700)
            sync_directory(RUNTIME_STORAGE.parent)
        except FileExistsError:
            pass
    trusted_directory(RUNTIME_STORAGE, private=True)


def trusted_observation_tree(root, *, links):
    """Check imported code without following application-owned runtime links."""
    trusted_directory(root)
    def fail(error):
        raise error
    for directory, children, files in os.walk(root, followlinks=False, onerror=fail):
        for name in children + files:
            path = Path(directory) / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                if path in links and os.readlink(path) == str(links[path]):
                    continue
                resolved = path.resolve(strict=True)
                if not resolved.is_relative_to(root):
                    raise ContractError('Untrusted observation code link')
                continue  # Its destination is checked by the same tree walk.
            if (info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022
                    or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode))):
                raise ContractError('Untrusted observation code')


def observe_runtime(release, commit):
    """Fixed read-only post-acceptance entry; never touches release state."""
    if (os.geteuid() != 0 or not re.fullmatch(r'v[0-9]{4}\.[0-9]{2}\.[0-9]+', release)
            or not re.fullmatch(r'[0-9a-f]{40}', commit)):
        raise ContractError('Invalid runtime observation request')
    base = Path('/opt/vantaline')
    target = base / 'releases' / release
    for path in reversed(target.parents):
        trusted_directory(path)
    current = base / 'current'
    if (not current.is_symlink() or current.lstat().st_uid != 0
            or current.resolve(strict=True) != target):
        raise ContractError('Runtime observation release mismatch')
    trusted_directory(target)
    identity = RuntimeTransition.identity(target)
    if identity['topology']['commit'] != commit or not identity['topology']['runtime_protocol']:
        raise ContractError('Runtime observation identity mismatch')
    venv = base / 'venv'
    executable = venv / 'bin/python'
    interpreter = executable.resolve(strict=True)
    if interpreter != Path('/usr/bin/python3').resolve(strict=True):
        raise ContractError('Untrusted observation base interpreter')
    for path in reversed(interpreter.parents):
        trusted_directory(path)
    info = interpreter.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
        raise ContractError('Untrusted observation interpreter')
    configuration = venv / 'pyvenv.cfg'
    info = configuration.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
        raise ContractError('Untrusted observation interpreter configuration')
    if info.st_size > 4096:
        raise ContractError('Invalid observation interpreter configuration')
    fields = {}
    for line in configuration.read_text(encoding='utf-8').splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            key = key.strip()
            if key in fields:
                raise ContractError('Invalid observation interpreter configuration')
            fields[key] = value.strip()
    home = fields.get('home')
    if not home or not Path(home).is_absolute() or Path(home).resolve(strict=True) != interpreter.parent:
        raise ContractError('Untrusted observation interpreter home')
    interpreter_links = {path: Path(os.readlink(path)) for path in (venv / 'bin').iterdir()
                         if path.is_symlink() and path.resolve(strict=True) == interpreter}
    trusted_observation_tree(venv, links=interpreter_links)
    trusted_observation_tree(target, links={
        target / '.venv': venv,
        target / 'models': base / 'shared/models',
        target / 'local_inspection_service/data': base / 'shared/data',
    })
    # -I -S ignores Python environment, user site, .pth and sitecustomize.
    # Only verified fixed site-packages and the immutable package are added. No caller-selected path/module/code is run.
    code = "import sys,runpy; sys.path.insert(0,'/opt/vantaline/venv/lib/python%d.%d/site-packages'%sys.version_info[:2]); sys.path.insert(0,sys.argv.pop(1)); runpy.run_module('local_inspection_service.runtime.observe_label_runtime',run_name='__main__')"
    result = subprocess.run([str(executable), '-I', '-S', '-B', '-c', code, str(target),
                             '--release', release, '--commit', commit], cwd=target,
                            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'},
                            capture_output=True, text=True, timeout=45, check=True)
    if len(result.stdout) > 65536:
        raise ContractError('Invalid runtime observation response')
    value = json.loads(result.stdout)
    keys = {'schema', 'git_commit', 'release', 'worker_mode', 'config_revision',
            'maintenance', 'paused', 'queued_runs', 'active_runs', 'roles',
            'samples_before', 'periodic_progress'}
    if (not isinstance(value, dict) or set(value) != keys or type(value['schema']) is not int
            or value['schema'] != 1 or value['git_commit'] != commit or value['release'] != release
            or value['worker_mode'] != identity['topology']['mode']
            or not isinstance(value['config_revision'], str)
            or not re.fullmatch(r'[0-9a-f]{64}', value['config_revision'])
            or any(type(value[key]) is not bool for key in ('maintenance', 'paused'))
            or any(type(value[key]) is not int or value[key] < 0 for key in ('queued_runs', 'active_runs'))
            or value['active_runs'] > 2 or value['periodic_progress'] is not True):
        raise ContractError('Invalid runtime observation response')
    expected_roles = {'web', 'label'} if value['worker_mode'] == 'external' else {'web'}
    samples = []
    for key in ('samples_before', 'roles'):
        rows = value[key]
        if not isinstance(rows, list) or len(rows) != len(expected_roles):
            raise ContractError('Invalid runtime observation roles')
        indexed = {}
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {'role', 'instance', 'pid', 'sampled_at'}
                    or row['role'] not in expected_roles or row['role'] in indexed
                    or not isinstance(row['instance'], str) or not re.fullmatch(r'[0-9a-f]{32}', row['instance'])
                    or type(row['pid']) is not int or row['pid'] <= 0
                    or type(row['sampled_at']) not in (int, float) or not math.isfinite(row['sampled_at'])
                    or row['sampled_at'] <= 0):
                raise ContractError('Invalid runtime observation roles')
            indexed[row['role']] = row
        samples.append(indexed)
    for role in expected_roles:
        before, after = samples[0][role], samples[1][role]
        if (before['instance'] != after['instance'] or before['pid'] != after['pid']
                or before['sampled_at'] >= after['sampled_at']):
            raise ContractError('Runtime observation did not advance')
    print(json.dumps(value, sort_keys=True))


def main():
    arguments = sys.argv[1:]
    operation = arguments.pop(0)
    if operation == 'observe' and len(arguments) == 2:
        try:
            observe_runtime(*arguments)
        except (RuntimeError, UnicodeError, OverflowError):
            raise ContractError('Runtime database observation failed') from None
        return
    if operation == 'prepare_storage' and not arguments:
        runtime_storage(create=True)
        return
    if operation == 'capabilities' and not arguments:
        print(json.dumps({'schema': 1, 'topologies': [1, 2], 'runtime_protocol': 1,
                          'services': [WEB, LABEL], 'drain_budget_seconds': 500, 'recovery_storage_schema': 1, 'configuration_schema': 1}, sort_keys=True))
        return
    if operation == 'validate' and len(arguments) == 3:
        directory, commit, allow_legacy = Path(arguments[0]), arguments[1], arguments[2] == '1'
        path = directory/'RUNTIME_TOPOLOGY.json'
        if not path.exists() and allow_legacy:
            print('runtime_topology=legacy-embedded')
            return
        topology = Topology.parse(read_object(path), commit)
        print('runtime_topology='+topology.mode)
        return
    if operation == 'mode' and len(arguments) == 2:
        identities = [RuntimeTransition.identity(Path(item)) for item in arguments]
        print('managed' if any(item['topology']['runtime_protocol'] for item in identities) else 'legacy')
        return
    if operation not in ('begin', 'start', 'accept', 'rollback', 'finish', 'verify', 'recover', 'previous', 'recovery_mode', 'prepare_recovery', 'check_journal') or len(arguments) < 1:
        raise ContractError('Unsupported controller operation')
    journal = Path(arguments.pop(0))
    if not journal.name.startswith('.runtime-transition-') or journal.parent != RUNTIME_STORAGE:
        raise ContractError('Invalid transition journal location')
    runtime_storage()
    if os.path.lexists(journal):
        info = journal.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ContractError('Untrusted transition journal')
    if operation == 'check_journal' and not arguments:
        if os.path.lexists(journal):
            read_object(journal, limit=65536)
        return
    if operation == 'finish' and not arguments:
        journal.unlink(missing_ok=True)
        return
    if operation == 'rollback' and not os.path.lexists(journal):
        return  # Preparation failed before any mutable action.
    if operation == 'verify' and len(arguments) == 1:
        identity = RuntimeTransition.identity(Path(arguments[0]))
        if not identity['topology']['runtime_protocol']:
            return
    controller = RuntimeTransition(journal)
    if operation == 'previous' and not arguments:
        controller.load()
        print(controller.data['old']['directory'])
        return
    if operation == 'begin' and len(arguments) == 2:
        controller.begin(*(Path(item) for item in arguments))
    elif operation == 'start' and not arguments:
        controller.start()
    elif operation == 'accept' and not arguments:
        controller.accept()
    elif operation == 'rollback' and not arguments:
        controller.rollback(Path('/opt/vantaline/current'))
    elif operation == 'recovery_mode' and len(arguments) == 2:
        print(controller.recovery_mode(Path(arguments[0]), arguments[1]))
    elif operation == 'prepare_recovery' and len(arguments) == 1:
        controller.prepare_recovery(Path(arguments[0]))
    elif operation == 'recover' and len(arguments) == 1:
        controller.recover(Path(arguments[0]))
    elif operation == 'verify' and len(arguments) == 1:
        if os.path.lexists(journal):
            raise ContractError('Pending transition requires explicit recovery')
        controller.data = {'revision': uuid.uuid4().hex}
        controller.ready(controller.identity(Path(arguments[0])), deadline=time.monotonic()+15)
    else:
        raise ContractError('Invalid controller arguments')


if __name__ == '__main__':
    try:
        main()
    except (ContractError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        # State, paths, unit output and configuration never enter deployment logs.
        print('Runtime transition failed; retained recovery evidence requires inspection', file=sys.stderr)
        raise SystemExit(1) from None

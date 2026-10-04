"""Private dispatch embedded into the standalone installer; never imported by Web."""
import sys
import json
import os
import stat
import subprocess
import time
import uuid
from pathlib import Path

from release_runtime_contract import ContractError, Topology, WEB, LABEL, read_object
from release_runtime_transition import RuntimeTransition


def main():
    arguments = sys.argv[1:]
    operation = arguments.pop(0)
    if operation == 'capabilities' and not arguments:
        print(json.dumps({'schema': 1, 'topologies': [1, 2], 'runtime_protocol': 1,
                          'services': [WEB, LABEL], 'drain_budget_seconds': 500}, sort_keys=True))
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
    if operation not in ('begin', 'start', 'accept', 'rollback', 'finish', 'verify', 'recover', 'previous', 'recovery_mode', 'prepare_recovery') or len(arguments) < 1:
        raise ContractError('Unsupported controller operation')
    journal = Path(arguments.pop(0))
    if not journal.name.startswith('.runtime-transition-') or journal.parent != Path('/opt/vantaline/backups'):
        raise ContractError('Invalid transition journal location')
    info = journal.parent.lstat()
    if journal.parent.is_symlink() or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o022:
        raise ContractError('Untrusted transition journal directory')
    if journal.exists():
        info = journal.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ContractError('Untrusted transition journal')
    if operation == 'finish' and not arguments:
        journal.unlink(missing_ok=True)
        return
    if operation == 'rollback' and not journal.exists():
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
        if journal.exists():
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

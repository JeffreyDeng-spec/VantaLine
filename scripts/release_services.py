"""Fixed service templates and reversible unit changes for immutable releases.

This module is installer-owned. Release metadata can select one of two known
roles, never a command, service name, username, path or unit template.
"""
from dataclasses import dataclass
import os
import re
import time
from pathlib import Path
import stat
import subprocess
import tempfile

from release_runtime_contract import ContractError, WEB, LABEL, Topology, sync_directory

SYSTEMD = Path('/etc/systemd/system')
WEB_DROPIN = Path('vantaline.service.d/70-label-runtime.conf')
LABEL_UNIT = Path('vantaline-label-worker.service')
MARKER = '# Managed by the VantaLine immutable release controller\n'
WEB_TEMPLATE = MARKER + '''[Service]
TimeoutStopSec=500
KillMode=control-group
'''
LABEL_TEMPLATE = MARKER + '''[Unit]
Description=VantaLine label inspection consumer
After=network.target postgresql.service vantaline.service

[Service]
Type=simple
User=vantaline
Group=vantaline
WorkingDirectory=/opt/vantaline/current
ExecStart=/opt/vantaline/current/.venv/bin/python -m local_inspection_service.label_inspection.runtime --config /etc/vantaline/runtime/current.json
TimeoutStopSec=500
KillMode=control-group
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
'''


class ServiceCommands:
    def run(self, *arguments: str, check=True, timeout=15):
        result = subprocess.run(['systemctl', *arguments], capture_output=True, text=True,
                                timeout=timeout, check=False)
        if check and result.returncode:
            # Unit output may contain file paths or environment values.
            raise ContractError('Service operation failed')
        return result

    def stop_all(self, services: tuple[str, ...], *, deadline: float):
        if not services or any(item not in (WEB, LABEL) for item in services):
            raise ContractError('Unsupported service stop')
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise ContractError('Service stop budget expired')
        self.run('stop', '--no-block', *services, timeout=remaining)
        while True:
            stopped = True
            for service in services:
                for name, accepted in (('ActiveState', ('inactive', 'failed')), ('MainPID', ('0',)), ('ControlPID', ('0',))):
                    remaining = deadline-time.monotonic()
                    if remaining <= 0:
                        raise ContractError('Service stop budget expired')
                    if self.property(service, name, timeout=remaining) not in accepted:
                        stopped = False
            if stopped:
                return
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise ContractError('Service stop budget expired')
            time.sleep(min(.1, remaining))

    def property(self, service: str, name: str, *, timeout=15) -> str:
        if service not in (WEB, LABEL) or name not in ('LoadState', 'ActiveState', 'MainPID', 'TimeoutStopUSec', 'KillMode', 'ControlPID'):
            raise ContractError('Unsupported service query')
        return self.run('show', service, '-p', name, '--value', timeout=timeout).stdout.strip()


@dataclass
class UnitChanges:
    directory: Path
    commands: ServiceCommands

    def _path(self, relative: Path) -> Path:
        if relative not in (WEB_DROPIN, LABEL_UNIT):
            raise ContractError('Unsupported unit path')
        if self.directory.is_symlink() or (self.directory / relative.parent).is_symlink():
            raise ContractError('Unexpected service directory')
        return self.directory / relative

    def capture(self) -> dict:
        files = {}
        for relative in (WEB_DROPIN, LABEL_UNIT):
            path = self._path(relative)
            try:
                info = path.lstat()
            except FileNotFoundError:
                files[str(relative)] = None
                continue
            if stat.S_ISLNK(info.st_mode) and relative == LABEL_UNIT and os.readlink(path) == '/dev/null':
                files[str(relative)] = {'masked': True}
            elif stat.S_ISREG(info.st_mode):
                if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o022 or info.st_size > 16384:
                    raise ContractError('Untrusted unit ownership or permissions')
                with path.open('rb') as handle:
                    raw = handle.read(16385)
                if len(raw) > 16384:
                    raise ContractError('Unexpected unit size')
                text = raw.decode('utf-8')
                if not text.startswith(MARKER) or len(text) > 16384:
                    raise ContractError('Refusing to replace an unmanaged unit')
                files[str(relative)] = {'text': text, 'mode': stat.S_IMODE(info.st_mode)}
            else:
                raise ContractError('Unexpected unit file type')
        enabled = self.commands.run('is-enabled', LABEL, check=False).stdout.strip()
        if enabled not in ('enabled', 'disabled', 'masked', 'not-found', ''):
            raise ContractError('Unsupported worker enable state')
        active = {service: self.commands.property(service, 'ActiveState') for service in (WEB, LABEL)}
        if any(value not in ('active', 'inactive', 'failed') for value in active.values()):
            raise ContractError('Service transition already in progress')
        return {'schema': 1, 'files': files, 'worker_enabled': enabled, 'active': active}

    def write(self, relative: Path, text: str, mode=0o644):
        path = self._path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix='.vantaline-unit-', dir=path.parent)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as handle:
                handle.write(text)
                handle.flush()
                os.fchmod(handle.fileno(), mode)
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            sync_directory(path.parent)
        finally:
            if os.path.lexists(temporary):
                os.unlink(temporary)

    def install(self, topology: Topology, *, deadline=None, stopping_services=()):
        def budget():
            remaining = 15 if deadline is None else min(15, deadline-time.monotonic())
            if remaining <= 0:
                raise ContractError('Runtime unit budget expired')
            return remaining
        self.write(WEB_DROPIN, WEB_TEMPLATE)
        if topology.mode == 'external':
            self.write(LABEL_UNIT, LABEL_TEMPLATE)
        self.commands.run('daemon-reload', timeout=budget())
        for service in dict.fromkeys((*topology.services, *stopping_services)):
            if duration_seconds(self.commands.property(service, 'TimeoutStopUSec', timeout=budget())) != 500:
                raise ContractError('Effective service stop budget mismatch')
            if self.commands.property(service, 'KillMode', timeout=budget()) != 'control-group':
                raise ContractError('Effective service kill mode mismatch')
        if topology.mode == 'external':
            self.commands.run('enable', LABEL, timeout=budget())

    def restore(self, snapshot: dict):
        if (self.directory / LABEL_UNIT).is_file():
            self.commands.run('disable', LABEL)
        # Restore only the two controller-owned paths. Other administrator units
        # and drop-ins are never rewritten or removed.
        for relative in (WEB_DROPIN, LABEL_UNIT):
            previous = snapshot['files'][str(relative)]
            path = self._path(relative)
            if previous is None:
                if os.path.lexists(path):
                    path.unlink()
            elif previous.get('masked'):
                if os.path.lexists(path):
                    path.unlink()
                path.symlink_to('/dev/null')
            else:
                self.write(relative, previous['text'], previous['mode'])
        self.commands.run('daemon-reload')
        if snapshot['worker_enabled'] == 'enabled':
            self.commands.run('enable', LABEL)


def duration_seconds(value: str) -> float:
    units = {'us': .000001, 'ms': .001, 's': 1, 'min': 60, 'h': 3600, 'd': 86400}
    tokens = re.findall(r'(\d+(?:\.\d+)?)(us|ms|min|s|h|d)', value)
    if not tokens or ''.join(number+unit for number, unit in tokens) != value.replace(' ', ''):
        raise ContractError('Unknown effective service stop budget')
    return sum(float(number)*units[unit] for number, unit in tokens)

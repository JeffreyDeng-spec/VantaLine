"""Fixed, read-only authentication probe; never emit connection/configuration data."""
import json
import os
from pathlib import Path
import pwd
import signal
import stat
import subprocess


def probe(environment, *, account=None):
    def drop():
        os.setgroups([])
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    try:
        result = subprocess.run(
            ['/usr/bin/psql', '-X', '-w', '-Atc', 'SELECT 1'],
            env=environment, cwd='/', capture_output=True, timeout=8,
            preexec_fn=drop if account is not None else None)
        if result.returncode == 0 and result.stdout.strip() == b'1':
            return 'success'
        # Match fixed categories, never print driver messages or DSNs.
        for token, category in [(b'Peer authentication failed', 'peer_authentication'),
                                (b'password authentication failed', 'password_authentication'),
                                (b'no password supplied', 'password_missing'),
                                (b'Connection refused', 'connection_refused')]:
            if token in result.stderr:
                return category
        return 'connection_failed'
    except subprocess.TimeoutExpired:
        return 'timeout'
    except Exception:
        return 'probe_unavailable'


def diagnose():
    result = {'schema': 1, 'read_only': True, 'root_connection': 'not_run',
              'application_connection': 'not_run', 'stage': 'root'}
    try:
        if os.geteuid() != 0:
            return result
        result['stage'] = 'configuration'
        path = Path('/etc/vantaline/runtime/current/config.json')
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o027):
                return result
            raw = stream.read(256 * 1024 + 1)
        if len(raw) > 256 * 1024:
            return result
        config = json.loads(raw)['environment']
        environment = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}
        environment.update({k: v for k, v in config.items()
                            if k.startswith('PG') and isinstance(v, str)})
        environment.update(PGDATABASE=config['DATABASE_URL'], PGCONNECT_TIMEOUT='2',
                           PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=2000')
        result['stage'] = 'authentication'
        result['root_connection'] = probe(environment)
        result['application_connection'] = probe(environment, account=pwd.getpwnam('vantaline'))
        result['stage'] = 'complete'
    except Exception:
        pass
    return result


if __name__ == '__main__':
    signal.alarm(25)
    print(json.dumps(diagnose(), sort_keys=True))

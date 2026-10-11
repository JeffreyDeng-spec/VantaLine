"""Fixed-path, unprivileged, read-only observation preflight diagnostics.

Print only stage codes and booleans. Never import application or venv code.
"""
import json
import os
import pathlib
import signal
import stat
import sys


def diagnose():
    report = {'schema': 1, 'system_python': list(sys.version_info[:2]),
              'read_only': True, 'preflight_passed': False}
    stage = 'base'
    visited = 0
    def check(path):
        info = path.lstat()
        if info.st_uid != 0:
            raise ValueError('owner')
        if stat.S_IMODE(info.st_mode) & 0o022:
            raise ValueError('mode')
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ValueError('type')
    try:
        root = pathlib.Path('/opt/vantaline/venv')
        interpreter = pathlib.Path('/usr/bin/python3').resolve(strict=True)
        stage = 'venv_root'
        check(root)
        stage = 'ancestors'
        for path in [*root.parents, interpreter, *interpreter.parents]:
            check(path)
        stage = 'interpreter'
        if (root/'bin/python').resolve(strict=True) != interpreter:
            raise ValueError('identity')
        stage = 'configuration'
        configuration = root/'pyvenv.cfg'
        check(configuration)
        if configuration.stat().st_size > 4096:
            raise ValueError('size')
        fields = {}
        for line in configuration.read_text().splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                if key.strip() in fields:
                    raise ValueError('duplicate')
                fields[key.strip()] = value.strip()
        stage = 'home'
        home = pathlib.Path(fields['home'])
        if not home.is_absolute() or home.resolve(strict=True) != interpreter.parent:
            raise ValueError('identity')
        stage = 'tree'
        def fail(error):
            raise error
        for folder, directories, files in os.walk(root, followlinks=False, onerror=fail):
            for name in directories + files:
                visited += 1
                if visited > 200000:
                    raise ValueError('limit')
                path = pathlib.Path(folder)/name
                if path.is_symlink():
                    destination = path.resolve(strict=True)
                    if not (destination.is_relative_to(root) or
                            (path.parent == root/'bin' and destination == interpreter)):
                        raise ValueError('link')
                else:
                    check(path)
        report['preflight_passed'] = True
        report['stage'] = 'complete'
        report['reason'] = 'none'
    except Exception as error:
        # Do not stringify driver/filesystem errors; their text contains paths.
        allowed = {'owner', 'mode', 'type', 'identity', 'size', 'duplicate', 'limit', 'link'}
        report['stage'] = stage
        report['reason'] = (error.args[0] if type(error) is ValueError and error.args
                            and type(error.args[0]) is str
                            and error.args[0] in allowed else
                            'permission' if isinstance(error, PermissionError) else
                            'missing' if isinstance(error, FileNotFoundError) else
                            'link_resolution' if isinstance(error, RuntimeError) else 'invalid')
    report['visited_entries'] = visited
    return report


if __name__ == '__main__':
    # Bounded without importing caller-selected code or executing venv hooks.
    signal.alarm(45)
    print(json.dumps(diagnose(), sort_keys=True))

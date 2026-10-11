"""Stdlib-only trust contract for the immutable observer dependency bundle."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import sys


class ObserverBundleError(RuntimeError):
    pass


def observer_json(path):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ObserverBundleError('Duplicate observer metadata key')
            result[key] = value
        return result
    try:
        with Path(path).open('rb') as handle:
            raw = handle.read(1024*1024 + 1)
        if len(raw) > 1024*1024:
            raise ObserverBundleError('Observer metadata too large')
        value = json.loads(raw, object_pairs_hook=unique)
        if not isinstance(value, dict):
            raise ObserverBundleError('Invalid observer metadata')
        return value
    except (ValueError, UnicodeError, TypeError):
        raise ObserverBundleError('Invalid observer metadata') from None


def observer_runtime_compatible():
    try:
        libc = os.confstr('CS_GNU_LIBC_VERSION').split()
        version = tuple(int(v) for v in libc[1].split('.'))
        return (sys.platform == 'linux' and platform.machine() == 'x86_64'
                and sys.implementation.name == 'cpython'
                and sys.implementation.cache_tag == 'cpython-310'
                and sys.version_info[:2] == (3, 10)
                and libc[0] == 'glibc' and version >= (2, 17))
    except (AttributeError, OSError, TypeError, ValueError, IndexError):
        return False


def observer_bundle_lock(path):
    value = observer_json(path)
    if (set(value) != {'schema', 'python', 'implementation', 'architecture', 'platform', 'wheels'}
            or type(value['schema']) is not int or value['schema'] != 1
            or value['python'] != [3, 10] or value['implementation'] != 'cpython'
            or value['architecture'] != 'x86_64' or value['platform'] != 'linux'
            or not isinstance(value['wheels'], list) or len(value['wheels']) != 3):
        raise ObserverBundleError('Invalid observer dependency lock')
    expected = {'psycopg': '3.3.4', 'psycopg-binary': '3.3.4', 'typing_extensions': '4.15.0'}
    seen = set()
    for wheel in value['wheels']:
        if (not isinstance(wheel, dict) or set(wheel) != {'name', 'version', 'filename', 'sha256', 'url'}
                or not isinstance(wheel['name'], str) or not isinstance(wheel['version'], str)
                or wheel['name'] in seen or expected.get(wheel['name']) != wheel['version']
                or not isinstance(wheel['filename'], str)
                or not re.fullmatch('[A-Za-z0-9_.-]+\\.whl', wheel['filename'])
                or not isinstance(wheel['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', wheel['sha256'])
                or not isinstance(wheel['url'], str)
                or not wheel['url'].startswith('https://files.pythonhosted.org/packages/')
                or not wheel['url'].endswith('/' + wheel['filename'])):
            raise ObserverBundleError('Invalid observer dependency wheel')
        seen.add(wheel['name'])
    return value


def observer_member_name(name):
    if not isinstance(name, str):
        raise ObserverBundleError('Invalid observer bundle member')
    path = PurePosixPath(name)
    if (not name or not path.parts or '\\' in name or path.is_absolute()
            or '..' in path.parts or str(path) != name
            or name.endswith(('.pth', '.pyc')) or path.name in {'sitecustomize.py', 'usercustomize.py'}):
        raise ObserverBundleError('Invalid observer bundle member')
    return path


def observer_dependency_member(name):
    path = observer_member_name(name)
    allowed = {'psycopg', 'psycopg_binary', 'psycopg_binary.libs', 'typing_extensions.py',
               'psycopg-3.3.4.dist-info', 'psycopg_binary-3.3.4.dist-info',
               'typing_extensions-4.15.0.dist-info'}
    if path.parts[0] not in allowed:
        raise ObserverBundleError('Unexpected observer dependency')
    return path


def verify_observer_bundle(directory, lock_path, *, require_root=True, require_runtime=True):
    directory = Path(directory)
    if require_runtime and not observer_runtime_compatible():
        raise ObserverBundleError('Unsupported observer runtime')
    def check(path):
        info = path.lstat()
        if (not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode))
                or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)
                or (require_root and (info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022))):
            raise ObserverBundleError('Untrusted observer dependency code')
    check(directory)
    manifest_path = directory/'manifest.json'
    check(manifest_path)
    lock = observer_bundle_lock(lock_path)
    value = observer_json(manifest_path)
    if (set(value) != {'schema', 'lock_sha256', 'files'} or type(value['schema']) is not int
            or value['schema'] != 1 or value['lock_sha256'] != hashlib.sha256(Path(lock_path).read_bytes()).hexdigest()
            or not isinstance(value['files'], dict) or not 1 <= len(value['files']) <= 1000):
        raise ObserverBundleError('Invalid observer bundle manifest')
    actual = set()
    def scan_error(error):
        raise ObserverBundleError('Observer dependency inventory unavailable') from None
    for folder, directories, files in os.walk(directory, followlinks=False, onerror=scan_error):
        for entry in directories + files:
            path = Path(folder)/entry
            check(path)
            if path.is_file():
                name = path.relative_to(directory).as_posix()
                if name == 'manifest.json':
                    continue
                observer_dependency_member(name)
                actual.add(name)
    if actual != set(value['files']):
        raise ObserverBundleError('Observer bundle members differ')
    for name, digest in value['files'].items():
        observer_dependency_member(name)
        if (not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)
                or hashlib.sha256((directory/name).read_bytes()).hexdigest() != digest):
            raise ObserverBundleError('Observer bundle checksum differs')
    required = {'psycopg/__init__.py', 'psycopg_binary/__init__.py', 'typing_extensions.py'}
    if not required <= actual:
        raise ObserverBundleError('Observer dependency missing')
    return lock

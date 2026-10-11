"""Fixed-path, unprivileged live status. No application imports or mutations."""
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        return None


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate status field')
        value[key] = item
    return value


def diagnose():
    result = dict(schema=1, read_only=True, web_state='unknown', label_state='unknown',
                  version_available=False, consistent=False, git_commit=None,
                  release=None, installer_sha256=None)
    for unit, field in [('vantaline', 'web_state'), ('vantaline-label-worker', 'label_state')]:
        try:
            output = subprocess.run(['/usr/bin/systemctl', 'is-active', unit],
                                    capture_output=True, timeout=2)
            state = output.stdout[:32].decode('ascii').strip()
            if len(output.stdout) <= 32 and (
                    (state in {'active', 'reloading'} and output.returncode == 0)
                    or (state in {'inactive', 'failed', 'activating', 'deactivating'}
                        and output.returncode == 3)):
                result[field] = state
        except Exception:
            pass
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open('http://127.0.0.1:8765/api/version', timeout=3) as response:
            raw = response.read(16385)
        if len(raw) <= 16384:
            version = json.loads(raw, object_pairs_hook=unique_object)
            if (type(version) is dict and type(version.get('git_commit')) is str
                    and re.fullmatch('[0-9a-f]{40}', version['git_commit'])
                    and type(version.get('release')) is str
                    and len(version['release']) <= 80
                    and re.fullmatch(r'v[0-9]{4}\.[0-9]{2}\.[0-9]+', version['release'])
                    and type(version.get('consistent')) is bool):
                result.update(version_available=True, consistent=version.get('consistent') is True,
                              git_commit=version['git_commit'], release=version['release'])
    except Exception:
        pass
    try:
        descriptor = os.open('/usr/local/sbin/vantaline-install-release',
                             os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            stream = os.fdopen(descriptor, 'rb')
        except Exception:
            os.close(descriptor)
            raise
        with stream:
            metadata = os.fstat(stream.fileno())
            if stat.S_ISREG(metadata.st_mode) and metadata.st_size <= 2 * 1024 * 1024:
                raw = stream.read(2 * 1024 * 1024 + 1)
                if len(raw) <= 2 * 1024 * 1024:
                    result['installer_sha256'] = hashlib.sha256(raw).hexdigest()
    except Exception:
        pass
    return result


if __name__ == '__main__':
    signal.alarm(30)
    print(json.dumps(diagnose(), sort_keys=True))

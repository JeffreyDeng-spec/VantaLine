"""Real Linux namespace checks; separately required in CI, not mocked."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import pytest
from local_inspection_service.codex_compare.worker import sandbox_command


@pytest.mark.skipif(sys.platform != 'linux', reason='Linux bubblewrap isolation is verified by the Linux CI job')
def test_linux_filesystem_and_environment(tmp_path):
    assert shutil.which('bwrap'), 'bubblewrap must be provisioned for Linux acceptance'
    task=tmp_path/'task';task.mkdir()
    for part in ('input','work','bin','auth','runtime'):(task/part).mkdir()
    (task/'input'/'input.txt').write_text('immutable')
    secret=tmp_path/'website-secret';secret.write_text('never exposed')
    runtime=task/'runtime'/'codex'
    runtime.write_text('#!/usr/bin/python3\n'+'''import json,os,pathlib
assert not pathlib.Path('''+repr(str(secret))+''').exists()
assert 'DATABASE_URL' not in os.environ
assert not pathlib.Path('/etc/passwd').exists()
assert not pathlib.Path('/input/input.txt').stat().st_mode & 0o222 or not os.access('/input/input.txt',os.W_OK)
try:
    pathlib.Path('/input/input.txt').write_text('bad')
    raise AssertionError('input was writable')
except OSError:
    pass
pathlib.Path('/work/result').write_text('allowed')
print(json.dumps({'ok':True}))
''')
    runtime.chmod(0o755)
    # Short separate socket directory also supports long work-root paths.
    with tempfile.TemporaryDirectory(prefix='vci-',dir='/tmp') as directory:
        sockpath=Path(directory)/'r.sock'
        sock=socket.socket(socket.AF_UNIX);sock.bind(str(sockpath))
        try:
            command=sandbox_command(task,task/'auth',runtime,'task-token','fixture',sockpath)
            result=subprocess.run(command,input=b'',capture_output=True,timeout=10,env={**os.environ,'DATABASE_URL':'must-not-be-inherited'})
            assert result.returncode==0,result.stderr.decode()
            assert json.loads(result.stdout)['ok']
            assert (task/'work'/'result').read_text()=='allowed'
        finally:sock.close()

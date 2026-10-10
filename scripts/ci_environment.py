"""Read-only PR reuse of a main-built, lock-bound Python environment.

Only a dedicated main workflow seals/saves caches. Database state and source are
never part of this directory; misses/corruption rebuild the entire environment.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT/'requirements-production.lock'
MARKER = '.vantaline-environment.json'
PREFIX = 'vantaline-backend-venv-v1-'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def descriptor():
    release = dict(line.split('=',1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    return dict(os=os.environ['RUNNER_OS'], ubuntu=release['VERSION_ID'].strip('"'),
        image=os.environ['ImageVersion'], architecture=os.environ['RUNNER_ARCH'],
        python=platform.python_version(), interpreter=str(Path(sys.executable).resolve()),
        lock=sha(LOCK), rules=sha(Path(__file__)))


def cache_key(info):
    return PREFIX + hashlib.sha256(json.dumps(info,sort_keys=True).encode()).hexdigest()


def environment_path():
    return Path(os.environ['RUNNER_TEMP'])/'vantaline-ci-venv'


def files_digest(directory):
    records=[]
    for p in sorted(directory.rglob('*')):
        relative=p.relative_to(directory)
        if p==directory/MARKER:continue
        if p.is_symlink():records.append((str(relative),'link',os.readlink(p)))
        elif p.is_file():records.append((str(relative),'file',sha(p)))
    return hashlib.sha256(json.dumps(records).encode()).hexdigest()


def validate(directory, info):
    marker=json.loads((directory/MARKER).read_text())
    assert marker['schema']==1 and marker['descriptor']==info
    assert marker['key']==cache_key(info) and marker['files_sha256']==files_digest(directory)
    version=subprocess.check_output([str(directory/'bin/python'),'-c',
        'import platform;print(platform.python_version())'],text=True).strip()
    assert version==info['python'], 'cached interpreter mismatch'


def prepare(cache_only=False):
    directory=environment_path();info=descriptor()
    try:
        validate(directory,info)
        print('Verified main-built environment cache; install still verifies the full lock.')
    except (OSError,ValueError,AssertionError,KeyError,subprocess.SubprocessError):
        if cache_only:
            print('Environment cache missing/invalid; defer full installation until pip cache recovery.')
            return False
        print('Environment cache missing/invalid; rebuilding all locked dependencies.')
        if directory.exists():shutil.rmtree(directory)
        subprocess.run([sys.executable,'-m','venv',str(directory)],check=True)
    python=str(directory/'bin/python')
    subprocess.run([python,'-m','pip','install','--extra-index-url',
        'https://download.pytorch.org/whl/cpu','-r',str(LOCK)],check=True)
    subprocess.run([python,str(ROOT/'scripts/verify_production_dependencies.py'),str(LOCK)],check=True)
    subprocess.run([python,'-c','import matplotlib.font_manager'],check=True)
    if os.environ.get('GITHUB_PATH'):
        with open(os.environ['GITHUB_PATH'],'a') as f:f.write(str(directory/'bin')+'\n')
    return True


def seal():
    assert os.environ['GITHUB_REF']=='refs/heads/main' and os.environ['GITHUB_EVENT_NAME'] in ('push','schedule','workflow_dispatch')
    directory=environment_path();info=descriptor()
    # Never seal/cache a PR-produced directory. This workflow starts fresh.
    marker=dict(schema=1,descriptor=info,key=cache_key(info),files_sha256=files_digest(directory),
        source_commit=os.environ['GITHUB_SHA'],source_run=os.environ['GITHUB_RUN_ID'])
    (directory/MARKER).write_text(json.dumps(marker,sort_keys=True)+'\n')
    validate(directory,info)


def prune():
    assert os.environ['GITHUB_REF']=='refs/heads/main'
    repo=os.environ['GITHUB_REPOSITORY']
    result=subprocess.check_output(['gh','api',f'repos/{repo}/actions/caches?ref=refs/heads/main&key={PREFIX}&per_page=100'],text=True)
    for cache in json.loads(result)['actions_caches']:
        if cache['key'].startswith(PREFIX):
            subprocess.run(['gh','api','--method','DELETE',f"repos/{repo}/actions/caches/{cache['id']}"],check=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['key','prepare','prepare-cache','seal','prune']);args=parser.parse_args()
    if args.command=='key':
        key=cache_key(descriptor());print(key)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('key='+key+'\n')
    elif args.command=='prepare':prepare()
    elif args.command=='prepare-cache':
        ready=prepare(cache_only=True)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('ready='+str(ready).lower()+'\n')
    elif args.command=='seal':seal()
    else:prune()

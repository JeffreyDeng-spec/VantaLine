"""Publish full CI receipts and conservatively reuse them after an exact-tree merge.

No artifact code is executed. GitHub job/run state is authoritative; any discovery
failure selects a complete test run. The outer process enforces the 20s deadline.
"""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

from backend_ci import ROOT, digest, load_manifest, validate_reports

OTHER_JOBS = ['artifact-storage', 'doc-image-runtime', 'source-safety',
              'release-package', 'documentation', 'frontend', 'codex-comparison']
FULL_JOBS = ['ci-mode', *OTHER_JOBS, *[f'backend-shard-{i}' for i in range(12)], 'backend-plc']
POLICY_FILES = ['requirements-production.lock', 'scripts/ci_evidence.py',
    'scripts/ci_environment.py', 'scripts/backend_ci.py', 'scripts/backend_ci_manifest.json',
    'scripts/backend_ci_baseline.sha256', 'scripts/verify_production_dependencies.py']


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def policy_hash(commit):
    paths = sorted(set(POLICY_FILES + git('ls-tree', '-r', '--name-only', commit,
                                        '.github/workflows').splitlines()))
    blobs = [(p, git('rev-parse', f'{commit}:{p}')) for p in paths]
    return hashlib.sha256(json.dumps(blobs).encode()).hexdigest()


def utc(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def validate_jobs(jobs, attempt, publishing=False):
    rows = jobs['jobs']
    expected = set(FULL_JOBS) - ({'backend-plc'} if publishing else set())
    selected = [j for j in rows if j['name'] in expected]
    assert len(selected) == len(expected) and {j['name'] for j in selected} == expected, 'missing/duplicate CI job'
    assert all(j['status'] == 'completed' and j['conclusion'] == 'success'
               and j['run_attempt'] == int(attempt) for j in selected), 'unsuccessful/partial-rerun CI'
    assert not {j['name'] for j in rows} - set(FULL_JOBS), 'unexpected CI job inventory'


def validate_needs(needs, mode):
    expected={'ci-mode','backend-shards',*OTHER_JOBS}
    assert set(needs)==expected, 'missing/unexpected gate dependency'
    verified={'ci-mode','frontend','source-safety'}
    assert all(v['result']==('success' if mode=='full' or k in verified else 'skipped')
               for k,v in needs.items()), 'unsuccessful gate dependency'


def publish(directory, jobs_file, needs):
    validate_needs(needs,'full')
    jobs = json.loads(jobs_file.read_text())
    validate_jobs(jobs, os.environ['GITHUB_RUN_ATTEMPT'], publishing=True)
    manifest = load_manifest()
    reports = [json.loads(p.read_text()) for p in sorted(directory.glob('shard-*.json'), key=lambda p:int(p.stem.split('-')[-1]))]
    sha = os.environ['GITHUB_SHA']
    assert git('rev-parse', 'HEAD') == sha
    validate_reports(manifest, reports, 'success', sha, os.environ['GITHUB_RUN_ID'],
                     os.environ['GITHUB_RUN_ATTEMPT'])
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    pr = event.get('pull_request')
    receipt = dict(schema=1, repository=os.environ['GITHUB_REPOSITORY'],
        repository_id=int(os.environ['GITHUB_REPOSITORY_ID']), event=os.environ['GITHUB_EVENT_NAME'],
        pr_number=pr['number'] if pr else None, head_sha=pr['head']['sha'] if pr else sha,
        base_sha=pr['base']['sha'] if pr else None, tested_sha=sha,
        tree=git('rev-parse', 'HEAD^{tree}'), parent=git('rev-parse', 'HEAD^'),
        policy_hash=policy_hash(sha), manifest_sha256=digest(manifest),
        workflow_blob=git('rev-parse', 'HEAD:.github/workflows/ci.yml'),
        run_id=int(os.environ['GITHUB_RUN_ID']), run_attempt=int(os.environ['GITHUB_RUN_ATTEMPT']),
        created_at=datetime.now(timezone.utc).isoformat(), jobs=FULL_JOBS,
        environments=[r['environment'] for r in reports])
    (directory/'ci-evidence.json').write_text(json.dumps(receipt, indent=2)+'\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as summary:
            summary.write('\n### All ordinary CI jobs\n\n| Job | Seconds including setup |\n|---|---:|\n')
            for job in jobs['jobs']:
                if job.get('completed_at'):
                    seconds=(utc(job['completed_at'])-utc(job['started_at'])).total_seconds()
                    summary.write(f"| {job['name']} | {seconds:.0f} |\n")


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, url):
        assert urllib.parse.urlparse(url).scheme == 'https', 'non-HTTPS redirect'
        redirected = super().redirect_request(request, fp, code, msg, headers, url)
        if urllib.parse.urlparse(request.full_url).netloc != urllib.parse.urlparse(url).netloc:
            redirected.remove_header('Authorization')
        return redirected


class GitHub:
    def __init__(self):
        self.base = os.environ.get('GITHUB_API_URL', 'https://api.github.com').rstrip('/')
        self.repo = os.environ['GITHUB_REPOSITORY']
        self.opener = urllib.request.build_opener(SafeRedirect())

    def raw(self, path):
        url = self.base + '/repos/' + self.repo + '/' + path
        request = urllib.request.Request(url, headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],
            'Accept':'application/vnd.github+json', 'User-Agent':'VantaLine-CI-evidence'})
        with self.opener.open(request, timeout=5) as response:
            data = response.read(2*1024*1024+1)
        assert len(data) <= 2*1024*1024, 'oversized evidence/API response'
        return data

    def get(self, path):
        return json.loads(self.raw(path))


def read_bundle(data, artifact):
    assert artifact.get('digest') == 'sha256:'+hashlib.sha256(data).hexdigest(), 'artifact digest mismatch'
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        expected = {'ci-evidence.json', *[f'shard-{i}.json' for i in range(12)]}
        names = archive.namelist()
        assert len(names) == 13 and set(names) == expected, 'unexpected evidence files'
        assert sum(i.file_size for i in archive.infolist()) <= 2*1024*1024, 'oversized expanded evidence'
        receipt = json.loads(archive.read('ci-evidence.json'))
        reports = [json.loads(archive.read(f'shard-{i}.json')) for i in range(12)]
    return receipt, reports


def validate_receipt(receipt, reports, run, jobs, artifact, pr, context, now):
    assert run['event'] == 'pull_request' and run['status'] == 'completed' and run['conclusion'] == 'success'
    assert run['path'] == '.github/workflows/ci.yml' and run['head_repository']['id'] == context['repository_id']
    assert pr['state'] == 'closed' and pr['merged_at'] and pr['merge_commit_sha'] == context['main_sha']
    assert pr['base']['ref'] == 'main' and pr['head']['repo']['id'] == context['repository_id']
    assert run['head_sha'] == pr['head']['sha'] == receipt['head_sha'], 'wrong final PR head'
    assert receipt['schema'] == 1 and receipt['event'] == 'pull_request'
    assert receipt['repository'] == context['repository'] and receipt['repository_id'] == context['repository_id']
    assert receipt['pr_number'] == pr['number'] and receipt['run_id'] == run['id']
    assert receipt['run_attempt'] == run['run_attempt'] and receipt['jobs'] == FULL_JOBS
    assert receipt['tree'] == context['tree'] and receipt['parent'] == context['parent']
    assert receipt['base_sha'] == context['parent'], 'changed base or rebase merge'
    assert receipt['policy_hash'] == context['policy_hash'] and receipt['workflow_blob'] == context['workflow_blob']
    assert receipt['manifest_sha256'] == digest(context['manifest'])
    assert 0 <= (now-utc(run['updated_at'])).total_seconds() <= 86400, 'expired source run'
    assert 0 <= (now-utc(receipt['created_at'])).total_seconds() <= 86400, 'expired receipt'
    assert utc(receipt['created_at']) <= utc(run['updated_at'])
    assert artifact['name'] == f"ci-evidence-{run['run_attempt']}" and not artifact['expired']
    assert artifact['workflow_run']['id'] == run['id'] and artifact['workflow_run']['head_sha'] == run['head_sha']
    validate_jobs(jobs, run['run_attempt'])
    validate_reports(context['manifest'], reports, 'success', receipt['tested_sha'], str(run['id']), str(run['run_attempt']))
    assert len(receipt['environments']) == 12
    assert receipt['environments'] == [r['environment'] for r in reports]
    assert all(e['python'].startswith('3.10.') and e['runner_os']=='Linux' for e in receipt['environments'])


def context():
    sha = os.environ['GITHUB_SHA']
    assert git('rev-parse', 'HEAD') == sha, 'checkout mismatch'
    parent = git('rev-parse', 'HEAD^')
    current_policy = policy_hash(sha)
    assert current_policy == policy_hash(parent), 'CI/dependency policy changed: full initialization required'
    return dict(repository=os.environ['GITHUB_REPOSITORY'], repository_id=int(os.environ['GITHUB_REPOSITORY_ID']),
        main_sha=sha, parent=parent, parents=git('rev-parse','HEAD^@').splitlines(),
        message=git('log','-1','--format=%B'), tree=git('rev-parse','HEAD^{tree}'), policy_hash=current_policy,
        workflow_blob=git('rev-parse','HEAD:.github/workflows/ci.yml'), manifest=load_manifest())


def validate_merge_shape(main, head_sha, head_message):
    parents=main['parents']
    if len(parents)==2:
        assert parents[1]==head_sha, 'merge second parent is not final PR head'
    else:
        assert len(parents)==1 and main['main_sha']!=head_sha
        # GitHub rebase preserves the final head commit message. Ambiguous/custom
        # squash messages conservatively fall back instead of guessing the method.
        assert main['message']!=head_message.strip(), 'rebase/ambiguous squash: full tests required'


def select_run(runs, head_sha):
    assert runs, 'no final-head CI'
    run=max(runs,key=lambda r:(r['run_number'],r['run_attempt']))
    assert run['head_sha']==head_sha and run['event']=='pull_request'
    assert run['status']=='completed' and run['conclusion']=='success', 'latest CI is not successful'
    return run


def resolve(output):
    c = context()
    api = GitHub()
    prs = api.get(f"commits/{c['main_sha']}/pulls")
    candidates = [p for p in prs if p.get('merged_at') and p['merge_commit_sha']==c['main_sha']]
    assert len(candidates) == 1, 'ambiguous/missing merged PR'
    pr = api.get(f"pulls/{candidates[0]['number']}")
    assert pr['head']['repo']['id'] == c['repository_id'], 'fork: full tests required'
    runs = api.get('actions/workflows/ci.yml/runs?'+urllib.parse.urlencode(
        dict(event='pull_request', head_sha=pr['head']['sha'], per_page=5)))['workflow_runs']
    # Newest run only; never select older success to mask failure or a partial rerun.
    run = select_run(runs, pr['head']['sha'])
    head_commit=api.get(f"git/commits/{pr['head']['sha']}")
    validate_merge_shape(c,pr['head']['sha'],head_commit['message'])
    artifacts = api.get(f"actions/runs/{run['id']}/artifacts?per_page=100")['artifacts']
    artifacts = [a for a in artifacts if a['name']==f"ci-evidence-{run['run_attempt']}"]
    assert len(artifacts) == 1, 'missing/duplicate current-attempt evidence'
    artifact = artifacts[0]
    receipt, reports = read_bundle(api.raw(f"actions/artifacts/{artifact['id']}/zip"), artifact)
    jobs = api.get(f"actions/runs/{run['id']}/jobs?filter=latest&per_page=100")
    # Verify the actual checkout commit from GitHub, not just the artifact's claim.
    commit = api.get(f"git/commits/{receipt['tested_sha']}")
    assert commit['tree']['sha'] == c['tree'] and commit['parents'][0]['sha'] == c['parent']
    validate_receipt(receipt, reports, run, jobs, artifact, pr, c, datetime.now(timezone.utc))
    proof = dict(mode='reuse', main_sha=c['main_sha'], policy_hash=c['policy_hash'],
        current_run=os.environ['GITHUB_RUN_ID'], current_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
        source_run=run['id'], source_attempt=run['run_attempt'], tree=c['tree'], jobs=FULL_JOBS)
    output.write_text(json.dumps(proof))


def prepare(force_full=False, cold=False):
    proof = dict(mode='full', reason='PR/manual/schedule/forced or rerun')
    if (os.environ['GITHUB_EVENT_NAME']=='push' and os.environ.get('GITHUB_REF')=='refs/heads/main'
        and os.environ['GITHUB_RUN_ATTEMPT']=='1' and not force_full and not cold):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'proof.json'
            process = subprocess.Popen([sys.executable, __file__, 'resolve', '--output', str(path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                out, err = process.communicate(timeout=20)
                if process.returncode == 0:
                    proof = json.loads(path.read_text())
                else:
                    proof['reason'] = 'source evidence unavailable or invalid; complete tests required'
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL);process.communicate()
                proof['reason'] = '20-second discovery deadline; complete tests required'
    encoded = base64.b64encode(json.dumps(proof).encode()).decode()
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:
            f.write(f"mode={proof['mode']}\nproof={encoded}\n")
    print(json.dumps(proof, sort_keys=True))


def assert_reuse(check):
    proof = json.loads(base64.b64decode(os.environ['CI_REUSE_PROOF'], validate=True))
    assert proof['mode']=='reuse' and check in ('frontend','source-safety','backend-plc')
    assert proof['main_sha']==os.environ['GITHUB_SHA'] == git('rev-parse','HEAD')
    assert proof['current_run']==os.environ['GITHUB_RUN_ID'] and proof['current_attempt']==os.environ['GITHUB_RUN_ATTEMPT']
    assert proof['tree']==git('rev-parse','HEAD^{tree}') and proof['policy_hash']==policy_hash('HEAD')
    assert proof['jobs']==FULL_JOBS and proof['source_run'] and proof['source_attempt']
    if check=='backend-plc':
        validate_needs(json.loads(os.environ['CI_NEEDS']),'reuse')
        (ROOT/'reuse-evidence.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(f"{check}: verified full PR CI {proof['source_run']} attempt {proof['source_attempt']}; exact tree {proof['tree']}")


if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--force-full',action='store_true');p.add_argument('--cold-cache',action='store_true')
    p=sub.add_parser('resolve');p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('publish');p.add_argument('--results',type=Path,required=True);p.add_argument('--jobs',type=Path,required=True)
    p=sub.add_parser('assert-reuse');p.add_argument('--check',required=True)
    args=parser.parse_args()
    if args.command=='prepare':prepare(args.force_full,args.cold_cache)
    elif args.command=='resolve':resolve(args.output)
    elif args.command=='publish':publish(args.results,args.jobs,json.loads(os.environ['CI_NEEDS']))
    else:assert_reuse(args.check)

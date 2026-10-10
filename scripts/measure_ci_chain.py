"""Read GitHub runs and account for a real PR -> main -> immutable release chain.

No deployment or production state changes. Queueing after the PR's initial start
and every workflow handoff count; human merge waiting is reported separately.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
from ci_evidence import validate_jobs


def api(repo, path):
    return json.loads(subprocess.check_output(['gh','api',f'repos/{repo}/{path}'],text=True))


def instant(value):
    return datetime.fromisoformat(value.replace('Z','+00:00'))


def interval(start, end):
    seconds=(instant(end)-instant(start)).total_seconds()
    assert seconds>=0, 'inconsistent event order'
    return seconds


def window(jobs):
    assert jobs and all(j['status']=='completed' for j in jobs)
    timed=[j for j in jobs if j.get('started_at') and j.get('completed_at')]
    assert timed, 'missing timing evidence'
    return min(j['started_at'] for j in timed),max(j['completed_at'] for j in timed)


def calculate(pr, main, release, pr_jobs, main_jobs, release_jobs, merged_at):
    pr_start,pr_end=window(pr_jobs)
    main_start,main_end=window(main_jobs)
    release_start,release_end=window(release_jobs)
    human=interval(pr_end,merged_at)
    initial_queue=interval(pr['created_at'],pr_start)
    raw=interval(pr['created_at'],release_end)
    stages=dict(pr_full=interval(pr_start,pr_end),main=interval(main['created_at'],main_end),
        release=interval(release['created_at'],release_end),
        handoff=interval(merged_at,main['created_at'])+interval(main_end,release['created_at']))
    total=raw-human-initial_queue
    assert total==sum(stages.values()), 'chain accounting mismatch'
    return dict(schema=1,seconds=stages,total_seconds=total,raw_seconds=raw,
        excluded_human_seconds=human,excluded_initial_pr_queue_seconds=initial_queue,
        subsequent_initial_queue_seconds=dict(main=interval(main['created_at'],main_start),
            release=interval(release['created_at'],release_start)),
        passed_budgets=dict(pr_full=stages['pr_full']<=170,main=stages['main']<=30,
            release=stages['release']<=90,handoff=stages['handoff']<=10,total=total<=300))


def measure(repo, pr_id, main_id, release_id):
    runs=[api(repo,f'actions/runs/{n}') for n in (pr_id,main_id,release_id)]
    pr,main,release=runs
    assert all(r['status']=='completed' and r['conclusion']=='success' for r in runs)
    assert pr['event']=='pull_request' and pr['path']==main['path']=='.github/workflows/ci.yml'
    assert main['event']=='push' and main['head_branch']=='main'
    assert release['path']=='.github/workflows/release-production.yml' and release['event']=='workflow_run'
    assert main['head_sha']==release['head_sha'], 'release/main commit mismatch'
    linked=[p for p in api(repo,f"commits/{main['head_sha']}/pulls") if p.get('merged_at') and p['merge_commit_sha']==main['head_sha']]
    assert len(linked)==1
    pull=api(repo,f"pulls/{linked[0]['number']}")
    assert pull['head']['sha']==pr['head_sha'] and pull['head']['repo']['id']==main['repository']['id']
    jobs=[api(repo,f"actions/runs/{r['id']}/attempts/{r['run_attempt']}/jobs?per_page=100") for r in runs]
    validate_jobs(jobs[0],pr['run_attempt'])
    assert all(j['conclusion']=='success' for j in jobs[2]['jobs'])
    result=calculate(pr,main,release,*(j['jobs'] for j in jobs),pull['merged_at'])
    result.update(repository=repo,pr_number=pull['number'],main_sha=main['head_sha'],
        runs=[dict(id=r['id'],attempt=r['run_attempt']) for r in runs])
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repository',required=True)
    p.add_argument('--pr-run',required=True,type=int);p.add_argument('--main-run',required=True,type=int)
    p.add_argument('--release-run',required=True,type=int);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();result=measure(a.repository,a.pr_run,a.main_run,a.release_run)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,sort_keys=True))

"""Exact-tree reuse acceptance and negative provider/artifact/provenance fixtures."""
import base64
import copy
from datetime import datetime,timedelta,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch
import zipfile
import ci_evidence as ci


class EvidenceContract(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,11,tzinfo=timezone.utc)
        self.manifest=ci.load_manifest()
        self.context=dict(repository='owner/repo',repository_id=1,main_sha='main',tree='tree',parent='base',policy_hash='policy',workflow_blob='workflow',manifest=self.manifest)
        self.pr=dict(state='closed',merged_at=self.now.isoformat(),merge_commit_sha='main',number=2,base={'ref':'main'},head={'sha':'head','repo':{'id':1}})
        self.run=dict(id=3,event='pull_request',status='completed',conclusion='success',path='.github/workflows/ci.yml',head_repository={'id':1},head_sha='head',run_attempt=1,updated_at=self.now.isoformat())
        self.artifact=dict(name='ci-evidence-1',expired=False,workflow_run={'id':3,'head_sha':'head'})
        self.jobs={'jobs':[dict(name=name,run_attempt=1,status='completed',conclusion='success') for name in ci.FULL_JOBS]}
        self.reports=[dict(schema=1,manifest_sha256=ci.digest(self.manifest),shard=n,commit='tested',run_id='3',run_attempt='1',completed_at='now',status='success',environment=dict(python='3.10.22',runner_os='Linux',image='image',architecture='X64'),commands=[dict(id=e['id'],status='success',returncode=0,seconds=1) for e in self.manifest['checks'] if e['shard']==n]) for n in range(12)]
        self.receipt=dict(schema=1,event='pull_request',repository='owner/repo',repository_id=1,pr_number=2,head_sha='head',base_sha='base',tested_sha='tested',tree='tree',parent='base',policy_hash='policy',workflow_blob='workflow',manifest_sha256=ci.digest(self.manifest),run_id=3,run_attempt=1,created_at=self.now.isoformat(),jobs=ci.FULL_JOBS,environments=[r['environment'] for r in self.reports])

    def check(self):
        ci.validate_receipt(self.receipt,self.reports,self.run,self.jobs,self.artifact,self.pr,self.context,self.now)

    def test_merge_and_squash_use_tree_and_first_parent_not_equal_commit_sha(self):
        self.check()
        self.context['main_sha']='different-squash';self.pr['merge_commit_sha']='different-squash';self.check()

    def test_failures_cannot_reuse(self):
        mutations=[
            lambda:self.context.update(tree='different'),lambda:self.context.update(parent='rebase'),
            lambda:self.context.update(policy_hash='different'),lambda:self.context.update(workflow_blob='different'),
            lambda:self.pr['head'].update(sha='new-head'),lambda:self.pr['head']['repo'].update(id=9),
            lambda:self.pr.update(merge_commit_sha='other'),lambda:self.pr.update(merged_at=None),
            lambda:self.run.update(conclusion='failure'),lambda:self.run.update(conclusion='cancelled'),
            lambda:self.run.update(status='in_progress'),lambda:self.run.update(event='workflow_dispatch'),
            lambda:self.run.update(path='other.yml'),lambda:self.run.update(run_attempt=2),
            lambda:self.jobs['jobs'].pop(),lambda:self.jobs['jobs'].append(copy.deepcopy(self.jobs['jobs'][0])),
            lambda:self.jobs['jobs'][0].update(run_attempt=0),lambda:self.jobs['jobs'][0].update(conclusion='skipped'),
            lambda:self.artifact.update(expired=True),lambda:self.artifact.update(name='ci-evidence-0'),
            lambda:self.artifact['workflow_run'].update(id=9),lambda:self.artifact['workflow_run'].update(head_sha='old'),
            lambda:self.receipt.update(created_at=(self.now-timedelta(hours=25)).isoformat()),
            lambda:self.receipt.update(created_at=(self.now+timedelta(seconds=1)).isoformat()),
            lambda:self.receipt.update(base_sha='old-base'),lambda:self.receipt.update(repository_id=9),
            lambda:self.receipt.update(manifest_sha256='different'),lambda:self.receipt.update(jobs=[]),
            lambda:self.reports[0]['commands'].pop(),lambda:self.reports[0]['commands'][0].update(returncode=7),
            lambda:self.reports[0].update(commit='old'),lambda:self.reports[0].update(run_attempt='0'),
            lambda:self.receipt['environments'][0].update(python='3.11.0')]
        for index,mutate in enumerate(mutations):
            self.setUp();mutate()
            with self.subTest(index=index),self.assertRaises((AssertionError,KeyError)):self.check()

    def test_latest_failed_or_partial_run_never_uses_older_green(self):
        old={**self.run,'run_number':1}
        for changed in ({'conclusion':'failure'},{'status':'in_progress'},{'conclusion':'cancelled'}):
            newer={**old,'run_number':2,**changed}
            with self.assertRaises(AssertionError):ci.select_run([old,newer],'head')
        partial={**old,'run_attempt':2,'conclusion':'failure'}
        with self.assertRaises(AssertionError):ci.select_run([old,partial],'head')

    def test_merge_shape_rejects_rebase_and_ambiguous_squash(self):
        ci.validate_merge_shape(dict(main_sha='merged',parents=['base','head'],message='Merge PR'),'head','Original')
        ci.validate_merge_shape(dict(main_sha='squashed',parents=['base'],message='Feature (#2)'),'head','Original')
        for main in (dict(main_sha='head',parents=['base'],message='Original'),dict(main_sha='rebased',parents=['base'],message='Original'),dict(main_sha='merged',parents=['base','wrong'],message='Merge')):
            with self.assertRaises(AssertionError):ci.validate_merge_shape(main,'head','Original')

    def test_expired_provider_run(self):
        self.run['updated_at']=(self.now-timedelta(hours=25)).isoformat()
        with self.assertRaises(AssertionError):self.check()

    def test_digest_and_archive_identity(self):
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as z:
            z.writestr('ci-evidence.json',json.dumps(self.receipt))
            for report in self.reports:z.writestr(f"shard-{report['shard']}.json",json.dumps(report))
        data=output.getvalue();artifact={'digest':'sha256:'+hashlib.sha256(data).hexdigest()}
        self.assertEqual(ci.read_bundle(data,artifact)[0]['tree'],'tree')
        with self.assertRaises(AssertionError):ci.read_bundle(data+b'corrupt',artifact)
        extra=io.BytesIO()
        with zipfile.ZipFile(extra,'w') as z:z.writestr('../executable.py','not executed')
        with self.assertRaises(AssertionError):ci.read_bundle(extra.getvalue(),{'digest':'sha256:'+hashlib.sha256(extra.getvalue()).hexdigest()})

    def test_manual_schedule_pr_cold_force_and_rerun_are_full(self):
        base=dict(GITHUB_EVENT_NAME='push',GITHUB_REF='refs/heads/main',GITHUB_RUN_ATTEMPT='1')
        cases=[({'GITHUB_EVENT_NAME':'pull_request'},{}),({'GITHUB_EVENT_NAME':'schedule'},{}),
            ({'GITHUB_EVENT_NAME':'workflow_dispatch'},{}),({'GITHUB_RUN_ATTEMPT':'2'},{}),({},dict(force_full=True)),({},dict(cold=True))]
        with tempfile.TemporaryDirectory() as temp:
            for overrides,flags in cases:
                output=Path(temp)/'out';output.write_text('')
                with patch.dict(os.environ,{**base,**overrides,'GITHUB_OUTPUT':str(output)},clear=True),patch.object(ci.subprocess,'Popen') as spawn:
                    ci.prepare(**flags);spawn.assert_not_called()
                self.assertIn('mode=full',output.read_text())

    def test_api_failure_selects_full_without_false_green(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'out';output.write_text('')
            env=dict(GITHUB_EVENT_NAME='push',GITHUB_REF='refs/heads/main',GITHUB_RUN_ATTEMPT='1',GITHUB_OUTPUT=str(output))
            with patch.dict(os.environ,env,clear=True),patch.object(ci.subprocess,'Popen') as spawn:
                spawn.return_value.communicate.return_value=(b'',b'API failure');spawn.return_value.returncode=1
                ci.prepare()
            self.assertIn('mode=full',output.read_text())

    def test_hard_discovery_deadline_kills_lookup_and_falls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'out'
            env=dict(GITHUB_EVENT_NAME='push',GITHUB_REF='refs/heads/main',GITHUB_RUN_ATTEMPT='1',GITHUB_OUTPUT=str(output))
            with patch.dict(os.environ,env,clear=True),patch.object(ci.subprocess,'Popen') as spawn,patch.object(ci.os,'killpg') as kill:
                spawn.return_value.pid=123
                spawn.return_value.communicate.side_effect=[subprocess.TimeoutExpired('lookup',20),(b'',b'')]
                ci.prepare();kill.assert_called_once_with(123,ci.signal.SIGKILL)
                self.assertEqual(spawn.return_value.communicate.call_args_list[0].kwargs['timeout'],20)
            self.assertIn('mode=full',output.read_text())

    def test_each_required_reuse_check_rejects_wrong_current_binding(self):
        proof=dict(mode='reuse',main_sha='main',current_run='9',current_attempt='1',tree='tree',policy_hash='policy',jobs=ci.FULL_JOBS,source_run=3,source_attempt=1)
        env=dict(GITHUB_SHA='main',GITHUB_RUN_ID='9',GITHUB_RUN_ATTEMPT='1')
        for check in ('frontend','source-safety','backend-plc'):
            for field in ('main_sha','current_run','current_attempt','tree','policy_hash','jobs','source_run','source_attempt'):
                changed=dict(proof);changed[field]=[] if field=='jobs' else ''
                with self.subTest(check=check,field=field),patch.dict(os.environ,{**env,'CI_REUSE_PROOF':base64.b64encode(json.dumps(changed).encode()).decode()},clear=True),patch.object(ci,'git',side_effect=lambda *args:'tree' if args[-1]=='HEAD^{tree}' else 'main'),patch.object(ci,'policy_hash',return_value='policy'),self.assertRaises(AssertionError):
                    ci.assert_reuse(check)

    def test_publisher_never_accepts_failed_cancelled_missing_or_skipped_needs(self):
        for result in ('failure','cancelled','skipped',''):
            with self.subTest(result=result),self.assertRaises(AssertionError):
                ci.publish(Path('/unused'),Path('/unused'),{'frontend':{'result':result}})

    def test_full_and_reuse_gates_require_exact_current_dependency_results(self):
        names={'ci-mode','backend-shards',*ci.OTHER_JOBS}
        for mode in ('full','reuse'):
            needs={n:{'result':'success' if mode=='full' or n in ('ci-mode','frontend','source-safety') else 'skipped'} for n in names}
            ci.validate_needs(needs,mode)
            for n in names:
                missing=copy.deepcopy(needs);missing.pop(n)
                with self.assertRaises(AssertionError):ci.validate_needs(missing,mode)
                for result in ('failure','cancelled',''):
                    bad=copy.deepcopy(needs);bad[n]['result']=result
                    with self.assertRaises(AssertionError):ci.validate_needs(bad,mode)

    def test_cross_host_redirect_does_not_leak_token(self):
        import urllib.request
        request=urllib.request.Request('https://api.github.com/archive',headers={'Authorization':'Bearer synthetic'})
        redirected=ci.SafeRedirect().redirect_request(request,None,302,'',{},'https://blob.example/archive')
        self.assertIsNone(redirected.get_header('Authorization'))


if __name__=='__main__':unittest.main()

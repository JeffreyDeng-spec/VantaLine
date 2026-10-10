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
        self.context=dict(repository='owner/repo',repository_id=1,main_sha='main',tree='tree',parent='base',policy_hash='policy',workflow_blob='workflow',manifest=self.manifest,lock_sha256='lock')
        self.pr=dict(state='closed',merged_at=self.now.isoformat(),merge_commit_sha='main',number=2,base={'ref':'main'},head={'sha':'head','repo':{'id':1}})
        self.run=dict(id=3,event='pull_request',status='completed',conclusion='success',path='.github/workflows/ci.yml',head_repository={'id':1},head_sha='head',run_attempt=1,updated_at=self.now.isoformat())
        self.artifact=dict(name='ci-evidence-1',expired=False,workflow_run={'id':3,'head_sha':'head'})
        self.jobs={'jobs':[dict(id=index+1,name=name,run_attempt=1,status='completed',conclusion='success',started_at=self.now.isoformat(),completed_at=self.now.isoformat()) for index,name in enumerate(ci.FULL_JOBS)]}
        self.reports=[dict(schema=1,manifest_sha256=ci.digest(self.manifest),shard=n,commit='tested',run_id='3',run_attempt='1',completed_at='now',status='success',environment=dict(python='3.10.22',runner_os='Linux',image='image',architecture='X64',postgresql='postgres (PostgreSQL) 16.10',lock_sha256='lock'),commands=[dict(id=e['id'],status='success',returncode=0,seconds=1) for e in self.manifest['checks'] if e['shard']==n]) for n in range(12)]
        self.receipt=dict(schema=1,event='pull_request',repository='owner/repo',repository_id=1,pr_number=2,head_sha='head',base_sha='base',tested_sha='tested',tree='tree',parent='base',policy_hash='policy',workflow_blob='workflow',manifest_sha256=ci.digest(self.manifest),run_id=3,run_attempt=1,created_at=self.now.isoformat(),jobs=ci.FULL_JOBS,environments=[r['environment'] for r in self.reports])

        from backend_ci import performance_plan
        from ci_performance_evidence import PROTOCOL_SHA256
        from verify_refactor_performance_protocol import BASELINE, MANUAL
        plan=performance_plan(self.manifest)
        self.receipt['performance']=dict(schema=1,manifest_sha256=ci.digest(self.manifest),status='success',completed_at='now',not_run=[],commit='tested',run_id='3',run_attempt='1',
            commands=[{**e,'status':'success','returncode':0,'seconds':1} for e in plan],
            raw_logs=[dict(path=e['id']+'.log',bytes=1,sha256='a'*64) for e in plan],
            numeric_protocols=dict(original_raw=54,original_rounded=2,beta=16,storage_snapshots=2),
            job_id=next(j['id'] for j in self.jobs['jobs'] if j['name']=='backend-performance'))
        files={}
        for name,ready in [('legacy-projection.json',True),('manual-history.json',False)]:
            cases=[]
            for mode,rep,size in [('AA',0,1000)]+[('AB',r,n) for r in (1,2,3) for n in (1000,10000)]:
                obs=[dict(python_cpu_seconds=0,gc_collections=[0,0,0]) for _ in range(31)]
                cases.append(dict(mode=mode,repetition=rep,tasks=size,fixture='ManualFixture',manual_baseline_sha256=MANUAL,tasks_baseline_sha256=BASELINE,
                    comparison='manual full first page versus frozen tasks and complete manual helper',populations={n:size for n in ('standards','sessions','pages','assets')},derived_published=ready,
                    old_queries=10,new_queries=10 if mode=='AA' else 7 if ready else 12,samples=31,
                    old_seconds=[1]*31,new_seconds=[1]*31,old_p95_seconds=1,new_p95_seconds=1,
                    old_peak_bytes=100,new_peak_bytes=100,old_peak_samples=[100]*3,new_peak_samples=[100]*3,
                    latency_limit=1.25,memory_limit=1048676,old_observations=obs,new_observations=obs))
            rows=cases+[dict(protocol='manual-history-repeated-v1',planned_aa_cases=1,planned_ab_cases=6,groups=[{**{k:e[k] for k in ('mode','repetition','tasks')},'status':'passed'} for e in cases])]
            files[name]=dict(rows=rows,bytes=1,sha256='b'*64)
        self.receipt['manual']=dict(files=files,artifact=dict(id=4,name='manual-history-performance-1',digest='sha256:'+'c'*64,expired=False,workflow_run={'id':3},created_at=self.now.isoformat()),raw_log=dict(bytes=1,sha256='d'*64),job_id=next(j['id'] for j in self.jobs['jobs'] if j['name']=='manual-history-performance'))

    def check(self):
        ci.validate_receipt(self.receipt,self.reports,self.run,self.jobs,self.artifact,self.pr,self.context,self.now)

    def test_both_performance_jobs_are_mandatory_current_attempt(self):
        for name in ('backend-performance','manual-history-performance'):
            for conclusion in ('failure','cancelled','skipped',None):
                self.setUp()
                next(j for j in self.jobs['jobs'] if j['name']==name)['conclusion']=conclusion
                with self.subTest(name=name,conclusion=conclusion),self.assertRaises(AssertionError):self.check()
            self.setUp()
            next(j for j in self.jobs['jobs'] if j['name']==name)['run_attempt']=0
            with self.assertRaises(AssertionError):self.check()

    def test_performance_commands_and_producers_fail_closed(self):
        mutations=[lambda p:p.update(commit='old'),lambda p:p.update(run_attempt='0'),
            lambda p:p.update(manifest_sha256='old'),lambda p:p.update(status='failed'),
            lambda p:p.update(not_run=['benchmark']),lambda p:p['commands'].pop(),
            lambda p:p['commands'].reverse(),lambda p:p['commands'].append(copy.deepcopy(p['commands'][0])),
            lambda p:p['commands'][0].update(returncode=124),lambda p:p['commands'][0].update(status='skipped'),
            lambda p:p['commands'][0].update(env={'VANTALINE_POSTGRES_DSN':'wrong'}),
            lambda p:p['commands'][0].update(run='exit 0'),lambda p:p.update(job_id=-1),
            lambda p:p['raw_logs'].pop(),lambda p:p['numeric_protocols'].update(beta=15)]
        for index,mutate in enumerate(mutations):
            self.setUp();mutate(self.receipt['performance'])
            with self.subTest(index=index),self.assertRaises((AssertionError,KeyError)):self.check()

    def test_manual_complete_raw_protocol_is_required_for_reuse(self):
        mutations=[lambda m:m['files'].pop('manual-history.json'),
            lambda m:m['files']['legacy-projection.json']['rows'].pop(),
            lambda m:m['files']['legacy-projection.json']['rows'][0]['old_seconds'].pop(),
            lambda m:m['files']['manual-history.json']['rows'][1].update(new_queries=7),
            lambda m:m['files']['manual-history.json']['rows'][0].update(derived_published=True),
            lambda m:m['files']['manual-history.json']['rows'][0].update(manual_baseline_sha256='old'),
            lambda m:m.update(job_id=-1)]
        for index,mutate in enumerate(mutations):
            self.setUp();mutate(self.receipt['manual'])
            with self.subTest(index=index),self.assertRaises((AssertionError,KeyError,ValueError)):self.check()

    def test_actual_manual_zip_members_and_digest_are_strict(self):
        import ci_performance_evidence as performance
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            for name,item in self.receipt['manual']['files'].items():archive.writestr(name,json.dumps(item['rows']))
        raw=output.getvalue();artifact={'digest':'sha256:'+hashlib.sha256(raw).hexdigest()}
        self.assertEqual(set(performance.read_manual_artifact(raw,artifact)),performance.MANUAL_MEMBERS)
        with self.assertRaises(AssertionError):performance.read_manual_artifact(raw+b'changed',artifact)
        for names in [('legacy-projection.json',),('legacy-projection.json','manual-history.json','extra.json'),
                      ('legacy-projection.json','legacy-projection.json')]:
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w') as archive:
                for name in names:archive.writestr(name,'[]')
            raw=output.getvalue()
            with self.subTest(names=names),self.assertRaises(AssertionError):
                performance.read_manual_artifact(raw,{'digest':'sha256:'+hashlib.sha256(raw).hexdigest()})

    def test_manual_artifact_cannot_predate_current_attempt_producer(self):
        import ci_performance_evidence as performance
        job=next(j for j in self.jobs['jobs'] if j['name']=='manual-history-performance')
        artifact=self.receipt['manual']['artifact']
        performance.validate_manual_producer(artifact,job,3,1)
        for changed in ({'name':'manual-history-performance-0'},
                        {'created_at':(self.now-timedelta(days=1)).isoformat()},
                        {'created_at':(self.now+timedelta(days=1)).isoformat()}):
            with self.subTest(changed=changed),self.assertRaises(AssertionError):
                performance.validate_manual_producer({**artifact,**changed},job,3,1)

    def test_manual_stdout_must_equal_both_actual_json_reports(self):
        import ci_performance_evidence as performance
        manual=self.receipt['manual']
        rows=[r for name in ('legacy-projection.json','manual-history.json') for r in manual['files'][name]['rows']]
        raw='\n'.join(json.dumps(r) for r in rows).encode()
        with tempfile.TemporaryDirectory() as temp:
            performance.validate_manual_raw(raw,manual,Path(temp))
            for changed in (rows[:-1],rows[1:],rows+rows[:1],list(reversed(rows))):
                altered='\n'.join(json.dumps(r) for r in changed).encode()
                with self.assertRaises(AssertionError):performance.validate_manual_raw(altered,manual,Path(temp))

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
            lambda:self.receipt['environments'][0].update(python='3.11.0'),
            lambda:self.receipt['environments'][0].update(postgresql='postgres (PostgreSQL) 17.1'),
            lambda:self.receipt['environments'][0].update(lock_sha256='wrong')]
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

    def test_verifier_exception_or_missing_proof_selects_full(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'out'
            env=dict(GITHUB_EVENT_NAME='push',GITHUB_REF='refs/heads/main',GITHUB_RUN_ATTEMPT='1',GITHUB_OUTPUT=str(output))
            with patch.dict(os.environ,env,clear=True),patch.object(ci.subprocess,'Popen') as spawn:
                spawn.return_value.communicate.return_value=(b'',b'');spawn.return_value.returncode=0
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

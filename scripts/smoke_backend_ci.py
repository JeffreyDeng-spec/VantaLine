"""Fail-closed evidence gate and real executor fault/cleanup tests (stdlib only)."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend_ci import digest, execute, load_manifest, performance, run_shard, validate_reports
import backend_ci


class GateContract(unittest.TestCase):
    def setUp(self):
        self.manifest=load_manifest()
        self.reports=[{'schema':1,'manifest_sha256':digest(self.manifest),'shard':shard,
            'commit':'sha','run_id':'123','run_attempt':'1','completed_at':'now','status':'success',
            'commands':[{'id':e['id'],'status':'success','returncode':0,'seconds':1}
                        for e in self.manifest['checks'] if e['shard']==shard]} for shard in range(12)]

    def check(self,reports=None,result='success'):
        validate_reports(self.manifest,self.reports if reports is None else reports,result,'sha','123','1')

    def test_frozen_inventory_and_refactor_delta_reject_changed_bytes(self):
        import json
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'inventory.json'
            base=json.loads(backend_ci.MANIFEST.read_text())
            for mutate in (lambda m:m['checks'].pop(),lambda m:m['checks'][0].update(env={'WRONG':'1'}),
                           lambda m:m['performance'].reverse()):
                changed=copy.deepcopy(base);mutate(changed);path.write_text(json.dumps(changed))
                with self.assertRaises(AssertionError):load_manifest(path)
            path.write_text(backend_ci.ADDITIONS.read_text()+' ')
            with patch.object(backend_ci,'ADDITIONS',path),self.assertRaises(AssertionError):load_manifest()

    def test_workflow_events_require_literal_on_key(self):
        backend_ci.validate_workflow_trigger('on:\n  workflow_dispatch:\n')
        backend_ci.validate_workflow_trigger("'on':\n  workflow_dispatch:\n")
        for source in ('true:\n  workflow_dispatch:\n','name: No trigger\n',
                       'on:\n  workflow_dispatch:\ntrue: duplicate\n'):
            with self.subTest(source=source),self.assertRaises(AssertionError):backend_ci.validate_workflow_trigger(source)

    def test_reuse_jobs_require_checkout_and_python_before_validator(self):
        import yaml
        workflow=yaml.safe_load((backend_ci.ROOT/'.github/workflows/ci.yml').read_text())
        backend_ci.validate_reuse_bootstrap(workflow)
        for name in ('frontend','source-safety','backend-plc'):
            for action in ('actions/checkout@','actions/setup-python@'):
                changed=copy.deepcopy(workflow)
                step=next(s for s in changed['jobs'][name]['steps'] if s.get('uses','').startswith(action))
                step['if']="${{ needs.ci-mode.outputs.mode == 'full' }}"
                with self.subTest(name=name,action=action),self.assertRaises(AssertionError):backend_ci.validate_reuse_bootstrap(changed)

    def test_cache_first_fallback_cannot_skip_a_successful_cache_miss(self):
        import yaml
        shards = yaml.safe_load((backend_ci.ROOT/'.github/workflows/ci.yml').read_text())['jobs']['backend-shards']
        backend_ci.validate_cache_bootstrap(shards)
        for name in ('Recover existing pip cache for a full fallback', 'Rebuild and verify all dependencies after a cache miss'):
            changed = copy.deepcopy(shards)
            step = next(s for s in changed['steps'] if s.get('name') == name)
            step['if'] = step['if'].replace(' || ', ' && ')
            with self.subTest(name=name), self.assertRaises(AssertionError):
                backend_ci.validate_cache_bootstrap(changed)
        for mode in ('run', 'conditional', 'continue'):
            changed = copy.deepcopy(shards)
            step = next(s for s in changed['steps'] if s.get('id') == 'cached-environment')
            if mode == 'run': step['run'] = 'exit 0'
            elif mode == 'conditional': step['if'] = 'false'
            else: step['continue-on-error'] = False
            with self.subTest(mode=mode), self.assertRaises(AssertionError):
                backend_ci.validate_cache_bootstrap(changed)

    def test_fixed_legacy_helper_replacement_has_exact_predecessor(self):
        import json
        base=json.loads(backend_ci.MANIFEST.read_text());delta=json.loads(backend_ci.ADDITIONS.read_text())
        for field,value in [('run','exit 0'),('env',{'WRONG':'1'}),('cwd','other'),('group','other')]:
            changed=copy.deepcopy(base)
            next(e for e in changed['checks'] if e['id']=='check-295')[field]=value
            with self.subTest(field=field),self.assertRaises(AssertionError):backend_ci.compose_manifest(changed,delta)

    def test_performance_timeout_keeps_final_storage_and_not_run(self):
        entries=[dict(id=name,group=name,run='exit 0',env={},cwd='.',**extra) for name,extra in [('initial',{}),('benchmark',{}),('final',{'always':True})]]
        manifest=dict(checks=[entries[0],entries[2]],performance=[entries[1]],performance_plan=[e['id'] for e in entries])
        def execute(item,*args,**kwargs):
            failed=item['id']=='benchmark'
            return dict(id=item['id'],status='failed' if failed else 'success',returncode=124 if failed else 0)
        with tempfile.TemporaryDirectory() as temp,patch.object(backend_ci,'execute',side_effect=execute):
            self.assertEqual(performance(manifest,Path(temp)),1)
            import json
            report=json.loads((Path(temp)/'performance.json').read_text())
            self.assertEqual([c['id'] for c in report['commands']],['initial','benchmark','final'])
            self.assertEqual(report['status'],'failed')

    def test_all_commands_required(self):
        self.check()
        for result in ('failure','cancelled','skipped',''):
            with self.subTest(result=result), self.assertRaises(AssertionError):self.check(result=result)
        for mutate in (
            lambda r:r.pop(),
            lambda r:r.append(copy.deepcopy(r[0])),
            lambda r:r[0].update(shard=1),
            lambda r:r[0].update(status='failed'),
            lambda r:r[0].pop('completed_at'),
            lambda r:r[0].update(commit='old'),
            lambda r:r[0].update(run_id='old'),
            lambda r:r[0].update(run_attempt='0'),
            lambda r:r[0].update(manifest_sha256='old'),
            lambda r:r[0]['commands'].pop(),
            lambda r:r[0]['commands'].append(copy.deepcopy(r[0]['commands'][0])),
            lambda r:r[0]['commands'].reverse(),
            lambda r:r[0]['commands'][0].update(status='skipped'),
            lambda r:r[0]['commands'][0].update(returncode=1),
            lambda r:r[0]['commands'][0].pop('seconds'),
        ):
            rows=copy.deepcopy(self.reports);mutate(rows)
            with self.assertRaises((AssertionError,KeyError)):self.check(rows)

    def test_executor_failure_retains_final_cleanup(self):
        def entry(name,command,**extra):
            return dict(id=name,run=command,env={},cwd='.',group=name,shard=0,**extra)
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)
            manifest={'checks':[entry('fail','exit 7'),entry('skip','exit 0'),
                                entry('cleanup','echo capacity',always=True)]}
            self.assertEqual(run_shard(manifest,0,output),1)
            import json
            report=json.loads((output/'shard-0.json').read_text())
            self.assertEqual([c['status'] for c in report['commands']],['failed','skipped','success'])
            self.assertIn('capacity',(output/'cleanup.log').read_text())
            self.assertEqual(report['status'],'failed')

    def test_executor_exception_preserves_failed_report(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest={'checks':[dict(id='raise',run='exit 0',env={},cwd='.',group='raise',shard=0)]}
            with patch('backend_ci.execute',side_effect=OSError('injected')):
                with self.assertRaises(OSError):run_shard(manifest,0,Path(temp))
            import json
            report=json.loads((Path(temp)/'shard-0.json').read_text())
            self.assertEqual(report['status'],'failed')
            self.assertIn('completed_at',report)

    def test_timeout_terminates_and_keeps_nonzero_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            record=execute(dict(id='timeout',group='timeout',run="python3 -c 'import time; time.sleep(10)'",env={},cwd='.'),Path(temp),timeout=.05)
            self.assertEqual(record['returncode'],124)
            self.assertEqual(record['status'],'failed')

    def test_performance_exception_cannot_write_success(self):
        manifest={'checks':[dict(id='cleanup',group='storage',run='python scripts/verify_ci_benchmark_storage.py',env={},cwd='.',always=True)],
                  'performance':[dict(id='benchmark',run='test benchmark',env={},cwd='.',group='benchmark')]}
        with tempfile.TemporaryDirectory() as temp:
            def fail(item,*args,**kwargs):
                if item['id']=='benchmark':raise OSError('injected')
                return dict(id=item['id'],status='success',returncode=0)
            with patch('backend_ci.execute',side_effect=fail):
                with self.assertRaises(OSError):performance(manifest,Path(temp))
            import json
            report=json.loads((Path(temp)/'performance.json').read_text())
            self.assertEqual(report['status'],'failed')
            self.assertEqual(report['commands'][-1]['id'],'cleanup')


if __name__=='__main__':unittest.main()

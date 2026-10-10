"""Fail-closed evidence gate and real executor fault/cleanup tests (stdlib only)."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend_ci import digest, load_manifest, run_shard, validate_reports


class GateContract(unittest.TestCase):
    def setUp(self):
        self.manifest=load_manifest()
        self.reports=[{'schema':1,'manifest_sha256':digest(self.manifest),'shard':shard,
            'commit':'sha','run_id':'123','run_attempt':'1','completed_at':'now','status':'success',
            'commands':[{'id':e['id'],'status':'success','returncode':0,'seconds':1}
                        for e in self.manifest['checks'] if e['shard']==shard]} for shard in range(12)]

    def check(self,reports=None,result='success'):
        validate_reports(self.manifest,self.reports if reports is None else reports,result,'sha','123','1')

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


if __name__=='__main__':unittest.main()

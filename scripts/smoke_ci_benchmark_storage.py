"""Fail-closed storage/settings inspection and benchmark-only routing contracts."""
from pathlib import Path
import os
import io
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import yaml
import verify_ci_benchmark_storage as storage


class StorageContracts(unittest.TestCase):
    def setUp(self):
        capture=patch.object(sys,'stdout',io.StringIO());capture.start();self.addCleanup(capture.stop)

    def container_output(self):
        return 'tmpfs 2147483648 1048576\n1048576 /var/lib/postgresql/data\nMEMORY_PEAK_BYTES\n268435456\nmax 0\noom 0\noom_kill 0\noom_group_kill 0\n0\n'

    def test_correct_mount_and_limits_with_memory_peak(self):
        metadata='{"/var/lib/postgresql/data":"rw,noexec,nosuid,size=2147483648"}|3221225472|3221225472|false'
        with patch.object(storage.subprocess,'check_output',side_effect=[metadata,self.container_output()]):
            result=storage.inspect_container('synthetic')
        self.assertEqual(result['container_peak_memory_bytes'],268435456)

    def test_bad_mount_memory_swap_oom_pressure_or_missing_evidence_fails(self):
        metadata='{"/var/lib/postgresql/data":"rw,noexec,nosuid,size=2147483648"}|3221225472|3221225472|false'
        for bad in [metadata.replace('2147483648','4294967296'),metadata.replace('3221225472|false','4294967296|false'),metadata.replace('|false','|true')]:
            with self.subTest(metadata=bad),patch.object(storage.subprocess,'check_output',return_value=bad):
                with self.assertRaises(AssertionError):storage.inspect_container('synthetic')
        for bad in [self.container_output().replace('oom 0','oom 1'),self.container_output().replace('max 0','max 1'),
                    self.container_output().replace('oom_kill 0\n',''),self.container_output().replace('268435456','4294967296')]:
            with self.subTest(evidence=bad),patch.object(storage.subprocess,'check_output',side_effect=[metadata,bad]):
                with self.assertRaises(AssertionError):storage.inspect_container('synthetic')

    def test_real_database_settings_are_checked_and_connection_released_on_failure(self):
        settings={'server_version_num':'160010','data_directory':'/var/lib/postgresql/data','fsync':'on',
            'synchronous_commit':'on','full_page_writes':'on','temp_tablespaces':'','max_wal_size':'1GB','shared_buffers':'128MB'}
        connection=Mock();connection.__enter__=Mock(return_value=connection);connection.__exit__=Mock(return_value=False)
        def execute(query,params=None):
            if params:return SimpleNamespace(fetchone=lambda:(settings[params[0]],))
            if 'pg_tablespace' in query:return SimpleNamespace(fetchall=lambda:[('pg_default',''),('pg_global','')])
            return SimpleNamespace(fetchone=lambda:('identity' if 'pg_control_system' in query else 1048576,))
        connection.execute.side_effect=execute
        with patch.dict(sys.modules,psycopg=SimpleNamespace(connect=Mock(return_value=connection))):
            self.assertEqual(storage.inspect_database('synthetic')['system_identifier'],'identity')
            settings['fsync']='off'
            with self.assertRaises(AssertionError):storage.inspect_database('synthetic')
        self.assertEqual(connection.__exit__.call_count,2)

    def test_cli_rejects_non_ci_or_non_synthetic_dsns_before_database_access(self):
        fail=Mock(side_effect=AssertionError('database must not be contacted'))
        for environment in [dict(GITHUB_ACTIONS='false'),dict(GITHUB_ACTIONS='true',VANTALINE_POSTGRES_DSN='non-synthetic')]:
            with self.subTest(environment=environment),patch.dict(os.environ,environment,clear=True),patch.object(storage,'inspect_database',fail):
                with self.assertRaises(AssertionError):storage.main()
        fail.assert_not_called()

    def test_same_instance_identity_fails_after_collecting_container_evidence(self):
        environment=dict(GITHUB_ACTIONS='true',VANTALINE_POSTGRES_DSN=storage.NORMAL_DSN,
            VANTALINE_BENCHMARK_POSTGRES_DSN=storage.BENCHMARK_DSN,VANTALINE_BENCHMARK_CONTAINER='synthetic')
        with patch.dict(os.environ,environment,clear=True),patch.object(storage,'inspect_database',return_value={'system_identifier':'same'}),patch.object(storage,'inspect_container',return_value={}) as inspect:
            with self.assertRaises(AssertionError):storage.main()
        inspect.assert_called_once()

    def test_only_four_real_pg_benchmarks_route_to_second_database(self):
        root=Path(__file__).resolve().parents[1]
        workflow=yaml.safe_load((root/'.github/workflows/ci.yml').read_text())
        backend=workflow['jobs']['backend-plc']
        self.assertEqual(backend['env']['VANTALINE_POSTGRES_DSN'],storage.NORMAL_DSN)
        self.assertEqual(backend['env']['VANTALINE_BENCHMARK_POSTGRES_DSN'],storage.BENCHMARK_DSN)
        ordinary=backend['services']['postgres'];self.assertEqual(ordinary['ports'],['5432:5432'])
        self.assertNotIn('--tmpfs',ordinary['options'])
        selected=[]
        prefix='VANTALINE_POSTGRES_DSN="$VANTALINE_BENCHMARK_POSTGRES_DSN" AGENT_TEST_DATABASE_URL="$VANTALINE_BENCHMARK_POSTGRES_DSN" '
        for step in backend['steps']:
            self.assertNotIn('VANTALINE_POSTGRES_DSN',step.get('env',{}))
            for line in step.get('run','').splitlines():
                if '$VANTALINE_BENCHMARK_POSTGRES_DSN' in line:
                    self.assertTrue(line.startswith(prefix));selected.append(line[len(prefix):])
        self.assertEqual(selected,['python scripts/benchmark_label_'+name+'.py' for name in ['history_statistics','summary_reads','projection','run_batch']])


if __name__=='__main__':unittest.main()

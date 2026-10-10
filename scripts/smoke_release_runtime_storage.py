"""Recovery storage boundaries; no host state, services or database are used."""
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import release_runtime_main as cli
from release_runtime_contract import ContractError
from release_runtime_transition import RuntimeTransition


class StorageTests(unittest.TestCase):
    def test_directory_type_owner_and_permissions(self):
        for mode, uid, private, accepted in (
            (stat.S_IFDIR | 0o755, 0, False, True),
            (stat.S_IFDIR | 0o700, 0, True, True),
            (stat.S_IFDIR | 0o755, 0, True, False),
            (stat.S_IFDIR | 0o700, 998, True, False),
            (stat.S_IFDIR | 0o770, 0, False, False),
            (stat.S_IFDIR | 0o777, 0, False, False),
            (stat.S_IFLNK | 0o700, 0, True, False),
            (stat.S_IFREG | 0o700, 0, True, False),
        ):
            with self.subTest(mode=mode, uid=uid, private=private), \
                    patch.object(cli.os, 'geteuid', return_value=0, create=True), \
                    patch.object(Path, 'lstat', return_value=SimpleNamespace(st_mode=mode, st_uid=uid)):
                if accepted:
                    cli.trusted_directory(Path('/synthetic'), private=private)
                else:
                    with self.assertRaises(ContractError):
                        cli.trusted_directory(Path('/synthetic'), private=private)

    def test_creation_order_and_existing_directory(self):
        events = []
        with patch.object(cli.os, 'geteuid', return_value=0, create=True), \
                patch.object(cli, 'trusted_directory', side_effect=lambda p, **k: events.append(('check', p.as_posix(), k))), \
                patch.object(Path, 'mkdir', side_effect=lambda **k: events.append(('mkdir', k))), \
                patch.object(cli, 'sync_directory', side_effect=lambda p: events.append(('sync', p.as_posix()))):
            cli.runtime_storage(create=True)
        self.assertEqual(events, [('check', '/', {}), ('check', '/var', {}), ('check', '/var/lib', {}),
                                 ('mkdir', {'mode': 0o700}), ('sync', '/var/lib'),
                                 ('check', '/var/lib/vantaline-release', {'private': True})])
        with patch.object(cli.os, 'geteuid', return_value=0, create=True), \
                patch.object(cli, 'trusted_directory') as check, \
                patch.object(Path, 'mkdir', side_effect=FileExistsError), \
                patch.object(cli, 'sync_directory') as sync:
            cli.runtime_storage(create=True)
            check.assert_called_with(cli.RUNTIME_STORAGE, private=True)
            sync.assert_not_called()

    def test_unsafe_ancestor_prevents_creation(self):
        with patch.object(cli.os, 'geteuid', return_value=0, create=True), \
                patch.object(cli, 'trusted_directory', side_effect=ContractError('unsafe ancestor')), \
                patch.object(Path, 'mkdir') as mkdir:
            with self.assertRaises(ContractError):
                cli.runtime_storage(create=True)
            mkdir.assert_not_called()

    def test_nonroot_prevents_creation(self):
        with patch.object(cli.os, 'geteuid', return_value=998, create=True), patch.object(Path, 'mkdir') as mkdir:
            with self.assertRaises(ContractError):
                cli.runtime_storage(create=True)
            mkdir.assert_not_called()

    def test_creation_and_sync_errors_propagate(self):
        for failing in ('mkdir', 'sync'):
            with self.subTest(failing=failing), patch.object(cli.os, 'geteuid', return_value=0, create=True), \
                    patch.object(cli, 'trusted_directory'), \
                    patch.object(Path, 'mkdir', side_effect=PermissionError() if failing == 'mkdir' else None), \
                    patch.object(cli, 'sync_directory', side_effect=OSError() if failing == 'sync' else None):
                with self.assertRaises(OSError):
                    cli.runtime_storage(create=True)

    def test_capabilities_do_not_create_storage(self):
        output = io.StringIO()
        with patch.object(cli.sys, 'argv', ['controller', 'capabilities']), \
                patch.object(cli, 'runtime_storage') as storage, contextlib.redirect_stdout(output):
            cli.main()
        storage.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['recovery_storage_schema'], 1)

    def test_legacy_location_rejected_before_dispatch(self):
        with patch.object(cli.sys, 'argv', ['controller', 'rollback', '/opt/vantaline/backups/.runtime-transition-v2026.10.1.json']), \
                patch.object(cli, 'runtime_storage') as storage:
            with self.assertRaises(ContractError):
                cli.main()
            storage.assert_not_called()

    def test_journal_entry_validation_before_controller(self):
        for mode, uid in ((stat.S_IFLNK | 0o600, 0), (stat.S_IFDIR | 0o600, 0),
                          (stat.S_IFIFO | 0o600, 0), (stat.S_IFREG | 0o644, 0),
                          (stat.S_IFREG | 0o600, 998)):
            with self.subTest(mode=mode, uid=uid), \
                    patch.object(cli.sys, 'argv', ['controller', 'check_journal', str(cli.RUNTIME_STORAGE / '.runtime-transition-v2026.10.1.json')]), \
                    patch.object(cli, 'runtime_storage'), patch.object(cli.os.path, 'lexists', return_value=True), \
                    patch.object(cli.os, 'geteuid', return_value=0, create=True), \
                    patch.object(Path, 'lstat', return_value=SimpleNamespace(st_mode=mode, st_uid=uid)), \
                    patch.object(cli, 'RuntimeTransition') as transition:
                with self.assertRaises(ContractError):
                    cli.main()
                transition.assert_not_called()

    def test_atomic_replace_failure_preserves_previous_journal(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = Path(folder) / 'journal.json'
            original = b'{"phase":"old"}'
            journal.write_bytes(original)
            transition = RuntimeTransition(journal, uid=0)
            transition.data = {'phase': 'new'}
            with patch('release_runtime_transition.os.replace', side_effect=OSError('interrupted replace')):
                with self.assertRaises(OSError):
                    transition.save()
            self.assertEqual(journal.read_bytes(), original)
            self.assertEqual(list(Path(folder).iterdir()), [journal])

    def test_journal_fsync_failure_preserves_previous_journal(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = Path(folder) / 'journal.json'
            journal.write_text('{"phase":"old"}')
            transition = RuntimeTransition(journal, uid=0)
            transition.data = {'phase': 'new'}
            with patch('release_runtime_transition.os.fsync', side_effect=OSError('fsync failure')):
                with self.assertRaises(OSError):
                    transition.save()
            self.assertEqual(json.loads(journal.read_text()), {'phase': 'old'})
            self.assertEqual(list(Path(folder).iterdir()), [journal])


class ObservationEntryTests(unittest.TestCase):
    release = 'v2026.10.1'
    commit = 'a' * 40

    def response(self):
        before = [{'role': role, 'instance': instance * 32, 'pid': pid, 'sampled_at': 10.0}
                  for role, instance, pid in (('web', 'b', 123), ('label', 'c', 456))]
        return {'schema': 1, 'git_commit': self.commit, 'release': self.release,
                'worker_mode': 'external', 'config_revision': 'd' * 64,
                'maintenance': False, 'paused': False, 'queued_runs': 0, 'active_runs': 0,
                'samples_before': before, 'roles': [dict(row, sampled_at=12.0) for row in before],
                'periodic_progress': True}

    def invoke(self, response=None, *, failure=None):
        result = SimpleNamespace(stdout=json.dumps(self.response() if response is None else response))
        identity = {'topology': {'commit': self.commit, 'mode': 'external', 'runtime_protocol': 1}}
        regular = SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o755, st_size=32)
        output = io.StringIO()
        target = Path('/opt/vantaline/releases') / self.release
        with patch.object(cli.os, 'geteuid', return_value=0, create=True), \
                patch.object(cli, 'trusted_directory'), patch.object(cli, 'trusted_observation_tree') as tree, \
                patch.object(Path, 'is_symlink', return_value=True), \
                patch.object(Path, 'resolve', side_effect=lambda item, **kwargs: target if item.as_posix() == '/opt/vantaline/current' else Path('/usr/bin') if item.as_posix() == '/usr/bin' else Path('/usr/bin/python3'), autospec=True), \
                patch.object(Path, 'lstat', return_value=regular), \
                patch.object(Path, 'iterdir', return_value=[]), \
                patch.object(Path, 'read_text', return_value='home = /usr/bin\n'), \
                patch.object(cli.RuntimeTransition, 'identity', return_value=identity), \
                patch.object(cli.subprocess, 'run', return_value=result, side_effect=failure) as run, \
                contextlib.redirect_stdout(output):
            cli.observe_runtime(self.release, self.commit)
        return json.loads(output.getvalue()), run.call_args, tree.call_args_list

    def test_fixed_child_isolated_imports_environment_timeout_and_trees(self):
        with patch.dict(cli.os.environ, {'PYTHONPATH': '/synthetic-attacker', 'PYTHONSTARTUP': '/secret',
                                         'DATABASE_URL': 'synthetic-secret'}):
            value, call, trees = self.invoke()
        self.assertEqual(value, self.response())
        self.assertEqual(call.kwargs['env'], {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        self.assertEqual(call.kwargs['timeout'], 45)
        self.assertTrue(call.kwargs['check'])
        self.assertEqual(call.args[0][:5], ['/opt/vantaline/venv/bin/python', '-I', '-S', '-B', '-c'])
        self.assertEqual([row.args[0].as_posix() for row in trees],
                         ['/opt/vantaline/venv', '/opt/vantaline/releases/v2026.10.1'])
        self.assertIn('observe_label_runtime', call.args[0][5])
        self.assertEqual(call.args[0][-4:], ['--release', self.release, '--commit', self.commit])

    def test_response_rejects_extra_sensitive_fields_wrong_identity_and_stalled_roles(self):
        for mutation in ('secret', 'commit', 'release', 'schema', 'flag', 'role', 'pid', 'instance', 'stalled', 'nan', 'huge_timestamp', 'active_limit'):
            value = self.response()
            if mutation == 'secret': value['secret'] = 'synthetic-customer-secret'
            elif mutation == 'commit': value['git_commit'] = 'e' * 40
            elif mutation == 'release': value['release'] = 'v2026.10.2'
            elif mutation == 'schema': value['schema'] = True
            elif mutation == 'flag': value['maintenance'] = 'synthetic-customer-secret'
            elif mutation == 'role': value['roles'][0]['role'] = 'customer-path'
            elif mutation == 'pid': value['roles'][0]['pid'] += 1
            elif mutation == 'instance': value['roles'][0]['instance'] = 'f' * 32
            elif mutation == 'stalled': value['roles'][0]['sampled_at'] = 10.0
            elif mutation == 'nan': value['roles'][0]['sampled_at'] = float('nan')
            elif mutation == 'huge_timestamp': value['roles'][0]['sampled_at'] = 10**400
            elif mutation == 'active_limit': value['active_runs'] = 3
            with self.subTest(mutation=mutation), self.assertRaises((ContractError, OverflowError)):
                self.invoke(value)

    def test_invalid_cli_values_never_spawn(self):
        for release, commit in (('../escape', self.commit), (self.release, 'A' * 40),
                                (self.release + '\n', self.commit), (self.release, self.commit + '\n')):
            with patch.object(cli.os, 'geteuid', return_value=0, create=True), \
                    patch.object(cli.subprocess, 'run') as run, self.assertRaises(ContractError):
                cli.observe_runtime(release, commit)
            run.assert_not_called()
        with patch.object(cli.os, 'geteuid', return_value=998, create=True), self.assertRaises(ContractError):
            cli.observe_runtime(self.release, self.commit)

    def test_observation_dispatch_never_creates_storage_or_transition(self):
        with patch.object(cli.sys, 'argv', ['controller', 'observe', self.release, self.commit]), \
                patch.object(cli, 'observe_runtime') as observe, \
                patch.object(cli, 'runtime_storage') as storage, patch.object(cli, 'RuntimeTransition') as transition:
            cli.main()
        observe.assert_called_once_with(self.release, self.commit)
        storage.assert_not_called(); transition.assert_not_called()

    def test_observation_dispatch_redacts_symlink_loop_unicode_and_timestamp_overflow(self):
        for error in (RuntimeError('synthetic-loop'), UnicodeError('synthetic-secret'), OverflowError('synthetic-secret')):
            with patch.object(cli.sys, 'argv', ['controller', 'observe', self.release, self.commit]), \
                    patch.object(cli, 'observe_runtime', side_effect=error), self.assertRaises(ContractError) as failure:
                cli.main()
            self.assertEqual(str(failure.exception), 'Runtime database observation failed')

    def test_child_failure_and_timeout_do_not_print_captured_customer_data(self):
        import subprocess
        for failure in (subprocess.CalledProcessError(1, ['fixed'], output='synthetic-customer-secret'),
                        subprocess.TimeoutExpired(['fixed'], 45, stderr='synthetic-customer-secret')):
            with self.assertRaises(subprocess.SubprocessError):
                self.invoke(failure=failure)


if __name__ == '__main__':
    unittest.main()

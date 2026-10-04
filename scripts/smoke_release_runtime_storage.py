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


if __name__ == '__main__':
    unittest.main()

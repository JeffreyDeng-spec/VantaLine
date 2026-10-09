"""Actual path/configuration cycle, initialization, scope and partial failures."""
from contextvars import ContextVar
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.path_configuration_composition import PathConfigurationWorkflows, PathConfigurationLocations
from local_inspection_service.runtime.service_path_ports import ServicePathSettings, PathProjectionPolicy, PathIdentity
from local_inspection_service.config.app_store_ports import AppConfigRows
from local_inspection_service.storage.artifacts.files import BusinessFiles


class PathConfigurationGraph(unittest.TestCase):
    def owner(self, marker):
        temporary = tempfile.TemporaryDirectory(prefix="vl-path-graph-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        data = root / "data"
        user = ContextVar(marker, default=None)
        files = BusinessFiles(runtime_provider=lambda: None)
        owner = PathConfigurationWorkflows(
            locations=PathConfigurationLocations(directories=lambda: (data, root/"outputs"),
                primary=lambda: data/"config.json", backup=lambda: data/"backup.json", data=lambda: data,
                migration_roots=lambda: (data,)),
            settings=ServicePathSettings(ROOT=lambda: root, APP_DIR=lambda: root/"app", OUTPUT_DIR=lambda: root/"outputs"),
            path_policy=PathProjectionPolicy(STALE_REPO_PATH_PREFIXES=lambda: ("/old/vantaline",),
                REMOVED_PHASE1_PUBLIC_CONFIG_KEYS=lambda: set(), LEGACY_OWNER_ID=lambda: "legacy", SYSTEM_OWNER_ID=lambda: "system"),
            identity=PathIdentity(_request_user=lambda: user, user_is_admin=lambda: lambda value: bool(value.get("admin"))),
            files=lambda: files,
            rows=AppConfigRows(runtime_postgres_repository_or_none=lambda: lambda: None,
                config_from_rows=lambda: lambda *a: self.fail("unexpected postgres"),
                app_config_rows=lambda: lambda *a, **kw: self.fail("unexpected postgres"),
                accessory_rows=lambda: lambda *a: self.fail("unexpected postgres")),
            defaults=lambda: {"accessories": [], "marker": marker}, protected_keys=lambda: ("plc",))
        return owner, root, user, files

    def test_inert_constructor_and_all_owned_edges(self):
        owner, root, _, _ = self.owner("a")
        self.assertFalse((root/"data").exists())
        self.assertIs(owner.directories.save_config().__self__, owner)
        self.assertIs(owner.directories.migrate().__self__, owner)
        self.assertIs(owner.migration.migrate_file().__self__, owner)
        self.assertIs(owner.configuration.store.files.ensure_dirs().__self__, owner)
        self.assertIs(owner.configuration.store.policy.public_path_sanitized().__self__, owner)
        for name in owner.paths.calls.__dataclass_fields__:
            self.assertIs(getattr(owner.paths.calls, name)().__self__, owner)

    def test_real_initialization_and_configuration_are_isolated(self):
        a, root_a, _, _ = self.owner("a")
        b, root_b, _, _ = self.owner("b")
        self.assertEqual(a.configuration.load_config()["marker"], "a")
        self.assertTrue((root_a/"data/config.json").exists())
        self.assertTrue(a.migration.done)
        self.assertFalse((root_b/"data/config.json").exists())
        self.assertFalse(b.migration.done)
        a.save_config({"marker": "updated-a", "accessories": []})
        self.assertEqual(b.configuration.load_config()["marker"], "b")
        self.assertEqual(a.configuration.load_config()["marker"], "updated-a")
        self.assertIsNot(a.configuration.lock, b.configuration.lock)
        self.assertIsNot(a.migration.lock, b.migration.lock)

    def test_output_identity_is_resolved_at_each_call(self):
        owner, root, user, _ = self.owner("a")
        for identity, target in (({"id": "alice"}, "users/alice"), ({"id": "bob"}, "users/bob"), ({"id": "admin", "admin": True}, "")):
            token = user.set(identity)
            try:
                self.assertEqual(owner.paths.output_write_dir("preview"), root/"outputs"/target/"preview")
            finally:
                user.reset(token)

    def test_saved_internal_callee_selects_component_after_arguments(self):
        owner, _, _, _ = self.owner("a")
        saved = owner.paths.calls.public_output_url()
        replacement = SimpleNamespace(public_output_url=Mock(return_value="new"))
        def argument():
            owner.paths = replacement
            return Path("synthetic")
        self.assertEqual(saved(argument()), "new")
        replacement.public_output_url.assert_called_once_with(Path("synthetic"))

    def test_existing_bound_aliases_keep_original_instances(self):
        owner, root, _, _ = self.owner("a")
        original_directories, original_migration = owner.directories, owner.migration
        new_directories = SimpleNamespace(ensure=Mock(side_effect=AssertionError("rebound fixed alias")))
        new_migration = SimpleNamespace(run=Mock(side_effect=AssertionError("rebound fixed alias")))
        owner.directories, owner.migration = new_directories, new_migration
        self.assertIs(owner._ensure_directories.__self__, original_directories)
        self.assertIs(owner._run_migration.__self__, original_migration)
        owner.configuration.load_config()
        self.assertTrue((root/"data/config.json").exists())
        self.assertTrue(original_migration.done)
        owner.migrate_persisted_local_paths_once()
        new_directories.ensure.assert_not_called()
        new_migration.run.assert_not_called()

    def test_failed_migration_does_not_mark_complete(self):
        owner, root, _, _ = self.owner("a")
        failing = Mock(side_effect=RuntimeError("synthetic failure"))
        with patch.object(type(owner.paths), "migrate_json_file_paths", failing), self.assertRaisesRegex(RuntimeError, "synthetic failure"):
            owner.ensure_dirs()
        self.assertTrue((root/"data/config.json").exists())
        self.assertFalse(owner.migration.done)
        owner.ensure_dirs()
        self.assertTrue(owner.migration.done)

    def test_failed_save_prevents_migration_and_preserves_recovery(self):
        owner, root, _, files = self.owner("a")
        with patch.object(files, "write_text", side_effect=RuntimeError("synthetic failure")), self.assertRaises(RuntimeError):
            owner.ensure_dirs()
        self.assertFalse(owner.migration.done)
        self.assertFalse((root/"data/config.json").exists())
        owner.ensure_dirs()
        self.assertTrue(owner.migration.done)

    def test_configuration_protection_and_atomic_mutation_remain(self):
        owner, _, _, _ = self.owner("a")
        owner.configuration.mutate_app_config_atomically(lambda value: value.update(plc={"station": "retained"}))
        owner.save_config({"plc": {"station": "replaced"}, "marker": "updated"})
        self.assertEqual(owner.configuration.load_config()["plc"], {"station": "retained"})
        self.assertEqual(owner.configuration.load_config()["marker"], "updated")


if __name__ == "__main__":
    unittest.main()

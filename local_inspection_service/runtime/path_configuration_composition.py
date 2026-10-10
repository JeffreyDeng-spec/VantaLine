"""Own the path, directory, migration and configuration cycle as one inert graph."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .directories import LocalPathMigration, ServiceDirectories
from .service_paths import ServicePaths
from .service_path_ports import PathCalls, PathFiles, PathIdentity, PathProjectionPolicy, ServicePathSettings
from ..config.application_composition import ApplicationConfiguration, ConfigurationFiles, ConfigurationPolicy
from ..config.app_store_ports import AppConfigRows
if TYPE_CHECKING:
    from ..storage.artifacts.files import BusinessFiles


@dataclass(frozen=True)
class PathConfigurationLocations:
    directories: Callable[[], tuple[Path, ...]]
    primary: Callable[[], Path]
    backup: Callable[[], Path]
    data: Callable[[], Path]
    migration_roots: Callable[[], tuple[Path, ...]]


class PathConfigurationWorkflows:
    """No I/O at construction; identity and repository selection stay call-time."""
    def __init__(self, *, locations: PathConfigurationLocations,
                 settings: ServicePathSettings, path_policy: PathProjectionPolicy,
                 identity: PathIdentity, files: Callable[[], "BusinessFiles"],
                 rows: AppConfigRows, defaults: Callable[[], dict[str, Any]],
                 protected_keys: Callable[[], tuple[str, ...]]):
        self.paths = ServicePaths(settings=settings, policy=path_policy,
            calls=PathCalls(
                rebase_stale_local_path_text=lambda: self.rebase_stale_local_path_text,
                rebase_stale_local_payload_text=lambda: self.rebase_stale_local_payload_text,
                public_path_sanitized=lambda: self.public_path_sanitized,
                service_rebased_path=lambda: self.service_rebased_path,
                resolve_service_path=lambda: self.resolve_service_path,
                path_is_under=lambda: self.path_is_under,
                public_output_url=lambda: self.public_output_url,
                output_write_dir_for_owner=lambda: self.output_write_dir_for_owner),
            files=PathFiles(_business_files=files), identity=identity)
        self.directories = ServiceDirectories(paths=locations.directories,
            config_path=locations.primary, defaults=defaults, files=files,
            save_config=lambda: self.save_config, migrate=lambda: self.migrate_persisted_local_paths_once)
        self.migration = LocalPathMigration(config_path=locations.primary,
            roots=locations.migration_roots, files=files,
            migrate_file=lambda: self.migrate_json_file_paths)
        # These two entry exports were bound aliases, unlike the path wrappers.
        # Keep their original instance even if a test replaces a component view.
        self._ensure_directories = self.directories.ensure
        self._run_migration = self.migration.run
        self.configuration = ApplicationConfiguration(
            files=ConfigurationFiles(files=files, primary=locations.primary,
                backup=locations.backup, directory=locations.data, ensure=lambda: self.ensure_dirs),
            rows=rows, policy=ConfigurationPolicy(defaults=defaults,
                protected_keys=protected_keys, sanitize=lambda: self.public_path_sanitized))

    def rebase_stale_local_path_text(self, value):
        return self.paths.rebase_stale_local_path_text(value)

    def rebase_stale_local_payload_text(self, text):
        return self.paths.rebase_stale_local_payload_text(text)

    def public_path_sanitized(self, value):
        return self.paths.public_path_sanitized(value)

    def service_rebased_path(self, path):
        return self.paths.service_rebased_path(path)

    def resolve_service_path(self, value, *, for_write=False):
        return self.paths.resolve_service_path(value, for_write=for_write)

    def path_is_under(self, path, root):
        return self.paths.path_is_under(path, root)

    def public_output_url(self, path):
        return self.paths.public_output_url(path)

    def output_write_dir_for_owner(self, kind="", owner_user_id=""):
        return self.paths.output_write_dir_for_owner(kind, owner_user_id)

    def migrate_json_file_paths(self, path):
        return self.paths.migrate_json_file_paths(path)

    def ensure_dirs(self):
        return self._ensure_directories()

    def save_config(self, config):
        return self.configuration.save_config(config)

    def migrate_persisted_local_paths_once(self):
        return self._run_migration()

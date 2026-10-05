"""Application configuration persistence with unchanged protected namespaces."""
import copy
from collections.abc import Callable
from dataclasses import dataclass
import json
import os
import time
from typing import Any
import uuid
from .app_store_ports import AppConfigFiles, AppConfigRows, AppConfigPolicy

@dataclass(frozen=True)
class AppConfigStore:
    files: AppConfigFiles
    rows: AppConfigRows
    policy: AppConfigPolicy

    def _read_config_file(self) -> dict[str, Any] | None:
        'Read config.json, retrying briefly on transient partial/empty reads.\n\n    Returns the parsed dict, an empty dict when the file legitimately does not\n    exist, or ``None`` when the file is present but could not be parsed cleanly\n    (e.g. mid-write). Callers must NOT treat ``None`` as "no accessories" — doing\n    so would silently drop every persisted record whenever a concurrent writer\n    is in the middle of replacing the file.\n    '
        for attempt in range(6):
            try:
                text = self.files._business_files().read_text(self.files.CONFIG_PATH(), encoding="utf-8")
            except FileNotFoundError:
                return {}
            except OSError:
                time.sleep(0.05)
                continue
            if not text.strip():
                # Empty/zero-byte read can happen during a non-atomic legacy write;
                # give the writer a moment and retry rather than wiping state.
                time.sleep(0.05)
                continue
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                time.sleep(0.05)
        return None


    def load_config(self) -> dict[str, Any]:
        self.files.ensure_dirs()()
        repository = self.rows.runtime_postgres_repository_or_none()()
        if repository is not None:
            current = self.rows.config_from_rows()(repository.fetch_all("app_config"), repository.fetch_all("accessories"))
        else:
            current = self.files._read_config_file()()
            if current is None:
                # The primary file exists but is unreadable right now. Fall back to the
                # last-good snapshot instead of DEFAULT_CONFIG so we never report that
                # user accessories/models suddenly vanished due to a write race.
                try:
                    backup_text = self.files._business_files().read_text(self.files.CONFIG_BACKUP_PATH(), encoding="utf-8")
                    current = json.loads(backup_text)
                except (FileNotFoundError, OSError, json.JSONDecodeError):
                    current = {}
        merged = json.loads(json.dumps(self.policy.DEFAULT_CONFIG()))
        for key, value in current.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
        return self.policy.public_path_sanitized()(merged)


    def save_config(self, config: dict[str, Any]) -> None:
        self.files.DATA_DIR().mkdir(parents=True, exist_ok=True)
        repository = self.rows.runtime_postgres_repository_or_none()()
        if repository is not None:
            now = int(time.time())
            with self.files._config_io_lock():
                repository.replace_app_config_preserving_keys(
                    self.rows.app_config_rows()(config, updated_at=now),
                    self.policy.PLC_PROTECTED_CONFIG_KEYS(),
                    additional_tables={"accessories": self.rows.accessory_rows()(config)},
                )
            return
        with self.files._config_io_lock():
            saved = copy.deepcopy(config)
            if not self.policy._plc_namespace_write_authorized().get():
                current = self.files._read_config_file()()
                current = current if isinstance(current, dict) else {}
                for key in self.policy.PLC_PROTECTED_CONFIG_KEYS():
                    if key in current:
                        saved[key] = copy.deepcopy(current[key])
                    else:
                        saved.pop(key, None)
            payload = json.dumps(saved, indent=2)
            tmp_path = self.files.CONFIG_PATH().with_name(f"{self.files.CONFIG_PATH().name}.tmp.{uuid.uuid4().hex}")
            try:
                self.files._business_files().write_text(tmp_path, payload, encoding="utf-8")
                os.replace(tmp_path, self.files.CONFIG_PATH())
            finally:
                try:
                    self.files._business_files().unlink(tmp_path)
                except OSError:
                    pass
            # Best-effort last-good snapshot for disaster recovery.
            try:
                backup_tmp = self.files.CONFIG_BACKUP_PATH().with_name(f"{self.files.CONFIG_BACKUP_PATH().name}.tmp.{uuid.uuid4().hex}")
                self.files._business_files().write_text(backup_tmp, payload, encoding="utf-8")
                os.replace(backup_tmp, self.files.CONFIG_BACKUP_PATH())
            except OSError:
                pass

    def save_app_config(self, config: dict[str, Any]) -> None:
        repository = self.rows.runtime_postgres_repository_or_none()()
        if repository is not None:
            with self.files._config_io_lock():
                repository.replace_app_config_preserving_keys(
                    self.rows.app_config_rows()(config, updated_at=int(time.time())),
                    self.policy.PLC_PROTECTED_CONFIG_KEYS(),
                )
            return
        self.save_config(config)


    def mutate_app_config_atomically(self, mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        'Atomically mutate only the protected PLC app-config namespace.\n\n    JSON is single-process/thread safe. PostgreSQL additionally uses a\n    transaction-scoped advisory lock so independent repository instances share\n    the same namespace linearization point.\n    '
        with self.files._config_io_lock():
            repository = self.rows.runtime_postgres_repository_or_none()()
            if repository is not None:

                def mutate_protected(values: dict[str, Any]) -> None:
                    mutator(values)
                    unexpected = set(values) - set(self.policy.PLC_PROTECTED_CONFIG_KEYS())
                    if unexpected:
                        raise ValueError(f'PLC namespace mutator wrote unprotected keys: {sorted(unexpected)}')
                repository.mutate_app_config_namespace(
                    self.policy.PLC_PROTECTED_CONFIG_KEYS(), mutate_protected,
                    updated_at=int(time.time()),
                )
                return self.load_config()
            config = self.load_config()
            unprotected_before = {key: copy.deepcopy(value) for key, value in config.items() if key not in self.policy.PLC_PROTECTED_CONFIG_KEYS()}
            mutator(config)
            unprotected_after = {key: value for key, value in config.items() if key not in self.policy.PLC_PROTECTED_CONFIG_KEYS()}
            if unprotected_after != unprotected_before:
                raise ValueError('PLC namespace mutator changed unprotected app-config keys')
            token = self.policy._plc_namespace_write_authorized().set(True)
            try:
                self.save_app_config(config)
            finally:
                self.policy._plc_namespace_write_authorized().reset(token)
            return config

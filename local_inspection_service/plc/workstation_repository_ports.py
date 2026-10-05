"""Scoped file, policy and PostgreSQL capabilities for workstation persistence."""
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from ..plc_fx_ascii import PlcConfigError
Record = dict[str, Any]
State = dict[str, Record | None]
LocalState = dict[str, dict[str, Any]]

class BusinessFilePort(Protocol):
    def read_text(self, path: Path, *, encoding: str) -> str: ...
    def write_text(self, path: Path, content: str, *, encoding: str) -> None: ...

class PostgresRows(Protocol):
    def upsert_row(self, table_name: str, row: Mapping[str, Any], *, commit: bool = True) -> None: ...
    def mutate_plc_web_serial_rows(self, station_id: str, dispatch_id: str | None, mutator: Callable[[State], None]) -> State: ...

@dataclass(frozen=True)
class WorkstationRepositoryFiles:
    _business_files: Callable[[], BusinessFilePort]
    DATA_DIR: Callable[[], Path]
    PLC_WEB_SERIAL_STATE_PATH: Callable[[], Path]

@dataclass(frozen=True)
class WorkstationRepositoryPolicy:
    PLC_WEB_SERIAL_JSON_TEST_ENV: Callable[[], str]
    PlcConfigError: Callable[[], type[PlcConfigError]]
    SYSTEM_OWNER_ID: Callable[[], str]

@dataclass(frozen=True)
class WorkstationRepositoryStorage:
    runtime_postgres_repository_or_none: Callable[[], Callable[[], PostgresRows | None]]
    _config_io_lock: Callable[[], AbstractContextManager]
    _plc_web_serial_empty_state: Callable[[], Callable[[], LocalState]]
    _plc_web_serial_load_local: Callable[[], Callable[[], LocalState]]
    _plc_web_serial_save_local: Callable[[], Callable[[LocalState], None]]

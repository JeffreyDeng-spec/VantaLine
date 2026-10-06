"""Capabilities needed by the dedicated camera orchestration path."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from fastapi import Request
Record = dict[str, Any]
class CameraFiles(Protocol):
    def write_bytes(self, path: Path, payload: bytes) -> Any: ...
@dataclass(frozen=True)
class CameraRequestAccess:
    ensure_dirs: Callable[[], Callable[[], None]]
    require_analyze_model_permission: Callable[[], Callable[[str | None], None]]
    require_plc_web_serial_station: Callable[[], Callable[[Request], Record]]
@dataclass(frozen=True)
class CameraDispatchEvidence:
    plc_web_serial_begin_camera_detection: Callable[[], Callable[[str, str, str, str, str], tuple[Record, bool]]]
    plc_web_serial_finish_camera_detection: Callable[[], Callable[..., Record]]
    plc_web_serial_dispatch_public: Callable[[], Callable[[Record], Record]]
@dataclass(frozen=True)
class CameraImageExecution:
    UPLOAD_DIR: Callable[[], Path]
    _business_files: Callable[[], CameraFiles]
    safe_name: Callable[[], Callable[[str], str]]
    analyze_bgr: Callable[[], Callable[..., Record]]

"""Storage, job evidence and provider capabilities for existing image execution."""
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Protocol
from ..storage.artifacts.runtime import ArtifactRuntime
Record = dict[str, Any]
Run = Callable[[Path, Record, Record], None]

class ExecutionFiles(Protocol):
    def exists(self, path: Path) -> bool: ...
    def is_file(self, path: Path) -> bool: ...
    def runtime(self, path: Path) -> ArtifactRuntime | None: ...
    def write_text(self, path: Path, value: str, *, encoding: str) -> Any: ...
    def write_bytes(self, path: Path, value: bytes) -> Any: ...
    def unlink(self, path: Path) -> Any: ...

class ExecutionImages(Protocol):
    def imread(self, path: str, flags: int) -> Any: ...

@dataclass(frozen=True)
class ImageExecutionFiles:
    _business_files: Callable[[], ExecutionFiles]
    _image_files: Callable[[], ExecutionImages]
    image_job_output_path: Callable[[], Callable[..., Path]]
    IMAGE_WORKER_LOG_DIR: Callable[[], Path]
    ROOT: Callable[[], Path]
    safe_name: Callable[[], Callable[[str], str]]
    resolve_service_path: Callable[[], Callable[[str], Path]]
    public_output_url: Callable[[], Callable[[Path], str]]

@dataclass(frozen=True)
class ImageExecutionEvidence:
    mutate_candidate_image_job: Callable[[], Callable[..., Record]]
    update_image_worker_status: Callable[[], Callable[..., Record]]
    _image_worker_processes: Callable[[], MutableMapping[str, subprocess.Popen]]
    image_job_prompt: Callable[[], Callable[[Record], str]]
    codex_log_has_generated_image: Callable[[], Callable[[Path], bool]]
    classify_image_worker_failure: Callable[[], Callable[[Path, int, Path], str]]
    bounded_text: Callable[[], Callable[[Any, int], str]]

@dataclass(frozen=True)
class ImageExecutionProviders:
    LOCAL_CODEX_IMAGE_PROVIDER: Callable[[], str]
    CURSOR_IMAGE2_PROVIDER: Callable[[], str]
    CURSOR_IMAGE2_QUEUE_STATUS: Callable[[], str]
    CODEX_IMAGE_WORKER_QUEUE_STATUS: Callable[[], str]
    MAX_IMAGE_WORKER_INPUTS: Callable[[], int]
    cursor_image2_settings: Callable[[], Callable[[], Record]]
    cursor_image2_payload: Callable[[], Callable[[Record, list[str], Record], Record]]
    cursor_auth_headers: Callable[[], Callable[[str], dict[str, str]]]
    extract_cursor_image2_bytes: Callable[[], Callable[[Record, Record], bytes]]
    run_codex_image_job: Callable[[], Run]
    run_cursor_image2_job: Callable[[], Run]
    run_cos_codex_image_job: Callable[[], Callable[[Path, Record, Record, ArtifactRuntime], None]]
    windows_worker_base_url: Callable[[], Callable[[], str]]
    windows_worker_headers: Callable[[], Callable[[], dict[str, str]]]
    windows_worker_image_timeout_seconds: Callable[[], Callable[[], float]]
    windows_worker_image_response_bytes: Callable[[], Callable[[Record], bytes]]
    masked_url_for_status: Callable[[], Callable[[str], str]]

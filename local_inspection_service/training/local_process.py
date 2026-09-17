"""Local training CLI lookup and bounded log-tail progress parsing."""
import os
from pathlib import Path
import re
import shutil
import sys


def parse_yolo_epoch_progress(log_path: Path, total_epochs: int) -> tuple[int, int] | None:
    if not log_path.exists():
        return None
    try:
        with log_path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 131072), os.SEEK_SET)
            text = fh.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    matches = re.findall(r"(?:^|\s)(\d{1,4})/(\d{1,4})(?=\s)", text, flags=re.MULTILINE)
    parsed: list[tuple[int, int]] = []
    for current_raw, total_raw in matches:
        current, total = int(current_raw), int(total_raw)
        if current <= 0 or total <= 0:
            continue
        if total_epochs and total != total_epochs:
            continue
        parsed.append((current, total))
    return parsed[-1] if parsed else None


def yolo_cli_command() -> str:
    configured = os.environ.get("INSPECTION_YOLO_COMMAND", "").strip()
    if configured:
        return configured
    discovered = shutil.which("yolo")
    if discovered:
        return discovered
    candidates = []
    virtual_env = os.environ.get("VIRTUAL_ENV", "").strip()
    if virtual_env:
        candidates.append(Path(virtual_env) / "bin" / "yolo")
    candidates.append(Path(sys.executable).parent / "yolo")
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "yolo"

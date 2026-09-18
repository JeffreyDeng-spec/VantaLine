"""Background Codex process and thread launch; command, prompt and failure boundaries are retained."""
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import subprocess
import threading
from typing import Protocol, TextIO


class GenerateCodexBackground(Protocol):
    def __call__(self, source_path: Path, set_dir: Path, set_id: str, count: int = 5) -> list[Path]: ...


class CodexBackgroundProcess(Protocol):
    def communicate(self, prompt: str, *, timeout: float) -> tuple[str | None, str | None]: ...
    def kill(self) -> None: ...


class StartCodexBackgroundProcess(Protocol):
    def __call__(self, command: list[str], *, cwd: str, stdin: int, stdout: TextIO,
                 stderr: int, text: bool) -> CodexBackgroundProcess: ...


class StartCodexBackgroundThread(Protocol):
    def __call__(self, *, target: GenerateCodexBackground, args: tuple[Path, Path, str, int],
                 name: str, daemon: bool) -> threading.Thread: ...


@dataclass(frozen=True)
class CodexBackgroundPaths:
    logs: Callable[[], Path]
    root: Callable[[], Path]


class CodexBackgroundGeneration:
    def __init__(self, which: Callable[[str], str | None], paths: CodexBackgroundPaths,
                 name: Callable[[str], str], start: Callable[[], StartCodexBackgroundProcess]):
        self.which, self.paths, self.name, self.start = which, paths, name, start

    def run_codex_background_generation(self, source_path: Path, set_dir: Path, set_id: str, count: int = 5) -> list[Path]:
        if not self.which("codex") or not source_path.exists():
            return []
        set_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.paths.logs() / f"background_{self.name(set_id)}_codexcli.log"
        outputs = [set_dir / f"codex_{self.name(set_id)}_{idx:02d}.png" for idx in range(1, count + 1)]
        prompt = "\n".join(
            [
                "You are the ImageWorker for the local assembly-line inspection service.",
                "",
                "Use the attached reference image as the source environment. Generate realistic, empty, overhead-view background PNGs of the same surface type and same environment. Keep camera geometry, material texture, scratches, dust, lighting, rails/edges if present, and mild natural variation. Do not add objects, text, labels, watermarks, hands, people, manuals, bottles, tools, or parts.",
                "",
                "Save the final PNG files exactly here:",
                *[str(path) for path in outputs],
            ]
        )
        command = [
            "codex",
            "exec",
            "--sandbox",
            "workspace-write",
            "-C",
            str(self.paths.root()),
            "-i",
            str(source_path),
            "-",
        ]
        try:
            with log_path.open("w", encoding="utf-8", errors="replace") as log:
                process = self.start()(command, cwd=str(self.paths.root()), stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, text=True)
                process.communicate(prompt + "\n", timeout=900)
        except subprocess.TimeoutExpired:
            try:
                process.kill()  # type: ignore[name-defined]
            except Exception:
                pass
            return [path for path in outputs if path.exists()]
        except Exception:
            return []
        return [path for path in outputs if path.exists()]


class CodexBackgroundThread:
    def __init__(self, create: Callable[[], StartCodexBackgroundThread], target: Callable[[], GenerateCodexBackground],
                 name: Callable[[str], str]):
        self.create, self.target, self.name = create, target, name

    def start_codex_background_generation(self, source_path: Path, set_dir: Path, set_id: str, count: int = 5) -> None:
        thread = self.create()(
            target=self.target(),
            args=(source_path, set_dir, set_id, count),
            name=f"codex-background-worker-{self.name(set_id)}",
            daemon=True,
        )
        thread.start()

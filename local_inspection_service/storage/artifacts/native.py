"""Leased native image jobs: private inputs and hard-capped, isolated scratch."""
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import signal
import subprocess

from .files import BusinessFiles
from .types import ArtifactUnavailable


def command(workspace, binary):
    bubblewrap = shutil.which("bwrap")
    if not bubblewrap or not binary.is_file():
        raise ArtifactUnavailable("isolated image runtime is unavailable")
    args = [bubblewrap, "--unshare-all", "--share-net", "--die-with-parent", "--new-session", "--clearenv"]
    for path in ("/usr", "/bin", "/lib", "/lib64"):
        if Path(path).exists():
            args += ["--ro-bind", path, path]
    args += ["--dir", "/etc"]
    for path in ("/etc/ssl", "/etc/resolv.conf", "/etc/hosts", "/etc/nsswitch.conf"):
        if Path(path).exists():
            args += ["--ro-bind", path, path]
    args += ["--proc", "/proc", "--dev", "/dev", "--bind", str(workspace), "/work",
             "--bind", str(workspace / "tmp"), "/tmp",
             "--ro-bind", str(binary.parent), "/codex-runtime", "--chdir", "/work",
             "--setenv", "HOME", "/work", "--setenv", "CODEX_HOME", "/work/.codex",
             "--setenv", "TMPDIR", "/tmp", "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin",
             "--setenv", "LANG", "C.UTF-8", "/codex-runtime/" + binary.name,
             "exec", "--skip-git-repo-check", "--sandbox", "danger-full-access", "-C", "/work"]
    return args


@contextmanager
def image_job(runtime, input_files, prompt, *, on_process=lambda p: None):
    budget = runtime.store.budget
    if not budget.preallocated:
        raise ArtifactUnavailable("native image jobs require hard-limited temporary storage")
    binary = Path(os.environ.get("VANTALINE_IMAGE_CODEX_BINARY", shutil.which("codex") or ""))
    auth = Path(os.environ.get("VANTALINE_IMAGE_CODEX_AUTH_HOME", ""))
    if not auth.is_absolute() or not (auth / "auth.json").is_file():
        raise ArtifactUnavailable("dedicated image runtime authentication is not configured")
    available = shutil.disk_usage(budget.scratch_roots["work"]).free
    size = max(1, min(budget.limits["work"], available) - 16 * 1024 * 1024)
    files = BusinessFiles(runtime_provider=lambda: runtime)
    with budget.workspace("work", size) as workspace:
        (workspace / "tmp").mkdir()
        private = workspace / ".codex"
        private.mkdir(mode=0o700)
        # Never expose object-store credentials, database settings, source media
        # roots or the host's home directory to the native child.
        for name in ("auth.json", "config.toml"):
            source = auth / name
            if source.is_file() and not source.is_symlink():
                shutil.copy2(source, private / name)
        for name in ("skills", "plugins"):
            source = auth / name
            if source.is_dir() and not source.is_symlink():
                shutil.copytree(source, private / name, symlinks=True)
        args = command(workspace, binary)
        for index, source in enumerate(input_files):
            destination = workspace / ("input-%03d" % index + Path(source).suffix)
            with files.local_file(source) as cached:
                shutil.copyfile(cached, destination)
            args += ["-i", "/work/" + destination.name]
        args += ["-"]
        log_path = workspace / "worker.log"
        output_path = workspace / "result.png"
        process = None
        try:
            with log_path.open("wb") as log:
                process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=True, env={"PATH": "/usr/bin:/bin"})
                on_process(process)
                process.communicate(prompt("/work/result.png").encode(), timeout=900)
            if log_path.stat().st_size > 16 * 1024 * 1024:
                raise ArtifactUnavailable("native image log exceeds publication limit")
            if output_path.is_symlink():
                raise ArtifactUnavailable("native output must be a regular file")
            yield output_path, log_path, process.returncode
        finally:
            if process is not None and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
            on_process(None)

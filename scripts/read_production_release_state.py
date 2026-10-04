"""Read-only, bounded, redacted production release-lock diagnostics.

Run over the already pinned SSH transport as the existing deploy account.
No sudo, signal delivery, lock acquisition/removal, DB access or service mutation.
Only a fixed metadata allowlist is printed; all error text is discarded.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import signal
import subprocess
import sys
import math
import urllib.request

BASE = Path("/opt/vantaline")
PROC = Path("/proc")
INSTALLER = Path("/usr/local/sbin/vantaline-install-release")


def identity(info):
    return info.st_dev, info.st_ino, info.st_mtime_ns, (info.st_ctime_ns if os.name != "nt" else None), info.st_size


def bounded(path, limit, *, metadata=False):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Diagnostic input is not a regular file")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if len(data) > limit:
        raise ValueError("Diagnostic input exceeds bound")
    return (data, before, after) if metadata else data


def process_state(pid, proc=PROC):
    output = {"pid": pid}
    try:
        data = bounded(proc / str(pid) / "stat", 4096).decode("ascii")
        fields = data.rsplit(")", 1)[1].split()
        output["exists"] = True
        output["parent_pid"] = int(fields[1])
        output["state"] = fields[0] if fields[0] in "RSDZTtXxKWPI" else "unknown"
        boot = re.search(rb"(?m)^btime ([0-9]+)$", bounded(proc / "stat", 256 * 1024))
        if boot:
            output["started_at_epoch"] = int(boot.group(1)) + int(fields[19]) / os.sysconf("SC_CLK_TCK")
        args = bounded(proc / str(pid) / "cmdline", 65536).split(b"\0")
        output["argv_names_installer"] = any(arg in (
            b"/usr/local/sbin/vantaline-install-release",
            b"/opt/vantaline/scripts/install_release.sh",
        ) for arg in args[:3])
    except FileNotFoundError:
        output.setdefault("exists", False)
        output["inspection"] = "process_disappeared_or_proc_unavailable"
    except Exception:
        output["inspection"] = "unavailable"
    return output


def lock_state(path=BASE / "backups/.production-release.lock", proc=PROC):
    try:
        before = path.lstat()
    except FileNotFoundError:
        return {"present": False}
    except Exception:
        return {"present": None, "inspection": "unavailable"}
    result = {"present": True, "regular_file": stat.S_ISREG(before.st_mode),
              "bytes": before.st_size, "mtime_epoch": before.st_mtime,
              "owner_uid": before.st_uid, "mode": oct(stat.S_IMODE(before.st_mode))}
    if not result["regular_file"]:
        return result
    try:
        data, opened, finished = bounded(path, 64, metadata=True)
        after = path.lstat()
        result["stable_during_read"] = len({identity(item) for item in (before, opened, finished, after)}) == 1
        if not result["stable_during_read"]:
            result["inspection"] = "unavailable"
            return result
        value = data.strip()
        if re.fullmatch(rb"[1-9][0-9]{0,9}", value):
            process = process_state(int(value), proc)
            result["process"] = process
            if "started_at_epoch" in process:
                result["process_started_before_lock"] = process["started_at_epoch"] <= before.st_mtime
        else:
            result["pid_format"] = "invalid"
    except Exception:
        result["inspection"] = "unavailable"
    return result


def version_fields(value):
    result = {}
    if not isinstance(value, dict):
        return {"inspection": "invalid"}
    for key in ("release", "git_commit"):
        text = value.get(key)
        pattern = r"v[0-9]{4}\.[0-9]{2}\.[0-9]+" if key == "release" else r"[a-f0-9]{40}"
        if isinstance(text, str) and re.fullmatch(pattern, text):
            result[key] = text
    if type(value.get("consistent")) is bool:
        result["consistent"] = value["consistent"]
    return result


def service_state(name):
    keys = ("LoadState", "ActiveState", "SubState", "MainPID", "TimeoutStopUSec", "KillMode")
    try:
        process = subprocess.run(["systemctl", "show", name, "--no-pager", "--property=" + ",".join(keys)],
                                 capture_output=True, text=True, timeout=5, check=False)
        if process.returncode or len(process.stdout) > 4096:
            return {"inspection": "unavailable"}
        result = {}
        for line in process.stdout.splitlines():
            key, separator, value = line.partition("=")
            if separator and key in keys and re.fullmatch(r"[a-zA-Z0-9_. -]{0,64}", value):
                result[key] = value
        return result
    except Exception:
        return {"inspection": "unavailable"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Version endpoint redirect refused")


def validate_report(value):
    """Reject arbitrary remote/profile output before exposing Actions logs."""
    def fields(item, allowed):
        if not isinstance(item, dict) or not item.keys() <= allowed:
            raise ValueError("Invalid diagnostic report fields")
    def scalar_fields(item, patterns):
        for key, field in item.items():
            pattern = patterns[key]
            if not isinstance(field, str) or not re.fullmatch(pattern, field):
                raise ValueError("Invalid diagnostic report value")
    def numbers(item, names):
        for name in names & item.keys():
            if type(item[name]) not in (int,float) or not math.isfinite(item[name]) or item[name] < 0:
                raise ValueError("Invalid diagnostic number")
    def inspection(item):
        if "inspection" in item and item["inspection"] not in ("unavailable","invalid","process_disappeared_or_proc_unavailable"):
            raise ValueError("Invalid diagnostic inspection")
    fields(value, {"schema","observed_at","lock","services","installed_script_sha256",
                   "installed_script","current_version","http_version"})
    if type(value.get("schema")) is not int or value["schema"] != 1:
        raise ValueError("Invalid diagnostic schema")
    scalar_fields({"observed_at":value["observed_at"]}, {"observed_at":r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}\+00:00"})
    datetime.datetime.fromisoformat(value["observed_at"])
    lock=value["lock"]
    fields(lock,{"present","regular_file","bytes","mtime_epoch","owner_uid","mode","process",
                 "process_started_before_lock","pid_format","stable_during_read","inspection"})
    numbers(lock,{"bytes","mtime_epoch","owner_uid"});inspection(lock)
    for name in {"present","regular_file","process_started_before_lock","stable_during_read"} & lock.keys():
        if type(lock[name]) is not bool and not (name=="present" and lock[name] is None):
            raise ValueError("Invalid diagnostic boolean")
    if "mode" in lock:scalar_fields({"mode":lock["mode"]},{"mode":r"0o[0-7]{1,4}"})
    if "pid_format" in lock and lock["pid_format"]!="invalid":raise ValueError("Invalid PID report")
    if "process" in lock:
        proc=lock["process"]
        fields(proc,{"pid","parent_pid","state","started_at_epoch","exists","inspection","argv_names_installer"})
        numbers(proc,{"pid","parent_pid","started_at_epoch"});inspection(proc)
        if "state" in proc:scalar_fields({"state":proc["state"]},{"state":r"[RSDZTtXxKWPI]|unknown"})
        for name in {"exists","argv_names_installer"} & proc.keys():
            if type(proc[name]) is not bool:raise ValueError("Invalid process boolean")
    fields(value["services"],{"vantaline","vantaline-label-worker"})
    for service in value["services"].values():
        fields(service,{"LoadState","ActiveState","SubState","MainPID","TimeoutStopUSec","KillMode","inspection"})
        inspection(service)
        patterns={"LoadState":r"loaded|not-found|error|bad-setting|masked|stub|merged",
                  "ActiveState":r"active|inactive|failed|activating|deactivating|reloading|maintenance|refreshing",
                  "SubState":r"running|dead|failed|exited|start|start-pre|start-post|stop|stop-sigterm|stop-sigkill|stop-post|auto-restart|auto-restart-queued|condition|final-sigterm|final-sigkill|reload|reload-signal|reload-notify|cleaning",
                  "MainPID":r"[0-9]{1,10}","TimeoutStopUSec":r"infinity|(?:[0-9]+(?:\.[0-9]+)?(?:us|ms|s|min|h|d|w|month|y)(?: |$)){1,6}",
                  "KillMode":r"control-group|mixed|process|none"}
        scalar_fields({k:v for k,v in service.items() if k!="inspection"},patterns)
    for name in ("current_version","http_version"):
        part=value[name];fields(part,{"release","git_commit","consistent","inspection"});inspection(part)
        if {k:v for k,v in part.items() if k!="inspection"} != version_fields(part):
            raise ValueError("Invalid diagnostic version")
    if "installed_script_sha256" in value:
        scalar_fields({"hash":value["installed_script_sha256"]},{"hash":r"[a-f0-9]{64}"})
    if "installed_script" in value:
        fields(value["installed_script"],{"inspection"});inspection(value["installed_script"])
    return value


def collect():
    result = {"schema": 1, "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="microseconds"),
              "lock": lock_state(), "services": {}}
    for name in ("vantaline", "vantaline-label-worker"):
        result["services"][name] = service_state(name)
    try:
        result["installed_script_sha256"] = hashlib.sha256(bounded(INSTALLER, 2 * 1024 * 1024)).hexdigest()
    except Exception:
        result["installed_script"] = {"inspection": "unavailable"}
    try:
        result["current_version"] = version_fields(json.loads(bounded(BASE / "current/VERSION.json", 16384)))
    except Exception:
        result["current_version"] = {"inspection": "unavailable"}
    try:
        # Fixed loopback GET; no configurable URL or authenticated API request.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open("http://127.0.0.1:8765/api/version", timeout=5) as response:
            raw = response.read(16385)
        if len(raw) > 16384:
            raise ValueError("Version response exceeds bound")
        result["http_version"] = version_fields(json.loads(raw))
    except Exception:
        result["http_version"] = {"inspection": "unavailable"}
    return result


class DiagnosticDeadline(BaseException):
    """Not swallowed by per-field unavailable fallback."""


def deadline_handler(signum, frame):
    raise DiagnosticDeadline()


DEADLINE_SECONDS = 30


def main():
    if not hasattr(signal, "SIGALRM"):
        raise SystemExit("Diagnostic collection requires POSIX deadline support")
    previous = signal.signal(signal.SIGALRM, deadline_handler)
    signal.setitimer(signal.ITIMER_REAL, DEADLINE_SECONDS)
    try:
        result = collect()
    except DiagnosticDeadline:
        raise SystemExit("Diagnostic deadline exceeded; no report emitted") from None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    print(json.dumps(validate_report(result), sort_keys=True))


if __name__ == "__main__":
    if sys.argv[1:] == ["--validate"]:
        try:
            raw = sys.stdin.read(16385)
            if len(raw)>16384:raise ValueError("Report too large")
            print(json.dumps(validate_report(json.loads(raw)),sort_keys=True))
        except Exception:
            raise SystemExit("Read-only diagnostic report rejected; raw output suppressed") from None
    elif len(sys.argv)==1:
        main()
    else:
        raise SystemExit("Unsupported diagnostic invocation")

"""Fail-closed Linux DOC converter; never use unconfined headless LibreOffice.

Provisioning/versions/fonts must be commissioned independently before enabling.
The sandbox exposes runtime libraries/fonts, never host HOME or customer files.
"""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

from .text_inspection_v2 import DOCUMENT_MAX_BYTES


def available() -> bool:
    return (sys.platform == "linux" and os.environ.get("VANTALINE_DOC_CONVERTER_VERIFIED") == "true"
            and all(shutil.which(cmd) for cmd in ("bwrap", "prlimit", "soffice")))


def convert(data: bytes) -> bytes:
    if not available():
        raise ValueError("DOC 安全转换组件或字体尚未通过生产验收，请上传 DOCX")
    if not data.startswith(bytes.fromhex("d0cf11e0a1b11e1")) or len(data) > DOCUMENT_MAX_BYTES:
        raise ValueError("无效或过大的 DOC")
    with tempfile.TemporaryDirectory(prefix="vantaline-doc-") as temporary:
        work = Path(temporary)
        (work / "source.doc").write_bytes(data)
        (work / "profile/user").mkdir(parents=True)
        (work / "profile/user/registrymodifications.xcu").write_text('''<?xml version="1.0"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Misc"><prop oor:name="LinkUpdateMode" oor:op="fuse"><value>0</value></prop></item>
</oor:items>''')
        command = [shutil.which("prlimit"), "--as=2147483648", "--cpu=45", "--fsize=125829120", "--nofile=128", "--nproc=64", "--",
                   shutil.which("bwrap"), "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
                   "--ro-bind", "/usr", "/usr", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                   "--dir", "/etc"]
        for path in ("/bin", "/lib", "/lib64", "/etc/fonts", "/etc/ld.so.cache"):
            if Path(path).exists():
                command += ["--ro-bind", path, path]
        command += ["--bind", temporary, "/work", "--chdir", "/work", "--clearenv",
                    "--setenv", "HOME", "/work", "--setenv", "PATH", "/usr/bin:/bin",
                    "--setenv", "SAL_USE_VCLPLUGIN", "gen", "--setenv", "LANG", "C.UTF-8",
                    "--", shutil.which("soffice"), "-env:UserInstallation=file:///work/profile", "--headless",
                    "--nologo", "--nodefault", "--norestore", "--convert-to", "docx", "--outdir", "/work", "/work/source.doc"]
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            code = process.wait(timeout=60)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise ValueError("DOC 转换超时") from exc
        target = work / "source.docx"
        if code or not target.is_file() or target.stat().st_size > DOCUMENT_MAX_BYTES:
            raise ValueError("DOC 安全转换失败")
        return target.read_bytes()

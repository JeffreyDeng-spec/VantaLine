"""Image worker log classification, file paths and process liveness diagnostics."""
from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import Any
from .image_worker_diagnostic_ports import ImageDiagnosticMedia, ImageDiagnosticRuntime, ImageDiagnosticPolicy

@dataclass(frozen=True)
class ImageWorkerDiagnostics:
    media: ImageDiagnosticMedia
    runtime: ImageDiagnosticRuntime
    policy: ImageDiagnosticPolicy

    def image_job_is_active(self, status: str) -> bool:
        return status in self.policy.IMAGE_JOB_ACTIVE_STATUSES()


    def codex_log_has_generated_image(self, log_path: Path) -> bool:
        if not self.media._business_files().exists(log_path):
            return False
        try:
            text = self.media._business_files().read_text(log_path, encoding="utf-8", errors="ignore")
        except OSError:
            return False
        return "/.codex/generated_images/" in text or "/home/dministrator/.codex/generated_images/" in text


    def image_job_output_path(self, job: dict[str, Any], *, for_write: bool = False) -> Path:
        return self.media.resolve_service_path()(job.get("output_path", ""), for_write=for_write)


    def image_job_log_path(self, job: dict[str, Any]) -> Path:
        raw_path = str(job.get("log_path") or "").strip()
        if raw_path:
            return self.media.resolve_service_path()(raw_path)
        job_id = str(job.get("job_id") or job.get("task_id") or "image_worker")
        return self.media.IMAGE_WORKER_LOG_DIR() / f"{self.media.safe_name()(job_id)}.log"


    def read_image_worker_log_tail(self, log_path: Path) -> str:
        if not self.media._business_files().exists(log_path):
            return ""
        try:
            with self.media._business_files().open_read(log_path) as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - self.policy.IMAGE_WORKER_LOG_TAIL_BYTES()))
                return handle.read().decode("utf-8", errors="ignore")
        except OSError:
            return ""


    def classify_image_worker_failure(self, log_path: Path, return_code: int | None, output_path: Path, *, stale: bool = False) -> str:
        text = self.media.read_image_worker_log_tail()(log_path)
        lower = text.lower()
        causes: list[str] = []
        if "toomanyrequests" in lower or "too many requests" in lower or "rate limit" in lower or "429" in lower:
            causes.append("图像生成供应商限流（TooManyRequests/429）")
        if "forbidden" in lower:
            causes.append("备用图像连接器被拒绝（FORBIDDEN）")
        if "fallback" in lower and ("approval" in lower or "approve" in lower or "explicit" in lower or "openai_api_key" in lower):
            causes.append("CLI fallback 需要显式配置或批准")
        if stale:
            causes.append("任务标记为 running，但当前服务没有发现仍在写日志的 Image Worker 进程")
        if return_code is not None:
            if return_code == 0:
                causes.append("Codex CLI 退出码 0，但没有写出目标 PNG")
            else:
                causes.append(f"Codex CLI 退出码 {return_code}")
        if not self.media._business_files().exists(output_path):
            causes.append(f"未生成目标 PNG：{output_path}")
        if not causes:
            causes.append("图像生成结束但未产出可用图片")
        return "；".join(causes) + "。请稍后重试，或配置并批准可用的 Image Worker fallback 后重新排队。"


    def image_worker_process_alive(self, job_id: str) -> bool:
        process = self.runtime._image_worker_processes().get(job_id)
        return bool(process and process.poll() is None)


    def codex_process_has_log_open(self, log_path: Path) -> bool:
        if not self.media._business_files().exists(log_path) or not self.media._business_files().exists(Path("/proc")):
            return False
        target = str(log_path.resolve())
        for pid_dir in self.media._business_files().iterdir(Path("/proc")):
            if not pid_dir.name.isdigit():
                continue
            try:
                cmdline = self.media._business_files().read_bytes(pid_dir / "cmdline").decode("utf-8", errors="ignore").replace("\x00", " ")
            except OSError:
                continue
            if "codex" not in cmdline:
                continue
            fd_dir = pid_dir / "fd"
            try:
                for fd in self.media._business_files().iterdir(fd_dir):
                    try:
                        linked = os.readlink(fd)
                    except OSError:
                        continue
                    if linked.removesuffix(" (deleted)") == target:
                        return True
            except OSError:
                continue
        return False


    def image_job_has_live_worker(self, job: dict[str, Any], log_path: Path) -> bool:
        job_id = str(job.get("job_id") or "")
        return self.runtime.image_worker_process_alive()(job_id) or self.runtime.codex_process_has_log_open()(log_path)


    def running_image_job_is_stale(self, job: dict[str, Any], log_path: Path) -> bool:
        if self.runtime.image_job_has_live_worker()(job, log_path):
            return False
        now = int(time.time())
        try:
            age = now - int(self.media._business_files().stat(log_path).st_mtime) if self.media._business_files().exists(log_path) else now - int(job.get("started_at") or job.get("created_at") or now)
        except (OSError, ValueError, TypeError):
            age = 0
        provider = str(job.get("provider") or "")
        generation_method = str(job.get("generation_method") or "")
        if generation_method == "codex_exec_image_worker" and provider == self.policy.LOCAL_CODEX_IMAGE_PROVIDER():
            return age >= self.policy.IMAGE_WORKER_STALE_SECONDS()
        return age >= self.policy.IMAGE_WORKER_STALE_SECONDS()

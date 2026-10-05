"""Existing image execution and evidence settlement; no provider retry policy changes."""
from dataclasses import dataclass
import cv2
import json
import mimetypes
import os
from pathlib import Path
import requests
import shutil
import signal
import subprocess
import time
from typing import Any
from .image_job_execution_ports import ImageExecutionFiles, ImageExecutionEvidence, ImageExecutionProviders

@dataclass(frozen=True)
class ImageJobExecution:
    files: ImageExecutionFiles
    evidence: ImageExecutionEvidence
    providers: ImageExecutionProviders

    def run_windows_worker_image_job(self, path: Path, candidate: dict[str, Any], job: dict[str, Any], *, reason: str) -> bool:
        job_id = str(job.get("job_id") or f"imgjob_{candidate.get('id')}")
        output_path = self.files.image_job_output_path()(job, for_write=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.files.IMAGE_WORKER_LOG_DIR().mkdir(parents=True, exist_ok=True)
        log_path = self.files.IMAGE_WORKER_LOG_DIR() / f"{self.files.safe_name()(job_id)}.windows_worker_image.log"
        self.evidence.mutate_candidate_image_job()(
            path,
            candidate,
            job,
            {
                "status": "failed",
                "progress": 100,
                "provider": self.providers.LOCAL_CODEX_IMAGE_PROVIDER(),
                "generation_method": "codex_exec_image_worker",
                "failed_at": int(time.time()),
                "error": "Windows-worker image fallback is retired. Configure Cursor Image2 or local Codex image generation.",
                "output_path": str(output_path),
                "output_url": self.files.public_output_url()(output_path),
                "log_path": str(log_path),
            },
        )
        return False
        input_files: list[Path] = []
        missing_input_files: list[str] = []
        for item in job.get("input_files", []) or []:
            input_path = self.files.resolve_service_path()(item)
            if self.files._business_files().exists(input_path):
                input_files.append(input_path)
            else:
                missing_input_files.append(str(item))
        if missing_input_files:
            self.evidence.mutate_candidate_image_job()(
                path,
                candidate,
                job,
                {
                    "status": "failed",
                    "progress": 100,
                    "provider": self.providers.LOCAL_CODEX_IMAGE_PROVIDER(),
                    "generation_method": "codex_exec_image_worker",
                    "failed_at": int(time.time()),
                    "error": "Windows Codex image worker cannot run because input files are missing: "
                    + "；".join(missing_input_files[:4])
                    + ("；..." if len(missing_input_files) > 4 else ""),
                    "output_path": str(output_path),
                    "output_url": self.files.public_output_url()(output_path),
                    "log_path": str(log_path),
                },
            )
            return False
        if not input_files:
            self.evidence.mutate_candidate_image_job()(
                path,
                candidate,
                job,
                {
                    "status": "failed",
                    "progress": 100,
                    "provider": self.providers.LOCAL_CODEX_IMAGE_PROVIDER(),
                    "generation_method": "codex_exec_image_worker",
                    "failed_at": int(time.time()),
                    "error": "Windows Codex image worker cannot run because no input image files were found.",
                    "output_path": str(output_path),
                    "output_url": self.files.public_output_url()(output_path),
                    "log_path": str(log_path),
                },
            )
            return False

        try:
            endpoint = self.providers.windows_worker_base_url()()
        except Exception as exc:
            self.evidence.mutate_candidate_image_job()(
                path,
                candidate,
                job,
                {
                    "status": "failed",
                    "progress": 100,
                    "provider": self.providers.LOCAL_CODEX_IMAGE_PROVIDER(),
                    "generation_method": "codex_exec_image_worker",
                    "failed_at": int(time.time()),
                    "error": f"{reason}; Windows Codex image worker is not configured: {exc}",
                    "output_path": str(output_path),
                    "output_url": self.files.public_output_url()(output_path),
                    "log_path": str(log_path),
                },
            )
            return False

        self.evidence.update_image_worker_status()(
            path,
            candidate,
            job,
            status="running",
            progress=max(int(job.get("progress", 0) or 0), 18),
            started_at=int(time.time()),
            provider=self.providers.LOCAL_CODEX_IMAGE_PROVIDER(),
            generation_method="codex_exec_image_worker",
            output_path=str(output_path),
            output_url=self.files.public_output_url()(output_path),
            log_path=str(log_path),
            note="系统正在通过 Windows 本地 CodexImageWorker 生成默认多角度图片。",
        )
        file_handles: list[Any] = []
        try:
            files = []
            for ref_path in input_files[:self.providers.MAX_IMAGE_WORKER_INPUTS()]:
                handle = ref_path.open("rb")
                file_handles.append(handle)
                files.append(
                    (
                        "reference_images",
                        (
                            ref_path.name,
                            handle,
                            mimetypes.guess_type(ref_path.name)[0] or "image/png",
                        ),
                    )
                )
            data = {
                "pose_family": str(job.get("pose_family") or "lying"),
                "output_name": output_path.name,
                "prompt": str(job.get("prompt") or ""),
                "generation_step": str(job.get("generation_step") or ""),
            }
            self.files._business_files().write_text(log_path, json.dumps(
                    {
                        "provider": self.providers.LOCAL_CODEX_IMAGE_PROVIDER(),
                        "endpoint": self.providers.masked_url_for_status()(endpoint),
                        "route": "/images/codex-default-crops",
                        "reason": reason,
                        "pose_family": data["pose_family"],
                        "input_count": len(files),
                        "input_files": [item.name for item in input_files[:self.providers.MAX_IMAGE_WORKER_INPUTS()]],
                        "output_path": str(output_path),
                        "requested_at": int(time.time()),
                    },
                    ensure_ascii=False,
                    indent=2,
                ), encoding="utf-8")
            response = requests.post(
                f"{endpoint}/images/codex-default-crops",
                data=data,
                files=files,
                headers=self.providers.windows_worker_headers()(),
                timeout=self.providers.windows_worker_image_timeout_seconds()(),
            )
            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError(f"Windows Codex image worker returned non-JSON response: {response.text[:240]}") from exc
            if response.status_code >= 400:
                detail = payload.get("detail") if isinstance(payload, dict) else payload
                raise RuntimeError(f"Windows Codex image worker failed: HTTP {response.status_code} {self.evidence.bounded_text()(detail, 180)}")
            if not isinstance(payload, dict):
                raise RuntimeError("Windows Codex image worker response was not a JSON object")
            self.files._business_files().write_bytes(output_path, self.providers.windows_worker_image_response_bytes()(payload))
            image = self.files._image_files().imread(str(output_path), cv2.IMREAD_UNCHANGED)
            if image is None:
                raise RuntimeError("Windows Codex image worker wrote bytes, but the saved output is not a readable image")
            self.evidence.mutate_candidate_image_job()(
                path,
                candidate,
                job,
                {
                    "status": "completed",
                    "progress": 100,
                    "provider": str(payload.get("provider") or self.providers.LOCAL_CODEX_IMAGE_PROVIDER()),
                    "generation_method": str(payload.get("method") or "codex_exec_image_worker"),
                    "output_path": str(output_path),
                    "output_url": self.files.public_output_url()(output_path),
                    "completed_at": int(time.time()),
                    "log_path": str(log_path),
                    "note": "Windows 本地 CodexImageWorker 生成任务已完成。",
                },
                preprocess_clean_sprites=True,
            )
            return True
        except Exception as exc:
            self.evidence.mutate_candidate_image_job()(
                path,
                candidate,
                job,
                {
                    "status": "failed",
                    "progress": 100,
                    "provider": self.providers.LOCAL_CODEX_IMAGE_PROVIDER(),
                    "generation_method": "codex_exec_image_worker",
                    "failed_at": int(time.time()),
                    "error": f"{reason}; {self.evidence.bounded_text()(str(exc), 240)}",
                    "output_path": str(output_path),
                    "output_url": self.files.public_output_url()(output_path),
                    "log_path": str(log_path),
                },
            )
            return False
        finally:
            for handle in file_handles:
                try:
                    handle.close()
                except OSError:
                    pass


    def run_cursor_image2_job(self, path: Path, candidate: dict[str, Any], job: dict[str, Any]) -> None:
        job_id = str(job.get("job_id") or f"imgjob_{candidate.get('id')}")
        output_path = self.files.image_job_output_path()(job, for_write=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.files.IMAGE_WORKER_LOG_DIR().mkdir(parents=True, exist_ok=True)
        log_path = self.files.IMAGE_WORKER_LOG_DIR() / f"{self.files.safe_name()(job_id)}.cursor_image2.log"
        input_files: list[str] = []
        missing_input_files: list[str] = []
        for item in job.get("input_files", []) or []:
            input_path = self.files.resolve_service_path()(item)
            if self.files._business_files().exists(input_path):
                input_files.append(str(input_path))
            else:
                missing_input_files.append(str(item))

        settings = self.providers.cursor_image2_settings()()
        if not settings["configured"]:
            self.providers.run_codex_image_job()(path, candidate, job)
            return
        if missing_input_files:
            self.evidence.update_image_worker_status()(
                path,
                candidate,
                job,
                status="failed",
                progress=100,
                failed_at=int(time.time()),
                error="部分输入图片路径不存在，且无法按当前服务根迁移：" + "；".join(missing_input_files[:4]) + ("；..." if len(missing_input_files) > 4 else ""),
                provider=self.providers.CURSOR_IMAGE2_PROVIDER(),
                output_path=str(output_path),
                output_url=self.files.public_output_url()(output_path),
                log_path=str(log_path),
            )
            return
        if not input_files:
            self.evidence.update_image_worker_status()(
                path,
                candidate,
                job,
                status="failed",
                progress=100,
                failed_at=int(time.time()),
                error="没有找到可用于 Cursor Image2 生成的有效输入图片。",
                provider=self.providers.CURSOR_IMAGE2_PROVIDER(),
                output_path=str(output_path),
                output_url=self.files.public_output_url()(output_path),
                log_path=str(log_path),
            )
            return

        self.evidence.update_image_worker_status()(
            path,
            candidate,
            job,
            status="running",
            progress=max(int(job.get("progress", 0) or 0), 12),
            started_at=int(time.time()),
            provider=self.providers.CURSOR_IMAGE2_PROVIDER(),
            output_path=str(output_path),
            output_url=self.files.public_output_url()(output_path),
            log_path=str(log_path),
            note="系统正在通过 Cursor Image2 API 生成默认图片。",
        )

        try:
            payload = self.providers.cursor_image2_payload()(job, input_files, settings)
            self.files._business_files().write_text(log_path, json.dumps(
                    {
                        "provider": self.providers.CURSOR_IMAGE2_PROVIDER(),
                        "endpoint": settings["endpoint_public"],
                        "model": settings["model"],
                        "input_count": len(input_files),
                        "output_path": str(output_path),
                        "requested_at": int(time.time()),
                    },
                    ensure_ascii=False,
                    indent=2,
                ), encoding="utf-8")
            response = requests.post(
                settings["endpoint"],
                json=payload,
                headers={**self.providers.cursor_auth_headers()(settings["api_key"]), "Content-Type": "application/json"},
                timeout=float(settings["timeout_seconds"]),
            )
            response.raise_for_status()
            response_payload = response.json()
            if not isinstance(response_payload, dict):
                raise RuntimeError("Cursor Image2 response was not a JSON object")
            image_bytes = self.providers.extract_cursor_image2_bytes()(response_payload, settings)
            self.files._business_files().write_bytes(output_path, image_bytes)
            image = self.files._image_files().imread(str(output_path), cv2.IMREAD_UNCHANGED)
            if image is None:
                raise RuntimeError("Cursor Image2 returned bytes, but the saved output is not a readable image")
            self.evidence.mutate_candidate_image_job()(
                path,
                candidate,
                job,
                {
                    "status": "completed",
                    "progress": 100,
                    "provider": self.providers.CURSOR_IMAGE2_PROVIDER(),
                    "output_path": str(output_path),
                    "output_url": self.files.public_output_url()(output_path),
                    "completed_at": int(time.time()),
                    "log_path": str(log_path),
                    "note": "Cursor Image2 API 生成任务已完成。",
                },
                preprocess_clean_sprites=True,
            )
        except Exception:
            if self.files._business_files().runtime(output_path) is not None:
                # Provider acceptance may already have happened. A timeout, storage
                # failure or database failure must never submit a second paid job.
                self.evidence.update_image_worker_status()(
                    path, candidate, job, status="failed", progress=100,
                    failed_at=int(time.time()), provider=self.providers.CURSOR_IMAGE2_PROVIDER(),
                    error="生成或持久保存未确认成功；未自动重试付费调用，请先核对原任务。",
                    output_path=str(output_path), log_path=str(log_path),
                )
                return
            self.providers.run_codex_image_job()(path, candidate, job)


    def run_cos_codex_image_job(self, path: Path, candidate: dict[str, Any], job: dict[str, Any], runtime) -> None:
        from ..storage.artifacts.native import image_job
        job_id = str(job.get("job_id") or f"imgjob_{candidate.get('id')}")
        output_path = self.files.image_job_output_path()(job, for_write=True)
        log_path = self.files.IMAGE_WORKER_LOG_DIR() / f"{self.files.safe_name()(job_id)}.log"
        def process_changed(process):
            if process is None:
                self.evidence._image_worker_processes().pop(job_id, None)
            else:
                self.evidence._image_worker_processes()[job_id] = process
        try:
            inputs = [self.files.resolve_service_path()(value) for value in (job.get("input_files") or [])[:self.providers.MAX_IMAGE_WORKER_INPUTS()]]
            if not inputs or not all(self.files._business_files().is_file(value) for value in inputs):
                raise RuntimeError("missing image input")
            generations = {}
            for destination in (output_path, log_path):
                key = runtime.key(destination)
                row = runtime.store.locations.get(key)
                generations[key] = row.generation if row else 0
            self.evidence.update_image_worker_status()(path, candidate, job, status="running", progress=12,
                                       started_at=int(time.time()), output_path=str(output_path), log_path=str(log_path))
            prompt = lambda output: self.evidence.image_job_prompt()({**job, "output_path": output}) + "\n"
            with image_job(runtime, inputs, prompt, on_process=process_changed) as (output, log, code):
                runtime.store.put(runtime.key(log_path), log, expected_generation=generations[runtime.key(log_path)])
                if code != 0 or not output.is_file() or not self.evidence.codex_log_has_generated_image()(log_path):
                    raise RuntimeError("native image generation was not confirmed")
                if self.files._image_files().imread(str(output), cv2.IMREAD_UNCHANGED) is None:
                    raise RuntimeError("native image output is invalid")
                runtime.store.put(runtime.key(output_path), output, expected_generation=generations[runtime.key(output_path)])
            self.evidence.mutate_candidate_image_job()(path, candidate, job, {
                "status": "completed", "progress": 100, "completed_at": int(time.time()),
                "output_path": str(output_path), "output_url": self.files.public_output_url()(output_path),
                "log_path": str(log_path), "note": "图像已生成并持久保存。",
            }, preprocess_clean_sprites=True)
        except Exception:
            self.evidence.update_image_worker_status()(path, candidate, job, status="failed", progress=100,
                                       failed_at=int(time.time()), log_path=str(log_path),
                                       error="图像生成或持久保存未确认成功；未自动重试付费调用。")


    def run_codex_image_job(self, path: Path, candidate: dict[str, Any], job: dict[str, Any]) -> None:
        runtime = self.files._business_files().runtime(self.files.image_job_output_path()(job, for_write=True))
        if runtime is not None:
            return self.providers.run_cos_codex_image_job()(path, candidate, job, runtime)
        job_id = str(job.get("job_id") or f"imgjob_{candidate.get('id')}")
        output_path = self.files.image_job_output_path()(job, for_write=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.files.IMAGE_WORKER_LOG_DIR().mkdir(parents=True, exist_ok=True)
        log_path = self.files.IMAGE_WORKER_LOG_DIR() / f"{self.files.safe_name()(job_id)}.log"
        input_files: list[str] = []
        missing_input_files: list[str] = []
        for item in job.get("input_files", []) or []:
            input_path = self.files.resolve_service_path()(item)
            if self.files._business_files().exists(input_path):
                input_files.append(str(input_path))
            else:
                missing_input_files.append(str(item))

        if not shutil.which("codex"):
            self.evidence.update_image_worker_status()(
                path,
                candidate,
                job,
                status="failed",
                progress=100,
                failed_at=int(time.time()),
                error="codex CLI was not found on PATH.",
                output_path=str(output_path),
                output_url=self.files.public_output_url()(output_path),
                log_path=str(log_path),
            )
            return
        if missing_input_files:
            self.evidence.update_image_worker_status()(
                path,
                candidate,
                job,
                status="failed",
                progress=100,
                failed_at=int(time.time()),
                error="部分输入图片路径不存在，且无法按当前服务根迁移："
                + "；".join(missing_input_files[:4])
                + ("；..." if len(missing_input_files) > 4 else ""),
                output_path=str(output_path),
                output_url=self.files.public_output_url()(output_path),
                log_path=str(log_path),
            )
            return
        if not input_files:
            self.evidence.update_image_worker_status()(
                path,
                candidate,
                job,
                status="failed",
                progress=100,
                failed_at=int(time.time()),
                error="没有找到可用于生成的有效输入图片。",
                output_path=str(output_path),
                output_url=self.files.public_output_url()(output_path),
                log_path=str(log_path),
            )
            return

        command = [
            "codex",
            "exec",
            "--sandbox",
            "workspace-write",
            "-C",
            str(self.files.ROOT()),
        ]
        for input_file in input_files[:self.providers.MAX_IMAGE_WORKER_INPUTS()]:
            command.extend(["-i", input_file])
        command.append("-")

        self.evidence.update_image_worker_status()(
            path,
            candidate,
            job,
            status="running",
            progress=max(int(job.get("progress", 0) or 0), 12),
            started_at=int(time.time()),
            output_path=str(output_path),
            output_url=self.files.public_output_url()(output_path),
            log_path=str(log_path),
            note="系统正在处理这个图像生成任务。",
        )

        process: subprocess.Popen | None = None
        try:
            with log_path.open("w", encoding="utf-8", errors="replace") as log:
                log.write(f"$ {' '.join(command)}\n\n")
                log.flush()
                process = subprocess.Popen(
                    command,
                    cwd=str(self.files.ROOT()),
                    stdin=subprocess.PIPE,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
                self.evidence._image_worker_processes()[job_id] = process
                process.communicate(self.evidence.image_job_prompt()(job) + "\n", timeout=900)
                return_code = process.returncode
        except subprocess.TimeoutExpired:
            if process:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
            self.evidence.update_image_worker_status()(
                path,
                candidate,
                job,
                status="failed",
                progress=100,
                failed_at=int(time.time()),
                error="图像生成超过 900 秒未完成。",
                log_path=str(log_path),
            )
            return
        except Exception as exc:
            self.evidence.update_image_worker_status()(
                path,
                candidate,
                job,
                status="failed",
                progress=100,
                failed_at=int(time.time()),
                error=str(exc),
                log_path=str(log_path),
            )
            return
        finally:
            self.evidence._image_worker_processes().pop(job_id, None)

        if return_code == 0 and self.files._business_files().exists(output_path) and not self.evidence.codex_log_has_generated_image()(log_path):
            updated_job = self.evidence.mutate_candidate_image_job()(
                path,
                candidate,
                job,
                {
                    "status": "failed",
                    "progress": 100,
                    "failed_at": int(time.time()),
                    "error": "生成结束但日志中没有可用的 AI 图像结果；已拒绝非生成输出。",
                    "output_path": str(output_path),
                    "output_url": self.files.public_output_url()(output_path),
                    "log_path": str(log_path),
                },
            )
            if updated_job.get("status") == "failed":
                try:
                    self.files._business_files().unlink(output_path)
                except OSError:
                    pass
        elif return_code == 0 and self.files._business_files().exists(output_path):
            self.evidence.mutate_candidate_image_job()(
                path,
                candidate,
                job,
                {
                    "status": "completed",
                    "progress": 100,
                    "output_path": str(output_path),
                    "output_url": self.files.public_output_url()(output_path),
                    "completed_at": int(time.time()),
                    "log_path": str(log_path),
                    "note": "本地生成任务已完成。",
                },
                preprocess_clean_sprites=True,
            )
        else:
            self.evidence.mutate_candidate_image_job()(
                path,
                candidate,
                job,
                {
                    "status": "failed",
                    "progress": 100,
                    "failed_at": int(time.time()),
                    "error": self.evidence.classify_image_worker_failure()(log_path, return_code, output_path),
                    "output_path": str(output_path),
                    "output_url": self.files.public_output_url()(output_path),
                    "log_path": str(log_path),
                },
            )


    def run_image_generation_job(self, path: Path, candidate: dict[str, Any], job: dict[str, Any]) -> None:
        provider = str(job.get("provider") or "").strip()
        status = str(job.get("status") or "").strip()
        if provider == self.providers.CURSOR_IMAGE2_PROVIDER() or status == self.providers.CURSOR_IMAGE2_QUEUE_STATUS():
            self.providers.run_cursor_image2_job()(path, candidate, job)
            return
        if provider == self.providers.LOCAL_CODEX_IMAGE_PROVIDER() or status == self.providers.CODEX_IMAGE_WORKER_QUEUE_STATUS():
            self.providers.run_codex_image_job()(path, candidate, job)
            return
        self.providers.run_codex_image_job()(path, candidate, job)

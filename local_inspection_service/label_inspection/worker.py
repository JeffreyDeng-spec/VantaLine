"""Two durable, at-most-once model stages. Interrupted stages are never replayed."""

import copy
import json
import os
import threading
import logging
import math
from collections.abc import Callable
from pathlib import Path
from .dependencies import RepositoryLifecycle, ModelProvider, require_models
import time
from . import model, quality, manual
from ..storage.label_inspection import LabelRepository
from ..storage.label_run_projection import LabelRunProjection
from ..runtime.label_metrics import LabelRuntimeMetrics
from ..codex_compare.media import MediaStore


def process(
    repo, media, run, key, invoke=model.invoke, resolved=None, record_call=None
):
    owner, identity = run["owner_user_id"], run["id"]
    is_pdf = run.get("strategy") == manual.VERSION
    if is_pdf and resolved:
        resolved = {**resolved, "model": model.MODEL, "timeout_seconds": 180}
    engine = manual if is_pdf else model
    started = time.monotonic()

    def stage(name, images, cropped=False):
        body = engine.payload(name, images, cropped)
        if resolved and not is_pdf:
            body["model"] = resolved["model"]
        audit = copy.deepcopy(body)
        hashes = [media.put(owner, data) for data in images]
        iterator = iter(hashes)
        for part in audit["messages"][0]["content"]:
            if part["type"] == "image_url":
                part["image_url"] = {"sha256": next(iterator), "encoding": "JPEG"}
        call = repo.begin_call(owner, identity, name, audit, hashes)
        start = time.monotonic()
        response = None

        def account(ok):
            if record_call and resolved:
                try:
                    record_call(
                        resolved,
                        round((time.monotonic() - start) * 1000),
                        ok,
                        response.get("usage", {}) if isinstance(response, dict) else {},
                    )
                except Exception:
                    import logging

                    logging.getLogger(__name__).warning(
                        "Model usage accounting unavailable"
                    )

        try:
            if resolved:
                from ..model_profiles.transport import invoke as profile_invoke

                status, raw = profile_invoke(
                    body,
                    (
                        {**resolved, "timeout_seconds": 180, "model": model.MODEL}
                        if is_pdf
                        else resolved
                    ),
                )
            else:
                status, raw = invoke(body, key)
            # Persist evidence before parsing; failures remain inspectable without replay.
            response = None
            try:
                response = json.loads(raw)
            except (ValueError, TypeError):
                pass
            repo.finish_call(
                owner,
                call["id"],
                status="received",
                http_status=status,
                elapsed=time.monotonic() - start,
                raw_response=raw.replace(key, "[REDACTED]"),
                usage=response.get("usage", {}) if isinstance(response, dict) else {},
            )
        except Exception:
            account(False)
            repo.finish_call(
                owner,
                call["id"],
                status="unknown",
                elapsed=time.monotonic() - start,
                error="网络中断或响应超限，调用结果未知；不会自动重试",
            )
            raise ValueError("模型调用结果未知；请查看诊断后手动重新检测") from None
        try:
            if status != 200:
                raise ValueError(f"模型服务返回 HTTP {status}；未自动重试")
            if not isinstance(response, dict):
                raise ValueError("模型服务未返回 JSON")
            parsed = model.parse(response)
        except Exception:
            account(False)
            raise
        account(True)
        return parsed

    quality_record = copy.deepcopy(run.get("quality") or {})

    def quality_save():
        repo.update_run(owner, identity, quality=quality_record)

    try:
        if quality_record.get("policy") != (
            manual.POLICY if is_pdf else quality.POLICY
        ):
            raise quality.Rejected("QUALITY_POLICY_CHANGED")
        if ((is_pdf or not resolved) and run["model"] != model.MODEL) or run[
            "prompt_hash"
        ] != engine.PROMPT_HASH:
            raise ValueError("提交后的模型或提示词版本发生变化，请手动重新检测")
        reference, ref_transform = (manual.decode_standard if is_pdf else model.decode)(
            media.read(owner, run["reference"]["media"]["original"])
        )
        actual, transform = model.decode(media.read(owner, run["actual"]["original"]))
        reference_input, actual_input = engine.jpeg(reference), engine.jpeg(actual)
        repo.update_run(
            owner,
            identity,
            transformations={"reference": ref_transform, "actual": transform},
        )
        if is_pdf:
            quality_record["preflight"] = {"passed": True, "method": "basic-decode"}
            quality_save()
            repo.update_run(owner, identity, phase="layout")
            layout = stage("layout", [actual_input])
            repo.update_run(owner, identity, layout=layout)
            crop = manual.crop_rect(layout, actual.size)
            x, y, w, h = crop
            actual_input = manual.jpeg(actual.crop((x, y, x + w, y + h)))
            quality_record["selected"] = {
                "passed": True,
                "method": "model-readability",
                "crop": crop,
            }
            quality_save()
            repo.update_run(
                owner,
                identity,
                crop=crop,
                coordinate_space=model.COORDINATE_SPACE,
                scope="仅检测框选的单张页面",
            )
        else:
            repo.update_run(owner, identity, phase="quality")
            try:
                quality_record["preflight"] = quality.inspect(actual_input, actual.size)
            except Exception:
                raise quality.Rejected("QUALITY_UNAVAILABLE") from None
            quality_save()
            if not quality_record["preflight"]["passed"]:
                raise quality.Rejected(quality_record["preflight"]["code"])
            repo.update_run(owner, identity, phase="layout")
            layout = stage("layout", [actual_input])
            crop = model.crop_rect(layout, actual.size)
            if crop:
                x, y, w, h = crop
                actual_input = model.jpeg(actual.crop((x, y, x + w, y + h)))
            repo.update_run(
                owner,
                identity,
                phase="compare",
                layout=layout,
                crop=crop,
                coordinate_space=model.COORDINATE_SPACE,
                scope="仅检测选中标签" if crop else "检测实物图中的单张标签",
            )
            repo.update_run(owner, identity, phase="quality_selected")
            selected_started = time.monotonic()
            target = quality.selected(quality_record["preflight"], crop, actual.size)
            quality_record["selected"] = {
                "passed": bool(target and target["passed"]),
                "code": (
                    None
                    if target and target["passed"]
                    else (
                        "QUALITY_SELECTED_REJECTED"
                        if target
                        else "QUALITY_TARGET_UNCERTAIN"
                    )
                ),
                "candidate": target,
                "crop": crop,
            }
            if target and target["passed"] and crop:
                try:
                    quality_record["selected"]["recheck"] = quality.recheck(
                        actual_input, target, crop, actual.size
                    )
                except Exception:
                    raise quality.Rejected("QUALITY_UNAVAILABLE") from None
                if not quality_record["selected"]["recheck"]["passed"]:
                    quality_record["selected"].update(
                        passed=False, code="QUALITY_SELECTED_REJECTED"
                    )
            quality_record["selected"]["elapsed_ms"] = round(
                (time.monotonic() - selected_started) * 1000, 2
            )
            quality_save()
            if not quality_record["selected"]["passed"]:
                raise quality.Rejected(quality_record["selected"]["code"])
        repo.update_run(owner, identity, phase="compare")
        value = stage("compare", [reference_input, actual_input], bool(crop))
        result = engine.result(value, crop, actual.size)
        repo.update_run(
            owner,
            identity,
            status="completed",
            phase="completed",
            finished_at=time.time(),
            elapsed=time.monotonic() - started,
            result=result,
            decision=result["decision"],
        )
    except Exception as exc:
        # Never publish transport details, file paths or credentials as a user-facing error.
        error = (
            str(exc)[:300]
            if isinstance(exc, ValueError)
            else "检测未完成，证据或服务不可用；未自动重试"
        )
        try:
            repo.update_run(
                owner,
                identity,
                status="failed",
                phase="failed",
                decision="REVIEW_REQUIRED",
                finished_at=time.time(),
                elapsed=time.monotonic() - started,
                error=error.replace(key, "[REDACTED]"),
                error_code=(
                    exc.code
                    if isinstance(exc, (quality.Rejected, manual.Rejected))
                    else None
                ),
                quality=quality_record,
            )
        except Exception:
            pass  # Expiration is authoritative; late completion cannot turn green.


class LabelWorker:
    """Own two consumer threads and acknowledge drain only after both exit.

    Admission is linearized under a short process-local lock. A poll admitted
    before request_stop may still be connecting/claiming; it belongs to drain.
    No lock is held across database work, model calls, connection cleanup or join.
    The repository retains the global concurrency and paid-call fences.
    """

    SHUTDOWN_SECONDS = 420 + 60

    def __init__(self, repositories: RepositoryLifecycle,
                 data_directory: Callable[[], Path], models: ModelProvider, *, stopping: Callable[[], bool] | None = None):
        self.repositories = repositories
        self.data_directory = data_directory
        self.models = models
        self.stopping = stopping or (lambda: False)

        self.metrics = LabelRuntimeMetrics()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._drainers = 0
        self._timed_out = False
        self._cleanup_failed = False
        self._startup_failed = False
        self._paused = False
        self._active_iterations = 0
        self.runtime_identity = None

    def start(self, *, paused: bool = False):
        with self._lock:
            if self._cleanup_failed or self._startup_failed:
                raise RuntimeError("Label worker lifecycle failed; process restart required")
            alive = [thread.is_alive() for thread in self._threads]
            if self._drainers or (any(alive) and self._stop.is_set()):
                raise RuntimeError("Label worker is still draining")
            if any(alive):
                if not all(alive):
                    raise RuntimeError("Label worker lost a consumer")
                return  # Duplicate startup must not double consumer threads.
            self._stop = threading.Event()
            self._timed_out = False
            self._paused = paused
            self._active_iterations = 0
            self._threads = []
            try:
                for index in range(2):
                    thread = threading.Thread(target=self._loop, args=(self._stop,),
                                              name=f"label-inspection-{index}", daemon=True)
                    self._threads.append(thread)
                    thread.start()
            except BaseException:
                self._startup_failed = True
                self._stop.set()  # Retain all started threads for drain/restart fencing.
                raise

    def status(self) -> dict:
        with self._lock:
            alive = sum(thread.is_alive() for thread in self._threads)
            state = ("timed_out" if self._timed_out else "draining") if alive and self._stop.is_set() else (
                "running" if alive == 2 else "failed" if alive else "stopped")
            return {"state": "failed" if self._cleanup_failed or self._startup_failed else state, "live_threads": alive}

    def request_pause(self):
        """Fence new iterations; admitted DB/model/cleanup work still counts."""
        with self._lock:
            self._paused = True

    def resume(self):
        with self._lock:
            if (self._cleanup_failed or self._startup_failed or self._stop.is_set()
                    or len(self._threads) != 2 or not all(t.is_alive() for t in self._threads)):
                raise RuntimeError("Label worker cannot resume; process restart required")
            self._paused = False

    def runtime_status(self) -> dict:
        with self._lock:
            alive = sum(t.is_alive() for t in self._threads)
            if self._cleanup_failed or self._startup_failed or alive != 2:
                state = "failed"
            elif self._stop.is_set():
                state = "timed_out" if self._timed_out else "draining"
            elif self._paused:
                state = "draining" if self._active_iterations else "drained"
            else:
                state = "ready"
            return {"state": state, "active_iterations": self._active_iterations}

    def request_stop(self):
        with self._lock:
            self._stop.set()

    def drain(self, timeout: float = SHUTDOWN_SECONDS) -> bool:
        """Request stop and wait a total budget; False never means drained."""
        if timeout < 0 or not math.isfinite(timeout):
            raise ValueError("Drain timeout must be finite and nonnegative")
        deadline = time.monotonic() + timeout
        with self._lock:
            self._stop.set()
            threads = tuple(self._threads)
            self._drainers += 1
        try:
            for thread in threads:
                # start() can fail before native launch or after it. Retain every
                # attempted thread; never join an unstarted one or acknowledge a
                # generation whose startup outcome was uncertain.
                if thread.ident is not None:
                    thread.join(max(0, deadline - time.monotonic()))
            drained = not any(thread.is_alive() for thread in threads)
            with self._lock:
                self._timed_out = not drained
                return drained and not (self._cleanup_failed or self._startup_failed)
        finally:
            with self._lock:
                self._drainers -= 1

    def _loop(self, stop):
        while True:
            with self._lock:
                if stop.is_set() or self.stopping():
                    return
                paused = self._paused
                if not paused:
                    # Include connecting, claiming, model work and connection cleanup.
                    self._active_iterations += 1
            if paused:
                stop.wait(.1)
                continue
            claimed = False
            try:
                claimed = self._iteration()
            except Exception:
                # Deliberately exclude exception messages/tracebacks: providers and
                # drivers may include credentials, media or customer information.
                self.metrics.error("worker_iteration_failed")
                logging.getLogger(__name__).error('{"event":"label_worker_iteration_failed"}')
            finally:
                try:
                    self.repositories.clear()
                except Exception:
                    with self._lock:
                        self._cleanup_failed = True
                        stop.set()
                    self.metrics.error("worker_cleanup_failed")
                    logging.getLogger(__name__).error('{"event":"label_worker_cleanup_failed"}')
                finally:
                    with self._lock:
                        self._active_iterations -= 1
            if not claimed:
                stop.wait(1)

    def _iteration(self) -> dict | None:
        run = None
        try:
            if os.getenv("VANTALINE_LABEL_INSPECTION_ENABLED", "").lower() != "true":
                return None
            raw_repo = self.repositories.repository()
            if not raw_repo:
                return None
            repo = LabelRepository(raw_repo, runtime_identity=self.runtime_identity, metrics=self.metrics) if self.runtime_identity else LabelRepository(raw_repo)
            run = repo.claim()
            if not run:
                return run
            # A claimed run is never requeued, including model resolution failure.
            reference = run.get("profile_snapshot") or require_models(self.models).snapshot_for_record(run).get("label")
            resolved = require_models(self.models).resolve("label", reference) if reference else None
            process(repo, MediaStore(self.data_directory() / "label_inspection" / "media"),
                    run, resolved["api_key"] if resolved else "", resolved=resolved,
                    record_call=require_models(self.models).record_call)
            self._publish_summary(raw_repo, run)
        except Exception:
            self.metrics.error("worker_iteration_failed")
            logging.getLogger(__name__).error('{"event":"label_worker_iteration_failed"}')
        return run

    def _publish_summary(self, repository, run):
        # Business settlement has already returned/committed. Optional derived
        # work remains part of this admitted iteration, including its cleanup.
        with self._lock:
            if self._paused or self._stop.is_set() or self.stopping():
                return
        try:
            LabelRunProjection(repository).publish(run["owner_user_id"], run["id"])
        except Exception:
            self.metrics.error("summary_publication_failed")
            logging.getLogger(__name__).warning('{"event":"summary_publication_failed"}')

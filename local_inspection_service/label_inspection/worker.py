"""Two durable, at-most-once model stages. Interrupted stages are never replayed."""

import copy
import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from fastapi import FastAPI
from .dependencies import RepositoryLifecycle, ModelProvider, require_models
import time
from . import model, quality, manual
from ..storage.label_inspection import LabelRepository
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


def register(app: FastAPI, repositories: RepositoryLifecycle, data_directory: Callable[[], Path], models: ModelProvider):
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            run = None
            try:
                if (
                    os.getenv("VANTALINE_LABEL_INSPECTION_ENABLED", "").lower()
                    == "true"
                ):
                    raw_repo = repositories.repository()
                    if raw_repo:
                        repo = LabelRepository(raw_repo)
                        run = repo.claim()
                        if run:
                            reference = run.get("profile_snapshot") or require_models(models).snapshot_for_record(run).get("label")
                            resolved = (
                                require_models(models).resolve("label", reference)
                                if reference
                                else None
                            )
                            process(
                                repo,
                                MediaStore(
                                    data_directory() / "label_inspection" / "media"
                                ),
                                run,
                                resolved["api_key"] if resolved else "",
                                resolved=resolved,
                                record_call=require_models(models).record_call,
                            )
            except Exception:
                pass  # Transient DB/config failures must not replay a claimed run.
            finally:
                repositories.clear()
            if not run:
                stop.wait(1)

    def start():
        stop.clear()
        for index in range(2):
            threading.Thread(
                target=loop, name=f"label-inspection-{index}", daemon=True
            ).start()

    app.on_event("startup")(start)
    app.on_event("shutdown")(stop.set)

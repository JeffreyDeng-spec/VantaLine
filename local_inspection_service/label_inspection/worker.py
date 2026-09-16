"""Two durable, at-most-once model stages. Interrupted stages are never replayed."""

import copy
import json
import threading
import time
from . import model
from ..storage.label_inspection import LabelRepository
from ..codex_compare.media import MediaStore


def process(repo, media, run, key, invoke=model.invoke):
    owner, identity = run["owner_user_id"], run["id"]
    started = time.monotonic()

    def stage(name, images, cropped=False):
        body = model.payload(name, images, cropped)
        audit = copy.deepcopy(body)
        hashes = [media.put(owner, data) for data in images]
        iterator = iter(hashes)
        for part in audit["messages"][0]["content"]:
            if part["type"] == "image_url":
                part["image_url"] = {"sha256": next(iterator), "encoding": "JPEG"}
        call = repo.begin_call(owner, identity, name, audit, hashes)
        start = time.monotonic()
        try:
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
            repo.finish_call(
                owner,
                call["id"],
                status="unknown",
                elapsed=time.monotonic() - start,
                error="网络中断或响应超限，调用结果未知；不会自动重试",
            )
            raise ValueError("模型调用结果未知；请查看诊断后手动重新检测") from None
        if status != 200:
            raise ValueError(f"模型服务返回 HTTP {status}；未自动重试")
        if not isinstance(response, dict):
            raise ValueError("模型服务未返回 JSON")
        return model.parse(response)

    try:
        if run["model"] != model.MODEL or run["prompt_hash"] != model.PROMPT_HASH:
            raise ValueError("提交后的模型或提示词版本发生变化，请手动重新检测")
        reference, ref_transform = model.decode(
            media.read(owner, run["reference"]["media"]["original"])
        )
        actual, transform = model.decode(media.read(owner, run["actual"]["original"]))
        reference_input, actual_input = model.jpeg(reference), model.jpeg(actual)
        repo.update_run(
            owner,
            identity,
            transformations={"reference": ref_transform, "actual": transform},
        )
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
        value = stage("compare", [reference_input, actual_input], bool(crop))
        result = model.result(value, crop, actual.size)
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
            )
        except Exception:
            pass  # Expiration is authoritative; late completion cannot turn green.


def register(ns):
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            run = None
            try:
                config = model.settings()
                if config["enabled"]:
                    raw_repo = ns["runtime_postgres_repository_or_none"]()
                    if raw_repo:
                        repo = LabelRepository(raw_repo)
                        run = repo.claim()
                        if run:
                            process(
                                repo,
                                MediaStore(
                                    ns["DATA_DIR"] / "label_inspection" / "media"
                                ),
                                run,
                                config["key"],
                            )
            except Exception:
                pass  # Transient DB/config failures must not replay a claimed run.
            finally:
                ns["clear_thread_runtime_repository_selection"]()
            if not run:
                stop.wait(1)

    def start():
        stop.clear()
        for index in range(2):
            threading.Thread(
                target=loop, name=f"label-inspection-{index}", daemon=True
            ).start()

    ns["app"].on_event("startup")(start)
    ns["app"].on_event("shutdown")(stop.set)

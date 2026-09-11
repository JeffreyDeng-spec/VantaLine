"""Account-scoped, resumable preparation with at-most-once paid attempts."""
import copy
import json
import os
import threading
import time
import uuid

from fastapi import HTTPException, Request, Response
from . import standard_preparation as engine
from .document_label_classifier import evidence, prepare_image


def enabled(owner):
    return owner in {v.strip() for v in os.getenv("VANTALINE_STANDARD_PREPARATION_ACCOUNTS", "").split(",") if v.strip()}


def snapshot(assets):
    rows = []
    for a in sorted(assets, key=lambda a: int(a.get("ordinal") or 0)):
        if a.get("status") not in {"candidate", "page"}:
            continue
        active = a.get("active_preparation")
        if a.get("preparation_required") and not active:
            if a.get("preparation_previous_snapshot"):
                rows.append(copy.deepcopy(a["preparation_previous_snapshot"]))
            continue
        value = {k: a.get(k, "") for k in ("id", "sha256", "ordinal", "mime_type")}
        value["ordinal"] = int(value["ordinal"] or 0)
        if active:
            value["preparation"] = copy.deepcopy(active)
            value["reference_sha256"] = active["sha256"]
        rows.append(value)
    return rows


class PreparationJobs:
    def __init__(self, namespace):
        class LiveNamespace:
            def __getattr__(self, name):
                return namespace[name]
        self.s = LiveNamespace()
        self.namespace = namespace
        self.slots = threading.BoundedSemaphore(1)
        self.ocr_lock = threading.Lock()

    def mutate(self, identity, owner, fn, publish=False):
        if not self.s._text_v2_owned("standards", identity, owner):
            raise HTTPException(404, "标准不存在")
        repo = self.s.runtime_postgres_repository_or_none()
        if repo is not None:
            return repo.mutate_text_document(identity, owner, fn, revision_action="prepare" if publish else None)
        with self.s._incoming_text_store_lock:
            standard = self.s._text_v2_owned("standards", identity, owner)
            if not standard:
                raise HTTPException(404, "标准不存在")
            assets = [a for a in self.s._text_v2_load("assets") if a.get("owner_user_id") == owner and a.get("standard_id") == identity]
            result = fn(standard, assets)
            if publish and result.get("published"):
                self.s._text_v2_apply_revision(standard, assets, action="prepare", asset_id="", now=int(time.time()))
            for asset in assets:
                self.s._text_v2_save("assets", asset)
            self.s._text_v2_save("standards", standard)
            return result

    def check(self, standard):
        if standard.get("status") == "deleted" or standard.get("standard_type") != "label":
            raise HTTPException(409, "该订单不能准备标签标准")

    def start(self, identity, owner):
        if not self.s._text_v2_owned("standards", identity, owner):
            raise HTTPException(404, "标准不存在")
        if not enabled(owner):
            raise HTTPException(409, "标准自动准备尚未启用")
        settings = self.s.ai_detection_settings()
        if not self.s.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED or not settings.get("configured"):
            raise HTTPException(409, "请先配置并授权当前账户的视觉模型")
        if not self.slots.acquire(blocking=False):
            # A duplicate submission must still be a harmless query.
            current = self.view(identity, owner)
            if current["job"].get("state") == "processing":
                return current
            raise HTTPException(429, "标准准备繁忙，请稍后重试；未新增模型调用")
        job_id = uuid.uuid4().hex
        def claim(standard, assets):
            self.check(standard)
            if standard.get("classification", {}).get("state") == "processing":
                raise HTTPException(409, "请等待文档图片分类完成")
            if standard.get("preparation_job", {}).get("state") == "processing":
                return False
            retained = [a for a in assets if a.get("status") == "candidate"]
            if not retained:
                raise HTTPException(409, "请先保留至少一张标签")
            fresh = [a for a in retained if not a.get("preparation_attempt")]
            if not fresh:
                return False
            standard["preparation_required"] = True
            standard["preparation_job"] = dict(id=job_id, state="processing", heartbeat=time.time())
            for a in assets:
                previous = next((v for v in standard.get("confirmed_assets", []) if v["id"] == a["id"]), None)
                if previous and not a.get("active_preparation"):
                    a["preparation_previous_snapshot"] = copy.deepcopy(previous)
                a["preparation_required"] = True
            return True
        try:
            if not self.mutate(identity, owner, claim):
                self.slots.release()
                return self.view(identity, owner)
            threading.Thread(target=self.run, args=(identity, owner, job_id, settings), daemon=True).start()
        except Exception:
            self.slots.release()
            raise
        return self.view(identity, owner)

    def observe(self, image, timeout=120):
        # One prediction; do not call the legacy two-pass matching routine.
        from .standard_preparation_ocr import recognize
        return engine.observations(image, lambda bgr: recognize(bgr, timeout=timeout))

    def store(self, identity, owner, asset, image, elements, **options):
        data, metadata = engine.clean(image, elements, **options)
        revision = uuid.uuid4().hex
        annotated = engine.overlay(image, elements)
        for kind, blob in (("clean", data), ("overlay", annotated)):
            path = self.s._text_v2_media_path(owner, identity, f"preparation_{revision}_{kind}.png")
            self.s._text_v2_write(path, blob)
            metadata[kind+"_sha256"] = self.s.sha256_bytes(blob)
        return {**metadata, "id": revision, "source_sha256": asset["sha256"], "created_at": time.time(),
                "human": bool(options.get("human"))}

    def run(self, identity, owner, job_id, settings):
        try:
            while True:
                def take(standard, assets):
                    self.check(standard)
                    if standard.get("preparation_job", {}).get("id") != job_id:
                        return None
                    for a in assets:
                        if a.get("status") == "candidate" and not a.get("preparation_attempt"):
                            a["preparation_attempt"] = dict(id=uuid.uuid4().hex, state="recognizing", started_at=time.time(),
                                source_sha256=a["sha256"], version=engine.VERSION)
                            standard["preparation_job"]["heartbeat"] = time.time()
                            return copy.deepcopy(a)
                    standard["preparation_job"]["state"] = "completed"
                    return None
                asset = self.mutate(identity, owner, take)
                if asset is None:
                    break
                result, elements, revision, diagnostics = {}, [], None, {}
                try:
                    blob = self.s._text_v2_asset_bytes(asset, owner)
                    image = engine.decode(blob)
                    peers = [a for a in self.s._text_v2_load("assets") if a.get("owner_user_id") == owner
                        and a.get("standard_id") == identity and a["id"] != asset["id"] and a.get("sha256") == asset["sha256"]
                        and a.get("preparation_attempt")]
                    if peers:
                        prior = peers[0]["preparation_attempt"]
                        if prior.get("state") not in {"ready", "review"} or not prior.get("elements"):
                            raise ValueError("same_source_attempt_unknown")
                        elements, result = copy.deepcopy(prior["elements"]), copy.deepcopy(prior["result"])
                        diagnostics = {"reused_attempt": prior["id"]}
                    else:
                        elements = self.observe(image)
                        def pre_call(standard, assets):
                            self.check(standard)
                            a = next(a for a in assets if a["id"] == asset["id"])
                            if a.get("status") != "candidate":
                                raise ValueError("asset_no_longer_retained")
                            a["preparation_attempt"].update(state="classifying", elements=copy.deepcopy(elements), external_started_at=time.time())
                            standard["preparation_job"]["heartbeat"] = time.time()
                        self.mutate(identity, owner, pre_call)
                        preview = prepare_image(engine.overlay(image, elements))
                        provider = self.s.call_ai_mcp_tool("provider.gemini.generate_json", {
                            "provider_config": {**settings, "timeout_seconds": 60}, "system_prompt": engine.PROMPT,
                            "user_content": [{"type": "image_url", "image_url": {"url": self.s._text_v2_data_url(prepare_image(blob), "image/jpeg")}},
                                {"type": "image_url", "image_url": {"url": self.s._text_v2_data_url(preview, "image/jpeg")}},
                                {"type": "text", "text": json.dumps([{k:e[k] for k in ("id", "type", "text", "box", "confidence")} for e in elements], ensure_ascii=False)}], "max_tokens": 6000, "max_attempts": 1})
                        diagnostics = evidence(json.dumps(self.s._text_v2_provider_diagnostics(provider, settings)), settings.get("api_key", ""))
                        if not provider.get("ok"):
                            raise ValueError("provider_result_unknown")
                        result = provider.get("parsed")
                        elements = engine.classify(result, elements)
                    revision = self.store(identity, owner, asset, image, elements)
                    if result.get("kind") != "label_design":
                        revision["reasons"].append("not_single_label_design")
                    if result.get("coverage_complete") is not True:
                        revision["reasons"].append("ocr_coverage_incomplete_requires_review")
                except Exception as exc:
                    diagnostics["failure"] = type(exc).__name__
                    diagnostics["reason_code"] = str(exc)[:160] if isinstance(exc, ValueError) else "processing_failed"
                def finish(standard, assets):
                    a = next(a for a in assets if a["id"] == asset["id"])
                    attempt = a["preparation_attempt"]
                    if attempt["id"] != asset["preparation_attempt"]["id"]:
                        return {"published": False}
                    if attempt.get("state") not in {"recognizing", "classifying"}:
                        attempt["late_result"] = {"diagnostics": diagnostics, "received_at": time.time()}
                        return {"published": False}
                    ready = bool(revision and not revision["reasons"])
                    attempt.update(state="ready" if ready else "review", elements=elements, result=result,
                        diagnostics=diagnostics, finished_at=time.time())
                    if revision:
                        a.setdefault("preparation_revisions", []).append(revision)
                        a["preparation_draft"] = revision["id"]
                    publish = ready and a.get("status") == "candidate" and standard.get("status") != "deleted" and a["sha256"] == asset["sha256"] and standard.get("preparation_job", {}).get("state") == "processing"
                    if publish:
                        a["active_preparation"] = copy.deepcopy(revision)
                        standard.update(status="confirmed", updated_at=int(time.time()))
                    standard["preparation_job"]["heartbeat"] = time.time()
                    return {"published": publish}
                self.mutate(identity, owner, finish, publish=True)
        finally:
            self.s.clear_thread_runtime_repository_selection()
            self.slots.release()

    def view(self, identity, owner):
        def read(standard, assets):
            self.check(standard)
            job = standard.get("preparation_job", {})
            if job.get("state") == "processing" and time.time()-job.get("heartbeat", 0) > 300:
                job.update(state="interrupted", reason="任务中断；已开始的模型请求不会自动重发")
                for a in assets:
                    attempt = a.get("preparation_attempt", {})
                    if attempt.get("state") in {"recognizing", "classifying"}:
                        attempt.update(state="review", diagnostics={"reason_code": "interrupted_no_replay"})
            items = []
            for a in assets:
                if a.get("status") != "candidate":
                    continue
                revisions = copy.deepcopy(a.get("preparation_revisions", []))
                base = f"/api/text-inspection/standards/{identity}/preparation/{a['id']}"
                for rev in revisions:
                    rev["clean_url"], rev["overlay_url"] = base+f"/{rev['id']}/clean", base+f"/{rev['id']}/overlay"
                items.append(dict(id=a["id"], source_sha256=a["sha256"], ordinal=a.get("ordinal"),
                    original_url=f"/api/text-inspection/assets/{a['id']}/content", attempt=a.get("preparation_attempt"),
                    revisions=revisions, draft=a.get("preparation_draft"), active=a.get("active_preparation", {}).get("id")))
            return dict(job=copy.deepcopy(job), items=items)
        return self.mutate(identity, owner, read)

    def edit(self, identity, owner, asset_id, body):
        if not isinstance(body, dict) or not isinstance(body.get("elements"), list):
            raise HTTPException(400, "请提供元素修改")
        def change(standard, assets):
            self.check(standard)
            a = next((a for a in assets if a["id"] == asset_id and a.get("status") == "candidate"), None)
            if not a:
                raise HTTPException(404, "保留图片不存在")
            if body.get("source_sha256") != a["sha256"] or body.get("expected_draft") != a.get("preparation_draft"):
                raise HTTPException(409, "版本已变化，请刷新")
            if a.get("preparation_attempt", {}).get("state") in {"recognizing", "classifying"}:
                raise HTTPException(409, "正在处理，不能覆盖进行中的版本")
            original = a.get("preparation_attempt", {}).get("elements", [])
            values = body["elements"]
            if len(values) != len(original) or {e.get("id") for e in values} != {e["id"] for e in original}:
                raise HTTPException(400, "修改必须包含全部原始元素")
            edited = []
            for initial in original:
                update = next(e for e in values if e.get("id") == initial["id"])
                if update.get("state") not in {"keep", "exclude"} or not isinstance(update.get("text"), str) or not update["text"].strip() or len(update["text"]) > 4000:
                    raise HTTPException(400, "请确认每个元素的归属和文字")
                if update["state"] == "exclude" and not str(update.get("reason", "")).strip():
                    raise HTTPException(400, "排除元素必须填写原因")
                edited.append({**initial, "text": update["text"], "state": update["state"], "reason": str(update.get("reason", "人工确认"))[:1000],
                               "box": engine.box(update.get("box", initial["box"]))})
            image = engine.decode(self.s._text_v2_asset_bytes(a, owner))
            revision = self.store(identity, owner, a, image, edited, crop_box=body.get("crop_box"), human=True)
            if revision["reasons"]:
                raise HTTPException(409, "清理仍不安全："+", ".join(revision["reasons"]))
            a.setdefault("preparation_revisions", []).append(revision)
            a["preparation_draft"] = revision["id"]
            a["active_preparation"] = copy.deepcopy(revision)
            a["preparation_required"] = True
            standard.update(status="confirmed", updated_at=int(time.time()))
            return {"published": True, "revision": revision["id"]}
        return self.mutate(identity, owner, change, publish=True)

    def media(self, identity, owner, asset_id, revision_id, kind):
        a = self.s._text_v2_owned("assets", asset_id, owner)
        if not a or a.get("standard_id") != identity or kind not in {"clean", "overlay"}:
            raise HTTPException(404, "证据不存在")
        revision = next((r for r in a.get("preparation_revisions", []) if r["id"] == revision_id), None)
        if not revision:
            raise HTTPException(404, "版本不存在")
        path = self.s._text_v2_media_path(owner, identity, f"preparation_{revision_id}_{kind}.png")
        return self.s._text_v2_read_verified(str(path), owner, identity, expected_sha256=revision[kind+"_sha256"])


def register(namespace):
    jobs = PreparationJobs(namespace)
    app = namespace["app"]
    def owner():
        namespace["require_permission"]("inspection", detail="没有文字检验权限")
        return namespace["_text_v2_owner"]()[0]

    @app.get("/api/text-inspection/preparation-capabilities")
    def capabilities():
        uid = owner()
        from .standard_preparation_ocr import available
        return {"enabled": enabled(uid), "ocr_available": available(), "scope": "text_and_decoded_codes_only", "graphics_checked": False}

    @app.get("/api/text-inspection/prepared-comparisons/{record_id}")
    def comparison(record_id: str):
        uid = owner()
        record = namespace["_text_v2_owned"]("records", record_id, uid)
        if not record or not record.get("preparation_compare"):
            raise HTTPException(404, "比较记录不存在")
        if record.get("status") == "attempting" and time.time()-record["created_at"] > 120:
            record.update(status="review_required", decision="REVIEW_REQUIRED", message="任务超时或服务重启，请复核；未自动重跑。")
            namespace["_text_v2_save"]("records", record)
        return namespace["_text_v2_public"](record)

    @app.get("/api/text-inspection/prepared-comparisons/{record_id}/media/{kind}")
    def comparison_media(record_id: str, kind: str):
        uid = owner()
        record = namespace["_text_v2_owned"]("records", record_id, uid)
        if not record or not record.get("preparation_compare") or kind != "reference":
            raise HTTPException(404, "比较证据不存在")
        data = namespace["_text_v2_read_verified"](record.get("reference_overlay_path", ""), uid, record["standard_id"], expected_sha256=record.get("reference_overlay_sha256", ""))
        return Response(data, media_type="image/png", headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

    @app.get("/api/text-inspection/standards/{identity}/preparation")
    def status(identity: str):
        return jobs.view(identity, owner())

    @app.post("/api/text-inspection/standards/{identity}/preparation")
    def start(identity: str):
        return jobs.start(identity, owner())

    @app.post("/api/text-inspection/standards/{identity}/preparation/{asset_id}/confirm")
    async def confirm(identity: str, asset_id: str, request: Request):
        uid = owner()
        if not enabled(uid):
            raise HTTPException(409, "该账户未启用标准准备")
        try:
            return jobs.edit(identity, uid, asset_id, await request.json())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/text-inspection/standards/{identity}/preparation/{asset_id}/{revision_id}/{kind}")
    def media(identity: str, asset_id: str, revision_id: str, kind: str):
        data = jobs.media(identity, owner(), asset_id, revision_id, kind)
        return Response(data, media_type="image/png", headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
    return jobs

"""Opt-in document import, append-only claims and immutable crop publication.

Workers are not replayed on process startup. Reads recover durable outcomes, never
submit model calls. Unknown calls require an explicit new per-image attempt.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from types import SimpleNamespace

from fastapi import HTTPException, Request
from fastapi.responses import Response

from . import document_label_crop as crop
from . import document_label_convert as converter
from . import document_label_source as source


def register(namespace):
    class Services:
        def __getattr__(self, key):
            return namespace[key]
    s = Services()
    worker_lock = threading.Semaphore(1)

    async def json_body(request):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 16384:
                raise HTTPException(413, "请求过大")
        try:
            value = json.loads(data)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, UnicodeError) as exc:
            raise HTTPException(400, "需要 JSON 对象") from exc

    def owner():
        s.require_permission("inspection", detail="没有文字检验权限")
        return s._text_v2_owner()[0]

    def enabled(uid):
        return uid in {v.strip() for v in os.environ.get("VANTALINE_DOCUMENT_LABEL_ACCOUNTS", "").split(",") if v.strip()}

    def settings(uid):
        if not enabled(uid) or not s.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED:
            raise HTTPException(503, "文档标签模型或图片外发授权未启用")
        value = s.ai_detection_settings()
        if not value.get("configured") or value.get("provider") != "qwen":
            raise HTTPException(503, "当前账户的已授权视觉模型不可用")
        return {**value, "single_attempt": True}

    def optional(identifier, uid):
        repository = s.runtime_postgres_repository_or_none()
        if repository is None:
            return s._text_v2_owned("document_imports", identifier, uid)
        row = repository.fetch_by_primary_key("text_document_imports", {"id": identifier})
        return row["raw_json"] if row and row["owner_user_id"] == uid else None

    def get(identifier, uid):
        value = optional(identifier, uid)
        if not value:
            raise HTTPException(404, "文档处理记录不存在")
        return value

    def rows(root):
        repository = s.runtime_postgres_repository_or_none()
        if repository is not None:
            return repository.fetch_document_import_rows(root["owner_user_id"], root["root_id"])
        return [v for v in s._text_v2_load("document_imports") if v.get("owner_user_id") == root["owner_user_id"] and v.get("root_id") == root["root_id"]]

    def save(value):
        return s._text_v2_save("document_imports", value, insert_only=True)

    def record(root, identifier, kind, **fields):
        return {"id": identifier, "root_id": root["root_id"], "standard_id": root["standard_id"],
                "owner_user_id": root["owner_user_id"], "created_at": time.time(), "kind": kind, **fields}

    def write(value, kind, data):
        sha = crop.digest(data)
        path = s._text_v2_media_path(value["owner_user_id"], value["root_id"], sha + ".bin")
        s._text_v2_write(path, data)
        value[kind + "_path"], value[kind + "_sha256"] = str(path), sha

    def read(value, kind):
        return s._text_v2_read_verified(value.get(kind + "_path", ""), value["owner_user_id"], value["root_id"], expected_sha256=value.get(kind + "_sha256", ""))

    def public(value):
        result = {k: v for k, v in value.items() if not k.endswith("_path") and k != "owner_user_id"}
        result["media"] = {kind: f"/api/text-inspection/document-imports/{value['root_id']}/records/{value['id']}/media/{kind}"
            for kind in ("original", "normalized", "input", "crop", "crop_input", "document", "converted") if value.get(kind + "_path")}
        return result

    def event(root, stage):
        save(record(root, "die_" + uuid.uuid4().hex, "progress", stage=stage))

    def terminal(root, **fields):
        return save(record(root, root["id"] + "_terminal", "terminal", **fields))

    def stopped(root):
        return optional(root["id"] + "_terminal", root["owner_user_id"]) is not None

    def publish(result):
        if result.get("status") != "candidate":
            return
        uid, standard_id = result["owner_user_id"], result["standard_id"]
        asset_id = "ast_" + crop.digest(result["id"].encode())[:32]
        repository = s.runtime_postgres_repository_or_none()
        if repository is not None:
            existing = repository.fetch_by_primary_key("text_inspection_assets", {"id": asset_id})
            if existing and existing["owner_user_id"] == uid:
                return
        elif s._text_v2_owned("assets", asset_id, uid):
            return
        asset = {"id": asset_id, "standard_id": standard_id, "owner_user_id": uid,
                 "asset_kind": "label_candidate", "ordinal": 0, "status": "candidate", "category": "label",
                 "sha256": result["crop_sha256"], "media_path": "", "mime_type": "image/png",
                 "document_item_id": result["item_id"], "document_result_id": result["id"],
                 "document_crop_version": result["version"],
                 "classification_source": result["approval"], "created_at": int(time.time()), "updated_at": int(time.time())}
        # Existing standard media access is rooted at standard_id, not job_id.
        path = s._text_v2_media_path(uid, standard_id, asset_id + ".png")
        s._text_v2_write(path, read(result, "crop"))
        asset["media_path"] = str(path)
        repository = s.runtime_postgres_repository_or_none()
        if repository is not None:
            repository.add_text_inspection_standard_asset(standard_id, uid, asset,
                revision_id="rev_" + uuid.uuid4().hex, updated_at=asset["updated_at"], replace_document_item=result["item_id"])
        else:
            with s._incoming_text_store_lock:
                if s._text_v2_owned("assets", asset_id, uid):
                    return
                standard = s._text_v2_owned("standards", standard_id, uid)
                existing = [v for v in s._text_v2_load("assets") if v.get("standard_id") == standard_id and v.get("owner_user_id") == uid]
                if any(v.get("document_item_id") == result["item_id"] and v.get("document_crop_version", -1) > result["version"] for v in existing):
                    return
                for old in existing:
                    if old.get("document_item_id") == result["item_id"]:
                        old.update(status="excluded", updated_at=asset["updated_at"])
                        s._text_v2_save("assets", old)
                asset["ordinal"] = max((v["ordinal"] for v in existing), default=0) + 1
                s._text_v2_save("assets", asset, insert_only=True)
                if standard.get("status") == "confirmed":
                    s._text_v2_apply_revision(standard, [*existing, asset], action="add", asset_id=asset_id, now=asset["updated_at"])
                else:
                    standard["asset_count"] = len(s._text_v2_confirmed_snapshot([*existing, asset]))
                s._text_v2_save("standards", standard)

    def latest(item, allrows):
        values = [v for v in allrows if v.get("kind") == "result" and v.get("item_id") == item["id"]]
        return max(values, key=lambda v: v["version"]) if values else None

    def view(root, diagnostics=False):
        values = rows(root)
        for attempt in (v for v in values if v["kind"] == "edit_claim"):
            if time.time() - attempt["created_at"] > 180 and not optional(attempt["result_id"], root["owner_user_id"]):
                save(record(root, attempt["result_id"], "result", item_id=attempt["item_id"], version=attempt["version"],
                    status="needs_confirmation", approval="none", reason="操作结果不明；不会自动重试"))
        values = rows(root)
        end = next((v for v in values if v["id"] == root["id"] + "_terminal"), None)
        progress = [v for v in values if v["kind"] in {"progress", "claim", "root", "result"}]
        last = max(progress, key=lambda v: v["created_at"], default=root)
        if not end and time.time() - last["created_at"] > 180:
            terminal(root, status="interrupted", reason="任务中断或结果不明；不会自动重发外部请求")
            end = optional(root["id"] + "_terminal", root["owner_user_id"])
        items = []
        for item in (v for v in values if v["kind"] == "item"):
            result = latest(item, values)
            # Reconcile only a persisted winner. This cannot make model calls.
            if result:
                publish(result)
            exposed = public(item)
            if not diagnostics:
                exposed["reference_count"] = len(exposed.pop("references", []))
            items.append({**exposed, "result": public(result) if result else None,
                          "status": result["status"] if result else ("needs_confirmation" if end else "pending")})
        counts = {key: sum(v["status"] == key for v in items) for key in ("candidate", "excluded", "needs_confirmation", "pending")}
        return {**public(root), "status": end.get("status") if end else "processing", "stage": "完成" if end else last.get("stage", "提取图片"),
                "reason": end.get("reason", "") if end else "", "counts": counts,
                "items": sorted(items, key=lambda v: v["ordinal"]),
                "diagnostics": [public(v) for v in values if v["kind"] in {"claim", "outcome", "terminal"}] if diagnostics else []}

    def call(root, item, version, stage, images, frozen, explicit=False):
        identifier = f"{item['id']}_v{version}_{stage}"
        if not enabled(root["owner_user_id"]) or not s.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED:
            raise ValueError("文档模型或图片外发授权已关闭")
        if (stopped(root) and not explicit) or optional(f"{item['id']}_v{version}_result", root["owner_user_id"]):
            raise ValueError("import_stopped")
        claim = record(root, identifier, "claim", item_id=item["id"], version=version,
                       stage="定位" if stage == "locate" else "复核", model=frozen["model"],
                       prompt_version=crop.VERSION, input_hashes=[crop.digest(v) for v in images])
        if not save(claim):
            raise ValueError("call_already_claimed")
        value, diagnostic = crop.request_once(images, stage, item["references"], frozen, s.ai_urlopen)
        save(record(root, identifier + "_outcome", "outcome", item_id=item["id"], version=version, diagnostics=diagnostic))
        if value is None:
            raise ValueError("模型调用失败或结果不明，不会自动重试")
        return value

    def process_item(root, item, version, frozen, explicit=False):
        result = record(root, f"{item['id']}_v{version}_result", "result", item_id=item["id"], version=version,
                        status="needs_confirmation", approval="none", reason="", prompt_version=crop.VERSION)
        try:
            if item["review_reason"]:
                raise ValueError(item["review_reason"])
            image = crop.decode(read(item, "original"))
            model_input, mapping = crop.preview(image)
            result["mapping"] = mapping
            located = crop.classify(call(root, item, version, "locate", [model_input], frozen, explicit))
            result.update(located)
            if located["classification"] == "non_label":
                result.update(status="excluded", reason=located["reason"])
            elif located["classification"] == "label_design":
                rectangle = crop.rectangle(located["box"], image.size)
                cropped = image.crop(rectangle)
                write(result, "crop", crop.png(cropped))
                crop_input, _ = crop.preview(cropped)
                write(result, "crop_input", crop_input)
                result["pixel_box"] = list(rectangle)
                verified = call(root, item, version, "verify", [model_input, crop_input], frozen, explicit)
                result["verification"] = verified
                if crop.verified(verified):
                    result.update(status="candidate", approval="model_verified")
                else:
                    result["reason"] = str(verified.get("reason", "裁剪复核不确定"))[:500]
        except ValueError as exc:
            result["reason"] = str(exc)[:500]
        except Exception as exc:
            result["reason"] = "图片处理失败：" + type(exc).__name__
        if stopped(root) and not explicit:
            result.update(status="needs_confirmation", approval="none", reason="任务已中断，迟到结果仅保留证据")
        if save(result):
            publish(result)

    def run(root, contents, frozen):
        try:
            with worker_lock:
                if stopped(root):
                    return
                if root["extension"] == ".doc":
                    event(root, "转换")
                    contents = converter.convert(contents)
                    converted = record(root, root["id"] + "_converted", "conversion")
                    write(converted, "converted", contents)
                    save(converted)
                event(root, "提取图片")
                extracted = source.extract(contents)
                items = []
                for ordinal, extracted_item in enumerate(extracted, 1):
                    blob = extracted_item.pop("blob")
                    item = record(root, root["id"] + "_" + extracted_item["sha256"], "item", ordinal=ordinal, **extracted_item)
                    if blob:
                        write(item, "original", blob)
                        try:
                            image = crop.decode(blob)
                            write(item, "normalized", crop.png(image))
                            preview, _ = crop.preview(image)
                            write(item, "input", preview)
                        except Exception:
                            pass
                    save(item)
                    items.append(item)
                for item in items:
                    if stopped(root):
                        return
                    process_item(root, item, 0, frozen)
                terminal(root, status="completed", reason="")
        except Exception as exc:
            reason = str(exc)[:500] if isinstance(exc, ValueError) else type(exc).__name__
            terminal(root, status="failed", reason=reason)
        finally:
            s.clear_thread_runtime_repository_selection()

    def start(contents, filename, uid, username, name, material, version):
        identity = crop.digest(json.dumps([uid, material, version], ensure_ascii=False).encode())[:32]
        standard_id, root_id = "std_doc_" + identity, "dim_" + identity
        existing = optional(root_id, uid)
        if existing:
            if existing["document_sha256"] != crop.digest(contents):
                raise HTTPException(409, "相同物料和版本已导入不同文件，请使用新版本")
            standard = s._text_v2_owned("standards", standard_id, uid)
            return {**s._text_v2_public(standard), "duplicate": True, "import_job_id": root_id}
        frozen = settings(uid)
        extension = ".docx" if filename.endswith(".docx") else ".doc"
        if extension == ".doc" and not converter.available():
            raise HTTPException(503, "DOC 安全转换组件及字体未通过生产验收，请上传 DOCX")
        root = {"id": root_id, "root_id": root_id, "standard_id": standard_id,
                "owner_user_id": uid, "created_at": time.time(), "kind": "root", "extension": extension,
                "prompt_version": crop.VERSION, "model": frozen["model"], "document_sha256": crop.digest(contents), "stage": "排队"}
        write(root, "document", contents)
        now = int(time.time())
        source_path = s._text_v2_media_path(uid, standard_id, "source" + extension)
        # Preserve original DOC for the standard; converted evidence belongs to job.
        standard = {"id": standard_id, "owner_user_id": uid, "owner_username": username, "name": name,
                    "material_code": material, "version_label": version, "standard_type": "label", "status": "draft",
                    "source_sha256": crop.digest(contents), "source_path": str(source_path), "created_at": now,
                    "updated_at": now, "asset_count": 0, "import_job_id": root_id}
        if not s._text_v2_save("standards", standard, insert_only=True):
            existing_standard = s._text_v2_owned("standards", standard_id, uid)
            if not existing_standard or existing_standard.get("source_sha256") != standard["source_sha256"]:
                raise HTTPException(409, "相同物料/版本已存在标准")
            # A response-loss or crashed initial import must not replay work.
            return {**s._text_v2_public(existing_standard), "duplicate": True}
        s._text_v2_write(source_path, contents)
        if save(root):
            threading.Thread(target=run, args=(root, contents, frozen), daemon=True).start()
        return {**s._text_v2_public(standard), "import_job_id": root_id}

    @s.app.get("/api/text-inspection/document-import-capabilities")
    def capabilities():
        uid = owner()
        try:
            settings(uid)
            reason, available = "", True
        except HTTPException as exc:
            reason, available = str(exc.detail), False
        return {"enabled": enabled(uid), "available": available, "doc_available": converter.available(), "reason": reason}

    @s.app.get("/api/text-inspection/document-imports/{job_id}")
    def query(job_id: str, diagnostics: bool = False):
        uid = owner()
        root = optional(job_id, uid)
        if not root:
            # A crash between standard reservation and root insertion is visible
            # and non-replayable, not an endless 404 or an implicit fresh import.
            standard = next((v for v in s._text_v2_load("standards") if v.get("owner_user_id") == uid and v.get("import_job_id") == job_id), None)
            if not standard:
                raise HTTPException(404, "任务不存在")
            root = {"id": job_id, "root_id": job_id, "standard_id": standard["id"], "owner_user_id": uid,
                    "kind": "root", "created_at": standard["created_at"], "stage": "初始化中断"}
            save(root)
            terminal(root, status="interrupted", reason="导入初始化中断，未自动重新调用模型；请保留此记录并用新版本重新导入")
            root = get(job_id, uid)
        if root["kind"] != "root":
            raise HTTPException(404, "任务不存在")
        return view(root, diagnostics)

    @s.app.get("/api/text-inspection/document-imports/{job_id}/records/{record_id}/media/{kind}")
    def media(job_id: str, record_id: str, kind: str):
        uid = owner()
        value = get(record_id, uid)
        if value["root_id"] != job_id or kind not in {"original", "normalized", "input", "crop", "crop_input", "document", "converted"} or not value.get(kind + "_path"):
            raise HTTPException(404, "资源不存在")
        mime = "image/jpeg" if kind in {"input", "crop_input"} else "image/png" if kind in {"normalized", "crop"} else "application/octet-stream"
        headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
        if mime == "application/octet-stream":
            headers["Content-Disposition"] = 'attachment; filename="source.bin"'
        return Response(read(value, kind), media_type=mime, headers=headers)

    @s.app.post("/api/text-inspection/document-imports/{job_id}/items/{item_id}/review")
    async def review(job_id: str, item_id: str, request: Request):
        uid = owner()
        root, item = get(job_id, uid), get(item_id, uid)
        if item.get("kind") != "item" or item["root_id"] != job_id:
            raise HTTPException(404, "图片不存在")
        if not stopped(root):
            raise HTTPException(409, "请等待文档处理结束后确认")
        body = await json_body(request)
        previous = latest(item, rows(root))
        version = previous["version"] if previous else -1
        if type(body.get("version")) is not int or body["version"] != version:
            raise HTTPException(409, "结果已变更，请刷新")
        action = body.get("action")
        if action not in {"confirm", "exclude"}:
            raise HTTPException(400, "需要确认或排除")
        result = record(root, f"{item_id}_v{version + 1}_result", "result", item_id=item_id,
                        version=version + 1, status="excluded", approval="human", reason="人工排除")
        if action == "confirm":
            if item.get("review_reason"):
                raise HTTPException(409, "该对象无法保证文字完整，请提供完整渲染图后通过已有添加图片功能导入")
            try:
                image = crop.decode(read(item, "original"))
                box = body.get("box")
                pixels = crop.rectangle(box, image.size)
                write(result, "crop", crop.png(image.crop(pixels)))
                result.update(box=box, pixel_box=list(pixels), status="candidate", reason="人工确认裁剪")
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        # Excluding a previously published crop uses the existing membership API;
        # do not create a contradictory review record without a revision.
        if action == "exclude" and previous and previous["status"] == "candidate":
            raise HTTPException(409, "已接纳图片请在订单候选列表中停用；历史裁剪证据保留")
        if not save(record(root, result["id"] + "_claim", "edit_claim", result_id=result["id"], item_id=item_id,
                           version=version + 1, action="human_" + action)):
            raise HTTPException(409, "已有操作进行中，请刷新")
        if not save(result):
            raise HTTPException(409, "并发修改冲突，请刷新")
        publish(result)
        return public(result)

    @s.app.post("/api/text-inspection/document-imports/{job_id}/items/{item_id}/retry")
    async def retry(job_id: str, item_id: str, request: Request):
        uid = owner()
        root, item = get(job_id, uid), get(item_id, uid)
        if item.get("kind") != "item" or item["root_id"] != job_id:
            raise HTTPException(404, "图片不存在")
        if not stopped(root):
            raise HTTPException(409, "请等待文档处理结束")
        body = await json_body(request)
        previous = latest(item, rows(root))
        version = previous["version"] if previous else -1
        request_id = body.get("request_id")
        if type(body.get("version")) is not int:
            raise HTTPException(400, "需要整数版本")
        if not isinstance(request_id, str) or not 8 <= len(request_id) <= 100:
            raise HTTPException(400, "需要有效重试请求 ID")
        fingerprint = crop.digest(json.dumps([uid, item_id, request_id]).encode())
        old = next((v for v in rows(root) if v.get("request_fingerprint") == fingerprint), None)
        if old:
            if old["version"] != body.get("version", -2) + 1:
                raise HTTPException(409, "重试请求 ID 对应输入冲突")
            return public(old)
        if type(body.get("version")) is not int or body["version"] != version:
            raise HTTPException(409, "结果已变更，请刷新")
        if previous and previous["status"] == "candidate":
            raise HTTPException(409, "已接纳裁剪请人工调整，不重复付费调用")
        if item["review_reason"]:
            raise HTTPException(409, "该对象需要完整渲染或安全解码，不可模型重试")
        frozen = settings(uid)
        result_id = f"{item_id}_v{version + 1}_result"
        claim = record(root, result_id + "_claim", "edit_claim", result_id=result_id, item_id=item_id,
                       version=version + 1, request_fingerprint=fingerprint, action="explicit_retry")
        if not save(claim):
            raise HTTPException(409, "已有操作进行中")
        def run_retry():
            try:
                with worker_lock:
                    if time.time() - claim["created_at"] <= 180 and not optional(result_id, uid):
                        process_item(root, item, version + 1, frozen, explicit=True)
            finally:
                s.clear_thread_runtime_repository_selection()
        threading.Thread(target=run_retry, daemon=True).start()
        return public(claim)

    def processing(job_id, uid):
        root = optional(job_id, uid)
        return not root or view(root)["status"] == "processing"

    return SimpleNamespace(start=start, enabled=enabled, view=view, process_item=process_item, processing=processing)

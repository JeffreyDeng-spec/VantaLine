"""Account-scoped, at-most-once label extraction and immutable edit revisions."""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from fastapi import File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from . import label_extraction as geometry


def register(namespace):
    class Services:
        def __getattr__(self, name):
            return namespace[name]
    s = Services()

    def owner():
        s.require_permission("inspection", detail="没有文字检验权限")
        return s._text_v2_owner()[0]

    def optional(identifier, uid):
        repository = s.runtime_postgres_repository_or_none()
        if repository is None:
            return s._text_v2_owned("extractions", identifier, uid)
        row = repository.fetch_by_primary_key("text_label_extractions", {"id":identifier})
        return row["raw_json"] if row and row["owner_user_id"] == uid else None

    def rows(uid, root=None):
        repository = s.runtime_postgres_repository_or_none()
        if repository is not None:
            return repository.fetch_label_extraction_rows(uid,root)
        return [v for v in s._text_v2_load("extractions") if v.get("owner_user_id") == uid and (root is None or v.get("root_id") == root)]

    def get(identifier, uid):
        value = optional(identifier,uid)
        if not value:
            raise HTTPException(404, "标签提取不存在")
        return value

    def save(value, once=False):
        return s._text_v2_save("extractions", value, insert_only=once)

    def latest(root, uid):
        revisions = [v for v in rows(uid,root) if v.get("kind") == "revision"]
        return max(revisions, key=lambda v: v["version"]) if revisions else get(root, uid)

    def read(value, kind):
        return s._text_v2_read_verified(value.get(kind+"_path", ""), value["owner_user_id"], value["root_id"], expected_sha256=value.get(kind+"_sha256", ""), max_bytes=100*1024*1024)

    def write(value, kind, data):
        path = s._text_v2_media_path(value["owner_user_id"],value["root_id"],value["id"]+"-"+s.sha256_bytes(data)[:24]+"-"+kind+".png")
        s._text_v2_write(path,data)
        value[kind+"_path"],value[kind+"_sha256"] = str(path),s.sha256_bytes(data)

    def public(value):
        result = {k:v for k,v in value.items() if not k.endswith("_path") and k != "owner_user_id"}
        result["media"] = {kind:f"/api/text-inspection/extractions/{value['id']}/media/{kind}" for kind in ("source","mask","crop") if value.get(kind+"_path")}
        if result["status"] == "attempting" and time.time() > value["deadline_at"]:
            result["status"] = "uncertain"
            result["error_code"] = "provider_outcome_unknown"
        if result["status"] == "expired":
            result["error_code"] = "draft_expired"
            result["media"] = {}
        return result

    def run(value, settings, original):
        started = time.monotonic()
        diagnostic = value["diagnostics"]
        stage = "prepare"
        try:
            data,meta,prompt = geometry.prepare(original,value["target"])
            diagnostic["geometry"] = meta
            diagnostic["prompt_version"] = geometry.PROMPT_VERSION
            stage = "provider"
            provider = s.image_generation_provider_from_settings(settings)
            response = provider.generate_image(prompt,[{"type":"image_url","image_url":{"url":s._text_v2_data_url(data,"image/png")}}],model=settings["model"])
            diagnostic["provider_result"] = s._text_v2_diagnostic_value({k:response.get(k) for k in ("text","usage_metadata","latency_ms","model")})
            stage = "mask_validation"
            geometry.decode(response["bytes"])
            write(value,"mask",response["bytes"])
            points,metrics = geometry.parse_mask(response["bytes"],original,meta)
            diagnostic["mask_metrics"] = metrics
            value["polygon"] = points
            stage = "crop"
            cropped,quality = geometry.crop(original,points)
            write(value,"crop",cropped)
            diagnostic["quality"] = quality
            value["status"] = "needs_adjustment" if metrics["requires_manual_adjustment"] else "ready"
            if metrics["requires_manual_adjustment"]:
                value["error_code"] = "weak_edge_support"
        except Exception as exc:
            value["status"] = "uncertain" if stage == "provider" else "needs_adjustment"
            # Exception messages may contain upstream URLs or credentials.
            value["error_code"] = str(exc)[:100] if stage != "provider" and isinstance(exc,ValueError) else type(exc).__name__
            diagnostic["failure"] = {"stage":stage,"type":type(exc).__name__,"code":value["error_code"]}
        diagnostic["elapsed_ms"] = round((time.monotonic()-started)*1000)
        value["finished_at"] = int(time.time())
        try:
            save(value)
            print(json.dumps({"event":"label_extraction","id":value["id"],"status":value["status"],"elapsed_ms":diagnostic["elapsed_ms"],"error_code":value.get("error_code","")}),flush=True)
        finally:
            s.clear_thread_runtime_repository_selection()

    def expire_drafts(uid):
        account_rows = rows(uid)
        pinned = {v["root_id"] for v in account_rows if v.get("status") == "confirmed"}
        pinned.update(v.get("diagnostics",{}).get("extraction",{}).get("root_id") for v in s._text_v2_load("records") if v.get("owner_user_id") == uid)
        for root in account_rows:
            if root.get("kind") != "task" or root["root_id"] in pinned or root["created_at"] > time.time()-7*86400:
                continue
            current = latest(root["id"],uid)
            if current["status"] != "expired":
                tombstone = {**current,"id":root["id"]+"_v"+str(current["version"]+1),"kind":"revision","version":current["version"]+1,"status":"expired","created_at":int(time.time())}
                # Competes for the same immutable version as an edit/confirmation.
                if not save(tombstone,True):
                    continue
            directory = s._text_v2_media_path(uid,root["id"],"sentinel.png").parent
            if directory.is_dir() and not directory.is_symlink():
                for path in directory.iterdir():
                    if path.is_file() and not path.is_symlink() and path.suffix == ".png":
                        path.unlink()

    @s.app.get("/api/text-inspection/extraction-capabilities")
    def capabilities():
        uid = owner()
        expire_drafts(uid)
        allowed = {v.strip() for v in os.environ.get("VANTALINE_LABEL_EXTRACTION_ACCOUNTS", "").split(",") if v.strip()}
        settings = s.image_generation_settings()
        return {"enabled":uid in allowed, "ai_available":uid in allowed and s.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED and bool(settings.get("configured")), "provider":settings.get("provider"), "model":settings.get("model")}

    @s.app.post("/api/text-inspection/extractions")
    async def create(file: UploadFile = File(...), target: str = Form(...), request_id: str = Form(...), method: str = Form("ai")):
        uid = owner()
        if not capabilities()["enabled"]:
            raise HTTPException(403,"当前账户尚未启用单标签提取")
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}",request_id) or method not in {"ai","manual"}:
            raise HTTPException(400,"提取请求无效")
        data = await file.read(10*1024*1024+1)
        try:
            target_box = geometry.box(json.loads(target))
            normalized = geometry.normalized_image(data)
        except Exception as exc:
            raise HTTPException(400,"图片或目标框无效："+str(exc)[:120]) from exc
        settings = {**s.image_generation_settings(),"single_attempt":True}
        fingerprint = s.sha256_bytes(json.dumps([s.sha256_bytes(data),target_box,method,geometry.PROMPT_VERSION],sort_keys=True).encode())
        identifier = "ext_"+hashlib.sha256((uid+":"+request_id).encode()).hexdigest()[:40]
        existing = optional(identifier,uid)
        if existing:
            if existing["fingerprint"] != fingerprint:
                raise HTTPException(409,"请求 ID 已用于另一张图片或目标框")
            current = latest(identifier,uid)
            if current["status"] == "expired":
                raise HTTPException(410,"未使用的提取草稿已过期，请重新拍照")
            return public(current)
        now = int(time.time())
        value = {"id":identifier,"root_id":identifier,"kind":"task","owner_user_id":uid,"created_at":now,"version":0,"fingerprint":fingerprint,"target":target_box,"status":"attempting","deadline_at":now+2*int(settings.get("timeout_seconds",300))+120,"source_upload_sha256":s.sha256_bytes(data),"diagnostics":{"provider":settings.get("provider"),"model":settings.get("model"),"max_attempts":1,"method":method}}
        # Save source first, then atomically claim. Concurrent losers write identical bytes.
        write(value,"source",normalized)
        if method == "manual" or not s.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED or not settings.get("configured"):
            value["status"] = "needs_adjustment"
            value["error_code"] = "manual_selection" if method == "manual" else "segmentation_not_configured"
        if not save(value,True):
            winner = get(identifier,uid)
            if winner["fingerprint"] != fingerprint:
                raise HTTPException(409,"提取请求冲突")
            return public(latest(identifier,uid))
        if value["status"] == "attempting":
            threading.Thread(target=run,args=(value,settings,normalized),daemon=True,name="label-extraction").start()
        return public(value)

    @s.app.get("/api/text-inspection/extractions/{identifier}")
    def status(identifier: str):
        uid = owner()
        value = get(identifier,uid)
        return public(latest(value["root_id"],uid))

    @s.app.get("/api/text-inspection/extractions/{identifier}/media/{kind}")
    def media(identifier: str, kind: str):
        value = get(identifier,owner())
        if kind not in {"source","mask","crop"} or not value.get(kind+"_path"):
            raise HTTPException(404,"提取图片不存在")
        data = read(value,kind)
        return Response(data,media_type="image/png" if data.startswith(b"\x89PNG") else "image/jpeg",headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

    @s.app.post("/api/text-inspection/extractions/{identifier}/revise")
    async def revise(identifier: str, request: Request):
        uid = owner()
        parent = get(identifier,uid)
        current = latest(parent["root_id"],uid)
        body = await request.json()
        if not isinstance(body,dict) or type(body.get("version")) is not int or body["version"] != current["version"]:
            raise HTTPException(409,"提取版本已改变，请刷新预览")
        if current["status"] == "expired":
            raise HTTPException(410,"提取草稿已过期，请重新拍照")
        if current["status"] == "attempting":
            raise HTTPException(409,"提取尚未结束，请等待或使用新的手动提取请求")
        confirmation = body.get("confirm") is True
        try:
            points = geometry.polygon(body.get("polygon"))
            root = get(parent["root_id"],uid)
            cropped,quality = geometry.crop(read(root,"source"),points)
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc
        if confirmation and (current["status"] not in {"ready","confirmed"} or current.get("polygon") != points):
            raise HTTPException(409,"请先保存轮廓并检查预览，再确认标签")
        revision = {**current,"id":parent["root_id"]+"_v"+str(current["version"]+1),"kind":"revision","version":current["version"]+1,"created_at":int(time.time()),"status":"confirmed" if confirmation else "ready","polygon":points,"error_code":"","diagnostics":{**current["diagnostics"],"quality":quality,"manually_adjusted":not confirmation or current["diagnostics"].get("manually_adjusted",False)}}
        if confirmation:
            asset = s._text_v2_owned("assets",str(body.get("standard_asset_id", "")),uid)
            standard = s._text_v2_owned("standards",asset["standard_id"],uid) if asset else None
            if not standard or standard.get("status") != "confirmed" or not any(v["id"] == asset["id"] for v in standard.get("confirmed_assets",[])):
                raise HTTPException(409,"标准已改变，请重新选择")
            revision["standard_asset_id"] = asset["id"]
            revision["standard_revision_id"] = standard.get("current_revision_id","")
        else:
            revision.pop("standard_asset_id",None)
            revision.pop("standard_revision_id",None)
        # Unique filenames avoid a losing concurrent edit overwriting the winner's pixels.
        path = s._text_v2_media_path(uid,parent["root_id"],uuid.uuid4().hex+"-crop.png")
        s._text_v2_write(path,cropped)
        revision["crop_path"],revision["crop_sha256"] = str(path),s.sha256_bytes(cropped)
        if not save(revision,True):
            path.unlink(missing_ok=True)
            winner = latest(parent["root_id"],uid)
            if winner.get("polygon") == points and winner.get("status") == revision["status"] and winner.get("standard_asset_id") == revision.get("standard_asset_id") and winner.get("standard_revision_id") == revision.get("standard_revision_id"):
                return public(winner)
            raise HTTPException(409,"轮廓被另一页面修改，请刷新")
        return public(revision)

    def resolve(identifier, uid, asset_id, standard):
        value = get(identifier,uid)
        if value["status"] != "confirmed" or value.get("standard_asset_id") != asset_id or value.get("standard_revision_id","") != standard.get("current_revision_id",""):
            raise HTTPException(409,"请重新确认提取标签和当前标准")
        if latest(value["root_id"],uid)["id"] != identifier:
            raise HTTPException(409,"提取轮廓已修改，请重新确认")
        return read(value,"crop"), public(value)

    return resolve

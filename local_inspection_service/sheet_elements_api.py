"""Account-owned append-only templates, jobs and media for whole-sheet inspection."""
from __future__ import annotations

import copy
import json
import os
import re
import threading
import time
import uuid

from fastapi import File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from . import label_extraction as images
from . import sheet_elements as engine
from . import sheet_elements_vlm as advisory

DEADLINE_SECONDS = 120
_inference_slot = threading.BoundedSemaphore(1)


def register(namespace):
    class Services:
        def __getattr__(self, name):
            return namespace[name]
    s = Services()

    def owner():
        s.require_permission("inspection", detail="没有文字检验权限")
        return s._text_v2_owner()[0]

    def allowed(uid, variable="VANTALINE_SHEET_ELEMENTS_ACCOUNTS"):
        return uid in {v.strip() for v in os.environ.get(variable, "").split(",") if v.strip()}

    def rows(uid, root=None):
        repository = s.runtime_postgres_repository_or_none()
        if repository is not None:
            return repository.fetch_sheet_element_rows(uid, root)
        return [v for v in s._text_v2_load("sheet_elements") if v["owner_user_id"] == uid
                and (root is None or v["root_id"] == root)]

    def optional(identifier, uid):
        repository = s.runtime_postgres_repository_or_none()
        if repository is not None:
            row = repository.fetch_by_primary_key("text_sheet_elements", {"id": identifier})
            return row["raw_json"] if row and row["owner_user_id"] == uid else None
        return s._text_v2_owned("sheet_elements", identifier, uid)

    def get(identifier, uid):
        value = optional(identifier, uid)
        if not value:
            raise HTTPException(404, "整页核对资源不存在")
        return value

    def save(value):
        return s._text_v2_save("sheet_elements", value, insert_only=True)

    def root_of(value):
        return get(value["root_id"], value["owner_user_id"])

    def terminal(root, **updates):
        value = {**root, **updates, "id": root["id"]+"_terminal", "kind": "terminal",
                 "created_at": time.time(), "finished_at": time.time()}
        save(value)  # Worker and timeout race for ONE immutable outcome.
        return get(value["id"], root["owner_user_id"])

    def expire(root):
        if time.time() >= root["deadline_at"] and not optional(root["id"]+"_terminal", root["owner_user_id"]):
            terminal(root, status="review", error_code="deadline_or_restart_outcome_unknown",
                     result={"decision": "REVIEW_REQUIRED", "elements": []})
            from .sheet_elements_runtime import cancel_task
            cancel_task(root["id"])

    def latest(root):
        expire(root)
        items = rows(root["owner_user_id"], root["id"])
        revisions = [v for v in items if v["kind"] == "revision"]
        if revisions:
            return max(revisions, key=lambda v: v["version"])
        final = next((v for v in items if v["kind"] == "terminal"), None)
        if final:
            return final
        events = sorted((v for v in items if v["kind"] == "event"), key=lambda v: v["created_at"])
        return {**root, **({"status": events[-1]["status"], "progress": events[-1].get("progress")} if events else {})}

    def write(value, kind, data):
        sha = s.sha256_bytes(data)
        path = s._text_v2_media_path(value["owner_user_id"], value["root_id"], sha+"-"+kind+".bin")
        s._text_v2_write(path, data)
        value[kind+"_path"], value[kind+"_sha256"] = str(path), sha

    def read(value, kind):
        return s._text_v2_read_verified(value.get(kind+"_path", ""), value["owner_user_id"],
                                        value["root_id"], expected_sha256=value.get(kind+"_sha256", ""))

    def public(value):
        result = {k: v for k, v in value.items() if not k.endswith("_path") and k not in {"owner_user_id", "settings"}}
        result["media"] = {kind: f"/api/text-inspection/sheet/resources/{value['id']}/media/{kind}"
                           for kind in ("source", "original", "reference", "standard_overlay", "actual_overlay", *("advisory_"+str(i) for i in range(6)))
                           if value.get(kind+"_path")}
        return result

    def selected(asset_id, uid):
        asset = s._text_v2_owned("assets", asset_id, uid)
        standard = s._text_v2_owned("standards", asset["standard_id"], uid) if asset else None
        if not asset or not standard:
            raise HTTPException(404, "标准不存在")
        if standard.get("status") != "confirmed" or not any(v["id"] == asset_id for v in standard.get("confirmed_assets", [])):
            raise HTTPException(409, "请选择当前已确认且启用的标准")
        return asset, standard

    def binding(asset, standard):
        return {"standard_asset_id": asset["id"], "standard_id": standard["id"],
                "standard_revision_id": standard.get("current_revision_id", ""), "reference_asset_sha256": asset["sha256"]}

    def validate_binding(value, uid):
        asset, standard = selected(value["standard_asset_id"], uid)
        if any(value.get(k) != v for k, v in binding(asset, standard).items()):
            raise HTTPException(409, "标准版本已改变，请重新建立并确认元素模板")

    def event(root, status, progress=None):
        if time.time() >= root["deadline_at"] or optional(root["id"]+"_terminal", root["owner_user_id"]):
            raise TimeoutError("sheet_deadline_exceeded")
        save({"id": root["id"]+"_event_"+uuid.uuid4().hex, "root_id": root["id"], "kind": "event",
              "owner_user_id": root["owner_user_id"], "created_at": time.time(), "status": status, "progress": progress})

    def ocr(image):
        # Injectable for endpoint fixtures. Real execution checks local artifacts
        # before Paddle can download anything; other workflows are unaffected.
        from .sheet_elements_runtime import observations
        return observations(image)

    namespace["sheet_elements_ocr"] = ocr

    def advisory_settings(uid):
        if not allowed(uid,"VANTALINE_SHEET_ELEMENTS_VLM_ACCOUNTS") or not s.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED:
            return None
        settings = s.ai_detection_settings()
        return {**settings,"single_attempt":True} if settings.get("configured") and settings.get("provider") == "qwen" else None

    def run(root, settings=None):
        acquired = False
        diagnostic = {"version": engine.VERSION, "external_attempts": 0}
        diagnostic["ocr_profile"] = root.get("ocr_profile","medium")
        timer = None
        try:
            timer = threading.Timer(max(0, root["deadline_at"]-time.time()), timeout, args=(root,))
            timer.daemon = True
            timer.start()
            acquired = _inference_slot.acquire(timeout=max(0, root["deadline_at"]-time.time()))
            if not acquired:
                raise TimeoutError("queue_timeout")
            from .sheet_elements_runtime import begin_task
            begin_task(root["id"],root["deadline_at"])
            event(root, "recognizing")
            source = images.decode(read(root, "source"))
            observations, metrics = engine.observe(source, s.sheet_elements_ocr, root["deadline_at"],
                                                   lambda state, progress: event(root, state, progress))
            diagnostic.update(metrics, observations_raw=observations)
            from .sheet_elements_runtime import metadata as ocr_metadata
            diagnostic["ocr_artifacts"] = ocr_metadata()
            event(root, "matching")
            proposals = []
            diagnostic["vlm"] = {"status":"not_called","reason":"unavailable_or_no_doubtful_regions"}
            if settings and time.time()+5 < root["deadline_at"]:
                inputs, regions, instruction = advisory.prepare(source, root.get("elements",[]), observations, root["task_type"])
                if inputs:
                    event(root,"reviewing",{"provider":"qwen","regions":len(inputs)})
                    provider_claim = {"id":root["id"]+"_vlm_claim","root_id":root["id"],"kind":"provider_claim",
                                      "owner_user_id":root["owner_user_id"],"created_at":time.time(),"model":settings["model"],
                                      "regions":regions,"input_sha256":[s.sha256_bytes(data) for data in inputs],"version":advisory.VERSION}
                    for index,data in enumerate(inputs):write(provider_claim,"advisory_"+str(index),data)
                    if save(provider_claim):
                        diagnostic["external_attempts"] = 1
                        diagnostic["vlm"] = {"status":"attempting","model":settings["model"],"regions":regions,"media":public(provider_claim)["media"]}
                        began=time.monotonic()
                        try:
                            parsed, provider_diagnostic=advisory.request_once(inputs,instruction,settings,s.ai_urlopen,root["deadline_at"])
                            diagnostic["vlm"].update(provider_diagnostic,status="returned")
                            if root["task_type"] == "template":
                                proposals=advisory.template_suggestions(parsed)
                            else:
                                observations=engine.deduplicate(observations+advisory.verify_regions(parsed,regions,source,s.sheet_elements_ocr,root["deadline_at"]))
                                diagnostic["observations_raw"]=observations
                        except Exception as exc:
                            diagnostic["vlm"].update(status="uncertain",failure_type=type(exc).__name__)
                        diagnostic["vlm"]["elapsed_ms"]=round((time.monotonic()-began)*1000)
                        save({**provider_claim,"id":root["id"]+"_vlm_outcome","kind":"provider_outcome","created_at":time.time(),
                              "diagnostics":s._text_v2_diagnostic_value(diagnostic["vlm"])})
            if root["task_type"] == "template":
                elements = engine.draft_elements(observations)
                # VLM inventory supplements OCR, never silently replaces it.
                for proposal in proposals:
                    if not any(proposal["type"]==value["type"] and proposal["expected"]==value["expected"] and
                               engine.overlap_ratio(proposal["box"],value["box"])>.7 for value in elements):
                        elements.append(proposal)
                elements=elements[:200]
                diagnostic["graphic_discovery"] = "manual_inventory_required"
                terminal(root, status="draft", elements=elements, diagnostics=diagnostic)
            else:
                result = engine.compare(root["elements"], observations, images.decode(read(root,"reference")),
                                        source, root["deadline_at"], graphic_verified=allowed(root["owner_user_id"],"VANTALINE_SHEET_ELEMENTS_GRAPHIC_VERIFIED_ACCOUNTS"))
                # All graphical matches remain uncommissioned. No external
                # suggestion can manufacture a local MATCH.
                event(root, "reviewing")
                output = copy.deepcopy(root)
                write(output, "standard_overlay", engine.annotate(images.decode(read(root,"reference")), result))
                write(output, "actual_overlay", engine.annotate(source, result, False))
                result["candidate_decision"] = result["decision"]
                try:
                    validate_binding(root,root["owner_user_id"])
                    template=get(root["template_id"],root["owner_user_id"])
                    if latest(root_of(template))["id"] != template["id"]:
                        raise HTTPException(409,"template_changed")
                except HTTPException:
                    result["decision"]="REVIEW_REQUIRED"
                    result["gate_reason"]="standard_or_template_changed"
                if result["decision"] == "MATCH" and not allowed(root["owner_user_id"], "VANTALINE_SHEET_ELEMENTS_VERIFIED_ACCOUNTS"):
                    result["decision"] = "REVIEW_REQUIRED"
                    result["gate_reason"] = "commissioning_not_complete"
                diagnostic["elapsed_ms"] = round((time.time()-root["created_at"])*1000)
                if time.time() >= root["deadline_at"]:
                    raise TimeoutError("sheet_deadline_exceeded")
                terminal(output, status="completed", result=result, diagnostics=diagnostic)
        except Exception as exc:
            if isinstance(exc,engine.ObservationTimeout):
                diagnostic.update(observations_raw=exc.observations,tiles=exc.stages,incomplete=True)
            diagnostic["failure"] = {"type": type(exc).__name__}
            diagnostic["elapsed_ms"] = round((time.time()-root["created_at"])*1000)
            # Never persist exception strings: providers/native libraries may
            # include credentials or arbitrary source data in their messages.
            terminal(root, status="review", error_code=type(exc).__name__, diagnostics=diagnostic,
                     result={"decision": "REVIEW_REQUIRED", "elements": []})
            # A timer may already own the immutable terminal. Append late safe
            # diagnostics separately, never overwrite that terminal outcome.
            save({"id":root["id"]+"_late_diagnostics","root_id":root["id"],"kind":"diagnostics",
                  "owner_user_id":root["owner_user_id"],"created_at":time.time(),"diagnostics":diagnostic})
        finally:
            if timer: timer.cancel()
            if acquired: _inference_slot.release()
            s.clear_thread_runtime_repository_selection()

    def timeout(root):
        try:
            expire(root)
        finally:
            s.clear_thread_runtime_repository_selection()

    def request_id(value):
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", value):
            raise HTTPException(400, "请求 ID 无效")

    def claim(root):
        existing = optional(root["id"], root["owner_user_id"])
        if existing:
            if existing["fingerprint"] != root["fingerprint"]:
                raise HTTPException(409, "请求 ID 已用于不同输入")
            return public(latest(existing))
        # Limit admitted work independently of the single native inference slot.
        pending = [v for v in rows(root["owner_user_id"]) if v["kind"] == "root" and v["deadline_at"] > time.time()
                   and not optional(v["id"]+"_terminal", root["owner_user_id"])]
        if len(pending) >= 4:
            raise HTTPException(429, "已有多个任务排队，请等待")
        if not save(root):
            winner = get(root["id"], root["owner_user_id"])
            if winner["fingerprint"] != root["fingerprint"]:
                raise HTTPException(409, "请求冲突")
            return public(latest(winner))
        settings=advisory_settings(root["owner_user_id"])
        threading.Thread(target=run, args=(copy.deepcopy(root),settings), daemon=True, name="sheet-elements").start()
        return public(root)

    def new_root(uid, identifier, task_type, fingerprint):
        return {"id": identifier, "root_id": identifier, "kind": "root", "owner_user_id": uid,
                "task_type": task_type, "fingerprint": fingerprint, "created_at": time.time(),
                "deadline_at": time.time()+DEADLINE_SECONDS, "version": 0, "status": "queued",
                "ocr_profile":os.environ.get("VANTALINE_SHEET_OCR_PROFILE","medium")}

    def enabled_owner():
        uid = owner()
        if not allowed(uid):
            raise HTTPException(403, "当前账户尚未启用整页元素核对")
        return uid

    async def json_body(request):
        data=bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>512*1024:raise HTTPException(413,"模板请求过大")
        try:
            body=json.loads(data)
        except (ValueError,UnicodeError):
            raise HTTPException(400,"请求 JSON 无效") from None
        if not isinstance(body,dict):raise HTTPException(400,"请求格式无效")
        return body

    @s.app.get("/api/text-inspection/sheet/capabilities")
    def capabilities():
        uid = owner()
        return {"enabled": allowed(uid), "verified": allowed(uid,"VANTALINE_SHEET_ELEMENTS_VERIFIED_ACCOUNTS"),
                "version": engine.VERSION, "deadline_seconds": DEADLINE_SECONDS,
                "graphic_verified": allowed(uid,"VANTALINE_SHEET_ELEMENTS_GRAPHIC_VERIFIED_ACCOUNTS"), "vlm_available": advisory_settings(uid) is not None}

    @s.app.get("/api/text-inspection/sheet/templates")
    def templates(standard_asset_id: str):
        uid = owner()
        selected(standard_asset_id,uid)
        roots = [v for v in rows(uid) if v["kind"] == "root" and v["task_type"] == "template" and v["standard_asset_id"] == standard_asset_id]
        return {"items": [public(latest(v)) for v in sorted(roots,key=lambda v:-v["created_at"])]}

    @s.app.post("/api/text-inspection/sheet/templates")
    async def create_template(request: Request):
        uid = enabled_owner()
        body = await json_body(request)
        if not isinstance(body, dict): raise HTTPException(400,"请求格式无效")
        rid = str(body.get("request_id", "")); request_id(rid)
        asset, standard = selected(str(body.get("standard_asset_id", "")), uid)
        identity = binding(asset,standard)
        identifier = "set_"+engine.digest([uid,rid])[:40]
        root = {**new_root(uid,identifier,"template",engine.digest([identity,engine.VERSION])), **identity}
        data = s._text_v2_asset_bytes(asset, uid)
        normalized, *_ = s._text_v2_prepare_image(data)
        write(root, "source", normalized)
        return claim(root)

    @s.app.post("/api/text-inspection/sheet/templates/{identifier}/revise")
    async def revise(identifier: str, request: Request):
        uid = enabled_owner()
        root = root_of(get(identifier, uid))
        if root["task_type"] != "template": raise HTTPException(404,"模板不存在")
        current = latest(root)
        body = await json_body(request)
        if not isinstance(body,dict) or type(body.get("version")) is not int or body["version"] != current["version"]:
            raise HTTPException(409,"模板版本已改变，请刷新")
        if current["status"] not in {"draft","confirmed","review"}:
            raise HTTPException(409,"标准分析尚未结束")
        validate_binding(root, uid)
        try:
            elements = engine.validate_elements(body.get("elements"))
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc
        confirm = body.get("confirm") is True
        if confirm and (current.get("elements") != elements or current["status"] != "draft"):
            raise HTTPException(409,"请先保存并检查模板，再确认")
        if confirm and body.get("inventory_confirmed") is not True:
            raise HTTPException(400,"请确认所有文字、编码和图形已列入检查清单")
        revision = {**current, "id": root["id"]+"_v"+str(current["version"]+1), "root_id": root["id"],
                    "kind": "revision", "version": current["version"]+1, "created_at": time.time(),
                    "status": "confirmed" if confirm else "draft", "elements": elements,
                    "elements_sha256": engine.digest(elements), "inventory_confirmed": confirm}
        if not save(revision): raise HTTPException(409,"模板被另一页面修改，请刷新")
        return public(revision)

    @s.app.post("/api/text-inspection/sheet/jobs")
    async def create_job(template_id: str = Form(...), request_id: str = Form(...), file: UploadFile = File(...)):
        uid = enabled_owner()
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}",request_id): raise HTTPException(400,"请求 ID 无效")
        template = get(template_id,uid)
        if template.get("task_type") != "template" or template["status"] != "confirmed":
            raise HTTPException(409,"请先确认元素模板")
        data = await file.read(10*1024*1024+1)
        try:
            normalized, *_ = s._text_v2_prepare_image(data)
        except Exception as exc:
            raise HTTPException(400,"图片无法解码或超过安全限制") from exc
        identity = engine.digest([template_id,template["elements_sha256"],s.sha256_bytes(data),engine.VERSION])
        identifier = "sej_"+engine.digest([uid,request_id])[:40]
        existing = optional(identifier,uid)
        # Read an unchanged previous request even if the standard later changed.
        if existing:
            if existing["fingerprint"] != identity: raise HTTPException(409,"请求 ID 已用于不同输入")
            return public(latest(existing))
        validate_binding(template,uid)
        if latest(root_of(template))["id"] != template_id:
            raise HTTPException(409,"模板已修改，请重新确认")
        root = {**new_root(uid,identifier,"comparison",identity),
                **{k:template[k] for k in ("standard_id","standard_asset_id","standard_revision_id","reference_asset_sha256")},
                "template_id": template_id, "elements_sha256": template["elements_sha256"], "elements": template["elements"]}
        write(root,"original",data); write(root,"source",normalized); write(root,"reference",read(template,"source"))
        return claim(root)

    @s.app.get("/api/text-inspection/sheet/jobs")
    def list_jobs(standard_asset_id: str):
        uid=owner()
        # Historical jobs stay readable after an asset is disabled.
        if not s._text_v2_owned("assets",standard_asset_id,uid):raise HTTPException(404,"标准不存在")
        values=sorted((v for v in rows(uid) if v["kind"]=="root" and v["task_type"]=="comparison" and v["standard_asset_id"]==standard_asset_id),key=lambda v:-v["created_at"])
        return {"items":[public(latest(value)) for value in values[:50]]}

    @s.app.get("/api/text-inspection/sheet/resources/{identifier}")
    def status(identifier: str):
        value = get(identifier, owner())
        root = root_of(value)
        result=public(latest(root) if value["kind"] == "root" else value)
        late=optional(root["id"]+"_late_diagnostics",root["owner_user_id"])
        if late:result["late_diagnostics"]=late["diagnostics"]
        return result

    @s.app.get("/api/text-inspection/sheet/resources/{identifier}/media/{kind}")
    def media(identifier: str, kind: str):
        value = get(identifier, owner())
        if kind not in {"source","original","reference","standard_overlay","actual_overlay",*("advisory_"+str(i) for i in range(6))} or not value.get(kind+"_path"):
            raise HTTPException(404,"图片不存在")
        data = read(value,kind)
        return Response(data, media_type="image/png" if data.startswith(b"\x89PNG") else "image/jpeg" if data.startswith(b"\xff\xd8") else "application/octet-stream",
                        headers={"Cache-Control":"private, no-store", "X-Content-Type-Options":"nosniff"})

    return {"run": run, "expire": expire}

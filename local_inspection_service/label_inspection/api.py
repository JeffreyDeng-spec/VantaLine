"""Account-owned label tasks and a read-only adapter for pre-existing histories."""

import asyncio
import io
import time
from pathlib import Path
from PIL import Image
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from collections.abc import Callable
from .dependencies import LabelAccess, RepositoryLifecycle, LabelImports, ModelProvider, Record, require_models
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from . import model, pdf_import, manual, manual_history
from ..storage.label_inspection import LabelRepository
from ..storage.agent_operations import OperationConflict
from ..codex_compare.media import MediaStore
from ..codex_compare.contracts import digest
from ..comparison_history import project, state

PREFIX = "/api/label-inspection"
IMAGE_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
    ".bmp": "BMP",
}
REQUEST = r"^[A-Za-z0-9_.-]{8,128}$"


class Edit(BaseModel):
    request_id: str = Field(pattern=REQUEST)
    revision: int = Field(ge=1)
    operation: str = Field(pattern="^(name|hide|restore)$")
    value: str = Field(min_length=1, max_length=200)


def public(value, *, diagnostic=False):
    result = {
        k: v
        for k, v in value.items()
        if k not in {"owner_user_id", "idempotency_key", "parameters", "kind"}
    }
    if not diagnostic and value.get("kind") == "run":
        for key in (
            "model",
            "prompt_hash",
            "layout",
            "transformations",
            "profile_snapshot",
        ):
            result.pop(key, None)
        if result.get("error") and not result.get("error_code"):
            result["error"] = (
                "检测未完成，请稍后手动重新检测；如需协助，请提供检测编号。"
            )
        if result.get("quality"):
            result["quality"] = {"checked": True}
    if "import" in result:
        result["import"] = {
            k: v
            for k, v in result["import"].items()
            if k in {"version", "completed", "total", "error"}
        }
    return result


def image(media, owner, data):
    picture, transform = model.decode(data)
    output = io.BytesIO()
    picture.save(output, "PNG")
    return {
        "original": media.put(owner, data),
        "image": media.put(owner, output.getvalue()),
        "preview": media.put(owner, model.jpeg(picture)),
        **transform,
    }


def asset(media, owner, data, identity, ordinal, metadata=None):
    value = {
        "id": identity,
        "ordinal": ordinal,
        "enabled": True,
        "name": f"标准 {ordinal}",
        **(metadata or {}),
    }
    try:
        value["media"] = image(media, owner, data)
    except Exception as exc:
        value.update(
            enabled=False,
            error=str(exc)[:250] if isinstance(exc, ValueError) else "图片内容无法解码",
            original=media.put(owner, data),
        )
    return value


def register(app: FastAPI, access: LabelAccess, repositories: RepositoryLifecycle,
             imports: LabelImports, models: ModelProvider, configuration: Callable[[], Record]):
    pdf_import.register(app, repositories, imports.data_directory)

    def context():
        access.require_permission("inspection")
        owner = access.owner()[0]
        raw = repositories.repository()
        if raw is None:
            raise HTTPException(503, "标签检验需要 PostgreSQL 存储")
        return (
            owner,
            LabelRepository(raw),
            MediaStore(imports.data_directory() / "label_inspection" / "media"),
        )

    def enabled():
        if not configuration()["enabled"]:
            raise HTTPException(503, "标签检测服务尚未启用；历史仍可查看")

    def call(fn):
        try:
            return fn()
        except KeyError:
            raise HTTPException(404, "任务或记录不存在") from None
        except OperationConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, OSError) as exc:
            raise HTTPException(
                422,
                str(exc)[:250] if isinstance(exc, ValueError) else "图片或文档无法读取",
            ) from exc

    def require(repo, owner, identity, kind="task"):
        value = repo.get(owner, identity, kind)
        if not value:
            raise KeyError(identity)
        return value

    def legacy_data(repo, owner):
        all_standards = repo.legacy(owner, "standards")
        known = {s["id"] for s in all_standards}
        referenced = {r.get("standard_id") for r in repo.legacy(owner, "records")}
        standards = {
            x["id"]: x
            for x in all_standards
            if x.get("standard_type") == "label"
            and (x.get("import_source") != "label-batch-v3" or x["id"] in referenced)
        }
        records = [
            x
            for x in repo.legacy(owner, "records")
            if x.get("standard_id") in standards
            or (
                x.get("standard_id") not in known
                and x.get("standard_type", "label") == "label"
            )
        ]
        return standards, records

    def legacy_task(repo, owner, identity):
        sid = identity.removeprefix("legacy:")
        standards, records = legacy_data(repo, owner)
        selected = [
            x for x in records if (x.get("standard_id") or "orphan-" + x["id"]) == sid
        ]
        standard = standards.get(sid)
        if not standard and not selected:
            raise KeyError(identity)
        assets = (
            sorted(
                [
                    x
                    for x in repo.legacy(owner, "assets")
                    if x.get("standard_id") == sid
                ],
                key=lambda x: x.get("ordinal", 0),
            )
            if standard
            else []
        )
        return {
            "id": identity,
            "task_id": identity,
            "name": (standard or {}).get("name") or "原订单已缺失",
            "revision": 0,
            "source": {"type": "legacy"},
            "legacy_id": sid,
            "assets": [
                {
                    "id": x["id"],
                    "ordinal": x.get("ordinal", i + 1),
                    "name": f"标准 {x.get('ordinal',i+1)}",
                    "enabled": False,
                    "legacy_url": f"/api/text-inspection/assets/{x['id']}/content",
                }
                for i, x in enumerate(assets)
            ],
            "missing": None if standard else "原订单关联缺失，旧记录可读，无法继续检测",
            "created_at": (standard or {}).get("created_at", 0),
            "updated_at": max(
                [x.get("created_at", 0) for x in selected]
                + [(standard or {}).get("updated_at", 0)]
            ),
        }

    def resolve(repo, owner, identity):
        if identity.startswith(manual_history.PREFIX):
            return manual_history.resolve(repo, owner, identity)
        if identity.startswith("legacy:"):
            extension = next(
                (
                    x
                    for x in repo.list(owner, "task")
                    if x.get("legacy_id") == identity[7:]
                ),
                None,
            )
            return extension or legacy_task(repo, owner, identity)
        return require(repo, owner, identity)

    def histories(repo, owner, task):
        if task.get("read_only"):
            return []
        runs = (
            [public(x) for x in repo.list(owner, "run", task["id"])]
            if task["revision"]
            else []
        )
        if task.get("legacy_id"):
            _, records = legacy_data(repo, owner)
            for record in records:
                if (record.get("standard_id") or "orphan-" + record["id"]) != task[
                    "legacy_id"
                ]:
                    continue
                row = project(record)
                runs.append(
                    {
                        "id": "legacy:" + record["id"],
                        "task_id": task["id"],
                        "created_at": row["created_at"],
                        "status": state(row),
                        "decision": row["decision"],
                        "revision": row.get("standard_revision_number"),
                        "legacy_record_id": record["id"],
                        "elapsed": (row.get("elapsed_ms") or 0) / 1000,
                    }
                )
        return sorted(runs, key=lambda x: (x["created_at"], x["id"]), reverse=True)

    def detail(repo, owner, task):
        return {**public(task), "runs": histories(repo, owner, task)}

    @app.get(PREFIX + "/capabilities")
    def capabilities():
        context()
        return {
            "enabled": configuration()["enabled"],
        }

    @app.get(PREFIX + "/tasks")
    def tasks(
        q: str = Query("", max_length=200),
        source: str = Query(
            "all", pattern="^(all|word|image|pdf|legacy|legacy_manual|beta)$"
        ),
        result: str = Query("all", pattern="^(all|MATCH|DIFFERENCES|REVIEW_REQUIRED)$"),
        cursor: str = Query("", max_length=512),
        limit: int = Query(20, ge=1, le=100),
    ):
        owner, repo, _ = context()

        def work():
            filters = {"q": q, "source": source, "result": result}
            if cursor:
                return repo.page(owner, [], filters, limit, cursor)
            current = repo.list(owner, "task")
            standards, records = legacy_data(repo, owner)
            extended = {x.get("legacy_id") for x in current}
            ids = set(standards) | {
                x.get("standard_id") or "orphan-" + x["id"] for x in records
            }
            current += [
                legacy_task(repo, owner, "legacy:" + sid) for sid in ids - extended
            ]
            rows = []
            for task in current:
                runs = histories(repo, owner, task)
                latest = runs[0] if runs else {}
                rows.append(
                    {
                        "id": task["id"],
                        "name": task["name"],
                        "source": (
                            "legacy"
                            if task.get("legacy_id")
                            else (task.get("source") or {}).get("type", "word")
                        ),
                        "updated_at": max(
                            task.get("updated_at", 0), latest.get("created_at", 0)
                        ),
                        "standard_count": len(task["assets"]),
                        "run_count": len(runs),
                        "decision": latest.get("decision", "REVIEW_REQUIRED"),
                        "status": latest.get("status", task.get("status", "ready")),
                    }
                )
            for task in manual_history.rows(repo, owner):
                history = task["manual_history"]
                records = history["pages"]
                latest = max(records, key=lambda v: v.get("created_at", 0), default={})
                rows.append(
                    {
                        "id": task["id"],
                        "name": task["name"],
                        "source": "legacy_manual",
                        "updated_at": task["updated_at"],
                        "standard_count": task["standard_count"],
                        "run_count": len(records),
                        "decision": latest.get("decision", "REVIEW_REQUIRED"),
                        "status": "read_only",
                    }
                )
            for beta in repo.legacy(owner, "beta"):
                inputs = beta.get("inputs") or {}
                batch = beta.get("report_version") == "label-batch-v3"
                rows.append(
                    {
                        "id": "beta:" + beta["id"],
                        "name": inputs.get("standard_name") or "标签检查 Beta",
                        "source": "beta",
                        "updated_at": beta.get("updated_at")
                        or beta.get("created_at", 0),
                        "standard_count": (
                            len(inputs.get("references", {})) if batch else 1
                        ),
                        "run_count": len(beta.get("labels", {})) if batch else 1,
                        "decision": (beta.get("summary") or {}).get(
                            "decision", "REVIEW_REQUIRED"
                        ),
                        "status": beta.get("status", ""),
                        "url": "/workspace/text-compare-codex?"
                        + ("batch=" if batch else "task=")
                        + beta["id"],
                    }
                )
            rows = [
                x
                for x in rows
                if q.lower() in x["name"].lower()
                and (source == "all" or source == x["source"])
                and (result == "all" or result == x["decision"])
            ]
            rows.sort(key=lambda x: (x["updated_at"], x["id"]), reverse=True)
            return repo.page(owner, rows, filters, limit)

        return call(work)

    @app.post(PREFIX + "/tasks")
    async def create(
        file: UploadFile = File(...), request_id: str = Form(..., pattern=REQUEST)
    ):
        context()
        filename = Path(file.filename or "").name
        extension = Path(filename).suffix.lower()
        if extension not in {*IMAGE_FORMATS, ".doc", ".docx", ".pdf"}:
            raise HTTPException(422, "仅支持 PDF、DOC、DOCX、JPG/JPEG、PNG、WebP、BMP")
        maximum = (
            pdf_import.MAX_BYTES
            if extension == ".pdf"
            else (
                model.MAX_BYTES
                if extension in IMAGE_FORMATS
                else (30 if extension == ".doc" else 100) * 1024 * 1024
            )
        )
        data = await file.read(maximum + 1)

        def work():
            owner, repo, media = context()
            if not data or len(data) > maximum:
                raise ValueError(
                    "图片不能为空或超过 10 MiB"
                    if extension in IMAGE_FORMATS
                    else "文档超出上传限制"
                )
            if extension == ".pdf":
                entries = pdf_import.inspect(data)
                task = repo.create_pdf(
                    owner,
                    request_id,
                    Path(filename).stem[:200] or "新任务",
                    {
                        "type": "pdf",
                        "filename": filename,
                        "document_sha256": media.put(owner, data),
                    },
                    entries,
                    pdf_import.VERSION,
                )
                return JSONResponse(detail(repo, owner, task), status_code=202)
            if extension in IMAGE_FORMATS:
                try:
                    with Image.open(io.BytesIO(data)) as source:
                        if source.format != IMAGE_FORMATS[extension]:
                            raise ValueError("图片实际格式与文件扩展名不一致")
                        if getattr(source, "n_frames", 1) != 1:
                            raise ValueError("不支持动画或多帧图片，请上传单张静态图片")
                except Image.DecompressionBombError as exc:
                    raise ValueError("图片超过 1600 万像素") from exc
                # Strict decoding must finish before creating any task. Unlike Word
                # extraction, a failed direct upload must not become an invalid asset.
                standard = {
                    "id": "a_" + digest({"request": request_id, "index": 0})[:24],
                    "ordinal": 1,
                    "enabled": True,
                    "name": "标准 1",
                    "media": image(media, owner, data),
                }
                task = repo.create(
                    owner,
                    request_id,
                    Path(filename).stem[:200] or "新任务",
                    [standard],
                    {
                        "type": "image",
                        "filename": filename,
                        "image_sha256": standard["media"]["original"],
                    },
                )
                return detail(repo, owner, task)
            if filename.lower().endswith(".docx"):
                entries, blobs = imports.extract_docx(data, raw_only=True)
            elif filename.lower().endswith(".doc"):
                entries, blobs = imports.extract_doc(data)
            else:
                raise ValueError("仅支持 DOC / DOCX 文档")
            if not entries or len(entries) > 500:
                raise ValueError("文档必须包含 1 到 500 张标准图片")
            assets = [
                asset(
                    media,
                    owner,
                    blob,
                    "a_" + digest({"request": request_id, "index": i})[:24],
                    i + 1,
                    {
                        k: entry[k]
                        for k in (
                            "source_part",
                            "paragraph_index",
                            "duplicate_of",
                            "context",
                        )
                        if k in entry
                    },
                )
                for i, (entry, blob) in enumerate(zip(entries, blobs))
            ]
            task = repo.create(
                owner,
                request_id,
                Path(filename).stem[:200] or "新任务",
                assets,
                {
                    "type": "word",
                    "filename": filename,
                    "document_sha256": media.put(owner, data),
                },
            )
            return detail(repo, owner, task)

        return await asyncio.to_thread(lambda: call(work))

    @app.get(PREFIX + "/tasks/{identity}")
    def get(identity: str):
        owner, repo, _ = context()
        return call(lambda: detail(repo, owner, resolve(repo, owner, identity)))

    @app.post(PREFIX + "/tasks/{identity}/continue")
    def continue_legacy(identity: str):
        owner, repo, media = context()

        def work():
            task = resolve(repo, owner, identity)
            if task.get("read_only") or task.get("import"):
                raise ValueError("此任务不能通过旧标准续检，请新建任务导入 PDF")
            if task["revision"]:
                return detail(repo, owner, task)
            if task["missing"]:
                raise ValueError(task["missing"])
            originals = sorted(
                [
                    a
                    for a in repo.legacy(owner, "assets")
                    if a.get("standard_id") == task["legacy_id"]
                ],
                key=lambda a: a.get("ordinal", 0),
            )
            if len(originals) > 500:
                raise ValueError("原订单超过 500 个标准条目，不能继续检测")
            assets = []
            for index, old in enumerate(originals):
                try:
                    entry = asset(
                        media,
                        owner,
                        imports.asset_bytes(old, owner),
                        old["id"],
                        index + 1,
                    )
                except Exception:
                    entry = {
                        "id": old["id"],
                        "ordinal": index + 1,
                        "name": f"标准 {index+1}",
                        "enabled": False,
                        "error": "原标准图片缺失或校验失败",
                    }
                assets.append(entry)
            if not assets:
                raise ValueError("原订单没有标准图片，无法继续检测")
            task = repo.create(
                owner,
                "legacy:" + task["legacy_id"],
                task["name"],
                assets,
                {"type": "legacy"},
                task["legacy_id"],
            )
            return detail(repo, owner, task)

        return call(work)

    @app.patch(PREFIX + "/tasks/{identity}")
    def edit(identity: str, body: Edit):
        owner, repo, _ = context()

        def change(task):
            if body.operation == "name":
                if not body.value.strip():
                    raise ValueError("名称不能为空")
                task["name"] = body.value.strip()
            else:
                entry = next((a for a in task["assets"] if a["id"] == body.value), None)
                if not entry:
                    raise KeyError(body.value)
                if body.operation == "restore" and not entry.get("media"):
                    raise ValueError("缺失或无效的原图不能恢复用于检测")
                entry["enabled"] = body.operation == "restore"

        return call(
            lambda: detail(
                repo,
                owner,
                repo.edit(
                    owner,
                    identity,
                    body.request_id,
                    body.revision,
                    body.operation,
                    body.value,
                    change,
                ),
            )
        )

    @app.post(PREFIX + "/tasks/{identity}/assets")
    async def add(
        identity: str,
        file: UploadFile = File(...),
        request_id: str = Form(..., pattern=REQUEST),
        revision: int = Form(..., ge=1),
    ):
        context()
        data = await file.read(model.MAX_BYTES + 1)

        def work():
            owner, repo, media = context()
            evidence = image(media, owner, data)

            def change(task):
                if len(task["assets"]) >= 500:
                    raise ValueError("每任务最多 500 个标准条目")
                task["assets"].append(
                    {
                        "id": "a_" + digest(request_id.encode())[:24],
                        "ordinal": len(task["assets"]) + 1,
                        "enabled": True,
                        "name": (file.filename or "追加标准")[:200],
                        "media": evidence,
                    }
                )

            return detail(
                repo,
                owner,
                repo.edit(
                    owner,
                    identity,
                    request_id,
                    revision,
                    "add",
                    {"image": evidence},
                    change,
                ),
            )

        return await asyncio.to_thread(lambda: call(work))

    @app.post(PREFIX + "/tasks/{identity}/runs")
    async def submit(
        identity: str,
        file: UploadFile = File(...),
        request_id: str = Form(..., pattern=REQUEST),
        revision: int = Form(..., ge=1),
        asset_id: str = Form(..., max_length=128),
        parent_id: str = Form("", max_length=128),
    ):
        context()
        enabled()
        data = await file.read(model.MAX_BYTES + 1)

        def work():
            owner, repo, media = context()
            enabled()
            task = require(repo, owner, identity)
            is_pdf = (task.get("source") or {}).get("type") == "pdf"
            actual = image(media, owner, data)
            # Resolve after checking idempotency: an acknowledged submission keeps its original configuration.
            prior = repo.request_run(owner, request_id)
            selected = (
                prior.get("profile_snapshot")
                if prior
                else require_models(models).snapshot().get("label")
            )
            resolved = require_models(models).resolve("label", selected)
            if is_pdf and resolved.get("provider") != "doubao":
                raise HTTPException(503, "PDF 检测需要已配置的豆包连接，请联系管理员")
            return public(
                repo.submit(
                    owner,
                    identity,
                    request_id,
                    revision,
                    asset_id,
                    actual,
                    model.MODEL if is_pdf else resolved["model"],
                    manual.PROMPT_HASH if is_pdf else model.PROMPT_HASH,
                    parent_id,
                    profile_snapshot=selected,
                )
            )

        return await asyncio.to_thread(lambda: call(work))

    @app.get(PREFIX + "/requests/{request_id}")
    def request_lookup(request_id: str):
        owner, repo, _ = context()
        run = repo.request_run(owner, request_id)
        return {"run": public(run) if run else None}

    @app.get(PREFIX + "/runs/{identity}")
    def get_run(identity: str):
        owner, repo, _ = context()
        return call(lambda: public(require(repo, owner, identity, "run")))

    @app.get(PREFIX + "/runs/{identity}/diagnostics")
    def diagnostics(identity: str):
        access.require_admin()
        owner, repo, _ = context()

        def work():
            run = require(repo, owner, identity, "run")
            return {
                "run": public(run, diagnostic=True),
                "quality": run.get("quality"),
                "calls": [
                    public(c)
                    for c in repo.list(owner, "call", run["task_id"])
                    if c["run_id"] == identity
                ],
            }

        return call(work)

    @app.get(PREFIX + "/tasks/{identity}/history-media/{page_id}")
    def manual_photo(identity: str, page_id: str):
        owner, repo, _ = context()

        def work():
            task = manual_history.resolve(repo, owner, identity)
            if not any(p["id"] == page_id for p in task["manual_history"]["pages"]):
                raise KeyError(page_id)
            page = next(
                p
                for p in (repo.legacy(owner, "pages") + repo.legacy(owner, "records"))
                if p["id"] == page_id
            )
            session = next(
                (
                    s
                    for s in repo.legacy(owner, "sessions")
                    if s["id"] == page.get("session_id")
                ),
                {},
            )
            data = imports.read_verified(
                page.get("media_path", ""),
                owner,
                page.get("standard_id") or session.get("standard_id", ""),
                expected_sha256=page.get("source_sha256", ""),
                max_bytes=20 * 1024 * 1024,
            )
            return Response(
                data,
                media_type="image/png" if data.startswith(b"\x89PNG") else "image/jpeg",
                headers={
                    "Cache-Control": "private, no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )

        return call(work)

    @app.get(PREFIX + "/tasks/{identity}/media/{sha}")
    def media_read(identity: str, sha: str):
        owner, repo, media = context()

        def work():
            task = require(repo, owner, identity)
            objects = (
                [task]
                + repo.list(owner, "revision", identity)
                + repo.list(owner, "run", identity)
            )
            allowed = set()
            for obj in objects:
                images = [a.get("media") for a in obj.get("assets", [])] + [
                    obj.get("actual"),
                    (obj.get("reference") or {}).get("media"),
                ]
                for evidence in images:
                    if evidence:
                        allowed.update(
                            evidence.get(k) for k in ("original", "image", "preview")
                        )
            if sha not in allowed:
                raise KeyError(sha)
            data = media.read(owner, sha)
            # Original files are attachments; display always uses normalized image/preview.
            mime = (
                "image/png"
                if data.startswith(b"\x89PNG")
                else (
                    "image/jpeg"
                    if data.startswith(b"\xff\xd8")
                    else "application/octet-stream"
                )
            )
            return Response(
                data,
                media_type=mime,
                headers={
                    "Cache-Control": "private, no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )

        return call(work)

    from .worker import register as register_worker

    register_worker(app, repositories, imports.data_directory, models)

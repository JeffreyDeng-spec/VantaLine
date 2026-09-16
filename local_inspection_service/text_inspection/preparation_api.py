"""HTTP registration for preparation and its historical comparison evidence."""
import time
from fastapi import FastAPI, HTTPException, Request, Response
from .preparation_jobs import PreparationJobs
from .preparation_policy import enabled
from .preparation_ports import PreparationAccess, PreparationRecords, PreparationMedia, PreparationHistory


def register(app: FastAPI, access: PreparationAccess, storage: PreparationRecords,
             history: PreparationHistory, media_dependencies: PreparationMedia,
             jobs: PreparationJobs):
    def owner():
        access.require_permission("inspection", detail="没有文字检验权限")
        return access.owner()[0]

    @app.get("/api/text-inspection/preparation-capabilities")
    def capabilities():
        uid = owner()
        from ..standard_preparation_ocr import available
        return {"enabled": enabled(uid), "ocr_available": available(), "scope": "text_and_decoded_codes_only", "graphics_checked": False}

    @app.get("/api/text-inspection/prepared-comparisons/by-request/{request_id}")
    def comparison_by_request(request_id: str):
        """Recover an upload acknowledgment; never submit or mutate a model job."""
        uid = owner()
        if not request_id or len(request_id) > 128:
            raise HTTPException(400, "无效请求标识")
        repository = storage.repository()
        if repository is not None:
            row = repository.fetch_one_by_columns(history.record_table(),
                {"owner_user_id": uid, "comparison_id": request_id})
            records = history.raw_rows([row]) if row else []
        else:
            records = storage.load("records")
        record = next((r for r in records
            if r.get("owner_user_id") == uid and r.get("comparison_id") == request_id
            and r.get("preparation_compare")), None)
        if not record:
            raise HTTPException(404, "本账户未找到该比较请求")
        return history.public(record)

    @app.get("/api/text-inspection/prepared-comparisons/{record_id}")
    def comparison(record_id: str):
        uid = owner()
        record = storage.owned("records", record_id, uid)
        if not record or not record.get("preparation_compare"):
            raise HTTPException(404, "比较记录不存在")
        if record.get("status") == "attempting" and time.time()-record["created_at"] > 120:
            if record.get("ocr_provider") == "qwen_ocr":
                from ..qwen_evidence_jobs import timeout
                timeout(history.update_attempt, record)
                return history.public(storage.owned("records", record_id, uid))
            record.update(status="review_required", decision="REVIEW_REQUIRED", message="任务超时或服务重启，请复核；未自动重跑。")
            storage.save("records", record)
        return history.public(record)

    @app.get("/api/text-inspection/prepared-comparisons/{record_id}/media/{kind}")
    def comparison_media(record_id: str, kind: str):
        uid = owner()
        record = storage.owned("records", record_id, uid)
        if not record or not record.get("preparation_compare"):
            raise HTTPException(404, "比较证据不存在")
        if kind.startswith('audit-'):
            evidence = next((f for a in record.get('diagnostics', {}).get('model_audits', [])
                for f in a.get('files', {}).values() if f.get('kind') == kind), None)
            if not evidence:
                raise HTTPException(404, "调用证据不存在")
            data = media_dependencies.read_verified(evidence['path'], uid, record['standard_id'], expected_sha256=evidence['sha256'])
            return Response(data, media_type='application/octet-stream', headers={
                'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
                'Content-Disposition': 'attachment; filename="model-evidence.bin"'})
        if kind == 'preview':
            path = record.get('source_preview_path')
            if path:
                data = media_dependencies.read_verified(path, uid, record['standard_id'], expected_sha256=record['source_preview_sha256'])
            else:
                # Historical records remain immutable; no model or business edit.
                from .. import evidence_preview
                from ..standard_preparation import decode
                source = media_dependencies.read_verified(record['source_path'], uid, record['standard_id'], expected_sha256=record['source_sha256'])
                data, _ = evidence_preview.create(decode(source))
            return Response(data, media_type='image/jpeg', headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
        if kind not in {"reference", "source"}:
            trace = next((t for t in record.get('diagnostics', {}).get('rereads', []) if t.get('id') == kind), None)
            if not trace:
                raise HTTPException(404, "比较证据不存在")
            data = media_dependencies.read_verified(trace.get('input_path', ''), uid, record['standard_id'], expected_sha256=trace.get('input_sha256', ''))
            return Response(data, media_type='image/png', headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})
        if kind == "source":
            from ..standard_preparation import decode, png
            from PIL import Image
            import io
            data = media_dependencies.read_verified(record.get("source_path", ""), uid, record["standard_id"], expected_sha256=record.get("source_sha256", ""))
            with Image.open(io.BytesIO(data)) as original:
                orientation = original.getexif().get(274, 1)
            if orientation != 1:
                data, mime = png(decode(data)), 'image/png'
            elif data.startswith(b'\xff\xd8\xff'):
                mime = 'image/jpeg'
            elif data.startswith(b'\x89PNG\r\n\x1a\n'):
                mime = 'image/png'
            else:
                data, mime = png(decode(data)), 'image/png'
            return Response(data, media_type=mime, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
        data = media_dependencies.read_verified(record.get("reference_overlay_path", ""), uid, record["standard_id"], expected_sha256=record.get("reference_overlay_sha256", ""))
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

    @app.get("/api/text-inspection/standards/{identity}/preparation/{asset_id}/recovery/{region_id}/{kind}")
    def recovery_media(identity: str, asset_id: str, region_id: str, kind: str):
        data = jobs.recovery_media(identity, owner(), asset_id, region_id, kind)
        return Response(data, media_type="image/png", headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
    return jobs

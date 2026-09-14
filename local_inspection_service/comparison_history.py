"""Read-only account-owned comparison history. Never starts or repairs jobs."""
import base64
import json
import time
from fastapi import HTTPException, Query, Response


def display_snapshot(standard, asset):
    return {"name": standard.get("name", ""), "material_code": standard.get("material_code", ""),
            "version_label": standard.get("version_label", ""), "ordinal": asset.get("ordinal")}


def project(record, standard=None):
    """Small projection also used by the JSON fallback; no diagnostic bodies."""
    diagnostics = record.get("diagnostics") or {}
    display = record.get("history_display")
    return {"id": record["id"], "standard_id": record.get("standard_id", ""),
            "created_at": record.get("created_at", 0), "status": record.get("status", ""),
            "decision": record.get("final_decision") or record.get("decision") or record.get("auto_decision") or "REVIEW_REQUIRED",
            "standard_revision_number": record.get("standard_revision_number"),
            "display": display or display_snapshot(standard or {}, {}),
            "metadata_source": "snapshot" if display else "current" if standard else "unavailable",
            "phase": diagnostics.get("phase", ""), "error_type": diagnostics.get("error_type", ""),
            "elapsed_ms": diagnostics.get("elapsed_ms"), "has_source": bool(record.get("source_path"))}


def state(row, now=None):
    phase = str(row.get("phase") or "")
    if "timeout" in phase or row.get("error_type") == "TimeoutError":
        return "timeout"
    if row.get("status") == "attempting":
        return "timeout" if (now or time.time()) - row.get("created_at", 0) > 120 else "processing"
    if phase in {"failed", "interrupted"} or row.get("status") in {"failed", "uncertain"}:
        return "failed"
    return "completed" if row.get("status") == "completed" else "review"


def cursor_encode(row):
    return base64.urlsafe_b64encode(json.dumps([row["created_at"], row["id"]]).encode()).decode()


def cursor_decode(value):
    if not value:
        return None
    try:
        pair = json.loads(base64.urlsafe_b64decode(value))
        if (not isinstance(pair, list) or len(pair) != 2 or type(pair[0]) is not int
                or not isinstance(pair[1], str) or len(pair[1]) > 128):
            raise ValueError()
        return pair
    except Exception as exc:
        raise HTTPException(400, "无效分页位置") from exc


def register(ns):
    app = ns["app"]
    def owner():
        ns["require_permission"]("inspection", detail="没有文字检验权限")
        return ns["_text_v2_owner"]()[0]

    def owned(record_id, uid):
        record = ns["_text_v2_owned"]("records", record_id, uid)
        if not record:
            raise HTTPException(404, "比较记录不存在")
        return record

    @app.get("/api/text-inspection/history")
    def listing(q: str = Query("", max_length=120), result: str = Query("all"),
                cursor: str = Query("", max_length=512), limit: int = Query(20, ge=1, le=100)):
        uid = owner()
        if result not in {"all", "MATCH", "DIFFERENCES", "REVIEW_REQUIRED"}:
            raise HTTPException(400, "无效结果筛选")
        before = cursor_decode(cursor)
        repo = ns["runtime_postgres_repository_or_none"]()
        if repo is not None:
            rows = repo.list_text_comparison_history(uid, q.strip(), result, before, limit + 1)
        else:
            standards = {r["id"]: r for r in ns["_text_v2_load"]("standards") if r.get("owner_user_id") == uid}
            rows = [project(r, standards.get(r.get("standard_id"))) for r in ns["_text_v2_load"]("records") if r.get("owner_user_id") == uid]
            rows = [r for r in rows if (not before or (r["created_at"], r["id"]) < tuple(before))
                    and (result == "all" or r["decision"] == result)
                    and q.strip().lower() in " ".join(str(v or "") for v in [r["standard_id"], *r["display"].values()]).lower()]
            rows.sort(key=lambda r: (r["created_at"], r["id"]), reverse=True)
            rows = rows[:limit + 1]
        more = len(rows) > limit
        rows = rows[:limit]
        for row in rows:
            row["execution_state"] = state(row)
            row["preview_url"] = f"/api/text-inspection/history/{row['id']}/media/thumbnail" if row.pop("has_source", False) else None
            row.pop("error_type", None)
        return {"items": rows, "next_cursor": cursor_encode(rows[-1]) if more else None}

    @app.get("/api/text-inspection/history/{record_id}")
    def detail(record_id: str):
        uid = owner()
        record = owned(record_id, uid)
        summary = project(record, ns["_text_v2_owned"]("standards", record.get("standard_id", ""), uid))
        value = ns["_text_v2_public"](record)
        value["decision"] = summary["decision"]
        value["differences"] = value.get("differences") or []
        value["history"] = {**summary, "execution_state": state(summary)}
        base = f"/api/text-inspection/history/{record_id}/media"
        value["source_url"] = base + "/source" if record.get("source_path") else None
        value["source_preview_url"] = base + "/preview" if record.get("source_path") else None
        value["reference_overlay_url"] = base + "/reference"
        value["annotated_image_data_url"] = None
        value["annotated_preview_url"] = base + "/annotated-preview" if record.get("annotated_path") else None
        value["history_warning"] = "" if record.get("preparation_compare") else "旧记录仅展示当时保存的证据；未保存的元素框或诊断无法恢复。"
        diagnostics = value.get("diagnostics") or {}
        value["diagnostics"] = {k: diagnostics[k] for k in ("provider", "normalized_response") if k in diagnostics}
        value["diagnostics_url"] = f"/api/text-inspection/history/{record_id}/diagnostics"
        return value

    @app.get("/api/text-inspection/history/{record_id}/diagnostics")
    def diagnostics(record_id: str):
        return ns["_text_v2_public"](owned(record_id, owner())).get("diagnostics", {})

    @app.get("/api/text-inspection/history/{record_id}/media/{kind}")
    def media(record_id: str, kind: str):
        uid = owner()
        record = owned(record_id, uid)
        sid = record["standard_id"]
        def read(path, sha):
            return ns["_text_v2_read_verified"](path or "", uid, sid, expected_sha256=sha or "")
        from . import evidence_preview
        from .standard_preparation import decode, png
        if kind == "reference":
            if record.get("reference_overlay_path"):
                data = read(record["reference_overlay_path"], record.get("reference_overlay_sha256"))
            else:
                # Resolve only the recorded immutable revision, never today's active image.
                revision = ns["_text_v2_owned"]("revisions", record.get("standard_revision_id", ""), uid)
                snap = next((a for a in (revision or {}).get("confirmed_assets", []) if a.get("id") == record.get("standard_asset_id")), None)
                if not snap or revision.get("standard_id") != sid:
                    raise HTTPException(404, "当次标准图片未留存")
                prep = snap.get("preparation")
                if prep:
                    if prep.get("sha256") != record.get("reference_sha256"):
                        raise HTTPException(409, "标准版本校验失败")
                    path = ns["_text_v2_media_path"](uid, sid, f"preparation_{prep['id']}_clean.png")
                    data = read(str(path), prep["sha256"])
                else:
                    asset = ns["_text_v2_owned"]("assets", snap["id"], uid)
                    if not asset or asset.get("standard_id") != sid or asset.get("sha256") != snap.get("sha256"):
                        raise HTTPException(404, "当次标准图片未留存")
                    data = read(asset.get("media_path"), snap["sha256"])
            data = png(decode(data)); mime = "image/png"
        elif kind in {"source", "preview", "thumbnail", "annotated-preview"}:
            if kind in {"preview", "thumbnail"} and record.get("source_preview_path"):
                data = read(record["source_preview_path"], record.get("source_preview_sha256")); mime = "image/jpeg"
            else:
                prefix = "annotated" if kind == "annotated-preview" else "source"
                data = read(record.get(prefix+"_path"), record.get(prefix+"_sha256"))
                if kind != "source":
                    data, _ = evidence_preview.create(decode(data)); mime = "image/jpeg"
                else:
                    import io
                    from PIL import Image
                    with Image.open(io.BytesIO(data)) as image:
                        orientation = image.getexif().get(274, 1)
                    if orientation == 1 and data.startswith(b'\xff\xd8\xff'):
                        mime = "image/jpeg"
                    elif orientation == 1 and data.startswith(b'\x89PNG\r\n\x1a\n'):
                        mime = "image/png"
                    else:
                        data = png(decode(data)); mime = "image/png"
            if kind == "thumbnail":
                import io
                from PIL import Image
                image = decode(data)
                image.thumbnail((240, 240), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.convert("RGB").save(output, format="JPEG", quality=80)
                data = output.getvalue(); mime = "image/jpeg"
        else:
            raise HTTPException(404, "比较证据不存在")
        return Response(data, media_type=mime, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

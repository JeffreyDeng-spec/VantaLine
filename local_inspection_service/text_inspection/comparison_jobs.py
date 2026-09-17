"""Local comparison consumes immutable prepared elements, never re-OCRs reference."""
import copy
import json
import threading
import time
import uuid
from collections.abc import Callable

from fastapi import HTTPException
from .. import standard_preparation as engine
from .. import qwen_evidence_jobs
from .. import local_ocr_reread
from .. import evidence_preview
from .history import display_snapshot
from .comparison_ports import ComparisonRecords, ComparisonMedia, ComparisonModels, EnvironmentReader

_slots = threading.BoundedSemaphore(1)


def submit(records: ComparisonRecords, media: ComparisonMedia, models: ComparisonModels,
           clear_repository: Callable[[], None], getenv: EnvironmentReader,
           jobs, owner, username, standard, asset, snapshot, upload, request_id, extraction):
    use_qwen = qwen_evidence_jobs.enabled(owner)
    binding = dict(standard_asset_id=asset["id"], standard_revision_id=standard.get("current_revision_id"),
        template_revision=snapshot["preparation"]["id"], reference_sha256=snapshot["preparation"]["sha256"],
        source_sha256=media.digest(upload), version=engine.VERSION,
        extraction_id=(extraction or {}).get("id"))
    if use_qwen:
        binding["actual_provider"] = qwen_evidence_jobs.VERSION
        binding["local_reread"] = local_ocr_reread.VERSION if local_ocr_reread.enabled(owner) else None
    fingerprint = media.digest(json.dumps(binding, sort_keys=True).encode())
    def existing():
        value = next((r for r in records.load("records") if r.get("owner_user_id") == owner and r.get("comparison_id") == request_id), None)
        if value and value.get("fingerprint") != fingerprint:
            raise HTTPException(409, "comparison_id 已用于其他输入或标准版本")
        return value
    prior = existing()
    if prior:
        return records.public(prior)
    try:
        resolved = qwen_evidence_jobs.settings(models, owner) if use_qwen else None
    except ValueError as error:
        raise HTTPException(409, "当前账户的 Qwen OCR 配置或外发授权不可用") from error
    if not engine.supports_text_comparison(snapshot["preparation"]):
        raise HTTPException(409, "该标准仅含图形，没有可核对文字或编码，当前不支持文字对比")
    # Decode/verify input before registering work; bytes stored exactly once.
    image = engine.decode(upload)
    record = dict(id="ins_"+uuid.uuid4().hex, owner_user_id=owner, owner_username=username,
        standard_id=standard["id"], standard_asset_id=asset["id"], comparison_id=request_id,
        history_display=display_snapshot(standard, asset),
        standard_revision_id=standard.get("current_revision_id", ""), standard_revision_number=standard.get("revision_number", 0),
        reference_sha256=binding["reference_sha256"], fingerprint=fingerprint, fingerprint_components=binding,
        source_sha256=binding["source_sha256"], source_format="image", status="attempting", decision="REVIEW_REQUIRED",
        auto_decision="REVIEW_REQUIRED", final_decision="", differences=[], created_at=int(time.time()), updated_at=int(time.time()),
        message="正在识别实拍图；仅检查文字与可解码编码，图形未检查。", preparation_compare=True,
        diagnostics=dict(template=copy.deepcopy(snapshot["preparation"]), phase="queued", external_calls=0))
    path = media.path(owner, standard["id"], record["id"]+"-source.bin")
    media.write(path, upload)
    record["source_path"] = str(path)
    before_preview = time.monotonic()
    evidence_preview.save(media, record, image)
    record['diagnostics']['preview_ms'] = round((time.monotonic()-before_preview)*1000)
    if use_qwen:
        record.update(ocr_provider="qwen_ocr", deadline_at=time.time()+120)
        record["diagnostics"].update(provider="qwen_ocr", version=qwen_evidence_jobs.VERSION,
                                    reread_version=binding.get("local_reread"))
    if not records.save("records", record, insert_only=True):
        prior = existing()
        if prior:
            return records.public(prior)
        raise HTTPException(409, "比较任务冲突")
    threading.Thread(target=qwen_evidence_jobs.run if use_qwen else run,
        args=(records, media, clear_repository, jobs, record, upload, resolved, models.record_usage) if use_qwen else
             (records, media, clear_repository, jobs, record, upload, getenv), daemon=True).start()
    return records.public(record)


def run(records: ComparisonRecords, media: ComparisonMedia, clear_repository: Callable[[], None],
        jobs, record, upload, getenv: EnvironmentReader):
    start = time.monotonic()
    acquired = False
    try:
        if not engine.supports_text_comparison(record["diagnostics"]["template"]):
            record.update(status="review_required", decision="REVIEW_REQUIRED", auto_decision="REVIEW_REQUIRED",
                          message="纯图形或空模板不支持文字对比；未执行识别，不能判定通过。")
            record["diagnostics"]["phase"] = "unsupported_template"
            return
        acquired = _slots.acquire(timeout=120)
        if not acquired or time.monotonic()-start >= 120:
            raise TimeoutError("queue_timeout")
        record["diagnostics"]["phase"] = "recognizing"
        records.save("records", record)
        observed = jobs.observe(engine.decode(upload), timeout=max(0, 120-(time.monotonic()-start)))
        if time.monotonic()-start >= 120:
            raise TimeoutError("recognition_timeout")
        template = record["diagnostics"]["template"]
        rows = engine.match(template["elements"], observed)
        reference = engine.decode(jobs.media(record["standard_id"], record["owner_user_id"], record["standard_asset_id"], template["id"], "clean"))
        annotation = engine.overlay(reference, [dict(id=r["element_id"], box=r["standard_box"], state="keep" if r["state"] == "matched" else "uncertain") for r in rows])
        path = media.path(record["owner_user_id"], record["standard_id"], record["id"]+"-reference.png")
        media.write(path, annotation)
        record.update(reference_overlay_path=str(path), reference_overlay_sha256=media.digest(annotation),
            reference_overlay_url=f"/api/text-inspection/prepared-comparisons/{record['id']}/media/reference")
        matched = bool(rows) and all(r["state"] == "matched" for r in rows)
        # Commissioning for the new pipeline is independent from old VLM MATCH.
        from .preparation_policy import enabled
        commissioned = record["owner_user_id"] in {v.strip() for v in getenv("VANTALINE_STANDARD_ELEMENTS_MATCH_ACCOUNTS", "").split(",")}
        record.update(decision="MATCH" if matched and commissioned and enabled(record["owner_user_id"]) else "REVIEW_REQUIRED",
            status="completed", message="文字与可解码编码均有匹配证据；图形未检查。" if matched and commissioned else
            "需要复核：未检出不等于漏印；图形未检查。" if not matched else "已检查元素均匹配，但此管线自动通过尚未验收；图形未检查。")
        record["auto_decision"] = record["decision"]
        record["diagnostics"].update(phase="completed", normalized_response=dict(elements=rows, observations=observed, graphics_checked=False))
    except Exception as exc:
        record.update(status="review_required", decision="REVIEW_REQUIRED", message="识别未完成，请人工复核；不会转用付费模型。")
        record["diagnostics"].update(phase="failed", error_type=type(exc).__name__)
    finally:
        if time.monotonic()-start >= 120:
            record.update(status="review_required", decision="REVIEW_REQUIRED", auto_decision="REVIEW_REQUIRED", message="识别超时，请人工复核。")
        record["diagnostics"]["elapsed_ms"] = round((time.monotonic()-start)*1000)
        record["updated_at"] = int(time.time())
        records.save("records", record)
        clear_repository()
        if acquired:
            _slots.release()

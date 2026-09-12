"""Opt-in actual-only OCR, durable no-replay cache, and verified text mappings."""
import copy
import hashlib
import json
import os
import threading
import time

from . import evidence_matching as matching
from . import qwen_ocr_evidence as ocr
from . import standard_preparation as engine

VERSION = "qwen-evidence-jobs-v2-existence"
_slots = threading.BoundedSemaphore(1)


def enabled(owner):
    return owner in {v.strip() for v in os.getenv("VANTALINE_QWEN_OCR_ACCOUNTS", "").split(",") if v.strip()}


def settings(s, owner):
    if not enabled(owner) or not s.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED:
        raise ValueError("ocr_external_authorization_unavailable")
    resolved = s.ai_detection_settings()
    if resolved.get("provider") != "qwen" or not resolved.get("api_key"):
        raise ValueError("qwen_credentials_unavailable")
    ocr.endpoint(resolved["base_url"])
    return resolved


def llm(resolved, request, timeout):
    import requests
    payload = dict(model=resolved["model"], input={"messages": [
        {"role": "system", "content": [{"text": matching.PROMPT}]},
        {"role": "user", "content": [{"text": json.dumps(request, ensure_ascii=False)}]}]},
        parameters={"enable_thinking": False, "temperature": 0, "max_tokens": 4096})
    response = requests.post(ocr.endpoint(resolved["base_url"]),
        headers={"Authorization": "Bearer " + resolved["api_key"]}, json=payload,
        timeout=max(.1, timeout), allow_redirects=False, stream=True)
    try:
        if response.status_code != 200:
            raise ocr.EvidenceError("mapping_http_" + str(response.status_code))
        chunks, count = [], 0
        for chunk in response.iter_content(65536):
            count += len(chunk)
            if count > 500_000:
                raise ocr.EvidenceError("mapping_response_capacity")
            chunks.append(chunk)
        raw = json.loads(b"".join(chunks))
        choices = raw.get("output", {}).get("choices", [])
        if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
            raise ocr.EvidenceError("mapping_incomplete")
        text = "".join(c.get("text", "") for c in choices[0].get("message", {}).get("content", []))
        if text.startswith("```json\n") and text.rstrip().endswith("```"):
            text = text[8:text.rfind("```")].strip()
        return json.loads(text), {"model": resolved["model"], "prompt_version": matching.VERSION,
            "usage": raw.get("usage", {}), "request_id": raw.get("request_id")}
    finally:
        response.close()


def expired(record):
    return time.time() >= record.get("deadline_at", record["created_at"] + 120)


def timeout(s, record):
    record = copy.deepcopy(record)
    record.update(status="review_required", decision="REVIEW_REQUIRED", auto_decision="REVIEW_REQUIRED",
        message="比较超过120秒或服务重启，请复核；不会自动重发付费请求。", updated_at=int(time.time()))
    record["diagnostics"].update(phase="timeout", error="comparison_deadline", elapsed_ms=120000)
    return s._text_v2_update_attempt("records", record)


def run(s, jobs, record, upload, resolved):
    started, acquired = time.monotonic(), False
    timer = threading.Timer(max(0, record["deadline_at"]-time.time()), lambda: settle_timeout(s, record))
    timer.daemon = True; timer.start()
    def remaining():
        seconds = record["deadline_at"] - time.time()
        if seconds <= 0:
            raise TimeoutError("comparison_deadline")
        return seconds
    def save(phase):
        remaining()
        record["diagnostics"]["phase"] = phase
        record["updated_at"] = int(time.time())
        if not s._text_v2_update_attempt("records", record):
            raise TimeoutError("comparison_already_settled")
    def measured(name, function):
        before = time.monotonic()
        try:
            return function()
        finally:
            record["diagnostics"].setdefault("stage_ms", {})[name] = round((time.monotonic()-before)*1000)
    try:
        acquired = _slots.acquire(timeout=remaining())
        if not acquired:
            raise TimeoutError("queue_timeout")
        record["diagnostics"]["stage_ms"] = {"queue": round((time.monotonic()-started)*1000)}
        image = measured("decode", lambda: engine.decode(upload))
        blob, transform = ocr.prepare(image)
        record["diagnostics"]["coordinate_transform"] = transform
        cache_id = "ocr_" + hashlib.sha256(json.dumps([record["owner_user_id"],record["source_sha256"],ocr.MODEL,ocr.VERSION]).encode()).hexdigest()
        cache = dict(id=cache_id, owner_user_id=record["owner_user_id"], status="attempting", created_at=int(time.time()),
            comparison_id=record["id"], model=ocr.MODEL, preprocess_version=ocr.VERSION,
            source_sha256=record["source_sha256"])
        save("extracting_text")
        # Insert-once is shared across workers, tabs, comparisons and restarts.
        winner = s._text_v2_save("ocr_evidence", cache, insert_only=True)
        record["diagnostics"].update(ocr_cache_id=cache_id, cache_hit=not winner)
        if winner:
            record["diagnostics"]["external_calls"] += 1
            record["diagnostics"]["ocr_call"] = {"state": "attempting", "model": ocr.MODEL}
            save("extracting_text")
            try:
                observations, diagnostic = measured("ocr", lambda: ocr.recognize(resolved, blob, image.size, remaining()))
                cache.update(status="completed", observations=observations, diagnostics=diagnostic)
                s._text_v2_update_attempt("ocr_evidence", cache)
            except Exception as error:
                cache.update(status="unknown", error_type=type(error).__name__, error=str(error) if isinstance(error, ocr.EvidenceError) else "provider_outcome_unknown")
                s._text_v2_update_attempt("ocr_evidence", cache)
                raise
        else:
            cache = s._text_v2_owned("ocr_evidence", cache_id, record["owner_user_id"])
            if not cache or cache.get("status") != "completed":
                raise ocr.EvidenceError("prior_ocr_pending_or_unknown_not_replayed")
            observations, diagnostic = copy.deepcopy(cache["observations"]), copy.deepcopy(cache["diagnostics"])
        remaining()
        record["diagnostics"]["ocr_call"] = {"state": "completed", **diagnostic}
        template = record["diagnostics"]["template"]
        if any(e.get("state") == "keep" and e.get("type") == "code" for e in template["elements"]):
            def decode_codes():
                try:
                    codes = engine.observations(image, lambda _: [])
                    for c in codes:
                        c.update(id="code_"+c["id"], provenance="local_decoder")
                    return codes
                except ValueError:
                    return []
            observations.extend(measured("codes", decode_codes))
        save("direct_matching")
        rows = measured("direct_matching", lambda: matching.direct(template["elements"], observations))
        request = measured("candidate_retrieval", lambda: matching.candidates(rows, observations))
        if request["elements"]:
            record["diagnostics"].update(mapping_request=request, llm_call={"state":"attempting", "model":resolved["model"]})
            record["diagnostics"]["external_calls"] += 1
            save("mapping_unmatched")  # Durable claim BEFORE the one text-only call.
            try:
                proposal, metadata = measured("llm", lambda: llm(resolved, request, remaining()))
                remaining()
                rows = matching.validate(proposal, request, rows)
                record["diagnostics"]["llm_call"] = {"state":"completed", **metadata, "validated_response":proposal}
            except Exception as error:
                record["diagnostics"]["llm_call"].update(state="unknown_or_invalid", error_type=type(error).__name__)
        remaining(); save("verifying_saving")
        reference = engine.decode(jobs.media(record["standard_id"], record["owner_user_id"], record["standard_asset_id"], template["id"], "clean"))
        def annotate():
            annotation = engine.overlay(reference, [dict(id=r["element_id"], box=r["standard_box"], state="keep" if r["state"] == "matched" else "exclude" if r["state"] == "difference" else "uncertain") for r in rows])
            path = s._text_v2_media_path(record["owner_user_id"], record["standard_id"], record["id"]+"-reference.png")
            s._text_v2_write(path, annotation)
            record.update(reference_overlay_path=str(path), reference_overlay_sha256=s.sha256_bytes(annotation),
                reference_overlay_url=f"/api/text-inspection/prepared-comparisons/{record['id']}/media/reference")
        measured("annotation", annotate)
        # This release deliberately has no MATCH commissioning path. Independent
        # template, negative-sample and 30-run latency acceptance are outstanding.
        record.update(status="completed", decision="REVIEW_REQUIRED", auto_decision="REVIEW_REQUIRED",
            message="已检查文字与编码均有字符匹配证据；自动通过尚未验收，请确认。图形未检查。" if rows and all(r["state"] == "matched" for r in rows)
            else "请复核标注元素：未检出不等于漏印，红色差异仍需核实。图形未检查。")
        record["diagnostics"].update(phase="completed", normalized_response={"elements":rows,"observations":observations,"graphics_checked":False},
            automatic_match_enabled=False, matching_policy=matching.VERSION,
            element_presence_satisfied=bool(rows) and all(r["state"] == "matched" for r in rows),
            inspection_scope="sheet_element_presence_not_each_label")
    except Exception as error:
        record.update(status="review_required", decision="REVIEW_REQUIRED", auto_decision="REVIEW_REQUIRED", message="文字提取或核对未完成，请人工复核；未重试或切换模型。")
        record["diagnostics"].update(phase="failed", error_type=type(error).__name__,
            error=str(error) if isinstance(error, (ocr.EvidenceError, TimeoutError)) else "evidence_processing_failed")
    finally:
        try:
            if expired(record):
                timeout(s, record)
            else:
                record["diagnostics"]["elapsed_ms"] = round((time.monotonic()-started)*1000)
                record["updated_at"] = int(time.time())
                s._text_v2_update_attempt("records", record)
        finally:
            timer.cancel()
            s.clear_thread_runtime_repository_selection()
            if acquired:
                _slots.release()


def settle_timeout(s, record):
    try:
        timeout(s, record)
    finally:
        s.clear_thread_runtime_repository_selection()

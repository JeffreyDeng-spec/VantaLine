"""Opt-in actual-only OCR, durable no-replay cache, and verified text mappings."""
import copy
import hashlib
import json
import os
import threading
import time

from . import evidence_matching as matching
from . import local_evidence_search
from . import local_ocr_reread as reread
from . import qwen_ocr_evidence as ocr
from . import standard_preparation as engine
from . import model_call_audit

VERSION = "qwen-evidence-jobs-v7-audited-json"
_slots = threading.BoundedSemaphore(1)


def enabled(owner):
    return owner in {v.strip() for v in os.getenv("VANTALINE_QWEN_OCR_ACCOUNTS", "").split(",") if v.strip()}


def settings(s, owner):
    if not enabled(owner) or not s.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED:
        raise ValueError("ocr_external_authorization_unavailable")
    resolved = s.ai_detection_settings("document")
    resolved["ocr_settings"] = s.ai_detection_settings("ocr")
    if resolved.get("provider") != "qwen" or not resolved.get("api_key"):
        raise ValueError("qwen_credentials_unavailable")
    dedicated = resolved["ocr_settings"]
    if dedicated.get("provider") != "qwen" or not dedicated.get("api_key") or dedicated.get("model") != "qwen-vl-ocr-2025-11-20":
        raise ValueError("qwen_ocr_credentials_unavailable")
    ocr.endpoint(dedicated["base_url"])
    return resolved


from .model_profiles.audit import metered_function

@metered_function(0)
def llm(resolved, request, timeout, *, audit=None, structured=True, record_usage=None):
    import requests
    payload = dict(model=resolved["model"], input={"messages": [
        {"role": "system", "content": [{"text": matching.PROMPT}]},
        {"role": "user", "content": [{"text": json.dumps(request, ensure_ascii=False)}]}]},
        parameters={"enable_thinking": False, "temperature": 0, "max_tokens": 4096})
    if structured:
        payload['parameters']['response_format'] = {'type': 'json_object'}
    if audit:
        audit('request', dict(payload=payload, prompt_version=matching.VERSION))
    network_started = time.monotonic()
    try:
        response = requests.post(ocr.endpoint(resolved["base_url"]),
            headers={"Authorization": "Bearer " + resolved["api_key"]}, json=payload,
            timeout=max(.1, timeout), allow_redirects=False, stream=True)
    except Exception as error:
        if audit: audit('transport_error', dict(error_type=type(error).__name__, elapsed_ms=round((time.monotonic()-network_started)*1000)))
        raise
    headers_ms = round((time.monotonic()-network_started)*1000)
    try:
        chunks, count = [], 0
        for chunk in response.iter_content(65536):
            count += len(chunk)
            if count > 500_000:
                if audit:
                    audit('response', dict(http_status=response.status_code, truncated=True,
                        body=(b''.join(chunks)+chunk)[:500_000].decode('utf-8', errors='replace')))
                raise ocr.EvidenceError("mapping_response_capacity")
            chunks.append(chunk)
        body = b"".join(chunks)
        if audit:
            audit('response', dict(http_status=response.status_code, truncated=False,
                body=body.decode('utf-8', errors='replace'), response_sha256=hashlib.sha256(body).hexdigest(),
                headers_ms=headers_ms, network_ms=round((time.monotonic()-network_started)*1000)))
        if response.status_code != 200:
            raise ocr.EvidenceError("mapping_http_" + str(response.status_code))
        raw = json.loads(body)
        if not isinstance(raw, dict):
            raise ocr.EvidenceError('mapping_invalid_response_envelope')
        metadata = ocr.response_metadata(raw, body)
        choices = raw.get("output", {}).get("choices", [])
        if len(choices) != 1 or choices[0].get("finish_reason") != "stop":
            raise ocr.EvidenceError("mapping_incomplete",metadata)
        text = "".join(c.get("text", "") for c in choices[0].get("message", {}).get("content", [])).strip()
        if text.startswith("```json\n") and text.rstrip().endswith("```"):
            text = text[8:text.rfind("```")].strip()
        try:
            proposal = json.loads(text)
        except json.JSONDecodeError as error:
            metadata['parse_error'] = dict(message=error.msg, line=error.lineno, column=error.colno, position=error.pos)
            if audit:
                audit('parse', dict(state='invalid_json', **metadata['parse_error']))
            raise ocr.EvidenceError('mapping_invalid_json',metadata) from None
        if audit:
            audit('parse', dict(state='parsed', proposal=proposal))
        return proposal, {"model": resolved["model"], "prompt_version": matching.VERSION,
            **metadata, "request_id": raw.get("request_id")}
    except Exception as error:
        if audit:
            audit('failure', dict(error_type=type(error).__name__,
                elapsed_ms=round((time.monotonic()-network_started)*1000),
                received_prefix=b''.join(chunks).decode('utf-8',errors='replace') if 'chunks' in locals() else ''))
        raise
    finally:
        response.close()


def expired(record):
    return time.time() >= record.get("deadline_at", record["created_at"] + 120)


def timeout(update_attempt, record):
    record = copy.deepcopy(record)
    record.update(status="review_required", decision="REVIEW_REQUIRED", auto_decision="REVIEW_REQUIRED",
        message="比较超过120秒或服务重启，请复核；不会自动重发付费请求。", updated_at=int(time.time()))
    record["diagnostics"].update(phase="timeout", error="comparison_deadline", elapsed_ms=120000)
    return update_attempt("records", record)


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
        cache_id = "ocr_" + hashlib.sha256(json.dumps([record["owner_user_id"],record["source_sha256"],ocr.MODEL,ocr.VERSION,ocr.PRESENCE_VERSION]).encode()).hexdigest()
        cache = dict(id=cache_id, owner_user_id=record["owner_user_id"], status="attempting", created_at=int(time.time()),
            comparison_id=record["id"], model=ocr.MODEL, preprocess_version=ocr.VERSION,
            source_sha256=record["source_sha256"],validation_policy=ocr.PRESENCE_VERSION)
        save("extracting_text")
        # Insert-once is shared across workers, tabs, comparisons and restarts.
        winner = s._text_v2_save("ocr_evidence", cache, insert_only=True)
        record["diagnostics"].update(ocr_cache_id=cache_id, cache_hit=not winner)
        if winner:
            record["diagnostics"]["external_calls"] += 1
            record["diagnostics"]["ocr_call"] = {"state": "attempting", "model": ocr.MODEL}
            save("extracting_text")
            try:
                audit = model_call_audit.recorder(s, record, 'ocr', save, resolved.get('ocr_settings', resolved)['api_key'])
                observations, diagnostic = measured("ocr", lambda: ocr.recognize(resolved.get("ocr_settings", resolved), blob, image.size, remaining(),presence_evidence=True, audit=audit, record_usage=getattr(s, "record_model_call", None)))
                cache.update(status="completed", observations=observations, diagnostics=diagnostic)
                s._text_v2_update_attempt("ocr_evidence", cache)
            except Exception as error:
                cache.update(status="unknown", error_type=type(error).__name__, error=str(error) if isinstance(error, ocr.EvidenceError) else "provider_outcome_unknown")
                if isinstance(error, ocr.EvidenceError):
                    cache['diagnostics'] = error.diagnostics
                    record['diagnostics']['ocr_call'].update(state='failed', **error.diagnostics)
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
        rows, local_diagnostic = measured("local_exact_matching", lambda: local_evidence_search.complete(rows,observations))
        record["diagnostics"]["local_exact_matching"] = local_diagnostic
        request = measured("candidate_retrieval", lambda: matching.candidates(rows, observations))
        if request["elements"]:
            record["diagnostics"].update(mapping_request=request, llm_call={"state":"attempting", "model":resolved["model"]})
            record["diagnostics"]["external_calls"] += 1
            save("mapping_unmatched")  # Durable claim BEFORE the one text-only call.
            try:
                audit = model_call_audit.recorder(s, record, 'mapping', save, resolved['api_key'])
                proposal, metadata = measured("llm", lambda: llm(resolved, request, remaining(), audit=audit, record_usage=getattr(s, "record_model_call", None)))
                remaining()
                record["diagnostics"]["llm_call"].update(**metadata)
                rows, validation = matching.validate_independently(proposal, request, rows)
                audit('validation', validation)
                record["diagnostics"]["llm_call"].update(
                    state="completed_with_rejections" if validation["rejected_mappings"] else "completed",
                    **validation)
            except Exception as error:
                record["diagnostics"]["llm_call"].update(state="unknown_or_invalid", error_type=type(error).__name__)
                if isinstance(error,ocr.EvidenceError):
                    record['diagnostics']['llm_call'].update(error= str(error), **error.diagnostics)
        if record['diagnostics'].get('reread_version') == reread.VERSION and any(r['state'] != 'matched' for r in rows):
            regions = reread.select(image, request, observations)
            traces = record['diagnostics'].setdefault('rereads', [])
            for mode, phase in [('advanced_recognition', 'rereading_regions'), ('text_recognition', 'transcribing_regions')]:
                for region in regions:
                    if not any(r['state'] != 'matched' for r in rows):
                        break
                    if mode == 'text_recognition' and not reread.needs_text(region, request, rows):
                        continue
                    if mode == 'text_recognition':
                        region = reread.text_region(region)
                    remaining()
                    identity = 'ocr_' + hashlib.sha256(json.dumps([record['owner_user_id'], record['source_sha256'],
                        region['input_sha256'], ocr.MODEL, ocr.VERSION, reread.VERSION, mode]).encode()).hexdigest()
                    trace = {k: v for k, v in region.items() if k != 'blob'}
                    trace.update(id=identity, mode=mode, model=ocr.MODEL, state='attempting')
                    path = s._text_v2_media_path(record['owner_user_id'], record['standard_id'], record['id']+'-'+identity+'.png')
                    s._text_v2_write(path, region['blob'])
                    trace.update(input_path=str(path), input_url=f"/api/text-inspection/prepared-comparisons/{record['id']}/media/{identity}")
                    traces.append(trace)
                    save(phase)
                    claim = dict(id=identity, owner_user_id=record['owner_user_id'], status='attempting',
                        created_at=int(time.time()), comparison_id=record['id'], source_sha256=record['source_sha256'],
                        model=ocr.MODEL, preprocess_version=reread.VERSION, mode=mode)
                    winner = s._text_v2_save('ocr_evidence', claim, insert_only=True)
                    trace['cache_hit'] = not winner
                    before = time.monotonic()
                    try:
                        if winner:
                            record['diagnostics']['external_calls'] += 1
                            save(phase)  # Persist each paid claim before sending image-only input.
                            audit = model_call_audit.recorder(s, record, identity, save, resolved.get('ocr_settings', resolved)['api_key'])
                            raw, metadata = ocr.recognize(resolved.get("ocr_settings", resolved), region['blob'], region['input_size'], remaining(),
                                presence_evidence=True, region_text=mode == 'text_recognition', audit=audit, record_usage=getattr(s, 'record_model_call', None))
                            claim.update(status='completed', observations=raw, diagnostics=metadata)
                            s._text_v2_update_attempt('ocr_evidence', claim)
                        else:
                            claim = s._text_v2_owned('ocr_evidence', identity, record['owner_user_id'])
                            if not claim or claim.get('status') != 'completed':
                                raise ocr.EvidenceError('prior_reread_pending_or_unknown_not_replayed')
                            raw, metadata = copy.deepcopy(claim['observations']), copy.deepcopy(claim['diagnostics'])
                        remaining()
                        rows, mapped = reread.merge(rows, template['elements'], raw, region, mode, identity)
                        observations.extend(mapped)
                        trace.update(state='completed', diagnostics=metadata, observations=mapped)
                    except TimeoutError:
                        raise
                    except Exception as error:
                        trace.update(state='unknown_or_invalid', error_type=type(error).__name__,
                            error=str(error) if isinstance(error, ocr.EvidenceError) else 'provider_outcome_unknown')
                        if isinstance(error, ocr.EvidenceError):
                            trace['diagnostics'] = error.diagnostics
                        if winner:
                            claim.update(status='unknown', diagnostics=trace.get('diagnostics', {}), error=trace['error'])
                            s._text_v2_update_attempt('ocr_evidence', claim)
                    finally:
                        trace['elapsed_ms'] = round((time.monotonic()-before)*1000)
                        record['diagnostics'].setdefault('stage_ms', {})[phase] = sum(
                            t.get('elapsed_ms', 0) for t in traces if t['mode'] == mode)
                    save(phase)
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
                timeout(s._text_v2_update_attempt, record)
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
        timeout(s._text_v2_update_attempt, record)
    finally:
        s.clear_thread_runtime_repository_selection()

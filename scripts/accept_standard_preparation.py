"""Explicit paid, read-only acceptance probe. Never creates production standards."""
import argparse
import importlib
import json
from pathlib import Path
import sys
import time

# Extra package path lets an isolated probe use immutable runtime auth/storage
# without copying or editing production source. Also applies to spawned OCR.
if "--runtime" in sys.argv:
    runtime = Path(sys.argv[sys.argv.index("--runtime")+1])
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import local_inspection_service
    local_inspection_service.__path__.append(str(runtime/"local_inspection_service"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--standard", required=True)
    parser.add_argument("--ordinals", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ocr-cache", type=Path, help="Explicit reuse of verified earlier OCR evidence, not provider output")
    parser.add_argument("--omit-ocr-id", help="Controlled missing-detection fixture only; never counts as natural OCR accuracy")
    parser.add_argument("--allow-paid-calls", action="store_true")
    args = parser.parse_args()
    if not args.allow_paid_calls: parser.error("explicit paid-call consent required")
    from local_inspection_service import server
    from local_inspection_service import standard_preparation as engine
    from local_inspection_service import standard_preparation_ocr as ocr
    from local_inspection_service.standard_preparation_recovery import recover
    from local_inspection_service.document_label_classifier import evidence, prepare_image
    settings = server.document_import_jobs.settings(args.owner)
    if not ocr.available(): raise RuntimeError("local_ocr_models_not_available")
    standard = server._text_v2_owned("standards", args.standard, args.owner)
    if not standard: raise ValueError("owned_standard_required")
    requested = {int(v) for v in args.ordinals.split(",")}
    assets = sorted([a for a in server._text_v2_load("assets") if a.get("owner_user_id") == args.owner and a.get("standard_id") == args.standard and a.get("ordinal") in requested], key=lambda a: a["ordinal"])
    if len(assets) != len(requested) or not 1 <= len(assets) <= 20: raise ValueError("invalid_probe_scope")
    args.output.mkdir(parents=True, exist_ok=False)
    report = []
    for asset in assets:
        folder = args.output/str(asset["ordinal"])
        folder.mkdir()
        result = dict(ordinal=asset["ordinal"], source_sha256=asset["sha256"], version=engine.VERSION, external_calls=0, automatic_acceptance_verified=False)
        started = time.monotonic()
        try:
            blob = server._text_v2_asset_bytes(asset, args.owner)
            image = engine.decode(blob)
            image.save(folder/"original.png")
            if args.ocr_cache:
                cached = args.ocr_cache/str(asset["ordinal"])
                if json.loads((cached/"result.json").read_text())["source_sha256"] != asset["sha256"]:
                    raise ValueError("cached_ocr_source_mismatch")
                elements = json.loads((cached/"ocr.json").read_text())
                result["reused_ocr"] = True
            else:
                elements = engine.observations(image, ocr.recognize)
            result["ocr_ms"] = round((time.monotonic()-started)*1000)
            (folder/"ocr.json").write_text(json.dumps(elements, ensure_ascii=False, indent=2))
            if args.omit_ocr_id:
                if not any(e["id"] == args.omit_ocr_id for e in elements):
                    raise ValueError("unknown_controlled_omission_id")
                elements = [e for e in elements if e["id"] != args.omit_ocr_id]
                result["controlled_omission_id"] = args.omit_ocr_id
            (folder/"ocr-input.json").write_text(json.dumps(elements, ensure_ascii=False, indent=2))
            (folder/"elements-before.png").write_bytes(engine.overlay(image, elements))
            previews = [prepare_image(blob), prepare_image(engine.overlay(image, elements))]
            (folder/"claim.json").write_text(json.dumps(dict(state="attempting", model=settings["model"], version=engine.VERSION)))
            result["external_calls"] = 1
            provider = server.call_ai_mcp_tool("provider.gemini.generate_json", dict(provider_config={**settings, "timeout_seconds":60}, system_prompt=engine.PROMPT,
                user_content=engine.classification_content(*[server._text_v2_data_url(p,"image/jpeg") for p in previews], elements), max_tokens=6000, max_attempts=1))
            result["provider"] = evidence(json.dumps(server._text_v2_provider_diagnostics(provider,settings)),settings.get("api_key",""))
            if not provider.get("ok"): raise ValueError("provider_not_ok")
            classification = provider["parsed"]
            classified = engine.classify(classification, elements)
            def checkpoint(recovery, crop, annotated):
                row = recovery["regions"][-1]
                prefix = f"{row['id']}-{row['state']}"
                if crop is not None: crop.save(folder/(prefix+"-input.png"))
                if annotated is not None: (folder/(prefix+"-ocr.png")).write_bytes(annotated)
                (folder/"recovery.json").write_text(json.dumps(recovery, ensure_ascii=False, indent=2))
            classified, recovery = recover(image, classified, classification,
                lambda picture, timeout: engine.observations(picture, lambda bgr: ocr.recognize(bgr, timeout=timeout)), progress=checkpoint)
            result["recovery"] = recovery
            cleaned, info = engine.clean(image, classified)
            info["reasons"].extend(recovery["reasons"])
            if classification.get("coverage_complete") is not True:
                info["reasons"].append("ocr_coverage_incomplete_requires_review")
            (folder/"clean.png").write_bytes(cleaned)
            (folder/"elements-after.png").write_bytes(engine.overlay(image,classified))
            result.update(kind=classification["kind"], info=info, automatic_candidate=classification["kind"]=="label_design" and not info["reasons"])
        except Exception as exc:
            result.update(error_type=type(exc).__name__, reason=str(exc)[:160] if isinstance(exc,ValueError) else "processing_failed")
        result["elapsed_ms"] = round((time.monotonic()-started)*1000)
        (folder/"result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        report.append(result)
        print(json.dumps({k:v for k,v in result.items() if k in {"ordinal","external_calls","ocr_ms","elapsed_ms","error_type","reason","automatic_candidate","kind"}}), flush=True)
    (args.output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    ocr.stop(graceful=True)


if __name__ == "__main__": main()

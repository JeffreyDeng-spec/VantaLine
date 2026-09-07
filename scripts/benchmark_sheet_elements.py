#!/usr/bin/env python3
"""Isolated evidence runner. NEVER imports server or writes production standards.

Manifest: [{name, source, reference_box:[x,y,w,h], elements?:[...], confirmed?:bool}].
Without a confirmed human inventory, all results are explicitly unvalidated.
"""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import os
import resource
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service import sheet_elements as engine
from local_inspection_service.sheet_elements_runtime import observations
from local_inspection_service.sheet_elements_runtime import metadata as ocr_metadata
from local_inspection_service.sheet_elements_runtime import begin_task, cancel_task


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--source-dir",type=Path)
    parser.add_argument("--samples",default="",help="Comma separated manifest names; empty runs all")
    parser.add_argument("--runs",type=int,default=1)
    parser.add_argument("--timeout",type=int,default=120)
    parser.add_argument("--prepare-only",action="store_true")
    args=parser.parse_args()
    manifest=json.loads(args.manifest.read_text())
    args.output.mkdir(parents=True,exist_ok=True)
    records=[]
    for sample in manifest:
        name=sample["name"]
        if args.samples and name not in args.samples.split(","):continue
        if not name.isalnum():raise ValueError("unsafe_sample_name")
        if args.source_dir:sample["source"]=str(args.source_dir/(name+".jpg"))
        dest=args.output/name;dest.mkdir(exist_ok=True)
        with Image.open(sample["source"]) as image:
            image=ImageOps.exif_transpose(image).convert("RGB")
            image.save(dest/"source.jpg",quality=95)
            w,h=image.size;x,y,bw,bh=engine.rectangle(sample["reference_box"])
            reference=image.crop((int(x*w),int(y*h),int(np.ceil((x+bw)*w)),int(np.ceil((y+bh)*h))))
            reference.save(dest/"reference.png")
            source=cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2BGR)
            ref=cv2.cvtColor(np.asarray(reference),cv2.COLOR_RGB2BGR)
        baseline={"sample":name,"source_size":[w,h],"source_sha256":hashlib.sha256(Path(sample["source"]).read_bytes()).hexdigest(),
                  "reference_box":sample["reference_box"],"reference_sha256":hashlib.sha256((dest/"reference.png").read_bytes()).hexdigest(),
                  "template_confirmed":sample.get("confirmed",False),"same_source_reference":True,
                  "independent_accuracy_evidence":False,"version":engine.VERSION,"external_calls":0,
                  "engine_sha256":hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest(),
                  "latency_scope":"engine_plus_overlays_not_full_api_or_queue"}
        (dest/"input.json").write_text(json.dumps(baseline,indent=2))
        if args.prepare_only:
            records.append({**baseline,"status":"prepared_not_tested"});continue
        elements=sample.get("elements")
        if not elements:
            try:
                begin_task(name+"_template",time.time()+args.timeout)
                detected,details=engine.observe(ref,observations,time.time()+args.timeout,rotations=(0,1,2,3))
                elements=engine.draft_elements(detected)
                (dest/"template-ocr.json").write_text(json.dumps(details,indent=2))
            except Exception as exc:
                elements=[]
                (dest/"template-error.json").write_text(json.dumps({"type":type(exc).__name__,"code":str(exc)[:300]}))
        (dest/"template-draft.json").write_text(json.dumps(elements,ensure_ascii=False,indent=2))
        for run in range(args.runs):
            started=time.time()
            begin_task(name+"_"+str(run),started+args.timeout)
            record={**baseline,"run":run,"cold_process":not records and run==0,"status":"review"}
            try:
                values,metrics=engine.observe(source,observations,started+args.timeout)
                result=engine.compare(elements,values,ref,source,started+args.timeout)
                if not sample.get("confirmed"):
                    result["unvalidated_candidate_decision"]=result["decision"]
                    result["decision"]="REVIEW_REQUIRED"
                    result["gate_reason"]="temporary_template_requires_human_inventory"
                record.update(status="completed",result=result,diagnostics=metrics,observations=values)
                (dest/f"standard-overlay-{run}.png").write_bytes(engine.annotate(ref,result))
                (dest/f"actual-overlay-{run}.png").write_bytes(engine.annotate(source,result,False))
            except Exception as exc:
                record["failure"]={"type":type(exc).__name__,"code":str(exc)[:300]}
                if isinstance(exc,engine.ObservationTimeout):
                    record["partial_observations"]=exc.observations
                    record["partial_stages"]=exc.stages
                # Even failed runs retain visible input evidence and an explicit status.
                (dest/f"standard-overlay-{run}.png").write_bytes((dest/"reference.png").read_bytes())
                cv2.imwrite(str(dest/f"actual-overlay-{run}.png"),source)
            record["elapsed_ms"]=round((time.time()-started)*1000)
            record["ocr_artifacts"]=ocr_metadata()
            record["max_rss_native_units"]=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            record["rss_scope"]="runner_process_only_excludes_native_ocr_subprocess"
            records.append(record)
            (dest/f"result-{run}.json").write_text(json.dumps(record,ensure_ascii=False,indent=2))
            print(json.dumps({k:record[k] for k in ("sample","run","status","elapsed_ms")}),flush=True)
            # Preserve an updated log if interrupted; never invent missing runs.
            publish(args.output,records)
    publish(args.output,records)
    if manifest:cancel_task(name+"_"+str(args.runs-1))


def publish(output,records):
    times=[r["elapsed_ms"] for r in records if "elapsed_ms" in r]
    report={"records":records,"completed_measurements":len(times),"p50_ms":float(np.percentile(times,50)) if times else None,
            "p95_ms":float(np.percentile(times,95)) if times else None,"accuracy_verified":False,
            "completed_inference_runs":sum(r["status"]=="completed" for r in records),
            "note":"Temporary same-photo standards are not independent accuracy evidence. No production writes or external calls."}
    (output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    cards=[]
    for r in records:
        name=r["sample"];run=r.get("run")
        pictures=[(f"{name}/reference.png","临时标准（需核对）"),(f"{name}/source.jpg","完整实拍输入")]
        if run is not None:pictures += [(f"{name}/standard-overlay-{run}.png","标准结果／失败时仅原图"),(f"{name}/actual-overlay-{run}.png","实拍结果／失败时仅原图")]
        cards.append(f"<section><h2>{html.escape(name)} · {html.escape(r['status'])}</h2><p>{r.get('elapsed_ms','—')} ms</p>"+
                     "".join(f'<figure><a href="{path}"><img src="{path}"></a><figcaption>{label}</figcaption></figure>' for path,label in pictures)+
                     f"<pre>{html.escape(json.dumps(r.get('result',r.get('failure',{})),ensure_ascii=False,indent=2))}</pre></section>")
    (output/"index.html").write_text('<!doctype html><meta charset="utf-8"><title>整页标签核对测试日志</title><style>body{font:16px system-ui;margin:30px;background:#f1f5f9}section{background:white;padding:20px;margin:20px 0}figure{display:inline-block;vertical-align:top;width:44%}img{width:100%;max-height:500px;object-fit:contain}pre{white-space:pre-wrap}</style><h1>整页标签核对实验</h1><p>原图制作的临时标准，不代表独立准确性验收；未启用生产。</p>'+"".join(cards))


if __name__=="__main__":main()

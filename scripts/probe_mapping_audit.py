"""Explicit two-call A/B mapping probe using an owned saved OCR request.

Run with the existing service environment, never mutates business records.
An exclusive output folder is the non-replay claim for this experiment.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--owner',required=True); p.add_argument('--record',required=True)
    p.add_argument('--candidate-dir',required=True); p.add_argument('--output',required=True)
    p.add_argument('--allow-paid-calls',action='store_true')
    args=p.parse_args()
    if not args.allow_paid_calls: p.error('Explicit paid permission required')
    folder=Path(args.output); folder.mkdir(mode=0o700,exist_ok=False)
    sys.path.insert(0,os.getcwd())
    from local_inspection_service import server, qwen_evidence_jobs, standard_preparation
    from local_inspection_service.text_inspection.comparison_ports import ComparisonModels
    settings=qwen_evidence_jobs.settings(ComparisonModels(server.ai_detection_settings,
        server.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED,server.record_model_call),args.owner)
    record=server._text_v2_owned('records',args.record,args.owner)
    if not record: raise ValueError('owned_record_missing')
    # Import experimental modules in this process only, outside installed release.
    import local_inspection_service
    for name in ['model_call_audit','evidence_preview','qwen_evidence_jobs']:
        spec=importlib.util.spec_from_file_location('local_inspection_service.'+name,Path(args.candidate_dir)/(name+'.py'))
        module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module
        setattr(local_inspection_service,name,module); spec.loader.exec_module(module)
    candidate=local_inspection_service.qwen_evidence_jobs
    source=server._text_v2_read_verified(record['source_path'],args.owner,record['standard_id'],expected_sha256=record['source_sha256'])
    (folder/'original.bin').write_bytes(source)
    preview,preview_meta=local_inspection_service.evidence_preview.create(standard_preparation.decode(source))
    (folder/'preview.jpg').write_bytes(preview)
    request=record['diagnostics']['mapping_request']
    summaries=[]
    for name,structured in [('prompt_only',False),('json_object',True)]:
        attempt=folder/name; attempt.mkdir(mode=0o700)
        (attempt/'claim.json').write_text(json.dumps(dict(state='attempting',started_at=time.time(),structured=structured,source_record=args.record)))
        def audit(event,value):
            text=json.dumps(value,ensure_ascii=False)
            text=local_inspection_service.model_call_audit.redact(text,settings['api_key'])
            with (attempt/(event+'.json')).open('x') as output: output.write(text)
        started=time.monotonic()
        try:
            proposal,metadata=candidate.llm(settings,request,45,audit=audit,structured=structured,record_usage=server.record_model_call)
            summary=dict(state='parsed',metadata=metadata,proposal=proposal)
        except Exception as error:
            summary=dict(state='failed',error_type=type(error).__name__,error=str(error) if isinstance(error,ValueError) else 'unknown',
                diagnostics=getattr(error,'diagnostics',{}))
        summary.update(mode=name,elapsed_ms=round((time.monotonic()-started)*1000))
        audit('result',summary); summaries.append(summary)
    result=dict(record=args.record,ocr_reused=True,paid_calls=2,business_writes=0,
        original_bytes=len(source),preview=preview_meta,attempts=summaries)
    (folder/'summary.json').write_text(json.dumps(result,ensure_ascii=False))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__': main()

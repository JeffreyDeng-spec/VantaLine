"""Isolated document artwork commissioning with original/input/crop evidence.

Uses already converted DOCX for development; does NOT certify DOC conversion.
No production standard/media writes. Each output directory is a single immutable
round. --offline inventories media only; it cannot claim any automatic success.
"""
import argparse
import base64
import html
import io
import json
from pathlib import Path
import selectors
import shlex
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service import document_label_crop as crop
from local_inspection_service import document_label_source as source

BRIDGE = r'''
import os,sys,subprocess,json
pid=subprocess.check_output(['systemctl','show',SERVICE,'-p','MainPID','--value'],text=True).strip()
os.environ.update(dict(x.split('=',1) for x in open('/proc/'+pid+'/environ').read().split('\0') if '=' in x))
sys.path.insert(0,RELEASE)
from local_inspection_service import server
settings=server.ai_detection_settings()
assert settings.get('configured') and settings.get('provider')=='qwen'
assert server.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED
settings['single_attempt']=True
def emit(value): print('DOCIMPORT:'+json.dumps(value),flush=True)
emit({'model':settings['model'],'provider':'qwen'})
for number,line in enumerate(sys.stdin):
    if number>=500:break
    payload=json.loads(line)
    assert payload['model']==settings['model']
    request=server.urllib.request.Request(settings['base_url'],data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+settings['api_key'],'Content-Type':'application/json'},method='POST')
    try:
        with server.ai_urlopen(request,settings,timeout=60) as response:body=response.read(1048577)
        if len(body)>1048576:raise ValueError('response_limit')
        emit({'body':body.decode(errors='replace').replace(settings['api_key'],'<redacted>')})
    except Exception as exc: emit({'error_type':type(exc).__name__})
'''


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docx", action="append", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--ssh-host"); parser.add_argument("--ssh-key")
    parser.add_argument("--remote-python"); parser.add_argument("--release")
    parser.add_argument("--service", default="vantaline")
    args = parser.parse_args()
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    with (out / "round.json").open("x") as f:
        json.dump({"version": crop.VERSION, "offline": args.offline, "started_at": time.time(), "max_calls_per_image": 2,
                   "doc_converter_verified": False, "independent_holdout": False}, f)
    process = selector = None
    settings = {}
    if not args.offline:
        if not all((args.ssh_host, args.ssh_key, args.remote_python, args.release)):
            raise SystemExit("SSH connection arguments required")
        code = "SERVICE=" + repr(args.service) + "\nRELEASE=" + repr(args.release) + "\n" + BRIDGE
        encoded = base64.b64encode(code.encode()).decode()
        command = "sudo " + shlex.quote(args.remote_python) + " -u -c " + shlex.quote("import base64;exec(base64.b64decode(" + repr(encoded) + "))")
        process = subprocess.Popen(["ssh", "-i", args.ssh_key, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", args.ssh_host, command],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        selector = selectors.DefaultSelector(); selector.register(process.stdout, selectors.EVENT_READ)
        def receive():
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if not selector.select(max(0, deadline-time.monotonic())):
                    break
                line = process.stdout.readline()
                if not line:
                    raise RuntimeError("bridge_closed")
                if line.startswith("DOCIMPORT:"):
                    return json.loads(line[len("DOCIMPORT:"):])
            raise TimeoutError("bridge_outcome_unknown")
        settings = {**receive(), "api_key": "bridge-placeholder", "base_url": "https://bridge.invalid", "configured": True}
        def transport(request, _settings, timeout):
            process.stdin.write(request.data.decode() + "\n"); process.stdin.flush()
            value = receive()
            if "body" not in value:
                raise RuntimeError(value.get("error_type", "provider_failure"))
            return io.BytesIO(value["body"].encode())
        dump(out / "model.json", {"model": settings["model"], "provider": settings["provider"]})
    summaries = []
    try:
        for docindex, filename in enumerate(args.docx, 1):
            document = Path(filename).read_bytes()
            items = source.extract(document)
            if len(summaries) + len(items) > 250:
                raise ValueError("round_image_limit")
            for index, item in enumerate(items, 1):
                directory = out / f"doc{docindex}-image{index:03d}"; directory.mkdir()
                blob = item.pop("blob")
                (directory / "original.bin").write_bytes(blob)
                dump(directory / "source.json", {**item, "document_sha256": crop.digest(document)})
                result = {"id": directory.name, "status": "needs_confirmation", "reason": item["review_reason"],
                          "independent_visual_review": "pending", "actual_currency_charge": None, "calls": 0}
                started = time.monotonic()
                def invoke(stage, images):
                    with (directory / (stage + "-claim.json")).open("x") as f:
                        json.dump({"started_at": time.time(), "max_attempts": 1, "input_hashes": [crop.digest(v) for v in images]}, f)
                    result["calls"] += 1
                    value, diagnostic = crop.request_once(images, stage, item["references"], settings, transport)
                    dump(directory / (stage + "-output.json"), diagnostic)
                    if value is None:
                        raise ValueError("provider_result_unknown")
                    return value
                try:
                    if item["review_reason"]:
                        raise ValueError(item["review_reason"])
                    image = crop.decode(blob)
                    (directory / "source.png").write_bytes(crop.png(image))
                    preview, mapping = crop.preview(image)
                    (directory / "input.jpg").write_bytes(preview)
                    dump(directory / "mapping.json", mapping)
                    if args.offline:
                        result.update(status="not_tested", reason="offline inventory only")
                    else:
                        located = crop.classify(invoke("locate", [preview]))
                        result.update(located)
                        if located["classification"] == "non_label":
                            result["status"] = "excluded"
                        elif located["classification"] == "label_design":
                            pixels = crop.rectangle(located["box"], image.size)
                            cropped = image.crop(pixels)
                            data = crop.png(cropped); (directory / "crop.png").write_bytes(data)
                            assert crop.decode(data).tobytes() == cropped.tobytes()
                            result.update(pixel_box=list(pixels), source_pixels_equal=True)
                            model_crop, _ = crop.preview(cropped)
                            (directory / "crop-input.jpg").write_bytes(model_crop)
                            verified = invoke("verify", [preview, model_crop])
                            result["verification"] = verified
                            result["status"] = "model_accepted_unreviewed" if crop.verified(verified) else "needs_confirmation"
                except Exception as exc:
                    result["reason"] = str(exc)[:500] if isinstance(exc, ValueError) else type(exc).__name__
                result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
                dump(directory / "result.json", result)
                summaries.append(result)
                dump(out / "summary.json", summaries)
                print(json.dumps({k: result.get(k) for k in ("id", "status", "calls", "elapsed_ms")}), flush=True)
                cards = []
                for row in summaries:
                    base = out / row["id"]
                    pictures = "".join(f'<a href="{row["id"]}/{name}" target="_blank"><img src="{row["id"]}/{name}" alt="{name}"></a>' for name in ("input.jpg", "crop.png") if (base / name).exists())
                    cards.append(f'<article><h2>{row["id"]}: {html.escape(row["status"])}</h2>{pictures}<p>{html.escape(row.get("reason", ""))}</p><a href="{row["id"]}/result.json">Result JSON</a></article>')
                (out / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Document crop development evidence</title><style>body{font-family:system-ui;margin:24px}article{border-top:1px solid #ccc;padding:16px}img{max-width:45%;max-height:420px;object-fit:contain}</style><h1>Development evidence — not independent acceptance</h1><p>Original input and actual original-pixel crop. Model acceptance is not a human-reviewed accuracy result. DOC conversion uncommissioned.</p>' + "".join(cards))
    finally:
        if process:
            process.stdin.close(); selector.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()


if __name__ == "__main__":
    main()

"""Explicit paid deployment probe; no production orders/standards are created."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service import server
from local_inspection_service import document_label_classifier as classifier


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--owner', required=True)
    parser.add_argument('--image', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-paid-calls', action='store_true')
    args = parser.parse_args()
    if not args.allow_paid_calls or not 1 <= len(args.image) <= 3:
        parser.error('Explicit paid authorization and 1-3 images required')
    settings = server.document_import_jobs.settings(args.owner)
    args.output.mkdir(parents=True, exist_ok=False)
    summaries = []
    for index, path in enumerate(args.image, 1):
        blob = path.read_bytes()
        preview = classifier.prepare_image(blob)
        folder = args.output / str(index)
        folder.mkdir()
        (folder / 'original.bin').write_bytes(blob)
        (folder / 'input.jpg').write_bytes(preview)
        claim = dict(state='attempting', source_sha256=hashlib.sha256(blob).hexdigest(), model=settings['model'], prompt_version=classifier.VERSION)
        # An interrupted probe is evidence, never a reason to replay this directory.
        (folder / 'claim.json').write_text(json.dumps(claim))
        value, diagnostic = classifier.classify_once(preview, '', settings, server.ai_urlopen)
        (folder / 'result.json').write_text(json.dumps(dict(result=value, diagnostics=diagnostic), ensure_ascii=False, indent=2))
        summary = dict(image=index, **value, elapsed_ms=diagnostic['elapsed_ms'], usage=diagnostic.get('usage', {}))
        summaries.append(summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    (args.output / 'summary.json').write_text(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()

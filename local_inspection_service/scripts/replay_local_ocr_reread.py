"""Replay authorized frozen experiment outputs without API calls or data writes.

Usage: python -m local_inspection_service.scripts.replay_local_ocr_reread DATASET
Customer fixtures stay outside Git. This checks port parity, not independent accuracy.
"""
import copy
import io
import json
import pathlib
import sys

from PIL import Image
from local_inspection_service import local_ocr_reread as reread


def replay(root):
    cases = json.loads((root/'variant-manifest.json').read_text())['cases']
    patches = json.loads((root/'patch-full-manifest.json').read_text())['cases']
    lookup = {(p['parent_id'], p['source_evidence_id']): p for p in patches}
    caches = {}
    for prefix in ('patch', 'region'):
        caches[prefix] = {}
        for file in root.glob(prefix+'-full-*-results/results/*/result.json'):
            value = json.loads(file.read_text())
            caches[prefix][value['source_sha256']] = value
    differences, geometry, count = [], [], 0
    for case in cases:
        if case.get('unsupported'):
            continue
        original = json.loads((root/'optimized-results/results'/case['id']/'result.json').read_text())
        target = json.loads((root/'region-combined/results'/case['id']/'result.json').read_text())
        rows = copy.deepcopy(original.get('elements', []))
        request = original.get('mapping_request', {})
        with Image.open(root/'variants'/case['file']) as picture:
            regions = reread.select(picture.convert('RGB'), request, original.get('observations', []))
        for prefix, mode in [('patch','advanced_recognition'), ('region','text_recognition')]:
            for region in regions:
                if mode == 'text_recognition' and not reread.needs_text(region, request, rows):
                    continue
                frozen = lookup[case['id'], region['source_evidence_id']]
                plain = reread.text_region(region)
                with Image.open(root/'patch-inputs'/frozen['file']) as expected, Image.open(io.BytesIO(plain['blob'])) as actual:
                    if expected.convert('RGB').tobytes() != actual.convert('RGB').tobytes() or region['source_box'] != frozen['source_box']:
                        geometry.append(case['id'])
                result = caches[prefix].get(frozen['sha256'], {})
                if result.get('status') == 'completed':
                    rows, _ = reread.merge(rows, case['elements'], result['observations'],
                        plain if mode == 'text_recognition' else region, mode, frozen['id']+prefix)
        actual_states = {r['element_id']: r['state'] == 'matched' for r in rows}
        target_states = {r['element_id']: r['state'] == 'matched' for r in target.get('elements', [])}
        if actual_states != target_states:
            differences.append(dict(case=case['id'], actual=actual_states, frozen=target_states))
        count += 1
    report = dict(cases=count, geometry_mismatches=geometry, state_differences=differences, paid_calls=0,
                  scope='frozen synthetic port parity, not independent accuracy or latency')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return not geometry and not differences


if __name__ == '__main__':
    raise SystemExit(0 if replay(pathlib.Path(sys.argv[1])) else 1)

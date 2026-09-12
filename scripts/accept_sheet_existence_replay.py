"""Replay saved real OCR, with explicitly synthetic negative/duplicate mutations.

No paid calls or production writes. This tests matching, not independent OCR accuracy.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from local_inspection_service import qwen_ocr_evidence as ocr, evidence_matching as matching


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    source, output = Path(args.evidence), Path(args.output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    image = Image.open(source / 'input.png')
    raw = json.loads((source / 'result.json').read_text())
    observations = ocr.normalize(raw['response'], image.size)
    image.save(output / 'input.png')
    Image.open(source / 'ocr-boxes.png').save(output / 'ocr-boxes.png')
    mutated = copy.deepcopy(observations)
    correct = next(o for o in observations if matching.token_spans('20V', o['text']))
    wrong = {**correct, 'id': 'synthetic-wrong-repeat', 'text': correct['text'].replace('20V', '120V'),
             'box': [.01,.01,.5,.05], 'polygon': [[.01,.01],[.5,.01],[.5,.05],[.01,.05]]}
    mutated.append(wrong)
    cases = [('real_positive', ['20V', '2000mAh', 'Made in China'], observations, [True]*3),
             ('synthetic_conflicting_repeat', ['20V'], mutated, [True]),
             ('synthetic_conflicting_repeat_reversed', ['20V'], list(reversed(mutated)), [True]),
             ('wrong_standard_negative', ['120V', 'MODEL: PPLBP-2020', 'made in china'], observations, [False]*3),
             ('synthetic_all_wrong', ['20V'], [wrong], [False])]
    report = dict(policy=matching.VERSION, scope='matching_replay_not_independent_ocr_acceptance',
                  source_size=image.size, observation_count=len(observations), cases=[])
    for name, expected, evidence, decisions in cases:
        elements = [dict(id='e'+str(i),type='text',text=text,state='keep',clean_box=[.02,.1+i*.25,.96,.18])
                    for i,text in enumerate(expected)]
        rows = matching.direct(elements, evidence)
        actual = [r['state']=='matched' for r in rows]
        assert actual == decisions, (name, actual, decisions)
        preview = Image.new('RGB', (800, max(160, len(rows)*90)), 'white')
        draw = ImageDraw.Draw(preview)
        for i,row in enumerate(rows):
            color = 'green' if row['state']=='matched' else 'orange'
            draw.rectangle((8, i*90+8,790,i*90+80), outline=color,width=3)
            draw.text((20,i*90+22),row['expected'],fill='black')
            draw.text((20,i*90+44),row['state']+' | '+row['reason'],fill=color)
        preview.save(output/(name+'.png'))
        report['cases'].append(dict(name=name,passed=True,elements=rows,image=name+'.png',
            observations=evidence,template=elements))
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    (output/'report.md').write_text('# Sheet presence regression\n\n'
        'Saved real OCR replay; temporary text templates and synthetic mutations are NOT production standards or independent OCR acceptance.\n\n'
        '![Actual OCR boxes](ocr-boxes.png)\n\n'+ '\n\n'.join(
        '## '+c['name']+' — PASS\n\n![Result]('+c['image']+')' for c in report['cases']))
    print(json.dumps(dict(passed=len(cases),observations=len(observations),output=str(output))))


if __name__ == '__main__':
    main()

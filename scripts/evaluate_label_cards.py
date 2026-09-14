#!/usr/bin/env python3
"""Score private labelled card exports without mixing real and synthetic samples.

Input JSON: {"cases": [{"id": "...", "kind": "real_photo|source_mutation|synthetic",
"expected": {"color": "difference", "text": "match"}, "report": {...task export...}}]}.
Only explicitly annotated dimensions are scored. Pending, uncertain and inapplicable
outcomes are reported separately; none count as verified correct negatives.
"""
import argparse
import json
from pathlib import Path

DIMENSIONS = {'text','typography','color','graphics','completeness','orientation','shape','layout','codes','print'}
KINDS = {'real_photo','source_mutation','synthetic'}


def evaluate(cases):
    groups = {}
    for case in cases:
        if case['kind'] not in KINDS or not case['expected'] or set(case['expected']) - DIMENSIONS:
            raise ValueError('Invalid sample kind/dimensions')
        report = case['report']
        group = groups.setdefault(case['kind'], {'samples':0,'completed':0,'seconds':[], 'dimensions':{}})
        group['samples'] += 1
        group['completed'] += report.get('status') == 'completed'
        if report.get('finished_at') and report.get('started_at'):
            group['seconds'].append(report['finished_at']-report['started_at'])
        checks = report.get('checks', [])
        if isinstance(checks, dict):checks=list(checks.values())
        for dimension, expected in case['expected'].items():
            if expected not in {'match','difference','uncertain'}:
                raise ValueError('Invalid expected outcome')
            m = group['dimensions'].setdefault(dimension, {'annotated':0,'true_positive':0,'true_negative':0,'false_positive':0,'false_negative':0,'uncertain':0,'uninspected':0,'not_applicable':0,'expected_uncertain':0})
            m['annotated'] += 1
            states={c['status'] for c in checks if c['dimension']==dimension}
            observed = ('difference' if 'difference' in states else 'pending' if not states or states & {'pending','running'} else 'uncertain' if 'uncertain' in states else 'match' if 'match' in states else 'not_applicable')
            if observed == 'pending':m['uninspected'] += 1
            elif observed == 'uncertain':m['uncertain'] += 1
            elif observed == 'not_applicable':m['not_applicable'] += 1
            if expected == 'uncertain':m['expected_uncertain'] += 1
            elif observed in {'difference','match'}:
                m[{('difference','difference'):'true_positive', ('match','match'):'true_negative', ('match','difference'):'false_positive', ('difference','match'):'false_negative'}[expected,observed]] += 1
    for group in groups.values():
        seconds=group.pop('seconds')
        group['mean_seconds']=sum(seconds)/len(seconds) if seconds else None
        for m in group['dimensions'].values():
            positives=m['true_positive']+m['false_positive']
            verified_expected_positive=m['true_positive']+m['false_negative']
            m['precision_on_decided']=m['true_positive']/positives if positives else None
            m['recall_on_decided']=m['true_positive']/verified_expected_positive if verified_expected_positive else None
            m['uncertainty_rate']=m['uncertain']/m['annotated']
    return groups


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    args=parser.parse_args()
    print(json.dumps(evaluate(json.loads(args.input.read_text())['cases']),ensure_ascii=False,indent=2))

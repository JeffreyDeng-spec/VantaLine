#!/usr/bin/env python3
"""Evaluate private batch exports, separating real_photo/source_mutation/synthetic.

Input: {"batches":[{"kind":"source_mutation","report":{...raw task...},
"expected":{"label_id":{"asset_id":"ast_id","dimensions":{"color":"difference"}}}}]}.
Every uploaded actual must be annotated. Matching accuracy is over all actuals,
with undecided matches counted separately, never credited as correct. Dimensions
use the existing evaluator and include pending/uncertain outcomes.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.codex_compare.batch_contracts import card, label_status
from scripts.evaluate_label_cards import evaluate, KINDS


def evaluate_batches(batches):
    groups={};cases=[]
    for case in batches:
        kind=case['kind'];task=case['report'];expected=case['expected']
        if kind not in KINDS or set(expected)!=set(task['labels']):
            raise ValueError('Annotate every actual label and provide a valid sample kind')
        g=groups.setdefault(kind,{'batches':0,'labels':0,'matched_correct':0,'matched_wrong':0,'matching_unresolved':0,'fully_checked_labels':0,'seconds':[]})
        g['batches']+=1
        if task.get('finished_at') and task.get('started_at'):g['seconds'].append(task['finished_at']-task['started_at'])
        for lid,e in task['labels'].items():
            g['labels']+=1
            match=e['match'];ref=task['references'].get(match.get('reference_id'),{})
            if match['status']!='matched':g['matching_unresolved']+=1
            elif ref.get('asset_id')==expected[lid]['asset_id']:g['matched_correct']+=1
            else:g['matched_wrong']+=1
            report=card(task,lid)
            from local_inspection_service.codex_compare.label_contracts import validate
            try:
                validate(report)
                checked=match['status']=='matched'
            except ValueError:checked=False
            g['fully_checked_labels']+=checked
            cases.append({'kind':kind,'expected':expected[lid]['dimensions'],'report':report})
    dimensions=evaluate(cases)
    for kind,g in groups.items():
        elapsed=g.pop('seconds');g['mean_batch_seconds']=sum(elapsed)/len(elapsed) if elapsed else None
        g['matching_accuracy_all_actuals']=g['matched_correct']/g['labels'] if g['labels'] else None
        g['matching_confirmation_rate']=g['matching_unresolved']/g['labels'] if g['labels'] else None
        g['fully_checked_fraction']=g['fully_checked_labels']/g['labels'] if g['labels'] else None
        g['dimensions']=dimensions.get(kind,{}).get('dimensions',{})
    return groups


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);a=p.parse_args()
    print(json.dumps(evaluate_batches(json.loads(a.input.read_text())['batches']),ensure_ascii=False,indent=2))

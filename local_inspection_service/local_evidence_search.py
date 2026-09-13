"""Bounded exact multi-box search over immutable OCR evidence, without a model.

Only existing characters can satisfy a template. The existing strict validator
rechecks every proposed path; geometry guards additionally reject skipped boxes.
"""
import copy
import re

from . import evidence_matching as matching

VERSION = "local-exact-paths-v1"
MAX_OPERATIONS = 100_000
MAX_PATHS = 128
MAX_PIECES = 8


def bounds(row):
    if row.get("polygon"):
        x, y = zip(*row["polygon"])
        return min(x), min(y), max(x), max(y)
    return row["box"]


def same_line(a, b):
    return min(a[3],b[3])-max(a[1],b[1]) >= .5*min(a[3]-a[1],b[3]-b[1])


def unobstructed(a, b, others):
    """Do not skip an OCR box such as NOT between otherwise adjacent pieces."""
    aa, bb = bounds(a), bounds(b)
    for other in others:
        if other['id'] in (a['id'],b['id']):
            continue
        cc=bounds(other)
        if same_line(aa,bb):
            if same_line(aa,cc) and aa[2] <= (cc[0]+cc[2])/2 <= bb[0]:
                return False
        else:
            # A wrapped line cannot jump over remaining words on either line.
            height=max(aa[3]-aa[1],bb[3]-bb[1],cc[3]-cc[1])
            if same_line(aa,cc) and 0 <= cc[0]-aa[2] <= 2*height:
                return False
            if same_line(bb,cc) and 0 <= bb[0]-cc[2] <= 2*height:
                return False
            if aa[3] <= (cc[1]+cc[3])/2 <= bb[1] and min(aa[2],bb[2],cc[2]) > max(aa[0],bb[0],cc[0]):
                return False
    return True


def complete(rows, observations):
    """Update exact matches only; preserve conflicts and expose bounded search."""
    text_rows=[o for o in observations if o.get('type')=='text' and o.get('text')
               and (o.get('polygon') or o.get('box'))]
    identities=[o['id'] for o in text_rows]
    if len(set(identities)) != len(identities):
        return rows, dict(version=VERSION,reason='duplicate_evidence_ids',operations=0,matched=[])
    operations=0;found=[];limited=[]
    for row in rows:
        if row['state']!='review' or row.get('type')!='text' or not row['expected'].strip():
            continue
        expected=matching.normalized(row['expected'])
        first=re.search(r'\w+|[^\w\s]', expected)
        if first is None:continue
        queue=[]
        for observation in text_rows:
            operations+=1
            if operations>MAX_OPERATIONS:break
            for start,_ in matching.token_spans(first.group(),observation['text']):
                value=matching.normalized(observation['text'][start:])
                if value and len(value)<len(expected) and expected.startswith(value):
                    queue.append(([matching.span(observation,start,len(observation['text']))],
                                  [observation['text'][start:]], observation))
                    if len(queue)>=MAX_PATHS:break
            if len(queue)>=MAX_PATHS:break
        paths=0
        while queue and operations<=MAX_OPERATIONS and paths<MAX_PATHS and row['state']=='review':
            pieces,texts,previous=queue.pop(0);paths+=1
            if len(pieces)>=MAX_PIECES:continue
            used={p['evidence_id'] for p in pieces}
            for candidate in text_rows:
                operations+=1
                if operations>MAX_OPERATIONS:break
                if candidate['id'] in used or not matching.adjacent(previous,candidate):continue
                # Account for the bounded full evidence scan in obstruction checks.
                operations+=len(text_rows)
                if operations>MAX_OPERATIONS:break
                if not unobstructed(previous,candidate,text_rows):continue
                text=candidate['text']
                ends=[m.end() for m in re.finditer(r'\S+(?:\s+|$)',text)]
                for end in ends:
                    operations+=1
                    if operations>MAX_OPERATIONS:break
                    value=matching.normalized(' '.join([*texts,text[:end]]))
                    proposed=[*pieces,matching.span(candidate,0,end)]
                    if value==expected:
                        draft=copy.deepcopy(row)
                        request=dict(elements=[dict(element_id=row['element_id'],evidence_ids=identities)],evidence=text_rows)
                        try:matching.validate(dict(mappings=[dict(element_id=row['element_id'],spans=proposed)]),request,[draft])
                        except (ValueError,TypeError,KeyError):continue
                        if draft['state']=='matched':
                            row.update(draft,reason='deterministic_local_characters')
                            found.append(row['element_id']);break
                    elif end==len(text) and value and expected.startswith(value) and len(queue)+paths<MAX_PATHS:
                        queue.append((proposed,[*texts,text],candidate))
                if row['state']=='matched':break
        if row['state']=='review' and (operations>MAX_OPERATIONS or queue or paths>=MAX_PATHS):
            limited.append(row['element_id'])
    return rows, dict(version=VERSION,operations=operations,matched=found,limited_element_ids=limited)

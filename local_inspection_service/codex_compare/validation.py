"""Shared bounded report value validation, independent of version dispatch."""
import math

DECISIONS = {'MATCH', 'DIFFERENCES', 'REVIEW_REQUIRED'}


def text(value, limit=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'Expected nonempty text, maximum {limit} characters')
    return value


def box(value):
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 4 or any(type(x) not in (float, int) or not math.isfinite(x) for x in value):
        raise ValueError('Box must be normalized [x,y,width,height]')
    x, y, w, h = value
    if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1 or y + h > 1:
        raise ValueError('Box lies outside the original image')
    return value


def summary(value):
    if set(value) != {'decision', 'message', 'checked_scope', 'unchecked_scope'}:
        raise ValueError('Summary needs decision, message, checked_scope, unchecked_scope')
    if value['decision'] not in DECISIONS:
        raise ValueError('Invalid decision')
    result = {k: text(value[k]) for k in ('message', 'checked_scope')}
    if not isinstance(value['unchecked_scope'], str) or len(value['unchecked_scope']) > 4000:
        raise ValueError('Invalid unchecked_scope')
    return {**result, 'decision': value['decision'], 'unchecked_scope': value['unchecked_scope']}

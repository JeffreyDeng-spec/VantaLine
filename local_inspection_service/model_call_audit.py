"""Private evidence files, not application logs or repeated polling payloads."""
import hashlib
import json
import re
import time


def redact(text, secret):
    if secret:
        text = text.replace(secret, '[REDACTED]')
    return re.sub(r'data:image/[^;\s]+;base64,[A-Za-z0-9+/=]+', '[IMAGE_REDACTED]', text)


def recorder(s, record, name, save, secret):
    """Register links before network I/O; write each event once with source hash."""
    entry = dict(name=name, started_at=time.time(), state='attempting', files={})
    record['diagnostics'].setdefault('model_audits', []).append(entry)
    save(record['diagnostics']['phase'])

    def emit(event, value):
        if event in entry['files']:
            raise ValueError('audit_event_already_written')
        text = value if isinstance(value, str) else ('' if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False))
        data = value if isinstance(value, bytes) else redact(text, secret).encode('utf-8')
        kind = 'audit-' + name + '-' + event
        path = s._text_v2_media_path(record['owner_user_id'], record['standard_id'], record['id']+'-'+kind+('.bin' if isinstance(value, bytes) else '.json'))
        s._text_v2_write(path, data)
        entry['files'][event] = dict(path=str(path), sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
            kind=kind, url=f"/api/text-inspection/prepared-comparisons/{record['id']}/media/{kind}")
        entry['state'] = event
        entry['updated_at'] = time.time()
        save(record['diagnostics']['phase'])
    return emit

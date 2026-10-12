"""Read-only owner-scoped account evidence. Never acquire/settle a PLC lease."""
import base64
import json
import time
from fastapi import HTTPException
from ..storage.postgres_runtime_repository import _decode_value, quote_ident

BUSINESS = {
    'text_inspection_standards': ('id', 'created_at'),
    'text_inspection_records': ('id', 'created_at'),
    'incoming_text_inspections': ('id', 'created_at'),
    'data_analysis_records': ('record_id', 'created_at'),
    'label_inspection_objects': ('id', 'created_at'),
    'codex_comparison_tasks': ('id', 'created_at'),
}
CATEGORIES = tuple(BUSINESS) + ('connections', 'stations', 'diagnostics', 'plc_executions')
SAFE = ('name', 'title', 'display_name', 'status', 'decision', 'auto_decision',
        'final_decision', 'passed', 'task_id', 'standard_id', 'kind', 'model_id',
        'outcome', 'updated_at', 'config_generation', 'lease_epoch', 'bundle_version')


def project(raw):
    return {k: raw[k] for k in SAFE if k in raw and isinstance(raw[k], (str, int, float, bool, type(None)))}


def records_page(repo, owner, category, cursor=None, limit=24):
    if category not in CATEGORIES:
        raise HTTPException(422, '未知记录分类')
    after = None
    if cursor:
        try:
            value = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
            if value['scope'] != [owner, category] or type(value['time']) is not int or not isinstance(value['id'], str):
                raise ValueError()
            after = (value['time'], value['id'])
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise HTTPException(422, '分页游标无效，请刷新列表') from None
    q = repo._qualified_table
    diagnostics_table = f'{quote_ident(repo.schema_name)}."plc_diagnostic_events"'
    params = [owner]
    if category in BUSINESS:
        identifier, clock = BUSINESS[category]
        source = f"SELECT {identifier} AS id, {clock} AS sort_time, raw_json FROM {q(category)} WHERE owner_user_id=%s"
    elif category == 'connections':
        source = f"SELECT l.station_id AS id, 0::bigint AS sort_time, (to_jsonb(l) - 'raw_json') || jsonb_build_object('name',s.name) AS raw_json FROM {q('plc_workstation_leases')} l LEFT JOIN {q('plc_workstations')} s ON s.id=l.station_id WHERE l.owner_user_id=%s"
    elif category == 'stations':
        source = f"""SELECT s.id, s.created_at AS sort_time,
            jsonb_build_object('name',s.name,'status',s.status,'config_generation',s.config_generation,
                'registered_by_target',s.created_by_user_id=%s) AS raw_json
            FROM {q('plc_workstations')} s WHERE s.created_by_user_id=%s OR EXISTS
            (SELECT 1 FROM {q('plc_workstation_leases')} l WHERE l.station_id=s.id AND l.owner_user_id=%s) OR EXISTS
            (SELECT 1 FROM {q('plc_web_serial_dispatches')} d WHERE d.station_id=s.id AND d.raw_json->>'owner_user_id'=%s)"""
        params = [owner, owner, owner, owner]
    elif category == 'diagnostics':
        source = f"SELECT event_id AS id, received_at AS sort_time, payload_json || jsonb_build_object('station_id',station_id,'step',step,'result',result,'code',code) AS raw_json FROM {diagnostics_table} WHERE owner_user_id=%s"
    else:
        source = f"""SELECT d.id, d.created_at AS sort_time,
            d.raw_json || jsonb_build_object('status',d.status,'passed',d.passed,'station_id',d.station_id,
                'ownership_basis',CASE WHEN d.raw_json->>'owner_user_id'=%s THEN 'saved_owner' ELSE 'matching_lease' END) AS raw_json
            FROM {q('plc_web_serial_dispatches')} d WHERE d.raw_json->>'owner_user_id'=%s OR
            (COALESCE(d.raw_json->>'owner_user_id','')='' AND EXISTS
                (SELECT 1 FROM {q('plc_workstation_leases')} l WHERE l.owner_user_id=%s
                AND l.station_id=d.station_id AND l.session_id=d.session_id AND l.lease_epoch=d.lease_epoch))"""
        params = [owner, owner, owner]
    c = repo._cursor()
    try:
        if category == 'diagnostics':
            c.execute('SELECT to_regclass(%s) AS present', (diagnostics_table,))
            if repo._row_to_dict(c, c.fetchone())['present'] is None:
                return {'items': [], 'total': 0, 'next_cursor': None, 'available': False}
        c.execute(f'SELECT count(*) AS total FROM ({source}) evidence', params)
        total = int(repo._row_to_dict(c, c.fetchone())['total'])
        where = 'WHERE (sort_time,id)<(%s,%s)' if after else ''
        c.execute(f'SELECT * FROM ({source}) evidence {where} ORDER BY sort_time DESC,id DESC LIMIT %s',
                  params + (list(after) if after else []) + [limit + 1])
        rows = [repo._row_to_dict(c, row) for row in c.fetchall()]
        items = []
        for row in rows[:limit]:
            stored = _decode_value('raw_json', row['raw_json'])
            raw = stored if isinstance(stored, dict) else {}
            item = project(raw)
            item.update(id=row['id'], created_at=int(row['sort_time']))
            if not isinstance(stored, dict):
                item['metadata_available'] = False
            if category in ('connections', 'stations', 'diagnostics', 'plc_executions'):
                for key in ('station_id', 'state', 'heartbeat_at', 'expires_at', 'step', 'result', 'code',
                            'target', 'duration_ms', 'expected_bytes', 'actual_bytes', 'ownership_basis', 'registered_by_target'):
                    if key in raw and isinstance(raw[key], (str, int, float, bool, type(None))):
                        item[key] = raw[key]
            if category == 'connections':
                item['station_id'] = row['id']
                item['status'] = raw.get('state', 'unknown') if int(raw.get('expires_at') or 0) > int(time.time()) else 'expired'
                item.pop('created_at', None)
            if category == 'diagnostics':
                item['created_at'] = int(row['sort_time']) / 1000
            if category == 'plc_executions' and raw.get('status') == 'detecting':
                item['passed'] = None
            items.append(item)
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit-1]
            next_cursor = base64.urlsafe_b64encode(json.dumps({'scope': [owner, category], 'time': int(last['sort_time']), 'id': last['id']}).encode()).decode().rstrip('=')
        return {'items': items, 'total': total, 'next_cursor': next_cursor, 'available': True}
    finally:
        c.close()
        repo._end_read_transaction()

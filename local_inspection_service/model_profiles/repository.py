"""Versioned model profiles: append-only versions and atomic binding revisions."""
import copy
import json
import time
import uuid
from contextlib import contextmanager


class Conflict(ValueError):
    pass


class Repository:
    def __init__(self, runtime):
        self.runtime = runtime
        self.table = runtime._qualified_table('model_profile_objects')

    @contextmanager
    def transaction(self):
        cursor = self.runtime._cursor()
        try:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended('model-profiles-v1',0))")
            yield cursor
            self.runtime.connection.commit()
        except Exception:
            self.runtime.connection.rollback()
            raise
        finally:
            cursor.close()

    def get(self, cursor, identity):
        cursor.execute(f'SELECT raw_json FROM {self.table} WHERE id=%s', (identity,))
        row = cursor.fetchone()
        if row is None:
            return None
        value = self.runtime._row_to_dict(cursor, row)['raw_json']
        return json.loads(value) if isinstance(value, str) else value

    def put(self, cursor, identity, kind, value, *, replace=False):
        sql = f'INSERT INTO {self.table}(id,kind,created_at,raw_json) VALUES (%s,%s,%s,%s::jsonb)'
        if replace:
            sql += ' ON CONFLICT(id) DO UPDATE SET raw_json=EXCLUDED.raw_json'
        cursor.execute(sql, (identity, kind, int(time.time()), json.dumps(value, ensure_ascii=False)))

    def event(self, cursor, actor, action, detail):
        self.put(cursor, uuid.uuid4().hex, 'audit', dict(actor=actor, action=action, detail=detail, at=time.time()))

    def state(self, cursor):
        return self.get(cursor, 'state')

    def versions(self, cursor, state):
        return [self.get(cursor, f'{identity}:{version}') for identity, version in state['heads'].items()]

    def save_bindings(self, expected, bindings, actor, validate):
        with self.transaction() as c:
            state = self.state(c)
            if state['revision'] != expected:
                raise Conflict('设置已被其他管理员修改，请刷新后重试')
            for purpose, identity in bindings.items():
                profile = self.get(c, f"{identity}:{state['heads'].get(identity, 0)}") if identity else None
                if purpose not in state['bindings'] or state['bindings'][purpose] != identity:
                    validate(purpose, profile)
            state = copy.deepcopy(state)
            state['bindings'].update(bindings)
            state['revision'] += 1
            self.put(c, 'state', 'state', state, replace=True)
            self.event(c, actor, 'bindings', dict(revision=state['revision'], bindings=bindings))
            return state

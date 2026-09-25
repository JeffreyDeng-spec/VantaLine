"""PostgreSQL-only queue and append-only report revisions; account locks match Agent primitives."""
from __future__ import annotations
import secrets
import time
import uuid
from contextlib import contextmanager
from ..codex_compare.contracts import TERMINAL, digest, encode, item, summary, validate_report
from .agent_operations import OperationConflict, OperationDenied

TASKS = 'codex_comparison_tasks'
EVENTS = 'codex_comparison_events'


class CodexComparisonsRepository:
    def __init__(self, repository):
        self.repository = repository

    def table(self, name):
        return self.repository._qualified_table(name)

    @contextmanager
    def tx(self):
        cursor = self.repository._cursor()
        try:
            # Small beta: serialize global admission/claim/writes, across processes.
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended('codex-comparison-v1',0))")
            yield cursor
            self.repository.connection.commit()
        except Exception:
            self.repository.connection.rollback()
            raise
        finally:
            cursor.close()

    @contextmanager
    def read_tx(self):
        cursor = self.repository._cursor()
        try:
            yield cursor
            self.repository.connection.commit()
        except Exception:
            self.repository.connection.rollback()
            raise
        finally:
            cursor.close()

    def rows(self, c):
        return [self.repository._row_to_dict(c, row)['raw_json'] for row in c.fetchall()]

    def read(self, c, owner, identifier):
        c.execute(f'SELECT raw_json FROM {self.table(TASKS)} WHERE owner_user_id=%s AND id=%s', (owner, identifier))
        rows = self.rows(c)
        return rows[0] if rows else None

    def save(self, c, task):
        task['updated_at'] = time.time()
        c.execute(f'''INSERT INTO {self.table(TASKS)} (id,owner_user_id,created_at,updated_at,status,idempotency_key,raw_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT(id) DO UPDATE
            SET updated_at=EXCLUDED.updated_at,status=EXCLUDED.status,raw_json=EXCLUDED.raw_json''',
            (task['id'], task['owner_user_id'], int(task['created_at']), int(task['updated_at']), task['status'], task['idempotency_key'], encode(task)))

    def event(self, c, task, kind, payload, key=None):
        task['sequence'] += 1
        value = {'sequence': task['sequence'], 'kind': kind, 'payload': payload, 'created_at': time.time()}
        c.execute(f'''INSERT INTO {self.table(EVENTS)} (id,owner_user_id,task_id,sequence,idempotency_key,created_at,raw_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)''',
            (uuid.uuid4().hex, task['owner_user_id'], task['id'], task['sequence'], key or uuid.uuid4().hex, int(time.time()), encode(value)))

    def get(self, owner, identifier):
        with self.tx() as c:
            return self.read(c, owner, identifier)

    def list(self, owner, before='', limit=30):
        with self.read_tx() as c:
            c.execute(f'SELECT raw_json FROM {self.table(TASKS)} WHERE owner_user_id=%s AND (%s=\'\' OR id<%s) ORDER BY id DESC LIMIT %s', (owner, before, before, limit))
            return self.rows(c)

    def events(self, owner, identifier, after):
        with self.read_tx() as c:
            c.execute(f'SELECT raw_json FROM {self.table(EVENTS)} WHERE owner_user_id=%s AND task_id=%s AND sequence>%s ORDER BY sequence LIMIT 100', (owner, identifier, after))
            return self.rows(c)

    def create(self, owner, key, inputs, *, parent_id=None, report_version=None):
        if report_version not in (None, 'label-v2', 'label-batch-v3'):
            raise ValueError('Unsupported report version')
        fingerprint = digest({'inputs': inputs, 'parent_id': parent_id, **({'report_version': report_version} if report_version else {})})
        with self.tx() as c:
            c.execute(f'SELECT raw_json FROM {self.table(TASKS)} WHERE owner_user_id=%s AND idempotency_key=%s', (owner, key))
            existing = self.rows(c)
            if existing:
                if existing[0]['fingerprint'] != fingerprint:
                    raise OperationConflict('提交标识已用于其他输入')
                return existing[0]
            task = {'id': f'cc_{time.time_ns():020d}_{uuid.uuid4().hex[:12]}', 'owner_user_id': owner,
                    'idempotency_key': key, 'fingerprint': fingerprint, 'inputs': inputs, 'parent_id': parent_id,
                    'status': 'queued', 'created_at': time.time(), 'sequence': 0, 'items': {}, 'artifacts': {},
                    'summary': None, 'reviews': [], 'finalized': False}
            if report_version == 'label-v2':
                task.update(report_version=report_version, elements={}, checks={}, issues={}, decodes={})
            if report_version == 'label-batch-v3':
                from ..codex_compare.batch_contracts import new_label
                task.update(report_version=report_version, status='draft', references=inputs.get('regions', {}).copy(),
                            labels={lid: new_label(lid, a['media'], a['name']) for lid, a in inputs.get('actuals', {}).items()})
                for lid, match in inputs.get('human_matches', {}).items():
                    task['labels'][lid].update(match=match, human_match=True)
            self.event(c, task, task['status'], {})
            self.save(c, task)
            return task

    def claim(self, owners, model, runner_version):
        with self.tx() as c:
            # One global active attempt. Never lease-requeue an uncertain session.
            c.execute(f"SELECT raw_json FROM {self.table(TASKS)} WHERE status IN ('running','cancel_requested')")
            if self.rows(c):
                return None
            c.execute(f"SELECT raw_json FROM {self.table(TASKS)} WHERE status='queued' AND owner_user_id=ANY(%s) ORDER BY id LIMIT 1", (list(owners),))
            rows = self.rows(c)
            if not rows:
                return None
            task = rows[0]
            token = secrets.token_urlsafe(32)
            task.update(status='running', attempt_id=uuid.uuid4().hex, token_hash=digest(token.encode()),
                        started_at=time.time(), deadline=time.time() + 600, heartbeat=time.time(),
                        model=model, reasoning_effort='high', runner_version=runner_version)
            self.event(c, task, 'running', {})
            self.save(c, task)
            return task, token

    def recover(self):
        with self.tx() as c:
            c.execute(f"SELECT raw_json FROM {self.table(TASKS)} WHERE status IN ('running','cancel_requested')")
            for task in self.rows(c):
                if time.time() - task.get('heartbeat', 0) > 30:
                    task.update(status='interrupted', error='Worker 心跳中断；保留部分报告，不自动重跑。', token_hash='')
                    self.event(c, task, 'interrupted', {})
                    self.save(c, task)

    def pulse(self, owner, identifier, attempt, metadata=None):
        with self.tx() as c:
            task = self.read(c, owner, identifier)
            if not task or task.get('attempt_id') != attempt or task['status'] in TERMINAL:
                return None
            task['heartbeat'] = time.time()
            if metadata:
                task.update({k: v for k, v in metadata.items() if k in {'session_id', 'usage', 'skill_version', 'skill_sha256', 'tool_version'}})
            self.save(c, task)
            return task

    def cancel(self, owner, identifier):
        with self.tx() as c:
            task = self.read(c, owner, identifier)
            if not task:
                raise KeyError(identifier)
            if task['status'] not in TERMINAL:
                task['status'] = 'cancelled' if task['status'] in {'queued', 'draft'} else 'cancel_requested'
                task['token_hash'] = ''
                self.event(c, task, task['status'], {})
                self.save(c, task)
            return task

    def write_report(self, owner, identifier, attempt, token, key, kind, payload):
        with self.tx() as c:
            task = self.read(c, owner, identifier)
            if (not task or task['status'] != 'running' or task.get('attempt_id') != attempt
                or time.time() >= task.get('deadline', 0) or not secrets.compare_digest(task.get('token_hash', ''), digest(token.encode()))):
                raise OperationDenied('Task credential expired or revoked')
            fingerprint = digest({'kind': kind, 'payload': payload})
            c.execute(f'SELECT raw_json FROM {self.table(EVENTS)} WHERE task_id=%s AND idempotency_key=%s', (identifier, key))
            previous = self.rows(c)
            if previous:
                if previous[0]['payload'].get('fingerprint') != fingerprint:
                    raise OperationConflict('Write key reused with different content')
                return {'sequence': previous[0]['sequence']}
            if task['finalized']:
                raise OperationConflict('Report already finalized')
            if task['sequence'] >= (20000 if task.get('report_version') == 'label-batch-v3' else 2000):
                raise ValueError('Report event limit reached')
            if task.get('report_version') == 'label-batch-v3':
                from ..codex_compare.batch_contracts import apply
                payload = apply(task, kind, payload)
            elif kind == 'progress':
                from ..codex_compare.contracts import text
                payload = {'message': text(payload.get('message'), 1000)}
            elif kind in {'element', 'checklist', 'check', 'issue'}:
                from ..codex_compare.label_contracts import apply
                payload = apply(task, kind, payload)
            elif kind == 'decode':
                if task.get('report_version') != 'label-v2' or len(task['decodes']) >= 200:
                    raise ValueError('Invalid decode operation or limit reached')
                task['decodes'][payload['id']] = payload
            elif kind == 'item':
                if task.get('report_version') == 'label-v2':
                    raise ValueError('Use checklist/check on label-v2 cards')
                payload = item(payload)
                if len(task['items']) >= 500 and payload['id'] not in task['items']:
                    raise ValueError('At most 500 items')
                if any(x not in task['artifacts'] for x in payload['artifact_ids']):
                    raise ValueError('Unknown evidence attachment')
                task['items'][payload['id']] = payload
            elif kind == 'summary':
                task['summary'] = summary(payload)
                payload = task['summary']
            elif kind == 'artifact':
                if len(task['artifacts']) >= 200:
                    raise ValueError('At most 200 evidence images')
                task['artifacts'][payload['id']] = payload
            elif kind == 'finalize':
                validate_report(task)
                task['finalized'] = True
                payload = {}
            else:
                raise ValueError('Unknown report operation')
            self.event(c, task, kind, {'value': payload, 'fingerprint': fingerprint}, key)
            self.save(c, task)
            return {'sequence': task['sequence']}

    def settle(self, owner, identifier, attempt, status, error=''):
        with self.tx() as c:
            task = self.read(c, owner, identifier)
            if not task or task.get('attempt_id') != attempt or task['status'] in TERMINAL:
                return task
            if task['status'] == 'cancel_requested':
                status = 'cancelled'
            if status == 'completed':
                if not task['finalized']:
                    status, error = 'failed', 'Codex 结束但未提交完整报告。'
                else:
                    validate_report(task)
            if status not in TERMINAL:
                raise ValueError('Invalid terminal state')
            task.update(status=status, error=error, token_hash='', finished_at=time.time())
            self.event(c, task, status, {'error': error})
            self.save(c, task)
            return task

    def review(self, owner, identifier, value, key):
        with self.tx() as c:
            task = self.read(c, owner, identifier)
            if not task:
                raise KeyError(identifier)
            if task['status'] not in TERMINAL:
                raise OperationConflict('任务结束后才能保存人工复核')
            previous = next((x for x in task['reviews'] if x['key'] == key), None)
            if previous:
                if previous['value'] != value:
                    raise OperationConflict('Review key conflict')
                return task
            if len(task['reviews']) >= 100:
                raise ValueError('Review history limit reached')
            task['reviews'].append({'key': key, 'value': value, 'created_at': time.time(), 'actor_id': owner})
            self.event(c, task, 'review', value)
            self.save(c, task)
            return task

    def edit_draft(self, owner, identifier, key, kind, payload, mutate):
        """CAS/idempotent draft updates. Nothing can mutate frozen queued input."""
        fingerprint = digest({'kind': kind, 'payload': payload})
        with self.tx() as c:
            task = self.read(c, owner, identifier)
            if not task or task.get('report_version') != 'label-batch-v3':
                raise KeyError(identifier)
            c.execute(f'SELECT raw_json FROM {self.table(EVENTS)} WHERE task_id=%s AND idempotency_key=%s', (identifier, key))
            previous = self.rows(c)
            if previous:
                if previous[0]['payload'].get('fingerprint') != fingerprint:
                    raise OperationConflict('Draft request key reused with different input')
                return task
            if task['status'] != 'draft':
                raise OperationConflict('Batch inputs are frozen; create a new batch')
            mutate(task)
            self.event(c, task, kind, {'value': payload, 'fingerprint': fingerprint}, key)
            self.save(c, task)
            return task

    def review_label(self, owner, identifier, lid, value, key):
        from ..codex_compare.batch_contracts import get_label
        with self.tx() as c:
            task = self.read(c, owner, identifier)
            if not task:
                raise KeyError(identifier)
            entry = get_label(task, lid)
            if task['status'] not in TERMINAL:
                raise OperationConflict('任务结束后才能保存人工复核')
            previous = next((x for x in entry['reviews'] if x['key'] == key), None)
            if previous:
                if previous['value'] != value:
                    raise OperationConflict('Review key conflict')
                return task
            if len(entry['reviews']) >= 100:
                raise ValueError('Review history limit reached')
            entry['reviews'].append({'key': key, 'value': value, 'actor_id': owner, 'created_at': time.time()})
            self.event(c, task, 'label_review', {'label_id': lid, 'value': value})
            self.save(c, task)
            return task

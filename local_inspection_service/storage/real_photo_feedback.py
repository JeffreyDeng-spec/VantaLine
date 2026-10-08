"""Account-scoped PostgreSQL feedback queue; no uncertain attempt is requeued."""
import copy
import secrets
import time
import uuid
from contextlib import contextmanager
from ..training.real_photo_contracts import STRATEGY, digest, encode

DDL = '''CREATE TABLE IF NOT EXISTS {schema}.real_photo_states (
 owner_user_id TEXT NOT NULL, task_id TEXT NOT NULL, raw_json JSONB NOT NULL,
 PRIMARY KEY(owner_user_id,task_id));
CREATE TABLE IF NOT EXISTS {schema}.real_photo_jobs (
 id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, task_id TEXT NOT NULL,
 kind TEXT NOT NULL, status TEXT NOT NULL, idempotency_key TEXT NOT NULL,
 created_at DOUBLE PRECISION NOT NULL, raw_json JSONB NOT NULL,
 UNIQUE(owner_user_id,task_id,idempotency_key));
CREATE INDEX IF NOT EXISTS idx_real_photo_queue ON {schema}.real_photo_jobs(kind,status,created_at);
CREATE TABLE IF NOT EXISTS {schema}.real_photo_events (
 id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, task_id TEXT NOT NULL,
 job_id TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL, raw_json JSONB NOT NULL);'''


class RealPhotoRepository:
    def __init__(self, repository):
        self.repository = repository

    def table(self, name):
        return self.repository._qualified_table('real_photo_' + name)

    @contextmanager
    def tx(self, write=True):
        c = self.repository._cursor()
        try:
            if write:
                c.execute("SELECT pg_advisory_xact_lock(hashtextextended('real-photo-v1',0))")
            yield c
            self.repository.connection.commit()
        except Exception:
            self.repository.connection.rollback()
            raise
        finally:
            c.close()

    def rows(self, c):
        return [self.repository._row_to_dict(c, row)['raw_json'] for row in c.fetchall()]

    def read_state(self, c, owner, task):
        c.execute(f'SELECT raw_json FROM {self.table("states")} WHERE owner_user_id=%s AND task_id=%s', (owner, task))
        values = self.rows(c)
        return values[0] if values else None

    def save_state(self, c, state):
        state['updated_at'] = time.time()
        c.execute(f'''INSERT INTO {self.table("states")} VALUES (%s,%s,%s::jsonb)
            ON CONFLICT(owner_user_id,task_id) DO UPDATE SET raw_json=EXCLUDED.raw_json''',
            (state['owner_user_id'], state['task_id'], encode(state)))

    def get(self, owner, task):
        with self.tx(False) as c:
            return self.read_state(c, owner, task)

    def states(self, owners):
        with self.tx(False) as c:
            c.execute(f'SELECT raw_json FROM {self.table("states")} WHERE owner_user_id=ANY(%s)', (list(owners),))
            return self.rows(c)

    def mutate(self, owner, task, fn):
        with self.tx() as c:
            state = self.read_state(c, owner, task)
            if state is None:
                raise KeyError(task)
            result = fn(state, c)
            self.save_state(c, state)
            return result

    def event(self, c, state, job, payload):
        c.execute(f'INSERT INTO {self.table("events")} VALUES (%s,%s,%s,%s,%s,%s::jsonb)',
                  (uuid.uuid4().hex, state['owner_user_id'], state['task_id'], job, time.time(), encode(payload)))

    def enqueue(self, c, state, kind, key, inputs):
        c.execute(f'''SELECT raw_json FROM {self.table("jobs")}
            WHERE owner_user_id=%s AND task_id=%s AND idempotency_key=%s''', (state['owner_user_id'], state['task_id'], key))
        existing = self.rows(c)
        if existing:
            if existing[0]['fingerprint'] != digest(inputs):
                raise ValueError('idempotency key reused with changed inputs')
            return existing[0]
        job = {'id': 'rp_' + uuid.uuid4().hex, 'owner_user_id': state['owner_user_id'],
               'task_id': state['task_id'], 'kind': kind, 'status': 'queued',
               'idempotency_key': key, 'fingerprint': digest(inputs), 'inputs': copy.deepcopy(inputs),
               'epoch': state['epoch'], 'created_at': time.time()}
        self.save_job(c, job)
        self.event(c, state, job['id'], {'kind': 'queued', 'fingerprint': job['fingerprint']})
        return job

    def save_job(self, c, job):
        c.execute(f'''INSERT INTO {self.table("jobs")} VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT(id) DO UPDATE SET status=EXCLUDED.status,raw_json=EXCLUDED.raw_json''',
            (job['id'], job['owner_user_id'], job['task_id'], job['kind'], job['status'],
             job['idempotency_key'], job['created_at'], encode(job)))

    def enable(self, owner, task, classes, profiles, enabled=True, context=None):
        with self.tx() as c:
            state = self.read_state(c, owner, task)
            if state is None:
                state = {'owner_user_id': owner, 'task_id': task, 'strategy': STRATEGY,
                         'epoch': uuid.uuid4().hex, 'classes': classes, 'profiles': profiles,
                         'samples': [], 'rounds': [], 'datasets': [], 'candidate_models': [], 'created_at': time.time(), 'business_context':context or {}}
            if state['classes'] != classes or state['profiles'] != profiles:
                state.update(classes=classes, profiles=profiles, epoch=uuid.uuid4().hex)
                state.pop('round', None)
                state.pop('initialization', None)
            state['enabled'] = enabled
            if not enabled:
                state['epoch'] = uuid.uuid4().hex
                c.execute(f'''SELECT raw_json FROM {self.table("jobs")}
                    WHERE owner_user_id=%s AND task_id=%s AND status IN ('queued','running')''', (owner, task))
                for job in self.rows(c):
                    job.update(status='cancel_requested' if job['status']=='running' else 'cancelled', token_hash='')
                    self.save_job(c, job)
            elif not state.get('initialization'):
                self.enqueue(c, state, 'initialize', 'initialize:' + state['epoch'],
                             {'classes': classes, 'history_count': len(state['samples']), 'business_context':state.get('business_context',{})})
            self.save_state(c, state)
            return state

    def capture(self, owner, task, sample):
        def write(state, c):
            if not state['enabled']:
                return None
            for previous in state['samples']:
                if {sample['image_sha256'], *sample.get('lineage_hashes', [])} & {previous['image_sha256'], *previous.get('lineage_hashes', [])}:
                    return previous
            state['samples'].append(copy.deepcopy(sample))
            if not sample.get('annotation'):
                self.enqueue(c, state, 'annotate', 'annotation:'+sample['sample_id']+':1',
                             {'sample': sample, 'classes': state['classes'], 'profiles': state['profiles'], 'version': 1})
            return sample
        return self.mutate(owner, task, write)

    def jobs(self, owner, task):
        with self.tx(False) as c:
            c.execute(f'SELECT raw_json FROM {self.table("jobs")} WHERE owner_user_id=%s AND task_id=%s ORDER BY created_at DESC LIMIT 100', (owner, task))
            return self.rows(c)

    def receipt(self, identifier, attempt, metadata):
        """Parent-only late receipt retention; never grants admission or requeues work."""
        with self.tx() as c:
            job=self.read_job(c,identifier)
            if not job or job.get('attempt_id')!=attempt:raise ValueError('wrong attempt receipt')
            if set(metadata)-{'external_call_started','usage','session_id','evidence','elapsed_seconds'}:
                raise ValueError('invalid receipt fields')
            job.setdefault('attempt_receipt',{}).update(metadata)
            self.save_job(c,job)

    def statistics(self,owner,task):
        with self.tx(False) as c:
            c.execute(f'SELECT raw_json FROM {self.table("jobs")} WHERE owner_user_id=%s AND task_id=%s',(owner,task))
            jobs=self.rows(c)
        result={}
        for j in jobs:
            kind='doubao' if j['kind']=='annotate' else 'agent' if j['kind'] in {'initialize','review','assess'} else j['kind']
            group=result.setdefault(kind,{'attempts':0,'failures':0,'elapsed_seconds':0,'usage':{},'unknown_usage_count':0,'estimated_cost':None})
            receipt=j.get('attempt_receipt') or {}
            if not receipt.get('external_call_started'):continue
            group['attempts']+=1;group['failures']+=int(j['status'] in {'failed','interrupted','stale','cancel_requested','cancelled'} or (j.get('result') or {}).get('status')=='failed')
            group['elapsed_seconds']+=j.get('elapsed_seconds',receipt.get('elapsed_seconds',0))
            usage=j.get('usage') or receipt.get('usage') or {}
            if not usage:group['unknown_usage_count']+=1
            for key,value in usage.items():
                if type(value)is int and value>=0:group['usage'][key]=group['usage'].get(key,0)+value
        return result

    def claim(self, owners, kinds, model, version):
        with self.tx() as c:
            c.execute(f'SELECT raw_json FROM {self.table("jobs")} WHERE kind=ANY(%s) AND status IN (\'running\',\'cancel_requested\')', (list(kinds),))
            live = self.rows(c)
            for job in live:
                if time.time() - job.get('heartbeat', 0) > 30 or time.time() > job.get('deadline', 0):
                    job.update(status='interrupted', token_hash='', error='uncertain attempt; explicit new attempt required')
                    self.save_job(c, job)
                    state = self.read_state(c, job['owner_user_id'], job['task_id'])
                    self.event(c, state, job['id'], {'kind':'interrupted'})
                else:
                    return None
            c.execute(f'''SELECT raw_json FROM {self.table("jobs")} WHERE kind=ANY(%s)
                AND status='queued' AND owner_user_id=ANY(%s) ORDER BY created_at LIMIT 1''', (list(kinds), list(owners)))
            rows = self.rows(c)
            if not rows:
                return None
            job = rows[0]; state = self.read_state(c, job['owner_user_id'], job['task_id'])
            if not state['enabled'] or job['epoch'] != state['epoch']:
                job['status'] = 'stale'; self.save_job(c, job); return None
            token = secrets.token_urlsafe(32)
            job.update(status='running', attempt_id=uuid.uuid4().hex, token_hash=digest(token.encode()),
                       started_at=time.time(), heartbeat=time.time(), deadline=time.time()+(180 if job['kind']=='annotate' else 600),
                       model='doubao-seed-2-1-pro-260915' if job['kind']=='annotate' else model, runner_version=version)
            self.save_job(c, job)
            return job, token

    def pulse(self, identifier, token):
        with self.tx() as c:
            job = self.read_job(c, identifier)
            if not job or job['status'] != 'running' or time.time() >= job['deadline'] or not secrets.compare_digest(job.get('token_hash',''), digest(token.encode())):
                return False
            job['heartbeat'] = time.time(); self.save_job(c, job); return True

    def read_job(self, c, identifier):
        c.execute(f'SELECT raw_json FROM {self.table("jobs")} WHERE id=%s', (identifier,))
        rows = self.rows(c)
        return rows[0] if rows else None

    def finish(self, identifier, token, result, apply, *, success=True):
        with self.tx() as c:
            job = self.read_job(c, identifier)
            if not job or not secrets.compare_digest(job.get('token_hash',''), digest(token.encode())):
                raise ValueError('attempt expired or revoked')
            if job['status'] != 'running' or time.time() > job['deadline']:
                raise ValueError('attempt no longer active')
            state = self.read_state(c, job['owner_user_id'], job['task_id'])
            job.update(result=result, elapsed_seconds=time.time()-job['started_at'], token_hash='')
            if job['epoch'] != state['epoch'] or not state['enabled']:
                job['status'] = 'stale'
            elif success:
                apply(state, job, c)
                job['status'] = 'completed'
            else:
                job['status'] = 'failed'
            self.event(c, state, identifier, {'kind': job['status'], 'result': result})
            self.save_job(c, job); self.save_state(c, state)
            return job

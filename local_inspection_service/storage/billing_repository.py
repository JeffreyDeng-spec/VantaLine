"""Financial-only PostgreSQL transactions and fenced, immutable publication.

Uses the application thread repository supplier; never constructs a connection,
changes business records or stores credentials. GET paths contain SELECT only.
"""
from contextlib import contextmanager
import json
import re
import uuid

from ..analytics.billing.types import BillingError

TABLES = frozenset(("billing_accounts", "billing_snapshots", "billing_entries", "billing_sync_state", "billing_sync_jobs"))


class BillingRepository:
    def __init__(self, repository):
        self.repository = repository

    @contextmanager
    def transaction(self):
        try:
            repo = self.repository()
            if repo is None:
                raise BillingError("billing_store_unavailable")
            schema = repo.schema_name
            if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", schema):
                raise BillingError("billing_store_unavailable")
            cursor = repo.connection.cursor()
            try:
                def table(name):
                    if name not in TABLES:
                        raise ValueError("invalid financial table")
                    return f'"{schema}"."{name}"'
                yield cursor, table, repo
                repo.connection.commit()
            except BaseException:
                repo.connection.rollback()
                raise
            finally:
                cursor.close()
        except BillingError:
            raise
        except Exception:
            raise BillingError("billing_store_unavailable") from None

    @staticmethod
    def decode(row):
        value = row["payload_json"]
        return json.loads(value) if isinstance(value, str) else value

    def latest(self, account, kind, period):
        with self.transaction() as (c, t, r):
            c.execute(f"SELECT id,created_at,payload_json FROM {t('billing_snapshots')} WHERE account_id=%s AND kind=%s AND period=%s ORDER BY publication_seq DESC LIMIT 1", (account, kind, period))
            raw = c.fetchone()
            if not raw:
                return None
            row = r._row_to_dict(c, raw)
            return {"snapshot_id": row["id"], "synced_at": row["created_at"], **self.decode(row)}

    def sync(self, account, kind, period):
        with self.transaction() as (c, t, r):
            c.execute(f"SELECT j.id,j.status,j.created_at,j.finished_at,j.error_code FROM {t('billing_sync_state')} s JOIN {t('billing_sync_jobs')} j ON j.id=s.job_id WHERE s.account_id=%s AND s.kind=%s AND s.period=%s", (account, kind, period))
            raw = c.fetchone()
            return r._row_to_dict(c, raw) if raw else None

    def request(self, payer, kind, period, actor, now, interval):
        lane = f"{payer.id}:{kind}:{period}"
        job = uuid.uuid4().hex
        with self.transaction() as (c, t, r):
            c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("billing:"+lane,))
            c.execute(f"INSERT INTO {t('billing_accounts')}(id,provider,currency,alias,updated_at) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET alias=EXCLUDED.alias,currency=EXCLUDED.currency,updated_at=EXCLUDED.updated_at", (payer.id,payer.provider,payer.currency,payer.alias,now))
            c.execute(f"SELECT s.job_id,s.last_attempt,j.status FROM {t('billing_sync_state')} s JOIN {t('billing_sync_jobs')} j ON j.id=s.job_id WHERE s.lane=%s", (lane,))
            previous = c.fetchone()
            if previous:
                previous = r._row_to_dict(c, previous)
                if previous["status"] in {"queued", "running"} or now-previous["last_attempt"] < interval:
                    return previous["job_id"]
            c.execute(f"INSERT INTO {t('billing_sync_jobs')}(id,account_id,kind,period,actor_id,status,created_at) VALUES(%s,%s,%s,%s,%s,'queued',%s)", (job,payer.id,kind,period,actor,now))
            c.execute(f"INSERT INTO {t('billing_sync_state')}(lane,account_id,kind,period,job_id,last_attempt) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(lane) DO UPDATE SET job_id=EXCLUDED.job_id,last_attempt=EXCLUDED.last_attempt,lease_token=NULL,lease_until=0", (lane,payer.id,kind,period,job,now))
        return job

    def pending(self, now):
        with self.transaction() as (c, t, r):
            c.execute(f"SELECT j.id,j.account_id,j.kind,j.period FROM {t('billing_sync_jobs')} j JOIN {t('billing_sync_state')} s ON s.job_id=j.id WHERE j.status IN ('queued','running') AND s.lease_until<=%s ORDER BY j.created_at,j.id LIMIT 32", (now,))
            return [r._row_to_dict(c,row) for row in c.fetchall()]

    def claim(self, job, now):
        token = uuid.uuid4().hex
        with self.transaction() as (c, t, r):
            c.execute(f"SELECT account_id FROM {t('billing_sync_jobs')} WHERE id=%s", (job,))
            row = c.fetchone()
            if not row:
                return None
            account = r._row_to_dict(c,row)['account_id']
            c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ('billing-worker:'+account,))
            c.execute(f"SELECT 1 FROM {t('billing_sync_state')} WHERE account_id=%s AND lease_until>%s", (account,now))
            if c.fetchone():
                return None
            c.execute(f"UPDATE {t('billing_sync_state')} SET lease_token=%s,lease_until=%s WHERE job_id=%s AND lease_until<=%s RETURNING lane", (token,now+600,job,now))
            if not c.fetchone():
                return None
            c.execute(f"UPDATE {t('billing_sync_jobs')} SET status='running' WHERE id=%s AND status IN ('queued','running') RETURNING id", (job,))
            if not c.fetchone():
                raise BillingError("billing_lease_lost")
        return token

    def settle(self, job, token, now, *, payload=None, entries=(), error=None):
        """Snapshot, all entries and job settlement commit as one transaction."""
        with self.transaction() as (c, t, r):
            c.execute(f"SELECT s.account_id,s.kind,s.period FROM {t('billing_sync_state')} s WHERE s.job_id=%s AND s.lease_token=%s AND s.lease_until>%s FOR UPDATE", (job,token,now))
            raw = c.fetchone()
            if not raw:
                raise BillingError("billing_lease_lost")
            state = r._row_to_dict(c,raw)
            if payload is not None:
                snapshot = uuid.uuid4().hex
                c.execute(f"INSERT INTO {t('billing_snapshots')}(id,account_id,kind,period,created_at,payload_json) VALUES(%s,%s,%s,%s,%s,%s::jsonb)", (snapshot,state['account_id'],state['kind'],state['period'],now,json.dumps(payload,allow_nan=False)))
                if entries:
                    c.executemany(f"INSERT INTO {t('billing_entries')}(snapshot_id,entry_id,day,payload_json) VALUES(%s,%s,%s,%s::jsonb)", [(snapshot,row['id'],row['day'],json.dumps(row,allow_nan=False)) for row in entries])
            c.execute(f"UPDATE {t('billing_sync_jobs')} SET status=%s,finished_at=%s,error_code=%s WHERE id=%s", ('failed' if error else 'succeeded',now,error,job))
            c.execute(f"UPDATE {t('billing_sync_state')} SET lease_token=NULL,lease_until=0 WHERE job_id=%s", (job,))

    def job(self, identifier):
        with self.transaction() as (c, t, r):
            c.execute(f"SELECT id,account_id,kind,period,status,created_at,finished_at,error_code FROM {t('billing_sync_jobs')} WHERE id=%s", (identifier,))
            raw = c.fetchone()
            return r._row_to_dict(c,raw) if raw else None

    def entries(self, account, period, snapshot, after, limit):
        with self.transaction() as (c, t, r):
            c.execute(f"SELECT payload_json FROM {t('billing_snapshots')} WHERE id=%s AND account_id=%s AND kind='bills' AND period=%s", (snapshot,account,period))
            raw = c.fetchone()
            if not raw:
                raise BillingError("invalid_billing_cursor")
            count = self.decode(r._row_to_dict(c,raw))['entry_count']
            condition = " AND (day,entry_id)<(%s,%s)" if after else ""
            args = (snapshot,*after,limit+1) if after else (snapshot,limit+1)
            c.execute(f"SELECT entry_id,day,payload_json FROM {t('billing_entries')} WHERE snapshot_id=%s{condition} ORDER BY day DESC,entry_id DESC LIMIT %s", args)
            return [self.decode(r._row_to_dict(c,row)) for row in c.fetchall()], count

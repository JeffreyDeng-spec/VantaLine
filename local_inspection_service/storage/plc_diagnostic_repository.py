"""One independent asynchronous diagnostic connection, bounded admission and SQL.

No business repository, station mutation, shared advisory lock or serial I/O.
The connection is closed after each request; disabled diagnostics allocate none.
"""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import time
from collections.abc import Callable, Mapping
from typing import Any
from fastapi import HTTPException

class PlcDiagnosticRepository:
    def __init__(self, environment: Mapping[str, str], connect: Callable[..., Any] | None = None):
        self.environment = environment
        self.connect = connect
        self.gate = asyncio.Semaphore(1)

    @asynccontextmanager
    async def connection(self):
        try:
            await asyncio.wait_for(self.gate.acquire(), .05)
        except asyncio.TimeoutError:
            raise HTTPException(503, 'plc_diagnostic_busy') from None
        connection = None
        try:
            import psycopg
            connect = self.connect or psycopg.AsyncConnection.connect
            dsn = self.environment.get('DATABASE_URL', '')
            if not dsn:
                raise HTTPException(503, 'plc_diagnostic_unavailable')
            connection = await asyncio.wait_for(connect(dsn, autocommit=True, options='-c statement_timeout=200 -c lock_timeout=50 -c application_name=vantaline_plc_diagnostics'), .05)
            yield connection
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, 'plc_diagnostic_unavailable') from None
        finally:
            try:
                if connection is not None:
                    await connection.close()
            finally:
                self.gate.release()

    async def append(self, user: dict, cookie: str, events: list[dict]) -> list[str]:
        owner = str(user['id'])
        async def persist(c):
            async with c.transaction():
                station_ids = {e['station_id'] for e in events if e.get('station_id')}
                observations = {}
                if station_ids:
                    cur = await c.execute('SELECT id,config_generation FROM vantaline.plc_workstations WHERE token_hash=%s', (hashlib.sha256(cookie.encode()).hexdigest(),))
                    station = await cur.fetchone()
                    if not station or station_ids != {station[0]}:
                        raise HTTPException(403, 'plc_diagnostic_station_denied')
                    cur = await c.execute('SELECT state,lease_epoch,owner_user_id,config_generation FROM vantaline.plc_workstation_leases WHERE station_id=%s', (station[0],))
                    lease = await cur.fetchone()
                    if lease and lease[2] == owner:
                        observations = {'state':lease[0], 'lease_epoch':lease[1], 'config_generation':lease[3]}
                now = int(time.time()*1000)
                for e in events:
                    report = {**e, 'evidence_source':'browser_report', 'server_observed_at':now}
                    # This is the current lease observed at ingestion, not confirmation
                    # of the historical physical operation reported by the browser.
                    if e.get('station_id') and observations:
                        report['server_lease_observation'] = observations
                    await c.execute('INSERT INTO vantaline.plc_diagnostic_events(owner_user_id,event_id,attempt_id,station_id,received_at,step,result,code,payload_json) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT(owner_user_id,event_id) DO NOTHING', (owner,e['event_id'],e['attempt_id'],e.get('station_id'),now,e['step'],e['result'],e['code'],json.dumps(report,separators=(',',':'))))
                return [e['event_id'] for e in events]
        async with self.connection() as c:
            return await asyncio.wait_for(persist(c), .2)

    async def list(self, user: dict, *, account='', station='', attempt='', code='', since=0, until=0, offset=0) -> dict:
        conditions, args = ['d.received_at >= %s'], [max(since,int(time.time()*1000)-30*86400000)]
        if user.get('role') != 'admin':
            if account and account not in (user['id'],user.get('username')):
                raise HTTPException(403, 'plc_diagnostic_account_denied')
            conditions.append('d.owner_user_id=%s'); args.append(user['id'])
        elif account:
            conditions.append('(d.owner_user_id=%s OR u.username=%s)'); args.extend([account,account])
        for value, clause in ((station,'d.station_id=%s'),(attempt,'d.attempt_id=%s'),(code,'d.code=%s'),(until,'d.received_at<=%s')):
            if value:
                conditions.append(clause); args.append(value)
        async def fetch(c):
            cur = await c.execute('SELECT d.payload_json,d.received_at,d.owner_user_id,u.username,w.name FROM vantaline.plc_diagnostic_events d LEFT JOIN vantaline.users u ON u.id=d.owner_user_id LEFT JOIN vantaline.plc_workstations w ON w.id=d.station_id WHERE '+ ' AND '.join(conditions)+' ORDER BY d.received_at DESC,d.event_id DESC LIMIT 51 OFFSET %s', (*args,offset))
            return await cur.fetchall()
        async with self.connection() as c:
            rows = await asyncio.wait_for(fetch(c), .2)
        return {'items':[{**r[0],'received_at':r[1],'owner_user_id':r[2],'username':r[3] or '', 'station_name':r[4] or ''} for r in rows[:50]], 'next_offset':offset+50 if len(rows)>50 and offset<10000 else None, 'limited':len(rows)>50 and offset>=10000}

    async def cleanup(self) -> int:
        async def remove(c):
            cur = await c.execute('WITH expired AS (SELECT owner_user_id,event_id FROM vantaline.plc_diagnostic_events WHERE received_at<%s ORDER BY received_at LIMIT 500 FOR UPDATE SKIP LOCKED) DELETE FROM vantaline.plc_diagnostic_events d USING expired e WHERE d.owner_user_id=e.owner_user_id AND d.event_id=e.event_id', (int(time.time()*1000)-30*86400000,))
            return cur.rowcount
        async with self.connection() as c:
            return await asyncio.wait_for(remove(c), .2)

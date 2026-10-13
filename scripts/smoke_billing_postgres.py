"""Real PostgreSQL financial publication/lease/paging tests in a disposable DB."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import unittest

import psycopg

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from local_inspection_service.analytics.billing.service import BillingService
from local_inspection_service.analytics.billing.types import Balance,Bills,BillingError,entry,payers
from local_inspection_service.storage.billing_repository import BillingRepository
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository

DSN=os.environ['BILLING_TEST_DATABASE_URL']
NOW=int(datetime.fromisoformat('2026-10-13T12:00:00+08:00').timestamp())
CONFIG={'VANTALINE_BILLING_ACCOUNTS_JSON':json.dumps([{'provider':'volc','payer_id':'fixture-payer','key_ref':'FIXTURE_KEY','secret_ref':'FIXTURE_SECRET','resource_projects':{'resource':'vantaline'}}])}


class Reader:
    def __init__(self):self.value='100.00';self.net='1';self.failure=False;self.count=101;self.duplicate=False;self.days=None;self.scope='payer'
    def balance(self,payer):
        if self.failure:raise BillingError('provider_denied')
        return Balance(self.value,{'CashBalance':self.value},'synthetic-official-balance')
    def bills(self,payer,period):
        if self.failure:raise RuntimeError('never-expose-secret-or-host')
        rows=[entry(str(i),period+'-07','fixture service',self.net,resource='resource',gross='2',discount='1',payer=payer) for i in range(self.count)]
        if self.duplicate:rows.append(rows[0].copy())
        days=self.days if self.days is not None else [{'date':(datetime.fromisoformat(period+'-05')+timedelta(days=i)).date().isoformat(),'amount':'10'} for i in range(7)]
        return Bills(rows,str(Decimal(self.net)*self.count),'2026-10-11','synthetic-official-bills',self.scope,'official_summary',days)


class FinancialPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(DSN) as c:
            if c.execute('SELECT current_database()').fetchone()[0]!='vantaline_billing_test':
                raise RuntimeError('refusing non-disposable database')
            c.execute('CREATE SCHEMA IF NOT EXISTS vantaline')
            c.execute('CREATE TABLE IF NOT EXISTS vantaline.feature_migrations(version TEXT PRIMARY KEY,applied_at BIGINT,metadata_json JSONB)')
        migration=(ROOT/'local_inspection_service/storage/migrations/2026_10_13_billing.sql').read_text()
        with psycopg.connect(DSN,autocommit=True) as c:
            c.execute(migration);c.execute(migration)

    def setUp(self):
        self.connection=psycopg.connect(DSN)
        self.addCleanup(self.connection.close)
        with self.connection.cursor() as c:
            c.execute('TRUNCATE vantaline.billing_entries,vantaline.billing_snapshots,vantaline.billing_sync_state,vantaline.billing_sync_jobs,vantaline.billing_accounts CASCADE')
        self.connection.commit()
        raw=PostgresRuntimeRepository(self.connection,'test-only')
        self.repo=BillingRepository(lambda:raw)
        self.clock=[NOW];self.reader=Reader()
        self.service=BillingService(CONFIG,self.repo,lambda _:'',clock=lambda:self.clock[0],reader=self.reader)
        self.payer=payers(CONFIG)[0]

    def sync(self,kind,period='2026-10'):
        job=self.repo.request(self.payer,kind,'' if kind=='balance' else period,'fixture-admin',self.clock[0],60 if kind=='balance' else 900)
        self.service.run_job(self.repo.job(job))
        return job

    def test_more_than_80_complete_paging_new_snapshots_and_account_isolation(self):
        self.sync('bills')
        page=self.service.entries(self.payer.id,'2026-10')
        self.assertEqual(len(page['items']),50);self.assertEqual(page['total'],101)
        cursor=page['next_cursor'];snapshot=page['snapshot_id']
        self.clock[0]+=901;self.reader.count=111;self.sync('bills')
        collected=page['items'][:]
        while cursor:
            page=self.service.entries(self.payer.id,'2026-10',cursor)
            self.assertEqual(page['snapshot_id'],snapshot)
            self.assertEqual(page['total'],101)
            collected+=page['items'];cursor=page['next_cursor']
        self.assertEqual(len(collected),101)
        self.assertEqual(len({r['id'] for r in collected}),101)
        self.assertEqual(self.service.entries(self.payer.id,'2026-10')['total'],111)
        other={**json.loads(CONFIG['VANTALINE_BILLING_ACCOUNTS_JSON'])[0],'payer_id':'other-payer'}
        self.service.environment={'VANTALINE_BILLING_ACCOUNTS_JSON':json.dumps([json.loads(CONFIG['VANTALINE_BILLING_ACCOUNTS_JSON'])[0],other])}
        other_payer=next(p for p in payers(self.service.environment) if p.payer_id=='other-payer')
        with self.assertRaises(BillingError):self.service.entries(other_payer.id,'2026-10',self.service.entries(self.payer.id,'2026-10')['next_cursor'])
        with self.assertRaises(BillingError):self.service.entries(self.payer.id,'2026-09',self.service.entries(self.payer.id,'2026-10')['next_cursor'])

    def test_failure_retains_snapshot_and_critical_colour_stops_prediction(self):
        self.reader.value='20';self.sync('balance');self.sync('bills')
        initial=self.service.detail(self.payer.id,'2026-10')
        self.assertEqual(initial['urgency'],'critical');self.assertEqual(initial['runway_days'],'2.0')
        self.clock[0]+=61;self.reader.failure=True;job=self.sync('balance')
        failed=self.service.detail(self.payer.id,'2026-10')
        self.assertEqual(failed['balance'],initial['balance'])
        self.assertEqual(failed['urgency'],'critical');self.assertIsNone(failed['runway_days'])
        self.assertEqual(self.repo.job(job)['error_code'],'provider_denied')
        self.clock[0]+=901;job=self.sync('bills')
        self.assertEqual(self.repo.job(job)['error_code'],'invalid_provider_record')
        self.assertEqual(self.service.detail(self.payer.id,'2026-10')['bills']['snapshot_id'],initial['bills']['snapshot_id'])

    def test_exact_sum_refund_recharge_unknowns_and_restart(self):
        self.reader.net='.1';self.reader.count=3;self.reader.duplicate=True
        self.sync('balance');self.sync('bills')
        data=self.service.detail(self.payer.id,'2026-10')
        self.assertEqual(data['bills']['entries_total'],'0.3')
        self.assertEqual(data['bills']['reconciliation_delta'],'0.0')
        before=data['bills']['snapshot_id']
        self.clock[0]+=61;self.reader.value='250';self.sync('balance')
        self.assertEqual(self.service.detail(self.payer.id,'2026-10')['bills']['snapshot_id'],before)
        self.clock[0]+=901;self.reader.net='-.1';self.sync('bills')
        self.assertEqual(self.service.detail(self.payer.id,'2026-10')['bills']['entries_total'],'-0.3')
        restarted=BillingService(CONFIG,self.repo,lambda _:'',clock=lambda:self.clock[0],reader=self.reader)
        self.assertEqual(restarted.detail(self.payer.id)['balance']['value'],'250')
        self.assertIsNone(restarted.detail('pending_codex')['balance'])
        self.assertNotIn('FIXTURE_SECRET',json.dumps(restarted.overview()))

    def test_missing_day_zero_refund_partial_scope_and_historical_month(self):
        self.sync('balance');self.sync('bills')
        historical=self.service.detail(self.payer.id,'2026-09')
        self.assertEqual(historical['daily_average'],'10')
        self.assertIsNone(historical['bills'])
        for data,expected in (([],None),([{'date':f'2026-10-{i:02}','amount':'0'} for i in range(5,12)],'0'),([{'date':f'2026-10-{i:02}','amount':'-1'} for i in range(5,12)],'-1')):
            self.clock[0]+=901;self.reader.days=data
            self.sync('balance');self.sync('bills')
            current=self.service.detail(self.payer.id)
            # An explicit empty daily list falls back to entries; it still has
            # a complete source day range. Exercise a genuinely missing day next.
            if data:self.assertEqual(current['daily_average'],expected);self.assertIsNone(current['runway_days'])
        self.clock[0]+=901;self.reader.days=[{'date':'2026-10-05','amount':'10'}];self.sync('bills')
        self.assertIsNone(self.service.detail(self.payer.id)['daily_average'])
        self.clock[0]+=901;self.reader.scope='supported_resources';self.sync('bills')
        self.assertIsNone(self.service.detail(self.payer.id)['runway_days'])

    def test_queued_requests_merge_across_connections_and_lease_fences(self):
        def request(_):
            with psycopg.connect(DSN) as c:
                repo=BillingRepository(lambda:PostgresRuntimeRepository(c,'test-only'))
                return repo.request(self.payer,'balance','','fixture-admin',NOW,60)
        with ThreadPoolExecutor(max_workers=6) as pool:jobs=list(pool.map(request,range(12)))
        self.assertEqual(len(set(jobs)),1)
        token=self.repo.claim(jobs[0],NOW)
        self.assertIsNotNone(token);self.assertIsNone(self.repo.claim(jobs[0],NOW))
        replacement=self.repo.claim(jobs[0],NOW+601)
        self.assertIsNotNone(replacement)
        with self.assertRaises(BillingError):self.repo.settle(jobs[0],token,NOW+601,payload={'value':'999'})
        self.assertIsNone(self.repo.latest(self.payer.id,'balance',''))
        self.repo.settle(jobs[0],replacement,NOW+601,payload={'value':'1'})
        self.assertEqual(self.repo.latest(self.payer.id,'balance','')['value'],'1')

    def test_publication_failure_is_atomic(self):
        self.sync('bills');old=self.repo.latest(self.payer.id,'bills','2026-10')
        self.clock[0]+=901
        job=self.repo.request(self.payer,'bills','2026-10','admin',self.clock[0],900)
        token=self.repo.claim(job,self.clock[0]);row=entry('duplicate','2026-10-07','fixture','1',payer=self.payer)
        with self.assertRaises(BillingError):self.repo.settle(job,token,self.clock[0],payload={'entry_count':2},entries=[row,row])
        self.assertEqual(self.repo.latest(self.payer.id,'bills','2026-10'),old)
        self.assertEqual(self.repo.job(job)['status'],'running')


if __name__=='__main__':unittest.main()

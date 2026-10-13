"""Local-only real application/React financial acceptance fixture.

Start with BILLING_TEST_DATABASE_URL pointing to vantaline_billing_test.
All users, snapshots and model records are synthetic. Supplier ports are replaced
with a fixed reader; no model/financial supplier or physical I/O is used.
"""
import os
os.environ.setdefault('YOLO_CONFIG_DIR','/private/tmp/billing-yolo-settings')
from contextlib import contextmanager
from datetime import datetime, timedelta
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from zoneinfo import ZoneInfo

import psycopg
from fastapi.responses import HTMLResponse
from fastapi import HTTPException, Response
import uvicorn

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from local_inspection_service.runtime.application import create_application
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.billing_repository import BillingRepository
from local_inspection_service.analytics.billing.types import Balance,Bills,BillingError,entry,payers
from local_inspection_service.analytics.billing.service import BillingService
from local_inspection_service.runtime.connections import ThreadRepositoryFactory
from local_inspection_service.storage.runtime_selector import RuntimeRepositorySelection

DSN=os.environ['BILLING_TEST_DATABASE_URL']
with psycopg.connect(DSN) as c:
    if c.execute('SELECT current_database()').fetchone()[0]!='vantaline_billing_test':
        raise RuntimeError('refusing non-disposable database')

home=Path(tempfile.mkdtemp(prefix='billing-react-fixture-'))
(home/'local_inspection_service/static').mkdir(parents=True)
brand=ROOT/'local_inspection_service/static/brand-logo.png'
if brand.is_file():shutil.copy(brand,home/'local_inspection_service/static/brand-logo.png')
shutil.copytree(ROOT/'local_inspection_service/frontend/dist-production',home/'local_inspection_service/frontend/dist-production')
index=home/'local_inspection_service/frontend/dist-production/index.html'
index.write_text(index.read_text().replace('<body>', '<body><aside style="padding:8px 16px;background:#fff5d9;color:#8c661d;font:12px system-ui">隔离验证环境 · 所有财务金额与用户均为测试数据</aside>'))
env={'LOCAL_INSPECTION_ROOT':str(home),'VANTALINE_DATA_STORE':'json','VANTALINE_FILE_STORE':'local','VANTALINE_LABEL_INSPECTION_ENABLED':'false','LOCAL_INSPECTION_AUTO_RESUME_WORKER':'0','INSPECTION_ENABLE_LAN_CORS':'0','INSPECTION_CORS_ORIGINS':'','VANTALINE_BILLING_ACCOUNTS_JSON':json.dumps([{'provider':p,'payer_id':'synthetic-'+p,'alias':label,'currency':'USD' if p=='runpod' else 'CNY','key_ref':'FIXTURE_KEY','secret_ref':'FIXTURE_SECRET'} for p,label in [('volc','模型生产账户'),('ali','检测与 OCR 账户'),('tencent','服务器与 COS 账户'),('runpod','GPU 训练账户')]])}
owned=create_application(env)


class Reader:
    scene='normal'
    def balance(self,payer):
        if self.scene=='failure' and payer.provider in {'runpod','tencent'}:raise BillingError('provider_unavailable')
        value={'volc':'1268.40','ali':'892.16','tencent':'2146.88','runpod':'74.28'}[payer.provider]
        if self.scene=='low' and payer.provider in {'volc','runpod'}:value='2.10'
        return Balance(value,{'CashBalance':value},'synthetic-fixture-only')
    def bills(self,payer,period):
        if self.scene=='failure' and payer.provider in {'runpod','tencent'}:raise BillingError('provider_unavailable')
        now=datetime.now(ZoneInfo(payer.timezone));end=now.date()-timedelta(days=2)
        if period!=end.strftime('%Y-%m'):
            next_month=datetime.fromisoformat(period+'-01').replace(day=28)+timedelta(days=4)
            end=next_month.date().replace(day=1)-timedelta(days=1)
        daily=[{'date':(end-timedelta(days=6-i)).isoformat(),'amount':str([13,10,15,18,12,21,17][i])} for i in range(7)]
        rows=[entry(str(i),period+'-07','服务器' if payer.provider=='tencent' else 'API 与计算', '1.25',resource='synthetic-resource',gross='1.50',discount='.25',payer=payer) for i in range(101)]
        return Bills(rows,'126.25',end.isoformat(),'synthetic-fixture-only',daily=daily)


factory=ThreadRepositoryFactory(lambda:RuntimeRepositorySelection('postgres',PostgresRuntimeRepository(psycopg.connect(DSN),'test-only')),lambda:('synthetic-billing',))
service=owned.analytics._billing
service.repository=BillingRepository(lambda:factory.selection().repository)
service.scope=factory.thread_scope
service.reader=Reader()
with factory.thread_scope():
    with psycopg.connect(DSN) as c:
        c.execute('TRUNCATE vantaline.billing_entries,vantaline.billing_snapshots,vantaline.billing_sync_state,vantaline.billing_sync_jobs,vantaline.billing_accounts CASCADE')
    for payer in payers(env):
        if payer.pending:continue
        for kind in ('balance','bills'):
            job=service.repository.request(payer,kind,'' if kind=='balance' else time.strftime('%Y-%m'),'fixture-setup',int(time.time()),0)
            service.run_job(service.repository.job(job))

@owned.app.get('/fixture')
def fixture():
    return HTMLResponse('''<!doctype html><html lang="zh"><meta charset="utf-8"><title>财务隔离验证控制</title><style>body{font:16px system-ui;padding:30px}form{display:inline-block;margin:10px}button{padding:10px 20px}</style><h1>财务隔离验证控制</h1><p>测试管理员：billing-admin / BillingFixture123!　普通用户：billing-user / BillingFixture123!</p><p>全部为隔离模拟记录，页面使用实际生产构建与后端。</p><form method="post" action="/fixture/normal"><button>正常场景</button></form><form method="post" action="/fixture/low"><button>低余额场景</button></form><form method="post" action="/fixture/failure"><button>同步失败场景</button></form><a href="/workspace/rules?section=usage">打开用量与成本</a></html>''')

requests_by_role={'admin':0,'user':0,'anonymous':0}
@owned.app.middleware('http')
async def observe_financial_requests(request,call_next):
    response=await call_next(request)
    if request.url.path.startswith('/api/admin/billing/'):
        user=getattr(request.state,'user',None)
        role=(user or {}).get('role','anonymous')
        requests_by_role[role]+=1
    return response

@owned.app.get('/fixture/requests')
def request_counts():
    return requests_by_role

@owned.app.post('/fixture/{scene}')
def scenario(scene:str):
    if scene not in {'normal','low','failure'}:raise HTTPException(400)
    service.reader.scene=scene
    with factory.thread_scope():
        for payer in payers(env):
            if payer.pending:continue
            for kind in ('balance','bills'):
                # Test-only admission forces a new job while retaining snapshots.
                with service.repository.transaction() as (c,t,_):
                    c.execute(f"UPDATE {t('billing_sync_state')} SET last_attempt=0 WHERE account_id=%s",(payer.id,))
                job=service.repository.request(payer,kind,'' if kind=='balance' else time.strftime('%Y-%m'),'fixture-admin',int(time.time()),0)
                service.run_job(service.repository.job(job))
    return HTMLResponse('<p>隔离场景已更新</p><a href="/fixture">返回验证控制</a>')

if __name__=='__main__':
    # Test controls must precede the application's frontend catch-all route.
    routes=owned.app.router.routes
    routes[:]=[r for r in routes if str(getattr(r,'path','')).startswith('/fixture')]+[r for r in routes if not str(getattr(r,'path','')).startswith('/fixture')]
    # Disable unrelated native startup tasks for browser acceptance. The owned
    # lifetime still drains every inert component on exit.
    owned.app.router.on_startup[:]=[service.start]
    uvicorn.run(owned.app,host='127.0.0.1',port=5197,log_level='error')

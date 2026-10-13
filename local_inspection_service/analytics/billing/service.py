"""Owned financial synchronization and read projections, with narrow ports."""
import base64
from contextlib import nullcontext
from datetime import datetime, timedelta
import json
import threading
import time
from zoneinfo import ZoneInfo

from .types import BillingError, PROVIDERS, amount, decimal, divide, mean, month_dates, payers, period_value, subtract, total
from .providers import ProviderReader
from .transport import FinancialTransport


class BillingService:
    def __init__(self, environment, repository, secret, scope=nullcontext, *, clock=time.time, reader=None, account_environment=None):
        self.environment, self.repository, self.scope, self.clock = environment, repository, scope, clock
        self.reader = reader or ProviderReader(FinancialTransport(secret),clock)
        self.account_environment = account_environment or (lambda: self.environment)
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.lock = threading.RLock()
        self.worker_error = None

    def configured(self):
        return payers(self.account_environment())

    def payer(self, identifier):
        found = next((p for p in self.configured() if p.id == identifier),None)
        if found is None:
            raise BillingError('billing_account_not_found')
        return found

    def start(self):
        with self.lock:
            if self.stop.is_set():
                raise RuntimeError('Billing service is closed')
            if self.thread is None:
                self.thread = threading.Thread(target=self.loop,name='financial-snapshot-sync',daemon=True)
                self.thread.start()

    def close(self, timeout):
        self.stop.set();self.wake.set()
        thread = self.thread
        if thread and thread is not threading.current_thread():
            thread.join(max(0,timeout))
        return not thread or not thread.is_alive()

    def loop(self):
        while not self.stop.is_set():
            try:
                with self.scope():
                    self.tick()
                self.worker_error = None
            except BillingError as exc:
                self.worker_error = exc.code
            except Exception:
                self.worker_error = 'billing_sync_failed'
            self.wake.wait(5);self.wake.clear()

    def tick(self):
        configured = [p for p in self.configured() if not p.pending and p.key_ref and (p.secret_ref or p.provider=='runpod')]
        if not configured:
            return
        now = int(self.clock())
        for payer in configured:
            today = datetime.fromtimestamp(now,ZoneInfo(payer.timezone)).date()
            current = today.strftime('%Y-%m')
            self.repository.request(payer,'balance','','scheduler',now,60)
            self.repository.request(payer,'bills',current,'scheduler',now,900)
            if today.day <= 9:
                previous = (today.replace(day=1)-timedelta(days=1)).strftime('%Y-%m')
                self.repository.request(payer,'bills',previous,'scheduler',now,900)
        for job in self.repository.pending(int(self.clock())):
            if self.stop.is_set():
                break
            self.run_job(job)

    def refresh(self, identifier, period, actor):
        if self.stop.is_set():
            raise BillingError('billing_sync_stopping')
        now=int(self.clock());period=period_value(period,now)
        selected=[self.payer(identifier)] if identifier else self.configured()
        jobs=[]
        for payer in selected:
            if payer.pending:
                continue
            jobs.append(self.repository.request(payer,'balance','',actor,now,60))
            jobs.append(self.repository.request(payer,'bills',period,actor,now,900))
        self.wake.set()
        return {'job_ids':list(dict.fromkeys(jobs)),'period':period,'pending_accounts':sum(bool(p.pending) for p in selected)}

    def run_job(self, job):
        token=self.repository.claim(job['id'],int(self.clock()))
        if token is None:
            return
        try:
            payer=self.payer(job['account_id'])
            if payer.pending:
                raise BillingError(payer.pending)
            if job['kind']=='balance':
                value=self.reader.balance(payer)
                payload={'value':amount(value.value),'components':value.components,'source':value.source,'currency':payer.currency}
                entries=()
            else:
                bills=self.reader.bills(payer,job['period']).validated(payer,job['period'])
                entries=bills.entries
                groups={}
                for row in entries:
                    for group,key in (('services',row['service']),('projects',row['project'])):
                        groups.setdefault(group,{}).setdefault(key,[]).append(row['net'])
                daily=bills.daily
                if not daily and bills.complete_until:
                    start,end=month_dates(job['period'])
                    end=min(end,datetime.fromisoformat(bills.complete_until).date())
                    amounts={}
                    for row in entries:
                        if row['granularity'] != 'monthly_resource':
                            amounts.setdefault(row['day'],[]).append(row['net'])
                    daily=[]
                    while start<=end:
                        daily.append({'date':start.isoformat(),'amount':total(amounts.get(start.isoformat(),[]))})
                        start+=timedelta(days=1)
                net=total(row['net'] for row in entries)
                delta=None if bills.official_total is None else amount(subtract(net,bills.official_total))
                payload={'currency':payer.currency,'official_total':bills.official_total,'entries_total':net,'entry_count':len(entries),'complete_until':bills.complete_until,'daily':daily,'source':bills.source,'scope':bills.scope,'summary_basis':bills.summary_basis,'reconciliation_delta':delta,'services':[{'name':key,'amount':total(values)} for key,values in groups.get('services',{}).items()],'projects':[{'name':key,'amount':total(values)} for key,values in groups.get('projects',{}).items()],'gross':total(row['gross'] for row in entries) if entries and all(row['gross'] is not None for row in entries) else None,'discount':total(row['discount'] for row in entries) if entries and all(row['discount'] is not None for row in entries) else None}
            self.repository.settle(job['id'],token,int(self.clock()),payload=payload,entries=entries)
        except Exception as exc:
            code=exc.code if isinstance(exc,BillingError) else 'invalid_provider_record'
            self.repository.settle(job['id'],token,int(self.clock()),error=code)

    def account(self, payer, period):
        now=self.clock()
        balance=bills=None;balance_sync=bill_sync=None;store=True
        if not payer.pending:
            try:
                balance=self.repository.latest(payer.id,'balance','')
                bills=self.repository.latest(payer.id,'bills',period)
                balance_sync=self.repository.sync(payer.id,'balance','')
                bill_sync=self.repository.sync(payer.id,'bills',period)
            except BillingError:
                store=False
        balance_stale=bool(balance and (now-balance['synced_at']>180 or (balance_sync or {}).get('status')=='failed'))
        bill_stale=bool(bills and (now-bills['synced_at']>1800 or (bill_sync or {}).get('status')=='failed'))
        has_references=bool(payer.key_ref and (payer.secret_ref or payer.provider=='runpod'))
        reason=payer.pending or ('credentials_missing' if not has_references else None) or (None if store else 'billing_store_unavailable')
        reason=reason or (balance_sync or {}).get('error_code') or (bill_sync or {}).get('error_code')
        if bills and bills['reconciliation_delta'] is not None and decimal(bills['reconciliation_delta']) != 0:
            reason=reason or 'billing_reconciliation_pending'
        if balance and balance['currency']!=payer.currency:
            balance=None;reason='billing_currency_mismatch'
        if bills and bills['currency']!=payer.currency:
            bills=None;reason='billing_currency_mismatch'
        average,runway,window=None,None,None
        trend=[]
        today=datetime.fromtimestamp(now,ZoneInfo(payer.timezone)).date()
        end=today-timedelta(days=2);start=end-timedelta(days=6)
        consumption_stale=True
        if not payer.pending and store:
            try:
                periods={start.strftime('%Y-%m'),end.strftime('%Y-%m')}
                sources=[self.repository.latest(payer.id,'bills',p) for p in sorted(periods)]
                valid=all(s and s['currency']==payer.currency and s['scope']=='payer' and s['complete_until'] and s['reconciliation_delta'] is not None and decimal(s['reconciliation_delta'])==0 for s in sources)
                consumption_stale=not valid or any(now-s['synced_at']>1800 or (self.repository.sync(payer.id,'bills',p) or {}).get('status')=='failed' for s,p in zip(sources,sorted(periods)) if s)
                by_day={row['date']:row['amount'] for source in sources if source for row in source['daily']}
                expected=[(start+timedelta(days=i)).isoformat() for i in range(7)]
                if valid and not all(day in by_day for day in expected):
                    # Retain the last complete seven-day evidence for colour and
                    # historical display; it cannot authorize a current runway.
                    previous=sorted(day for day in by_day if day<=end.isoformat())[-7:]
                    if len(previous)==7 and all((datetime.fromisoformat(previous[i+1])-datetime.fromisoformat(previous[i])).days==1 for i in range(6)):
                        expected=previous
                        consumption_stale=True
                if valid and all(day in by_day for day in expected):
                    trend=[{'date':day,'amount':by_day[day]} for day in expected]
                    average=mean((row['amount'] for row in trend),7)
                    window={'from':expected[0],'to':expected[-1],'timezone':payer.timezone}
                    if balance and not balance_stale and not consumption_stale and decimal(average)>0 and decimal(balance['value'])>0:
                        runway=amount(divide(balance['value'],average,places=1))
            except BillingError:
                reason=reason or 'billing_store_unavailable'
        # Preserve urgent known evidence even if a later sync fails.
        urgent=bool(balance and decimal(balance['value'])<=0)
        if balance and average and decimal(average)>0 and divide(balance['value'],average)<3:
            urgent=True
        attention=balance_stale or bill_stale or bool(reason and balance)
        urgency='critical' if urgent else 'warning' if attention or (runway is not None and decimal(runway)<14) else 'normal' if balance and (runway is not None or (average is not None and decimal(average)==0 and not consumption_stale and not balance_stale)) else 'pending'
        return {'id':payer.id,'provider':payer.provider,'name':PROVIDERS[payer.provider],'alias':payer.alias,'currency':payer.currency,'period':period,'balance':balance,'bills':bills,'balance_sync':balance_sync,'bill_sync':bill_sync,'balance_stale':balance_stale,'bill_stale':bill_stale,'reason':reason or ('not_synced' if not balance else None),'urgency':urgency,'daily_average':average,'runway_days':runway,'consumption_window':window,'consumption_stale':consumption_stale,'trend':trend,'storage_available':store}

    def overview(self, period=None):
        period=period_value(period,self.clock())
        items=[self.account(p,period) for p in self.configured()]
        currencies=sorted({p['currency'] for p in items})
        groups=[]
        for currency in currencies:
            cohort=[p for p in items if p['currency']==currency]
            known=[p for p in cohort if p['bills'] and p['bills']['official_total'] is not None]
            dates=sorted(set.intersection(*(set(r['date'] for r in p['bills']['daily']) for p in known)))[-7:] if known else []
            trend=[{'date':day,'amount':total(next(r['amount'] for r in p['bills']['daily'] if r['date']==day) for p in known)} for day in dates]
            groups.append({'currency':currency,'amount':total(p['bills']['official_total'] for p in known) if known else None,'covered':len(known),'total_accounts':len(cohort),'stale':any(p['bill_stale'] for p in known),'trend':trend,'daily_average':mean((p['amount'] for p in trend),len(trend)) if trend else None})
        return {'period':period,'accounts':items,'totals':groups,'read_only':True,'worker_error':self.worker_error}

    def detail(self, identifier, period=None):
        period=period_value(period,self.clock())
        return self.account(self.payer(identifier),period)

    def entries(self,identifier,period=None,cursor=None,limit=50,snapshot_id=None):
        payer=self.payer(identifier);period=period_value(period,self.clock())
        after=None
        if cursor:
            try:
                if len(cursor)>1024:
                    raise ValueError()
                decoded=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if decoded['account']!=payer.id or decoded['period']!=period:
                    raise ValueError()
                snapshot=decoded['snapshot'];after=decoded['after']
                if snapshot_id and snapshot_id!=snapshot:
                    raise ValueError()
                if not isinstance(after,list) or len(after)!=2 or not all(isinstance(v,str) for v in after):
                    raise ValueError()
            except Exception:
                raise BillingError('invalid_billing_cursor') from None
        elif snapshot_id:
            snapshot=snapshot_id
        else:
            latest=self.repository.latest(payer.id,'bills',period)
            if not latest:
                return {'items':[],'next_cursor':None,'snapshot_id':None,'total':None}
            snapshot=latest['snapshot_id']
        rows,count=self.repository.entries(payer.id,period,snapshot,after,limit)
        more=len(rows)>limit;rows=rows[:limit]
        next_cursor=None
        if more:
            data={'account':payer.id,'period':period,'snapshot':snapshot,'after':[rows[-1]['day'],rows[-1]['id']]}
            next_cursor=base64.urlsafe_b64encode(json.dumps(data,separators=(',',':')).encode()).decode().rstrip('=')
        return {'items':rows,'next_cursor':next_cursor,'snapshot_id':snapshot,'total':count}

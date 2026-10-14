"""Provider normalization. Official fields only; missing amounts are not zero.

Sources and supported coverage are recorded with each snapshot. Ali resources
are monthly aggregates; RunPod REST covers three documented resource families,
not an asserted complete payer invoice. Neither is disguised as a charge event.
"""
from datetime import date, datetime, timedelta
import hashlib
import json
from zoneinfo import ZoneInfo

from .types import Balance, Bills, BillingError, amount, decimal, divide, entry, month_dates, subtract, total


def field(row, *names):
    for name in names:
        if row.get(name) is not None:
            return row[name]
    raise BillingError('invalid_provider_record')


def identity(value, payer):
    if str(value) != payer.payer_id:
        raise BillingError('payer_identity_mismatch')


def check_currency(row, payer, name='Currency'):
    if row.get(name) != payer.currency:
        raise BillingError('billing_currency_mismatch')


def aggregate_id(row, keys):
    """A documented aggregation key, not a guessed transactional identity."""
    return json.dumps([str(row.get(k,'')) for k in keys], ensure_ascii=False, separators=(',',':'))


def bill_day(value):
    try:
        parts = str(value).split(' ',1)[0].split('T',1)[0].replace('/','-').split('-')
        return date(*map(int,parts)).isoformat()
    except (ValueError, TypeError):
        raise BillingError('invalid_provider_record') from None


def volc_net(row,payer):
    # Both documented schema generations exist. Select an explicit matching
    # currency/field pair, never convert or fall back to an unrelated amount.
    if row.get('CurrencySettlement') == payer.currency and row.get('SettlePayableAmount') is not None:
        return field(row,'SettlePayableAmount')
    check_currency(row,payer)
    return field(row,'PayableAmount')


class ProviderReader:
    def __init__(self, transport, clock):
        self.transport, self.clock = transport, clock

    def balance(self, payer):
        client = self.transport.session(payer)
        if payer.provider == 'volc':
            if payer.site != 'cn' or payer.currency != 'CNY':
                raise BillingError('billing_source_unverified')
            row = client.cloud('QueryBalanceAcct')
            identity(field(row,'AccountID'),payer)
            components = {k: amount(row[k]) if row.get(k) is not None else None for k in ('CashBalance','CreditLimit','FreezeAmount','ArrearsBalance')}
            return Balance(amount(field(row,'AvailableBalance')),components,'QueryBalanceAcct.AvailableBalance')
        if payer.provider == 'ali':
            # Balance response has no payer ID. Verify the principal separately.
            overview = client.cloud('QueryBillOverview',{'BillingCycle':datetime.fromtimestamp(self.clock(),ZoneInfo(payer.timezone)).strftime('%Y-%m')})
            identity(field(overview,'AccountID'),payer)
            row = client.cloud('QueryAccountBalance')
            check_currency(row,payer)
            components = {k: amount(row[k]) if row.get(k) is not None else None for k in ('AvailableCashAmount','CreditAmount','MybankCreditAmount')}
            return Balance(amount(field(row,'AvailableAmount')),components,'QueryAccountBalance.AvailableAmount')
        if payer.provider == 'tencent':
            if payer.currency != ('USD' if payer.site=='international' else 'CNY'):
                raise BillingError('billing_currency_mismatch')
            row = client.cloud('DescribeAccountBalance')
            identity(field(row,'Uin'),payer)
            components = {k: amount(divide(row[k],100)) if row.get(k) is not None else None for k in ('CashAccountBalance','PresentAccountBalance','CreditAmount','FreezeAmount','OweAmount','RealCreditBalance')}
            return Balance(amount(divide(field(row,'RealBalance'),100)),components,'DescribeAccountBalance.RealBalance / 100')
        if payer.provider == 'runpod':
            if payer.currency != 'USD':
                raise BillingError('billing_currency_mismatch')
            row = client.runpod(query='query { myself { id clientBalance } }')
            identity(field(row,'id'),payer)
            return Balance(amount(field(row,'clientBalance')),{},'GraphQL.myself.clientBalance')
        raise BillingError('billing_source_unverified')

    def bills(self, payer, period):
        client = self.transport.session(payer)
        first, last = month_dates(period)
        today = datetime.fromtimestamp(self.clock(),ZoneInfo(payer.timezone)).date()
        # Billing delay exists. This window is explicitly labelled, never live.
        cutoff = min(last,today-timedelta(days=2))
        if payer.provider == 'ali':
            overview = client.cloud('QueryBillOverview',{'BillingCycle':period})
            identity(field(overview,'AccountID'),payer)
            summary = field(overview,'Items')['Item']
            for row in summary:
                check_currency(row,payer)
            official = total(field(row,'PretaxAmount') for row in summary)
            monthly = self.ali_pages(client,payer,period)
            entries = [self.ali_entry(row,payer,period+'-01','monthly_resource') for row in monthly]
            daily = []
            if cutoff >= first:
                start = max(first,cutoff-timedelta(days=6))
                day = start
                while day <= cutoff:
                    rows = self.ali_pages(client,payer,period,day.isoformat())
                    daily.append({'date':day.isoformat(),'amount':total(field(row,'PretaxAmount') for row in rows)})
                    day += timedelta(days=1)
            return Bills(entries,official,cutoff.isoformat() if cutoff>=first else None,'QueryBillOverview + DescribeInstanceBill','payer','official_summary',daily).validated(payer,period)
        if payer.provider == 'tencent':
            self.balance(payer)  # Verify the credential principal before billing.
            summary = client.cloud('DescribeBillSummaryByProduct',{'BeginTime':period,'EndTime':period})
            if summary.get('Ready') != 1:
                raise BillingError('official_summary_unavailable')
            official = amount(field(field(summary,'SummaryTotal'),'RealTotalCost'))
            rows = self.offset_pages(client,'DescribeBillDetail',{'Month':period,'NeedRecordNum':1},'DetailSet')
            entries = []
            for row in rows:
                identity(field(row,'PayerUin'),payer)
                components = field(row,'ComponentSet')
                net = total(field(c,'RealCost') for c in components)
                gross = total(field(c,'Cost') for c in components)
                day = bill_day(field(row,'BillDay'))
                identifier = field(row,'Id')
                resource = str(row.get('ResourceId') or '')
                entries.append(entry(identifier,day,row.get('BusinessCodeName') or row.get('BusinessCode'),net,resource=resource,gross=gross,discount=subtract(gross,net),payer=payer))
            return Bills(entries,official,cutoff.isoformat() if cutoff>=first else None,'DescribeBillSummaryByProduct + DescribeBillDetail').validated(payer,period)
        if payer.provider == 'volc':
            self.balance(payer)
            summary = client.cloud('ListBillOverviewByCategory',{'BillPeriod':period})
            summary_rows = field(summary,'List')
            # The official API also returns one exact List-only envelope.
            # Unwrap that observed shape once; mixed/deeper groups are unknown.
            if (isinstance(summary_rows,list) and len(summary_rows)==1
                    and isinstance(summary_rows[0],dict) and set(summary_rows[0])=={'List'}):
                summary_rows = summary_rows[0]['List']
            if not isinstance(summary_rows,list) or any(not isinstance(r,dict) or 'List' in r for r in summary_rows):
                raise BillingError('invalid_provider_record')
            totals = [r for r in summary_rows if r.get('BillCategoryParent') in {'合计','total','Total'}]
            if len(totals) != 1:
                raise BillingError('official_summary_unavailable')
            official = amount(volc_net(totals[0],payer))
            rows = self.offset_pages(client,'ListBillDetail',{'BillPeriod':period,'GroupTerm':0,'GroupPeriod':1,'NeedRecordNum':1},'List')
            entries = []
            for row in rows:
                identity(field(row,'PayerID'),payer)
                day = bill_day(field(row,'ExpenseDate'))
                provider_id=row.get('BillDetailId') or row.get('BillDetailID')
                identifier = provider_id or aggregate_id(row,['ExpenseDate','PayerID','OwnerID','InstanceNo','Product','BillCategory','BillingMode','ElementCode','ConfigName','RegionCode','ZoneCode','ConfigurationCode'])
                net=volc_net(row,payer)
                gross=row.get('OriginalBillAmount') if row.get('Currency')==payer.currency and row.get('SettlePayableAmount') is None else None
                entries.append(entry(identifier,day,row.get('ProductZh') or row.get('ProductName') or row.get('Product'),net,resource=str(row.get('InstanceNo') or ''),gross=gross,discount=None if gross is None else subtract(gross,net),granularity='daily_resource',provider_record_id=provider_id,payer=payer))
            return Bills(entries,official,cutoff.isoformat() if cutoff>=first else None,'ListBillOverviewByCategory + ListBillDetail').validated(payer,period)
        if payer.provider == 'runpod':
            self.balance(payer)
            params={'bucketSize':'day','startTime':first.isoformat()+'T00:00:00Z','endTime':last.isoformat()+'T23:59:59Z'}
            entries=[]
            for path,label in (('pods','Pod 计算与工作盘'),('endpoints','Serverless'),('networkvolumes','网络盘')):
                rows=client.runpod(path=path,params={**params,**({'grouping':'podId'} if path=='pods' else {'grouping':'endpointId'} if path=='endpoints' else {})})
                if not isinstance(rows,list):
                    raise BillingError('invalid_provider_record')
                for row in rows:
                    # Network-volume billing also returns startDate in the
                    # live schema. Never substitute query dates for missing
                    # evidence or silently choose conflicting date fields.
                    time_value=field(row,'time','startDate') if path=='networkvolumes' else field(row,'time')
                    day=bill_day(time_value)
                    if path=='networkvolumes' and row.get('time') is not None and row.get('startDate') is not None and bill_day(row['startDate'])!=day:
                        raise BillingError('billing_scope_mismatch')
                    resource=str(row.get('podId') or row.get('endpointId') or '')
                    identifier=aggregate_id({**row,'time':day+'T00:00:00Z'},['time','podId','endpointId','gpuTypeId'])+':'+path
                    entries.append(entry(identifier,day,label,field(row,'amount'),resource=resource,granularity='daily_resource',payer=payer))
            # These APIs do not establish coverage of public APIs, savings plans
            # or clusters. Do not invent an account total, zero delta or runway.
            return Bills(entries,None,None,'GraphQL identity + RunPod REST billing','supported_resources','coverage_unverified').validated(payer,period)
        raise BillingError('billing_source_unverified')

    def ali_pages(self,client,payer,period,day=None):
        params={'BillingCycle':period,'MaxResults':300,'Granularity':'DAILY' if day else 'MONTHLY','IsHideZeroCharge':'false'}
        if day:
            params['BillingDate']=day
        rows,tokens=[],set()
        while True:
            data=client.cloud('DescribeInstanceBill',params)
            identity(field(data,'AccountID'),payer)
            if data.get('BillingCycle') != period:
                raise BillingError('billing_scope_mismatch')
            page=field(data,'Items')
            if not isinstance(page,list):
                raise BillingError('invalid_provider_record')
            rows.extend(page)
            if len(rows)>100000:
                raise BillingError('billing_sync_limit')
            token=data.get('NextToken')
            if not token:
                break
            if token in tokens or not page:
                raise BillingError('incomplete_provider_pagination')
            tokens.add(token);params['NextToken']=token
        for row in rows:
            check_currency(row,payer)
        return rows

    @staticmethod
    def ali_entry(row,payer,day,granularity):
        key=aggregate_id(row,['BillAccountID','InstanceID','ProductCode','ProductType','CommodityCode','SubscriptionType','Item','BillingItemCode','OwnerID','Region','BizType'])
        net=field(row,'PretaxAmount');gross=field(row,'PretaxGrossAmount')
        return entry(key,day,row.get('ProductName') or row.get('ProductCode'),net,resource=str(row.get('InstanceID') or ''),gross=gross,discount=subtract(gross,net),granularity=granularity,payer=payer)

    @staticmethod
    def offset_pages(client,action,params,list_key):
        rows,offset,seen=[],0,set()
        while True:
            data=client.cloud(action,{**params,'Offset':offset,'Limit':300})
            page=field(data,list_key)
            if not isinstance(page,list):
                raise BillingError('invalid_provider_record')
            digest=hashlib.sha256(json.dumps(page,sort_keys=True,default=str).encode()).hexdigest()
            if page and digest in seen:
                raise BillingError('incomplete_provider_pagination')
            seen.add(digest);rows.extend(page)
            if len(rows)>100000:
                raise BillingError('billing_sync_limit')
            # Tencent Total is cached for 24h. Page until a short page instead
            # of stopping at a potentially stale count.
            if len(page)<300:
                break
            offset+=len(page)
        return rows

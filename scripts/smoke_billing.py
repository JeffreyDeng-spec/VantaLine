"""Financial contract tests. Synthetic credentials/data; no supplier network."""
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from local_inspection_service.analytics.billing.api import register_billing_api
from local_inspection_service.analytics.billing.providers import ProviderReader
from local_inspection_service.analytics.billing.service import BillingService
from local_inspection_service.analytics.billing.transport import FinancialSession, cloud_request
from local_inspection_service.analytics.billing.types import BillingError, Payer, amount, decimal, entry, payers, period_value
from local_inspection_service.auth.access import AccessControl
from local_inspection_service.runtime.identity import RequestIdentity

NOW=datetime.fromisoformat('2026-10-13T12:00:00+08:00').timestamp()


class Contracts(unittest.TestCase):
    def test_exact_money_configuration_identity_and_months(self):
        self.assertEqual(amount(decimal('.1')+decimal('.2')),'0.3')
        for invalid in (None, True, 'NaN','Infinity', '1e25'):
            with self.subTest(invalid=invalid),self.assertRaises(BillingError):decimal(invalid)
        self.assertEqual(len(payers({})),6)
        base={'provider':'ali','payer_id':'synthetic-payer','key_ref':'FINANCE_KEY','secret_ref':'FINANCE_SECRET'}
        a=next(p for p in payers({'VANTALINE_BILLING_ACCOUNTS_JSON':json.dumps([base])}) if p.provider=='ali' and not p.pending)
        b=next(p for p in payers({'VANTALINE_BILLING_ACCOUNTS_JSON':json.dumps([{**base,'alias':'renamed'}])}) if p.provider=='ali' and not p.pending)
        self.assertEqual(a.id,b.id)
        c=[p for p in payers({'VANTALINE_BILLING_ACCOUNTS_JSON':json.dumps([base,{**base,'payer_id':'different'}])}) if p.provider=='ali' and not p.pending]
        self.assertNotEqual(c[0].id,c[1].id)
        for values in ([base,base],[{**base,'key_ref':'https://invalid'}],[{**base,'secret':'never-accept-plaintext'}]):
            with self.assertRaises(BillingError):payers({'VANTALINE_BILLING_ACCOUNTS_JSON':json.dumps(values)})
        for value in ('2026-13','2026-11','2025-01','invalid'):
            with self.assertRaises(BillingError):period_value(value,NOW)

    def test_every_endpoint_authorizes_before_validation_or_storage(self):
        identity=RequestIdentity();access=AccessControl(identity)
        app=FastAPI();service=Mock()
        service.overview.return_value={'accounts':[]}
        service.detail.return_value={}
        service.entries.return_value={'items':[]}
        service.refresh.return_value={'job_ids':[]}
        service.repository.job.return_value={'id':'synthetic-job'}
        register_billing_api(app,access.require_admin_role,service)
        calls=[('GET','/api/admin/billing/overview',None),('GET','/api/admin/billing/accounts/synthetic',None),('GET','/api/admin/billing/accounts/synthetic/entries',None),('GET','/api/admin/billing/jobs/synthetic',None),('POST','/api/admin/billing/refresh',{})]
        client=TestClient(app)
        for user,expected in ((None,401),({'id':'normal','role':'user'},403),({'id':'settings-user','role':'user','permissions':['system_settings']},403),({'id':'admin-A','role':'admin'},200),({'id':'admin-B','role':'admin'},200)):
            service.reset_mock()
            with identity.bind(user):
                for method,path,data in calls:
                    response=client.request(method,path,json=data) if data is not None else client.request(method,path)
                    self.assertEqual(response.status_code,expected,response.text)
                    if expected==200:self.assertEqual(response.headers['Cache-Control'],'no-store')
                if expected!=200:
                    self.assertEqual(client.post('/api/admin/billing/refresh',json={'unknown':'field'}).status_code,expected)
                    self.assertEqual(client.get('/api/admin/billing/accounts/x/entries?limit=0').status_code,expected)
                    self.assertEqual(service.mock_calls,[])
        # Expiry removes the bound identity even if the caller retains old IDs.
        self.assertEqual(client.get('/api/admin/billing/accounts/synthetic').status_code,401)
        self.assertFalse(service.start.called)

    def test_read_only_queries_never_request_or_call_a_provider(self):
        repository=Mock();reader=Mock()
        service=BillingService({},repository,lambda _: '',clock=lambda:NOW,reader=reader)
        overview=service.overview()
        self.assertEqual(len(overview['accounts']),6)
        self.assertTrue(all(a['urgency']=='pending' and a['balance'] is None for a in overview['accounts']))
        service.detail('pending_codex')
        self.assertEqual(repository.mock_calls,[])
        self.assertEqual(reader.mock_calls,[])
        # A configured payer without secret references must explain why it is
        # pending, instead of waiting indefinitely under an ambiguous status.
        repository.latest.return_value=None;repository.sync.return_value=None
        configured={'VANTALINE_BILLING_ACCOUNTS_JSON':json.dumps([{'provider':'ali','payer_id':'synthetic-missing-key'}])}
        service=BillingService(configured,repository,lambda _: '',clock=lambda:NOW,reader=reader)
        account=next(a for a in service.overview()['accounts'] if a['provider']=='ali')
        self.assertEqual(account['reason'],'credentials_missing')
        self.assertIsNone(account['balance'])
        self.assertFalse(repository.request.called)
        self.assertEqual(reader.mock_calls,[])

    def test_provider_units_principal_and_no_silent_zero(self):
        client=Mock();transport=Mock();transport.session.return_value=client
        reader=ProviderReader(transport,lambda:NOW)
        payer=Payer('test','tencent','123','fixture',currency='CNY')
        client.cloud.return_value={'Uin':123,'RealBalance':'12345.678','CashAccountBalance':'12000'}
        result=reader.balance(payer)
        self.assertEqual(result.value,'123.45678')
        self.assertEqual(result.components['CashAccountBalance'],'120')
        client.cloud.return_value={'Uin':999,'RealBalance':'100'}
        with self.assertRaises(BillingError) as e:reader.balance(payer)
        self.assertEqual(e.exception.code,'payer_identity_mismatch')
        client.cloud.return_value={'Uin':123}
        with self.assertRaises(BillingError):reader.balance(payer)
        payer=Payer('runpod','runpod','rp','fixture',currency='USD')
        client.runpod.return_value={'id':'rp','clientBalance':Decimal('0.001')}
        self.assertEqual(reader.balance(payer).value,'0.001')

    def test_complete_provider_pagination_and_stale_count(self):
        client=Mock()
        first=[{'Id':str(i)} for i in range(300)]
        last=[{'Id':'300'}]
        client.cloud.side_effect=[{'DetailSet':first,'Total':1},{'DetailSet':last,'Total':1}]
        result=ProviderReader.offset_pages(client,'DescribeBillDetail',{},'DetailSet')
        self.assertEqual(len(result),301)
        self.assertEqual(client.cloud.call_args_list[1].args[1]['Offset'],300)
        client.cloud.side_effect=[{'DetailSet':first},{'DetailSet':first}]
        with self.assertRaises(BillingError):ProviderReader.offset_pages(client,'DescribeBillDetail',{},'DetailSet')
        payer=Payer('ali','ali','123','fixture')
        client.cloud.side_effect=[{'AccountID':'123','BillingCycle':'2026-10','Items':[{'Currency':'CNY','InstanceID':str(i)} for i in range(81)],'NextToken':'next'}, {'AccountID':'123','BillingCycle':'2026-10','Items':[{'Currency':'CNY','InstanceID':'82'}]}]
        self.assertEqual(len(ProviderReader(Mock(),lambda:NOW).ali_pages(client,payer,'2026-10')),82)
        self.assertEqual(client.cloud.call_args_list[-1].args[1]['NextToken'],'next')

    def test_transport_fixed_operations_and_error_redaction(self):
        payer=Payer('ali','ali','123',key_ref='KEY',secret_ref='SECRET')
        with self.assertRaises(BillingError):cloud_request(payer,'CreateInstance',{},'fixture','fixture',NOW)
        session=FinancialSession(payer,lambda _:'synthetic-secret')
        with patch('requests.Session') as requests:
            requests.return_value.__enter__.return_value.request.side_effect=RuntimeError('secret-url-token-private-host')
            with self.assertRaises(BillingError) as e:session.cloud('QueryAccountBalance')
            self.assertEqual(str(e.exception),'provider_unavailable')
            self.assertIs(requests.return_value.__enter__.return_value.trust_env,False)
            options=requests.return_value.__enter__.return_value.request.call_args.kwargs
            self.assertIs(options['allow_redirects'],False)

    def test_runpod_partial_scope_is_not_complete_account_cost(self):
        client=Mock();transport=Mock();transport.session.return_value=client
        client.runpod.side_effect=[{'id':'rp','clientBalance':'10'},[{'time':'2026-10-07T00:00:00Z','podId':'pod','amount':'1.23'}],[],[]]
        result=ProviderReader(transport,lambda:NOW).bills(Payer('rp','runpod','rp',currency='USD'),'2026-10')
        self.assertIsNone(result.official_total)
        self.assertIsNone(result.complete_until)
        self.assertEqual(result.scope,'supported_resources')
        self.assertEqual(result.entries[0]['granularity'],'daily_resource')


if __name__=='__main__':unittest.main()

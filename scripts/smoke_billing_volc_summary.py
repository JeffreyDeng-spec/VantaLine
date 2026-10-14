"""Official Volcengine summary envelopes; synthetic data, no supplier calls."""
from datetime import datetime
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from local_inspection_service.analytics.billing.providers import ProviderReader
from local_inspection_service.analytics.billing.types import BillingError,Payer,total

NOW=datetime.fromisoformat('2026-10-14T12:00:00+08:00').timestamp()


class VolcSummary(unittest.TestCase):
    def read(self, summary, *, rows=None):
        payer=Payer('fixture','volc','123',currency='CNY')
        client=Mock();transport=Mock();transport.session.return_value=client
        client.cloud.side_effect=[{'AccountID':'123','AvailableBalance':'10'}, {'List':summary}, {'List':rows or []}]
        return ProviderReader(transport,lambda:NOW).bills(payer,'2026-10')

    def test_flat_and_single_envelope_preserve_exact_total_without_double_count(self):
        rows=[{'BillCategoryParent':'合计','Currency':'CNY','PayableAmount':'0.2'},
              {'BillCategoryParent':'消费','Currency':'CNY','PayableAmount':'0.3'},
              {'BillCategoryParent':'退款','Currency':'CNY','PayableAmount':'-0.1'}]
        detail=[{'PayerID':'123','ExpenseDate':'2026-10-07','Currency':'CNY','PayableAmount':value,'BillDetailId':str(i),
                 'BillCategory':'consume-use' if i==0 else 'refund-terminate'}
                for i,value in enumerate(('0.3','-0.1'))]
        for summary in (rows,[{'List':rows}]):
            with self.subTest(summary=summary):
                bills=self.read(summary,rows=detail)
                self.assertEqual(bills.official_total,'0.2')
                self.assertEqual(total(r['net'] for r in bills.entries),'0.2')
                self.assertEqual(len(bills.entries),2)

    def test_explicit_settlement_currency_and_payer_validation_remain_required(self):
        row={'BillCategoryParent':'合计','Currency':'USD','PayableAmount':'99',
             'CurrencySettlement':'CNY','SettlePayableAmount':'1.234567'}
        self.assertEqual(self.read([{'List':[row]}]).official_total,'1.234567')
        for invalid in ({**row,'CurrencySettlement':'USD'}, {k:v for k,v in row.items() if k!='SettlePayableAmount'}):
            with self.assertRaises(BillingError) as error:self.read([{'List':[invalid]}])
            self.assertEqual(error.exception.code,'billing_currency_mismatch')
        detail=[{'PayerID':'other','ExpenseDate':'2026-10-07','Currency':'CNY','PayableAmount':'1'}]
        with self.assertRaises(BillingError) as error:self.read([{'List':[row]}],rows=detail)
        self.assertEqual(error.exception.code,'payer_identity_mismatch')

    def test_unknown_or_mixed_envelopes_are_rejected(self):
        row={'BillCategoryParent':'合计','Currency':'CNY','PayableAmount':'1'}
        for summary in (None,{},'unknown',[1],[{'List':None}],[{'List':{}}],
                        [{'List':[{'List':[row]}]}],[{'List':[row],'other':True}],
                        [{'List':[row]},row],[{'List':[row]},{'List':[row]}]):
            with self.subTest(summary=summary),self.assertRaises(BillingError) as error:self.read(summary)
            self.assertEqual(error.exception.code,'invalid_provider_record')

    def test_daily_aggregates_do_not_treat_shared_markers_as_record_ids(self):
        rows=[{'PayerID':'123','ExpenseDate':'2026-10-07','Currency':'CNY',
               'PayableAmount':'0.01','ConfigName':str(i),'BillDetailId':'aggregate-marker'} for i in range(81)]
        summary=[{'List':[{'BillCategoryParent':'合计','Currency':'CNY','PayableAmount':'0.81'}]}]
        bills=self.read(summary,rows=[*rows,rows[0]])
        self.assertEqual(len(bills.entries),81)
        self.assertEqual(total(r['net'] for r in bills.entries),'0.81')
        self.assertTrue(all(r['provider_record_id'] is None for r in bills.entries))
        with self.assertRaises(BillingError) as error:self.read(summary,rows=[rows[0],{**rows[0],'PayableAmount':'0.02'}])
        self.assertEqual(error.exception.code,'conflicting_provider_record')

    def test_missing_and_duplicate_totals_are_not_fabricated(self):
        row={'BillCategoryParent':'合计','Currency':'CNY','PayableAmount':'1'}
        for summary in ([],[{'List':[]}],[{'List':[{'BillCategoryParent':'消费'}]}],[{'List':[row,row]}]):
            with self.subTest(summary=summary),self.assertRaises(BillingError) as error:self.read(summary)
            self.assertEqual(error.exception.code,'official_summary_unavailable')


if __name__=='__main__':unittest.main()

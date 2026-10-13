"""RunPod live date compatibility, using synthetic financial records only."""
from datetime import datetime
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from local_inspection_service.analytics.billing.providers import ProviderReader
from local_inspection_service.analytics.billing.types import BillingError,Payer

NOW=datetime.fromisoformat('2026-10-13T12:00:00+00:00').timestamp()


class RunPodDates(unittest.TestCase):
    def read(self, volumes, endpoints=()):
        client=Mock();transport=Mock();transport.session.return_value=client
        client.runpod.side_effect=[{'id':'synthetic-payer','clientBalance':'10'},[],list(endpoints),volumes]
        return ProviderReader(transport,lambda:NOW).bills(Payer('synthetic','runpod','synthetic-payer',currency='USD'),'2026-10')

    def test_live_volume_date_variant_and_schema_independent_deduplication(self):
        rows=[{'startDate':'2026-10-07T00:00:00Z','amount':'0.123456789'},
              {'time':'2026-10-07T00:00:00Z','amount':'0.123456789'}]
        bills=self.read(rows,[{'time':'2026-10-07T00:00:00Z','endpointId':'synthetic-endpoint','amount':'1.2'}])
        self.assertEqual(len(bills.entries),2)
        volume=next(r for r in bills.entries if r['service']=='网络盘')
        self.assertEqual(volume['day'],'2026-10-07')
        self.assertEqual(volume['net'],'0.123456789')
        self.assertEqual(volume['project'],'unknown')
        self.assertEqual(bills.scope,'supported_resources')
        self.assertIsNone(bills.official_total)
        self.assertIsNone(bills.complete_until)

    def test_missing_invalid_conflicting_or_out_of_period_dates_fail_closed(self):
        for row in ({'amount':'1'},{'startDate':'unknown','amount':'1'},
                    {'startDate':'2026-09-30','amount':'1'},
                    {'time':'2026-10-07','startDate':'2026-10-08','amount':'1'}):
            with self.subTest(row=row),self.assertRaises(BillingError):self.read([row])
        with self.assertRaises(BillingError):
            self.read([], [{'startDate':'2026-10-07','amount':'1'}])

    def test_conflicting_same_day_amounts_reject_the_complete_snapshot(self):
        with self.assertRaises(BillingError) as error:
            self.read([{'startDate':'2026-10-07','amount':'1'},
                       {'time':'2026-10-07T00:00:00Z','amount':'2'}])
        self.assertEqual(error.exception.code,'conflicting_provider_record')


if __name__=='__main__':unittest.main()

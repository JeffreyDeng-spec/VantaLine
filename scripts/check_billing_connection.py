"""Explicit read-only supplier acceptance; never prints financial values/keys.

Provide server payer config/secret references and a private console snapshot
file. No Web application, database, queues, credentials or grants are created.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from local_inspection_service.analytics.billing.providers import ProviderReader
from local_inspection_service.analytics.billing.transport import FinancialTransport
from local_inspection_service.analytics.billing.types import BillingError,decimal,payers,period_value,total


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-file',type=Path,required=True,help='private official-console snapshot JSON; never commit it')
    parser.add_argument('--secret-env-file',type=Path,help='existing private runtime secret file; values never logged')
    args=parser.parse_args()
    try:
        if args.expected_file.stat().st_size>65536:
            raise ValueError()
        expected=json.loads(args.expected_file.read_text())
        if not isinstance(expected,list) or len(expected)>32:
            raise ValueError()
        secrets={}
        if args.secret_env_file:
            for line in args.secret_env_file.read_text().splitlines():
                if not line.strip() or line.lstrip().startswith('#') or '=' not in line:continue
                name,value=line.split('=',1)
                try:value=json.loads(value)
                except ValueError:value=value.strip().strip("'\"")
                if isinstance(value,str):secrets[name.strip()]=value
        secret=lambda name:os.environ.get(name) or secrets.get(name,'')
        reader=ProviderReader(FinancialTransport(secret),time.time)
        configured=[p for p in payers(os.environ) if not p.pending]
        reports=[]
        for payer in configured:
            match=next((row for row in expected if row.get('provider')==payer.provider and str(row.get('payer_id'))==payer.payer_id and row.get('site','cn')==payer.site),None)
            if not match:
                reports.append({'provider':payer.provider,'accepted':False,'code':'console_evidence_missing'});continue
            try:
                capture=datetime.fromisoformat(match['captured_at'].replace('Z','+00:00'))
                if capture.tzinfo is None or not 0<=time.time()-capture.timestamp()<=180:
                    raise BillingError('console_evidence_expired')
                period=period_value(match.get('period'),time.time())
                balance=reader.balance(payer)
                balance_at=datetime.now(timezone.utc).isoformat()
                balance_match=match.get('currency')==payer.currency and decimal(match['balance'])==decimal(balance.value)
                bills=reader.bills(payer,period).validated(payer,period)
                fee_match=None if bills.official_total is None else decimal(match['official_total'])==decimal(bills.official_total)
                complete=bills.scope=='payer' and bills.official_total is not None
                entries_match=None if bills.official_total is None else decimal(total(row['net'] for row in bills.entries))==decimal(bills.official_total)
                reports.append({'provider':payer.provider,'currency':payer.currency,'period':period,'balance_captured_at':balance_at,'bills_captured_at':datetime.now(timezone.utc).isoformat(),'balance_matches_console':balance_match,'official_total_matches_console':fee_match,'entries_match_official_total':entries_match,'complete_payer_coverage':complete,'accepted':balance_match and fee_match is True and entries_match is True and complete})
            except BillingError as exc:
                reports.append({'provider':payer.provider,'accepted':False,'code':exc.code})
            except Exception:
                reports.append({'provider':payer.provider,'accepted':False,'code':'console_evidence_invalid'})
        print(json.dumps({'configured_accounts':len(configured),'results':reports,'read_only':True},ensure_ascii=False))
        return 0 if reports and all(r['accepted'] for r in reports) else 2
    except Exception:
        print(json.dumps({'accepted':False,'code':'acceptance_configuration_invalid'}))
        return 2


if __name__=='__main__':raise SystemExit(main())

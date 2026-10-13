"""Fixed financial endpoints/actions only. No redirects, ambient proxy or retry.

Cloud signing follows the providers' public signing protocols. Secrets are used
only in memory; exceptions are reduced to fixed codes before leaving this port.
"""
import base64
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import time
from urllib.parse import quote, urlencode
import uuid

import requests
from .types import BillingError

ACTIONS = {
    "volc": {"QueryBalanceAcct", "ListBillOverviewByCategory", "ListBillDetail"},
    "ali": {"QueryAccountBalance", "QueryBillOverview", "DescribeInstanceBill"},
    "tencent": {"DescribeAccountBalance", "DescribeBillSummaryByProduct", "DescribeBillDetail"},
}


def sign(key, text, digest=hashlib.sha256):
    return hmac.new(key if isinstance(key, bytes) else key.encode(), text.encode(), digest).digest()


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def cloud_request(payer, action, params, key, secret, now):
    if action not in ACTIONS.get(payer.provider, ()):
        raise BillingError("unsupported_billing_operation")
    timestamp = datetime.fromtimestamp(now, timezone.utc)
    body = json.dumps(params, separators=(",", ":"), ensure_ascii=False)
    if payer.provider == "ali":
        host = "business.ap-southeast-1.aliyuncs.com" if payer.site == "international" else "business.aliyuncs.com"
        query = {**params,"Action":action,"Version":"2017-12-14","Format":"JSON","AccessKeyId":key,"SignatureMethod":"HMAC-SHA1","SignatureVersion":"1.0","SignatureNonce":uuid.uuid4().hex,"Timestamp":timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")}
        encode = lambda value: quote(str(value), safe="~")
        canonical = "&".join(f"{encode(k)}={encode(query[k])}" for k in sorted(query))
        query['Signature'] = base64.b64encode(sign(secret+'&', 'GET&%2F&'+encode(canonical), hashlib.sha1)).decode()
        return "GET", "https://"+host, {}, None, query
    if payer.provider == "tencent":
        host = "billing.intl.tencentcloudapi.com" if payer.site == "international" else "billing.tencentcloudapi.com"
        date = timestamp.strftime("%Y-%m-%d")
        scope = date+"/billing/tc3_request"
        canonical = 'POST\n/\n\ncontent-type:application/json; charset=utf-8\nhost:'+host+'\n\ncontent-type;host\n'+sha(body)
        signing = sign(sign(sign('TC3'+secret,date),'billing'),'tc3_request')
        signature = sign(signing,'TC3-HMAC-SHA256\n'+str(int(now))+'\n'+scope+'\n'+sha(canonical)).hex()
        headers = {'Content-Type':'application/json; charset=utf-8','Host':host,'X-TC-Action':action,'X-TC-Version':'2018-07-09','X-TC-Timestamp':str(int(now)), 'Authorization':f'TC3-HMAC-SHA256 Credential={key}/{scope}, SignedHeaders=content-type;host, Signature={signature}'}
        return "POST", "https://"+host, headers, body.encode(), None
    host = "open.byteplusapi.com" if payer.site == "international" else "open.volcengineapi.com"
    date, stamp = timestamp.strftime('%Y%m%d'), timestamp.strftime('%Y%m%dT%H%M%SZ')
    query = urlencode({'Action':action,'Version':'2022-01-01'})
    canonical_headers = f'content-type:application/json\nhost:{host}\nx-content-sha256:{sha(body)}\nx-date:{stamp}\n'
    signed = 'content-type;host;x-content-sha256;x-date'
    canonical = 'POST\n/\n'+query+'\n'+canonical_headers+'\n'+signed+'\n'+sha(body)
    scope = date+'/cn-north-1/billing/request'
    signing = sign(sign(sign(sign(secret,date),'cn-north-1'),'billing'),'request')
    signature = sign(signing,'HMAC-SHA256\n'+stamp+'\n'+scope+'\n'+sha(canonical)).hex()
    headers = {'Content-Type':'application/json','Host':host,'X-Date':stamp,'X-Content-Sha256':sha(body),'Authorization':f'HMAC-SHA256 Credential={key}/{scope}, SignedHeaders={signed}, Signature={signature}'}
    return "POST", "https://"+host+'/?'+query, headers, body.encode(), None


class FinancialTransport:
    def __init__(self, secret):
        self.secret = secret

    def session(self, payer):
        return FinancialSession(payer, self.secret)


class FinancialSession:
    def __init__(self, payer, secret):
        self.payer, self.secret = payer, secret
        self.started, self.last, self.calls = time.monotonic(), 0.0, 0

    def request(self, method, url, headers, body=None, params=None):
        self.calls += 1
        if self.calls > 300 or time.monotonic()-self.started > 480:
            raise BillingError("billing_sync_limit")
        gap = .26-(time.monotonic()-self.last)
        if gap > 0:
            time.sleep(gap)
        self.last = time.monotonic()
        try:
            with requests.Session() as client:
                client.trust_env = False
                with client.request(method,url,headers=headers,data=body,params=params,timeout=(5,12),allow_redirects=False,stream=True) as response:
                    if response.status_code in (401,403):
                        raise BillingError('provider_denied')
                    if response.status_code == 429:
                        raise BillingError('provider_rate_limited')
                    if response.status_code != 200:
                        raise BillingError()
                    parts, size = [], 0
                    for part in response.iter_content(65536):
                        size += len(part)
                        if size > 8*1024*1024 or time.monotonic()-self.started > 480:
                            raise BillingError('billing_sync_limit')
                        parts.append(part)
                    result = json.loads(b''.join(parts), parse_float=Decimal, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                    return result
        except BillingError:
            raise
        except Exception:
            raise BillingError() from None

    def credentials(self):
        key = self.secret(self.payer.key_ref) if self.payer.key_ref else ''
        secret = self.secret(self.payer.secret_ref) if self.payer.secret_ref else ''
        if not key or (self.payer.provider != 'runpod' and not secret):
            raise BillingError('credentials_missing')
        return key, secret

    def cloud(self, action, params=None):
        if action not in ACTIONS.get(self.payer.provider, ()):
            raise BillingError('unsupported_billing_operation')
        key, secret = self.credentials()
        request = cloud_request(self.payer,action,params or {},key,secret,time.time())
        result = self.request(*request)
        if not isinstance(result,dict):
            raise BillingError('invalid_provider_record')
        if self.payer.provider == 'ali':
            if result.get('Success') is not True:
                raise BillingError('provider_denied' if result.get('Code') in {'NotAuthorized','NoPermission','Forbidden'} else 'provider_unavailable')
            return result['Data']
        if self.payer.provider == 'tencent':
            response = result.get('Response',{})
            if response.get('Error'):
                raise BillingError('provider_unavailable')
            return response
        metadata = result.get('ResponseMetadata',{})
        if metadata.get('Error'):
            raise BillingError('provider_unavailable')
        return result['Result']

    def runpod(self, *, query=None, path=None, params=None):
        if self.payer.provider != 'runpod' or (query is not None and query != 'query { myself { id clientBalance } }'):
            raise BillingError('unsupported_billing_operation')
        key, _ = self.credentials()
        headers = {'Authorization':'Bearer '+key,'Content-Type':'application/json'}
        if query is not None:
            # This is a fixed read query, never a caller-provided GraphQL document.
            result = self.request('POST','https://api.runpod.io/graphql',headers,json.dumps({'query':query}).encode())
            if result.get('errors'):
                raise BillingError('provider_denied')
            return result['data']['myself']
        if path not in {'pods','endpoints','networkvolumes'}:
            raise BillingError('unsupported_billing_operation')
        return self.request('GET','https://rest.runpod.io/v1/billing/'+path,headers,params=params)

"""Single POST, bounded Responses transport, separate from label/pretraining clients."""
import json
import time
from urllib.parse import urlsplit, urlunsplit
import requests

_session = requests.Session()
_session.trust_env = False
_session.mount('https://', requests.adapters.HTTPAdapter(max_retries=0,pool_connections=2,pool_maxsize=2))
_last_finished = None
MAX_POOL_IDLE = 30


def invoke(payload, settings, evidence=None, before_send=None):
    global _last_finished
    evidence = evidence if evidence is not None else {}
    url=urlsplit(settings['base_url'])
    if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('explicit HTTPS provider endpoint required')
    path=url.path.rstrip('/')
    if path.endswith('/responses'):path=path[:-len('/responses')]
    if path.endswith('/chat/completions'):path=path[:-len('/chat/completions')]
    if not path.endswith('/api/v3'):raise ValueError('Ark v3 endpoint required')
    endpoint=urlunsplit((url.scheme,url.netloc,path+'/responses','',''))
    proxy=settings.get('proxy_url_raw')
    timeout=max(1,min(float(settings['timeout_seconds']),120))
    body=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode()
    start=time.monotonic()
    # urllib3 also applies the connect timeout to request-body writes. Do not
    # truncate a bounded image upload at the former ten-second connect limit.
    upload_timeout=min(30,timeout)
    idle_reset=_last_finished is not None and start-_last_finished>=MAX_POOL_IDLE
    if idle_reset:_session.close()
    evidence.update(api='responses',request_bytes=len(body),automatic_retries=0,proxy_configured=bool(proxy),
                    transport_stage='send_wait_headers',connect_upload_timeout_seconds=upload_timeout,
                    read_timeout_seconds=timeout,pool_idle_reset=idle_reset)
    try:
        if before_send is not None:before_send()
        # Bearer auth is per request; never propagate provider cookies across owners.
        _session.cookies.clear()
        with _session.post(endpoint,data=body,headers={'Authorization':'Bearer '+settings['api_key'],
                            'Content-Type':'application/json; charset=utf-8'},
                           proxies={'http':proxy,'https':proxy} if proxy else {},timeout=(upload_timeout,timeout),
                           allow_redirects=False,stream=True) as response:
            evidence.update(http_status=response.status_code,headers_seconds=time.monotonic()-start,transport_stage='read_body')
            chunks=[];total=0
            for chunk in response.iter_content(65536):
                total+=len(chunk)
                if total>1024*1024 or time.monotonic()-start>130:raise ValueError('provider response exceeds bound')
                chunks.append(chunk)
            evidence.update(response_bytes=total,transport_stage='complete')
            return response.status_code,b''.join(chunks).decode('utf-8')
    except Exception:
        # Retire the connection for future explicit work; never replay this POST.
        _session.close()
        evidence['pool_failure_reset']=True
        raise
    finally:
        _last_finished=time.monotonic()
        evidence['transport_seconds']=_last_finished-start

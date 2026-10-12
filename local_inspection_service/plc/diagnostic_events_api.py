"""Best-effort browser diagnostics with independent storage and authenticated scope."""
import json
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from fastapi import HTTPException, Query, Request
from ..schemas.plc_diagnostics import PlcDiagnosticBatch, Code
from ..storage.plc_diagnostic_repository import PlcDiagnosticRepository

class DiagnosticAdmission:
    def __init__(self):
        self.windows = OrderedDict()

    def check(self, owner: str, operation: str):
        now = time.monotonic()
        key = (owner,operation)
        start,count = self.windows.pop(key,(now,0))
        if now-start>=60: start,count=now,0
        count += 1
        self.windows[key]=(start,count)
        while len(self.windows)>1024: self.windows.popitem(last=False)
        if count > (12 if operation=='write' else 60):
            raise HTTPException(429,'plc_diagnostic_rate_limited',headers={'Retry-After':'60'})

def diagnostic_enabled(environment: Mapping[str,str], user: dict) -> bool:
    if environment.get('VANTALINE_PLC_DIAGNOSTICS_ENABLED','1') != '1': return False
    accounts={s.strip().casefold() for s in environment.get('VANTALINE_PLC_DIAGNOSTIC_ACCOUNTS','jhc001').split(',') if s.strip()}
    return '*' in accounts or str(user.get('username','')).casefold() in accounts or str(user.get('id','')).casefold() in accounts

def register_diagnostic_events(app, *, environment: Mapping[str,str], current_user: Callable[[],dict], cookie_name: str = 'vantaline_plc_workstation', repository=None):
    store = repository or PlcDiagnosticRepository(environment)
    admission = DiagnosticAdmission()
    def actor():
        user=current_user()
        if user.get('role')!='admin' and not set(user.get('permissions') or []).intersection({'inspection','ai_detection'}):
            raise HTTPException(403,'Permission denied')
        return user

    @app.get('/api/plc/diagnostic-events/config')
    def config():
        user=actor()
        return {'enabled':diagnostic_enabled(environment,user),'account_id':user['id']}

    @app.post('/api/plc/diagnostic-events/batch')
    async def batch(request: Request):
        user=actor(); admission.check(user['id'],'write')
        if not diagnostic_enabled(environment,user): return {'accepted':[], 'enabled':False}
        # Stream cap applies even to chunked requests, before JSON/Pydantic parsing.
        raw=bytearray()
        async for chunk in request.stream():
            if len(raw)+len(chunk)>32768: raise HTTPException(413,'plc_diagnostic_batch_too_large')
            raw.extend(chunk)
        try:
            payload=PlcDiagnosticBatch.model_validate_json(bytes(raw))
        except Exception:
            raise HTTPException(422,'invalid_plc_diagnostic_events') from None
        accepted=await store.append(user,request.cookies.get(cookie_name,''),[e.model_dump() for e in payload.events])
        return {'accepted':accepted, 'enabled':True}

    @app.get('/api/plc/diagnostic-events')
    async def events(account: str=Query('',max_length=80),station: str=Query('',max_length=80),attempt: str=Query('',max_length=80),code: Code='',since: int=Query(0,ge=0),until: int=Query(0,ge=0),offset: int=Query(0,ge=0,le=10000)):
        user=actor(); admission.check(user['id'],'read')
        return await store.list(user,account=account,station=station,attempt=attempt,code=code,since=since,until=until,offset=offset)
    return store

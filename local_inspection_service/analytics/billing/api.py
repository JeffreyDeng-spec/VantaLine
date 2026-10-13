"""Endpoint-local role checks precede all financial storage and work admission."""
from collections.abc import Callable
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from .types import BillingError


class BillingRefreshRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    account_id: str | None=None
    period: str | None=None


def register_billing_api(app: FastAPI, require_admin: Callable, service):
    def guard():
        return require_admin()

    def call(response,fn,*args,**kwargs):
        response.headers['Cache-Control']='no-store'
        try:
            return fn(*args,**kwargs)
        except BillingError as exc:
            status=404 if exc.code=='billing_account_not_found' else 400 if exc.code in {'invalid_period','invalid_billing_cursor'} else 503
            raise HTTPException(status,exc.code) from None

    @app.get('/api/admin/billing/overview', dependencies=[Depends(guard)])
    def overview(response: Response,period: str | None=None):
        require_admin()
        return call(response,service.overview,period)

    @app.get('/api/admin/billing/accounts/{identifier}', dependencies=[Depends(guard)])
    def detail(identifier: str,response: Response,period: str | None=None):
        require_admin()
        return call(response,service.detail,identifier,period)

    @app.get('/api/admin/billing/accounts/{identifier}/entries', dependencies=[Depends(guard)])
    def entries(identifier: str,response: Response,period: str | None=None,cursor: str | None=None,limit: int=Query(50,ge=1,le=100),snapshot_id: str | None=None):
        require_admin()
        return call(response,service.entries,identifier,period,cursor,limit,snapshot_id)

    @app.post('/api/admin/billing/refresh', dependencies=[Depends(guard)])
    def refresh(payload: BillingRefreshRequest,response: Response):
        actor=require_admin()
        return call(response,service.refresh,payload.account_id,payload.period,str(actor['id']))

    @app.get('/api/admin/billing/jobs/{identifier}', dependencies=[Depends(guard)])
    def job(identifier: str,response: Response):
        require_admin()
        result=call(response,service.repository.job,identifier)
        if not result:
            raise HTTPException(404,'billing_job_not_found')
        return result

    def start_billing_sync():
        service.start()
    app.router.add_event_handler('startup',start_billing_sync)

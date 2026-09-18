"""HTTP registration for account-owned document classification."""
from fastapi import FastAPI, HTTPException
from .document_jobs import DocumentJobs
from .document_ports import DocumentAccess, DocumentRecords


def register(app: FastAPI, access: DocumentAccess, records: DocumentRecords, jobs: DocumentJobs):
    @app.post('/api/text-inspection/standards/{standard_id}/classify')
    def classify(standard_id: str):
        access.require_permission('inspection', detail='没有文字检验权限')
        owner, _ = access.owner()
        if not records.owned('standards', standard_id, owner):
            raise HTTPException(404, '标准不存在')
        jobs.start(standard_id, owner)
        return records.public(records.owned('standards', standard_id, owner))
    @app.delete('/api/text-inspection/standards/{standard_id}')
    def delete(standard_id: str):
        access.require_permission('inspection', detail='没有文字检验权限')
        owner, _ = access.owner()
        if not records.owned('standards', standard_id, owner):
            raise HTTPException(404, '标准不存在')
        return records.public(jobs.delete(standard_id, owner))
    return jobs

"""Authenticated discovery and durable operation inspection/cancellation.

This module does not expose arbitrary service dispatch or grant extra privileges.
Operation submission is deliberately absent until domain worker integration is
complete. A commissioning allowlist keeps the developing browser surface off.
"""
from __future__ import annotations
import os
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from .storage.agent_operations import AgentOperationsRepository, OperationConflict, OperationDenied


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: StrictInt = Field(ge=0)
    enabled: StrictBool
    budget: StrictInt = Field(ge=0,le=10**12)
    cloud_targets: list[str] = Field(default_factory=list,max_length=50)


class CancelOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: StrictInt = Field(ge=1)


def public_operation(value):
    # Inputs, provider credentials and attempt details never become tool logs.
    fields = ("id","kind","status","version","created_at","updated_at","external_job_id","actual_cost")
    return {key:value[key] for key in fields if key in value}


def register(namespace):
    def user():
        return namespace["current_auth_user"]()

    def repository():
        repo = namespace["runtime_postgres_repository_or_none"]()
        if repo is None:
            raise HTTPException(503,"Durable agent operations require PostgreSQL")
        return AgentOperationsRepository(repo)

    @namespace["app"].get("/api/agent/capabilities")
    def capabilities():
        account = user()
        allowlist = {value.strip() for value in os.environ.get("VANTALINE_WEBMCP_ACCOUNTS","").split(",") if value.strip()}
        # No new-table query on accounts outside the commissioning allowlist.
        if account["id"] not in allowlist:
            return {"enabled":False,"reason":"NOT_COMMISSIONED","account_id":account["id"],"operation_submission":False}
        policy = repository().policy(account["id"])
        return {"enabled":bool(policy and policy["enabled"]),"reason":None if policy and policy["enabled"] else "POLICY_DISABLED","account_id":account["id"],"permissions":account["permissions"],"policy_version":(policy or {}).get("version",0),"operation_submission":False}

    @namespace["app"].get("/api/agent/policy/{account_id}")
    def get_policy(account_id: str):
        namespace["require_admin_role"]()
        return repository().policy(account_id) or {"id":account_id,"version":0,"enabled":False,"budget":0,"reserved":0,"spent":0,"cloud_targets":[]}

    @namespace["app"].put("/api/agent/policy/{account_id}")
    def set_policy(account_id: str, request: PolicyUpdate):
        namespace["require_admin_role"]()
        if not namespace["find_user"](namespace["load_auth_store"](),account_id):
            raise HTTPException(404,"Account not found")
        try:
            return repository().set_policy(account_id,**request.model_dump())
        except OperationConflict as exc:
            raise HTTPException(409,str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc

    @namespace["app"].get("/api/operations/{operation_id}")
    def get_operation(operation_id: str):
        value = repository().get(user()["id"],operation_id)
        if not value:
            raise HTTPException(404,"Operation not found")
        return public_operation(value)

    @namespace["app"].post("/api/operations/{operation_id}/cancel")
    def cancel_operation(operation_id: str, request: CancelOperation):
        owner = user()["id"]
        repo = repository()
        if not repo.get(owner,operation_id):
            raise HTTPException(404,"Operation not found")
        try:
            return public_operation(repo.transition(owner,operation_id,expected_version=request.expected_version,event="cancel"))
        except OperationConflict as exc:
            raise HTTPException(409,str(exc)) from exc
        except OperationDenied as exc:
            raise HTTPException(403,str(exc)) from exc

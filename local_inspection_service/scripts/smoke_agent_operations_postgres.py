#!/usr/bin/env python3
"""Real PostgreSQL tests in a newly created disposable schema; never uses DATABASE_URL."""
from __future__ import annotations
import concurrent.futures
import ast
import json
import os
from pathlib import Path
import sys
import uuid
from types import SimpleNamespace
from typing import Any

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import psycopg
from local_inspection_service.storage.agent_operations import AgentOperationsRepository, OperationConflict, OperationDenied
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.runtime_records import auth_user_rows, auth_session_rows, auth_store_from_rows, session_key_hash


def rejects(kind, call):
    try:
        call()
    except kind:
        return
    raise AssertionError(f"expected {kind.__name__}")


def main():
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    schema = "agent_test_"+uuid.uuid4().hex
    connection = psycopg.connect(dsn)
    try:
        connection.execute(postgres_ddl(schema))
        connection.commit()
        repository = PostgresRuntimeRepository(connection,"test",schema)
        operations = AgentOperationsRepository(repository)
        owner = "account-a"
        operations.set_policy(owner, expected_version=0, enabled=True, budget=100, cloud_targets=["configured-provider"])
        accepts = dict(kind="fixture_inspection",payload={"asset_id":"fixture"},idempotency_key="request-0001",reserve=30)

        def concurrent_accept(_):
            with psycopg.connect(dsn) as conn:
                repo = AgentOperationsRepository(PostgresRuntimeRepository(conn,"test",schema))
                return repo.accept(owner,**accepts)["id"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(concurrent_accept,range(16)))
        assert len(set(ids))==1
        assert operations.policy(owner)["reserved"]==30
        rejects(OperationConflict,lambda:operations.accept(owner,**{**accepts,"payload":{"asset_id":"different"}}))
        rejects(OperationDenied,lambda:operations.accept(owner,**{**accepts,"idempotency_key":"request-0002","reserve":80}))
        assert operations.get("account-b",ids[0]) is None
        op = operations.transition(owner,ids[0],expected_version=1,event="claim")
        rejects(OperationConflict,lambda:operations.transition(owner,ids[0],expected_version=1,event="claim"))
        operations.set_policy(owner,expected_version=1,enabled=False,budget=100,cloud_targets=[])
        rejects(OperationDenied,lambda:operations.transition(owner,op["id"],expected_version=op["version"],event="egress",provider_id="configured-provider"))
        operations.set_policy(owner,expected_version=2,enabled=True,budget=100,cloud_targets=["configured-provider"])
        op = operations.transition(owner,op["id"],expected_version=op["version"],event="egress",provider_id="configured-provider")
        rejects(OperationConflict,lambda:operations.transition(owner,op["id"],expected_version=op["version"],event="egress",provider_id="configured-provider"))
        op = operations.transition(owner,op["id"],expected_version=op["version"],event="cancel")
        assert op["status"]=="cancel_requested" and operations.policy(owner)["reserved"]==30
        op = operations.transition(owner,op["id"],expected_version=op["version"],event="unknown")
        assert operations.accept(owner,**accepts)["status"]=="outcome_unknown"
        rejects(OperationConflict,lambda:operations.transition(owner,op["id"],expected_version=op["version"],event="claim"))
        op = operations.transition(owner,op["id"],expected_version=op["version"],event="external_job",external_job_id="provider-job-1")
        op = operations.transition(owner,op["id"],expected_version=op["version"],event="complete",actual_cost=23)
        assert op["status"]=="completed"
        assert operations.policy(owner)["reserved"]==0 and operations.policy(owner)["spent"]==23
        rejects(OperationConflict,lambda:operations.transition(owner,op["id"],expected_version=op["version"],event="complete",actual_cost=23))
        pending = operations.accept(owner,**{**accepts,"idempotency_key":"cancel-before-claim"})
        operations.set_policy(owner,expected_version=3,enabled=False,budget=100,cloud_targets=[])
        pending = operations.transition(owner,pending["id"],expected_version=1,event="cancel")
        assert pending["status"]=="cancelled" and operations.policy(owner)["reserved"]==0
        assert all("payload" not in row["raw_json"] for row in repository.fetch_all("agent_operation_audit"))
        # Admission and audit are atomic when the audit insert fails.
        operations.set_policy(owner,expected_version=4,enabled=True,budget=100,cloud_targets=[])
        saved_audit = operations.audit
        def failure(*args): raise RuntimeError("simulated audit failure")
        operations.audit = failure
        rejects(RuntimeError,lambda:operations.accept(owner,**{**accepts,"idempotency_key":"rollback-request"}))
        operations.audit = saved_audit
        assert operations.policy(owner)["reserved"]==0

        # Exercise the actual HTTP module with fixture authentication and the
        # real disposable PostgreSQL repository. Full account auth has its own smoke.
        from contextvars import ContextVar
        from fastapi import FastAPI, HTTPException
        from fastapi.testclient import TestClient
        from local_inspection_service.agent_api import register
        app=FastAPI()
        principal=ContextVar("fixture_principal",default=None)
        accounts={owner:{"id":owner,"role":"admin","permissions":["agent_config","inspection"]},"account-b":{"id":"account-b","role":"user","permissions":["inspection"]}}
        def current_user():
            value=principal.get()
            if value is None: raise HTTPException(401,"Authentication required")
            return value
        def require_admin():
            if current_user()["role"]!="admin": raise HTTPException(403,"Admin role required")
        @app.middleware("http")
        async def fixture_auth(request,call_next):
            token=principal.set(accounts.get(request.headers.get("x-fixture-account")))
            try: return await call_next(request)
            finally: principal.reset(token)
        register({"app":app,"current_auth_user":current_user,"require_admin_role":require_admin,"runtime_postgres_repository_or_none":lambda:repository,"find_user":lambda store,key:accounts.get(key),"load_auth_store":lambda:accounts})
        with TestClient(app) as client:
            headers={"x-fixture-account":owner}
            assert client.get("/api/agent/capabilities").status_code==401
            assert client.get("/api/agent/capabilities",headers=headers).json()["enabled"] is False
            previous_allowlist=os.environ.get("VANTALINE_WEBMCP_ACCOUNTS")
            try:
                os.environ["VANTALINE_WEBMCP_ACCOUNTS"]=owner
                assert client.get("/api/agent/capabilities",headers=headers).json()["enabled"] is True
            finally:
                if previous_allowlist is None: os.environ.pop("VANTALINE_WEBMCP_ACCOUNTS",None)
                else: os.environ["VANTALINE_WEBMCP_ACCOUNTS"]=previous_allowlist
            assert client.get(f"/api/operations/{op['id']}",headers={"x-fixture-account":"account-b"}).status_code==404
            response=client.get(f"/api/operations/{op['id']}",headers=headers)
            assert response.status_code==200 and "payload" not in response.json()
            assert client.get(f"/api/agent/policy/{owner}",headers={"x-fixture-account":"account-b"}).status_code==403
            assert client.put(f"/api/agent/policy/{owner}",headers=headers,json={"expected_version":5,"enabled":True,"budget":-1,"cloud_targets":[]}).status_code==422
            assert client.post(f"/api/operations/{op['id']}/cancel",headers=headers,json={"expected_version":1}).status_code==409

        # Real primary-key authentication, legacy JSONB compatibility and revocation.
        user = {"id":owner,"username":"fixture","active":True,"role":"user","permissions":["inspection"],"password_hash":"fixture-only","created_at":1,"updated_at":1}
        session = {"user_id":owner,"created_at":1,"last_seen_at":10,"expires_at":1000}
        repository.upsert_row("users",auth_user_rows({"users":[user]})[0])
        session_row = auth_session_rows({"sessions":{"fixture-cookie":session}})[0]
        repository.upsert_row("auth_sessions",session_row)
        u,s,exists = repository.authenticate_session(session_key_hash("fixture-cookie"),now=100,ttl=500,persist_interval=30)
        assert exists and auth_store_from_rows([u],[s])["users"][0]["id"]==owner and s["expires_at"]==600
        legacy_user=auth_user_rows({"users":[user]})[0]
        legacy_user["raw_json"]=json.dumps(legacy_user["raw_json"])
        legacy_session={**session_row,"raw_json":json.dumps(session_row["raw_json"])}
        repository.upsert_row("users",legacy_user)
        repository.upsert_row("auth_sessions",legacy_session)
        u,s,_=repository.authenticate_session(session_key_hash("fixture-cookie"),now=100,ttl=500,persist_interval=30)
        assert auth_store_from_rows([u],[s])["users"][0]["id"]==owner and s["expires_at"]==600
        source=Path(__file__).resolve().parents[1]/"server.py"
        tree=ast.parse(source.read_text())
        functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in {"authenticate_request","find_user"}]
        namespace={"Any":Any,"Request":object,"time":SimpleNamespace(time=lambda:100),"runtime_postgres_repository_or_none":lambda:repository,"session_key_hash":session_key_hash,"auth_store_from_rows":auth_store_from_rows,"AUTH_SESSION_COOKIE":"fixture","AUTH_SESSION_TTL_SECONDS":500,"AUTH_SESSION_PERSIST_INTERVAL_SECONDS":30,"public_user":lambda value:{"id":value["id"]}}
        exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),"exec"),namespace)
        request=SimpleNamespace(cookies={"fixture":"fixture-cookie"})
        assert namespace["authenticate_request"](request,indexed=True)[0]["id"]==owner
        repository.upsert_row("users",{**legacy_user,"raw_json":json.dumps({**user,"active":False})})
        assert namespace["authenticate_request"](request,indexed=True)[0] is None
        repository.upsert_row("users",legacy_user)
        repository.upsert_row("auth_sessions",{**session_row,"raw_json":{**session_row["raw_json"],"user_id":"mismatched-account"}})
        assert namespace["authenticate_request"](request,indexed=True)[0] is None
        repository.upsert_row("auth_sessions",legacy_session)
        namespace["authenticate_request"](request,indexed=True)
        repository.upsert_row("users",{**legacy_user,"active":False})
        assert repository.authenticate_session(session_key_hash("fixture-cookie"),now=101,ttl=500,persist_interval=30)[0] is None
        repository.upsert_row("users",legacy_user)
        u,s,exists = repository.authenticate_session(session_key_hash("fixture-cookie"),now=601,ttl=500,persist_interval=30)
        assert u is None and s is None and exists
        connection.execute(f'DELETE FROM "{schema}".auth_sessions')
        connection.commit()
        assert repository.authenticate_session(session_key_hash("fixture-cookie"),now=100,ttl=500,persist_interval=30)[0] is None
        assert repository.count_rows(("auth_sessions",))["auth_sessions"]==0
        print("Agent PostgreSQL: concurrent idempotency, reservations, revocation, cancellation, unknown outcomes, audit rollback and indexed auth passed")
    finally:
        connection.rollback()
        connection.execute(f'DROP SCHEMA "{schema}" CASCADE')
        connection.commit()
        connection.close()


if __name__ == "__main__": main()

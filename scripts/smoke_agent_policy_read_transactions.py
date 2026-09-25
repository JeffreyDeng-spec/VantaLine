#!/usr/bin/env python3
"""Isolated PostgreSQL contract for the Agent policy display read."""
from __future__ import annotations

import concurrent.futures
import copy
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg.pq import TransactionStatus
from local_inspection_service.storage.agent_operations import AgentOperationsRepository, OperationConflict, OperationDenied
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl


def bounded(repo):
    conn = repo.repository.connection
    conn.execute("SET lock_timeout = '6000ms'")
    conn.execute("SET statement_timeout = '8000ms'")
    conn.commit()
    assert conn.info.transaction_status == TransactionStatus.IDLE


def advisory_wait(make, pid):
    monitor = make().repository.connection
    try:
        for _ in range(80):
            state = monitor.execute(
                'SELECT wait_event_type, wait_event FROM pg_stat_activity WHERE pid=%s',
                (pid,),
            ).fetchone()
            monitor.commit()
            if state == ('Lock', 'advisory'):
                return
            time.sleep(0.05)
        raise AssertionError('expected an actual account advisory-lock wait')
    finally:
        monitor.rollback()
        assert monitor.info.transaction_status == TransactionStatus.IDLE


def main():
    dsn = os.environ['AGENT_TEST_DATABASE_URL']
    schema = 'agent_policy_read_' + uuid.uuid4().hex
    connections = []
    with psycopg.connect(dsn) as setup:
        setup.execute(postgres_ddl(schema))

    def make():
        conn = psycopg.connect(dsn)
        connections.append(conn)
        return AgentOperationsRepository(PostgresRuntimeRepository(conn, 'test', schema))

    try:
        owner = 'account-a'
        repo = make()
        initial = repo.set_policy(owner, expected_version=0, enabled=True, budget=100, cloud_targets=[])
        assert initial['version'] == 1 and repo.policy(owner) == initial
        assert repo.policy('account-b') is None
        for falsey in (None, '', 0):
            try:
                repo.policy(falsey)
            except OperationDenied as exc:
                assert str(exc) == 'account required'
            else:
                raise AssertionError('falsey owner bypassed the original rejection')

        invalid = make()
        opened_invalid = []
        original_cursor = PostgresRuntimeRepository._cursor

        def track_invalid(self):
            cursor = original_cursor(self)
            if self is invalid.repository:
                opened_invalid.append(cursor)
            return cursor

        with patch.object(PostgresRuntimeRepository, '_cursor', track_invalid):
            with patch.object(invalid, 'read', side_effect=AssertionError('invalid owner reached SELECT')):
                try:
                    invalid.policy(1)
                except TypeError as exc:
                    assert str(exc) == 'can only concatenate str (not "int") to str'
                else:
                    raise AssertionError('truthy non-string owner changed behavior')
        assert opened_invalid[-1].closed
        assert invalid.repository.connection.info.transaction_status == TransactionStatus.IDLE

        writer = make()
        updated = copy.deepcopy(initial)
        updated.update(version=2, enabled=False)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with writer.transaction(owner) as cursor:
                writer.write(cursor, 'agent_policies', updated)
                reader = make()
                bounded(reader)
                old = pool.submit(reader.policy, owner)
                assert old.result(timeout=3) == initial
        assert repo.policy(owner) == updated

        reader = make()
        original_decode = PostgresRuntimeRepository._row_to_dict
        entered = threading.Event()
        release = threading.Event()

        def paused_decode(self, cursor, row):
            if self is reader.repository:
                entered.set()
                assert release.wait(3), 'decoder did not resume'
            return original_decode(self, cursor, row)

        with patch.object(PostgresRuntimeRepository, '_row_to_dict', paused_decode):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(reader.policy, owner)
                try:
                    assert entered.wait(3), 'nonempty policy read did not decode'
                    independent_writer = make()
                    independent_writer.repository.connection.execute("SET lock_timeout = '750ms'")
                    with independent_writer.transaction(owner) as cursor:
                        cursor.execute('SELECT 1')
                finally:
                    release.set()
                assert future.result(timeout=3) == updated

        failing = make()
        original_cursor = PostgresRuntimeRepository._cursor
        opened = []
        marker = RuntimeError('synthetic policy decode failure')

        def tracked_cursor(self):
            cursor = original_cursor(self)
            if self is failing.repository:
                opened.append(cursor)
            return cursor

        def fail_decode(self, cursor, row):
            if self is failing.repository:
                raise marker
            return original_decode(self, cursor, row)

        with patch.object(PostgresRuntimeRepository, '_cursor', tracked_cursor):
            with patch.object(PostgresRuntimeRepository, '_row_to_dict', fail_decode):
                try:
                    failing.policy(owner)
                except RuntimeError as exc:
                    assert exc is marker
                else:
                    raise AssertionError('decode failure was swallowed')
            assert failing.repository.connection.info.transaction_status == TransactionStatus.IDLE
            assert opened[-1].closed
            assert failing.policy(owner) == updated
            assert failing.repository.connection.info.transaction_status == TransactionStatus.IDLE
            assert opened[-1].closed
            assert failing.policy('account-b') is None
            assert failing.repository.connection.info.transaction_status == TransactionStatus.IDLE
            assert opened[-1].closed

        latest = copy.deepcopy(updated)
        latest['version'] = 3
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with writer.transaction(owner) as cursor:
                writer.write(cursor, 'agent_policies', latest)
                competing = make()
                bounded(competing)
                future = pool.submit(competing.set_policy, owner, expected_version=2,
                                     enabled=True, budget=100, cloud_targets=[])
                advisory_wait(make, competing.repository.connection.info.backend_pid)
                assert not future.done()
            try:
                future.result(timeout=3)
            except OperationConflict:
                pass
            else:
                raise AssertionError('set_policy ignored committed revision change')
        assert repo.policy(owner) == latest

        accepting_owner = 'account-accept'
        accept_repo = make()
        accept_repo.set_policy(accepting_owner, expected_version=0, enabled=True, budget=100, cloud_targets=[])
        accept_writer = make()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with accept_writer.transaction(accepting_owner) as cursor:
                policy = accept_writer.read(cursor, 'agent_policies', accepting_owner, accepting_owner)
                policy['version'] = 2
                policy['enabled'] = False
                accept_writer.write(cursor, 'agent_policies', policy)
                competing = make()
                bounded(competing)
                future = pool.submit(competing.accept, accepting_owner, kind='fixture',
                                     payload={'asset_id': 'synthetic'}, idempotency_key='policy-read-test-001', reserve=10)
                advisory_wait(make, competing.repository.connection.info.backend_pid)
                assert not future.done()
            try:
                future.result(timeout=3)
            except OperationDenied:
                pass
            else:
                raise AssertionError('admission ignored committed policy revocation')
        assert accept_repo.policy(accepting_owner)['enabled'] is False
        print('PASS Agent policy read: committed view, no read fence, rollback/IDLE, falsey owner, write/admission advisory waits')
    finally:
        for conn in connections:
            conn.close()
        with psycopg.connect(dsn) as cleanup:
            cleanup.execute(f'DROP SCHEMA "{schema}" CASCADE')


if __name__ == '__main__':
    main()

"""Real PostgreSQL post-settlement publication and row-lock contracts."""
import concurrent.futures
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.storage.label_inspection import LabelRepository
from local_inspection_service.storage.label_run_projection import LabelRunProjection
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl
from local_inspection_service.storage.runtime_selector import default_postgres_connector
from local_inspection_service.label_inspection.run_summary import VERSION, project


def main():
    schema='projection_publish_'+uuid.uuid4().hex[:12]
    dsn=os.environ['VANTALINE_POSTGRES_DSN']
    conns=[]
    created=False
    def execute(conn,sql,params=()):
        with conn.cursor() as c:
            c.execute(sql,params)
            return c.fetchall() if c.description else None
    def source(identity,status='completed',**fields):
        value=repo.new('alice','task','run',identity,id=identity,status=status,created_at=1.75,
                       quality={'synthetic':'x'*8192},decision='MATCH',**fields)
        with repo.tx() as c:repo.put(c,value)
        return value
    def cached(identity):
        rows=execute(writer,f'SELECT projection_version,raw_json FROM {cache} WHERE id=%s',(identity,))
        writer.commit();return rows
    try:
        for _ in range(4):
            conns.append(default_postgres_connector(dsn))
        raws=[PostgresRuntimeRepository(c,'<synthetic>',schema_name=schema) for c in conns]
        writer,reader,other,observer=conns
        observer.autocommit=True
        repo=LabelRepository(raws[0]);store=LabelRunProjection(raws[1]);table=repo.table
        cache=raws[0]._qualified_table('label_run_projection')
        created=True
        execute(writer,postgres_ddl(schema));writer.commit()
        row=source('run')
        assert not store.publish('bob','run') and not store.publish('alice','missing')
        assert store.publish('alice','run')
        assert cached('run')==[(VERSION,{'id':'run','created_at':1.75,'status':'completed','decision':'MATCH'})]
        for status in ('queued','running','ready'):
            source('unsettled',status)
            assert not store.publish('alice','unsettled') and not cached('unsettled')
        for status in ('failed','interrupted'):
            source('ended',status)
            assert store.publish('alice','ended')
        source('bad',**{'import':None})
        assert not store.publish('alice','bad') and not cached('bad')
        source('large',extra='x'*(256*1024))
        assert not store.publish('alice','large') and not cached('large')
        # Source-changing old code removes the cache, including malformed input.
        execute(writer,f"UPDATE {table} SET raw_json='{{}}' WHERE id='run'");writer.commit()
        assert not cached('run') and not store.publish('alice','run')
        source('run');assert store.publish('alice','run')
        before=cached('run')
        execute(reader,"SELECT 1")
        try:store.publish('alice','run')
        except RuntimeError:pass
        else:raise AssertionError('active outer transaction was committed')
        assert reader.info.transaction_status==2;reader.rollback()
        reader.autocommit=True
        try:
            try:store.publish('alice','run')
            except RuntimeError:pass
            else:raise AssertionError('autocommit source lock accepted')
        finally:reader.autocommit=False
        assert cached('run')==before
        # Busy source is skipped, never waited on; old commit invalidates cache.
        execute(writer,f"UPDATE {table} SET updated_at=20 WHERE id='run'")
        assert not store.publish('alice','run')
        writer.rollback();assert cached('run')==before
        print('settled-only, owner, malformed/large fallback, old invalidation and transaction ownership passed',flush=True)

        source('queued','queued')
        entered=threading.Event();release=threading.Event()
        def held(*args):
            entered.set()
            assert release.wait(5)
            return project(*args)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with patch('local_inspection_service.storage.label_run_projection.project',held):
                future=pool.submit(store.publish,'alice','run')
                try:
                    assert entered.wait(3)
                    # The held projection row lock must not own the advisory fence.
                    execute(other,"SET lock_timeout='100ms'");other.commit()
                    claimed=LabelRepository(raws[2]).claim()
                    assert claimed and claimed['id']=='queued'
                    execute(writer,"SET LOCAL lock_timeout='100ms'")
                    try:execute(writer,f"UPDATE {table} SET updated_at=21 WHERE id='run'")
                    except Exception as exc:assert exc.sqlstate=='55P03';writer.rollback()
                    else:raise AssertionError('source changed while proof was pending')
                finally:release.set()
                assert future.result(timeout=3)
        assert cached('run')==before
        execute(writer,f"UPDATE {table} SET status='failed' WHERE id='run'");writer.commit()
        assert not cached('run')
        # Proof failure rolls back and leaves the connection reusable.
        source('run')
        failure=RuntimeError('synthetic')
        opened=[];original_cursor=raws[1]._cursor
        def tracked_cursor(_):
            cursor=original_cursor();opened.append(cursor);return cursor
        with patch.object(PostgresRuntimeRepository,'_cursor',tracked_cursor), \
             patch('local_inspection_service.storage.label_run_projection.project',side_effect=failure):
            try:store.publish('alice','run')
            except RuntimeError as exc:assert exc is failure
            else:raise AssertionError('proof error was swallowed')
        assert opened[-1].closed and reader.info.transaction_status==0 and not cached('run')
        assert store.publish('alice','run')
        # Cache-row conflict times out and never mutates the business result.
        execute(writer,f"UPDATE {cache} SET projection_version=9 WHERE id='run'")
        try:store.publish('alice','run')
        except Exception as exc:assert exc.sqlstate=='55P03'
        else:raise AssertionError('cache lock timeout was not enforced')
        writer.rollback()
        assert reader.info.transaction_status==0 and cached('run')[0][0]==VERSION
        assert LabelRepository(raws[2]).get('alice','run')['status']=='completed'
        assert execute(reader,'SHOW lock_timeout')==[('0',)]
        reader.rollback()
        print('source-first proof, unrelated real claim progress, rollback/reuse and local timeout reset passed',flush=True)

        # Three participants: publisher row lock -> writer holding the global
        # advisory fence -> unrelated claim waiting indirectly on that writer.
        # A fourth read-only observer establishes actual PostgreSQL wait events.
        source('queued-chain','queued')
        entered.clear();release.clear()
        def blocked_writer():
            with repo.tx() as cursor:
                cursor.execute(f"UPDATE {table} SET updated_at=22 WHERE id='run'")
        def waiting(pid,events):
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                rows=execute(observer,'SELECT wait_event_type,wait_event FROM pg_stat_activity WHERE pid=%s',(pid,))
                if rows and rows[0][0]=='Lock' and rows[0][1] in events:return
                time.sleep(.005)
            raise AssertionError('Expected PostgreSQL lock wait was not observed')
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            with patch('local_inspection_service.storage.label_run_projection.project',held):
                projection=pool.submit(store.publish,'alice','run')
                try:
                    assert entered.wait(3)
                    update=pool.submit(blocked_writer)
                    waiting(writer.info.backend_pid,{'transactionid','tuple'})
                    # Restore default timeout from the preceding positive control.
                    execute(other,"SET lock_timeout='5s'");other.commit()
                    claim=pool.submit(LabelRepository(raws[2]).claim)
                    waiting(other.info.backend_pid,{'advisory'})
                    assert not update.done() and not claim.done()
                finally:release.set()
                assert projection.result(timeout=3)
                update.result(timeout=3)
                result=claim.result(timeout=3)
                assert result and result['id']=='queued-chain'
        assert not cached('run'), 'old writer must invalidate the freshly committed cache'
        print('indirect publisher -> globally fenced writer -> unrelated claim wait chain and recovery passed',flush=True)

    finally:
        pending=sys.exc_info()[0] is not None
        cleanup_error=None
        for conn in conns:
            try:conn.rollback()
            except Exception as exc:cleanup_error=cleanup_error or exc
        if created:
            try:
                with default_postgres_connector(dsn) as cleanup:
                    execute(cleanup,f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                    cleanup.commit()
            except Exception as exc:cleanup_error=cleanup_error or exc
        for conn in conns:
            try:conn.close()
            except Exception as exc:cleanup_error=cleanup_error or exc
        if cleanup_error is not None:
            if not pending:raise cleanup_error
            print('Additional fixture cleanup failure; original exception retained',file=sys.stderr)



if __name__=='__main__':main()

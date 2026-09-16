"""Candidate repair, persistence, lock and real HTTP side-effect contracts."""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from local_inspection_service.accessories.candidate_api import register_candidate_api
from local_inspection_service.accessories.candidate_queries import CandidateQueries, CandidateQueryDependencies
from local_inspection_service.accessories.candidate_repository import CandidateRepository, CandidateStoreDependencies
from local_inspection_service.auth.access import AccessControl
from local_inspection_service.records.access import RecordAccess
from local_inspection_service.records.audit import RecordAudit, record_created_at, record_updated_at
from local_inspection_service.records.ownership import RecordOwnership
from local_inspection_service.runtime.identity import RequestIdentity
from local_inspection_service.runtime.connections import ThreadRepositoryFactory
from local_inspection_service.storage.postgres_runtime_repository import PostgresRuntimeRepository
from local_inspection_service.storage.postgres_schema import postgres_ddl


class LockTrace:
    def __init__(self):
        self.lock, self.depth, self.events = threading.RLock(), 0, []

    @contextmanager
    def scope(self):
        with self.lock:
            self.depth += 1
            self.events.append(("enter", self.depth))
            try: yield
            finally:
                self.events.append(("exit", self.depth))
                self.depth -= 1

    def assert_released(self):
        assert self.depth == 0
        def acquire():
            acquired = self.lock.acquire(timeout=1)
            if acquired: self.lock.release()
            return acquired
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(acquire).result()


def repository(directory, *, runtime=lambda: None, repair=lambda _: False, trace=None):
    trace = trace or LockTrace()
    return CandidateRepository(CandidateStoreDependencies(
        runtime, lambda: directory, trace.scope, repair,
        lambda value: re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "record")).strip("._") or "record",
        record_created_at, record_updated_at))


class CandidateContracts(unittest.TestCase):
    def test_json_repair_and_atomic_file_failure(self):
        with tempfile.TemporaryDirectory(prefix="candidate-json-") as temporary:
            directory, trace, calls = Path(temporary), LockTrace(), []
            def repair(item):
                calls.append(("repair", trace.depth))
                if item.get("task_id"): return False
                item["task_id"] = "fixture-task"
                return True
            service = repository(directory, repair=repair, trace=trace)
            path = directory / "candidate.json"
            original = {"id": "candidate", "owner_user_id": "alice", "name": "合成 fixture"}
            service.save_accessory_candidate(path, original)
            self.assertEqual(path.read_text(encoding="utf-8"), json.dumps(original, indent=2))
            result = service.load_accessory_candidate("candidate")
            self.assertEqual(result["task_id"], "fixture-task")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), result)
            self.assertEqual(calls, [("repair", 1)])
            self.assertIn(("enter", 2), trace.events)
            self.assertFalse(path.with_name(".candidate.json.tmp").exists())
            before = path.read_text(encoding="utf-8")
            with patch("local_inspection_service.accessories.candidate_repository.os.replace", side_effect=OSError("synthetic replace failure")):
                with self.assertRaises(OSError): service.save_accessory_candidate(path, {"id": "replacement"})
            self.assertEqual(path.read_text(encoding="utf-8"), before)
            self.assertEqual(json.loads(path.with_name(".candidate.json.tmp").read_text()), {"id": "replacement"})
            trace.assert_released()
            self.assertEqual(service.accessory_candidate_record_path({"candidate_id": "..a/b.."}).name, "a_b.json")
            with self.assertRaises(HTTPException) as caught: service.load_accessory_candidate(" missing ")
            self.assertEqual((caught.exception.status_code, caught.exception.detail), (404, "Accessory candidate not found"))
            explicit = directory / "explicit.json"
            explicit.write_text("{}")
            self.assertTrue(service.delete_accessory_candidate(" different ", explicit))
            self.assertFalse(service.delete_accessory_candidate("different", explicit))
            self.assertFalse(service.delete_accessory_candidate(" ", path))
            self.assertTrue(path.exists())

    def test_json_listing_uses_file_order_and_only_skips_invalid_json(self):
        with tempfile.TemporaryDirectory(prefix="candidate-list-") as temporary:
            directory = Path(temporary)
            service = repository(directory)
            for name, mtime, payload in (("new", 300, '{"id":"new","updated_at":1}'), ("old", 100, '{"id":"old","updated_at":999}'), ("invalid", 200, '{bad'), ("scalar", 250, 'null')):
                path = directory / (name+".json")
                path.write_text(payload)
                os.utime(path, (mtime, mtime))
            self.assertEqual([p.stem for p, _ in service.list_accessory_candidate_records()], ["new", "scalar", "old"])
            self.assertIsNone(service.list_accessory_candidate_records()[1][1])
            self.assertEqual([p.stem for p, _ in service.list_accessory_candidate_records(reverse=False)], ["old", "scalar", "new"])
            with patch.object(Path, "read_text", side_effect=PermissionError("synthetic read denial")):
                with self.assertRaises(PermissionError): service.list_accessory_candidate_records()

    def test_pg_factory_lock_order_raw_ids_and_failure(self):
        with tempfile.TemporaryDirectory(prefix="candidate-fake-pg-") as temporary:
            directory, trace, events = Path(temporary), LockTrace(), []
            def fetch(table, key):
                events.append(("fetch", key["id"], trace.depth))
                return {"raw_json": {"id": key["id"]}}
            def write(table, row):
                events.append(("write", row["id"], trace.depth))
            selected = [SimpleNamespace(fetch_by_primary_key=fetch, upsert_row=write,
                                        delete_by_primary_key=lambda table, key: events.append(("delete", key["id"], trace.depth)))]
            def runtime():
                events.append(("runtime", trace.depth))
                return selected[0]
            def repair(item):
                events.append(("repair", trace.depth))
                item["task_id"] = "repaired"
                return True
            service = repository(directory, runtime=runtime, repair=repair, trace=trace)
            self.assertEqual(events, [])
            self.assertEqual(service.load_accessory_candidate(" spaced ")["id"], " spaced ")
            self.assertEqual(events, [("runtime", 0), ("fetch", " spaced ", 0), ("repair", 0), ("runtime", 1), ("write", "spaced", 1)])
            events.clear()
            self.assertTrue(service.delete_accessory_candidate(" spaced "))
            self.assertEqual(events, [("runtime", 1), ("fetch", "spaced", 1), ("delete", "spaced", 1)])
            self.assertEqual(list(directory.iterdir()), [])
            def failure(*args): raise RuntimeError("synthetic database failure")
            selected[0] = SimpleNamespace(upsert_row=failure, fetch_by_primary_key=failure)
            with self.assertRaises(RuntimeError): service.save_accessory_candidate(directory/'missing-id.json', {"name": "fixture"})
            with self.assertRaises(RuntimeError): service.load_accessory_candidate("missing")
            with self.assertRaises(RuntimeError): service.delete_accessory_candidate("missing")
            trace.assert_released()
            self.assertEqual(list(directory.iterdir()), [])

    def test_http_repair_before_guard_refresh_after_guard_and_lock_release(self):
        with tempfile.TemporaryDirectory(prefix="candidate-http-") as temporary:
            directory, trace, events = Path(temporary), LockTrace(), []
            identity, ownership = RequestIdentity(), RecordOwnership("legacy_admin", "system")
            auth = AccessControl(identity)
            access = RecordAccess(identity, ownership, auth.current_auth_user, lambda _: None)
            def repair(item):
                events.append(("repair", trace.depth))
                if item.get("task_id"): return False
                item["task_id"] = "synthetic-task"
                return True
            store = repository(directory, repair=repair, trace=trace)
            path = directory/'candidate.json'
            store.save_accessory_candidate(path, {"id": "candidate", "owner_user_id": "alice", "shared_with_user_ids": ["bob"], "jobs": [{"id": "job", "status": "running"}]})
            def guard(record, user=None, *, write=False):
                events.append(("guard", trace.depth))
                return access.require_record_access(record, user, write=write)
            def refresh(job):
                events.append(("refresh", trace.depth))
                return {**job, "status": "completed"}
            def save_job(candidate, job):
                events.append(("store_job", trace.depth))
                candidate["jobs"] = [job]
            queries = CandidateQueries(store, CandidateQueryDependencies(auth.current_auth_user,
                RecordAudit(ownership).enrich_record_audit_fields, guard,
                lambda item: item["jobs"], lambda *args: False, refresh, save_job))
            app = FastAPI()
            @app.middleware("http")
            async def bind(request: Request, call_next):
                name = request.headers.get("x-fixture-user")
                with identity.bind({"id": name, "role": "user"} if name else None):
                    return await call_next(request)
            register_candidate_api(app, queries)
            client = TestClient(app, raise_server_exceptions=False)
            self.assertEqual(client.get('/api/accessories/candidates/candidate').status_code, 401)
            self.assertEqual(events, [])
            denied = client.get('/api/accessories/candidates/candidate', headers={"x-fixture-user": "stranger"})
            self.assertEqual((denied.status_code, denied.json()), (404, {"detail": "Resource not found"}))
            self.assertEqual(events, [("repair", 2), ("guard", 1)])
            self.assertEqual(json.loads(path.read_text())["task_id"], "synthetic-task")
            self.assertEqual(json.loads(path.read_text())["jobs"][0]["status"], "running")
            events.clear()
            allowed = client.get('/api/accessories/candidates/candidate', headers={"x-fixture-user": "bob"})
            self.assertEqual(allowed.json()["candidate"]["jobs"][0]["status"], "completed")
            self.assertEqual(events, [("repair", 2), ("guard", 1), ("repair", 1), ("refresh", 1), ("store_job", 1)])
            self.assertEqual(json.loads(path.read_text())["jobs"][0]["status"], "completed")
            with patch("local_inspection_service.accessories.candidate_repository.os.replace", side_effect=OSError("synthetic write failure")):
                self.assertEqual(client.get('/api/accessories/candidates/candidate', headers={"x-fixture-user": "alice"}).status_code, 500)
            trace.assert_released()
            self.assertEqual(client.get('/api/accessories/candidates/missing', headers={"x-fixture-user": "alice"}).status_code, 404)
            self.assertIsNone(identity.get())
            client.close()


    def test_refresh_and_store_fail_without_retry_or_final_save(self):
        with tempfile.TemporaryDirectory(prefix="candidate-errors-") as temporary:
            directory, trace, events = Path(temporary), LockTrace(), []
            def repair(candidate):
                if candidate.get("task_id"): return False
                candidate["task_id"] = "persisted-repair"
                return True
            store = repository(directory, repair=repair, trace=trace)
            path = directory / "candidate.json"
            initial = {"id": "candidate", "jobs": [{"id": "one"}, {"id": "two"}]}
            store.save_accessory_candidate(path, initial)
            def audit(candidate, path):
                events.append(("audit", trace.depth))
                return {**candidate, "audit_only": True}
            def refresh(job):
                events.append(("refresh", job["id"], trace.depth))
                return {**job, "updated": True}
            def fail_refresh(job):
                events.append(("refresh_failed", job["id"], trace.depth))
                raise RuntimeError("synthetic refresh failure")
            def fail_store(candidate, job):
                events.append(("store_failed", job["id"], trace.depth))
                raise RuntimeError("synthetic store failure")
            dependencies = CandidateQueryDependencies(lambda: {"id": "alice"}, audit,
                lambda *args: events.append(("guard", trace.depth)), lambda item: item["jobs"],
                lambda item, job: events.append(("ensure", job["id"], trace.depth)) or False,
                fail_refresh, fail_store)
            for selected, expected in ((dependencies, [("audit",1),("guard",1),("ensure","one",1),("refresh_failed","one",1)]),
                                       (replace(dependencies, refresh_image_job=refresh), [("audit",1),("guard",1),("ensure","one",1),("refresh","one",1),("store_failed","one",1)])):
                events.clear()
                with self.assertRaises(RuntimeError): CandidateQueries(store, selected).get_accessory_candidate("candidate")
                self.assertEqual(events, expected)
                self.assertEqual(json.loads(path.read_text()), {**initial, "task_id": "persisted-repair"})
                trace.assert_released()


def root_callback_contract():
    with tempfile.TemporaryDirectory(prefix="candidate-root-") as temporary:
        root = Path(temporary)
        (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=temporary, VANTALINE_DATA_STORE='json',
                          VANTALINE_LABEL_INSPECTION_ENABLED='false', LOCAL_INSPECTION_AUTO_RESUME_WORKER='0')
        from local_inspection_service import server
        from local_inspection_service.scripts.model_profiles_fixture import install
        install(server)
        trace = LockTrace()
        store = repository(root/'candidates', repair=server.ensure_candidate_image_job_task_ids, trace=trace)
        anchor, guide = root/'anchor.png', root/'guide.png'
        anchor.write_bytes(b'synthetic anchor bytes')
        guide.write_bytes(b'synthetic guide bytes')
        queries = CandidateQueries(store, CandidateQueryDependencies(server.current_auth_user,
            server.enrich_record_audit_fields, server.require_record_access, server.candidate_image_jobs,
            server.ensure_image_job_task_id, lambda job: dict(job), server.store_candidate_image_job))
        old_binding = {'image': {'id': 'historical', 'version': 7, 'prompt_version': 'source-sha256:v1:fixture'}}
        with patch.object(server, 'POSE_TARGET_GUIDE_IMAGES', {'fixture': [guide]}):
            singular = {'generation_step':'anchor_replacement','status':'completed','pose_family':'fixture',
                        'anchor_image_path':str(anchor),'input_files':[str(anchor)],'model_profiles':copy.deepcopy(old_binding)}
            store.save_accessory_candidate(root/'candidates/legacy.json', {'id':'legacy','owner_user_id':'alice','codex_image_job':singular})
            with server._request_user.bind({'id':'alice','role':'user'}):
                response = queries.get_accessory_candidate('legacy')
            candidate = response['candidate']
            job = candidate['codex_image_job']
            assert job is candidate['codex_image_jobs'][0]
            assert job['job_id'] and job['task_id'] and job['candidate_id']=='legacy'
            assert job['anchor_image_basename']=='anchor.png' and job['anchor_image_sha256'] is None
            assert job['anchor_provenance']=='legacy_path_only' and job['target_guide_paths']==[str(guide)]
            assert job['model_profiles']==old_binding
            clean = {'id':'already','owner_user_id':'alice','codex_image_job':{'job_id':'job','candidate_id':'already','task_id':'stable'}}
            assert server.ensure_candidate_image_job_task_ids(clean) is False
            assert clean['codex_image_job'] is clean['codex_image_jobs'][0]
            original_alias = {'id':'already','owner_user_id':'alice','codex_image_job':{'job_id':'job','candidate_id':'already','task_id':'stable'}}
            alias_path = root/'candidates/already.json'
            store.save_accessory_candidate(alias_path, original_alias)
            loaded_alias = store.load_accessory_candidate('already')
            assert loaded_alias['codex_image_job'] is loaded_alias['codex_image_jobs'][0]
            assert 'codex_image_jobs' not in json.loads(alias_path.read_text())
            no_binding = {'id':'new','owner_user_id':'alice','codex_image_job':{'job_id':'new-job','candidate_id':'new','task_id':'new-task'}}
            store.save_accessory_candidate(root/'candidates/new.json', no_binding)
            with server._request_user.bind({'id':'alice','role':'user'}):
                new = queries.get_accessory_candidate('new')['candidate']
            assert new['codex_image_job']['model_profiles']==server.model_profile_service.snapshot()
            invalid = {'id':'invalid','codex_image_jobs':[None, 'invalid'], 'codex_image_job':{'job_id':'ignored'}}
            assert server.candidate_image_jobs(invalid)==[]
            assert server.ensure_candidate_image_job_task_ids(invalid) is False
            # Exercise the actual application composition and its lazy root
            # callbacks as well as the isolated service tested above.
            with patch.object(server, 'ACCESSORY_CANDIDATES_DIR', root/'assembled'), patch.object(server, 'refresh_codex_image_job', side_effect=lambda value: dict(value)):
                server.save_accessory_candidate(root/'assembled/wired.json',
                    {'id':'wired','owner_user_id':'alice','codex_image_job':{'job_id':'wired-job','task_id':'stable','candidate_id':'wired'}})
                with server._request_user.bind({'id':'alice','role':'user'}):
                    assembled = server.get_accessory_candidate('wired')['candidate']
                assert assembled['codex_image_job']['model_profiles']==server.model_profile_service.snapshot()
                assert json.loads((root/'assembled/wired.json').read_text())['codex_image_job']['model_profiles']==assembled['codex_image_job']['model_profiles']
                assert server._candidate_queries.repository is server._candidate_repository
                assert server._candidate_repository.dependencies.lock() is server._candidate_store_lock
        trace.assert_released()
    print('PASS actual root legacy image-job repair, guide provenance and immutable model freeze callbacks')


def postgres_contract(dsn):
    import psycopg
    from psycopg import sql
    schema, connections = 'candidate_' + uuid.uuid4().hex, []
    def connect():
        connection = psycopg.connect(dsn)
        connections.append(connection)
        return SimpleNamespace(store='postgres', repository=PostgresRuntimeRepository(connection, 'fixture', schema))
    factory = ThreadRepositoryFactory(connect, lambda: schema)
    with tempfile.TemporaryDirectory(prefix='candidate-pg-') as temporary, psycopg.connect(dsn, autocommit=True) as control:
        directory = Path(temporary)
        control.execute(postgres_ddl(schema))
        def repair(item):
            if item.get('task_id'): return False
            item['task_id'] = 'synthetic'
            return True
        store = repository(directory, runtime=lambda: factory.selection().repository, repair=repair)
        try:
            def write(index):
                with factory.thread_scope():
                    identity = f'candidate_{index:02d}'
                    store.save_accessory_candidate(directory/(identity+'.json'), {'id':identity,'owner_user_id':'alice','created_at':100,'updated_at':index+1})
                    assert store.load_accessory_candidate(identity)['task_id'] == 'synthetic'
            with ThreadPoolExecutor(max_workers=4) as pool: list(pool.map(write,range(20)))
            with factory.thread_scope():
                listed = store.list_accessory_candidate_records()
                assert len(listed)==20 and [r['id'] for _,r in listed]==[f'candidate_{i:02d}' for i in reversed(range(20))]
                assert [r['id'] for _,r in store.list_accessory_candidate_records(reverse=False)]==[f'candidate_{i:02d}' for i in range(20)]
                for identity, created in [('tie-a',10),('tie-b',10),('tie-c',9)]:
                    store.save_accessory_candidate(directory/(identity+'.json'), {'id':identity,'created_at':created,'updated_at':99})
                assert [r['id'] for _,r in store.list_accessory_candidate_records()][:3]==['tie-b','tie-a','tie-c']
                store.save_accessory_candidate(directory/'fallback.json', {'name':'no id','owner_user_id':'alice'})
                assert store.load_accessory_candidate('fallback')['name']=='no id'
                listed=store.list_accessory_candidate_records()
                assert any(path.name=='fallback.json' and record['id']=='fallback' for path,record in listed)
                raw=factory.selection().repository.fetch_by_primary_key('accessory_candidates',{'id':'fallback'})['raw_json']
                assert 'id' not in raw
                assert store.delete_accessory_candidate(' candidate_00 ')
                assert not store.delete_accessory_candidate('candidate_00')
            assert not list(directory.iterdir())
            assert all(c.closed for c in connections)
        finally:
            factory.clear()
            control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
    print('PASS isolated PostgreSQL candidate repair, listing, raw-ID fallback and thread cleanup')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--postgres', action='store_true')
    parser.add_argument('--root', action='store_true')
    args=parser.parse_args()
    result=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(CandidateContracts))
    if not result.wasSuccessful(): raise SystemExit(1)
    if args.postgres: postgres_contract(os.environ['VANTALINE_POSTGRES_DSN'])
    if args.root: root_callback_contract()

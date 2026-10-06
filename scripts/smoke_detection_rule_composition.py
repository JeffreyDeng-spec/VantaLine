"""Rule-domain composition, HTTP and per-app request isolation contracts."""
import asyncio
from contextvars import ContextVar
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from local_inspection_service.detection.rule_api import compose_detection_rule_api, RULE_PATHS
from local_inspection_service.detection.rule_request_ports import RulePolicy, RuleStore, RuleAccess


def fixture(owner, barrier=None):
    app = FastAPI()
    identity = ContextVar('rule-identity-' + owner, default=None)
    config, saved, observations = {}, [], []
    def user():
        value = identity.get()
        observations.append((value, threading.get_ident()))
        if barrier is not None:
            barrier.wait(timeout=10)
        return value
    @app.middleware('http')
    async def identity_scope(request, call_next):
        token = identity.set({'id': request.headers.get('x-test-user', owner)})
        try:
            return await call_next(request)
        finally:
            identity.reset(token)
    policy = RulePolicy(task_rule_id=lambda v: str(v or '').strip(), CLASS_NAMES={0: owner})
    store = RuleStore(load_config=lambda: config, save_config=lambda c: saved.append(c),
                      list_trained_model_specs=lambda c: [{'task_id':'one', 'owner':owner, 'selected_accessory_ids':[owner]}],
                      time=SimpleNamespace(time=lambda: 100))
    access = RuleAccess(current_auth_user=user, record_visible_to_user=lambda spec,u: spec['owner'] == u['id'])
    service = compose_detection_rule_api(app, policy=policy, store=store, access=access)
    return SimpleNamespace(**locals())


class Composition(unittest.TestCase):
    def test_construction_does_not_invoke_dependencies_and_duplicate_is_atomic(self):
        app = FastAPI()
        fail = Mock(side_effect=AssertionError('construction I/O'))
        policy = RulePolicy(task_rule_id=fail, CLASS_NAMES={})
        store = RuleStore(load_config=fail, save_config=fail, list_trained_model_specs=fail, time=SimpleNamespace(time=fail))
        access = RuleAccess(current_auth_user=fail, record_visible_to_user=fail)
        service = compose_detection_rule_api(app, policy=policy, store=store, access=access)
        self.assertIs(service.store, store)
        self.assertFalse(fail.called)
        before = list(app.routes)
        with self.assertRaisesRegex(ValueError, 'already registered'):
            compose_detection_rule_api(app, policy=policy, store=store, access=access)
        self.assertEqual(app.routes, before)
        second = FastAPI()
        second.post(RULE_PATHS[1])(lambda: None)
        before = list(second.routes)
        with self.assertRaises(ValueError):
            compose_detection_rule_api(second, policy=policy, store=store, access=access)
        self.assertEqual(second.routes, before)
        third = FastAPI()
        third.get(RULE_PATHS[0])(lambda: None)
        compose_detection_rule_api(third, policy=policy, store=store, access=access)
        self.assertFalse(fail.called)

    def test_two_apps_concurrent_identity_and_thread_scope(self):
        barrier = threading.Barrier(2)
        a, b = fixture('alice', barrier), fixture('bob', barrier)
        event_thread = threading.get_ident()
        async def run():
            async with AsyncClient(transport=ASGITransport(app=a.app), base_url='http://test') as ca, AsyncClient(transport=ASGITransport(app=b.app), base_url='http://test') as cb:
                for number in (2, 3):
                    responses = await asyncio.gather(ca.post(RULE_PATHS[1].format(task_id='one'), json={'confidence_threshold':.6, 'required_accessory_counts':{'alice':number, 'bob':9}}), cb.post(RULE_PATHS[1].format(task_id='one'), json={'confidence_threshold':.4, 'required_accessory_counts':{'bob':number, 'alice':9}}))
                    self.assertEqual([x.status_code for x in responses], [200,200])
                    self.assertEqual(responses[0].json()['rule']['required_accessory_counts'], {'alice':number})
                    self.assertEqual(responses[1].json()['rule']['required_accessory_counts'], {'bob':number})
        asyncio.run(run())
        self.assertEqual(a.config['task_rules']['one']['required_accessory_counts'], {'alice':3})
        self.assertEqual(b.config['task_rules']['one']['required_accessory_counts'], {'bob':3})
        self.assertIsNot(a.service, b.service)
        for f, owner in ((a,'alice'), (b,'bob')):
            self.assertEqual(len(f.saved), 2)
            self.assertIsNone(f.identity.get())
            self.assertTrue(all(u == {'id':owner} and tid != event_thread for u,tid in f.observations))

    def test_http_order_schema_errors_and_live_request_identity(self):
        f = fixture('alice')
        routes = [r for r in f.app.routes if getattr(r,'path',None) in RULE_PATHS]
        self.assertEqual([r.path for r in routes], list(RULE_PATHS))
        self.assertEqual([r.name for r in routes], ['update_rules','update_task_rules'])
        self.assertTrue(all(r.endpoint.__self__ is f.service for r in routes))
        schema = f.app.openapi()
        self.assertEqual(schema['paths'][RULE_PATHS[0]]['post']['operationId'], 'update_rules_api_config_rules_post')
        self.assertEqual(schema['paths'][RULE_PATHS[1]]['post']['operationId'], 'update_task_rules_api_config_task_rules__task_id__post')
        with TestClient(f.app) as c:
            valid = {'confidence_threshold':.5, 'required_accessory_counts':{'alice':2}}
            hidden = c.post(RULE_PATHS[1].format(task_id='one'), json=valid, headers={'x-test-user':'bob'})
            self.assertEqual((hidden.status_code, hidden.json()), (404, {'detail':'Detection task not found'}))
            self.assertEqual(f.saved, [])
            self.assertEqual(c.post(RULE_PATHS[1].format(task_id='one'), json=valid).status_code, 200)
            malformed = c.post(RULE_PATHS[0], json={})
            self.assertEqual(malformed.status_code, 422)
            self.assertEqual({v['loc'][-1] for v in malformed.json()['detail']}, {'confidence_threshold','required_classes','min_counts'})
            invalid = c.post(RULE_PATHS[0], json={'confidence_threshold':2, 'required_classes':[], 'min_counts':{}})
            self.assertEqual((invalid.status_code, invalid.json()), (400, {'detail':'confidence_threshold must be between 0 and 1'}))
            valid_global = c.post(RULE_PATHS[0], json={'confidence_threshold':.7, 'required_classes':[0], 'min_counts':{'0':0}})
            self.assertEqual(valid_global.status_code, 200)
            self.assertEqual(valid_global.json()['rule']['min_counts'], {'0':1})

    def test_self_lookup_and_fixed_method_dependencies(self):
        f = fixture('alice')
        self.assertFalse(hasattr(f.service.policy, 'task_rule_overrides'))
        with self.assertRaises(AttributeError):
            f.service.store.load_config = lambda: {}
        self.assertEqual(f.service.apply_task_rule_override_to_spec({'task_id':'one'}, {'task_rules':{'one':{'confidence_threshold':.8}}})['confidence_threshold'], .8)

    def test_actual_application_permissions_and_composition(self):
        # capture imports/assembles the full app in disposable storage, without lifespan.
        from scripts import verify_backend_contract as contract
        original_errors = contract.capture_http_errors
        def check_permissions(app):
            errors = original_errors(app)
            anonymous = TestClient(app, base_url='https://testserver')
            reader = TestClient(app, base_url='https://testserver')
            admin = TestClient(app, base_url='https://testserver')
            try:
                for client, username in ((reader,'contract-reader'), (admin,'contract-admin')):
                    self.assertEqual(client.post('/api/auth/login', json={'username':username,'password':'contract-fixture-password-only'}).status_code, 200)
                for path in (RULE_PATHS[0], RULE_PATHS[1].format(task_id='missing')):
                    self.assertEqual(anonymous.post(path, json={}).status_code, 401)
                    self.assertEqual(reader.post(path, json={}).status_code, 403)
                    self.assertEqual(admin.post(path, json={}).status_code, 422)
            finally:
                anonymous.close(); reader.close(); admin.close()
            return errors
        early = []
        def observe(frame, event, arg):
            if event == 'call' and frame.f_code.co_name in ('task_rule_overrides', 'apply_task_rule_override_to_spec') and frame.f_code.co_filename == str(ROOT/'local_inspection_service/server.py'):
                if '_detection_rule_requests' not in frame.f_globals:
                    early.append(frame.f_code.co_name)
        previous = sys.getprofile()
        try:
            sys.setprofile(observe)
            with patch.object(contract, 'capture_http_errors', check_permissions):
                snapshot = contract.capture()
        finally:
            sys.setprofile(previous)
        self.assertEqual(early, [])
        self.assertEqual(contract.encoded(snapshot), contract.BASELINE.read_text(encoding='utf-8'))
        from local_inspection_service import server
        from local_inspection_service.detection.rules import CountRules
        self.assertIsInstance(server._detection_rules, CountRules)
        service = server._detection_rule_requests
        selected = [r for r in server.app.routes if getattr(r,'path',None) in RULE_PATHS and 'POST' in getattr(r,'methods',())]
        self.assertEqual(len(selected), 2)
        self.assertTrue(all(r.endpoint.__self__ is service for r in selected))
        self.assertIs(service.store.list_trained_model_specs, server.list_trained_model_specs)
        self.assertIs(service.access.current_auth_user, server.current_auth_user)
        self.assertIs(server.update_rules.__self__, service)
        self.assertIs(server.update_task_rules.__self__, service)
        selected_loader = service.store.load_config
        with patch.object(server, 'load_config', Mock(side_effect=AssertionError('rebound loader'))), patch.object(server, 'task_rule_overrides', Mock(side_effect=AssertionError('rebound self lookup'))):
            self.assertIs(service.store.load_config, selected_loader)
            self.assertEqual(service.apply_task_rule_override_to_spec({}, {}), {'confidence_threshold':.25})



if __name__ == '__main__':
    unittest.main()

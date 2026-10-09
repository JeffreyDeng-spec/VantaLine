"""Authentication graph ownership and real HTTP composition contracts."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from local_inspection_service.auth.composition import AuthenticationServices, AuthenticationStorage, AuthenticationSettings
from local_inspection_service.auth.application import AuthenticationDomain
from local_inspection_service.auth.http_composition import AuthenticationHttp, AuthenticationHttpPolicy
from local_inspection_service.auth.policy import user_is_admin
from local_inspection_service.auth.sessions import SessionSettings
from local_inspection_service.auth.login_limits import LoginLimitSettings
from local_inspection_service.runtime.identity import RequestIdentity
from scripts import smoke_auth_api as existing


@contextmanager
def application(cookie):
    with tempfile.TemporaryDirectory(prefix='auth-composition-') as temporary, patch.dict(os.environ,{
            'VANTALINE_BOOTSTRAP_ADMIN_USERNAME':'','VANTALINE_BOOTSTRAP_ADMIN_PASSWORD':''}):
        root=Path(temporary)
        settings=[SessionSettings(cookie,500,30)]
        limits=[LoginLimitSettings(60,10,120)]
        domain=AuthenticationDomain(
            storage=AuthenticationStorage(lambda:root,lambda:root/'auth.json',lambda:None),
            settings=AuthenticationSettings(lambda:120000,lambda:settings[0],lambda:limits[0],lambda:'legacy'),
        )
        identity,graph=domain.identity,domain.services
        # Preserve the existing HTTP fault fixture's explicit PostgreSQL branch
        # substitute without changing the actual JSON repository used by it.
        postgres=[False]
        graph.flows.postgres=lambda:postgres[0]
        graph.users.postgres=lambda:postgres[0]
        app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
        http=domain.http(AuthenticationHttpPolicy(lambda *_:False,lambda *_:True,lambda *_:False))
        http.register_security(app)
        http.register_auth(app)
        http.register_users(app)
        http.register_documentation(app)
        with TestClient(app,base_url='https://testserver',raise_server_exceptions=False) as client:
            yield SimpleNamespace(client=client,app=app,repository=graph.repository,limiter=graph.limits,
                                  settings=settings,limits=limits,postgres=postgres,identity=identity,graph=graph,http=http)


class ExistingHttpContracts(existing.AuthApiContracts):
    """Keep all five existing assertion bodies, run them with the real composer."""
    def setUp(self):
        self.replacement=patch.object(existing,'application',application)
        self.replacement.start()
        self.addCleanup(self.replacement.stop)


class Composition(unittest.TestCase):
    def test_no_construction_io_shared_guard_and_distinct_graphs(self):
        fail=Mock(side_effect=AssertionError('constructor I/O'))
        storage=AuthenticationStorage(fail,fail,fail)
        settings=AuthenticationSettings(fail,fail,fail,fail)
        domains=[AuthenticationDomain(storage=storage,settings=settings) for _ in range(2)]
        a,b=(domain.services for domain in domains)
        self.assertIsNot(domains[0].identity,domains[1].identity)
        self.assertIs(a.access.identity,domains[0].identity)
        self.assertIs(b.access.identity,domains[1].identity)
        self.assertFalse(fail.called)
        for g in (a,b):
            self.assertIs(g.repository.dependencies.write_lock(),g.write_lock)
            self.assertIs(g.users.write_lock(),g.write_lock)
            self.assertIs(g.users.store,g.repository)
            self.assertIs(g.users.accounts,g.accounts)
            self.assertIs(g.users.access,g.access)
            self.assertIs(g.flows.store,g.repository)
            self.assertIs(g.flows.sessions,g.sessions)
            self.assertIs(g.flows.accounts,g.accounts)
            self.assertIs(g.flows.limits,g.limits)
            with g.write_lock:
                self.assertTrue(g.write_lock.acquire(blocking=False))
                g.write_lock.release()
                with ThreadPoolExecutor(1) as pool:
                    self.assertFalse(pool.submit(g.write_lock.acquire,False).result(timeout=5))
        self.assertIsNot(a.write_lock,b.write_lock)
        self.assertIsNot(a.limits.lock,b.limits.lock)
        a.limits.failures['one']=[100]
        self.assertEqual(b.limits.failures,{})

    def test_internal_methods_are_bound_and_external_suppliers_remain_live(self):
        calls=[]
        repository=[None]
        settings=[SessionSettings('first',10,3)]
        limits=[LoginLimitSettings(20,3,30)]
        def select():
            calls.append(threading.get_ident())
            return repository[0]
        g=AuthenticationServices(storage=AuthenticationStorage(lambda:Path('unused'),lambda:Path('unused/auth'),select),
            settings=AuthenticationSettings(lambda:12,lambda:settings[0],lambda:limits[0],lambda:'legacy'),identity=RequestIdentity())
        bindings=((g.accounts.dependencies.load_store,g.repository,'load_auth_store'),
                  (g.accounts.dependencies.save_store,g.repository,'save_auth_store'),
                  (g.accounts.dependencies.hash_password,g.hasher,'password_hash'),
                  (g.sessions.dependencies.load_store,g.repository,'load_auth_store'),
                  (g.sessions.dependencies.bootstrap_admin,g.accounts,'bootstrap_admin_from_env'),
                  (g.sessions.dependencies.save_touch_or_prune,g.repository,'save_auth_session_touch_or_prune'))
        for method,owner,name in bindings:
            self.assertIs(method.__self__,owner)
            self.assertEqual(method,getattr(owner,name))
        self.assertFalse(g.flows.postgres())
        repository[0]=object()
        self.assertTrue(g.users.postgres())
        self.assertIs(g.sessions.dependencies.runtime_repository(),repository[0])
        self.assertIs(g.repository.dependencies.runtime_repository(),repository[0])
        self.assertEqual(len(calls),4)
        settings[0]=SessionSettings('second',99,7)
        limits[0]=LoginLimitSettings(40,4,50)
        self.assertIs(g.sessions.settings(),settings[0])
        self.assertIs(g.limits.settings(),limits[0])
        failure=RuntimeError('factory failed')
        with patch.object(g.repository,'load_auth_store',Mock(side_effect=failure)):
            self.assertEqual(g.accounts.dependencies.load_store.__name__,'load_auth_store')
            self.assertNotEqual(g.accounts.dependencies.load_store,g.repository.load_auth_store)

    def test_async_http_enters_threads_with_isolated_identity_and_failure_reset(self):
        with application('alpha-cookie') as a, application('beta-cookie') as b:
            existing.bootstrap(a,'alpha-admin');existing.bootstrap(b,'beta-admin')
            self.assertEqual(a.client.get('/openapi.json').status_code,200)
            self.assertEqual(b.client.get('/openapi.json').status_code,200)
            self.assertIsNot(a.app.openapi_schema,b.app.openapi_schema)
            barrier=threading.Barrier(2)
            event_thread=threading.get_ident()
            observations=[]
            def make_endpoint(graph):
                def endpoint(fail:bool=False):
                    who=graph.access.current_auth_user()['username']
                    observations.append((who,threading.get_ident()))
                    barrier.wait(timeout=10)
                    if fail:
                        raise RuntimeError('synthetic request failure')
                    return {'user':who}
                return endpoint
            for f in (a,b):
                f.app.get('/api/auth/composition-probe')(make_endpoint(f.graph))
            async def run():
                async with AsyncClient(transport=ASGITransport(app=a.app,raise_app_exceptions=False),base_url='https://testserver',cookies=a.client.cookies) as ca, AsyncClient(transport=ASGITransport(app=b.app,raise_app_exceptions=False),base_url='https://testserver',cookies=b.client.cookies) as cb:
                    responses=await asyncio.gather(ca.get('/api/auth/composition-probe?fail=true'),cb.get('/api/auth/composition-probe'))
                    self.assertEqual([r.status_code for r in responses],[500,200])
                    self.assertEqual(responses[1].json(),{'user':'beta-admin'})
                    self.assertIsNone(a.identity.get());self.assertIsNone(b.identity.get())
                    responses=await asyncio.gather(ca.get('/api/auth/composition-probe'),cb.get('/api/auth/composition-probe'))
                    self.assertEqual([r.json()['user'] for r in responses],['alpha-admin','beta-admin'])
            asyncio.run(run())
            self.assertEqual(sorted(user for user,_ in observations),['alpha-admin','alpha-admin','beta-admin','beta-admin'])
            self.assertTrue(all(thread!=event_thread for _,thread in observations))

    def test_actual_root_graph_and_full_http_contract(self):
        from scripts import verify_backend_contract as contract
        snapshot=contract.capture()
        self.assertEqual(contract.encoded(snapshot),contract.BASELINE.read_text(encoding='utf-8'))
        from local_inspection_service import server
        g=server._authentication
        for name,field in {'_password_hasher':'hasher','_auth_repository':'repository','_account_service':'accounts','_session_service':'sessions','_access_control':'access','_login_limiter':'limits','_user_service':'users','_auth_flows':'flows'}.items():
            self.assertIs(getattr(server,name),getattr(g,field))
        self.assertIs(g.access.identity,server._request_user)
        self.assertFalse(hasattr(server,'_auth_store_write_lock'))
        self.assertEqual(server.load_auth_store,g.repository.load_auth_store)
        self.assertEqual(server.authenticate_request,g.sessions.authenticate_request)
        old=g.accounts.dependencies.load_store
        with patch.object(server,'load_auth_store',Mock(side_effect=AssertionError('root rebound'))):
            self.assertIs(g.accounts.dependencies.load_store,old)
        self.assertIs(server._authentication_domain.services,g)
        self.assertIs(server._authentication_domain.identity,server._request_user)
        self.assertEqual(g.sessions.dependencies.runtime_repository,
                         server._runtime_repository_owner.access.runtime_postgres_repository_or_none)
        original_path=g.repository.dependencies.auth_path()
        with patch.object(server,'AUTH_PATH',Path('/unused-rebound-auth')):
            self.assertEqual(g.repository.dependencies.auth_path(),original_path)
        with patch.object(server,'runtime_postgres_repository_or_none',Mock(side_effect=AssertionError('root repository rebound'))):
            self.assertIsNone(g.sessions.dependencies.runtime_repository())
        original=server.AUTH_SESSION_TTL_SECONDS
        with patch.object(server,'AUTH_SESSION_TTL_SECONDS',original+1):
            self.assertEqual(g.sessions.settings().ttl,original)
        current=g.sessions.settings()
        with patch.object(g.sessions,'settings',return_value=SessionSettings(current.cookie,original+1,current.persist_interval)):
            self.assertEqual(g.sessions.settings().ttl,original+1)


class HttpComposition(unittest.TestCase):
    def test_constructor_no_io_and_identity_mismatch(self):
        identity=RequestIdentity();fail=Mock(side_effect=AssertionError('constructor callback'))
        services=SimpleNamespace(access=SimpleNamespace(identity=identity),
            sessions=SimpleNamespace(authenticate_request=fail),accounts=SimpleNamespace(users_exist=fail))
        http=AuthenticationHttp(services,identity,AuthenticationHttpPolicy(fail,fail,fail))
        fail.assert_not_called()
        self.assertIs(http.security.authenticate,http.documentation.authenticate)
        self.assertIs(http.security.users_exist,http.documentation.users_exist)
        with self.assertRaises(ValueError):
            AuthenticationHttp(services,RequestIdentity(),AuthenticationHttpPolicy(fail,fail,fail))
        fail.assert_not_called()

    def test_two_actual_auth_graphs_have_distinct_routes_and_same_internal_bindings(self):
        with application('first-cookie') as a, application('second-cookie') as b:
            for fixture in (a,b):
                self.assertEqual(fixture.http.security.authenticate,fixture.graph.sessions.authenticate_request)
                self.assertEqual(fixture.http.security.users_exist,fixture.graph.accounts.users_exist)
                self.assertIs(fixture.http.security.identity,fixture.identity)
                route_keys=[(route.path,tuple(sorted(route.methods or ()))) for route in fixture.app.routes]
                self.assertEqual(len(route_keys),len(set(route_keys)))
            self.assertEqual([r.path for r in a.app.routes],[r.path for r in b.app.routes])
            self.assertTrue(all(x.endpoint is not y.endpoint for x,y in zip(a.app.routes,b.app.routes)))
            existing.bootstrap(a,'admin-one');existing.bootstrap(b,'admin-two')
            self.assertEqual(a.client.get('/api/auth/status').json()['user']['username'],'admin-one')
            self.assertEqual(b.client.get('/api/auth/status').json()['user']['username'],'admin-two')

    def test_real_root_security_does_not_reenter_compatibility_exports(self):
        from scripts import verify_backend_contract as contract
        contract.capture()
        from local_inspection_service import server
        http=server._authentication_http
        self.assertIs(http.services,server._authentication)
        self.assertIs(http.security.identity,server._request_user)
        self.assertIs(http.documentation,server._documentation_access)
        self.assertEqual(http.security.output_visible,server._account_projections.output_path_visible_to_user)
        self.assertEqual(http.security.same_origin,server._public_network_policy.same_origin)
        self.assertEqual(http.security.cors_origin_allowed,server._public_network_policy.cors_origin_allowed)
        from contextlib import ExitStack
        with ExitStack() as stack:
            for name in ('authenticate_request','users_exist','same_origin','cors_origin_allowed','require_docs_admin'):
                stack.enter_context(patch.object(server,name,Mock(side_effect=AssertionError('root compatibility export used'))))
            client=TestClient(server.app,base_url='https://testserver')
            try:
                self.assertEqual(client.get('/api/status').status_code,401)
                self.assertEqual(client.post('/api/auth/login',json={'username':'contract-admin','password':'contract-fixture-password-only'}).status_code,200)
                self.assertEqual(client.get('/openapi.json').status_code,200)
                self.assertEqual(client.post('/api/auth/logout',headers={'origin':'https://evil.invalid'}).status_code,403)
            finally:
                client.close()


def postgres_composition_contract(dsn):
    # Replay every established PostgreSQL repository assertion with the actual
    # composed repository. The factory retains a callable, never a connection.
    from scripts import smoke_auth_foundation as foundation
    graphs=[]
    released_after_failure=[]
    def compose(dependencies):
        domain=AuthenticationDomain(
            storage=AuthenticationStorage(dependencies.data_directory,dependencies.auth_path,dependencies.runtime_repository),
            settings=AuthenticationSettings(lambda:120000,lambda:SessionSettings('fixture',500,30),
                lambda:LoginLimitSettings(60,10,120),lambda:'legacy'))
        graph=domain.services
        assert graph.access.identity is domain.identity
        assert graph.repository.dependencies.write_lock() is graph.users.write_lock()
        assert graph.sessions.dependencies.runtime_repository is dependencies.runtime_repository
        original_save_login_session=graph.repository.save_login_session
        def save_login_session(*args,**kwargs):
            try:
                return original_save_login_session(*args,**kwargs)
            except RuntimeError:
                # The inherited fixture checks its own unused guard. Probe the
                # composed guard after the real method has fully unwound.
                def acquire_after_failure():
                    acquired=graph.write_lock.acquire(timeout=2)
                    if acquired:
                        graph.write_lock.release()
                    return acquired
                with ThreadPoolExecutor(max_workers=1) as pool:
                    released_after_failure.append(pool.submit(acquire_after_failure).result(timeout=3))
                assert released_after_failure[-1], 'composed auth guard leaked after write failure'
                raise
        graph.repository.save_login_session=save_login_session
        graphs.append(graph)
        return graph.repository
    with patch.object(foundation,'AuthRepository',compose):
        foundation.postgres_contract(dsn)
    assert len(graphs)==1
    assert released_after_failure==[True]
    print('PASS composed authentication real PostgreSQL account/session and reentrant persistence contracts')


if __name__=='__main__':
    postgres='--postgres' in sys.argv
    if postgres:
        sys.argv.remove('--postgres')
    result=unittest.main(exit=False)
    if not result.result.wasSuccessful():
        sys.exit(1)
    if postgres:
        postgres_composition_contract(os.environ['VANTALINE_POSTGRES_DSN'])

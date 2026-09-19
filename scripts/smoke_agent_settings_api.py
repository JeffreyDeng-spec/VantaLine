"""Offline contracts for the existing Agent configuration HTTP boundary."""
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import Mock,patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path.cwd()))

class AgentSettingsApiContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ);cls.environment.start()
        cls.root=tempfile.TemporaryDirectory(prefix='agent-settings-api-app-')
        (Path(cls.root.name)/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=cls.root.name,VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):
        cls.root.cleanup();cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for name in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):
            self.stack.enter_context(patch(name,side_effect=AssertionError('external operation forbidden')))
    @contextmanager
    def identity(self,role):
        token=self.api._request_user.set({'id':'synthetic-'+role,'role':role} if role else None)
        try:yield
        finally:self.api._request_user.reset(token)
    def client(self):
        # Use the real registered route objects, without application workers/lifespan.
        app=FastAPI();paths={'/api/agent/config','/api/agent/config/test','/api/agent/recommend'}
        app.router.routes.extend(route for route in self.api.app.routes if getattr(route,'path',None) in paths)
        return self.stack.enter_context(TestClient(app))
    def test_registered_route_methods_endpoint_identity_and_order(self):
        expected=[('/api/agent/config',{'GET'},'get_agent_config'),('/api/agent/config',{'POST'},'update_agent_config'),('/api/agent/config/test',{'POST'},'test_agent_config'),('/api/agent/recommend',{'POST'},'agent_recommend')]
        routes=[r for r in self.api.app.routes if getattr(r,'path','') in {p for p,_,_ in expected}]
        self.assertEqual([(r.path,r.methods,r.endpoint.__name__) for r in routes],expected)
        self.assertEqual(len(routes),4)
        for route in routes:
            self.assertIs(route.endpoint,getattr(self.api,route.endpoint.__name__))
            self.assertIs(route.dependant.call,route.endpoint)
    def test_read_requires_authentication_before_projection(self):
        with self.identity(''),patch.object(self.api,'public_agent_config') as projection:
            with self.assertRaises(self.api.HTTPException) as caught:self.api.get_agent_config()
        self.assertEqual((caught.exception.status_code,caught.exception.detail),(401,'Authentication required'));projection.assert_not_called()
    def test_read_rejects_member_before_projection(self):
        with self.identity('member'),patch.object(self.api,'public_agent_config') as projection:
            with self.assertRaises(self.api.HTTPException) as caught:self.api.get_agent_config()
        self.assertEqual((caught.exception.status_code,caught.exception.detail),(403,'Admin role required'));projection.assert_not_called()
    def test_read_admin_returns_existing_projection_identity(self):
        result={'synthetic':'projection'}
        with self.identity('admin'),patch.object(self.api,'public_agent_config',return_value=result) as projection:
            self.assertIs(self.api.get_agent_config(),result)
        projection.assert_called_once_with()
    def test_retired_write_and_probe_guard_before_any_old_side_effect(self):
        calls=[lambda:self.api.update_agent_config(self.api.AgentConfigRequest(api_key='synthetic')),self.api.test_agent_config]
        config=dict(self.api.DEFAULT_AGENT_CONFIG,provider='openai_compatible',base_url='https://synthetic.invalid',api_key='synthetic-previous',model='synthetic-model')
        names=('load_agent_config','save_agent_config','set_local_secret_env','test_agent_connection','public_agent_config')
        with ExitStack() as guards:
            spies=[guards.enter_context(patch.object(self.api,name,side_effect=lambda *args,**kwargs:dict(config))) for name in names]
            for role,status,detail in [('',401,'Authentication required'),('member',403,'Admin role required'),('admin',409,'请使用模型与 API 配置库；旧配置入口已停用')]:
                for call in calls:
                    with self.subTest(role=role,call=call),self.identity(role):
                        with self.assertRaises(self.api.HTTPException) as caught:call()
                        self.assertEqual((caught.exception.status_code,caught.exception.detail),(status,detail))
            for spy in spies:spy.assert_not_called()
    def test_recommend_stage_normalization_and_input_forwarding(self):
        result={'synthetic':'recommendation'}
        for stage,expected in [('samples','samples'),('training','training'),('other','samples')]:
            request=self.api.AgentRecommendRequest(stage=stage,accessory_ids=['synthetic-id'],sample_count=123)
            with patch.object(self.api,'agent_recommendation',return_value=result) as recommend:
                self.assertIs(self.api.agent_recommend(request),result)
            recommend.assert_called_once_with(expected,request.accessory_ids,123)
    def test_http_read_status_and_error_body_contract(self):
        client=self.client()
        for role,status,body in [('',401,{'detail':'Authentication required'}),('member',403,{'detail':'Admin role required'}),('admin',200,{'synthetic':'public'})]:
            with self.subTest(role=role),self.identity(role),patch.object(self.api,'public_agent_config',return_value={'synthetic':'public'}):
                response=client.get('/api/agent/config')
                self.assertEqual(response.status_code,status);self.assertEqual(response.json(),body)
    def test_http_retired_endpoints_return409_for_admin(self):
        client=self.client()
        with self.identity('admin'),patch.object(self.api,'save_agent_config') as save,patch.object(self.api,'test_agent_connection') as probe:
            for path in ('/api/agent/config','/api/agent/config/test'):
                response=client.post(path,json={})
                self.assertEqual(response.status_code,409);self.assertEqual(response.json(),{'detail':'请使用模型与 API 配置库；旧配置入口已停用'})
        save.assert_not_called();probe.assert_not_called()
    def test_http_request_validation_precedes_handler(self):
        client=self.client()
        with self.identity('admin'),patch.object(self.api,'require_admin_role') as admin,patch.object(self.api,'agent_recommendation') as recommend:
            response=client.post('/api/agent/config',json={'timeout_seconds':'not-a-number'})
            self.assertEqual(response.status_code,422)
            self.assertEqual(response.json()['detail'][0]['loc'],['body','timeout_seconds'])
            response=client.post('/api/agent/recommend',json={})
            self.assertEqual(response.status_code,422)
            self.assertEqual(response.json()['detail'][0]['loc'],['body','stage'])
        admin.assert_not_called();recommend.assert_not_called()
    def test_http_recommend_preserves_defaults_and_payload(self):
        client=self.client()
        with patch.object(self.api,'agent_recommendation',return_value={'stage':'samples','params':{}}) as recommend:
            response=client.post('/api/agent/recommend',json={'stage':'unknown'})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json(),{'stage':'samples','params':{}})
        recommend.assert_called_once_with('samples',[],None)

    def test_public_projection_is_resolved_after_authorization(self):
        before=Mock(return_value={'which':'before'});after=Mock(return_value={'which':'after'})
        def authorize():self.api.public_agent_config=after
        with patch.object(self.api,'require_admin_role',side_effect=authorize) as guard,patch.object(self.api,'public_agent_config',before):
            self.assertEqual(self.api.get_agent_config(),{'which':'after'})
        guard.assert_called_once();before.assert_not_called();after.assert_called_once_with()

    def test_authorization_failure_is_not_retried(self):
        error=RuntimeError('synthetic authorization unavailable');calls=[]
        def authorize():
            calls.append(None)
            if len(calls)==1:raise error
            return {'role':'admin'}
        with patch.object(self.api,'require_admin_role',side_effect=authorize),patch.object(self.api,'public_agent_config',return_value={'valid':'late'}) as projection:
            with self.assertRaises(RuntimeError) as caught:self.api.get_agent_config()
        self.assertIs(caught.exception,error);self.assertEqual(len(calls),1);projection.assert_not_called()

    def test_retired_error_factory_is_selected_after_authorization(self):
        original=self.api.HTTPException
        class SelectedHTTP(original):pass
        def authorize():self.api.HTTPException=SelectedHTTP
        calls=[lambda:self.api.update_agent_config(self.api.AgentConfigRequest()),self.api.test_agent_config]
        for call in calls:
            with self.subTest(call=call),patch.object(self.api,'require_admin_role',side_effect=authorize),patch.object(self.api,'HTTPException',original):
                with self.assertRaises(original) as caught:call()
            self.assertIs(type(caught.exception),SelectedHTTP);self.assertEqual(caught.exception.status_code,409)

    def test_recommendation_callback_capture_precedes_request_fields(self):
        selected=Mock(return_value={'which':'selected'});late=Mock(return_value={'which':'late'})
        api=self.api
        class Request:
            stage='training'
            sample_count=123
            @property
            def accessory_ids(self):
                api.agent_recommendation=late
                return ['synthetic-id']
        with patch.object(api,'agent_recommendation',selected):
            self.assertEqual(api.agent_recommend(Request()),{'which':'selected'})
        selected.assert_called_once_with('training',['synthetic-id'],123);late.assert_not_called()

    def test_projection_failure_propagates_without_retry(self):
        error=RuntimeError('synthetic projection failed');calls=[]
        def project():
            calls.append(None)
            if len(calls)==1:raise error
            return {'valid':'late'}
        with patch.object(self.api,'require_admin_role',return_value={'role':'admin'}),patch.object(self.api,'public_agent_config',side_effect=project):
            with self.assertRaises(RuntimeError) as caught:self.api.get_agent_config()
        self.assertIs(caught.exception,error);self.assertEqual(len(calls),1)


    def test_settings_api_constructor_does_not_read_capabilities(self):
        from dataclasses import fields
        from local_inspection_service.agent import settings_api_ports as p
        from local_inspection_service.agent.settings_api import AgentSettingsApi
        getters=[]
        def group(kind):
            values={f.name:Mock(return_value=None) for f in fields(kind)}
            getters.extend(values.values());return kind(**values)
        AgentSettingsApi(*(group(kind) for kind in (p.AgentSettingsHttpAccess,p.AgentSettingsProjectionCall,p.AgentRecommendationCall,p.AgentLegacySettingsPolicy,p.AgentLegacyKeyPolicy,p.AgentLegacySettingsEffects)))
        for getter in getters:getter.assert_not_called()

    def test_two_live_settings_api_instances_retain_their_capabilities(self):
        from dataclasses import fields
        from local_inspection_service.agent import settings_api_ports as p
        from local_inspection_service.agent.settings_api import AgentSettingsApi
        events=[]
        def group(kind,**selected):return kind(**{f.name:selected.get(f.name,lambda:None) for f in fields(kind)})
        def make(name):
            def admin():events.append((name,'admin'));return {'role':'admin'}
            def public(config=None):events.append((name,'public'));return {'instance':name}
            def recommend(stage,ids,count):events.append((name,'recommend'));return {'instance':name,'stage':stage,'ids':ids,'count':count}
            return AgentSettingsApi(group(p.AgentSettingsHttpAccess,admin=lambda:admin,http_error=lambda:self.api.HTTPException),group(p.AgentSettingsProjectionCall,public=lambda:public),group(p.AgentRecommendationCall,recommend=lambda:recommend),group(p.AgentLegacySettingsPolicy),group(p.AgentLegacyKeyPolicy),group(p.AgentLegacySettingsEffects))
        instances={name:make(name) for name in ('first','second')}
        with patch.object(self.api,'public_agent_config',side_effect=AssertionError('root projection')),patch.object(self.api,'agent_recommendation',side_effect=AssertionError('root recommendation')):
            for name in ('first','second','first'):
                with self.subTest(instance=name):
                    service=instances[name]
                    self.assertEqual(service.get_agent_config(),{'instance':name})
                    self.assertEqual(service.agent_recommend(self.api.AgentRecommendRequest(stage='training',accessory_ids=['synthetic'],sample_count=7)),{'instance':name,'stage':'training','ids':['synthetic'],'count':7})
        self.assertEqual(events,[(name,operation) for name in ('first','second','first') for operation in ('admin','public','recommend')])


if __name__=='__main__':unittest.main()

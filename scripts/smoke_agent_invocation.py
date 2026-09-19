"""Synthetic Agent invocation and recommendation contracts; no external calls."""
import copy
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path.cwd()))

class AgentInvocationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ);cls.environment.start()
        cls.root=tempfile.TemporaryDirectory(prefix='agent-invocation-app-')
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
        self.config={'enabled':True,'provider':'openai_compatible','base_url':'https://synthetic.invalid/v1','api_key':'synthetic-secret','model':'synthetic-model','timeout_seconds':37.0,'connection_status':'connected'}
    def response(self,body):
        response=Mock();response.read.return_value=json.dumps(body).encode();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        return response
    def test_url_auth_and_model_availability_helpers(self):
        self.assertEqual(self.api.openai_compatible_chat_url(' https://synthetic.invalid/v1/ '),'https://synthetic.invalid/v1/chat/completions')
        self.assertEqual(self.api.openai_compatible_models_url('https://synthetic.invalid/v1/chat/completions'),'https://synthetic.invalid/v1/models')
        self.assertEqual(self.api.cursor_auth_headers('synthetic'),{'Authorization':'Basic c3ludGhldGljOg=='})
        self.assertEqual(self.api.cursor_api_url('', '/v1/models'),'https://api.cursor.com/v1/models')
        self.assertTrue(self.api.cursor_model_available('ALIAS',[{'id':'x','aliases':['alias']}]))
        self.assertTrue(self.api.cursor_model_available('default',[]))
        self.assertFalse(self.api.cursor_model_available('missing',[{'id':'x'}]))
    def test_chat_payload_headers_timeout_and_trimmed_response(self):
        messages=[{'role':'user','content':'synthetic-input'}]
        with patch.object(self.api.urllib.request,'urlopen',return_value=self.response({'choices':[{'message':{'content':'  synthetic-output  '}}]})) as send:
            self.assertEqual(self.api.agent_openai_chat_completion(messages,self.config),'synthetic-output')
        request=send.call_args.args[0]
        self.assertEqual(request.full_url,'https://synthetic.invalid/v1/chat/completions')
        self.assertEqual(request.get_method(),'POST')
        self.assertEqual(request.get_header('Authorization'),'Bearer synthetic-secret')
        self.assertEqual(json.loads(request.data),{'model':'synthetic-model','messages':messages,'temperature':0.2})
        self.assertEqual(send.call_args.kwargs,{'timeout':37.0})
    def test_chat_guards_and_connected_override(self):
        with patch.object(self.api.urllib.request,'urlopen') as send:
            for change in ({'provider':'cursor','base_url':'https://api.cursor.com'},{'api_key':''},{'connection_status':'untested'}):
                with self.subTest(change=change),self.assertRaises(RuntimeError):
                    self.api.agent_openai_chat_completion([],{**self.config,**change})
            send.assert_not_called()
        with patch.object(self.api.urllib.request,'urlopen',return_value=self.response({'choices':[{'message':{'content':'ok'}}]})):
            self.assertEqual(self.api.agent_openai_chat_completion([],{**self.config,'connection_status':'untested'},require_connected=False),'ok')
    def test_chat_http_url_and_empty_result_errors(self):
        errors=[urllib.error.HTTPError('https://synthetic.invalid',429,'synthetic',{},io.BytesIO(b'synthetic detail')),urllib.error.URLError('synthetic unavailable')]
        for error in errors:
            with self.subTest(error=type(error).__name__),patch.object(self.api.urllib.request,'urlopen',side_effect=error) as send:
                with self.assertRaises(RuntimeError) as caught:self.api.agent_openai_chat_completion([],self.config)
                self.assertIs(caught.exception.__cause__,error)
                send.assert_called_once()
        with patch.object(self.api.urllib.request,'urlopen',return_value=self.response({})):
            with self.assertRaisesRegex(RuntimeError,'empty response'):self.api.agent_openai_chat_completion([],self.config)
    def test_bound_chat_preserves_model_settings_and_one_attempt(self):
        config={**self.config,'profile_id':'synthetic-profile','configuration_version':7}
        before=copy.deepcopy(config);messages=[{'role':'system','content':'system-a'},{'role':'user','content':'input'},{'role':'system','content':'system-b'}]
        with patch.object(self.api,'generate_provider_json_with_fallback',return_value=({'value':'synthetic'},None,None)) as generate,patch.object(self.api,'agent_openai_chat_completion') as legacy:
            self.assertEqual(json.loads(self.api.agent_chat_completion(messages,config)),{'value':'synthetic'})
        settings,system,content=generate.call_args.args
        self.assertEqual(settings,{**config,'base_url':'https://synthetic.invalid/v1/chat/completions'})
        self.assertEqual(system,'system-a\nsystem-b')
        self.assertEqual(content,[{'type':'text','text':'input'}])
        self.assertEqual(generate.call_args.kwargs,{'max_tokens':1400,'max_attempts':1})
        self.assertEqual(config,before);legacy.assert_not_called()
    def test_chat_uses_current_loader_and_legacy_fallback(self):
        with patch.object(self.api,'load_agent_config',return_value=self.config) as loader,patch.object(self.api,'agent_openai_chat_completion',return_value='synthetic') as legacy:
            self.assertEqual(self.api.agent_chat_completion([],{}),'synthetic')
        loader.assert_called_once_with();legacy.assert_called_once_with([],self.config,require_connected=True)
        with patch.object(self.api,'generate_provider_json_with_fallback') as generate:
            with self.assertRaises(RuntimeError):self.api.agent_chat_completion([],{**self.config,'profile_id':'synthetic','connection_status':'untested'})
            generate.assert_not_called()
    def test_model_discovery_request_and_projection(self):
        with patch.object(self.api.urllib.request,'urlopen',return_value=self.response({'data':[{'id':'synthetic-model','display_name':'Synthetic'}]})) as send:
            self.assertEqual(self.api.fetch_openai_compatible_model_options(self.config),[{'id':'synthetic-model','label':'synthetic-model · Synthetic'}])
        request=send.call_args.args[0]
        self.assertEqual(request.full_url,'https://synthetic.invalid/v1/models');self.assertEqual(request.get_method(),'GET')
        self.assertEqual(send.call_args.kwargs,{'timeout':37.0})
    def test_cursor_connection_filters_items_and_falls_back_to_auto(self):
        config={**self.config,'provider':'cursor','base_url':'https://api.cursor.com','model':'absent'}
        with patch.object(self.api.urllib.request,'urlopen',return_value=self.response({'items':[{'id':'model-a','aliases':['alias-a']},None]})) as send:
            result=self.api.test_cursor_agent_connection(config)
        self.assertEqual(result['model'],'auto');self.assertFalse(result['model_available']);self.assertEqual(result['last_model_count'],1)
        self.assertEqual(result['model_options'][0]['id'],'auto');self.assertIn('已切换为 auto',result['message'])
        self.assertEqual(send.call_args.args[0].full_url,'https://api.cursor.com/v1/models')
    def test_openai_connection_selects_discovered_model_and_preserves_warning(self):
        with patch.object(self.api,'fetch_openai_compatible_model_options',return_value=[{'id':'discovered','label':'Discovered'}]),patch.object(self.api,'agent_openai_chat_completion',return_value='ok') as chat:
            result=self.api.test_openai_agent_connection({**self.config,'model':''})
        self.assertEqual(result['model'],'discovered');self.assertEqual(result['last_model_count'],1)
        self.assertEqual(chat.call_args.kwargs,{'require_connected':False})
        with patch.object(self.api,'fetch_openai_compatible_model_options',side_effect=urllib.error.URLError('synthetic')),patch.object(self.api,'agent_openai_chat_completion',return_value='ok'):
            result=self.api.test_openai_agent_connection(self.config)
        self.assertIn('模型列表获取失败',result['message']);self.assertEqual(result['last_model_count'],0)
    def test_connection_provider_dispatch_and_json_parse(self):
        with patch.object(self.api,'test_cursor_agent_connection',return_value={'cursor':True}) as cursor,patch.object(self.api,'test_openai_agent_connection',return_value={'openai':True}) as openai:
            self.assertEqual(self.api.test_agent_connection(self.config),{'openai':True})
            self.assertEqual(self.api.test_agent_connection({**self.config,'base_url':'https://api.cursor.com'}),{'cursor':True})
        cursor.assert_called_once();openai.assert_called_once()
        self.assertEqual(self.api.parse_agent_json('```json\n{"x":1}\n```'),{'x':1})
        with self.assertRaisesRegex(RuntimeError,'did not contain JSON'):self.api.parse_agent_json('nothing')
    def test_rules_and_clamp_keep_context_and_bounds(self):
        with patch.object(self.api,'accessory_material_type',return_value='text'),patch.object(self.api,'selected_background_set_id',return_value='synthetic-background'):
            result=self.api.rule_recommendation('samples',[{'id':'synthetic'}])
        self.assertEqual(result['params'],{'sample_count':200,'train_mode':'yolo_ocr','background_set_id':'synthetic-background'})
        self.assertEqual(self.api.rule_recommendation('training',[],800)['params'],{'epochs':60,'image_size':640,'train_mode':'yolo'})
        fallback={'epochs':40,'image_size':640,'train_mode':'yolo'}
        self.assertEqual(self.api.clamp_recommend_params('training',{'epochs':999,'image_size':10,'train_mode':'invalid'},fallback),{'epochs':500,'image_size':320,'train_mode':'yolo'})
        self.assertEqual(fallback,{'epochs':40,'image_size':640,'train_mode':'yolo'})
    def test_recommendation_success_and_failure_return_rule_evidence(self):
        rules={'stage':'training','params':{'epochs':40,'image_size':640,'train_mode':'yolo'},'reason':'synthetic rule'}
        with patch.object(self.api,'load_config',return_value={}),patch.object(self.api,'selected_accessories',return_value=[]),patch.object(self.api,'rule_recommendation',return_value=rules),patch.object(self.api,'load_agent_config',return_value=self.config),patch.object(self.api,'agent_chat_completion',return_value='{"epochs":70,"reason":"synthetic reason"}') as chat:
            result=self.api.agent_recommendation('training',[],100)
        self.assertEqual(result,{'stage':'training','params':{'epochs':70,'image_size':640,'train_mode':'yolo'},'reason':'synthetic reason','source':'agent'})
        self.assertEqual(len(chat.call_args.args[0]),2)
        with patch.object(self.api,'load_config',return_value={}),patch.object(self.api,'selected_accessories',return_value=[]),patch.object(self.api,'rule_recommendation',return_value=rules),patch.object(self.api,'load_agent_config',return_value=self.config),patch.object(self.api,'agent_chat_completion',side_effect=RuntimeError('synthetic failure')) as chat:
            self.assertEqual(self.api.agent_recommendation('training',[],100),{**rules,'source':'rules','agent_error':'synthetic failure'})
        chat.assert_called_once()

    def test_request_factory_capture_precedes_url_callback(self):
        request_class=self.api.urllib.request.Request
        selected=Mock(side_effect=request_class);late=Mock(side_effect=request_class)
        def url(base):
            self.api.urllib.request.Request=late
            return 'https://synthetic.invalid/chat/completions'
        with patch.object(self.api.urllib.request,'Request',selected),patch.object(self.api,'openai_compatible_chat_url',url),patch.object(self.api.urllib.request,'urlopen',return_value=self.response({'choices':[{'message':{'content':'ok'}}]})):
            self.assertEqual(self.api.agent_openai_chat_completion([],self.config),'ok')
        selected.assert_called_once();late.assert_not_called()

    def test_send_callback_capture_precedes_timeout_subscription(self):
        selected=Mock(return_value=self.response({'choices':[{'message':{'content':'selected'}}]}))
        late=Mock(return_value=self.response({'choices':[{'message':{'content':'late'}}]}))
        api=self.api
        class Config(dict):
            def __getitem__(self,key):
                if key=='timeout_seconds':api.urllib.request.urlopen=late
                return super().__getitem__(key)
        with patch.object(api.urllib.request,'urlopen',selected):
            self.assertEqual(api.agent_openai_chat_completion([],Config(self.config)),'selected')
        selected.assert_called_once();late.assert_not_called()

    def test_json_decoder_capture_precedes_response_read(self):
        response=self.response({})
        decoder=json.loads
        selected=Mock(side_effect=decoder);late=Mock(side_effect=decoder)
        def read():
            self.api.json.loads=late
            return b'{"choices":[{"message":{"content":"selected"}}]}'
        response.read.side_effect=read
        with patch.object(self.api.json,'loads',selected),patch.object(self.api.urllib.request,'urlopen',return_value=response):
            self.assertEqual(self.api.agent_openai_chat_completion([],self.config),'selected')
        selected.assert_called_once();late.assert_not_called()

    def test_http_exception_class_is_resolved_after_send_failure(self):
        class ChangedHTTP(RuntimeError):
            code=499
            def read(self):return b'synthetic changed HTTP'
        error=ChangedHTTP('synthetic')
        def send(*args,**kwargs):
            self.api.urllib.error.HTTPError=ChangedHTTP
            raise error
        with patch.object(self.api.urllib.error,'HTTPError',self.api.urllib.error.HTTPError),patch.object(self.api.urllib.request,'urlopen',side_effect=send) as request:
            with self.assertRaisesRegex(RuntimeError,'HTTP 499') as caught:self.api.agent_openai_chat_completion([],self.config)
        self.assertIs(caught.exception.__cause__,error);request.assert_called_once()

    def test_unknown_paid_call_errors_are_not_retried(self):
        error=RuntimeError('synthetic unknown result');calls=[]
        def generate(*args,**kwargs):
            calls.append((args,kwargs))
            if len(calls)==1:raise error
            return {'valid':'later'},None,None
        with patch.object(self.api,'generate_provider_json_with_fallback',side_effect=generate),patch.object(self.api,'agent_openai_chat_completion',return_value='valid-late') as legacy:
            with self.assertRaises(RuntimeError) as caught:self.api.agent_chat_completion([],{**self.config,'profile_id':'synthetic-profile','configuration_version':7})
        self.assertIs(caught.exception,error);self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][0][0]['configuration_version'],7)
        self.assertEqual(calls[0][1],{'max_tokens':1400,'max_attempts':1});legacy.assert_not_called()
        calls.clear()
        def send(*args,**kwargs):
            calls.append(None)
            if len(calls)==1:raise error
            return self.response({'choices':[{'message':{'content':'later'}}]})
        with patch.object(self.api.urllib.request,'urlopen',side_effect=send):
            with self.assertRaises(RuntimeError) as caught:self.api.agent_openai_chat_completion([],self.config)
        self.assertIs(caught.exception,error);self.assertEqual(len(calls),1)

    def test_rule_background_callback_capture_and_request_identity_refresh(self):
        from types import SimpleNamespace
        selected=Mock(return_value='selected-background');late=Mock(return_value='late-background')
        account={'id':'synthetic-account'}
        def identity():
            self.api.selected_background_set_id=late
            return account
        with patch.object(self.api,'selected_background_set_id',selected),patch.object(self.api,'_request_user',SimpleNamespace(get=identity)):
            self.assertEqual(self.api.rule_recommendation('samples',[])['params']['background_set_id'],'selected-background')
        selected.assert_called_once_with(None,account);late.assert_not_called()
        seen=[]
        with patch.object(self.api,'selected_background_set_id',side_effect=lambda unused,user: seen.append(user['id']) or user['id']):
            for name in ('first','second','first'):
                token=self.api._request_user.set({'id':name})
                try:self.assertEqual(self.api.rule_recommendation('samples',[])['params']['background_set_id'],name)
                finally:self.api._request_user.reset(token)
        self.assertEqual(seen,['first','second','first'])
        with patch.object(self.api,'_request_user',SimpleNamespace(get=Mock(side_effect=AssertionError('training identity read')))):
            self.assertEqual(self.api.rule_recommendation('training',[],800)['params']['epochs'],60)

    def test_recommendation_exception_scope_and_no_inference_when_disabled(self):
        error=RuntimeError('synthetic selection failed')
        with patch.object(self.api,'load_config',return_value={}),patch.object(self.api,'selected_accessories',side_effect=error),patch.object(self.api,'rule_recommendation',return_value={'stage':'training','params':{},'reason':'synthetic'}) as rule,patch.object(self.api,'load_agent_config',return_value={**self.config,'enabled':False}) as load,patch.object(self.api,'agent_chat_completion',return_value='valid') as chat:
            with self.assertRaises(RuntimeError) as caught:self.api.agent_recommendation('training',[])
        self.assertIs(caught.exception,error);chat.assert_not_called();rule.assert_not_called();load.assert_not_called()
        rules={'stage':'training','params':{},'reason':'synthetic'}
        with patch.object(self.api,'load_config',return_value={}),patch.object(self.api,'selected_accessories',side_effect=self.api.HTTPException(404,'synthetic')),patch.object(self.api,'rule_recommendation',return_value=rules) as rule,patch.object(self.api,'load_agent_config',return_value={**self.config,'enabled':False}),patch.object(self.api,'agent_chat_completion') as chat:
            self.assertEqual(self.api.agent_recommendation('training',['missing']),{**rules,'source':'rules'})
        rule.assert_called_once_with('training',[],None);chat.assert_not_called()

    def test_unknown_discovery_failure_does_not_send_completion(self):
        error=RuntimeError('synthetic unknown discovery')
        with patch.object(self.api,'fetch_openai_compatible_model_options',side_effect=error) as fetch,patch.object(self.api,'agent_openai_chat_completion',return_value='valid') as chat:
            with self.assertRaises(RuntimeError) as caught:self.api.test_openai_agent_connection(self.config)
        self.assertIs(caught.exception,error);fetch.assert_called_once();chat.assert_not_called()

    def test_error_body_read_failure_escapes_once(self):
        error=RuntimeError('synthetic body unavailable');calls=[]
        class Body(io.BytesIO):
            def read(self,*args):
                calls.append(None)
                if len(calls)==1:raise error
                return b'valid late body'
        http=urllib.error.HTTPError('https://synthetic.invalid',429,'synthetic',{},Body())
        with patch.object(self.api.urllib.request,'urlopen',side_effect=http) as send:
            with self.assertRaises(RuntimeError) as caught:self.api.agent_openai_chat_completion([],self.config)
        self.assertIs(caught.exception,error);self.assertEqual(len(calls),1);send.assert_called_once()

    def test_recommendation_chat_capture_precedes_serializing_prompt(self):
        rules={'stage':'training','params':{'epochs':40,'image_size':640,'train_mode':'yolo'},'reason':'synthetic'}
        selected=Mock(return_value='{"epochs":70}');late=Mock(return_value='{"epochs":80}')
        encode=json.dumps
        def dumps(value,**kwargs):
            self.api.agent_chat_completion=late
            return encode(value,**kwargs)
        with patch.object(self.api,'load_config',return_value={}),patch.object(self.api,'selected_accessories',return_value=[]),patch.object(self.api,'rule_recommendation',return_value=rules),patch.object(self.api,'load_agent_config',return_value=self.config),patch.object(self.api,'agent_chat_completion',selected),patch.object(self.api.json,'dumps',side_effect=dumps):
            result=self.api.agent_recommendation('training',[],100)
        self.assertEqual(result['params']['epochs'],70);selected.assert_called_once();late.assert_not_called()
        self.assertIs(selected.call_args.args[1],self.config)
        self.assertEqual(json.loads(selected.call_args.args[0][1]['content'])['sample_count'],100)

    def test_recommendation_preserves_baseexception_identity(self):
        error=KeyboardInterrupt('synthetic signal only')
        rules={'stage':'training','params':{},'reason':'synthetic'}
        with patch.object(self.api,'load_config',return_value={}),patch.object(self.api,'selected_accessories',return_value=[]),patch.object(self.api,'rule_recommendation',return_value=rules),patch.object(self.api,'load_agent_config',return_value=self.config),patch.object(self.api,'agent_chat_completion',side_effect=error) as chat:
            with self.assertRaises(KeyboardInterrupt) as caught:self.api.agent_recommendation('training',[])
        self.assertIs(caught.exception,error);chat.assert_called_once()

    def test_bound_snapshot_and_real_accounting_boundary_run_once(self):
        from types import SimpleNamespace
        nested={'synthetic':'nested'}
        config={**self.config,'configured':True,'profile_id':'synthetic-profile','profile_version':7,'profile_purpose':'training_assistant','configuration_version':7,'snapshot_metadata':nested}
        before=copy.deepcopy(config)
        record=Mock(side_effect=RuntimeError('synthetic ledger unavailable'))
        body={'choices':[{'finish_reason':'stop','message':{'content':'{"answer":"synthetic"}'}}],'usage':{'total_tokens':9}}
        with patch.object(self.api,'ai_settings_match_runtime',return_value=False),patch.object(self.api,'ai_urlopen',return_value=self.response(body)) as send,patch.object(self.api,'_openai_profile_resolver',return_value=SimpleNamespace(record_call=record)),patch.object(self.api,'load_agent_config',side_effect=AssertionError('snapshot reload')),self.assertLogs('local_inspection_service.model_profiles.audit',level='WARNING'):
            self.assertEqual(json.loads(self.api.agent_chat_completion([{'role':'user','content':'synthetic'}],config)),{'answer':'synthetic'})
        send.assert_called_once();record.assert_called_once()
        settings,elapsed,ok,usage=record.call_args.args
        self.assertEqual((settings['profile_id'],settings['profile_version'],settings['profile_purpose']),('synthetic-profile',7,'training_assistant'))
        self.assertIs(settings['snapshot_metadata'],nested);self.assertIsNot(settings,config)
        self.assertEqual(config,before);self.assertTrue(ok);self.assertEqual(usage,{'total_tokens':9})


    def test_invocation_service_constructors_do_not_read_capabilities(self):
        from dataclasses import fields
        from local_inspection_service.agent import invocation_ports as p
        from local_inspection_service.agent.protocol_policy import AgentProtocolPolicy
        from local_inspection_service.agent.chat_transport import AgentChatTransport
        from local_inspection_service.agent.connection_discovery import AgentConnectionDiscovery
        from local_inspection_service.agent.recommendation import AgentRecommendation
        reads=[]
        def group(kind):
            values={field.name:Mock(return_value=None) for field in fields(kind)}
            reads.extend(values.values());return kind(**values)
        AgentProtocolPolicy(group(p.AgentProtocolRuntime))
        AgentChatTransport(group(p.AgentInvocationSettings),group(p.AgentHttpIO),group(p.AgentInvocationCodec),group(p.AgentChatCalls))
        AgentConnectionDiscovery(group(p.AgentInvocationSettings),group(p.AgentHttpIO),group(p.AgentInvocationCodec),group(p.AgentModelCalls))
        AgentRecommendation(group(p.AgentInvocationSettings),group(p.AgentInvocationCodec),group(p.AgentResponseParsing),group(p.AgentRecommendationInputs),group(p.AgentRecommendationCalls))
        for getter in reads:getter.assert_not_called()

    def test_two_live_invocation_compositions_keep_their_dependencies(self):
        from dataclasses import fields
        from local_inspection_service.agent import invocation_ports as p
        from local_inspection_service.agent.protocol_policy import AgentProtocolPolicy
        from local_inspection_service.agent.chat_transport import AgentChatTransport
        from local_inspection_service.agent.connection_discovery import AgentConnectionDiscovery
        from local_inspection_service.agent.recommendation import AgentRecommendation
        def forbidden():raise AssertionError('unselected capability')
        def group(kind,**selected):return kind(**{field.name:selected.get(field.name,forbidden) for field in fields(kind)})
        events=[]
        def make(name):
            config={**self.config,'profile_id':name,'profile_version':7,'profile_purpose':'training_assistant'}
            settings=group(p.AgentInvocationSettings,load=lambda:lambda:config,normalize_provider=lambda:lambda provider,url:'openai_compatible',cursor_provider=lambda:'cursor',connected=lambda:lambda value:True,recommended=lambda:lambda value:False)
            protocol=AgentProtocolPolicy(group(p.AgentProtocolRuntime,cursor_base_url=lambda:'https://'+name+'.invalid'))
            codec=group(p.AgentInvocationCodec,dumps=lambda:json.dumps)
            def generate(values,system,content,**kwargs):
                events.append((name,values['profile_id'],kwargs));return {'instance':name},0,{}
            calls=group(p.AgentChatCalls,chat_url=lambda:lambda url:'https://'+name+'.invalid/chat',generate=lambda:generate)
            chat=AgentChatTransport(settings,group(p.AgentHttpIO),codec,calls)
            discovery=AgentConnectionDiscovery(settings,group(p.AgentHttpIO),group(p.AgentInvocationCodec),group(p.AgentModelCalls,openai_test=lambda:lambda value:{'instance':name}))
            inputs=group(p.AgentRecommendationInputs,config=lambda:lambda:{'instance':name},selected=lambda:lambda values,ids:[],selection_error=lambda:self.api.HTTPException)
            recommendation=AgentRecommendation(settings,group(p.AgentInvocationCodec),group(p.AgentResponseParsing),inputs,group(p.AgentRecommendationCalls,rule=lambda:lambda stage,selected,count:{'stage':stage,'params':{'instance':name},'reason':name}))
            return protocol,chat,discovery,recommendation
        instances={name:make(name) for name in ('first','second')}
        with patch.object(self.api,'load_agent_config',side_effect=AssertionError('root settings')),patch.object(self.api,'generate_provider_json_with_fallback',side_effect=AssertionError('root generation')),patch.object(self.api,'test_openai_agent_connection',side_effect=AssertionError('root connection')),patch.object(self.api,'rule_recommendation',side_effect=AssertionError('root rules')):
            for name in ('first','second','first'):
                with self.subTest(instance=name):
                    protocol,chat,discovery,recommendation=instances[name]
                    self.assertEqual(protocol.cursor_api_url('','/models'),'https://'+name+'.invalid/models')
                    self.assertEqual(json.loads(chat.agent_chat_completion([])),{'instance':name})
                    self.assertEqual(discovery.test_agent_connection(self.config),{'instance':name})
                    self.assertEqual(recommendation.agent_recommendation('training',[]),{'stage':'training','params':{'instance':name},'reason':name,'source':'rules'})
        self.assertEqual(events,[(name,name,{'max_tokens':1400,'max_attempts':1}) for name in ('first','second','first')])


if __name__=='__main__':unittest.main()

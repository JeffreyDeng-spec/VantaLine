"""Offline behavior baseline for public status and configuration projections."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path.cwd()))

class PublicStatusContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env=patch.dict(os.environ);cls.env.start();cls.tmp=tempfile.TemporaryDirectory(prefix='public-status-')
        root=Path(cls.tmp.name);(root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup();cls.env.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for target in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):
            self.stack.enter_context(patch(target,side_effect=AssertionError('external operation forbidden')))
        self.settings={'enabled':True,'configured':True,'status':'ready','message':'synthetic','provider_label':'synthetic provider','model':'synthetic-model','api_key':'synthetic-key','api_key_candidates':[{'key':'synthetic-key'}],'proxy_url_raw':'synthetic-proxy','api_keys':[{'masked_key':'***'}],'extra_public':7}
        self.image={'configured':True,'model':'synthetic-image','api_key':'synthetic-image-key','proxy_url_raw':'synthetic-image-proxy','extra_public':8}
        self.ai=self.stack.enter_context(patch.object(self.api,'ai_detection_settings',return_value=self.settings))
        self.images=self.stack.enter_context(patch.object(self.api,'image_generation_settings',return_value=self.image))
        self.permission=self.stack.enter_context(patch.object(self.api,'user_has_permission',side_effect=lambda user,name:bool(user and name in user.get('permissions',[]))))
        self.admin=self.stack.enter_context(patch.object(self.api,'user_is_admin',side_effect=lambda user:bool(user and user.get('admin'))))
    def test_ai_status_removes_only_existing_private_fields_and_adds_image(self):
        before=copy.deepcopy(self.settings);result=self.api.public_ai_detection_status()
        self.assertEqual(result,{**{k:v for k,v in self.settings.items() if k not in {'api_key','api_key_candidates','proxy_url_raw'}},'image_generation':{k:v for k,v in self.image.items() if k not in {'api_key','proxy_url_raw'}}})
        self.assertEqual(self.settings,before);self.assertIsNot(result,self.settings);self.assertIs(result['api_keys'],self.settings['api_keys'])
        self.ai.assert_called_once_with();self.images.assert_called_once_with()
    def test_image_status_preserves_public_values_without_mutation(self):
        before=copy.deepcopy(self.image);result=self.api.public_image_generation_status()
        self.assertEqual(result,{'configured':True,'model':'synthetic-image','extra_public':8})
        self.assertEqual(self.image,before);self.assertIsNot(result,self.image);self.ai.assert_not_called()
    def test_permission_status_shortcut_returns_existing_projection_identity(self):
        user={'permissions':['ai_config']};expected={'public':'synthetic'}
        with patch.object(self.api,'public_ai_detection_status',return_value=expected) as delegated:
            self.assertIs(self.api.public_ai_detection_status_for_user(user),expected)
        delegated.assert_called_once_with();self.permission.assert_called_once_with(user,'ai_config');self.ai.assert_not_called();self.images.assert_not_called()
    def test_restricted_ai_status_defaults_and_exact_shape(self):
        for user in (None,{'permissions':[]},{'permissions':['other']}):
            with self.subTest(user=user):
                result=self.api.public_ai_detection_status_for_user(user)
                self.assertEqual(result,{'enabled':True,'configured':True,'status':'ready','message':'synthetic','provider_label':'synthetic provider'})
        self.images.assert_not_called()
        self.ai.return_value={};self.assertEqual(self.api.public_ai_detection_status_for_user(None),{'enabled':False,'configured':False,'status':'','message':'','provider_label':''})
    def test_model_allowlist_and_provider_status_permission(self):
        model={'id':'one','label':'synthetic','owner_user_id':'owner','is_ai_detection':True,'provider_status':{'api_key_present':True},'internal_path':'synthetic-private','unknown':'hidden'}
        before=copy.deepcopy(model)
        for allowed in (False,True):
            user={'permissions':['ai_config'] if allowed else []};result=self.api.public_status_model_for_user(model,user)
            self.assertEqual(result,{k:v for k,v in model.items() if k in self.api.STATUS_MODEL_PUBLIC_KEYS or (k=='provider_status' and allowed)})
            self.assertNotIn('internal_path',result);self.assertNotIn('unknown',result)
            if allowed:self.assertIs(result['provider_status'],model['provider_status'])
        self.assertEqual(model,before)
    def test_non_ai_model_never_calls_permission_and_missing_status_is_not_added(self):
        self.assertEqual(self.api.public_status_model_for_user({'id':'one','provider_status':{'private':1}},None),{'id':'one'})
        self.permission.assert_not_called()
        result=self.api.public_status_model_for_user({'id':'one','is_ai_detection':True},{'permissions':['ai_config']})
        self.assertNotIn('provider_status',result)
    def test_admin_service_status_is_identity_and_skips_nested_reads(self):
        payload={'service':'synthetic','internal':'admin-value'};user={'admin':True}
        self.assertIs(self.api.public_service_status_for_user(user,payload),payload)
        self.admin.assert_called_once_with(user);self.ai.assert_not_called();self.images.assert_not_called();self.permission.assert_not_called()
    def test_restricted_service_status_filters_models_preserves_order_and_aliases(self):
        user={'admin':False};tasks=[{'task':'one'}];classes=['part'];rule={'required':1}
        payload={'service':'synthetic','model_exists':True,'active_model_id':'one','available_models':[{'id':'one','unknown':'hidden'},None,'skip',{'id':'two'}],'specialized_models':[7,{'id':'three'}],'specialized_model_tasks':tasks,'ai_detection_tasks':tasks,'classes':classes,'rule':rule,'ocr':{'private':1},'training_execution':{'private':1},'cursor_image2':{'private':1},'internal_path':'hidden'}
        before=copy.deepcopy(payload);result=self.api.public_service_status_for_user(user,payload)
        self.assertEqual(result,{'service':'synthetic','model_exists':True,'active_model_id':'one','available_models':[{'id':'one'},{'id':'two'}],'specialized_models':[{'id':'three'}],'specialized_model_tasks':tasks,'ai_detection_tasks':tasks,'ai_detection':{'enabled':True,'configured':True,'status':'ready','message':'synthetic','provider_label':'synthetic provider'},'training_execution':{'status':'restricted','executor':''},'cursor_image2':{'status':'restricted','configured':False},'classes':classes,'rule':rule,'ocr':{}})
        self.assertIs(result['classes'],classes);self.assertIs(result['rule'],rule);self.assertIs(result['ai_detection_tasks'],tasks);self.assertEqual(payload,before)
    def test_restricted_service_status_empty_defaults(self):
        result=self.api.public_service_status_for_user(None,{})
        self.assertEqual(set(result),{'service','model_exists','active_model_id','available_models','specialized_models','specialized_model_tasks','ai_detection_tasks','ai_detection','training_execution','cursor_image2','classes','rule','ocr'})
        self.assertIsNone(result['service']);self.assertIsNone(result['model_exists']);self.assertIsNone(result['active_model_id'])
        for key in ('available_models','specialized_models','specialized_model_tasks','ai_detection_tasks','classes'):self.assertEqual(result[key],[])
        self.assertEqual(result['rule'],{});self.assertEqual(result['ocr'],{})
    def test_configuration_summary_sanitizes_once_at_original_boundary(self):
        config={'confidence_threshold':0.4,'required_classes':['part'],'min_counts':{'part':2},'internal_path':'synthetic-private'};expected=object()
        with patch.object(self.api,'public_path_sanitized',return_value=expected) as sanitize:
            self.assertIs(self.api.public_config_summary_for_user({'admin':True},config),expected);sanitize.assert_called_once_with(config)
            sanitize.reset_mock();self.assertIs(self.api.public_config_summary_for_user(None,config),expected)
            sanitize.assert_called_once_with({'confidence_threshold':0.4,'required_classes':['part'],'min_counts':{'part':2}})
    def test_dependency_failures_escape_without_retry_or_extra_reads(self):
        for site in ('ai_detection_settings','image_generation_settings','public_path_sanitized'):
            with self.subTest(site=site):
                error=RuntimeError('synthetic first failure');calls=[];caught=None
                def callback(*args,**kwargs):
                    calls.append(1)
                    if len(calls)==1:raise error
                    return {}
                with patch.object(self.api,site,side_effect=callback):
                    try:
                        if site=='ai_detection_settings':self.api.public_ai_detection_status()
                        elif site=='image_generation_settings':self.api.public_image_generation_status()
                        else:self.api.public_config_summary_for_user(None,{})
                    except BaseException as exc:caught=exc
                self.assertIs(caught,error);self.assertEqual(calls,[1])
    def test_two_accounts_concurrent_projection_does_not_share_privilege(self):
        from concurrent.futures import ThreadPoolExecutor
        payload={'service':'synthetic','internal':'admin-only'}
        with ThreadPoolExecutor(max_workers=2) as pool:
            admin=pool.submit(self.api.public_service_status_for_user,{'admin':True},payload)
            restricted=pool.submit(self.api.public_service_status_for_user,{'admin':False},payload)
            self.assertIs(admin.result(timeout=5),payload);self.assertNotIn('internal',restricted.result(timeout=5))
        self.assertEqual(payload,{'service':'synthetic','internal':'admin-only'})


    def test_service_model_callback_refreshes_for_each_item(self):
        calls=[]
        def second(model,user):calls.append(('second',model['id']));return {'id':'second'}
        def first(model,user):
            calls.append(('first',model['id']));self.api.public_status_model_for_user=second;return {'id':'first'}
        with patch.object(self.api,'public_status_model_for_user',first):
            result=self.api.public_service_status_for_user(None,{'available_models':[{'id':'a'},{'id':'b'}],'specialized_models':[{'id':'c'}]})
        self.assertEqual(calls,[('first','a'),('second','b'),('second','c')])
        self.assertEqual(result['available_models'],[{'id':'first'},{'id':'second'}]);self.assertEqual(result['specialized_models'],[{'id':'second'}])
    def test_admin_and_permission_decisions_refresh_between_invocations(self):
        payload={'service':'synthetic','private':1};user={}
        self.admin.return_value=False;self.admin.side_effect=None
        first=self.api.public_service_status_for_user(user,payload)
        self.admin.return_value=True
        self.assertIs(self.api.public_service_status_for_user(user,payload),payload);self.assertNotIn('private',first)
        self.permission.side_effect=None;self.permission.return_value=False
        self.assertNotIn('model',self.api.public_ai_detection_status_for_user(user))
        self.permission.return_value=True
        refreshed=self.api.public_ai_detection_status_for_user(user)
        self.assertIn('model',refreshed)
        self.assertEqual(refreshed['model'],'synthetic-model')
    def test_late_image_and_sanitizer_selection_after_prior_callback(self):
        replacement=Mock(return_value={'late':'image'})
        def settings():self.api.public_image_generation_status=replacement;return self.settings
        with patch.object(self.api,'public_image_generation_status',Mock(side_effect=AssertionError('stale image callback'))):
            self.ai.side_effect=settings
            self.assertEqual(self.api.public_ai_detection_status()['image_generation'],{'late':'image'})
        replacement.assert_called_once_with()
        sanitizer=Mock(return_value={'late':'sanitized'})
        def admin(user):self.api.public_path_sanitized=sanitizer;return True
        with patch.object(self.api,'public_path_sanitized',Mock(side_effect=AssertionError('stale sanitizer'))):
            self.admin.side_effect=admin
            self.assertEqual(self.api.public_config_summary_for_user(None,{'x':1}),{'late':'sanitized'})
        sanitizer.assert_called_once_with({'x':1})


    def test_independent_compositions_are_isolated_without_application_callbacks(self):
        from local_inspection_service.auth.status import PublicStatusProjection
        from local_inspection_service.auth.status_ports import StatusPolicy, StatusSources, StatusProjectionCalls
        from concurrent.futures import ThreadPoolExecutor
        def make(label):
            state={'reads':0}
            def settings():state['reads']+=1;return {'enabled':True,'model':label,'api_key':'synthetic-key'}
            service=None
            policy=StatusPolicy(lambda:lambda u:bool(u and u.get('admin')),lambda:lambda u,p:bool(u and p in u.get('permissions',[])),lambda:{'id'},lambda:lambda v:{'sanitized':label})
            sources=StatusSources(lambda:settings,lambda:lambda:{'model':label+'-image','api_key':'synthetic-key'})
            calls=StatusProjectionCalls(lambda:service.public_ai_detection_status,lambda:service.public_image_generation_status,lambda:service.public_status_model_for_user,lambda:service.public_ai_detection_status_for_user)
            service=PublicStatusProjection(policy,sources,calls)
            self.assertEqual(state['reads'],0)
            return service,state
        a,sa=make('a');b,sb=make('b')
        for name in ('user_is_admin','user_has_permission','public_path_sanitized','ai_detection_settings','image_generation_settings','public_ai_detection_status','public_image_generation_status','public_status_model_for_user','public_ai_detection_status_for_user'):
            self.stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('independent service used root')))
        with ThreadPoolExecutor(max_workers=2) as pool:
            ra,rb=list(pool.map(lambda service:service.public_ai_detection_status_for_user({'permissions':['ai_config']}),(a,b)))
        self.assertEqual(ra,{'enabled':True,'model':'a','image_generation':{'model':'a-image'}})
        self.assertEqual(rb,{'enabled':True,'model':'b','image_generation':{'model':'b-image'}})
        self.assertEqual(sa['reads'],1);self.assertEqual(sb['reads'],1)
        self.assertNotIn('model',a.public_ai_detection_status_for_user(None));self.assertEqual(sb['reads'],1)
    def test_constructor_never_reads_capabilities_and_keeps_only_dependencies(self):
        from local_inspection_service.auth.status import PublicStatusProjection
        from local_inspection_service.auth.status_ports import StatusPolicy, StatusSources, StatusProjectionCalls
        forbidden=Mock(side_effect=AssertionError('constructor capability read'))
        policy=StatusPolicy(forbidden,forbidden,forbidden,forbidden)
        sources=StatusSources(forbidden,forbidden);calls=StatusProjectionCalls(forbidden,forbidden,forbidden,forbidden)
        service=PublicStatusProjection(policy,sources,calls)
        forbidden.assert_not_called();self.assertEqual(vars(service),{'_policy':policy,'_sources':sources,'_calls':calls})


    def test_restricted_sanitizer_is_captured_before_config_argument_effects(self):
        for mode in ('ordinary','prior','missing'):
            with self.subTest(mode=mode):
                events=[]
                def chosen(value):events.append(('chosen',value));return {'chosen':value}
                def replacement(value):events.append(('replacement',value));return {'replacement':value}
                target=None if mode=='missing' else chosen
                class Config(dict):
                    def get(inner,key,*args):
                        events.append(('get',key));self.api.public_path_sanitized=replacement
                        return super().get(key,*args)
                config=Config(confidence_threshold=0.5,required_classes=['x'],min_counts={'x':1})
                def admin(user):
                    events.append(('admin',user));self.api.public_path_sanitized=target
                    return False
                with patch.object(self.api,'public_path_sanitized',chosen if mode=='prior' else replacement):
                    self.admin.side_effect=admin
                    if mode=='missing':
                        with self.assertRaises(TypeError):self.api.public_config_summary_for_user(None,config)
                    else:
                        self.assertEqual(self.api.public_config_summary_for_user(None,config),{'chosen':dict(config)})
                self.assertEqual(events[:4],[('admin',None),('get','confidence_threshold'),('get','required_classes'),('get','min_counts')])
                self.assertEqual(events[4:],[] if mode=='missing' else [('chosen',dict(config))])

if __name__=='__main__':unittest.main()

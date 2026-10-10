"""Scoped Agent settings test substitution on finite native dependencies."""
from dataclasses import replace
from unittest.mock import patch

PROJECTION=(('_auth',{'current_user':'current_auth_user','is_admin':'user_is_admin'}),('_access',{'load':'load_agent_config','credentials':'agent_credentials_present','recommendation':'agent_recommendation_supported'}))
HTTP=(('_access',{'admin':'require_admin_role','http_error':'HTTPException'}),('_projection',{'public':'public_agent_config'}),('_recommendation',{'recommend':'agent_recommendation'}))


def bind_agent_settings(api,stack,*,http=False):
    app=api._default_application;owner=app.training_pipeline._agent_settings_api if http else app.training_pipeline._agent_settings_projection
    for attribute,mapping in HTTP if http else PROJECTION:
        stack.enter_context(patch.object(owner,attribute,replace(getattr(owner,attribute),**{field:(lambda name=name:getattr(api,name)) for field,name in mapping.items()})))
    if not http:
        legacy=app.infrastructure._legacy_agent_settings_store
        stack.enter_context(patch.object(legacy,'_paths',replace(legacy._paths,file=lambda:api.AGENT_LOCAL_CONFIG_PATH,directory=lambda:api.DATA_DIR)))
        stack.enter_context(patch.object(legacy,'_defaults',replace(legacy._defaults,config=lambda:api.DEFAULT_AGENT_CONFIG)))


def assert_default_agent_settings(api,*,http=False):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.runtime.wiring import training_pipeline
    from local_inspection_service.agent.settings_projection import AgentSettingsProjection
    from local_inspection_service.agent.settings_api import AgentSettingsApi
    from local_inspection_service.agent.legacy_settings_store import LegacyAgentSettingsStore
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;infra=app.infrastructure;item,other=object(),object()
    if http:
        owner=graph._agent_settings_api;case.assertIs(type(owner),AgentSettingsApi);case.assertIs(api._agent_settings_api,owner)
        case.assertIs(owner._access.admin(),infra.require_admin_role);case.assertIs(owner._access.http_error(),training_pipeline.HTTPException)
        for selected,target,method,args,kw,expected in ((owner._projection.public(),graph._agent_settings_projection,'public_agent_config',(),{},(None,)),(owner._projection.public(),graph._agent_settings_projection,'public_agent_config',(item,),{},(item,)),(owner._recommendation.recommend(),graph._agent_recommendation,'agent_recommendation',('stage',[item]),{},('stage',[item],None))):
            if method=='agent_recommendation':expected=(*args,None)
            assert_native_relay(case,selected,(target,method,args,kw,expected,{}))
            if method=='agent_recommendation':
                explicit_args=('stage',[item],17)
                assert_native_relay(case,selected,(target,method,explicit_args,{},explicit_args,{}))
        for selected,method,args in ((api.get_agent_config,'get_agent_config',()),(api.update_agent_config,'update_agent_config',(item,)),(api.test_agent_config,'test_agent_config',()),(api.agent_recommend,'agent_recommend',(item,))):
            assert_native_relay(case,selected,(owner,method,args,{},args,{}))
    else:
        owner=graph._agent_settings_projection;legacy=infra._legacy_agent_settings_store
        case.assertIs(type(owner),AgentSettingsProjection);case.assertIs(api._agent_settings_projection,owner);case.assertIs(type(legacy),LegacyAgentSettingsStore);case.assertIs(api._legacy_agent_settings_store,legacy)
        case.assertIs(owner._auth.current_user(),infra.current_auth_user);case.assertIs(owner._auth.is_admin(),training_pipeline.user_is_admin)
        for field,method in (('credentials','agent_credentials_present'),('recommendation','agent_recommendation_supported')):
            assert_native_relay(case,getattr(owner._access,field)(),(owner,method,(item,),{},(item,),{}))
        assert_native_relay(case,owner._access.load(),(infra._model_profile_configuration,'load_agent_config',(),{},(),{}))
        for selected,name in ((legacy._paths.file,'AGENT_LOCAL_CONFIG_PATH'),(legacy._paths.directory,'DATA_DIR'),(legacy._defaults.config,'DEFAULT_AGENT_CONFIG')):
            original=getattr(app.values,name);case.assertIs(selected(),original)
            try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
            finally:object.__setattr__(app.values,name,original)

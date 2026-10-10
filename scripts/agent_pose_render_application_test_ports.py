"""Finite fixture ports for original pose rendering contracts."""
from dataclasses import replace
from unittest.mock import patch

SOURCES={'settings':'image_generation_settings','provider_key':'image_generation_provider_key','provider_label':'image_generation_provider_label','model':'default_image_generation_model','base_url':'default_image_generation_base_url','key_environment':'default_image_generation_api_key_env'}
DEFAULTS={'provider':'IMAGE_GENERATION_DEFAULT_PROVIDER','timeout':'IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS','key_environment':'IMAGE_GENERATION_API_KEY_ENV','model_environment':'IMAGE_GENERATION_MODEL_ENV','timeout_environment':'IMAGE_GENERATION_TIMEOUT_ENV','high_fidelity_model':'AGENT_MCP_GEMINI_IMAGE_HIGH_FIDELITY_MODEL','legacy_model_environment':'AGENT_MCP_GEMINI_IMAGE_MODEL_ENV','legacy_timeout_environment':'AGENT_MCP_GEMINI_IMAGE_TIMEOUT_ENV'}
REFERENCES={'contexts':'accessory_reference_image_contexts','resolve':'resolve_service_path','public_url':'public_output_url_for_existing','digest':'file_sha256'}
ARTIFACTS={'digest':'file_sha256','public_url':'public_output_url','bounded':'bounded_text'}


def bind_pose_render(api,stack):
    owner=api._default_application.training_pipeline._photo_pose_workflows;config=owner.state.configuration
    def bind(selected,attribute,mapping):
        stack.enter_context(patch.object(selected,attribute,replace(getattr(selected,attribute),**{field:(lambda _name=name:getattr(api,_name)) for field,name in mapping.items()})))
    stack.enter_context(patch.object(config,'_sources',replace(config._sources,settings=lambda:api.image_generation_settings)))
    bind(config,'_defaults',DEFAULTS)
    bind(owner.render,'_references',REFERENCES)
    bind(owner.render,'_presentation',{'screen':'normalize_chroma_screen'})
    bind(owner.artifacts,'_paths',{'owner_root':'output_write_dir_for_owner','sanitize':'safe_record_id'})
    bind(owner.artifacts,'_artifacts',ARTIFACTS)
    bind(owner.artifacts,'_presentation',{'screen':'normalize_chroma_screen'})


def assert_default_pose_render(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.agent.pose_render_configuration import PoseRenderConfiguration
    from local_inspection_service.agent.pose_render_content import PoseRenderContent
    from local_inspection_service.agent.pose_artifact_store import PoseArtifactStore
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;owner=graph._photo_pose_workflows;config=owner.state.configuration;item,other,third,fourth=object(),object(),object(),object()
    for selected,kind,alias in ((config,PoseRenderConfiguration,'_pose_render_configuration'),(owner.render,PoseRenderContent,'_pose_render_content'),(owner.artifacts,PoseArtifactStore,'_pose_artifact_store')):
        case.assertIs(type(selected),kind);case.assertIs(getattr(api,alias),selected)
    case.assertIs(owner.state,graph._agent_state_workflows);case.assertIs(owner.render.files,app.artifacts.files);case.assertIs(owner.artifacts.files,app.artifacts.files)
    for field,name in DEFAULTS.items():
        getter=getattr(config._defaults,field);original=getattr(app.values,name);case.assertIs(getter(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(getter(),other)
        finally:object.__setattr__(app.values,name,original)
    for field,name in SOURCES.items():
        target=app.infrastructure._model_profile_configuration if field=='settings' else app.infrastructure._provider_configuration
        args=() if field=='settings' else (item,)
        if field!='settings':
            native=getattr(config._sources,field)();case.assertIs(native.__self__,target);case.assertIs(native.__func__,getattr(type(target),name))
        assert_native_relay(case,lambda *a,**kw:getattr(config._sources,field)()(*a,**kw),(target,name,args,{},args,{}))
    refs=owner.render._references;paths=owner.artifacts._paths;artifacts=owner.artifacts._artifacts;service=app.infrastructure._service_paths;evidence=app.inspection._reference_evidence
    for selected,target,name,args,kw,expected_kw in ((refs.contexts(),evidence,'accessory_reference_image_contexts',(item,),{'max_images':other},{'max_images':other}),(refs.resolve(),service,'resolve_service_path',(item,),{'for_write':True},{'for_write':True}),(refs.public_url(),service,'public_output_url_for_existing',(item,),{},{}),(paths.owner_root(),service,'output_write_dir_for_owner',(item,other),{},{}),(paths.sanitize(),app.inspection._pose_collection_jobs,'safe_record_id',(item,),{},{}),(artifacts.public_url(),service,'public_output_url',(item,),{},{}),(owner.render._presentation.screen(),evidence,'normalize_chroma_screen',(item,),{},{}),(owner.artifacts._presentation.screen(),evidence,'normalize_chroma_screen',(item,),{},{})):
        assert_native_relay(case,selected,(target,name,args,kw,args,expected_kw))
    assert_native_relay(case,refs.resolve(),(service,'resolve_service_path',(item,),{},(item,),{'for_write':False}))
    case.assertIs(refs.mime(),wiring.mimetypes.guess_type);case.assertIs(refs.encode(),wiring.base64.b64encode);case.assertIs(artifacts.bounded(),wiring.bounded_text);case.assertIs(artifacts.dumps(),wiring.json.dumps)
    for selected in (refs.digest(),artifacts.digest()):
        with patch.object(wiring,'strict_training_file_sha256',return_value=other) as receiver:
            case.assertIs(selected(item),other);receiver.assert_called_once_with(item,files=app.artifacts.files)
    native=artifacts.now();case.assertIs(native.__self__,owner.state);case.assertIs(native.__func__,type(owner.state).agent_mcp_now);assert_native_relay(case,native,(owner.state.state,'agent_mcp_now',(),{},(),{}))
    native=artifacts.output();case.assertIs(native.__self__,owner);case.assertIs(native.__func__,type(owner).agent_mcp_pose_output_path)
    assert_native_relay(case,native,(owner.artifacts,'agent_mcp_pose_output_path',(item,other,third,fourth),{},(item,other,third,fourth),{}))

"""Native pipeline background contracts with finite suppliers and actual owners."""
from types import SimpleNamespace
from local_inspection_service.agent.pipeline_background_publication import PipelineBackgroundPublication
from local_inspection_service.agent.pipeline_background_publication_ports import BackgroundPublicationTasks,BackgroundPublicationPaths,BackgroundPublicationSelection,BackgroundPublicationProviders,BackgroundPublicationCatalog,BackgroundPublicationProjection
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.images import ImageFiles

GROUPS=(
    (BackgroundPublicationTasks,{'state':'agent_mcp_orchestration','ids':'canonical_pipeline_accessory_ids','lookup':'accessory_lookup_by_id'}),
    (BackgroundPublicationPaths,{'output':'output_write_dir_for_owner','record_id':'safe_record_id','set_id':'safe_background_set_id','resolve':'resolve_service_path','sets_directory':'BACKGROUND_SETS_DIR'}),
    (BackgroundPublicationSelection,{'prompt':'pipeline_background_plate_prompt','match':'match_background_library_plate','derive':'derive_background_plate_from_accessory'}),
    (BackgroundPublicationProviders,{'config':'agent_mcp_gemini_image_config','references':'agent_mcp_pose_reference_content','settings':'image_generation_settings','create':'image_generation_provider_from_settings','error_type':'AiProviderError'}),
    (BackgroundPublicationCatalog,{'images':'image_file_list','variants':'create_background_variants_from_source','manifest':'load_background_sets_manifest','publish':'write_background_sets_manifest'}),
    (BackgroundPublicationProjection,{'bounded':'bounded_text','url':'public_output_url_for_existing','digest':'file_sha256','now':'agent_mcp_now','legacy_owner':'LEGACY_OWNER_ID'}),
)


def pipeline_background_fixture(server):
    assert_default_pipeline_background(server)
    names={name for _,fields in GROUPS for name in fields.values()}|{'Image','time'}
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    def supplier(name):return lambda:getattr(api,name)
    capabilities=[kind(**{field:supplier(name) for field,name in fields.items()}) for kind,fields in GROUPS]
    files=BusinessFiles(lambda:None)
    owner=PipelineBackgroundPublication(*capabilities,files=files,images=ImageFiles(pil_provider=lambda:api.Image,files=files))
    api.ensure_pipeline_background_plate=owner.ensure_pipeline_background_plate
    return api


def assert_default_pipeline_background(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import training_pipeline, infrastructure
    from local_inspection_service.compatibility import infrastructure as legacy
    verify_actual_sources()
    case=unittest.TestCase()
    application=server._default_application
    graph,inspection,infra=application.training_pipeline,application.inspection,application.infrastructure
    owner=graph._pipeline_background_publication
    case.assertIs(type(owner),PipelineBackgroundPublication)
    case.assertIs(server._pipeline_background_publication,owner)
    case.assertIs(owner.files,application.artifacts.files)
    case.assertIs(owner.images,infra._agent_pil_images)
    case.assertIs(type(owner.images),ImageFiles)
    case.assertIs(owner.images.files,application.artifacts.files)
    case.assertIs(owner.images.pil_provider(),infrastructure.Image)
    case.assertIs(owner._providers.error_type(),training_pipeline.AiProviderError)
    case.assertIs(owner._projection.bounded(),training_pipeline.bounded_text)
    case.assertIs(owner._paths.set_id(),training_pipeline.safe_background_set_id)
    item,other=object(),object()
    for selected,target,method,args,keywords,forwarded,forward_keywords in (
        (owner._tasks.state(),graph._agent_orchestration_state,'agent_mcp_orchestration',(item,),{},(item,),{}),
        (owner._tasks.ids(),graph._pipeline_candidate_flow,'canonical_pipeline_accessory_ids',(item,other),{},(item,other),{}),
        (owner._tasks.lookup(),inspection._accessory_lookup,'accessory_lookup_by_id',(item,),{},(item,),{}),
        (owner._paths.output(),infra._service_paths,'output_write_dir_for_owner',('synthetic','owner'),{},('synthetic','owner'),{}),
        (owner._paths.record_id(),inspection._pose_collection_jobs,'safe_record_id',(item,),{},(item,),{}),
        (owner._paths.resolve(),infra._service_paths,'resolve_service_path',(item,),{},(item,),{'for_write':False}),
        (owner._selection.match(),inspection._background_library_matcher,'match_background_library_plate',(item,'owner'),{},(item,'owner'),{}),
        (owner._selection.derive(),inspection._background_plate_derivation,'derive_background_plate_from_accessory',(item,other),{},(item,other),{}),
        (owner._providers.config(),graph._pose_render_configuration,'agent_mcp_gemini_image_config',(),{},(),{}),
        (owner._providers.references(),graph._pose_render_content,'agent_mcp_pose_reference_content',(item,),{'max_images':2},(item,),{'max_images':2}),
        (owner._providers.settings(),infra._model_profile_configuration,'image_generation_settings',(),{},(),{}),
        (owner._providers.create(),inspection._provider_selection,'image_generation_provider_from_settings',(item,),{},(item,),{}),
        (owner._catalog.images(),graph._background_image_files,'image_file_list',(item,),{},(item,),{}),
        (owner._catalog.variants(),graph._background_variants,'create_background_variants_from_source',(item,other),{'count':7},(item,other,7),{}),
        (owner._catalog.manifest(),graph._background_manifest,'load_background_sets_manifest',(),{},(),{}),
        (owner._catalog.publish(),graph._background_manifest,'write_background_sets_manifest',(item,),{},(item,),{}),
        (owner._projection.url(),infra._service_paths,'public_output_url_for_existing',(item,),{},(item,),{}),
        (owner._projection.now(),graph._agent_orchestration_state,'agent_mcp_now',(),{},(),{}),
        (server.ensure_pipeline_background_plate,owner,'ensure_pipeline_background_plate',(item,other),{},(item,other),{}),
    ):
        assert_native_relay(case,selected,(target,method,args,keywords,forwarded,forward_keywords))
    for selected,module,name,args,keywords in (
        (owner._selection.prompt(),training_pipeline,'_pipeline_background_plate_prompt_impl',(item,),{}),
        (server.pipeline_background_plate_prompt,legacy,'_pipeline_background_plate_prompt_impl',(item,),{}),
        (owner._projection.digest(),training_pipeline,'strict_training_file_sha256',(item,),{'files':application.artifacts.files}),
    ):
        sentinel=object()
        with patch.object(module,name,return_value=sentinel) as callee:
            case.assertIs(selected(*args),sentinel)
            callee.assert_called_once_with(*args,**keywords)
            case.assertIs(callee.call_args.args[0],item)
    for selected,name in ((owner._paths.sets_directory,'BACKGROUND_SETS_DIR'),(owner._projection.legacy_owner,'LEGACY_OWNER_ID')):
        original=getattr(application.values,name)
        case.assertIs(selected(),original)
        sentinel=object()
        try:
            object.__setattr__(application.values,name,sentinel)
            case.assertIs(selected(),sentinel)
        finally:object.__setattr__(application.values,name,original)

"""Finite native dependency replacements for actual accessory HTTP contracts."""
from contextlib import contextmanager,ExitStack
from unittest.mock import Mock,patch
from types import ModuleType

@contextmanager
def frozen_field(owner,name,value):
    previous=getattr(owner,name)
    try:
        object.__setattr__(owner,name,value)
        yield
    finally:object.__setattr__(owner,name,previous)

@contextmanager
def accessory_callback(server,name,*replacement,**options):
    assert hasattr(server,'_default_application')
    assert len(replacement)<=1
    callback=replacement[0] if replacement else Mock(**options)
    assert not replacement or not options
    targets={
        'accessory_ai_profile_ready':(server._accessory_policy,'accessory_ai_profile_ready'),
        'accessory_ai_profile_rejected':(server._accessory_policy,'accessory_ai_profile_rejected'),
        'accessory_detail_payload':(server._accessory_gallery,'accessory_detail_payload'),
        'accessory_image_paths':(server._reference_evidence,'accessory_image_paths'),
        'add_pipeline_accessory_id':(server._pipeline_state_store,'add_pipeline_accessory_id'),
        'add_pipeline_pending_candidate_id':(server._pipeline_state_store,'add_pipeline_pending_candidate_id'),
        'canonical_text_assets':(server._text_asset_catalog,'canonical_text_assets'),
        'canonical_text_assets_complete':(server._text_asset_catalog,'canonical_text_assets_complete'),
        'clean_sprite_assets':(server._sprite_asset_catalog,'clean_sprite_assets'),
        'delete_accessory_item':(server._accessory_repository,'delete_accessory_item'),
        'ensure_accessory_ai_profile':(server._accessory_profile_generation,'ensure_accessory_ai_profile'),
        'ensure_candidate_image_job_task_ids':(server._image_job_metadata,'ensure_candidate_image_job_task_ids'),
        'ensure_default_ai_profile_reference':(server._accessory_preparation,'ensure_default_ai_profile_reference'),
        'ensure_pose_collection_image_jobs':(server._pose_collection_jobs,'ensure_pose_collection_image_jobs'),
        'extract_video_reference_frames':(server._accessory_reference_media,'extract_video_reference_frames'),
        'fallback_accessory_ai_profile':(server._accessory_profile_projection,'fallback_accessory_ai_profile'),
        'generate_accessory_ai_profile':(server._accessory_profile_generation,'generate_accessory_ai_profile'),
        'load_accessory_candidate':(server._candidate_repository,'load_accessory_candidate'),
        'load_config':(server._app_configuration,'load_config'),
        'normalize_accessory_assets':(server._accessory_preparation,'normalize_accessory_assets'),
        'normalize_text_image':(server._accessory_text_preparation,'normalize_text_image'),
        'physical_size_payload':(server._accessory_dimensions,'physical_size_payload'),
        'pipeline_accessories_payload':(server._pipeline_candidate_flow,'pipeline_accessories_payload'),
        'refresh_accessory_assets_after_source_change':(server._accessory_refresh,'refresh_accessory_assets_after_source_change'),
        'refresh_codex_image_job':(server._image_job_management,'refresh_codex_image_job'),
        'remove_pipeline_accessory_id':(server._pipeline_state_store,'remove_pipeline_accessory_id'),
        'remove_pipeline_pending_candidate_id':(server._pipeline_state_store,'remove_pipeline_pending_candidate_id'),
        'runtime_postgres_repository_or_none':(server._runtime_repository_access,'runtime_postgres_repository_or_none'),
        'save_accessory_candidate':(server._candidate_repository,'save_accessory_candidate'),
        'save_accessory_item':(server._accessory_repository,'save_accessory_item'),
        'save_ai_profile_cache':(server._profile_cache_store,'save_ai_profile_cache'),
        'save_app_config':(server._app_configuration,'save_app_config'),
        'serialize_accessory':(server._accessory_projection,'serialize_accessory'),
        'store_candidate_image_job':(server._image_job_metadata,'store_candidate_image_job'),
        'write_thumbnail':(server._accessory_reference_media,'write_thumbnail'),
    }
    from local_inspection_service.runtime.wiring import inspection
    special={
        '_candidate_store_lock':[(server._accessory_confirmation.store,'lock'),(server._candidate_repository.dependencies,'lock')],
        'candidate_has_active_image_jobs':[(server._accessory_creation.profiles,'has_active_jobs')],
        'start_image_worker':[(server._accessory_creation.profiles,'start_worker'),(server._accessory_confirmation.jobs,'start_worker')],
        'current_auth_user':[(server._accessory_removal.access,'current_user')],
    }
    files=server._accessory_files
    creation=server._accessory_creation
    confirmation=server._accessory_confirmation
    factory=server._candidate_factory
    refresh=server._accessory_refresh
    routing=server._accessory_routing
    special.update({
        'refresh_accessory_assets_after_source_change':[(files.profiles,'refresh')],
        'fallback_accessory_ai_profile':[(files.profiles,'fallback'),(refresh.profiles,'fallback')],
        'generate_accessory_ai_profile':[(files.profiles,'generate'),(refresh.profiles,'generate')],
        'save_ai_profile_cache':[(files.profiles,'save_cache')],
        'save_app_config':[(server._accessory_removal.store,'save_app_config')],
        'physical_size_payload':[(factory.media,'default_size')],
        'extract_video_reference_frames':[(server._accessory_preparation.media,'extract_frames')],
        'write_thumbnail':[(factory.media,'thumbnail')],
        'ensure_accessory_ai_profile':[(creation.profiles,'ensure_profile'),(confirmation.profiles,'ensure_profile'),(factory.preparation,'ensure_profile'),(routing.actions,'ensure_profile')],
        'ensure_default_ai_profile_reference':[(creation.profiles,'ensure_reference'),(confirmation.profiles,'ensure_reference'),(factory.preparation,'ensure_reference')],
        'ensure_pose_collection_image_jobs':[(creation.profiles,'ensure_pose_jobs'),(confirmation.jobs,'ensure_pose'),(factory.preparation,'ensure_pose_jobs')],
        'save_accessory_candidate':[(creation.candidates,'save'),(confirmation.store,'save_candidate'),(factory.storage,'save')],
        'canonical_text_assets_complete':[(confirmation.media,'complete')],
        'defer_accessory_normalization':[(creation.media,'defer'),(confirmation.media,'defer'),(factory.preparation,'defer'),(refresh.preparation,'defer')],
        'normalize_accessory_assets':[(creation.media,'normalize'),(confirmation.media,'normalize'),(refresh.preparation,'normalize')],
        'upsert_dashboard_ai_task':[(routing.actions,'upsert_task')],
        'pipeline_accessories_payload':[(creation.pipeline,'payload'),(confirmation.pipeline,'payload')],
    })
    if name in special:
        value=(lambda:callback) if name=='_candidate_store_lock' else callback
        with ExitStack() as stack:
            for owner,field in special[name]:stack.enter_context(frozen_field(owner,field,value))
            yield callback
        return
    with native_callback(server,name,callback,targets,inspection):yield callback

@contextmanager
def native_callback(server,name,callback,targets,inspection):
    if name in {'_candidate_store_lock','candidate_has_active_image_jobs','start_image_worker','current_auth_user','upsert_dashboard_ai_task'}:
        yield callback
        return
    if name=='defer_accessory_normalization':
        with patch.object(inspection,'_preparation_defer',callback):yield callback
        return
    assert name in targets,'Unmapped accessory dependency: '+name
    owner,method=targets[name]
    if isinstance(owner,ModuleType):
        with patch.object(owner,method,callback):yield callback
        return
    from functools import wraps
    import inspect
    original=getattr(type(owner),method)
    signature=inspect.signature(original)
    @wraps(original)
    def selected(receiver,*args,**kwargs):
        signature.bind(receiver,*args,**kwargs)
        assert receiver is owner,'Accessory dependency used a foreign instance'
        return callback(*args,**kwargs)
    with patch.object(type(owner),method,selected):yield callback

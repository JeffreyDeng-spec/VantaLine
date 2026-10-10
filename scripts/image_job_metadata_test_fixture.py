"""Native metadata tests with model and provenance default-owner witnesses."""
from types import SimpleNamespace
from local_inspection_service.accessories import image_job_metadata as metadata
from local_inspection_service.storage.artifacts.files import BusinessFiles


def image_job_metadata_fixture(server):
    import unittest
    from unittest.mock import patch
    from pathlib import Path
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.model_profile_test_ports import patch_profile_service
    from local_inspection_service.runtime.wiring import inspection
    verify_actual_sources()
    case=unittest.TestCase()
    application=server._default_application
    actual=application.inspection._image_job_metadata
    case.assertIs(type(actual),metadata.ImageJobMetadata)
    case.assertIs(server._image_job_metadata,actual)
    case.assertIs(application.inspection._image_jobs.metadata,actual)
    case.assertIs(actual.files,application.artifacts.files)
    case.assertIs(type(actual.provenance),metadata.ProvenanceDependencies)
    for field,name in (('policy_version','ANCHOR_POLICY_VERSION'),('guide_images','POSE_TARGET_GUIDE_IMAGES'),('max_inputs','MAX_IMAGE_WORKER_INPUTS')):
        case.assertIs(getattr(actual.provenance,field)(),getattr(application.values,name))
        original=getattr(application.values,name)
        replacements=({'fixture':[]},{'another':[]}) if field=='guide_images' else (1,2) if field=='max_inputs' else ('fixture-A','fixture-B')
        try:
            for replacement in replacements:
                object.__setattr__(application.values,name,replacement)
                case.assertIs(getattr(actual.provenance,field)(),replacement)
        finally:
            object.__setattr__(application.values,name,original)
    path,sentinel=Path('synthetic.png'),object()
    with patch.object(inspection,'strict_training_file_sha256',return_value=sentinel) as callee:
        case.assertIs(actual.provenance.hash_file(path),sentinel)
        callee.assert_called_once_with(path,files=application.artifacts.files)
        case.assertIs(callee.call_args.args[0],path)
        case.assertIs(callee.call_args.kwargs['files'],application.artifacts.files)
    resolver=SimpleNamespace()
    with patch_profile_service(server,resolver):
        case.assertIs(actual.model_resolver(),resolver)
    names=('file_sha256','ANCHOR_POLICY_VERSION','POSE_TARGET_GUIDE_IMAGES','MAX_IMAGE_WORKER_INPUTS','resolve_model_profiles')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    native=metadata.ImageJobMetadata(metadata.ProvenanceDependencies(
        lambda path:api.file_sha256(path),lambda:api.ANCHOR_POLICY_VERSION,
        lambda:api.POSE_TARGET_GUIDE_IMAGES,lambda:api.MAX_IMAGE_WORKER_INPUTS),
        lambda:api.resolve_model_profiles(),files=BusinessFiles(lambda:None))
    for name in ('ensure_anchor_image_provenance','ensure_image_job_target_guides','ensure_candidate_image_job_task_ids','store_candidate_image_job'):
        setattr(api,name,getattr(native,name))
    for name in ('candidate_image_jobs','deterministic_task_id','ensure_image_job_task_id'):
        setattr(api,name,getattr(metadata,name))
    return api

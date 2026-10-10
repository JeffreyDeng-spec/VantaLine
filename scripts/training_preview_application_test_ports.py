"""Finite plan projection and preview submission fixtures."""
from dataclasses import replace
from unittest.mock import patch,Mock

PLAN=(('access',{'current':'current_auth_user','is_admin':'user_is_admin'}),('config',{'load':'load_config','filtered':'filtered_training_state'}),('backgrounds',{'list':'list_background_sets'}))
PLAN_GETTERS=(('access',{'sanitize':'public_path_sanitized'}),('config',{'scope':'scope_config_for_user'}),('backgrounds',{'selected':'selected_background_set_id','physical_size':'BACKGROUND_SIZE_MM'}))
SUBMISSION=(('config',{'load':'load_config','scope':'scope_config_for_user','set_state':'set_training_state_for_user','merge':'merge_scoped_accessory_updates','save':'save_config'}),('selection',{'uid':'accessory_uid','material':'accessory_material_type','sprites':'clean_sprite_assets','version':'accessory_sprite_version','cache':'preview_cache_key'}),('policy',{'sequence':'preview_pose_family_sequence','label':'preview_pose_family_sequence_label'}))
SUBMISSION_GETTERS=(('config',{'ensure':'ensure_training_assets_for_request'}),('selection',{'selected':'selected_accessories'}),('policy',{'normalize':'normalize_preview_pose_family_policy','background':'selected_background_set_id'}))


def bind_training_preview(api,stack):
    graph=api._default_application.training_pipeline;plan=graph._training_plan_query;submission=graph._training_preview_submission;artifacts=graph._training_preview_artifacts
    for owner,groups in ((plan,PLAN),(submission,SUBMISSION)):
        for attribute,mapping in groups:stack.enter_context(patch.object(owner,attribute,replace(getattr(owner,attribute),**{field:(lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)) for field,name in mapping.items()})))
    for owner,groups in ((plan,PLAN_GETTERS),(submission,SUBMISSION_GETTERS)):
        for attribute,mapping in groups:stack.enter_context(patch.object(owner,attribute,replace(getattr(owner,attribute),**{field:(lambda _name=name:getattr(api,_name)) for field,name in mapping.items()})))
    stack.enter_context(patch.object(plan,'serialize',lambda:api.serialize_accessory_items));stack.enter_context(patch.object(plan,'execution',lambda **kw:api.training_execution_status(**kw)))
    stack.enter_context(patch.object(submission,'current',lambda:api.current_auth_user()));stack.enter_context(patch.object(submission,'draw',lambda:api.draw_training_preview));stack.enter_context(patch.object(submission,'clock',lambda:api.time.time()));stack.enter_context(patch.object(submission,'uuid',lambda:api.uuid.uuid4()))
    stack.enter_context(patch.object(artifacts,'output',lambda kind:api.output_write_dir(kind)));stack.enter_context(patch.object(artifacts,'jobs',lambda:api.TRAINING_JOBS_DIR))


def assert_default_training_preview(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.training_records_application_test_ports import _frozen_slot
    from local_inspection_service.training.preview_query import TrainingPlanQuery
    from local_inspection_service.training.preview_submission import TrainingPreviewSubmission
    from local_inspection_service.training.preview_artifacts import PreviewArtifactStore
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;infra=app.infrastructure;inspection=app.inspection;plan=graph._training_plan_query;submission=graph._training_preview_submission;artifacts=graph._training_preview_artifacts;item,other,third,fourth=object(),object(),object(),object()
    for name,kind in (('_training_plan_query',TrainingPlanQuery),('_training_preview_submission',TrainingPreviewSubmission),('_training_preview_artifacts',PreviewArtifactStore)):case.assertIs(type(getattr(graph,name)),kind);case.assertIs(getattr(api,name),getattr(graph,name))
    case.assertIs(submission.artifacts,artifacts);case.assertIs(artifacts.files,app.artifacts.files)
    for selected,name in ((plan.backgrounds.physical_size,'BACKGROUND_SIZE_MM'),(artifacts.jobs,'TRAINING_JOBS_DIR')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)
    for selected in (plan.access.current,submission.current):
        receiver=Mock(return_value=other)
        with _frozen_slot(infra,'current_auth_user',receiver):case.assertIs(selected(),other);receiver.assert_called_once_with()
    with patch.object(wiring,'user_is_admin',return_value=other) as receiver:case.assertIs(plan.access.is_admin(item),other);receiver.assert_called_once_with(item)
    for selected,target,method,args,kw,expected,expected_kw in (
        (plan.access.sanitize(),infra._service_paths,'public_path_sanitized',(item,),{},(item,),{}),
        (plan.config.load,infra._app_configuration,'load_config',(),{},(),{}),
        (plan.config.scope(),infra._account_projections,'scope_config_for_user',(item,other,third),{},(item,other,third),{}),
        (plan.config.filtered,graph._training_task_workflows,'filtered_training_state',(item,other,third),{},(item,other,third),{}),
        (plan.backgrounds.list,graph._background_catalog,'list_background_sets',(item,other),{},(item,other),{}),
        (plan.backgrounds.selected(),graph._background_selection,'selected_background_set_id',(item,other,third),{},(item,other,third),{}),
        (plan.serialize(),inspection._accessory_projection,'serialize_accessory_items',(item,),{'summary':False},(item,),{'summary':False}),
        (plan.execution,graph._training_executor_settings,'training_execution_status',(),{'include_worker_probe':False},(),{'include_worker_probe':False,'include_worker_services':False}),
        (submission.config.load,infra._app_configuration,'load_config',(),{},(),{}),
        (submission.config.scope,infra._account_projections,'scope_config_for_user',(item,other),{},(item,other,None),{}),
        (submission.config.ensure(),graph._training_asset_preparation,'ensure_training_assets_for_request',(item,other,third,fourth),{},(item,other,third,fourth),{}),
        (submission.config.set_state,graph._training_account_state,'set_training_state_for_user',(item,other,third),{},(item,other,third),{}),
        (submission.config.merge,infra._account_projections,'merge_scoped_accessory_updates',(item,other,third),{},(item,other,third),{}),
        (submission.config.save,infra._app_configuration,'save_config',(item,),{},(item,),{}),
        (submission.selection.selected(),inspection._accessory_selection,'selected_accessories',(item,other),{},(item,other),{}),
        (submission.selection.sprites,inspection._sprite_asset_catalog,'clean_sprite_assets',(item,),{},(item,),{}),
        (submission.selection.version,graph._training_preview_cache,'accessory_sprite_version',(item,),{},(item,),{}),
        (submission.selection.cache,graph._training_preview_cache,'preview_cache_key',(item,),{},(item,),{}),
        (submission.policy.normalize(),inspection._preview_pose_policy,'normalize_preview_pose_family_policy',(item,),{},(item,),{}),
        (submission.policy.background(),graph._background_selection,'selected_background_set_id',(item,other),{},(item,other,None),{}),
        (submission.policy.sequence,inspection._preview_pose_policy,'preview_pose_family_sequence',(item,other,third),{},(item,other,third),{}),
        (submission.policy.label,inspection._preview_pose_policy,'preview_pose_family_sequence_label',(item,),{},(item,),{}),
        (submission.draw(),graph._training_preview_renderer,'draw_training_preview',(item,other),{'seed':third,'pose_family_policy':fourth,'background_set_id':item},(item,other,third,fourth,None,item),{}),
        (artifacts.output,infra._service_paths,'output_write_dir',(item,),{},(item,),{})):
        assert_native_relay(case,selected,(target,method,args,kw,expected,expected_kw))
    for selected,name in ((submission.selection.uid,'accessory_uid'),(submission.selection.material,'accessory_material_type')):
        with patch.object(wiring._accessory_policy,name,return_value=other) as receiver:case.assertIs(selected(item),other);receiver.assert_called_once_with(item)
    for selected,target,name in ((submission.clock,wiring.time,'time'),(submission.uuid,wiring.uuid,'uuid4')):
        with patch.object(target,name,return_value=other) as receiver:case.assertIs(selected(),other);receiver.assert_called_once_with()

    assert_native_relay(case,plan.serialize(),(inspection._accessory_projection,'serialize_accessory_items',(item,),{'summary':True},(item,),{'summary':True}))

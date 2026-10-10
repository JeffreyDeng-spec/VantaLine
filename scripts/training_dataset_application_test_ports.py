"""Finite synthetic dataset dependencies on actual planning/rendering owners."""
from dataclasses import replace
from unittest.mock import patch

DIRECT=(('records',{'load':'load_config','save':'save_config','normalize_assets':'ensure_training_normalized_assets_for_selection','select':'selected_accessories','uses_ocr':'accessory_uses_ocr'}),('plan',{'build':'build_training_sample_plan'}),('render',{'yaml':'write_dataset_yaml'}))
GETTERS=(('plan',{'normalize_pose':'normalize_preview_pose_family_policy','background':'selected_background_set_id'}),('render',{'draw':'draw_training_preview','label':'yolo_detection_label_line','annotation':'write_training_annotation_preview','max_occlusion':'DETECTION_MAX_OCCLUSION_FRACTION','min_visible_area':'DETECTION_MIN_VISIBLE_AREA_PX'}))


def bind_training_dataset(api,stack):
    graph=api._default_application.training_pipeline;owner=graph._training_dataset_generator
    for attribute,mapping in DIRECT:
        stack.enter_context(patch.object(owner,attribute,replace(getattr(owner,attribute),**{field:(lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)) for field,name in mapping.items()})))
    for attribute,mapping in GETTERS:
        stack.enter_context(patch.object(owner,attribute,replace(getattr(owner,attribute),**{field:(lambda _name=name:getattr(api,_name)) for field,name in mapping.items()})))
    stack.enter_context(patch.object(owner,'output',lambda:api.output_write_dir_for_owner));stack.enter_context(patch.object(owner,'update_provider',lambda:api.update_training_task))
    planner=graph._training_sample_planner
    for field,name in (('split','split_counts'),('missing','missing_count_for_false_sample'),('poses','preview_pose_family_sequence')):
        stack.enter_context(patch.object(planner,field,lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)))
    links=graph._training_output_links
    stack.enter_context(patch.object(links,'media',replace(links.media,output_root=lambda:api.OUTPUT_DIR,public_url=lambda path:api.public_output_url(path))))
    stack.enter_context(patch.object(graph._training_annotation_preview,'public_url',lambda path:api.public_training_output_url(path)))


def assert_default_training_dataset(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.training.dataset_generation import DatasetGenerator
    from local_inspection_service.training.sample_plan import SamplePlanner
    from local_inspection_service.training.annotations import TrainingOutputLinks,AnnotationPreview
    from local_inspection_service.runtime.wiring import training_pipeline
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;infra=app.infrastructure;inspection=app.inspection;owner=graph._training_dataset_generator;planner=graph._training_sample_planner;links=graph._training_output_links;annotation=graph._training_annotation_preview;item,other,third=object(),object(),object()
    for name,kind in (('_training_dataset_generator',DatasetGenerator),('_training_sample_planner',SamplePlanner),('_training_output_links',TrainingOutputLinks),('_training_annotation_preview',AnnotationPreview)):
        case.assertIs(type(getattr(graph,name)),kind);case.assertIs(getattr(api,name),getattr(graph,name))
    case.assertIs(owner.files,app.artifacts.files);case.assertIs(annotation.images,infra._training_image_io);case.assertIs(annotation.images.files,app.artifacts.files);case.assertIs(annotation.images.files.runtime_provider,app.artifacts.files.runtime_provider)
    for selected,name in ((owner.render.max_occlusion,'DETECTION_MAX_OCCLUSION_FRACTION'),(owner.render.min_visible_area,'DETECTION_MIN_VISIBLE_AREA_PX'),(links.media.output_root,'OUTPUT_DIR')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)
    for selected,target,method,args,kw,forwarded,forward_kw in ((owner.records.load,infra._app_configuration,'load_config',(),{},(),{}),(owner.records.save,infra._app_configuration,'save_config',(item,),{},(item,),{}),(owner.records.normalize_assets,graph._training_asset_preparation,'ensure_training_normalized_assets_for_selection',(item,other),{},(item,other),{}),(owner.records.select,inspection._accessory_selection,'selected_accessories',(item,other),{},(item,other),{}),(owner.plan.build,planner,'build_training_sample_plan',(item,17,41,other),{},(item,17,41,other),{}),(owner.plan.normalize_pose(),inspection._preview_pose_policy,'normalize_preview_pose_family_policy',(item,),{},(item,),{}),(owner.plan.background(),graph._background_selection,'selected_background_set_id',(item,),{},(item,None,None),{}),(owner.render.draw(),graph._training_preview_renderer,'draw_training_preview',(item,other,17),{},(item,other,17,None,None,None),{}),(owner.render.annotation(),annotation,'write_training_annotation_preview',(item,other,third),{},(item,other,third),{}),(owner.output(),infra._service_paths,'output_write_dir_for_owner',(item,other),{},(item,other),{}),(owner.update_provider(),graph._training_state_workflows,'update_training_task',(item,),{'status':other},(item,),{'status':other}),(planner.poses,inspection._preview_pose_policy,'preview_pose_family_sequence',(item,17,other),{},(item,17,other),{}),(links.media.public_url,infra._service_paths,'public_output_url',(item,),{},(item,),{}),(annotation.public_url,links,'public_training_output_url',(item,),{},(item,),{}),(api.generate_training_dataset,owner,'generate_training_dataset',(item,),{},(item,),{})):
        assert_native_relay(case,selected,(target,method,args,kw,forwarded,forward_kw))
    for selected,target,name,args in ((owner.records.uses_ocr,training_pipeline._accessory_policy,'accessory_uses_ocr',(item,)),(planner.split,training_pipeline,'split_counts',(17,)),(planner.missing,training_pipeline,'missing_count_for_false_sample',(17,item))):
        with patch.object(target,name,return_value=other) as receiver:case.assertIs(selected(*args),other);receiver.assert_called_once_with(*args)
    with patch.object(training_pipeline,'_write_dataset_yaml',return_value=other) as receiver:case.assertIs(owner.render.yaml(item,other,third),other);receiver.assert_called_once_with(item,other,third,files=owner.files)
    draw_kw={'seed':17,'pose_family_policy':item,'split':other,'background_set_id':third}
    assert_native_relay(case,owner.render.draw(),(graph._training_preview_renderer,'draw_training_preview',(item,other),draw_kw,(item,other,17,item,other,third),{}))
    case.assertIs(owner.render.label(),training_pipeline.yolo_detection_label_line)

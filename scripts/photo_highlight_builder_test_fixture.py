"""Native photo mask builder contracts and actual default receiver witnesses."""
from local_inspection_service.agent import photo_highlight_builder_ports as ports
from local_inspection_service.agent.photo_highlight_builder import PhotoHighlightSpriteBuilder
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.images import ImageFiles


def photo_highlight_builder_fixture(server, groups):
    from scripts.photo_highlight_workflow_test_fixture import photo_highlight_workflow_fixture
    from scripts.photo_highlight_image_test_fixture import photo_highlight_image_fixture
    api = photo_highlight_workflow_fixture(server)
    image = photo_highlight_image_fixture(server)
    assert_default_builder(server, groups)
    for _, _, bindings in groups:
        for source in bindings.values():
            if '.' not in source and not hasattr(api, source):
                setattr(api, source, getattr(server, source))
    api.time, api.cv2, api.np = server.time, server.cv2, server.np
    for name in ('photo_highlight_mask_prompt','photo_highlight_input_data_url','photo_highlight_auto_compare','decode_photo_highlight_mask','photo_highlight_auto_roi_mask'):
        setattr(api,name,getattr(image,name))
    capabilities=[]
    for _, kind, bindings in groups:
        def supplier(source):
            def selected():
                value=api
                for part in source.split('.'):
                    value=getattr(value,part)
                return value
            return selected
        capabilities.append(getattr(ports,kind)(**{field:supplier(source) for field,source in bindings.items()}))
    files=BusinessFiles(lambda:None)
    builder=PhotoHighlightSpriteBuilder(*capabilities,files=files,images=ImageFiles(lambda:api.cv2,files=files))
    api.build_clean_sprites_from_photo_highlight_masks=builder.build_clean_sprites_from_photo_highlight_masks
    return api


def assert_default_builder(server, groups):
    import unittest
    from unittest.mock import patch
    from pathlib import Path
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import training_pipeline
    case=unittest.TestCase()
    application=server._default_application
    graph=application.training_pipeline._photo_pose_workflows
    actual=graph.builder
    case.assertIs(type(actual),PhotoHighlightSpriteBuilder)
    case.assertIs(server._photo_highlight_sprite_builder,actual)
    case.assertIs(actual.files,application.artifacts.files)
    case.assertIs(type(actual.images),ImageFiles)
    case.assertIs(actual.images.files,application.artifacts.files)
    case.assertIs(actual.images.cv2_provider(),training_pipeline.cv2)
    item,other,image,mask=object(),object(),object(),object()
    path=Path('synthetic.png')
    native={
        'clean_sprites_policy_complete':(application.inspection._sprite_asset_catalog,(item,other),(item,other)),
        'output_write_dir_for_owner':(application.infrastructure._service_paths,('mask','owner'),('mask','owner')),
        'safe_record_id':(application.inspection._pose_collection_jobs,(item,),(item,)),
        'write_clean_sprite':(application.inspection._sprite_artifact_writer,(path,image,mask,other),(path,image,mask,other)),
        'public_output_url_for_existing':(application.infrastructure._service_paths,(path,),(path,)),
        'pose_render_footprint_metadata':(application.inspection._sprite_footprint,('lying',other,item),('lying',other,item)),
        'normalize_sprite_family_canvases':(application.inspection._sprite_canvas_normalizer,(other,),(other,)),
        'apply_upright_scale_correction_metadata':(application.inspection._sprite_scale,(other,item),(other,item)),
        'apply_laying_standard_render_size_hints':(application.inspection._sprite_render_metadata,(other,),(other,)),
    }
    bound_names=('object_photo_highlight_source_paths','photo_highlight_clean_sprites_ready','photo_highlight_mask_prompt','photo_highlight_input_data_url','photo_highlight_auto_compare')
    pure={
        'decode_photo_highlight_mask':('_decode_photo_highlight_mask_impl',(image,),(image,)),
        'photo_highlight_auto_roi_mask':('_photo_highlight_auto_roi_mask_impl',(image,mask),(image,mask)),
        'alpha_bbox':('_alpha_bbox_impl',(mask,),(mask,8)),
    }
    for name,kind,bindings in groups:
        port=getattr(actual,'_'+name)
        case.assertIs(type(port),getattr(ports,kind))
        for field,source in bindings.items():
            selected=getattr(port,field)()
            if source.isupper():
                case.assertIs(selected,getattr(application.values,source))
                case.assertIn(source,('PHOTO_HIGHLIGHT_MIN_REFERENCE_IMAGES','NORMALIZED_DIR','PHOTO_HIGHLIGHT_MASK_MAX_ATTEMPTS','AGENT_MCP_SPRITE_BUILD_VERSION','PHOTO_HIGHLIGHT_SPRITE_BUILD_VERSION'))
                original=getattr(application.values,source)
                replacement=original+101 if type(original) is int else Path('synthetic-normalized-root')
                try:
                    object.__setattr__(application.values,source,replacement)
                    case.assertIs(getattr(port,field)(),replacement)
                finally:
                    object.__setattr__(application.values,source,original)
            elif source in native:
                owner,args,forwarded=native[source]
                assert_native_relay(case,selected,(owner,source,args,{},forwarded,{}))
            elif source in bound_names:
                case.assertIs(selected.__self__,graph)
                case.assertIs(selected.__func__,getattr(type(graph),source))
            elif source in pure:
                attribute,args,forwarded=pure[source]
                sentinel=object()
                with patch.object(training_pipeline,attribute,return_value=sentinel) as callee:
                    case.assertIs(selected(*args),sentinel)
                    callee.assert_called_once_with(*forwarded)
                    for observed,expected in zip(callee.call_args.args,forwarded):
                        if type(expected) is object:case.assertIs(observed,expected)
                    if source=='alpha_bbox':
                        for threshold in (8,28):
                            callee.reset_mock()
                            case.assertIs(selected(mask,threshold=threshold),sentinel)
                            callee.assert_called_once_with(mask,threshold)
                            case.assertIs(callee.call_args.args[0],mask)
            elif source in ('accessory_material_type','object_alpha_material_policy','accessory_uid'):
                forwarded=(item,None) if source=='object_alpha_material_policy' else (item,)
                sentinel=object()
                with patch.object(training_pipeline._accessory_policy,source,return_value=sentinel) as callee:
                    case.assertIs(selected(item),sentinel)
                    callee.assert_called_once_with(*forwarded)
                    case.assertIs(callee.call_args.args[0],item)
            elif source in ('image_processing_item','upsert_data_analysis_image_processing_record'):
                owner=application.inspection._analysis_processing if source=='image_processing_item' else application.inspection._analysis_publisher
                case.assertIs(selected.__self__,owner)
                case.assertIs(selected.__func__,getattr(type(owner),source))
            else:
                case.assertIn(source,('AiProviderError','time.time','bounded_text','sanitize_data_analysis_record_id'))
                expected=training_pipeline
                for part in source.split('.'):
                    expected=getattr(expected,part)
                case.assertIs(selected,expected)

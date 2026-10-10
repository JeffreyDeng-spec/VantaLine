"""Native sprite writer and canvas normalization contracts with explicit I/O."""
from types import SimpleNamespace
from local_inspection_service.accessories.sprite_artifact_writer import SpriteArtifactWriter
from local_inspection_service.accessories.sprite_canvas_normalization import SpriteCanvasNormalizer
from local_inspection_service.accessories.sprite_publication_ports import SpriteArtifactGeometry,SpriteArtifactMetadata,SpriteImageEncoder,SpriteCanvasGeometry,SpriteCanvasImageReads,SpriteResampling


def sprite_publication_fixture(server):
    assert_default_publication(server)
    names=('cv2','normalize_sprite_upright','material_aware_object_alpha','pose_render_footprint_metadata',
        'add_sprite_safety_margin','alpha_bbox','alpha_edge_max','alpha_edge_stats','trim_masked_asset','resolve_service_path')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    encoder=SpriteImageEncoder(convert=lambda:api.cv2.cvtColor,bgra_mode=lambda:api.cv2.COLOR_BGR2BGRA,write=lambda:api.cv2.imwrite)
    writer=SpriteArtifactWriter(SpriteArtifactGeometry(normalize=lambda:api.normalize_sprite_upright,margin=lambda:api.add_sprite_safety_margin,
        bounds=lambda:api.alpha_bbox,edge_max=lambda:api.alpha_edge_max,edge_stats=lambda:api.alpha_edge_stats),
        SpriteArtifactMetadata(alpha=lambda:api.material_aware_object_alpha,footprint=lambda:api.pose_render_footprint_metadata),encoder)
    canvas=SpriteCanvasNormalizer(SpriteCanvasGeometry(trim=lambda:api.trim_masked_asset,margin=lambda:api.add_sprite_safety_margin,
        bounds=lambda:api.alpha_bbox,edge_max=lambda:api.alpha_edge_max,edge_stats=lambda:api.alpha_edge_stats),
        SpriteCanvasImageReads(resolve=lambda:api.resolve_service_path,decode=lambda:api.cv2.imread,unchanged_mode=lambda:api.cv2.IMREAD_UNCHANGED),
        SpriteResampling(resize=lambda:api.cv2.resize,cubic=lambda:api.cv2.INTER_CUBIC,area=lambda:api.cv2.INTER_AREA,linear=lambda:api.cv2.INTER_LINEAR),encoder)
    api.write_clean_sprite=writer.write_clean_sprite
    api.normalize_sprite_family_canvases=canvas.normalize_sprite_family_canvases
    return api


def assert_default_publication(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    verify_actual_sources()
    case=unittest.TestCase();app=server._default_application;graph=app.inspection
    writer,canvas=graph._sprite_artifact_writer,graph._sprite_canvas_normalizer
    for owner,kind,name in ((writer,SpriteArtifactWriter,'_sprite_artifact_writer'),(canvas,SpriteCanvasNormalizer,'_sprite_canvas_normalizer')):
        case.assertIs(type(owner),kind);case.assertIs(getattr(server,name),owner)
    item,mask,metadata=object(),object(),object()
    for selected,target,method,args,keywords,forwarded,forward_keywords in (
        (writer._geometry.normalize(),graph._sprite_geometry,'normalize_sprite_upright',(item,mask),{},(item,mask),{}),
        (writer._metadata.alpha(),graph._material_alpha,'material_aware_object_alpha',(item,mask),{},(item,mask,None),{}),
        (writer._metadata.alpha(),graph._material_alpha,'material_aware_object_alpha',(item,mask),{'metadata':metadata},(item,mask,metadata),{}),
        (writer._metadata.footprint(),graph._sprite_footprint,'pose_render_footprint_metadata',('top',[2,3],metadata),{},('top',[2,3],metadata),{}),
        (canvas._images.resolve(),app.infrastructure._service_paths,'resolve_service_path',(item,),{'for_write':True},(item,),{'for_write':True}),
        (canvas._images.resolve(),app.infrastructure._service_paths,'resolve_service_path',(item,),{},(item,),{'for_write':False}),
        (server.write_clean_sprite,writer,'write_clean_sprite',(item,item,mask),{},(item,item,mask,None),{}),
        (server.write_clean_sprite,writer,'write_clean_sprite',(item,item,mask),{'metadata':metadata},(item,item,mask,metadata),{}),
        (server.normalize_sprite_family_canvases,canvas,'normalize_sprite_family_canvases',([metadata],),{},([metadata],),{}),
    ):
        # Lists must be shared by caller and expected argument, not reconstructed.
        if method=='pose_render_footprint_metadata' or method=='normalize_sprite_family_canvases':forwarded=args
        assert_native_relay(case,selected,(target,method,args,keywords,forwarded,forward_keywords))
    for geometry in (writer._geometry,canvas._geometry):
        with patch.object(inspection,'_alpha_bbox_impl',return_value=metadata) as callee:
            case.assertIs(geometry.bounds()(mask),metadata);callee.assert_called_once_with(mask,8)
        for selected,name,args,forwarded in (
            (geometry.margin(),'_add_sprite_safety_margin_impl',(item,mask,19),(item,mask,19)),
            (geometry.bounds(),'_alpha_bbox_impl',(mask,27),(mask,27)),
            (geometry.edge_max(),'_alpha_edge_max_impl',(mask,),(mask,)),
            (geometry.edge_stats(),'_alpha_edge_stats_impl',(mask,),(mask,)),
        ):
            sentinel=object()
            with patch.object(inspection,name,return_value=sentinel) as callee:
                case.assertIs(selected(*args),sentinel);callee.assert_called_once_with(*forwarded)
                case.assertIs(callee.call_args.args[0],args[0])
    with patch.object(inspection,'_trim_masked_asset_impl',return_value=metadata) as callee:
        case.assertIs(canvas._geometry.trim()(item,mask,23),metadata);callee.assert_called_once_with(item,mask,23)
    with patch.object(inspection,'_trim_masked_asset_impl',return_value=metadata) as callee:
        case.assertIs(canvas._geometry.trim()(item,mask,pad=8),metadata);callee.assert_called_once_with(item,mask,8)
    for encoder in (writer._encoder,canvas._encoder):
        case.assertIs(encoder.convert(),inspection.cv2.cvtColor);case.assertEqual(encoder.bgra_mode(),inspection.cv2.COLOR_BGR2BGRA)
    case.assertEqual(canvas._images.unchanged_mode(),inspection.cv2.IMREAD_UNCHANGED)
    case.assertIs(canvas._sampling.resize(),inspection.cv2.resize)
    for selected,name in ((canvas._sampling.cubic,'INTER_CUBIC'),(canvas._sampling.area,'INTER_AREA'),(canvas._sampling.linear,'INTER_LINEAR')):
        case.assertEqual(selected(),getattr(inspection.cv2,name))
    files,images=app.artifacts.files,app.artifacts.images
    for getter,name,args in ((writer._encoder.write,'imwrite',('synthetic',item)),(canvas._encoder.write,'imwrite',('synthetic',item)),(canvas._images.decode,'imread',('synthetic',19))):
        with patch.object(files,'runtime_provider',return_value=None):case.assertIs(getter(),getattr(inspection.cv2,name))
        with patch.object(files,'runtime_provider',return_value=object()):
            selected=getter();case.assertIs(selected.__self__,images)
            case.assertIs(selected.__func__,getattr(type(images),'_'+name))
            assert_native_relay(case,lambda *values:getter()(*values),(images,'_'+name,args,{},args,{}))

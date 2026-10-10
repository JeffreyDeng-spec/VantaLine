"""Finite compositing ports; verify canonical defaults before substitution."""
from types import SimpleNamespace
from local_inspection_service.accessories.compositing import AssetCompositor
from local_inspection_service.accessories.compositing_ports import CompositionGeometry,CompositionOperations


def compositing_fixture(server):
    assert_default_compositing(server)
    names=('cv2','trim_masked_asset','resize_masked_asset_to_visible_footprint','visible_mask_size_px',
        'trim_rect_asset','physical_mask_for_rect_asset','paste_rectified_document_asset','long_axis_unified_render_box')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    owner=AssetCompositor(CompositionGeometry(trim=lambda:api.trim_masked_asset,
        resize_footprint=lambda:api.resize_masked_asset_to_visible_footprint,visible_size=lambda:api.visible_mask_size_px),
        CompositionOperations(paste_masked=lambda:api.paste_masked_asset,trim_rect=lambda:api.trim_rect_asset,
            physical_mask=lambda:api.physical_mask_for_rect_asset))
    for name in ('paste_masked_asset','paste_physical_object_asset','paste_rotated_asset'):
        setattr(api,name,getattr(owner,name))
    return api


def assert_default_compositing(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    from local_inspection_service.compatibility import infrastructure as legacy
    verify_actual_sources()
    case=unittest.TestCase()
    graph=server._default_application.inspection
    owner=graph._asset_compositor
    case.assertIs(type(owner),AssetCompositor)
    case.assertIs(server._asset_compositor,owner)
    item,mask=object(),object()
    for selected,target,method,args,forwarded in (
        (owner._geometry.resize_footprint(),graph._sprite_geometry,'resize_masked_asset_to_visible_footprint',(item,mask,(2,3)),(item,mask,(2,3),False)),
        (owner._geometry.visible_size(),graph._sprite_geometry,'visible_mask_size_px',(mask,),(mask,)),
        (owner._operations.paste_masked(),owner,'paste_masked_asset',(item,item,mask,(2,3),(4,5),6),(item,item,mask,(2,3),(4,5),6,True,False,True)),
        (server.paste_masked_asset,owner,'paste_masked_asset',(item,item,mask,(2,3),(4,5),6),(item,item,mask,(2,3),(4,5),6,True,False,True)),
        (server.paste_physical_object_asset,owner,'paste_physical_object_asset',(item,item,mask,(2,3),4,5,6),(item,item,mask,(2,3),4,5,6,False)),
        (server.paste_rotated_asset,owner,'paste_rotated_asset',(item,item,(2,3),(4,5),6),(item,item,(2,3),(4,5),6)),
    ):
        assert_native_relay(case,selected,(target,method,args,{},forwarded,{}))
    for selected,target,method,args,keywords,forwarded in (
        (owner._geometry.resize_footprint(),graph._sprite_geometry,'resize_masked_asset_to_visible_footprint',(item,mask,(2,3)),{'preserve_aspect_ratio':True},(item,mask,(2,3),True)),
        (owner._operations.paste_masked(),owner,'paste_masked_asset',(item,item,mask,(2,3),(4,5),6),{'trim_before_paste':False,'return_visible_mask':True,'resize_to_target':False},(item,item,mask,(2,3),(4,5),6,False,True,False)),
        (server.paste_masked_asset,owner,'paste_masked_asset',(item,item,mask,(2,3),(4,5),6),{'trim_before_paste':False,'return_visible_mask':True,'resize_to_target':False},(item,item,mask,(2,3),(4,5),6,False,True,False)),
        (server.paste_physical_object_asset,owner,'paste_physical_object_asset',(item,item,mask,(2,3),4,5,6),{'preserve_aspect_ratio':True},(item,item,mask,(2,3),4,5,6,True)),
        (owner._operations.paste_masked(),owner,'paste_masked_asset',(item,item,mask,(2,3),(4,5),6),{'trim_before_paste':True,'return_visible_mask':True,'resize_to_target':False},(item,item,mask,(2,3),(4,5),6,True,True,False)),
        (server.paste_masked_asset,owner,'paste_masked_asset',(item,item,mask,(2,3),(4,5),6),{'trim_before_paste':True,'return_visible_mask':True,'resize_to_target':False},(item,item,mask,(2,3),(4,5),6,True,True,False)),
    ):
        assert_native_relay(case,selected,(target,method,args,keywords,forwarded,{}))
    for selected,module,name,args,forwarded in (
        (owner._geometry.trim(),inspection,'_trim_masked_asset_impl',(item,mask),(item,mask,4)),
        (owner._operations.trim_rect(),inspection,'_trim_rect_asset_impl',(item,),(item,0)),
        (owner._operations.physical_mask(),inspection,'_physical_mask_for_rect_asset_impl',(item,),(item,)),
        (server.trim_rect_asset,legacy,'_trim_rect_asset_impl',(item,),(item,0)),
        (server.paste_rectified_document_asset,legacy,'_paste_rectified_document_asset_impl',(item,item,(2,3),(4,5),6),(item,item,(2,3),(4,5),6)),
        (server.long_axis_unified_render_box,legacy,'_long_axis_unified_render_box_impl',(2,3,4,5),(2,3,4,5)),
    ):
        sentinel=object()
        with patch.object(module,name,return_value=sentinel) as callee:
            case.assertIs(selected(*args),sentinel)
            callee.assert_called_once_with(*forwarded)

"""Native cutout geometry with a finite, live test capability surface."""
from types import SimpleNamespace
from local_inspection_service.accessories.cutout_selection import ObjectCutoutSelection
from local_inspection_service.accessories.chroma_cutouts import ChromaCutoutProcessor
from local_inspection_service.accessories.cutout_geometry_ports import SelectionOperations,ChromaPolicyOperations,ChromaMatteOperations


def cutout_geometry_fixture(server):
    assert_default_cutout_geometry(server)
    names=('cv2','foreground_mask','ai_background_cutout_with_bbox','normalize_chroma_screen',
        'saturated_chroma_mask','suppress_green_spill','bright_green_conveyor_mask')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    selection=ObjectCutoutSelection(SelectionOperations(foreground=lambda:api.foreground_mask,
        object_fallback=lambda:api.object_cutout_from_image,bounded_ai=lambda:api.ai_background_cutout_with_bbox,
        bounded_green=lambda:api.green_screen_object_cutout_with_bbox))
    chroma=ChromaCutoutProcessor(ChromaPolicyOperations(normalize=lambda:api.normalize_chroma_screen,
        saturated=lambda:api.saturated_chroma_mask,green_spill=lambda:api.suppress_green_spill),
        ChromaMatteOperations(background=lambda:api.chroma_background_mask,distance=lambda:api.chroma_distance_alpha,
            spill=lambda:api.suppress_chroma_spill))
    for owner,names in ((selection,('object_cutout_from_image','green_screen_object_cutout_with_bbox','ai_background_cutout','green_screen_object_cutout')),
        (chroma,('suppress_chroma_spill','chroma_background_mask','chroma_distance_alpha','chroma_screen_object_cutout','green_conveyor_object_cutout'))):
        for name in names:setattr(api,name,getattr(owner,name))
    return api


def assert_default_cutout_geometry(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    verify_actual_sources()
    case=unittest.TestCase()
    graph=server._default_application.inspection
    selection,chroma=graph._cutout_selection,graph._chroma_cutouts
    case.assertIs(type(selection),ObjectCutoutSelection)
    case.assertIs(type(chroma),ChromaCutoutProcessor)
    case.assertIs(server._cutout_selection,selection)
    case.assertIs(server._chroma_cutouts,chroma)
    item,other=object(),object()
    for selected,target,method,args,forwarded in (
        (selection._selection.object_fallback(),selection,'object_cutout_from_image',(item,other),(item,other)),
        (selection._selection.bounded_ai(),graph._background_cutouts,'ai_background_cutout_with_bbox',(item,),(item,)),
        (selection._selection.bounded_green(),selection,'green_screen_object_cutout_with_bbox',(item,other),(item,other)),
        (chroma._policy.normalize(),graph._reference_evidence,'normalize_chroma_screen',(item,),(item,)),
        (chroma._matte.background(),chroma,'chroma_background_mask',(item,),(item,None)),
        (chroma._matte.distance(),chroma,'chroma_distance_alpha',(item,),(item,None)),
        (chroma._matte.spill(),chroma,'suppress_chroma_spill',(item,),(item,None)),
    ):
        assert_native_relay(case,selected,(target,method,args,{},forwarded,{}))
    for target,names in ((selection,('object_cutout_from_image','green_screen_object_cutout_with_bbox','ai_background_cutout','green_screen_object_cutout')),
        (chroma,('suppress_chroma_spill','chroma_background_mask','chroma_distance_alpha','chroma_screen_object_cutout','green_conveyor_object_cutout'))):
        for name in names:
            args=(item,other) if name in ('object_cutout_from_image','green_screen_object_cutout_with_bbox','green_screen_object_cutout') else (item,)
            forwarded=args+(None,) if name in ('suppress_chroma_spill','chroma_background_mask','chroma_distance_alpha','chroma_screen_object_cutout') else args
            assert_native_relay(case,getattr(server,name),(target,name,args,{},forwarded,{}))
    for selected,name in ((chroma._matte.background(),'chroma_background_mask'),(chroma._matte.distance(),'chroma_distance_alpha'),
        (chroma._matte.spill(),'suppress_chroma_spill'),(server.suppress_chroma_spill,'suppress_chroma_spill'),
        (server.chroma_background_mask,'chroma_background_mask'),(server.chroma_distance_alpha,'chroma_distance_alpha'),
        (server.chroma_screen_object_cutout,'chroma_screen_object_cutout')):
        assert_native_relay(case,selected,(chroma,name,(item,),{'screen':other},(item,other),{}))
    for selected,name,args in (
        (selection._selection.foreground(),'_foreground_mask_impl',(item,)),
        (chroma._policy.saturated(),'_saturated_chroma_mask_impl',(item,other)),
        (chroma._policy.green_spill(),'_suppress_green_spill_impl',(item,)),
    ):
        sentinel=object()
        with patch.object(inspection,name,return_value=sentinel) as callee:
            case.assertIs(selected(*args),sentinel)
            callee.assert_called_once_with(*args)
            case.assertIs(callee.call_args.args[0],item)

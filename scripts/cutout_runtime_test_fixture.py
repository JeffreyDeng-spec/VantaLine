"""Shared native cutout lifecycle with explicit session and green operations."""
from types import SimpleNamespace
from local_inspection_service.accessories.cutout_runtime import RembgSessionRuntime
from local_inspection_service.accessories.background_cutouts import BackgroundCutoutProcessor
from local_inspection_service.accessories.cutout_ports import CutoutRuntimeOperations,CutoutGreenOperations


def cutout_runtime_fixture(server):
    assert_default_cutout_runtime(server)
    names=('cv2','bright_green_conveyor_mask','suppress_green_spill')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    api._rembg_runtime=RembgSessionRuntime()
    api.rembg_session=lambda:api._rembg_runtime.rembg_session()
    owner=BackgroundCutoutProcessor(CutoutRuntimeOperations(session=lambda:api.rembg_session,
        lock=lambda:api._rembg_runtime.lock),CutoutGreenOperations(mask=lambda:api.bright_green_conveyor_mask,
        spill=lambda:api.suppress_green_spill))
    api.ai_background_cutout_with_bbox=owner.ai_background_cutout_with_bbox
    api.precise_green_plate_cutout=owner.precise_green_plate_cutout
    return api


def assert_default_cutout_runtime(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    verify_actual_sources()
    case=unittest.TestCase()
    graph=server._default_application.inspection
    owner,runtime=graph._background_cutouts,graph._rembg_runtime
    case.assertIs(type(owner),BackgroundCutoutProcessor)
    case.assertIs(type(runtime),RembgSessionRuntime)
    case.assertIs(server._background_cutouts,owner)
    case.assertIs(server._rembg_runtime,runtime)
    case.assertIs(owner._runtime.lock(),runtime.lock)
    item=object()
    for selected,target,method,args in (
        (owner._runtime.session(),runtime,'rembg_session',()),
        (server.rembg_session,runtime,'rembg_session',()),
        (server.ai_background_cutout_with_bbox,owner,'ai_background_cutout_with_bbox',(item,)),
        (server.precise_green_plate_cutout,owner,'precise_green_plate_cutout',(item,)),
    ):
        assert_native_relay(case,selected,(target,method,args,{},args,{}))
    for selected,name in ((owner._green.mask(),'_bright_green_conveyor_mask_impl'),(owner._green.spill(),'_suppress_green_spill_impl')):
        sentinel=object()
        with patch.object(inspection,name,return_value=sentinel) as callee:
            case.assertIs(selected(item),sentinel)
            callee.assert_called_once_with(item)
            case.assertIs(callee.call_args.args[0],item)

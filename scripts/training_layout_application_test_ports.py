"""Finite native placement and mask conversion dependencies."""
from unittest.mock import patch


def bind_training_layout(api,stack):
    graph=api._default_application.training_pipeline;placement=graph._preview_placement;masks=graph._preview_masks
    for field,name in (('canvas','PREVIEW_CANVAS_SIZE_PX'),('constrained','constrained_center_range'),('intersection','rotated_rect_overlap_area')):
        stack.enter_context(patch.object(placement,field,lambda _name=name:getattr(api,_name)))
    for field,name in (('rectangle','rotated_rect_tuple'),('random_center','random_center_inside_background'),('overlap','object_placement_overlap_area')):
        stack.enter_context(patch.object(placement,field,lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)))
    stack.enter_context(patch.object(masks,'contour',lambda:api.contour_to_polygon));stack.enter_context(patch.object(masks,'polygons',lambda *args:api.visible_polygons_from_mask(*args)))


def assert_default_training_layout(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.training.preview_placement import PreviewPlacement
    from local_inspection_service.training.preview_masks import PreviewMasks
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;placement=graph._preview_placement;masks=graph._preview_masks;item,other,third,fourth=object(),object(),object(),object()
    case.assertIs(type(placement),PreviewPlacement);case.assertIs(type(masks),PreviewMasks);case.assertIs(api._preview_placement,placement);case.assertIs(api._preview_masks,masks)
    original=app.values.PREVIEW_CANVAS_SIZE_PX;case.assertIs(placement.canvas(),original)
    try:object.__setattr__(app.values,'PREVIEW_CANVAS_SIZE_PX',other);case.assertIs(placement.canvas(),other)
    finally:object.__setattr__(app.values,'PREVIEW_CANVAS_SIZE_PX',original)
    case.assertIs(placement.constrained(),wiring.constrained_center_range);case.assertIs(placement.intersection(),wiring.rotated_rect_overlap_area);case.assertIs(masks.contour(),wiring.contour_to_polygon)
    with patch.object(wiring,'rotated_rect_tuple',return_value=other) as receiver:case.assertIs(placement.rectangle(item,other,third),other);receiver.assert_called_once_with(item,other,third)
    for selected,target,method,args in ((placement.random_center,placement,'random_center_inside_background',(item,other,third,fourth)),(placement.overlap,placement,'object_placement_overlap_area',(item,other,third,fourth)),(masks.polygons,masks,'visible_polygons_from_mask',(item,other))):assert_native_relay(case,selected,(target,method,args,{},args,{}))

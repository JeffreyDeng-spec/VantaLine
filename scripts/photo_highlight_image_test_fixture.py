"""Finite image contract fixture with separate default graph witnesses."""
from types import SimpleNamespace


class PhotoHighlightImageContractFixture(SimpleNamespace):
    pass


def photo_highlight_image_fixture(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.agent.photo_highlight_image_input import PhotoHighlightImageInput
    from local_inspection_service.agent.photo_highlight_comparison import PhotoHighlightComparison
    from local_inspection_service.agent.photo_highlight_image_ports import PhotoHighlightImagePolicy, PhotoMaskGeometry
    from local_inspection_service.runtime.wiring import training_pipeline
    from local_inspection_service.agent import photo_highlight_masks
    verify_actual_sources()
    case = unittest.TestCase()
    application = server._default_application
    graph = application.training_pipeline
    inputs, comparison = graph._photo_highlight_image_input, graph._photo_highlight_comparison
    case.assertIs(type(inputs), PhotoHighlightImageInput)
    case.assertIs(type(comparison), PhotoHighlightComparison)
    case.assertIs(server._photo_highlight_image_input, inputs)
    case.assertIs(server._photo_highlight_comparison, comparison)
    case.assertIs(inputs._policy.max_side(), application.values.PHOTO_HIGHLIGHT_MASK_MAX_SIDE)
    original_max_side = application.values.PHOTO_HIGHLIGHT_MASK_MAX_SIDE
    try:
        for max_side in (8, 32, 8):
            object.__setattr__(application.values, 'PHOTO_HIGHLIGHT_MASK_MAX_SIDE', max_side)
            case.assertIs(inputs._policy.max_side(), max_side)
    finally:
        object.__setattr__(application.values, 'PHOTO_HIGHLIGHT_MASK_MAX_SIDE', original_max_side)
    case.assertIs(comparison._geometry.iou(), training_pipeline.bbox_iou_xyxy)
    item, mask, sentinel = object(), object(), object()
    with patch.object(training_pipeline._accessory_policy, 'accessory_uid', return_value=sentinel) as callee:
        case.assertIs(inputs._policy.identifier()(item), sentinel)
        callee.assert_called_once_with(item)
        case.assertIs(callee.call_args.args[0], item)
    with patch.object(training_pipeline, '_alpha_bbox_impl', return_value=sentinel) as callee:
        case.assertIs(comparison._geometry.alpha()(mask), sentinel)
        callee.assert_called_once_with(mask, 8)
        case.assertIs(callee.call_args.args[0], mask)
        callee.reset_mock()
        case.assertIs(comparison._geometry.alpha()(mask, threshold=28), sentinel)
        callee.assert_called_once_with(mask, 28)
        case.assertIs(callee.call_args.args[0], mask)
    api = PhotoHighlightImageContractFixture(**{name: getattr(server, name) for name in (
        'cv2', 'np', 'accessory_uid', 'PHOTO_HIGHLIGHT_MASK_MAX_SIDE', 'alpha_bbox', 'bbox_iou_xyxy')})
    native_inputs = PhotoHighlightImageInput(PhotoHighlightImagePolicy(lambda: api.accessory_uid, lambda: api.PHOTO_HIGHLIGHT_MASK_MAX_SIDE))
    native_comparison = PhotoHighlightComparison(PhotoMaskGeometry(lambda: api.alpha_bbox, lambda: api.bbox_iou_xyxy))
    api.photo_highlight_mask_prompt = native_inputs.photo_highlight_mask_prompt
    api.photo_highlight_input_data_url = native_inputs.photo_highlight_input_data_url
    api.photo_highlight_auto_compare = native_comparison.photo_highlight_auto_compare
    api.decode_photo_highlight_mask = photo_highlight_masks.decode_photo_highlight_mask
    api.photo_highlight_auto_roi_mask = photo_highlight_masks.photo_highlight_auto_roi_mask
    return api

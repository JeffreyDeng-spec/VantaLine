"""Native annotation contracts and actual default media/storage witnesses."""
from types import SimpleNamespace
from local_inspection_service.detection.annotation import DetectionAnnotation


def detection_annotation_fixture(server):
    assert_default_annotation(server)
    names=('normalize_ai_box_2d','bounded_text','cv2','output_write_dir','output_url')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    owner=DetectionAnnotation(lambda value:api.normalize_ai_box_2d(value),lambda:api.ai_box_2d_to_pixels,
        lambda:api.bounded_text,lambda:api.cv2,lambda kind:api.output_write_dir(kind),lambda path:api.output_url(path),
        lambda image,detections,rule:api.draw_ai_detection_boxes(image,detections,rule),
        lambda image,request_id:api.write_ai_original_output(image,request_id),runtime_provider=lambda:None)
    for name in ('ai_box_2d_to_pixels','draw_ai_detection_boxes','write_ai_original_output','write_ai_annotated_output'):
        setattr(api,name,getattr(owner,name))
    return api


def assert_default_annotation(server):
    import unittest
    from unittest.mock import patch
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    from local_inspection_service.compatibility import infrastructure as legacy_infrastructure
    verify_actual_sources()
    case=unittest.TestCase()
    application=server._default_application
    owner=application.inspection._detection_annotation
    case.assertIs(type(owner),DetectionAnnotation)
    case.assertIs(server._detection_annotation,owner)
    case.assertIs(owner.images(),inspection.cv2)
    case.assertIs(owner.text(),inspection.bounded_text)
    item,other,rule=object(),object(),object()
    for selected,target,method,args in (
        (owner.pixels(),owner,'ai_box_2d_to_pixels',(item,other)),
        (owner.directory,application.infrastructure._service_paths,'output_write_dir',('ai_detection',)),
        (owner.url,application.infrastructure._service_paths,'output_url',(item,)),
        (owner.draw,owner,'draw_ai_detection_boxes',(item,other,rule)),
        (owner.original,owner,'write_ai_original_output',(item,'fixture-request')),
        (server.ai_box_2d_to_pixels,owner,'ai_box_2d_to_pixels',(item,other)),
        (server.draw_ai_detection_boxes,owner,'draw_ai_detection_boxes',(item,other,rule)),
        (server.write_ai_original_output,owner,'write_ai_original_output',(item,'fixture-request')),
        (server.write_ai_annotated_output,owner,'write_ai_annotated_output',(item,'fixture-request',other,rule)),
    ):
        assert_native_relay(case,selected,(target,method,args,{},args,{}))
    sentinel=object()
    for selected,module in ((owner.normalize,inspection),(server.normalize_ai_box_2d,legacy_infrastructure)):
        with patch.object(module,'_normalize_ai_box_2d',return_value=sentinel) as callee:
            case.assertIs(selected(item),sentinel)
            callee.assert_called_once_with(item)
            case.assertIs(callee.call_args.args[0],item)
    with patch.object(application.artifacts.files,'runtime_provider',return_value=sentinel) as provider:
        case.assertIs(owner.runtime_provider(),sentinel)
        provider.assert_called_once_with()

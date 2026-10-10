"""Finite native detection labels/rules and actual application suppliers."""
from types import SimpleNamespace
from local_inspection_service.detection.results import DetectionLabels, DetectionResults
from local_inspection_service.detection.rules import CountRules


def detection_results_fixture(server):
    assert_default_detection(server)
    names=('CLASS_NAMES','CLASS_LABELS','GENERIC_DETECTION_CLASS_NAMES','GENERIC_DETECTION_LABELS','MANUAL_TYPE_LABELS',
           'polygon_overlap_ratio','polygon_area','polygon_bbox','bbox_gap','bbox_overlap_ratio',
           'filter_detections','dedupe_detections','postprocess_detections','draw_detections')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    results=DetectionResults(DetectionLabels(lambda:api.CLASS_NAMES,lambda:api.CLASS_LABELS,
        lambda:api.GENERIC_DETECTION_CLASS_NAMES,lambda:api.GENERIC_DETECTION_LABELS),
        lambda values,shape,spec:api.postprocess_detections(values,shape,spec))
    rules=CountRules(lambda:api.CLASS_LABELS,lambda:api.MANUAL_TYPE_LABELS)
    api._detection_results=results
    api._detection_rules=rules
    api.parse_detections=results.parse
    api.detection_names_for_business_class=results.names
    api.apply_rule=rules.apply
    return api


def assert_default_detection(server):
    import unittest
    from unittest.mock import patch
    from local_inspection_service.runtime.wiring import inspection
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.detection import geometry,postprocessing,drawing
    verify_actual_sources()
    case=unittest.TestCase()
    application=server._default_application
    graph=application.inspection
    results,rules=graph._detection_results,graph._detection_rules
    case.assertIs(type(results),DetectionResults)
    case.assertIs(type(rules),CountRules)
    case.assertIs(server._detection_results,results)
    case.assertIs(server._detection_rules,rules)
    for selected,owner,method in ((server.parse_detections,results,'parse'),(server.detection_names_for_business_class,results,'names'),(server.apply_rule,rules,'apply')):
        case.assertIs(selected.__self__,owner)
        case.assertIs(selected.__func__,getattr(type(owner),method))
    for selected,name in ((results.labels.class_names,'CLASS_NAMES'),(results.labels.class_labels,'CLASS_LABELS'),
        (results.labels.generic_names,'GENERIC_DETECTION_CLASS_NAMES'),(results.labels.generic_labels,'GENERIC_DETECTION_LABELS'),
        (rules.class_labels,'CLASS_LABELS'),(rules.manual_labels,'MANUAL_TYPE_LABELS')):
        original=getattr(application.values,name)
        case.assertIs(selected(),original)
        try:
            for replacement in ({7:'synthetic-A'},{8:'synthetic-B'}):
                object.__setattr__(application.values,name,replacement)
                case.assertIs(selected(),replacement)
        finally:object.__setattr__(application.values,name,original)
    for module,names in ((geometry,('polygon_overlap_ratio','polygon_area','polygon_bbox','bbox_gap','bbox_overlap_ratio')),
        (postprocessing,('filter_detections','dedupe_detections','postprocess_detections')),(drawing,('draw_detections',))):
        for name in names:case.assertIs(getattr(server,name),getattr(module,name))
    rows,shape_arg,spec_arg=object(),object(),object()
    sentinel=object()
    with patch.object(inspection,'postprocess_detections',return_value=sentinel) as callee:
        case.assertIs(results.postprocess(rows,shape_arg,spec_arg),sentinel)
        callee.assert_called_once_with(rows,shape_arg,spec_arg)
        for actual,expected in zip(callee.call_args.args,(rows,shape_arg,spec_arg)):case.assertIs(actual,expected)
    shape=(1000,1000)
    spec={'is_specialized':True,'confidence_threshold':.5}
    # A zero-area low-confidence row must be removed by the actual postprocessor.
    rejected={'class_id':0,'confidence':.1,'polygon':[[0,0],[1,0],[1,1]]}
    case.assertEqual(results.postprocess([rejected],shape,spec),postprocessing.postprocess_detections([dict(rejected)],shape,spec))
    case.assertEqual(results.postprocess([dict(rejected)],shape,spec),[])
    accepted={'class_id':0,'confidence':.9,'polygon':[[0,0],[100,0],[100,100],[0,100]]}
    projected=results.postprocess([accepted],shape,spec)
    case.assertEqual(projected,[accepted])
    case.assertIs(projected[0],accepted)

"""Native OCR contracts with finite policies and actual composition witnesses."""
from types import SimpleNamespace
from local_inspection_service.detection.ocr_matching import OCRMatching, MatchThresholds
from local_inspection_service.detection.ocr_scoring import OCRScoring
from local_inspection_service.detection.ocr_attachment import OCRAttachment, AttachmentDependencies
from local_inspection_service.detection.manual_text import ManualClassifier, ManualProjection
from local_inspection_service.detection.results import DetectionLabels
from local_inspection_service.runtime.paddle import DetectionOCREngine
from local_inspection_service.text_inspection.incoming_analysis import IncomingOCREngine


def detection_ocr_fixture(server):
    assert_default_ocr(server)
    names=('OCR_ACCESSORY_PROFILE_STOPWORDS','OCR_ACCESSORY_MATCH_MIN_TEXT_SCORE','OCR_ACCESSORY_MATCH_MIN_CONFIDENCE',
        'OCR_ACCESSORY_MATCH_MIN_MARGIN','MANUAL_TYPE_KEYWORDS','MANUAL_TYPE_LABELS','MANUAL_TYPE_CLASS_IDS',
        'CLASS_NAMES','CLASS_LABELS','GENERIC_DETECTION_CLASS_NAMES','GENERIC_DETECTION_LABELS',
        'accessory_uid','ocr_engine','prepare_paddle_runtime','normalize_ocr_text','crop_detection_region',
        'better_ocr_result','resize_for_ocr','rotate_quarter_turn')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    matching=OCRMatching(lambda:api.OCR_ACCESSORY_PROFILE_STOPWORDS,lambda item:api.accessory_uid(item),
        MatchThresholds(lambda:api.OCR_ACCESSORY_MATCH_MIN_TEXT_SCORE,lambda:api.OCR_ACCESSORY_MATCH_MIN_CONFIDENCE,lambda:api.OCR_ACCESSORY_MATCH_MIN_MARGIN))
    classifier=ManualClassifier(lambda:api.MANUAL_TYPE_KEYWORDS,lambda:api.MANUAL_TYPE_LABELS)
    scoring=OCRScoring(lambda:api.ocr_engine(),lambda texts:api.classify_manual_text(texts))
    projection=ManualProjection(lambda:api.MANUAL_TYPE_CLASS_IDS,DetectionLabels(lambda:api.CLASS_NAMES,lambda:api.CLASS_LABELS,lambda:api.GENERIC_DETECTION_CLASS_NAMES,lambda:api.GENERIC_DETECTION_LABELS))
    attachment=OCRAttachment(AttachmentDependencies(lambda:api.crop_detection_region,lambda:api.score_ocr_variants,lambda:api.match_ocr_text_accessory,lambda det,result,orientation,max_texts:api.finalize_ocr_detection(det,result,orientation,max_texts)))
    for name,owner,aliases in (
        ('_ocr_matching',matching,{'ocr_keyword_terms':'keywords','build_ocr_accessory_profiles':'profiles','match_ocr_text_accessory':'match'}),
        ('_manual_classifier',classifier,{'classify_manual_text':'classify'}),
        ('_ocr_scoring',scoring,{'build_ocr_result':'build','score_ocr_variant':'variant','score_ocr_variants':'variants','run_ocr_on_crop':'run_crop'}),
        ('_manual_projection',projection,{'finalize_ocr_detection':'finalize'}),
        ('_ocr_attachment',attachment,{'attach_ocr_results':'attach'}),
    ):
        setattr(api,name,owner)
        for public,method in aliases.items():setattr(api,public,getattr(owner,method))
    api._detection_ocr_engine=DetectionOCREngine(lambda:api.prepare_paddle_runtime())
    api._incoming_ocr_engine=IncomingOCREngine(lambda:api.prepare_paddle_runtime())
    return api


def assert_default_ocr(server):
    import unittest
    from unittest.mock import patch,create_autospec
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection,text
    from local_inspection_service.runtime import paddle
    from local_inspection_service.text_inspection import incoming_analysis
    from local_inspection_service.detection import ocr_images,ocr_matching,ocr_scoring
    verify_actual_sources()
    case=unittest.TestCase()
    application=server._default_application
    graph=application.inspection
    for name,kind in (('_ocr_matching',OCRMatching),('_manual_classifier',ManualClassifier),('_ocr_scoring',OCRScoring),('_manual_projection',ManualProjection),('_ocr_attachment',OCRAttachment),('_detection_ocr_engine',DetectionOCREngine)):
        case.assertIs(type(getattr(graph,name)),kind)
        case.assertIs(getattr(server,name),getattr(graph,name))
    case.assertIs(type(application.text._incoming_ocr_engine),IncomingOCREngine)
    case.assertIs(server._incoming_ocr_engine,application.text._incoming_ocr_engine)
    case.assertIs(graph._detection_ocr_engine.factory,paddle.create_detection_ocr)
    case.assertIs(application.text._incoming_ocr_engine.factory,incoming_analysis.create_paddle_ocr)
    assert_native_relay(case,server.ocr_engine,(graph._detection_ocr_engine,'get',(),{},(),{}))
    for module,names in ((ocr_images,('crop_detection_region','resize_for_ocr','rotate_quarter_turn')),
        (ocr_matching,('normalize_ocr_text',)),(ocr_scoring,('better_ocr_result',)),(paddle,('prepare_runtime',))):
        for name in names:case.assertIs(getattr(server,'prepare_paddle_runtime' if name=='prepare_runtime' else name),getattr(module,name))
    for module,selected in ((inspection,graph._detection_ocr_engine.prepare),(text,application.text._incoming_ocr_engine.prepare_runtime)):
        sentinel=object()
        with patch.object(module,'prepare_paddle_runtime',return_value=sentinel) as callee:
            # Bootstrap prepares runtime only; this witness never loads an OCR model.
            case.assertIs(selected(),sentinel)
            callee.assert_called_once_with()
    matching,classifier,scoring,projection,attachment=graph._ocr_matching,graph._manual_classifier,graph._ocr_scoring,graph._manual_projection,graph._ocr_attachment
    for selected,name in ((matching.stopwords,'OCR_ACCESSORY_PROFILE_STOPWORDS'),(matching.thresholds.text_score,'OCR_ACCESSORY_MATCH_MIN_TEXT_SCORE'),
        (matching.thresholds.confidence,'OCR_ACCESSORY_MATCH_MIN_CONFIDENCE'),(matching.thresholds.margin,'OCR_ACCESSORY_MATCH_MIN_MARGIN'),
        (classifier.keywords,'MANUAL_TYPE_KEYWORDS'),(classifier.labels,'MANUAL_TYPE_LABELS'),(projection.class_ids,'MANUAL_TYPE_CLASS_IDS'),
        (projection.labels.class_names,'CLASS_NAMES'),(projection.labels.class_labels,'CLASS_LABELS'),
        (projection.labels.generic_names,'GENERIC_DETECTION_CLASS_NAMES'),(projection.labels.generic_labels,'GENERIC_DETECTION_LABELS')):
        original=getattr(application.values,name)
        case.assertIs(selected(),original)
        replacement={'synthetic'} if isinstance(original,set) else {'synthetic':'fixture'} if isinstance(original,dict) else 101.25
        try:
            object.__setattr__(application.values,name,replacement)
            case.assertIs(selected(),replacement)
        finally:object.__setattr__(application.values,name,original)
    item,other,orientation=object(),object(),object()
    for selected,target,method,args in (
        (scoring.engine,graph._detection_ocr_engine,'get',()),
    ):
        assert_native_relay(case,selected,(target,method,args,{},args,{}))
    for selected,owner,method in ((attachment.dependencies.score(),scoring,'variants'),(attachment.dependencies.match(),matching,'match')):
        case.assertIs(selected.__self__,owner)
        case.assertIs(selected.__func__,getattr(type(owner),method))
    for selected,captured_name,owner,method,args in (
        (scoring.classify,'classify_manual_text',classifier,'classify',(item,)),
        (attachment.dependencies.finalize,'finalize_ocr_detection',projection,'finalize',(item,other,orientation,17)),
    ):
        cell=dict(zip(selected.__code__.co_freevars,selected.__closure__))[captured_name]
        original=cell.cell_contents
        case.assertIs(original.__self__,owner)
        case.assertIs(original.__func__,getattr(type(owner),method))
        sentinel=object()
        receiver=create_autospec(original,return_value=sentinel)
        try:
            cell.cell_contents=receiver
            case.assertIs(selected(*args),sentinel)
            receiver.assert_called_once_with(*args)
            for actual,expected in zip(receiver.call_args.args,args):
                if type(expected) is object:case.assertIs(actual,expected)
        finally:cell.cell_contents=original
    case.assertIs(attachment.dependencies.crop(),ocr_images.crop_detection_region)
    sentinel=object()
    with patch.object(inspection._accessory_policy,'accessory_uid',return_value=sentinel) as callee:
        case.assertIs(matching.uid(item),sentinel)
        callee.assert_called_once_with(item)
        case.assertIs(callee.call_args.args[0],item)
    for public,owner,method in (('ocr_keyword_terms',matching,'keywords'),('build_ocr_accessory_profiles',matching,'profiles'),
        ('match_ocr_text_accessory',matching,'match'),('classify_manual_text',classifier,'classify'),
        ('build_ocr_result',scoring,'build'),('score_ocr_variant',scoring,'variant'),('score_ocr_variants',scoring,'variants'),
        ('run_ocr_on_crop',scoring,'run_crop'),('finalize_ocr_detection',projection,'finalize'),('attach_ocr_results',attachment,'attach')):
        selected=getattr(server,public)
        case.assertIs(selected.__self__,owner)
        case.assertIs(selected.__func__,getattr(type(owner),method))

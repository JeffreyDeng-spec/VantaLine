"""Finite native model, DOC, OCR and geometry substitutes for original HTTP tests."""
from contextlib import ExitStack
from dataclasses import replace
from functools import wraps
from unittest.mock import patch


def set_text_external_enabled(api,enabled):
    object.__setattr__(api._default_application.values,'TEXT_INSPECTION_EXTERNAL_VLM_ENABLED',enabled)


def assert_default_text_endpoint_ports(api,kind):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.text_application_test_ports import assert_prepared_comparison_defaults,text_value
    from local_inspection_service.runtime.wiring import text as wiring
    case=unittest.TestCase();verify_actual_sources();app=api._default_application;graph=app.text;models=graph._text_comparisons.extraction_models;item,other=object(),object()
    if kind in ('document','extraction','bbox'):
        from scripts.training_resource_application_test_ports import read_cell
        endpoint=next(route.endpoint for route in api.app.routes if getattr(route,'path','')=='/api/text-inspection/extraction-capabilities')
        case.assertIs(read_cell(endpoint,'models').cell_contents,models)
        assert_prepared_comparison_defaults(case,api)
        for flag in (False,True,False):
            with text_value(app.values,'TEXT_INSPECTION_EXTERNAL_VLM_ENABLED',flag):
                case.assertIs(models.external_enabled(),flag);case.assertIs(graph._text_standards.documents.models.external_enabled(),flag)
        assert_native_relay(case,models.image_settings,(app.infrastructure._model_profile_configuration,'image_generation_settings',(),{},(),{}))
        assert_native_relay(case,models.image_provider,(app.inspection._provider_selection,'image_generation_provider_from_settings',(item,),{},(item,),{}))
        assert_native_relay(case,models.detection_settings,(app.infrastructure._model_profile_configuration,'ai_detection_settings',('label_bbox',),{},('label_bbox',),{}))
        assert_native_relay(case,models.detection_settings,(app.infrastructure._model_profile_configuration,'ai_detection_settings',('document',),{},('document',),{}))
        documents=graph._text_standards.documents
        assert_native_relay(case,documents.models.settings,(app.infrastructure._model_profile_configuration,'ai_detection_settings',('document',),{},('document',),{}))
        case.assertIs(graph._text_standards.imports.parsers.doc(),wiring.extract_doc_images)
    elif kind=='incoming':
        from scripts.incoming_analysis_application_test_ports import assert_default_incoming_analysis
        from local_inspection_service import text_compare_beta
        assert_default_incoming_analysis(case,api)
        case.assertIs(graph._incoming_execution.imaging.rectify(),text_compare_beta.rectify_label)
    else:raise ValueError(kind)


def with_text_endpoint_test_ports(api,kind):
    assert kind in ('document','extraction','bbox','incoming')
    def decorate(main):
        @wraps(main)
        def run(*args,**kwargs):
            assert_default_text_endpoint_ports(api,kind)
            from scripts.text_application_test_ports import text_value
            from scripts.training_resource_application_test_ports import replace_read_cell,read_cell
            graph=api._default_application.text
            with ExitStack() as stack:
                if kind in ('document','extraction','bbox'):
                    values=api._default_application.values
                    stack.enter_context(text_value(values,'TEXT_INSPECTION_EXTERNAL_VLM_ENABLED',values.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED))
                    models=graph._text_comparisons.extraction_models
                    fields={'image_settings':lambda:api.image_generation_settings(),'image_provider':lambda settings:api.image_generation_provider_from_settings(settings),'detection_settings':lambda purpose:api.ai_detection_settings(purpose)}
                    from scripts.training_records_application_test_ports import _frozen_slot
                    for field,value in fields.items():stack.enter_context(_frozen_slot(models,field,value))
                    if kind=='document':
                        docs=graph._text_standards.documents
                        stack.enter_context(patch.object(docs,'models',replace(docs.models,settings=lambda purpose:api.ai_detection_settings(purpose))))
                        imports=graph._text_standards.imports
                        stack.enter_context(patch.object(imports,'parsers',replace(imports.parsers,doc=lambda:api.extract_doc_images)))
                else:
                    observe=graph._beta_comparison.observer
                    stack.enter_context(replace_read_cell(observe,'incoming_text_ocr_observations',lambda image:api.incoming_text_ocr_observations(image)))
                    imaging=graph._incoming_execution.imaging
                    stack.enter_context(patch.object(graph._incoming_execution,'imaging',replace(imaging,rectify=lambda:api.rectify_label)))
                return main(*args,**kwargs)
        return run
    return decorate

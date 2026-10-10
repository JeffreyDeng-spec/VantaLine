"""Finite native OCR dependencies used by unchanged incoming analysis assertions."""
from contextlib import contextmanager
from scripts.training_resource_application_test_ports import read_cell,replace_read_cell


def assert_default_incoming_analysis(case,api):
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.text_inspection import incoming_analysis as analysis
    from local_inspection_service.text_inspection.beta_comparison import BetaComparison
    from local_inspection_service.runtime.wiring import text as wiring
    verify_actual_sources();app=api._default_application;graph=app.text;observe=graph._beta_comparison.observer();engine=graph._incoming_ocr_engine
    case.assertIs(type(engine),analysis.IncomingOCREngine);case.assertIs(type(graph._beta_comparison),BetaComparison)
    case.assertIs(api._incoming_ocr_engine,engine);case.assertIs(api._beta_comparison,graph._beta_comparison)
    case.assertIs(graph._beta_comparison.observer(),observe)
    case.assertIs(wiring._incoming_observations,analysis.observations);case.assertIs(wiring._ocr_result_mapping,analysis.result_mapping)
    native_engine=read_cell(observe,'incoming_text_ocr_engine').cell_contents
    case.assertIs(read_cell(native_engine,'_incoming_ocr_engine').cell_contents,engine)
    case.assertIs(read_cell(graph._incoming_execution.ocr.observe,'incoming_text_ocr_observations').cell_contents,observe)
    corroborate=read_cell(graph._incoming_execution.ocr.corroborate,'incoming_text_corroboration_observations').cell_contents
    case.assertIs(read_cell(corroborate,'incoming_text_ocr_observations').cell_contents,observe)
    shared_cell=read_cell(graph._beta_comparison.observer,'incoming_text_ocr_observations')
    case.assertIs(shared_cell.cell_contents,observe);case.assertIs(read_cell(graph._incoming_execution.ocr.observe,'incoming_text_ocr_observations'),shared_cell);case.assertIs(read_cell(corroborate,'incoming_text_ocr_observations'),shared_cell)
    from unittest.mock import patch
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime import paddle
    case.assertIs(engine.factory,analysis.create_paddle_ocr);case.assertIs(wiring.prepare_paddle_runtime,paddle.prepare_runtime);case.assertIs(wiring._incoming_corroboration,analysis.corroboration)
    item,other,sentinel=object(),object(),object()
    with patch.object(wiring,'prepare_paddle_runtime',return_value=sentinel) as receiver:
        case.assertIs(engine.prepare_runtime(),sentinel);receiver.assert_called_once_with()
    assert_native_relay(case,native_engine,(engine,'get',(),{},(),{}))
    for selected in (observe,graph._incoming_execution.ocr.observe):
        with patch.object(wiring,'_incoming_observations',return_value=sentinel) as receiver:
            case.assertIs(selected(item),sentinel);receiver.assert_called_once()
            case.assertEqual(receiver.call_args.args,(item,));case.assertIs(receiver.call_args.args[0],item)
            case.assertEqual(set(receiver.call_args.kwargs),{'engine','mapping_provider'})
            assert_native_relay(case,receiver.call_args.kwargs['engine'],(engine,'get',(),{},(),{}))
            case.assertIs(receiver.call_args.kwargs['mapping_provider'](),analysis.result_mapping)
    for selected in (corroborate,graph._incoming_execution.ocr.corroborate):
        with patch.object(wiring,'_incoming_corroboration',return_value=sentinel) as receiver:
            case.assertIs(selected(item,other),sentinel);receiver.assert_called_once()
            case.assertEqual(receiver.call_args.args,(item,other));case.assertIs(receiver.call_args.args[0],item);case.assertIs(receiver.call_args.args[1],other);case.assertEqual(set(receiver.call_args.kwargs),{'observe'})
            with patch.object(wiring,'_incoming_observations',return_value=sentinel) as actual:
                case.assertIs(receiver.call_args.kwargs['observe'](item),sentinel);actual.assert_called_once();case.assertIs(actual.call_args.args[0],item)


@contextmanager
def incoming_observer_fixture(api):
    """The two native consumers share one captured observation capability."""
    graph=api._default_application.text;cell=read_cell(graph._beta_comparison.observer,'incoming_text_ocr_observations')
    corroborate=read_cell(graph._incoming_execution.ocr.corroborate,'incoming_text_corroboration_observations').cell_contents
    assert cell is read_cell(corroborate,'incoming_text_ocr_observations')
    assert cell is read_cell(graph._incoming_execution.ocr.observe,'incoming_text_ocr_observations')
    with replace_read_cell(graph._beta_comparison.observer,'incoming_text_ocr_observations',api.incoming_text_ocr_observations):
        yield

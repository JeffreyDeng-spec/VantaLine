"""Finite external model registry/factory seams; native selection/cache edges remain owned."""
from dataclasses import replace
from unittest.mock import patch,Mock


def bind_local_model(api,stack):
    graph=api._default_application.training_pipeline;catalog=graph._model_catalog;selection=catalog.selection
    for field,name in (('specialized','list_ai_detection_specialized_model_specs'),('removed','removed_phase1_feature')):
        stack.enter_context(patch.object(selection,field,lambda *args,_name=name:getattr(api,_name)(*args)))
    stack.enter_context(patch.object(selection,'registry',lambda:api.MODEL_REGISTRY));stack.enter_context(patch.object(selection,'default_id',lambda:api.DEFAULT_MODEL_ID))
    stack.enter_context(patch.object(catalog,'registry',replace(catalog.registry,registry=lambda:api.MODEL_REGISTRY)))
    stack.enter_context(patch.object(catalog.local,'factory',lambda:api.YOLO))


def assert_default_local_model(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.training.catalog_composition import ModelCatalog
    from local_inspection_service.detection.local_models import LocalModels
    from local_inspection_service.detection.model_selection import ModelSelection
    from local_inspection_service.runtime.wiring import training_pipeline
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;catalog=graph._model_catalog;selection=catalog.selection;local=catalog.local;item,other=object(),object()
    case.assertIs(type(catalog),ModelCatalog);case.assertIs(type(selection),ModelSelection);case.assertIs(type(local),LocalModels)
    case.assertIs(api._model_catalog,catalog);case.assertIs(api._model_selection,selection);case.assertIs(api._local_models,local);case.assertIs(api._models,local.models);case.assertIs(api._model_paths,local.paths);case.assertIs(local.files,app.artifacts.files)
    for selected,name in ((selection.registry,'MODEL_REGISTRY'),(selection.default_id,'DEFAULT_MODEL_ID'),(catalog.registry.registry,'MODEL_REGISTRY')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)
    case.assertIs(local.factory(),training_pipeline.YOLO)
    for selected,target,method,args,kw,expected in ((local.select,selection,'selected_model_spec',(item,other),{},(item,other)),(selection.trained,catalog.catalog,'list_trained_model_specs',(item,),{},(item,)),(local.trained_specs,catalog.catalog,'list_trained_model_specs',(),{},()),(local.legacy_specs,catalog,'legacy_model_specs',(),{},())):
        assert_native_relay(case,selected,(target,method,args,kw,expected,{}))
    assert_native_relay(case,selection.specialized,(app.inspection._detection_task_catalog,'list_ai_detection_specialized_model_specs',(item,),{},(item,None,None),{}))
    with patch.object(training_pipeline,'removed_phase1_feature',return_value=other) as receiver:case.assertIs(selection.removed(item),other);receiver.assert_called_once_with(item)

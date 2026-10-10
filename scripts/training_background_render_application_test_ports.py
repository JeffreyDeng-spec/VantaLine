"""Finite background library and renderer fixture capabilities."""
from dataclasses import replace
from unittest.mock import patch

PATHS={'directory':'BACKGROUND_DIR','default_image':'DEFAULT_BACKGROUND_IMAGE','suffixes':'IMAGE_REFERENCE_SUFFIXES'}
LOOKUP={'manifest':'load_training_background_manifest','selected':'selected_background_set_id','files':'background_set_image_files'}
RENDER={'library':'training_background_library','candidates':'background_candidates_for_split','synthetic':'synthetic_training_background','fit':'fit_training_background_to_canvas','augment':'augment_training_background'}


def bind_training_background_render(api,stack):
    graph=api._default_application.training_pipeline;library=graph._training_background_library;renderer=graph._training_background_renderer
    stack.enter_context(patch.object(graph._background_selection,'selected',lambda selected:api.selected_background_set_id(selected)))
    stack.enter_context(patch.object(graph._background_selection,'images',lambda:api.image_file_list));stack.enter_context(patch.object(graph._background_selection,'sets',lambda:api.BACKGROUND_SETS_DIR))
    stack.enter_context(patch.object(graph._background_image_files,'suffixes',lambda:api.IMAGE_REFERENCE_SUFFIXES))
    stack.enter_context(patch.object(library,'paths',replace(library.paths,**{field:(lambda _name=name:getattr(api,_name)) for field,name in PATHS.items()})))
    stack.enter_context(patch.object(library,'lookup',replace(library.lookup,**{field:(lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)) for field,name in LOOKUP.items()})))
    for field,name in RENDER.items():stack.enter_context(patch.object(renderer,field,lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)))


def assert_default_training_background_render(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.training.background_library import TrainingBackgroundLibrary
    from local_inspection_service.training.background_rendering import TrainingBackgroundRenderer
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;library=graph._training_background_library;renderer=graph._training_background_renderer;item,other=object(),object()
    case.assertIs(type(library),TrainingBackgroundLibrary);case.assertIs(type(renderer),TrainingBackgroundRenderer);case.assertIs(api._training_background_library,library);case.assertIs(api._training_background_renderer,renderer);case.assertIs(library.files,app.artifacts.files);case.assertIs(renderer.images,app.infrastructure._background_image_io);case.assertIs(renderer.images.files,app.artifacts.files);case.assertIs(renderer.images.files.runtime_provider,app.artifacts.files.runtime_provider)
    for field,name in PATHS.items():
        selected=getattr(library.paths,field);original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)
    for selected,target,method,args,expected in ((library.lookup.manifest,library,'load_training_background_manifest',(),()),(library.lookup.selected,graph._background_selection,'selected_background_set_id',(item,),(item,None,None)),(library.lookup.files,graph._background_selection,'background_set_image_files',(item,),(item,)),(renderer.library,library,'training_background_library',(item,),(item,))):assert_native_relay(case,selected,(target,method,args,{},expected,{}))
    for selected,name,args in ((renderer.candidates,'background_candidates_for_split',(item,other)),(renderer.synthetic,'synthetic_training_background',(item,)),(renderer.fit,'fit_training_background_to_canvas',(item,other)),(renderer.augment,'augment_training_background',(item,other))):
        with patch.object(wiring,name,return_value=other) as receiver:case.assertIs(selected(*args),other);receiver.assert_called_once_with(*args)

    case.assertIs(graph._background_image_files.files,app.artifacts.files)
    assert_native_relay(case,graph._background_selection.selected,(graph._background_selection,'selected_background_set_id',(item,),{},(item,None,None),{}))
    assert_native_relay(case,graph._background_selection.images(),(graph._background_image_files,'image_file_list',(item,),{},(item,),{}))
    for selected,name in ((graph._background_selection.sets,'BACKGROUND_SETS_DIR'),(graph._background_image_files.suffixes,'IMAGE_REFERENCE_SUFFIXES')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)

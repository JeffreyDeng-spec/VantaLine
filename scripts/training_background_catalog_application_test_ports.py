"""Finite background catalog, selection and seeding fixtures."""
from dataclasses import replace
from unittest.mock import patch,Mock

CATALOG=(('records',{'load':'load_background_sets_manifest','directories':'background_set_dirs'}),('access',{'audit':'record_audit_fields','visible':'record_visible_to_user'}))


def bind_training_background_catalog(api,stack):
    graph=api._default_application.training_pipeline;manifest=graph._background_manifest;seed=graph._background_seeding;catalog=graph._background_catalog;selection=graph._background_selection
    for owner,field,name in ((manifest,'directory','BACKGROUND_DIR'),(manifest,'path','BACKGROUND_SETS_MANIFEST'),(graph._background_image_files,'suffixes','IMAGE_REFERENCE_SUFFIXES'),(selection,'sets','BACKGROUND_SETS_DIR'),(selection,'safe','safe_background_set_id'),(selection,'images','image_file_list')):stack.enter_context(patch.object(owner,field,lambda _name=name:getattr(api,_name)))
    stack.enter_context(patch.object(seed,'paths',replace(seed.paths,default=lambda:api.DEFAULT_BACKGROUND_IMAGE,sets=lambda:api.BACKGROUND_SETS_DIR)))
    for field,name in (('load','load_background_sets_manifest'),('write','write_background_sets_manifest'),('minimum','ensure_background_set_minimum_images'),('seed','seed_default_background_set')):stack.enter_context(patch.object(seed,field,lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)))
    stack.enter_context(patch.object(catalog,'paths',replace(catalog.paths,sets=lambda:api.BACKGROUND_SETS_DIR,output=lambda:api.OUTPUT_DIR)))
    for attribute,mapping in CATALOG:stack.enter_context(patch.object(catalog,attribute,replace(getattr(catalog,attribute),**{field:(lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)) for field,name in mapping.items()})))
    stack.enter_context(patch.object(catalog,'access',replace(catalog.access,system_owner=lambda:api.SYSTEM_OWNER_ID)));stack.enter_context(patch.object(catalog,'records',replace(catalog.records,payload=lambda:api.background_set_payload)))
    for owner,field,name in ((catalog,'safe','safe_background_set_id'),(catalog,'images','image_file_list'),(catalog,'url','public_output_url'),(selection,'list','list_background_sets'),(selection,'load','load_background_sets_manifest'),(selection,'selected','selected_background_set_id')):stack.enter_context(patch.object(owner,field,lambda *args,_name=name,**kw:getattr(api,_name)(*args,**kw)))


def assert_default_training_background_catalog(api):
    import unittest
    from scripts.auto_optimization_test_ports import assert_native_relay
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.training_records_application_test_ports import _frozen_slot
    from local_inspection_service.training.background_manifest import BackgroundManifest
    from local_inspection_service.training.background_seeding import BackgroundSeeding
    from local_inspection_service.training.background_catalog import BackgroundCatalog,BackgroundImageFiles
    from local_inspection_service.training.background_selection import BackgroundSelection
    from local_inspection_service.runtime.wiring import training_pipeline as wiring
    verify_actual_sources();case=unittest.TestCase();app=api._default_application;graph=app.training_pipeline;infra=app.infrastructure;manifest=graph._background_manifest;seed=graph._background_seeding;catalog=graph._background_catalog;selection=graph._background_selection;item,other,third=object(),object(),object()
    for name,kind in (('_background_manifest',BackgroundManifest),('_background_seeding',BackgroundSeeding),('_background_catalog',BackgroundCatalog),('_background_image_files',BackgroundImageFiles),('_background_selection',BackgroundSelection)):case.assertIs(type(getattr(graph,name)),kind);case.assertIs(getattr(api,name),getattr(graph,name))
    for owner in (manifest,seed,graph._background_image_files):case.assertIs(owner.files,app.artifacts.files)
    for selected,name in ((manifest.directory,'BACKGROUND_DIR'),(manifest.path,'BACKGROUND_SETS_MANIFEST'),(seed.paths.default,'DEFAULT_BACKGROUND_IMAGE'),(seed.paths.sets,'BACKGROUND_SETS_DIR'),(catalog.paths.sets,'BACKGROUND_SETS_DIR'),(catalog.paths.output,'OUTPUT_DIR'),(catalog.access.system_owner,'SYSTEM_OWNER_ID'),(graph._background_image_files.suffixes,'IMAGE_REFERENCE_SUFFIXES'),(selection.sets,'BACKGROUND_SETS_DIR')):
        original=getattr(app.values,name);case.assertIs(selected(),original)
        try:object.__setattr__(app.values,name,other);case.assertIs(selected(),other)
        finally:object.__setattr__(app.values,name,original)
    for selected,name,args in ((catalog.access.audit,'record_audit_fields',(item,other)),(catalog.access.visible,'record_visible_to_user',(item,other,third))):
        receiver=Mock(return_value=other)
        with _frozen_slot(infra,name,receiver):case.assertIs(selected(*args),other);receiver.assert_called_once_with(*args)
    for selected,target,method,args,expected in ((seed.load,manifest,'load_background_sets_manifest',(),()),(seed.write,manifest,'write_background_sets_manifest',(item,),(item,)),(seed.minimum,graph._background_minimum_images,'ensure_background_set_minimum_images',(item,),(item,6)),(seed.seed,seed,'seed_default_background_set',(),()),(catalog.records.load,manifest,'load_background_sets_manifest',(),()),(catalog.records.directories,seed,'background_set_dirs',(),()),(catalog.records.payload(),catalog,'background_set_payload',(item,other),(item,other)),(catalog.images,graph._background_image_files,'image_file_list',(item,),(item,)),(catalog.url,infra._service_paths,'public_output_url',(item,),(item,)),(selection.list,catalog,'list_background_sets',(item,other),(item,other)),(selection.load,manifest,'load_background_sets_manifest',(),()),(selection.selected,selection,'selected_background_set_id',(item,),(item,None,None)),(selection.images(),graph._background_image_files,'image_file_list',(item,),(item,))):assert_native_relay(case,selected,(target,method,args,{},expected,{}))
    case.assertIs(selection.safe(),wiring.safe_background_set_id)
    with patch.object(wiring,'safe_background_set_id',return_value=other) as receiver:case.assertIs(catalog.safe(item),other);receiver.assert_called_once_with(item)
    with patch.object(wiring.time,'time',return_value=other) as receiver:case.assertIs(seed.clock(),other);receiver.assert_called_once_with()

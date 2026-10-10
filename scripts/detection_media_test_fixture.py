"""Finite native media graph for retained callback-window contracts."""
from types import SimpleNamespace
from local_inspection_service.detection.media_ports import InspectionImagePolicy, ReferenceCollectionPolicy, ReferenceSheetPolicy, ReferenceSheetCache, ReferenceSheetImages
from local_inspection_service.detection.image_encoding import ImageEncoding
from local_inspection_service.detection.inspection_image_store import InspectionImageStore
from local_inspection_service.detection.reference_images import ReferenceCollection, ReferenceTileRenderer
from local_inspection_service.detection.reference_sheet import ReferenceSheet
from local_inspection_service.storage.artifacts.files import BusinessFiles


def detection_media_fixture(server):
    assert_default_media(server)
    names=('cv2','np','bounded_text','accessory_uid','accessory_image_paths','data_url_payload',
           'output_write_dir','safe_name','time','AiProviderError','AI_MCP_INSPECTION_IMAGE_DIR',
           'AI_INSPECTION_IMAGE_MAX_SIDE','AI_INSPECTION_IMAGE_QUALITY','AI_REFERENCE_IMAGES_PER_ACCESSORY',
           'AI_REFERENCE_IMAGE_MAX_SIDE','AI_REFERENCE_IMAGE_QUALITY','IMAGE_REFERENCE_SUFFIXES',
           'AI_PROFILE_REFERENCE_MODE','AI_PROFILE_REFERENCE_SHEET_QUALITY','AI_PROFILE_REFERENCE_SHEET_MAX_SIDE',
           '_REFERENCE_SHEET_DESCRIPTOR_CACHE','_REFERENCE_SHEET_DESCRIPTOR_CACHE_LOCK')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    encoding=ImageEncoding(lambda:api.cv2,lambda message:api.AiProviderError(message),lambda image,**kwargs:api.image_bgr_data_url(image,**kwargs),runtime_provider=lambda:None)
    store=InspectionImageStore(lambda:api.cv2,InspectionImagePolicy(lambda:api.AI_MCP_INSPECTION_IMAGE_DIR,lambda:api.AI_INSPECTION_IMAGE_MAX_SIDE,lambda:api.AI_INSPECTION_IMAGE_QUALITY),lambda:api.time.time_ns(),lambda name:api.safe_name(name),runtime_provider=lambda:None)
    collection=ReferenceCollection(lambda:api.bounded_text,lambda item:api.accessory_uid(item),lambda item:api.accessory_image_paths(item),lambda path,**kwargs:api.image_path_data_url(path,**kwargs),lambda value:api.data_url_payload(value),ReferenceCollectionPolicy(lambda:api.AI_REFERENCE_IMAGES_PER_ACCESSORY,lambda:api.AI_REFERENCE_IMAGE_MAX_SIDE,lambda:api.AI_REFERENCE_IMAGE_QUALITY))
    tiles=ReferenceTileRenderer(lambda:api.cv2,lambda:api.np)
    sheet=ReferenceSheet(lambda:api.bounded_text,lambda name:api.output_write_dir(name),ReferenceSheetPolicy(lambda:api.IMAGE_REFERENCE_SUFFIXES,lambda:api.AI_PROFILE_REFERENCE_MODE,lambda:api.AI_PROFILE_REFERENCE_SHEET_QUALITY,lambda:api.AI_PROFILE_REFERENCE_SHEET_MAX_SIDE),ReferenceSheetCache(lambda:api._REFERENCE_SHEET_DESCRIPTOR_CACHE_LOCK,lambda:api._REFERENCE_SHEET_DESCRIPTOR_CACHE),ReferenceSheetImages(lambda:api.cv2,lambda:api.np,lambda *args:api.fit_image_into_cell(*args),lambda:api.image_path_data_url),files=lambda:BusinessFiles(lambda:None))
    for name,owner,methods in (
        ('_image_encoding',encoding,('image_bgr_data_url','image_path_data_url')),
        ('_inspection_image_store',store,('write_mcp_inspection_image',)),
        ('_reference_collection',collection,('tool_accessory_reference_collect',)),
        ('_reference_tile_renderer',tiles,('fit_image_into_cell',)),
        ('_reference_sheet',sheet,('build_reference_sheet_descriptor',))):
        setattr(api,name,owner)
        for method in methods:setattr(api,method,getattr(owner,method))
    api.AI_MCP_TOOL_HANDLERS=dict(server.AI_MCP_TOOL_HANDLERS,**{'accessory.reference.collect':api.tool_accessory_reference_collect})
    return api


def assert_default_media(server):
    import unittest
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from unittest.mock import patch
    from pathlib import Path
    from local_inspection_service.runtime.wiring import inspection
    verify_actual_sources()
    case=unittest.TestCase()
    application=server._default_application
    graph=application.inspection
    encoding,store,collection,tiles,sheet=(getattr(graph,name) for name in ('_image_encoding','_inspection_image_store','_reference_collection','_reference_tile_renderer','_reference_sheet'))
    for name,owner,kind in (('_image_encoding',encoding,ImageEncoding),('_inspection_image_store',store,InspectionImageStore),('_reference_collection',collection,ReferenceCollection),('_reference_tile_renderer',tiles,ReferenceTileRenderer),('_reference_sheet',sheet,ReferenceSheet)):
        case.assertIs(type(owner),kind)
        case.assertIs(getattr(server,name),owner)
    case.assertIs(encoding.images(),inspection.cv2)
    case.assertIs(store.images(),inspection.cv2)
    case.assertIs(tiles.images(),inspection.cv2)
    case.assertIs(tiles.arrays(),inspection.np)
    case.assertIs(sheet.media.images(),inspection.cv2)
    case.assertIs(sheet.media.arrays(),inspection.np)
    case.assertIs(sheet.files(),application.artifacts.files)
    case.assertIs(sheet.text(),inspection.bounded_text)
    case.assertIs(collection.text(),inspection.bounded_text)
    case.assertIs(sheet.cache.records(),graph._REFERENCE_SHEET_DESCRIPTOR_CACHE)
    case.assertIs(sheet.cache.lock(),graph._REFERENCE_SHEET_DESCRIPTOR_CACHE_LOCK)
    for policy,kind,bindings in ((store.policy,InspectionImagePolicy,{'directory':'AI_MCP_INSPECTION_IMAGE_DIR','max_side':'AI_INSPECTION_IMAGE_MAX_SIDE','quality':'AI_INSPECTION_IMAGE_QUALITY'}),(collection.policy,ReferenceCollectionPolicy,{'limit':'AI_REFERENCE_IMAGES_PER_ACCESSORY','max_side':'AI_REFERENCE_IMAGE_MAX_SIDE','quality':'AI_REFERENCE_IMAGE_QUALITY'}),(sheet.policy,ReferenceSheetPolicy,{'suffixes':'IMAGE_REFERENCE_SUFFIXES','mode':'AI_PROFILE_REFERENCE_MODE','quality':'AI_PROFILE_REFERENCE_SHEET_QUALITY','max_side':'AI_PROFILE_REFERENCE_SHEET_MAX_SIDE'})):
        case.assertIs(type(policy),kind)
        for field,name in bindings.items():
            original=getattr(application.values,name)
            case.assertIs(getattr(policy,field)(),original)
            replacement=original+101 if type(original) is int else {'fixture-extension'} if type(original) is set else Path('synthetic-media-root') if isinstance(original,Path) else 'fixture-mode'
            try:
                object.__setattr__(application.values,name,replacement)
                case.assertIs(getattr(policy,field)(),replacement)
            finally:
                object.__setattr__(application.values,name,original)
    item=object()
    for selected,owner,method,args,kwargs,forwarded,forward_keywords in (
        (server.tool_accessory_reference_collect,collection,'tool_accessory_reference_collect',(item,),{},(item,),{}),
        (server.AI_MCP_TOOL_HANDLERS['accessory.reference.collect'],collection,'tool_accessory_reference_collect',(item,),{},(item,),{}),
        (encoding.encode,encoding,'image_bgr_data_url',(item,),{},(item,),{'max_side':1280,'quality':82}),
        (sheet.media.fit,tiles,'fit_image_into_cell',(item,12,8),{},(item,12,8),{}),
        (sheet.media.encode(),encoding,'image_path_data_url',(item,),{},(item,),{'max_side':1024,'quality':78}),
        (collection.encode,encoding,'image_path_data_url',(item,),{},(item,),{'max_side':1024,'quality':78}),
        (collection.paths,graph._reference_evidence,'accessory_image_paths',(item,),{},(item,),{}),
        (collection.mime,graph._provider_payloads,'data_url_payload',(item,),{},(item,),{}),
        (sheet.output,application.infrastructure._service_paths,'output_write_dir',('reference',),{},('reference',),{}),
    ):
        assert_native_relay(case,selected,(owner,method,args,kwargs,forwarded,forward_keywords))
        if method in ('image_bgr_data_url','image_path_data_url'):
            parameters={'max_side':17,'quality':73}
            assert_native_relay(case,selected,(owner,method,args,parameters,forwarded,parameters))
    for selected,owner,attribute,args in ((collection.uid,inspection._accessory_policy,'accessory_uid',(item,)),(store.name,inspection,'safe_name',('name',)),(store.now_ns,inspection.time,'time_ns',()),(encoding.error,inspection,'AiProviderError',('message',))):
        sentinel=object()
        with patch.object(owner,attribute,return_value=sentinel) as callee:
            case.assertIs(selected(*args),sentinel)
            callee.assert_called_once_with(*args)
            if args and type(args[0]) is object:case.assertIs(callee.call_args.args[0],args[0])
    sentinel=object()
    with patch.object(application.artifacts.files,'runtime_provider',return_value=sentinel) as provider:
        case.assertIs(encoding.runtime_provider(),sentinel)
        case.assertIs(store.runtime_provider(),sentinel)
        case.assertEqual(provider.call_count,2)
    case.assertEqual(set(server.AI_MCP_TOOL_HANDLERS),{'accessory.profile.generate','accessory.reference.collect','vision.inspect.presence','provider.gemini.generate_json'})

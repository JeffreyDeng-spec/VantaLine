"""Native task catalog contracts with explicit request identity and live policies."""
from types import SimpleNamespace
from local_inspection_service.detection.task_catalog import TaskCatalog,TaskCatalogSources,TaskCatalogAccess,TaskModelRegistry
from local_inspection_service.detection.task_projection import TaskProjection


def detection_task_catalog_fixture(server):
    assert_default_catalog(server)
    from local_inspection_service.detection import task_identity
    names=('load_config','load_ai_detection_tasks','list_trained_model_specs','ai_detection_task_background_record',
        'public_path_sanitized','record_audit_fields','accessory_lookup_by_id','record_visible_to_user','record_owner_username',
        'accessory_uid','serialize_accessory','MODEL_REGISTRY','AI_DETECTION_MODEL_ID','AI_DETECTION_LABEL',
        'AI_DETECTION_TASK_PREFIX','LEGACY_OWNER_ID','AI_DETECTION_TASKS_PATH','_request_user','AiDetectionTaskRequest','HTTPException')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    api.ai_detection_task_model_id=lambda task_id:task_identity.ai_detection_task_model_id(task_id,api.AI_DETECTION_TASK_PREFIX)
    projection=TaskProjection(lambda config:api.accessory_lookup_by_id(config),lambda record:api.record_audit_fields(record),
        lambda task_id:api.ai_detection_task_background_record(task_id),lambda value:api.public_path_sanitized(value),lambda task_id:api.ai_detection_task_model_id(task_id))
    catalog=TaskCatalog(TaskCatalogSources(lambda:api.load_config(),lambda:api.load_ai_detection_tasks(),lambda *args:api.list_trained_model_specs(*args),
        lambda item:api.accessory_uid(item),lambda item:api.serialize_accessory(item)),
        TaskCatalogAccess(lambda:api._request_user.get(),lambda record,user,target:api.record_visible_to_user(record,user,target),lambda record:api.record_owner_username(record)),
        TaskModelRegistry(lambda:api.MODEL_REGISTRY[api.AI_DETECTION_MODEL_ID],lambda:api.AI_DETECTION_LABEL,
            lambda:api.AI_DETECTION_TASKS_PATH,lambda:api.LEGACY_OWNER_ID,lambda task_id:api.ai_detection_task_model_id(task_id)),
        lambda task,config:api.serialize_ai_detection_task(task,config))
    api._detection_task_catalog=catalog
    for owner,names in ((projection,('serialize_ai_detection_task','ai_detection_task_payload_from_request')),
        (catalog,('list_ai_detection_task_model_specs','list_ai_detection_specialized_model_specs','ai_detection_tasks_response'))):
        for name in names:setattr(api,name,getattr(owner,name))
    return api


def assert_default_catalog(server):
    import unittest
    from unittest.mock import patch,Mock
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    verify_actual_sources()
    case=unittest.TestCase()
    application=server._default_application
    graph,infra=application.inspection,application.infrastructure
    catalog,projection=graph._detection_task_catalog,graph._detection_task_projection
    case.assertIs(type(catalog),TaskCatalog)
    case.assertIs(type(projection),TaskProjection)
    case.assertIs(server._detection_task_catalog,catalog)
    case.assertIs(server._detection_task_projection,projection)
    item,config,user=object(),object(),object()
    for selected,owner,method,args in (
        (catalog.sources.config,infra._app_configuration,'load_config',()),
        (catalog.sources.tasks,graph._detection_task_store,'load_ai_detection_tasks',()),
        (catalog.sources.trained,application.training_pipeline._trained_model_catalog,'list_trained_model_specs',(config,)),
        (catalog.sources.serialize_accessory,graph._accessory_projection,'serialize_accessory',(item,)),
        (projection.lookup,graph._accessory_lookup,'accessory_lookup_by_id',(config,)),
        (projection.public_path,infra._service_paths,'public_path_sanitized',(item,)),
        (catalog.project,projection,'serialize_ai_detection_task',(item,config)),
        (server.serialize_ai_detection_task,projection,'serialize_ai_detection_task',(item,config)),
        (server.ai_detection_task_payload_from_request,projection,'ai_detection_task_payload_from_request',(item,config)),
        (server.list_ai_detection_task_model_specs,catalog,'list_ai_detection_task_model_specs',(config,'owner-fixture')),
    ):
        assert_native_relay(case,selected,(owner,method,args,{},args,{}))
    for selected,attribute,owner,method,args in (
        (projection.audit,'record_audit_fields',infra._record_audit,'record_audit_fields',(item,)),
        (catalog.access.visible,'record_visible_to_user',infra._record_ownership,'record_visible_to_user',(item,user,'owner-fixture')),
        (catalog.access.owner_username,'record_owner_username',infra._record_ownership,'record_owner_username',(item,)),
    ):
        original=getattr(infra,attribute)
        case.assertIs(original.__self__,owner)
        case.assertIs(original.__func__,getattr(type(owner),method))
        sentinel=object();callee=Mock(return_value=sentinel)
        try:
            object.__setattr__(infra,attribute,callee)
            case.assertIs(selected(*args),sentinel)
            callee.assert_called_once_with(*args)
            for actual,expected in zip(callee.call_args.args,args):
                if type(expected) is object:case.assertIs(actual,expected)
        finally:object.__setattr__(infra,attribute,original)
    background=object()
    with patch.object(inspection,'_detection_task_background_record',return_value=background) as callee:
        case.assertIs(projection.background('synthetic-task'),background)
        callee.assert_called_once()
        case.assertEqual(callee.call_args.args,('synthetic-task',))
        abilities=callee.call_args.kwargs
        case.assertEqual(set(abilities),{'find_task','normalize_background'})
        assert_native_relay(case,abilities['find_task'],(graph._detection_task_store,'find_ai_detection_task',('synthetic-task',),{},('synthetic-task',),{}))
        case.assertIs(abilities['normalize_background'](),inspection.safe_background_set_id)
    identity=infra._request_user
    case.assertIs(server._request_user,identity)
    token=identity.set({'id':'synthetic-catalog-identity'})
    try:case.assertIs(catalog.access.user(),identity.get())
    finally:identity.reset(token)
    for selected,name in ((catalog.registry.label,'AI_DETECTION_LABEL'),(catalog.registry.tasks_path,'AI_DETECTION_TASKS_PATH'),(catalog.registry.legacy_owner,'LEGACY_OWNER_ID')):
        original=getattr(application.values,name)
        case.assertIs(selected(),original)
        sentinel=object()
        try:
            object.__setattr__(application.values,name,sentinel)
            case.assertIs(selected(),sentinel)
        finally:object.__setattr__(application.values,name,original)
    registry,selected_id=application.values.MODEL_REGISTRY,application.values.AI_DETECTION_MODEL_ID
    case.assertIs(catalog.registry.base_spec(),registry[selected_id])
    first,second={'fixture':'first'},{'fixture':'second'}
    try:
        object.__setattr__(application.values,'MODEL_REGISTRY',{'synthetic-first':first,'synthetic-second':second})
        for key,value in (('synthetic-first',first),('synthetic-second',second)):
            object.__setattr__(application.values,'AI_DETECTION_MODEL_ID',key)
            case.assertIs(catalog.registry.base_spec(),value)
    finally:
        object.__setattr__(application.values,'MODEL_REGISTRY',registry)
        object.__setattr__(application.values,'AI_DETECTION_MODEL_ID',selected_id)
    prefix=application.values.AI_DETECTION_TASK_PREFIX
    try:
        for current in (prefix,'synthetic-model-prefix:'):
            object.__setattr__(application.values,'AI_DETECTION_TASK_PREFIX',current)
            for selected in (projection.model_id,catalog.registry.model_id):
                with patch.object(inspection,'_detection_task_model_id',return_value=config) as callee:
                    case.assertIs(selected('synthetic-task'),config)
                    callee.assert_called_once_with('synthetic-task',current)
    finally:object.__setattr__(application.values,'AI_DETECTION_TASK_PREFIX',prefix)
    for selected,method,args,keywords in (
        (server.ai_detection_tasks_response,'ai_detection_tasks_response',(config,'synthetic-selected'),{'user':user,'target_user_id':'synthetic-owner'}),
        (server.list_ai_detection_specialized_model_specs,'list_ai_detection_specialized_model_specs',(config,item,'synthetic-owner'),{}),
    ):
        assert_native_relay(case,selected,(catalog,method,args,keywords,args,keywords))
    with patch.object(inspection._accessory_policy,'accessory_uid',return_value=config) as callee:
        case.assertIs(catalog.sources.accessory_uid(item),config)
        callee.assert_called_once_with(item)

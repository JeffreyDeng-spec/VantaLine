"""Native task storage contracts with explicit live paths, rows and repositories."""
from types import SimpleNamespace
from local_inspection_service.detection.task_store import DetectionTaskStore, TaskStorePaths, TaskReadCache, TaskRows


def detection_task_store_fixture(server):
    assert_default_task_store(server)
    from local_inspection_service.detection import task_backgrounds,task_identity
    names=('DATA_DIR','AI_DETECTION_TASKS_PATH','runtime_postgres_repository_or_none','ensure_dirs',
        'store_read_cache_get','store_read_cache_put','store_read_cache_invalidate','safe_background_set_id',
        'row_raw_json_list','ai_detection_task_row','sanitize_ai_detection_task_id','clean_ai_detection_task_name',
        'normalize_ai_detection_task_counts','AI_DETECTION_TASK_PREFIX')
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    api.ai_detection_task_model_id=lambda task_id:task_identity.ai_detection_task_model_id(task_id,api.AI_DETECTION_TASK_PREFIX)
    owner=DetectionTaskStore(lambda:api.runtime_postgres_repository_or_none(),
        TaskStorePaths(lambda:api.DATA_DIR,lambda:api.AI_DETECTION_TASKS_PATH,lambda:api.ensure_dirs()),
        TaskReadCache(lambda key:api.store_read_cache_get(key),lambda key,value:api.store_read_cache_put(key,value),lambda key:api.store_read_cache_invalidate(key)),
        TaskRows(lambda task:api.ai_detection_task_row(task),lambda:api.row_raw_json_list),lambda:api.safe_background_set_id)
    for name in ('load_ai_detection_tasks','save_ai_detection_tasks','find_ai_detection_task','save_ai_detection_task'):
        setattr(api,name,getattr(owner,name))
    api.ai_detection_task_background_record=lambda task_id:task_backgrounds.ai_detection_task_background_record(task_id,find_task=lambda value:api.find_ai_detection_task(value),normalize_background=lambda:api.safe_background_set_id)
    api.hydrate_auto_optimize_background_from_ai_task=lambda state:task_backgrounds.hydrate_auto_optimize_background_from_ai_task(state,background_record=lambda:api.ai_detection_task_background_record,normalize_background=lambda:api.safe_background_set_id)
    return api


def assert_default_task_store(server):
    import unittest
    from unittest.mock import patch,Mock
    from scripts.canonical_application_source_contract import verify_actual_sources
    from scripts.auto_optimization_test_ports import assert_native_relay
    from local_inspection_service.runtime.wiring import inspection
    from local_inspection_service.detection import task_identity
    verify_actual_sources()
    case=unittest.TestCase()
    application=server._default_application
    graph=application.inspection
    owner=graph._detection_task_store
    infra=application.infrastructure
    case.assertIs(type(owner),DetectionTaskStore)
    case.assertIs(server._detection_task_store,owner)
    for selected,name in ((owner.paths.data,'DATA_DIR'),(owner.paths.tasks,'AI_DETECTION_TASKS_PATH')):
        original=getattr(application.values,name)
        case.assertIs(selected(),original)
        try:
            from pathlib import Path
            replacement=Path('synthetic-task-store')
            object.__setattr__(application.values,name,replacement)
            case.assertIs(selected(),replacement)
        finally:object.__setattr__(application.values,name,original)
    case.assertIs(owner.rows.decode(),inspection.row_raw_json_list)
    case.assertIs(owner.normalize_background(),inspection.safe_background_set_id)
    item,value=object(),object()
    for selected,target,method,args in (
        (owner.repository,infra._runtime_repository_access,'runtime_postgres_repository_or_none',()),
        (server.load_ai_detection_tasks,owner,'load_ai_detection_tasks',()),
        (server.save_ai_detection_tasks,owner,'save_ai_detection_tasks',(item,)),
        (server.find_ai_detection_task,owner,'find_ai_detection_task',('synthetic',)),
    ):
        assert_native_relay(case,selected,(target,method,args,{},args,{}))
    for selected,attribute,target,method,args in (
        (owner.paths.ensure,'ensure_dirs',infra._service_directories,'ensure',()),
        (owner.cache.get,'store_read_cache_get',infra._store_cache,'get',('ai_detection_tasks',)),
        (owner.cache.put,'store_read_cache_put',infra._store_cache,'put',('ai_detection_tasks',item)),
        (owner.cache.invalidate,'store_read_cache_invalidate',infra._store_cache,'invalidate',('ai_detection_tasks',)),
    ):
        original=getattr(infra,attribute)
        case.assertIs(original.__self__,target)
        case.assertIs(original.__func__,getattr(type(target),method))
        callee=Mock(return_value=value)
        try:
            object.__setattr__(infra,attribute,callee)
            case.assertIs(selected(*args),value)
            callee.assert_called_once_with(*args)
            for actual,expected in zip(callee.call_args.args,args):
                if type(expected) is object:case.assertIs(actual,expected)
        finally:object.__setattr__(infra,attribute,original)
    with patch.object(inspection,'ai_detection_task_row',return_value=value) as callee:
        case.assertIs(owner.rows.encode(item),value)
        callee.assert_called_once_with(item)
        case.assertIs(callee.call_args.args[0],item)
    case.assertIs(server.sanitize_ai_detection_task_id,task_identity.sanitize_ai_detection_task_id)
    case.assertEqual(server.ai_detection_task_model_id(' synthetic-task '),task_identity.ai_detection_task_model_id(' synthetic-task ',server.AI_DETECTION_TASK_PREFIX))

    for keywords,forwarded in (({}, {'prepend':False}),({'prepend':True},{'prepend':True})):
        assert_native_relay(case,server.save_ai_detection_task,(owner,'save_ai_detection_task',(item,),keywords,(item,),forwarded))
    from local_inspection_service.compatibility import infrastructure as legacy
    with patch.object(legacy,'_detection_task_background_record',return_value=value) as callee:
        case.assertIs(server.ai_detection_task_background_record('synthetic-task'),value)
        callee.assert_called_once()
        case.assertEqual(callee.call_args.args,('synthetic-task',))
        abilities=callee.call_args.kwargs
        case.assertEqual(set(abilities),{'find_task','normalize_background'})
        assert_native_relay(case,abilities['find_task'],(owner,'find_ai_detection_task',('synthetic-task',),{},('synthetic-task',),{}))
        case.assertIs(abilities['normalize_background'](),legacy.safe_background_set_id)
    with patch.object(legacy,'_hydrate_detection_task_background',return_value=value) as callee:
        case.assertIs(server.hydrate_auto_optimize_background_from_ai_task(item),value)
        callee.assert_called_once()
        case.assertIs(callee.call_args.args[0],item)
        abilities=callee.call_args.kwargs
        case.assertEqual(set(abilities),{'background_record','normalize_background'})
        case.assertIs(abilities['background_record'](),legacy.ai_detection_task_background_record)
        case.assertIs(abilities['normalize_background'](),legacy.safe_background_set_id)

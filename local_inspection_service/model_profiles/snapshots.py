"""Persist references at submission; scope manual worker threads to those references."""
import copy
import functools
import inspect
import sys
from .service import _scope


def freeze_record(ns, record):
    if 'model_profiles' not in record:
        service = ns.get('model_profile_service')
        if service is not None:
            record['model_profiles'] = copy.deepcopy(_scope.get() or service.snapshot_for_record(record))
    return record


def pinned(loader=None, argument=0):
    def decorate(fn):
        signature = inspect.signature(fn)
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            ns = vars(sys.modules[fn.__module__])
            service = ns.get('model_profile_service')
            if service is None:
                return fn(*args, **kwargs)
            bound = signature.bind(*args, **kwargs)
            values = list(bound.arguments.values())
            value = values[argument] if len(values)>argument else None
            record = ns[loader](value) if loader and value is not None else value if isinstance(value,dict) else None
            snapshot = record.get('model_profiles') if isinstance(record,dict) else None
            if snapshot is None:
                snapshot = _scope.get() or service.snapshot_for_record(record or {})
            with service.scope(snapshot):
                return fn(*args, **kwargs)
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapped(*args, **kwargs):
                ns = vars(sys.modules[fn.__module__])
                service = ns.get('model_profile_service')
                if service is None:
                    return await fn(*args, **kwargs)
                with service.scope(_scope.get()):
                    return await fn(*args, **kwargs)
            return async_wrapped
        return wrapped
    return decorate


def public_record(value):
    if isinstance(value, dict):
        return {k: public_record(v) for k,v in value.items() if k not in {'model_profiles','profile_snapshot','secret_ref','proxy_ref'}}
    if isinstance(value, list):
        return [public_record(v) for v in value]
    return value

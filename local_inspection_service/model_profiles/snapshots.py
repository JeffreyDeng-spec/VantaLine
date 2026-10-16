"""Persist task references and carry their binding across sync/async execution."""
import copy
import functools
import inspect
from ..privacy.identities import PRIVATE_IDENTITIES, snapshot_identity_terms

from .dependencies import RecordLoader, ResolverProvider, require_resolver


def freeze_record(service_provider: ResolverProvider, record):
    if 'model_profiles' not in record:
        service = require_resolver(service_provider)
        snapshot = service.current_snapshot()
        if snapshot is None:
            snapshot = service.snapshot_for_record(record)
        record['model_profiles'] = copy.deepcopy(snapshot)
    return record


def pinned(service_provider: ResolverProvider, loader: RecordLoader | None = None, argument=0):
    """Bind before executing; absence of an injected resolver fails closed.

    A callable loader is resolved by the composition root, independent of the
    decorated function's source module. The provider is lazy for startup order
    and per-application test replacement; it never looks up a module namespace.
    """
    if not callable(service_provider) or (loader is not None and not callable(loader)):
        raise TypeError('Model resolver provider and task loader must be callable')

    def decorate(fn):
        signature = inspect.signature(fn)

        def binding(args, kwargs):
            service = require_resolver(service_provider)
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            values = list(bound.arguments.values())
            value = values[argument] if len(values) > argument else None
            record = loader(value) if loader is not None and value is not None else value if isinstance(value, dict) else None
            snapshot = record.get('model_profiles') if isinstance(record, dict) else None
            if snapshot is None:
                snapshot = service.current_snapshot()
            if snapshot is None:
                snapshot = service.snapshot_for_record(record or {})
            return service, snapshot

        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            service, snapshot = binding(args, kwargs)
            with service.scope(snapshot):
                return fn(*args, **kwargs)

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapped(*args, **kwargs):
                service, snapshot = binding(args, kwargs)
                with service.scope(snapshot):
                    return await fn(*args, **kwargs)
            return async_wrapped
        return wrapped
    return decorate


def public_record(value):
    return _public_record(value, ())


def _public_record(value, inherited):
    if isinstance(value, dict):
        terms = inherited
        if value.get('model_profiles') or value.get('profile_snapshot'):
            terms = tuple(sorted(set(inherited) | set(snapshot_identity_terms(value.get('model_profiles'))) |
                                 set(snapshot_identity_terms(value.get('profile_snapshot'))), key=lambda term: (-len(term), term)))
        result = {k: _public_record(v, terms) for k,v in value.items() if k not in {'model_profiles','profile_snapshot','secret_ref','proxy_ref'}}
        if (value.get('role') in {'agent','assistant'} or ('action' in value and 'message_to_user' in value and value.get('role')!='user')) and terms:
            existing = value.get(PRIVATE_IDENTITIES)
            existing_terms = {item for item in existing if isinstance(item,str)} if isinstance(existing,list) else set()
            result[PRIVATE_IDENTITIES] = sorted(set(terms) | existing_terms)
        return result
    if isinstance(value, list):
        return [_public_record(v, inherited) for v in value]
    return value


def bind_current(service_provider: ResolverProvider, target):
    """Carry only an already bound model snapshot into a deferred callback.

    Capture the resolver and a private snapshot before submission. Other
    ContextVars (identity, read caches, write authorization) are not copied.
    Missing binding fails before the executor can submit a paid operation.
    """
    service = require_resolver(service_provider)
    snapshot = service.current_snapshot()
    if snapshot is None:
        raise RuntimeError("No bound model snapshot for deferred model work")
    snapshot = copy.deepcopy(snapshot)
    @functools.wraps(target)
    def run(*args, **kwargs):
        with service.scope(snapshot):
            return target(*args, **kwargs)
    return run

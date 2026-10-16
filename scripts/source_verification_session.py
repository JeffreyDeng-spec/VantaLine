"""Deduplicate shared validators within one synchronous source proof only.

Each outer entry starts a new context and drops it on success or failure. Current
files, inventories and fixtures are therefore re-read on the next proof, including
warm source/fixture mutation tests. Direct validators remain uncached outside a
proof. Product code never imports this helper.
"""
from contextvars import ContextVar
from functools import wraps
from importlib import import_module

_session = ContextVar("source_verification_session", default=None)


def verification_entry(function):
    @wraps(function)
    def checked(*args, **kwargs):
        if _session.get() is not None:
            return function(*args, **kwargs)
        _prepare_shared_validators()
        token = _session.set({})
        try:
            return function(*args, **kwargs)
        finally:
            _session.reset(token)
    return checked


def shared_validator(function):
    """Only no-argument, read-only fixture validators may use this decorator."""
    @wraps(function)
    def checked():
        cache = _session.get()
        if cache is None:
            return function()
        if function not in cache:
            cache[function] = function()
        return cache[function]
    checked._source_shared_validator = True
    return checked


def _prepare_shared_validators():
    # Keep the historical validators and their pinned source bytes unchanged.
    # Their complete original bodies run once in each new outer proof; outside
    # that proof the wrappers execute the original bodies on every direct call.
    for name, attribute in (
        ("admin_user_data_source_contract", "fixture"),
        ("plc_modbus_source_contract", "checked_fixture"),
        ("plc_global_protocol_source_contract", "checked_global_fixture"),
        ("billing_source_contract", "fixture"),
        ("billing_configuration_source_contract", "fixture"),
        ("billing_volc_summary_source_contract", "fixture"),
    ):
        module = import_module(name)
        function = getattr(module, attribute)
        if not getattr(function, "_source_shared_validator", False):
            setattr(module, attribute, shared_validator(function))

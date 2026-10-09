"""Request-scoped original capture group; no PLC execution capability."""
from contextvars import ContextVar
from contextlib import contextmanager

source_group=ContextVar('real_photo_source_group',default='')


@contextmanager
def group(value):
    token=source_group.set(value)
    try:yield
    finally:source_group.reset(token)

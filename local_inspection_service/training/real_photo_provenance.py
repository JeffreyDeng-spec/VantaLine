"""Request-scoped original capture group; no PLC execution capability."""
from contextvars import ContextVar
from contextlib import contextmanager

original_sha=ContextVar('real_photo_original_sha',default='')
pixel_sha=ContextVar('real_photo_pixel_sha',default='')
source_group=ContextVar('real_photo_source_group',default='')


@contextmanager
def group(value, *, original_hash="", pixel_hash=""):
    token=source_group.set(value)
    raw_token=original_sha.set(original_hash);pixel_token=pixel_sha.set(pixel_hash)
    try:yield
    finally:
        source_group.reset(token);original_sha.reset(raw_token);pixel_sha.reset(pixel_token)

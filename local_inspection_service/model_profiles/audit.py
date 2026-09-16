"""Provider call accounting; no prompts, images, endpoints or secrets in the ledger."""
import functools
import logging
import time

from .dependencies import ResolverProvider, require_resolver


def _record(recorder, settings, start, ok, usage):
    try:
        recorder(settings, round((time.monotonic() - start) * 1000), ok, usage)
    except Exception:
        # A completed inference must never be repeated because its usage ledger
        # is unavailable. No provider exception or credential is logged here.
        logging.getLogger(__name__).warning('Model usage accounting unavailable')


def _redact_error(exc, settings):
    message = str(exc)
    if getattr(exc, 'http_status', None):
        message = f"模型服务返回 HTTP {exc.http_status}"

    def redact(value):
        if isinstance(value, str):
            for secret in (settings.get('api_key'), settings.get('proxy_url_raw')):
                if secret:
                    value = value.replace(secret, '[REDACTED]')
        elif isinstance(value, list):
            value = [redact(v) for v in value]
        elif isinstance(value, dict):
            value = {k: redact(v) for k, v in value.items()}
        return value

    for field in ('response_preview', 'previous_errors', 'usage_metadata', 'failed_usage_metadata'):
        if hasattr(exc, field):
            setattr(exc, field, redact(getattr(exc, field)))
    message = redact(message)
    if message != str(exc):
        exc.args = (message,)
        raise exc from None


def metered(service_provider: ResolverProvider):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(self, *args, **kwargs):
            settings = self.settings
            recorder = require_resolver(service_provider).record_call if settings.get('profile_id') else None
            start = time.monotonic()
            ok, result = False, None
            try:
                result = fn(self, *args, **kwargs)
                ok = True
                return result
            except Exception as exc:
                if settings.get('profile_id'):
                    _redact_error(exc, settings)
                raise
            finally:
                if recorder is not None:
                    usage = result.get('usage_metadata', result.get('usage', {})) if isinstance(result, dict) else getattr(self, 'last_usage_metadata', {})
                    _record(recorder, settings, start, ok, usage)
        return wrapped
    return decorate


def metered_function(settings_argument=0):
    """Direct transports receive their recorder from the calling runtime."""
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            settings = args[settings_argument] if len(args) > settings_argument else kwargs.get('settings', kwargs.get('resolved', {}))
            recorder = kwargs.get('record_usage')
            if settings.get('profile_id') and recorder is None:
                raise RuntimeError('Model usage recorder is not configured')
            start = time.monotonic()
            ok, usage = False, {}
            try:
                result = fn(*args, **kwargs)
                diagnostic = result[1] if isinstance(result, tuple) and len(result) > 1 and isinstance(result[1], dict) else {}
                usage = diagnostic.get('usage', {})
                ok = not diagnostic.get('error_type')
                return result
            finally:
                if recorder is not None and settings.get('profile_id'):
                    _record(recorder, settings, start, ok, usage)
        return wrapped
    return decorate

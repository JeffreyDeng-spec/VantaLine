"""Provider call accounting; no prompts, images, endpoints or secrets in the ledger."""
import functools
import logging
import sys
import time


def metered(fn):
    @functools.wraps(fn)
    def wrapped(self,*args,**kwargs):
        start = time.monotonic()
        ok = False
        result = None
        try:
            result = fn(self,*args,**kwargs)
            ok = True
            return result
        except Exception as exc:
            settings = self.settings
            if settings.get('profile_id'):
                message = str(exc)
                if getattr(exc,'http_status',None):
                    message = f"模型服务返回 HTTP {exc.http_status}"
                def redact(value):
                    if isinstance(value,str):
                        for secret in (settings.get('api_key'), settings.get('proxy_url_raw')):
                            if secret: value=value.replace(secret,'[REDACTED]')
                    elif isinstance(value,list): value=[redact(v) for v in value]
                    elif isinstance(value,dict): value={k:redact(v) for k,v in value.items()}
                    return value
                for field in ('response_preview','previous_errors','usage_metadata','failed_usage_metadata'):
                    if hasattr(exc,field): setattr(exc,field,redact(getattr(exc,field)))
                for secret in (settings.get('api_key'), settings.get('proxy_url_raw')):
                    if secret:
                        message = message.replace(secret, '[REDACTED]')
                if message != str(exc):
                    exc.args = (message,)
                    raise exc from None
            raise
        finally:
            settings = self.settings
            if settings.get('profile_id'):
                ns = vars(sys.modules[fn.__module__])
                try:
                    ns['model_profile_service'].record_call(settings, round((time.monotonic()-start)*1000), ok, (result.get('usage_metadata', result.get('usage',{})) if isinstance(result,dict) else getattr(self,'last_usage_metadata',{})))
                except Exception:
                    logging.getLogger(__name__).warning('Model usage accounting unavailable')
    return wrapped


_service = None

def metered_function(settings_argument=0):
    """Account for existing direct OCR transports without changing retry behavior."""
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            settings = args[settings_argument] if len(args)>settings_argument else kwargs.get('settings',kwargs.get('resolved',{}))
            start = time.monotonic()
            ok, usage = False, {}
            try:
                result = fn(*args,**kwargs)
                diagnostic = result[1] if isinstance(result,tuple) and len(result)>1 and isinstance(result[1],dict) else {}
                usage = diagnostic.get('usage',{})
                ok = not diagnostic.get('error_type')
                return result
            finally:
                if _service is not None and settings.get('profile_id'):
                    try:
                        _service.record_call(settings,round((time.monotonic()-start)*1000),ok,usage)
                    except Exception:
                        logging.getLogger(__name__).warning('Model usage accounting unavailable')
        return wrapped
    return decorate

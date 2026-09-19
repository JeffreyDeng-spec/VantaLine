"""Public status projections without application or request state."""
from typing import Any
from .status_ports import StatusPolicy, StatusSources, StatusProjectionCalls

class PublicStatusProjection:
    def __init__(self, policy: StatusPolicy, sources: StatusSources, calls: StatusProjectionCalls) -> None:
        self._policy = policy
        self._sources = sources
        self._calls = calls

    def public_ai_detection_status(self) -> dict[str, Any]:
        settings = self._sources.ai()()
        public = {key: value for key, value in settings.items() if key not in {'api_key', 'api_key_candidates', 'proxy_url_raw'}}
        public['image_generation'] = self._calls.image()()
        return public

    def public_ai_detection_status_for_user(self, user: dict[str, Any] | None) -> dict[str, Any]:
        if self._policy.permission()(user, 'ai_config'):
            return self._calls.ai()()
        settings = self._sources.ai()()
        return {'enabled': bool(settings.get('enabled')), 'configured': bool(settings.get('configured')), 'status': str(settings.get('status') or ''), 'message': str(settings.get('message') or ''), 'provider_label': str(settings.get('provider_label') or '')}

    def public_status_model_for_user(self, model: dict[str, Any], user: dict[str, Any] | None) -> dict[str, Any]:
        public = {key: model.get(key) for key in self._policy.model_fields() if key in model}
        if model.get('is_ai_detection') and self._policy.permission()(user, 'ai_config') and ('provider_status' in model):
            public['provider_status'] = model.get('provider_status')
        return public

    def public_service_status_for_user(self, user: dict[str, Any] | None, payload: dict[str, Any]) -> dict[str, Any]:
        if self._policy.admin()(user):
            return payload
        return {'service': payload.get('service'), 'model_exists': payload.get('model_exists'), 'active_model_id': payload.get('active_model_id'), 'available_models': [self._calls.model()(item, user) for item in payload.get('available_models') or [] if isinstance(item, dict)], 'specialized_models': [self._calls.model()(item, user) for item in payload.get('specialized_models') or [] if isinstance(item, dict)], 'specialized_model_tasks': payload.get('specialized_model_tasks') or [], 'ai_detection_tasks': payload.get('ai_detection_tasks') or [], 'ai_detection': self._calls.ai_for_user()(user), 'training_execution': {'status': 'restricted', 'executor': ''}, 'cursor_image2': {'status': 'restricted', 'configured': False}, 'classes': payload.get('classes') or [], 'rule': payload.get('rule') or {}, 'ocr': {}}

    def public_config_summary_for_user(self, user: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
        if self._policy.admin()(user):
            return self._policy.sanitize()(config)
        return self._policy.sanitize()({'confidence_threshold': config.get('confidence_threshold'), 'required_classes': config.get('required_classes'), 'min_counts': config.get('min_counts')})

    def public_image_generation_status(self) -> dict[str, Any]:
        settings = self._sources.image()()
        return {key: value for key, value in settings.items() if key not in {'api_key', 'proxy_url_raw'}}

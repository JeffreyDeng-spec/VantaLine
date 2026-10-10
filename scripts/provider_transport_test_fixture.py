"""Independent native transport graphs for offline dependency-capture contracts."""
from types import SimpleNamespace


def transport_fixture(server):
    from local_inspection_service.model_providers.transport_composition import ProviderTransports, TransportInputs
    from local_inspection_service.model_providers.openai_ports import OpenAITransportIO, OpenAITransportErrors
    from local_inspection_service.model_providers.gemini_ports import GeminiTransportIO, GeminiTransportErrors
    from local_inspection_service.model_providers.image_ports import ImageTransportIO, ImageTransportErrors
    from local_inspection_service.model_providers.http_errors import ProviderHttpErrors, ProviderErrorTypes
    from local_inspection_service.model_providers.payloads import ProviderPayloadParser
    names=(
        'AiProviderError','AiProviderAuthError','AiProviderOverloaded','AiProviderConfigError',
        'AiProviderNonRetryableError','AiProviderTimeout','bounded_text','sha256_bytes',
        'ai_urlopen','parse_ai_json_object','data_url_payload','decode_b64_image',
        'masked_url_for_status','time','urllib','requests','json','model_profile_service',
        'resolve_model_profiles','AI_PROFILE_CACHE_TTL_SECONDS',
        'normalize_ai_json_root','ai_json_text_candidates','cursor_image2_response_candidates',
    )
    api=SimpleNamespace(**{name:getattr(server,name) for name in names})
    parser=ProviderPayloadParser(lambda:api.ai_json_text_candidates,
        lambda:api.normalize_ai_json_root,lambda:api.AiProviderError)
    api.parse_ai_json_object=parser.parse_ai_json_object
    api.data_url_payload=parser.data_url_payload
    error_policy=ProviderHttpErrors(lambda:api.bounded_text,ProviderErrorTypes(
        lambda:api.AiProviderError,lambda:api.AiProviderAuthError,lambda:api.AiProviderOverloaded,
        lambda:api.AiProviderConfigError,lambda:api.AiProviderNonRetryableError))
    api.provider_http_error=error_policy.provider_http_error
    openai=OpenAITransportIO(lambda:api.ai_urlopen,lambda:api.parse_ai_json_object,
        lambda:api.bounded_text,lambda:api.sha256_bytes,lambda:api.provider_http_error)
    gemini=GeminiTransportIO(lambda:api.ai_urlopen,lambda:api.parse_ai_json_object,
        lambda:api.bounded_text,lambda:api.data_url_payload,lambda:api.decode_b64_image,
        lambda:api.masked_url_for_status,lambda:api.urllib.parse.quote,lambda:api.provider_http_error)
    image=ImageTransportIO(lambda:api.ai_urlopen,lambda:api.bounded_text,
        lambda:api.decode_b64_image,lambda:api.masked_url_for_status,lambda:api.requests.get)
    openai_errors=OpenAITransportErrors(lambda:api.AiProviderConfigError,
        lambda:api.AiProviderTimeout,lambda:api.AiProviderError)
    gemini_errors=GeminiTransportErrors(lambda:api.AiProviderConfigError,
        lambda:api.AiProviderTimeout,lambda:api.AiProviderError,
        lambda:api.AiProviderAuthError,lambda:api.AiProviderOverloaded)
    image_errors=ImageTransportErrors(lambda:api.AiProviderConfigError,
        lambda:api.AiProviderTimeout,lambda:api.AiProviderError,
        lambda:api.AiProviderAuthError,lambda:api.AiProviderOverloaded,
        lambda:api.requests.RequestException)
    resolve=lambda:api.model_profile_service
    graph=ProviderTransports(TransportInputs(lambda:openai,lambda:openai_errors,
        lambda:gemini,lambda:gemini_errors,lambda:image,lambda:image_errors,
        lambda:'1024x1024',lambda:'1024*1024',
        lambda:api.cursor_image2_response_candidates),resolve,
        cache_ttl_seconds=api.AI_PROFILE_CACHE_TTL_SECONDS)
    api._provider_transports=graph
    api.OpenAICompatibleAiProvider=graph.openai
    api.GeminiAiProvider=graph.gemini
    api.AgnesImageProvider=graph.agnes
    api.QwenImageProvider=graph.qwen
    return api

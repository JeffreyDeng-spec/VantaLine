"""Read the pre-registry configuration exactly once during additive migration."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LegacyConfiguration:
    ai: Callable[[], dict[str, Any]]
    image: Callable[[], dict[str, Any]]
    agent: Callable[[], dict[str, Any]]
    local: Callable[[], dict[str, Any]]
    ai_keys: Callable[..., list[dict[str, Any]]]
    image_keys: Callable[..., list[dict[str, Any]]]
    agent_keys: Callable[..., list[dict[str, Any]]]


def sources(config: LegacyConfiguration):
    ai = config.ai()
    image = config.image()
    agent = config.agent()
    local = config.local()
    ai['api_key_candidates'] = config.ai_keys(local)
    image['api_key_candidates'] = config.image_keys(local, image['provider'])
    agent['api_key_candidates'] = config.agent_keys(agent)
    key = agent.get('api_key', '')
    result = [('原 AI 配置', ai, ['pipeline','manual','accessory','training_vision','document']),
              ('原图片生成配置', image, ['image']),
              ('原训练助手', {**agent, 'api_key': key}, ['training_assistant'])]
    from ..label_inspection.model import legacy_settings, MODEL, URL
    label = legacy_settings()
    result.append(('原标签配置', dict(provider='doubao',model=MODEL,base_url=URL,api_key=label['key'],timeout_seconds=180), ['label']))
    if ai.get('provider') == 'qwen' and ai.get('api_key'):
        result.append(('原专用 OCR', {**ai, 'model':'qwen-vl-ocr-2025-11-20'}, ['ocr']))
    return result

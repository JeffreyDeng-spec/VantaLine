"""Private configured identities accompany raw Agent evidence, never user input."""
import re

PRIVATE_IDENTITIES = "_private_model_identities"


def identity_terms(config):
    if not isinstance(config, dict):
        return []
    return sorted({value.strip() for key in ("model", "model_name", "provider", "provider_label")
                   if isinstance(value := config.get(key), str) and len(value.strip()) >= 3}, key=lambda value: (-len(value), value))


def neutralize_identities(value, terms):
    if not isinstance(value, str):
        return value
    for term in terms if isinstance(terms, list) else []:
        if isinstance(term, str) and len(term) >= 3:
            value = re.sub(re.escape(term), "AI 检测", value, flags=re.I)
    return value

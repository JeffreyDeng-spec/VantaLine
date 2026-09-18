"""Public text-record projection; private evidence stays in persistence."""
import copy
from typing import Any
from urllib.parse import quote


def public_record(value: dict[str, Any]) -> dict[str, Any]:
    from ..model_profiles.snapshots import public_record
    result = public_record(copy.deepcopy(value))
    result.pop("model_profiles", None)
    result.pop("source_path", None)
    result.pop("source_preview_path", None)
    for audit in result.get('diagnostics', {}).get('model_audits', []):
        for evidence in audit.get('files', {}).values():
            evidence.pop('path', None)
    result.pop("media_path", None)
    result.pop("annotated_path", None)
    result.pop("reference_overlay_path", None)
    for trace in result.get('diagnostics', {}).get('rereads', []):
        trace.pop('input_path', None)
    if result.get("id") and result.get("asset_kind"):
        result["content_url"] = f"/api/text-inspection/assets/{quote(str(result['id']))}/content"
        result["original_url"] = result["content_url"]
        active = result.get("active_preparation")
        result["comparison_ready"] = not result.get("preparation_required") or bool(active or result.get("preparation_previous_snapshot"))
        if active:
            from ..standard_preparation import supports_text_comparison
            if not supports_text_comparison(active):
                result["comparison_ready"] = False
                result["comparison_unavailable_reason"] = "纯图形标准：已保存，当前不支持文字对比"
            result["content_url"] = f"/api/text-inspection/standards/{result['standard_id']}/preparation/{result['id']}/{active['id']}/clean"
    return result

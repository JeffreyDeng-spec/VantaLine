"""Explicit recommendation service without application imports."""
from typing import Any
import urllib.error
from .invocation_ports import AgentInvocationSettings, AgentInvocationCodec, AgentResponseParsing, AgentRecommendationInputs, AgentRecommendationCalls


class AgentRecommendation:
    def __init__(self, settings: AgentInvocationSettings, codec: AgentInvocationCodec, parsing: AgentResponseParsing, inputs: AgentRecommendationInputs, calls: AgentRecommendationCalls) -> None:
        self._settings = settings
        self._codec = codec
        self._parsing = parsing
        self._inputs = inputs
        self._calls = calls

    def parse_agent_json(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = self._parsing.substitute()(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
        match = self._parsing.search()(r"\{.*\}", text, flags=self._parsing.dotall())
        if not match:
            raise RuntimeError("Agent response did not contain JSON")
        return self._codec.loads()(match.group(0))

    def rule_recommendation(self, stage: str, selected: list[dict[str, Any]], sample_count: int | None = None) -> dict[str, Any]:
        accessory_count = max(1, len(selected))
        has_text = any(self._inputs.material()(item) == "text" for item in selected)
        train_mode = "yolo_ocr" if has_text else "yolo"
        if stage == "samples":
            recommended_samples = max(200, min(2000, accessory_count * 200))
            return {
                "stage": stage,
                "params": {
                    "sample_count": recommended_samples,
                    "train_mode": train_mode,
                    "background_set_id": self._inputs.background()(None, self._inputs.current_user()()),
                },
                "reason": f"{accessory_count} 个配件,按每个配件约 200 张合成样本估算,共 {recommended_samples} 张。",
            }
        effective_samples = max(1, int(sample_count or accessory_count * 200))
        if effective_samples < 300:
            epochs = 25
        elif effective_samples < 800:
            epochs = 40
        else:
            epochs = 60
        return {
            "stage": "training",
            "params": {
                "epochs": epochs,
                "image_size": 640,
                "train_mode": train_mode,
            },
            "reason": f"约 {effective_samples} 张样本,推荐 {epochs} 个 epoch、640px 分辨率{'、附带 OCR' if has_text else ''}。",
        }

    def clamp_recommend_params(self, stage: str, params: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        result = dict(fallback)
        if stage == "samples":
            try:
                result["sample_count"] = max(50, min(20000, int(params.get("sample_count", result["sample_count"]))))
            except (TypeError, ValueError):
                pass
        else:
            try:
                result["epochs"] = max(1, min(500, int(params.get("epochs", result["epochs"]))))
            except (TypeError, ValueError):
                pass
            try:
                result["image_size"] = max(320, min(1280, int(params.get("image_size", result["image_size"]))))
            except (TypeError, ValueError):
                pass
        if str(params.get("train_mode") or "") in {"yolo", "yolo_ocr"}:
            result["train_mode"] = str(params["train_mode"])
        return result

    def agent_recommendation(self, stage: str, accessory_ids: list[str], sample_count: int | None = None) -> dict[str, Any]:
        config = self._inputs.config()()
        try:
            selected = self._inputs.selected()(config, accessory_ids)
        except self._inputs.selection_error():
            selected = []
        rules = self._calls.rule()(stage, selected, sample_count)
        agent_config = self._settings.load()()
        if self._settings.normalize_provider()(agent_config.get("provider"), agent_config.get("base_url", "")) == self._settings.cursor_provider():
            if self._settings.connected()(agent_config):
                return {
                    **rules,
                    "source": "rules",
                    "reason": f"{self._settings.cursor_message()}。{rules['reason']}",
                    "agent_error": self._settings.cursor_message(),
                }
            return {**rules, "source": "rules"}
        if not self._settings.recommended()(agent_config):
            return {**rules, "source": "rules"}
        summary = [
            {
                "name": item.get("name"),
                "material_type": self._inputs.material()(item),
                "source_image_count": len(item.get("source_files") or []),
            }
            for item in selected
        ]
        prompt = {
            "stage": stage,
            "accessories": summary,
            "sample_count": sample_count,
            "defaults": rules["params"],
            "constraints": {
                "sample_count": [50, 20000],
                "epochs": [1, 500],
                "image_size": [320, 1280],
                "train_mode": ["yolo", "yolo_ocr"],
            },
        }
        system = (
            "你是工业视觉质检平台的训练规划 Agent。根据配件信息推荐训练参数。"
            "只输出一个 JSON 对象,不要输出其他文本。字段:"
            '{"sample_count": int, "epochs": int, "image_size": int, "train_mode": "yolo"|"yolo_ocr", "reason": "一句话中文理由"}。'
            "只需要给出与 stage 相关的字段。"
        )
        try:
            content = self._calls.chat()(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": self._codec.dumps()(prompt, ensure_ascii=False)},
                ],
                agent_config,
            )
            parsed = self._calls.parse()(content)
            params = self._calls.clamp()(stage, parsed, rules["params"])
            reason = str(parsed.get("reason") or rules["reason"]).strip()[:200]
            return {"stage": rules["stage"], "params": params, "reason": reason, "source": "agent"}
        except Exception as exc:  # noqa: BLE001 - 外部 API 任意失败都应回退规则引擎
            return {**rules, "source": "rules", "agent_error": str(exc)[:200]}

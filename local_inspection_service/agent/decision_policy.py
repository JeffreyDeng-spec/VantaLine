"""Explicit decision policy service without application imports."""
from typing import Any
from .pipeline_decision_ports import AgentDecisionPolicyValues, AgentDecisionRuleCalls, AgentDecisionText


class AgentDecisionPolicy:
    def __init__(self, policy: AgentDecisionPolicyValues, rules: AgentDecisionRuleCalls, text: AgentDecisionText) -> None:
        self._policy = policy
        self._rules = rules
        self._text = text

    def normalize_agent_pipeline_decision(self, parsed: dict[str, Any]) -> dict[str, Any]:
        action = str(parsed.get("action") or "reply").strip().lower()
        if action not in self._policy.actions():
            action = "reply"
        decision: dict[str, Any] = {
            "action": action,
            "params": {},
            "advance_after": bool(parsed.get("advance_after")),
            "target_stage": "",
            "needs_user": bool(parsed.get("needs_user")) or action == "pause_and_ask",
            "message_to_user": self._text.bounded()(parsed.get("message_to_user"), 600),
            "reason": self._text.bounded()(parsed.get("reason"), 300),
            "suggested_actions": [self._text.bounded()(item, 40) for item in (parsed.get("suggested_actions") or []) if str(item).strip()][:6],
            "source": "agent",
        }
        raw_params = parsed.get("params") if isinstance(parsed.get("params"), dict) else {}
        for key in ("sample_count", "epochs", "image_size"):
            if key in raw_params:
                try:
                    decision["params"][key] = int(raw_params[key])
                except (TypeError, ValueError):
                    pass
        if str(raw_params.get("train_mode") or "") in {"yolo", "yolo_ocr"}:
            decision["params"]["train_mode"] = str(raw_params["train_mode"])
        if "sample_count" in decision["params"]:
            decision["params"]["sample_count"] = max(50, min(20000, decision["params"]["sample_count"]))
        if "epochs" in decision["params"]:
            decision["params"]["epochs"] = max(1, min(500, decision["params"]["epochs"]))
        if "image_size" in decision["params"]:
            decision["params"]["image_size"] = max(320, min(1280, decision["params"]["image_size"]))
        target = str(parsed.get("target_stage") or "").strip().lower()
        if target in self._policy.targets():
            decision["target_stage"] = target
        if not decision["message_to_user"]:
            decision["message_to_user"] = decision["reason"] or "已处理你的请求。"
        return decision

    def _rule_rerun_failed_stage(self, stage: str) -> tuple[str, str]:
        """Map a 'rerun the failed stage' intent to a concrete action/target.

    Re-running samples (or a later stage) goes through goto_stage->samples so the
    stale failed job is cleared and sample generation runs again while reusing
    the pose images already on disk (the existence guard prevents duplicate AI
    image generation). A failed draft stage simply advances again.
    """
        if stage in {"samples", "training", "library"}:
            return "goto_stage", "samples"
        return "advance", ""

    def agent_pipeline_rule_decision(self, task: dict[str, Any], user_message: str | None, trigger: str) -> dict[str, Any]:
        stage = str(task.get("stage") or "")
        status = str(task.get("status") or "")
        text = (user_message or "").lower().strip()

        def has(*keywords: str) -> bool:
            return any(keyword in text for keyword in keywords)

        if user_message:
            action = "reply"
            target_stage = ""
            if has("取消", "cancel", "停止", "stop", "abort"):
                action = "cancel"
            elif has(
                "从头", "重新开始", "重头", "推倒重来", "start over", "start-over",
                "startover", "restart", "from scratch", "reset",
            ):
                action, target_stage = "goto_stage", "draft"
            elif has("沿用", "现有素材", "继续素材", "reuse", "existing asset", "skip pose", "skip generation"):
                action = "continue_existing_assets"
            elif has(
                "重规划", "重新规划", "replan", "re-plan", "重做姿态", "换姿态",
                "调整方案", "换个角度", "换个方案",
            ):
                action = "replan"
            elif has("改配件", "重新选", "改参数", "回到草稿", "go back", "回退", "goto", "回到"):
                action, target_stage = "goto_stage", "draft"
            elif has("训练", "train") and stage == "samples" and status != "failed":
                action = "continue_training"
            elif has(
                "重试", "retry", "再试", "try again", "again", "重跑", "重新运行", "重新跑",
                "rerun", "re-run", "run again", "再生成", "重新生成", "重来",
                "continue", "继续", "推进", "下一步", "advance", "proceed", "resume",
                "go ahead", "go on", "keep going", "next", "go",
            ):
                # Forward / retry intent. On a failed task this means "re-run the
                # stage that failed"; otherwise advance to the next stage.
                if status == "failed":
                    action, target_stage = self._rules.rerun()(stage)
                elif has("重试", "retry", "再试", "rerun", "re-run", "again", "重跑", "重新生成图"):
                    action = "retry"
                else:
                    action = "advance"
            elif status == "failed":
                # Any other affirmative reply on a failed task -> re-run failed stage.
                action, target_stage = self._rules.rerun()(stage)
            else:
                action = "reply"

            if action == "goto_stage" and target_stage == "samples":
                message = "好的，正在重新生成训练样本（复用已生成的实拍抠图素材，不会回退到旧 AI 姿态图）。"
            elif action == "goto_stage":
                message = "好的，已回退到草稿阶段，便于你调整配件或参数。"
            else:
                message = {
                    "cancel": "好的，已为你取消本次流程。",
                    "retry": "好的，正在重试实拍高亮抠图素材生成。",
                    "continue_training": "好的，确认样本质量后进入训练。",
                    "continue_existing_assets": "好的，将沿用现有素材继续。",
                    "replan": "好的，正在按当前任务重新准备实拍高亮抠图素材。",
                    "advance": "好的，正在推进到下一阶段。",
                    "reply": "已收到你的消息。我可以重试当前阶段、推进到下一步、重新准备实拍抠图素材，或回退到草稿阶段（也可以直接说“取消”）。",
                }[action]

            return {
                **self._rules.normalize()(
                    {
                        "action": action,
                        "target_stage": target_stage,
                        "message_to_user": message,
                        "reason": "规则解析（Agent 未连接或解析失败）",
                    }
                ),
                "source": "rules",
            }
        if status == "completed" and stage in {"samples", "training"}:
            return {
                **self._rules.normalize()(
                    {
                        "action": "advance",
                        "message_to_user": "上一阶段已完成，自动推进到下一阶段。",
                        "reason": "规则自动推进",
                    }
                ),
                "source": "rules",
            }
        if status == "failed":
            return {
                **self._rules.normalize()(
                    {
                        "action": "pause_and_ask",
                        "message_to_user": "当前阶段执行失败，请确认是重试、重新准备素材还是取消。",
                        "reason": "规则自动升级：执行失败",
                        "suggested_actions": ["retry", "replan", "cancel"],
                    }
                ),
                "source": "rules",
            }
        return {
            **self._rules.normalize()(
                {"action": "reply", "message_to_user": "当前没有需要处理的事项。", "reason": "无动作"}
            ),
            "source": "rules",
        }

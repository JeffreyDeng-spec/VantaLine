"""Pure label response projection, shared without importing the HTTP layer."""

def public(value, *, diagnostic=False):
    result = {
        k: v
        for k, v in value.items()
        if k not in {"owner_user_id", "idempotency_key", "parameters", "kind"}
    }
    if not diagnostic and value.get("kind") == "run":
        for key in (
            "model",
            "prompt_hash",
            "layout",
            "transformations",
            "profile_snapshot",
        ):
            result.pop(key, None)
        if result.get("error") and not result.get("error_code"):
            result["error"] = (
                "检测未完成，请稍后手动重新检测；如需协助，请提供检测编号。"
            )
        if result.get("quality"):
            result["quality"] = {"checked": True}
    if "import" in result:
        result["import"] = {
            k: v
            for k, v in result["import"].items()
            if k in {"version", "completed", "total", "error"}
        }
    return result

"""RunPod terminal classification and strict worker-output decoding."""
from collections.abc import Callable
import json
from typing import Any


def runpod_terminal_status(status: str) -> bool:
    return status.upper() in {"COMPLETED", "FAILED", "CANCELLED", "CANCELED", "TIMED_OUT"}


class RunPodOutputParser:
    def __init__(self, bound_text: Callable[[], Callable[[Any, int], str]]):
        self.bound_text = bound_text

    def extract_runpod_worker_output(self, status_body: dict[str, Any]) -> dict[str, Any]:
        output = status_body.get("output")
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                output = {"message": output}
        if not isinstance(output, dict):
            raise RuntimeError("RunPod completed without a JSON worker output")
        if output.get("ok") is not True:
            detail = output.get("error") or output.get("message") or output.get("status") or "worker failed"
            raise RuntimeError(f"RunPod worker failed: {self.bound_text()(str(detail), 300)}")
        return output

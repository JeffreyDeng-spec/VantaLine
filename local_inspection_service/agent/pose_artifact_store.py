"""Explicit pose artifact store service without application imports."""
from typing import Any
from .pose_render_ports import PoseRenderPaths, PoseRenderArtifacts, PoseRenderPresentation
from pathlib import Path


class PoseArtifactStore:
    def __init__(self, paths: PoseRenderPaths, artifacts: PoseRenderArtifacts, presentation: PoseRenderPresentation) -> None:
        self._paths = paths
        self._artifacts = artifacts
        self._presentation = presentation

    def agent_mcp_pose_output_path(self, task: dict[str, Any], accessory_id: str, pose_id: str, mime_type: str) -> Path:
        extension = ".jpg" if "jpeg" in str(mime_type or "").lower() else ".png"
        owner_id = str(task.get("owner_user_id") or "")
        output_dir = self._paths.owner_root()("agent_mcp_pose_images", owner_id) / self._paths.sanitize()(str(task.get("id") or "task"))
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"{self._paths.sanitize()(accessory_id)}__{self._paths.sanitize()(pose_id)}{extension}"

    def write_agent_mcp_pose_artifact(self,
        task: dict[str, Any],
        call: dict[str, Any],
        result: dict[str, Any],
        *,
        prompt: str,
        reference_assets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        mime_type = str(result.get("mime_type") or "image/png")
        output_path = self._artifacts.output()(task, str(call.get("accessory_id") or ""), str(call.get("pose_id") or ""), mime_type)
        output_path.write_bytes(result["bytes"])
        digest = self._artifacts.digest()(output_path)
        provider_key = str(call.get("provider") or result.get("provider") or "gemini_native_image_generation")
        native_provider = "agnes" if provider_key == "agnes_image_generation" else "gemini"
        metadata = {
            "provider": provider_key,
            "model": result.get("model") or "",
            "prompt": prompt,
            "task_id": task.get("id"),
            "call_id": call.get("call_id"),
            "accessory_id": call.get("accessory_id"),
            "pose_id": call.get("pose_id"),
            "source_reference_assets": reference_assets,
            "chroma_screen": self._presentation.screen()(call.get("chroma_screen")),
            "output_path": str(output_path),
            "output_url": self._artifacts.public_url()(output_path),
            "mime_type": mime_type,
            "sha256": digest,
            "latency_ms": int(result.get("latency_ms") or 0),
            "usage_metadata": result.get("usage_metadata") if isinstance(result.get("usage_metadata"), dict) else {},
            "proxy": {
                "used": bool(result.get("proxy_used")),
                "source_name": str(result.get("proxy_source_name") or ""),
                "url": str(result.get("proxy_url") or ""),
                "auto_local": bool(result.get("proxy_auto_local")),
            },
            "generated_source_metadata": {
                "native_provider": native_provider,
                "generated_by": "Agnes Image" if native_provider == "agnes" else "Nano Banana",
                "synthid_watermark_expected": native_provider == "gemini",
            },
            "provider_text": self._artifacts.bounded()(result.get("text") or "", 600),
            "created_at": self._artifacts.now()(),
        }
        metadata_path = output_path.with_suffix(output_path.suffix + ".metadata.json")
        metadata_path.write_text(self._artifacts.dumps()(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return {**metadata, "metadata_path": str(metadata_path), "metadata_url": self._artifacts.public_url()(metadata_path)}

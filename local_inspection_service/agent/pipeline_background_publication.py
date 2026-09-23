"""Pipeline background plate prompt and publication workflow."""
from typing import Any
from pathlib import Path
import shutil
import time
from PIL import Image
from .pipeline_background_publication_ports import BackgroundPublicationTasks, BackgroundPublicationPaths, BackgroundPublicationSelection, BackgroundPublicationProviders, BackgroundPublicationCatalog, BackgroundPublicationProjection

def pipeline_background_plate_prompt(item: dict[str, Any]) -> str:
    name = str(item.get("name") or item.get("id") or "the item")
    return "\n".join(
        [
            "Generate ONE empty work-surface background plate for VantaLine training-sample synthesis.",
            f"Reference context: the original capture environment of accessory '{name}'.",
            "Reproduce the SAME visible background surface / environment shown in the reference photo, but completely EMPTY — remove every product, paper sheet, cable, strap, shadow of the product, hand, text, label, ruler, or tool so only the bare target surface remains.",
            "Do not invent a green conveyor or chroma background unless the reference background itself is green.",
            "Camera: STRICTLY vertical top-down (bird's-eye) at 90 degrees, optical axis perpendicular to the surface. No tilt, no perspective, no oblique angle.",
            "The surface must fill the entire frame edge to edge. Match the reference material, colour, texture scale, lighting, and camera height as closely as possible. Even, diffuse lighting; no glare, no objects, no people, no text, no rulers, no grid.",
        ]
    )

class PipelineBackgroundPublication:
    def __init__(self, tasks: BackgroundPublicationTasks, paths: BackgroundPublicationPaths, selection: BackgroundPublicationSelection, providers: BackgroundPublicationProviders, catalog: BackgroundPublicationCatalog, projection: BackgroundPublicationProjection) -> None:
        self._tasks = tasks
        self._paths = paths
        self._selection = selection
        self._providers = providers
        self._catalog = catalog
        self._projection = projection

    def ensure_pipeline_background_plate(self, task: dict[str, Any], config: dict[str, Any]) -> str | None:
        'Select or generate a single strict top-down empty background plate for the\n    task, register it as a per-task background set, and reuse it for both sprite\n    preparation and sample-generation backgrounds.'
        orchestration = self._tasks.state()(task)
        existing = orchestration.get("background_plate") if isinstance(orchestration.get("background_plate"), dict) else None
        if existing:
            set_id = str(existing.get("background_set_id") or "")
            if set_id and self._catalog.images()(self._paths.sets_directory() / set_id):
                task["background_set_id"] = set_id
                return set_id
        accessory_ids = self._tasks.ids()(config, [str(item_id) for item_id in task.get("accessory_ids") or []])
        if not accessory_ids:
            return None
        item = self._tasks.lookup()(config).get(accessory_ids[0])
        if not item:
            return None
        owner_id = str(task.get("owner_user_id") or "")
        plate_dir = self._paths.output()("agent_mcp_background_plates", owner_id) / self._paths.record_id()(str(task.get("id") or "task"))
        plate_dir.mkdir(parents=True, exist_ok=True)
        plate_path: Path | None = None
        plate_method = ""
        background_match: dict[str, Any] | None = None
        prompt = self._selection.prompt()(item)
        # 1) PRIMARY: reuse the closest existing background-library plate when the
        # exposed background patches in the first accessory capture match with high
        # confidence. This avoids unnecessary API calls and keeps repeated tasks in a
        # consistent environment.
        matched = self._selection.match()(item, owner_id)
        if matched:
            matched_path = self._paths.resolve()(matched.get("image_path"))
            if matched_path.exists():
                plate_path = plate_dir / "plate.png"
                try:
                    with Image.open(matched_path) as handle:
                        handle.convert("RGB").save(plate_path, format="PNG")
                    plate_method = "background_library_match"
                    background_match = matched
                    orchestration["background_plate_error"] = ""
                    print(
                        f"[pipeline.bg_plate] background library match set={matched.get('background_set_id')} "
                        f"distance={matched.get('distance')} src={matched_path}",
                        flush=True,
                    )
                except (OSError, ValueError):
                    plate_path = None
                    background_match = None
        # 2) FALLBACK: ask the image model to generate one empty mother plate only
        # when no existing background confidently matches.
        tool_config = self._providers.config()()
        reference_content, _reference_assets = self._providers.references()(item, max_images=2)
        provider: Any = None
        if plate_path is None and tool_config.get("configured"):
            settings = self._providers.settings()()
            settings["model"] = tool_config["model"]
            settings["timeout_seconds"] = tool_config["timeout_seconds"]
            provider = self._providers.create()(settings)
        if plate_path is None and reference_content and provider is not None:
            try:
                result = provider.generate_image(prompt, reference_content, model=tool_config["model"])
                payload = result.get("bytes")
                mime_type = str(result.get("mime_type") or "image/png")
            except self._providers.error_type() as exc:
                orchestration["background_plate_error"] = self._projection.bounded()(str(exc), 240)
                payload = None
                mime_type = "image/png"
            if payload:
                extension = ".jpg" if "jpeg" in mime_type.lower() else ".png"
                plate_path = plate_dir / f"plate{extension}"
                plate_path.write_bytes(payload)
                plate_method = f"agent_{str(tool_config.get('provider_name') or 'image')}_empty_surface"
                orchestration["background_plate_error"] = ""
        # 3) LAST LOCAL FALLBACK: only if API generation is unavailable/failed, try a
        # cheap local derivation to keep the existing no-background hard fallback
        # behavior. It is no longer the primary path because strip extraction is weak
        # when the accessory covers most of the photo.
        if plate_path is None:
            derived = self._selection.derive()(item, plate_dir / "plate.png")
            if derived is not None:
                plate_path = derived
                plate_method = "accessory_photo_surface_local_fallback"
                orchestration["background_plate_error"] = ""
        if plate_path is None or not plate_path.exists():
            if not orchestration.get("background_plate_error"):
                orchestration["background_plate_error"] = "无法从首个配件环境生成背景底板。"
            return None
        set_id = self._paths.set_id()(f"task_plate_{self._paths.record_id()(str(task.get('id') or 'task'))}")
        set_dir = self._paths.sets_directory() / set_id
        if set_dir.exists():
            shutil.rmtree(set_dir, ignore_errors=True)
        set_dir.mkdir(parents=True, exist_ok=True)
        try:
            with Image.open(plate_path) as handle:
                handle.convert("RGB").save(set_dir / "plate.png", format="PNG")
        except (OSError, ValueError):
            pass
        self._catalog.variants()(plate_path, set_dir, count=6)
        if not self._catalog.images()(set_dir):
            return None
        manifest = self._catalog.manifest()()
        sets = manifest.get("sets") if isinstance(manifest.get("sets"), dict) else {}
        sets[set_id] = {
            "id": set_id,
            "name": f"流水线背景 · {str(task.get('name') or task.get('id') or '')}".strip(),
            "description": "Agent 根据首个配件环境匹配或生成的垂直俯拍背景集",
            "source": str(plate_path),
            "created_at": int(time.time()),
            "owner_user_id": owner_id or self._projection.legacy_owner(),
            "owner_username": str(task.get("owner_username") or ""),
            "shared_with_user_ids": [],
            "generation_method": plate_method or "agent_task_background_plate",
            "background_match": background_match or {},
        }
        manifest["sets"] = sets
        self._catalog.publish()(manifest)
        orchestration["background_plate"] = {
            "background_set_id": set_id,
            "accessory_id": accessory_ids[0],
            "plate_path": str(plate_path),
            "plate_url": self._projection.url()(plate_path),
            "prompt": prompt,
            "method": plate_method or "agent_task_background_plate",
            "background_match": background_match or {},
            "api_calls": 1 if plate_method == "agent_gemini_empty_surface" else 0,
            "sha256": self._projection.digest()(plate_path),
            "created_at": self._projection.now()(),
        }
        orchestration["background_plate_error"] = ""
        task["background_set_id"] = set_id
        return set_id

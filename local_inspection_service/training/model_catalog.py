"""Training model specifications assembled from run artifacts and explicit record ports."""
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .task_lookup import TaskFinder

Record = dict[str, Any]


@dataclass(frozen=True)
class TrainingFiles:
    roots: Callable[[], Sequence[Path]]
    finder: Callable[[], TaskFinder]
    task_path: Callable[[], Callable[[str], Path]]
    read: Callable[[Path], Any]
    output: Callable[[], Path]
    resolve: Callable[[], Callable[[str], Path]]


@dataclass(frozen=True)
class TrainingAccessories:
    uid: Callable[[Record], str]
    serialize: Callable[[Record], Record]
    uses_ocr: Callable[[], Callable[[Record], bool]]
    profiles: Callable[[], Callable[[list[Record], dict[str, str]], Record]]


@dataclass(frozen=True)
class TrainingPipeline:
    tasks: Callable[[], list[Record]]
    link: Callable[[], Callable[[str, list[Record]], dict[str, str]]]
    method: Callable[[], Callable[[str], str]]


@dataclass(frozen=True)
class TrainingAccess:
    current_user: Callable[[], Record | None]
    visible: Callable[[Record, Record], bool]
    audit: Callable[[], Callable[[Record, Path], Record]]


class TrainedModelCatalog:
    def __init__(self, config: Callable[[], Record], files: TrainingFiles,
                 accessories: TrainingAccessories, pipeline: TrainingPipeline, access: TrainingAccess,
                 rules: Callable[[Record, Record], Record]):
        self.config, self.files, self.accessories = config, files, accessories
        self.pipeline, self.access, self.rules = pipeline, access, rules

    def list_trained_model_specs(self, config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        models = []
        config = config or self.config()
        accessories_by_id = {
            str(item.get("id") or self.accessories.uid(item)): self.accessories.serialize(item)
            for item in config.get("accessories", [])
        }
        run_dirs: list[Path] = []
        for runs_dir in self.files.roots():
            if runs_dir.exists():
                run_dirs.extend([p for p in runs_dir.iterdir() if p.is_dir()])
        find_training_task_for_path = self.files.finder()
        pipeline_tasks = self.pipeline.tasks()
        pipeline_tasks_by_id = {str(item.get("id") or ""): item for item in pipeline_tasks}
        for run_dir in sorted(run_dirs, key=lambda p: p.stat().st_mtime, reverse=True):
            task = find_training_task_for_path(self.files.task_path()(run_dir.name)) or {}
            if task.get("action") != "train_model":
                continue
            weights = run_dir / "weights" / "best.pt"
            meta_path = run_dir / "library_metadata.json"
            meta = self.files.read(meta_path)
            if not isinstance(meta, dict):
                meta = {}
            manifest_path = self.files.output() / "training_datasets" / run_dir.name / "manifest.json"
            if task.get("manifest_path"):
                manifest_path = self.files.resolve()(task["manifest_path"])
            manifest = self.files.read(manifest_path)
            if not isinstance(manifest, dict):
                manifest = {}
            audit = self.access.audit()({**manifest, **task}, run_dir)
            raw_class_names = [str(name or f"class_{idx}") for idx, name in enumerate(manifest.get("class_names") or ["accessory"])]
            task_id_value = str(task.get("task_id") or manifest.get("task_id") or run_dir.name)
            pipeline_link = self.pipeline.link()(run_dir.name, pipeline_tasks)
            pipeline_task_id = str(
                task.get("pipeline_task_id") or manifest.get("pipeline_task_id") or meta.get("pipeline_task_id") or pipeline_link.get("pipeline_task_id") or ""
            )
            pipeline_task_name = str(
                task.get("pipeline_task_name")
                or manifest.get("pipeline_task_name")
                or meta.get("pipeline_task_name")
                or pipeline_link.get("pipeline_task_name")
                or ""
            )
            variant = str(task.get("model_variant") or task.get("mode") or manifest.get("model_variant") or manifest.get("mode") or "yolo")
            uses_ocr = variant == "yolo_ocr"
            selected_accessory_ids = list(task.get("selected_accessory_ids") or manifest.get("selected_accessory_ids") or [])
            required_accessory_counts = {
                str(k): max(0, int(v))
                for k, v in (task.get("required_accessory_counts") or manifest.get("required_accessory_counts") or {}).items()
            }
            if not required_accessory_counts:
                required_accessory_counts = {str(item_id): 1 for item_id in selected_accessory_ids}
            accessory_class_map = {
                int(k): str(v)
                for k, v in (task.get("accessory_class_map") or manifest.get("accessory_class_map") or {}).items()
                if str(k).lstrip("-").isdigit()
            }
            if not accessory_class_map:
                accessory_class_map = {idx: str(item_id) for idx, item_id in enumerate(selected_accessory_ids)}
            accessory_names = [
                str((accessories_by_id.get(str(item_id)) or {}).get("name") or (accessories_by_id.get(str(item_id)) or {}).get("label") or item_id)
                for item_id in selected_accessory_ids
            ]
            if len(accessory_names) != len(raw_class_names):
                accessory_names = raw_class_names
            class_names = {idx: accessory_names[idx] if idx < len(accessory_names) else raw_class_names[idx] for idx in range(len(raw_class_names))}
            accessory_labels = {
                str(accessory_id): class_names.get(model_cls_id, str(accessory_id))
                for model_cls_id, accessory_id in accessory_class_map.items()
            }
            ocr_accessory_ids = {
                str(item_id)
                for item_id in (task.get("ocr_accessory_ids") or manifest.get("ocr_accessory_ids") or [])
            }
            if not ocr_accessory_ids:
                ocr_accessory_ids = {
                    str(item_id)
                    for item_id in selected_accessory_ids
                    if self.accessories.uses_ocr()(accessories_by_id.get(str(item_id), {}))
                }
            if not ocr_accessory_ids and pipeline_task_id:
                pipeline_task = pipeline_tasks_by_id.get(pipeline_task_id)
                if pipeline_task and self.pipeline.method()(str(pipeline_task.get("detection_method") or "")) == "yolo_ocr":
                    ocr_accessory_ids = {
                        str(item_id)
                        for item_id in selected_accessory_ids
                        if self.accessories.uses_ocr()(accessories_by_id.get(str(item_id), {}))
                    }
                    if not ocr_accessory_ids and selected_accessory_ids:
                        ocr_accessory_ids = {str(selected_accessory_ids[0])}
            ocr_model_class_ids = sorted(
                model_cls_id for model_cls_id, accessory_id in accessory_class_map.items() if str(accessory_id) in ocr_accessory_ids
            )
            available_variants = [variant if variant in {"yolo", "yolo_ocr"} else "yolo"]
            pipeline_task_requires_ocr = False
            if pipeline_task_id:
                pipeline_task = pipeline_tasks_by_id.get(pipeline_task_id)
                pipeline_task_requires_ocr = bool(
                    pipeline_task and self.pipeline.method()(str(pipeline_task.get("detection_method") or "")) == "yolo_ocr"
                )
            if ocr_accessory_ids or pipeline_task_requires_ocr:
                sibling_variant = "yolo" if available_variants[0] == "yolo_ocr" else "yolo_ocr"
                available_variants.append(sibling_variant)
            for spec_variant in available_variants:
                spec_uses_ocr = spec_variant == "yolo_ocr"
                spec_ocr_accessory_ids = sorted(ocr_accessory_ids) if spec_uses_ocr else []
                spec_ocr_model_class_ids = ocr_model_class_ids if spec_uses_ocr else []
                spec_payload = {
                        "id": f"trained_{run_dir.name}__{spec_variant}",
                        "run_id": run_dir.name,
                        "run_dir": str(run_dir),
                        "task_id": task_id_value,
                        "pipeline_task_id": pipeline_task_id,
                        "pipeline_task_name": pipeline_task_name,
                        "variant": spec_variant,
                        "label": meta.get("display_name") or f"{run_dir.name} · {spec_variant.upper()}",
                        "description": "由训练库生成的任务模型。",
                        "note": meta.get("note") or "",
                        "path": weights,
                        "artifact_path": str(weights),
                        "metadata_path": str(manifest_path),
                        "uses_ocr": spec_uses_ocr,
                        "is_specialized": True,
                        "selected_accessory_ids": selected_accessory_ids,
                        "required_accessory_counts": required_accessory_counts,
                        "accessory_class_map": {str(k): v for k, v in accessory_class_map.items()},
                        "class_accessory_map": {v: k for k, v in accessory_class_map.items()},
                        "ocr_accessory_ids": spec_ocr_accessory_ids,
                        "ocr_model_class_ids": spec_ocr_model_class_ids,
                        "ocr_accessory_profiles": self.accessories.profiles()(
                            [accessories_by_id.get(str(item_id), {}) for item_id in spec_ocr_accessory_ids],
                            accessory_labels,
                        ) if spec_uses_ocr else {},
                        "accessory_names": accessory_names,
                        "accessory_labels": accessory_labels,
                        "model_class_names": class_names,
                        "model_to_business_class": {idx: idx for idx in class_names},
                        "model_to_accessory_id": accessory_class_map,
                        "rule_required_accessory_ids": list(required_accessory_counts.keys()),
                        "rule_required_classes": list(class_names.keys()),
                        "rule_min_counts": {str(idx): 1 for idx in class_names},
                        "rule_class_labels": class_names,
                        "created_at": audit["created_at"],
                        "updated_at": audit["updated_at"],
                        "owner_user_id": audit["owner_user_id"],
                        "owner_username": audit["owner_username"],
                    }
                models.append(self.rules(spec_payload, config))
        user = self.access.current_user()
        if user:
            models = [spec for spec in models if self.access.visible(spec, user)]
        return models

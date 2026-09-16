"""Analysis image-processing projections; no worker or provider execution."""
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Record = dict[str, Any]


@dataclass(frozen=True)
class ProcessingDependencies:
    safe_id: Callable[[Any], str]
    bounded_text: Callable[[Any, int], str]
    sanitize_paths: Callable[[Any], Any]
    output_url: Callable[[Path], str]
    resolve_path: Callable[[Any], Path]
    load_json: Callable[[Path], Any]
    current_cache: Callable[[], dict[str, Any] | None]
    created_at: Callable[[Record], int]
    updated_at: Callable[[Record], int]
    auto_state: Callable[[str], Record]


def image_processing_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in {"labeling", "processing", "running", "queued", "pending"}:
        return "running" if status in {"labeling", "processing"} else status
    if status in {"trainable", "ready", "completed", "complete", "ok", "success"}:
        return "completed"
    if status in {"rejected", "skipped"}:
        return "rejected"
    if status in {"failed", "error"}:
        return "failed"
    return status or "pending"


def image_processing_type_label(value: str) -> str:
    labels = {
        "source_photo": "原始照片",
        "ai_detection_overlay": "AI 检测图",
        "auto_optimize_sample": "自动优化样本",
        "ai_mask": "AI mask",
        "ai_mask_box_overlay": "AI mask 框选图",
        "roi_crop": "ROI 裁剪",
        "ai_roi_mask": "AI ROI mask",
        "traditional_roi_mask": "传统 ROI mask",
        "transparent_sprite": "透明 sprite",
        "clean_sprite": "标准 sprite",
        "dataset_image": "训练图片",
        "dataset_label": "训练标签",
    }
    return labels.get(value, value)


def image_processing_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(item.get("status") or "pending") for item in items if isinstance(item, dict))
    running = counts.get("queued", 0) + counts.get("pending", 0) + counts.get("running", 0)
    return {
        "total": len(items),
        "queued": counts.get("queued", 0) + counts.get("pending", 0),
        "running": counts.get("running", 0),
        "completed": counts.get("completed", 0),
        "rejected": counts.get("rejected", 0),
        "failed": counts.get("failed", 0),
        "active": running,
        "by_status": dict(counts),
    }


class ProcessingProjection:
    def __init__(self, dependencies: ProcessingDependencies):
        self.dependencies = dependencies

    def image_processing_public_url(self, path_or_url: Any) -> str:
        value = str(path_or_url or "").strip()
        if not value:
            return ""
        if value.startswith(("http://", "https://", "/")):
            return value
        return self.dependencies.output_url(self.dependencies.resolve_path(value))

    def image_processing_item(self,
        *,
        item_id: str,
        item_type: str,
        status: Any,
        label: str = "",
        url: Any = "",
        created_at: Any = 0,
        updated_at: Any = 0,
        reason: str = "",
        metrics: dict[str, Any] | None = None,
        sample_id: str = "",
        accessory_id: str = "",
        record_id: str = "",
        task_id: str = "",
    ) -> dict[str, Any]:
        public_status = image_processing_status(status)
        return {
            "id": self.dependencies.safe_id(item_id),
            "type": item_type,
            "type_label": image_processing_type_label(item_type),
            "status": public_status,
            "label": self.dependencies.bounded_text(label or image_processing_type_label(item_type), 120),
            "url": self.image_processing_public_url(url),
            "created_at": int(created_at or 0),
            "updated_at": int(updated_at or created_at or 0),
            "reason": self.dependencies.bounded_text(reason or "", 240),
            "metrics": self.dependencies.sanitize_paths(metrics or {}),
            "sample_id": str(sample_id or ""),
            "accessory_id": str(accessory_id or ""),
            "record_id": str(record_id or ""),
            "task_id": str(task_id or ""),
        }

    def merge_image_processing_items(self, existing: list[dict[str, Any]], updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for item in existing + updates:
            if not isinstance(item, dict):
                continue
            item_id = self.dependencies.safe_id(item.get("id") or f"{item.get('type')}_{len(merged)}")
            current = dict(merged.get(item_id) or {})
            current.update(item)
            current["id"] = item_id
            merged[item_id] = current
        return sorted(
            merged.values(),
            key=lambda item: (int(item.get("created_at") or 0), str(item.get("type") or ""), str(item.get("id") or "")),
        )

    def auto_optimize_dataset_processing_items_for_sample(self,
        state: dict[str, Any],
        sample: dict[str, Any],
        *,
        record_id: str,
        task_id: str,
    ) -> list[dict[str, Any]]:
        sample_id = str(sample.get("sample_id") or "")
        items: list[dict[str, Any]] = []
        read_cache = self.dependencies.current_cache()
        for dataset in state.get("datasets") or []:
            if not isinstance(dataset, dict):
                continue
            manifest_path = self.dependencies.resolve_path(dataset.get("manifest_path") or "")
            manifest_key = f"dataset_manifest:{manifest_path}"
            if read_cache is not None and manifest_key in read_cache:
                manifest = read_cache[manifest_key]
            else:
                manifest = self.dependencies.load_json(manifest_path)
                if not isinstance(manifest, dict):
                    manifest = {}
                if read_cache is not None:
                    read_cache[manifest_key] = manifest
            for idx, dataset_sample in enumerate(manifest.get("samples") or []):
                if not isinstance(dataset_sample, dict):
                    continue
                if str(dataset_sample.get("source_sample_id") or "") != sample_id and str(dataset_sample.get("source_record_id") or "") != record_id:
                    continue
                base_id = f"{dataset.get('id') or 'dataset'}_{sample_id}_{idx}"
                created_at = dataset.get("created_at") or sample.get("label_completed_at") or sample.get("created_at")
                items.append(
                    self.image_processing_item(
                        item_id=f"{base_id}_image",
                        item_type="dataset_image",
                        status="completed",
                        label=str(dataset.get("display_name") or "训练图片"),
                        url=dataset_sample.get("image"),
                        created_at=created_at,
                        updated_at=created_at,
                        metrics={"split": dataset_sample.get("split"), "label_count": dataset_sample.get("label_count")},
                        sample_id=sample_id,
                        record_id=record_id,
                        task_id=task_id,
                    )
                )
                items.append(
                    self.image_processing_item(
                        item_id=f"{base_id}_label",
                        item_type="dataset_label",
                        status="completed",
                        label="YOLO bbox 标签",
                        url="",
                        created_at=created_at,
                        updated_at=created_at,
                        metrics={"split": dataset_sample.get("split"), "label_count": dataset_sample.get("label_count")},
                        sample_id=sample_id,
                        record_id=record_id,
                        task_id=task_id,
                    )
                )
        return items

    def auto_optimize_sample_processing_items(self, state: dict[str, Any], sample: dict[str, Any], record: dict[str, Any]) -> list[dict[str, Any]]:
        task_id = str(state.get("task_id") or sample.get("task_id") or (record.get("task") or {}).get("id") or "")
        record_id = str(record.get("record_id") or sample.get("record_id") or "")
        sample_id = str(sample.get("sample_id") or "")
        created_at = sample.get("created_at") or self.dependencies.created_at(record)
        label_status = sample.get("label_status") or "pending"
        items = [
            self.image_processing_item(
                item_id=f"{sample_id}_auto_optimize_sample",
                item_type="auto_optimize_sample",
                status=label_status,
                label=f"候选配件 {len(sample.get('candidate_accessories') or [])}",
                url=(sample.get("source_image") or {}).get("url") or (sample.get("source_image") or {}).get("path"),
                created_at=created_at,
                updated_at=sample.get("label_completed_at") or sample.get("label_started_at") or created_at,
                reason=sample.get("label_reject_reason") or "",
                metrics={"candidate_count": len(sample.get("candidate_accessories") or [])},
                sample_id=sample_id,
                record_id=record_id,
                task_id=task_id,
            )
        ]
        label_artifacts = sample.get("label_artifacts") if isinstance(sample.get("label_artifacts"), dict) else {}
        if label_artifacts.get("multi_color"):
            common = {
                "created_at": sample.get("label_started_at") or created_at,
                "updated_at": sample.get("label_completed_at") or sample.get("label_started_at") or created_at,
                "sample_id": sample_id,
                "record_id": record_id,
                "task_id": task_id,
            }
            candidate_count = len(sample.get("candidate_accessories") or [])
            labels = [item for item in sample.get("labels") or [] if isinstance(item, dict)]
            failures = [item for item in sample.get("label_failures") or [] if isinstance(item, dict)]
            status = "completed" if labels and not failures else "rejected"
            reason = "" if status == "completed" else sample.get("label_reject_reason") or (failures[0].get("reason") if failures else "no_valid_label")
            items.append(
                self.image_processing_item(
                    item_id=f"{sample_id}_multicolor_ai_mask",
                    item_type="ai_mask",
                    status="completed" if label_artifacts.get("color_mask_url") else "failed",
                    label="多色 AI mask",
                    url=label_artifacts.get("color_mask_url"),
                    reason="" if label_artifacts.get("color_mask_url") else "color_mask_missing",
                    metrics={
                        "multi_color": True,
                        "candidate_count": candidate_count,
                        "passed_count": len(labels),
                        "failed_count": len(failures),
                        "class_check": label_artifacts.get("class_check") or {},
                    },
                    **common,
                )
            )
            review_meta = label_artifacts.get("review_meta") if isinstance(label_artifacts.get("review_meta"), dict) else {}
            items.append(
                self.image_processing_item(
                    item_id=f"{sample_id}_review_ai_mask_box_overlay",
                    item_type="ai_mask_box_overlay",
                    status=status,
                    label="AI mask bbox 复核图",
                    url=label_artifacts.get("review_overlay_url"),
                    reason=reason,
                    metrics={
                        "review_unit": True,
                        "multi_color": True,
                        "candidate_count": candidate_count,
                        "passed_count": len(labels),
                        "failed_count": len(failures),
                        "class_check": label_artifacts.get("class_check") or {},
                        **review_meta,
                    },
                    **common,
                )
            )
            for label in labels:
                sprite = label.get("sprite") if isinstance(label.get("sprite"), dict) else {}
                if not sprite.get("url") and not sprite.get("path"):
                    continue
                accessory_id = str(label.get("accessory_id") or sprite.get("accessory_id") or "")
                item_base = f"{sample_id}_{accessory_id or self.dependencies.safe_id(str(label.get('label') or 'sprite'))}"
                items.append(
                    self.image_processing_item(
                        item_id=f"{item_base}_transparent_sprite",
                        item_type="transparent_sprite",
                        status=sprite.get("status") or "completed",
                        label=str(label.get("label") or accessory_id or "透明 sprite"),
                        url=sprite.get("url") or sprite.get("path"),
                        reason="" if sprite.get("status") != "failed" else "sprite_write_failed",
                        metrics={"bbox_xyxy": label.get("bbox_xyxy"), "source": "ai_mask_sprite_pool"},
                        accessory_id=accessory_id,
                        **common,
                    )
                )
            items.extend(self.auto_optimize_dataset_processing_items_for_sample(state, sample, record_id=record_id, task_id=task_id))
            return items
        for label in sample.get("labels") or []:
            if not isinstance(label, dict):
                continue
            accessory_id = str(label.get("accessory_id") or "")
            label_name = str(label.get("label") or accessory_id or "目标配件")
            mask_meta = label.get("mask_meta") if isinstance(label.get("mask_meta"), dict) else {}
            artifacts = mask_meta.get("processing_artifacts") if isinstance(mask_meta.get("processing_artifacts"), dict) else {}
            compare_meta = mask_meta.get("auto_compare") if isinstance(mask_meta.get("auto_compare"), dict) else {}
            item_base = f"{sample_id}_{accessory_id or self.dependencies.safe_id(label_name)}"
            common = {
                "created_at": sample.get("label_started_at") or created_at,
                "updated_at": sample.get("label_completed_at") or sample.get("label_started_at") or created_at,
                "sample_id": sample_id,
                "record_id": record_id,
                "task_id": task_id,
                "accessory_id": accessory_id,
            }
            items.extend(
                [
                    self.image_processing_item(
                        item_id=f"{item_base}_ai_mask",
                        item_type="ai_mask",
                        status="completed",
                        label=label_name,
                        url=label.get("mask_url"),
                        metrics={
                            "bbox_xyxy": label.get("bbox_xyxy"),
                            "confidence": label.get("confidence"),
                            "latency_ms": mask_meta.get("latency_ms"),
                            "model": mask_meta.get("model"),
                        },
                        **common,
                    ),
                    self.image_processing_item(
                        item_id=f"{item_base}_ai_mask_box_overlay",
                        item_type="ai_mask_box_overlay",
                        status="completed" if artifacts.get("ai_mask_box_overlay_url") else "failed",
                        label=label_name,
                        url=artifacts.get("ai_mask_box_overlay_url"),
                        reason="" if artifacts.get("ai_mask_box_overlay_url") else "ai_mask_box_overlay_missing",
                        metrics={"bbox_xyxy": label.get("bbox_xyxy"), "confidence": label.get("confidence")},
                        **common,
                    ),
                    self.image_processing_item(
                        item_id=f"{item_base}_roi",
                        item_type="roi_crop",
                        status="completed",
                        label=label_name,
                        url=artifacts.get("source_roi_url"),
                        metrics={"bbox_xyxy": label.get("bbox_xyxy")},
                        **common,
                    ),
                    self.image_processing_item(
                        item_id=f"{item_base}_ai_roi_mask",
                        item_type="ai_roi_mask",
                        status="completed",
                        label=label_name,
                        url=artifacts.get("ai_roi_mask_url"),
                        metrics={"bbox_xyxy": label.get("bbox_xyxy")},
                        **common,
                    ),
                    self.image_processing_item(
                        item_id=f"{item_base}_traditional_roi_mask",
                        item_type="traditional_roi_mask",
                        status="completed" if artifacts.get("traditional_roi_mask_url") else "rejected",
                        label=label_name,
                        url=artifacts.get("traditional_roi_mask_url"),
                        reason="" if artifacts.get("traditional_roi_mask_url") else "traditional_mask_unavailable",
                        metrics=compare_meta,
                        **common,
                    ),
                    self.image_processing_item(
                        item_id=f"{item_base}_transparent_sprite",
                        item_type="transparent_sprite",
                        status="completed",
                        label=label_name,
                        url=artifacts.get("transparent_sprite_url"),
                        metrics={"bbox_xyxy": label.get("bbox_xyxy"), "mask_compare_score": compare_meta.get("score")},
                        **common,
                    ),
                ]
            )
        for failure in sample.get("label_failures") or []:
            if not isinstance(failure, dict):
                continue
            accessory_id = str(failure.get("accessory_id") or "")
            label_name = str(failure.get("label") or accessory_id or "目标配件")
            artifacts = failure.get("processing_artifacts") if isinstance(failure.get("processing_artifacts"), dict) else {}
            item_base = f"{sample_id}_{accessory_id or self.dependencies.safe_id(label_name)}_failure"
            failed_status = failure.get("status") or sample.get("label_status") or "failed"
            items.append(
                self.image_processing_item(
                    item_id=f"{item_base}_ai_mask",
                    item_type="ai_mask",
                    status=failed_status,
                    label=label_name,
                    url=failure.get("mask_url"),
                    created_at=sample.get("label_started_at") or created_at,
                    updated_at=sample.get("label_completed_at") or sample.get("label_started_at") or created_at,
                    reason=failure.get("reason") or "",
                    metrics={k: v for k, v in failure.items() if k not in {"mask_url", "processing_artifacts", "reason"}},
                    sample_id=sample_id,
                    record_id=record_id,
                    task_id=task_id,
                    accessory_id=accessory_id,
                )
            )
            for artifact_type, artifact_key in (
                ("ai_mask_box_overlay", "ai_mask_box_overlay_url"),
                ("roi_crop", "source_roi_url"),
                ("traditional_roi_mask", "traditional_roi_mask_url"),
                ("transparent_sprite", "transparent_sprite_url"),
            ):
                if artifacts.get(artifact_key):
                    items.append(
                        self.image_processing_item(
                            item_id=f"{item_base}_{artifact_type}",
                            item_type=artifact_type,
                            status=failed_status,
                            label=label_name,
                            url=artifacts.get(artifact_key),
                            created_at=sample.get("label_started_at") or created_at,
                            updated_at=sample.get("label_completed_at") or sample.get("label_started_at") or created_at,
                            reason=failure.get("reason") or "",
                            metrics={"score": failure.get("score")},
                            sample_id=sample_id,
                            record_id=record_id,
                            task_id=task_id,
                            accessory_id=accessory_id,
                        )
                    )
        items.extend(self.auto_optimize_dataset_processing_items_for_sample(state, sample, record_id=record_id, task_id=task_id))
        return items

    def data_analysis_image_processing_items(self, record: dict[str, Any], *, include_auto_optimize: bool = True) -> list[dict[str, Any]]:
        record_id = str(record.get("record_id") or "")
        task = record.get("task") if isinstance(record.get("task"), dict) else {}
        task_id = str(task.get("id") or "")
        created_at = self.dependencies.created_at(record)
        source = record.get("source_image") if isinstance(record.get("source_image"), dict) else {}
        result = record.get("ai_detection_result") if isinstance(record.get("ai_detection_result"), dict) else {}
        persisted_items = [
            item for item in record.get("image_processing_items") or [] if isinstance(item, dict)
        ]
        items = [
            self.image_processing_item(
                item_id=f"{record_id}_source_photo",
                item_type="source_photo",
                status="completed",
                label=source.get("filename") or "原始检测照片",
                url=source.get("url") or source.get("path"),
                created_at=created_at,
                updated_at=self.dependencies.updated_at(record),
                record_id=record_id,
                task_id=task_id,
            )
        ]
        overlay_url = result.get("annotated_url") or result.get("preview_url") or record.get("image_url")
        if overlay_url:
            items.append(
                self.image_processing_item(
                    item_id=f"{record_id}_ai_detection_overlay",
                    item_type="ai_detection_overlay",
                    status="completed",
                    label="AI 检测标注图",
                    url=overlay_url,
                    created_at=created_at,
                    updated_at=self.dependencies.updated_at(record),
                    metrics={"request_id": result.get("request_id")},
                    record_id=record_id,
                    task_id=task_id,
                )
            )
        items.extend(persisted_items)
        if include_auto_optimize and task_id:
            state = self.dependencies.auto_state(task_id)
            for sample in state.get("samples") or []:
                if not isinstance(sample, dict) or str(sample.get("record_id") or "") != record_id:
                    continue
                items.extend(self.auto_optimize_sample_processing_items(state, sample, record))
        return self.merge_image_processing_items([], items)

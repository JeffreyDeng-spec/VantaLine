"""Object sprite preprocessing without application imports."""
from typing import Any
from pathlib import Path
import cv2
import numpy as np
from .object_preprocessing_ports import ObjectSpritePolicy, ObjectSpriteSources, ObjectSpriteRuntime, ObjectSpriteCutouts, ObjectSpriteComponents, ObjectSpriteMetadata, ObjectSpriteArtifacts


class ObjectSpritePreprocessor:
    def __init__(self, policy: ObjectSpritePolicy, sources: ObjectSpriteSources, runtime: ObjectSpriteRuntime, cutouts: ObjectSpriteCutouts, components: ObjectSpriteComponents, metadata: ObjectSpriteMetadata, artifacts: ObjectSpriteArtifacts) -> None:
        self._policy = policy
        self._sources = sources
        self._runtime = runtime
        self._cutouts = cutouts
        self._components = components
        self._metadata = metadata
        self._artifacts = artifacts


    def preprocess_object_clean_sprites(self, item: dict[str, Any], allow_ai_cutout: bool = True, force: bool = False) -> bool:
        if self._policy.material()(item) == "text":
            return False
        item["material_alpha_policy"] = self._policy.alpha()(item)
        pose_jobs = [
            job
            for job in self._sources.jobs()(item)
            if Path(str(job.get("output_path", ""))).exists() and not job.get("intermediate")
        ]
        expected_pose_sprite_count = len(pose_jobs) * len(self._sources.positions())
        existing = self._policy.existing()(item)
        existing_complete = self._policy.complete()(item, existing)
        expected_existing_count = min(18, expected_pose_sprite_count) if expected_pose_sprite_count else len(existing)
        if existing and not force and existing_complete and len(existing) >= expected_existing_count:
            return False

        uid = self._runtime.identifier()(item)
        sprite_dir = self._runtime.root() / uid / "clean_sprites"
        generated: list[dict[str, Any]] = []
        rng = self._runtime.rng()(int(item.get("created_at") or self._runtime.now()()))
        physical_size = item.get("physical_size") if isinstance(item.get("physical_size"), dict) else {}
        alpha_policy = self._policy.alpha()(item)

        failed_cells: list[dict[str, Any]] = []

        def add_cutout(
            cutout: tuple[np.ndarray, np.ndarray] | None,
            source_shape: tuple[int, ...],
            method: str,
            metadata: dict[str, Any] | None = None,
        ) -> bool:
            usable = self._cutouts.usable()(cutout, source_shape)
            if not usable:
                return False
            out_path = sprite_dir / f"sprite_{len(generated) + 1:02d}.png"
            asset = self._artifacts.write()(out_path, usable[0], usable[1], metadata)
            if asset:
                asset["method"] = method
                generated.append(asset)
                return True
            return False

        pose_paths = [Path(str(job.get("output_path", ""))) for job in pose_jobs]
        for job in pose_jobs:
            pose_path = Path(str(job.get("output_path", "")))
            if not pose_path.exists():
                continue
            pose_family = str(job.get("pose_family") or "")
            pose = cv2.imread(str(pose_path), cv2.IMREAD_COLOR)
            if pose is not None:
                base_regions = self._sources.regions()(pose, padded=False)
                for idx, (x1, y1, x2, y2) in enumerate(self._sources.regions()(pose, padded=True)):
                    tile = pose[y1:y2, x1:x2].copy()
                    pose_position = self._sources.positions()[idx] if idx < len(self._sources.positions()) else str(idx)
                    local_bbox = None
                    cutout = None
                    method = "pose_collection_lightweight_cutout"
                    base_region = base_regions[idx] if idx < len(base_regions) else (x1, y1, x2, y2)
                    focus_bbox = (
                        max(0, int(base_region[0] - x1)),
                        max(0, int(base_region[1] - y1)),
                        min(tile.shape[1], int(base_region[2] - x1)),
                        min(tile.shape[0], int(base_region[3] - y1)),
                    )
                    target_center_xy = ((focus_bbox[0] + focus_bbox[2]) / 2.0, (focus_bbox[1] + focus_bbox[3]) / 2.0)
                    mask_diagnostics: dict[str, Any] = {}

                    def apply_crop_component_cleanup(
                        crop_asset: np.ndarray,
                        crop_alpha: np.ndarray,
                        bbox: tuple[int, int, int, int],
                        source_alpha: np.ndarray | None = None,
                    ) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]]:
                        source_count, source_area = self._components.summary()(source_alpha if source_alpha is not None else crop_alpha)
                        bx1, by1, _, _ = bbox
                        local_anchor = (target_center_xy[0] - bx1, target_center_xy[1] - by1)
                        cleaned_alpha, diagnostics = self._components.cleanup()(crop_asset, crop_alpha, local_anchor)
                        kept_count, kept_area = self._components.summary()(cleaned_alpha)
                        diagnostics["removed_stray_component_count"] = max(
                            int(diagnostics.get("removed_stray_component_count") or 0),
                            max(0, source_count - kept_count),
                        )
                        diagnostics["removed_stray_component_area_px"] = max(
                            int(diagnostics.get("removed_stray_component_area_px") or 0),
                            max(0, source_area - kept_area),
                        )
                        cleaned_bbox = self._components.bounds()(cleaned_alpha)
                        updated_bbox = (
                            int(bx1 + cleaned_bbox[0]),
                            int(by1 + cleaned_bbox[1]),
                            int(bx1 + cleaned_bbox[2]),
                            int(by1 + cleaned_bbox[3]),
                        )
                        mask_diagnostics.update(diagnostics)
                        return crop_asset, cleaned_alpha, updated_bbox

                    if allow_ai_cutout:
                        ai_cutout = self._cutouts.ai_bounded()(tile)
                        if ai_cutout:
                            full_alpha = np.zeros(tile.shape[:2], dtype=np.uint8)
                            bx1, by1, bx2, by2 = ai_cutout[2]
                            full_alpha[by1:by2, bx1:bx2] = ai_cutout[1]
                            focused = self._components.focus()(tile, full_alpha, focus_bbox)
                            if focused:
                                crop_asset, crop_alpha, local_bbox = apply_crop_component_cleanup(
                                    focused[0], focused[1], focused[2], full_alpha
                                )
                                cutout = (crop_asset, crop_alpha)
                                method = "pose_collection_crop_stage_alpha_cutout"
                    if cutout is None:
                        fallback_cutout = self._cutouts.green()(tile, rng)
                        if fallback_cutout:
                            full_alpha = np.zeros(tile.shape[:2], dtype=np.uint8)
                            bx1, by1, bx2, by2 = fallback_cutout[2]
                            full_alpha[by1:by2, bx1:bx2] = fallback_cutout[1]
                            focused = self._components.focus()(tile, full_alpha, focus_bbox)
                            if focused:
                                crop_asset, crop_alpha, local_bbox = apply_crop_component_cleanup(
                                    focused[0], focused[1], focused[2], full_alpha
                                )
                                cutout = (crop_asset, crop_alpha)
                                method = "pose_collection_crop_stage_alpha_fallback"
                            else:
                                crop_asset, crop_alpha, local_bbox = apply_crop_component_cleanup(
                                    fallback_cutout[0], fallback_cutout[1], fallback_cutout[2], full_alpha
                                )
                                cutout = (crop_asset, crop_alpha)
                    if cutout is None:
                        local_bbox = (0, 0, tile.shape[1], tile.shape[0])
                        cutout = (tile.copy(), np.full(tile.shape[:2], 255, dtype=np.uint8))
                        method = "pose_collection_full_cell_fallback"
                        mask_diagnostics["pose_collection_full_cell_fallback"] = True
                    if local_bbox is None:
                        local_bbox = (0, 0, tile.shape[1], tile.shape[0])
                    bx1, by1, bx2, by2 = local_bbox
                    source_bbox = [int(x1 + bx1), int(y1 + by1), int(x1 + bx2), int(y1 + by2)]
                    source_size_px = [int(source_bbox[2] - source_bbox[0]), int(source_bbox[3] - source_bbox[1])]
                    metadata = {
                        "task_id": str(job.get("task_id") or self._metadata.task_id()(item, job)),
                        "source_pose_collection_job_id": str(job.get("job_id") or ""),
                        "source_pose_collection": str(pose_path),
                        "pose_family": pose_family,
                        "source_pose_family": pose_family,
                        "pose_index": idx,
                        "pose_position": pose_position,
                        "source_position": pose_position,
                        "source_image_size_px": [int(pose.shape[1]), int(pose.shape[0])],
                        "source_image_width": int(pose.shape[1]),
                        "source_image_height": int(pose.shape[0]),
                        "source_region_bbox_xyxy": [int(x1), int(y1), int(x2), int(y2)],
                        "source_region_core_bbox_xyxy": [int(base_region[0]), int(base_region[1]), int(base_region[2]), int(base_region[3])],
                        "source_region_target_center_xy": [
                            int(round(x1 + target_center_xy[0])),
                            int(round(y1 + target_center_xy[1])),
                        ],
                        "source_object_bbox_xyxy": source_bbox,
                        "source_object_center_xy": [
                                int(round((source_bbox[0] + source_bbox[2]) / 2)),
                                int(round((source_bbox[1] + source_bbox[3]) / 2)),
                        ],
                        "source_object_size_px": source_size_px,
                        "physical_size_mm": physical_size,
                        "material_alpha_policy": alpha_policy,
                    }
                    metadata.update(mask_diagnostics)
                    metadata.update(self._metadata.footprint()(pose_family, source_size_px, physical_size))
                    added_cutout = add_cutout(cutout, tile.shape, method, metadata)
                    if not added_cutout:
                        full_source_bbox = [int(x1), int(y1), int(x2), int(y2)]
                        full_source_size_px = [int(x2 - x1), int(y2 - y1)]
                        fallback_metadata = dict(metadata)
                        fallback_metadata.update(
                            {
                                "source_object_bbox_xyxy": full_source_bbox,
                                "source_object_center_xy": [
                                    int(round((full_source_bbox[0] + full_source_bbox[2]) / 2)),
                                    int(round((full_source_bbox[1] + full_source_bbox[3]) / 2)),
                                ],
                                "source_object_size_px": full_source_size_px,
                                "pose_collection_full_cell_fallback": True,
                                "pose_collection_failed_cutout_method": method,
                            }
                        )
                        fallback_metadata.update(self._metadata.footprint()(pose_family, full_source_size_px, physical_size))
                        out_path = sprite_dir / f"sprite_{len(generated) + 1:02d}.png"
                        fallback_asset = self._artifacts.write()(
                            out_path,
                            tile.copy(),
                            np.full(tile.shape[:2], 255, dtype=np.uint8),
                            fallback_metadata,
                        )
                        if fallback_asset:
                            fallback_asset["method"] = "pose_collection_full_cell_fallback"
                            generated.append(fallback_asset)
                            added_cutout = True
                    if not added_cutout:
                        failed_cells.append(
                            {
                                "pose_family": pose_family,
                                "source_pose_family": pose_family,
                                "pose_index": idx,
                                "pose_position": metadata["pose_position"],
                                "source_position": metadata["source_position"],
                                "source_region_bbox_xyxy": metadata["source_region_bbox_xyxy"],
                                "source_object_bbox_xyxy": source_bbox,
                                "source_object_size_px": source_size_px,
                                "reason": "no usable object cutout",
                            }
                        )

        if not generated and existing:
            for asset_meta in existing[:18]:
                path = Path(str(asset_meta.get("path", "")))
                image_any = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
                if image_any is None or image_any.ndim != 3 or image_any.shape[2] < 4:
                    continue
                alpha = image_any[:, :, 3]
                if int((alpha > 8).sum()) < 240:
                    continue
                bbox = self._components.bounds()(alpha)
                source_size_px = [max(1, int(bbox[2] - bbox[0])), max(1, int(bbox[3] - bbox[1]))]
                pose_family = str(asset_meta.get("source_pose_family") or asset_meta.get("pose_family") or "")
                metadata = dict(asset_meta)
                metadata.update(
                    {
                        "task_id": str(asset_meta.get("task_id") or "legacy_clean_sprite"),
                        "source_pose_collection_job_id": str(asset_meta.get("source_pose_collection_job_id") or "legacy_clean_sprite"),
                        "pose_family": pose_family or ("upright" if self._metadata.top_view()("", source_size_px) else "lying"),
                        "source_pose_family": pose_family or ("upright" if self._metadata.top_view()("", source_size_px) else "lying"),
                        "pose_position": str(asset_meta.get("pose_position") or asset_meta.get("source_position") or "center"),
                        "source_position": str(asset_meta.get("source_position") or asset_meta.get("pose_position") or "center"),
                        "source_image_size_px": [int(image_any.shape[1]), int(image_any.shape[0])],
                        "source_image_width": int(image_any.shape[1]),
                        "source_image_height": int(image_any.shape[0]),
                        "source_region_bbox_xyxy": asset_meta.get("source_region_bbox_xyxy") or bbox,
                        "source_object_bbox_xyxy": asset_meta.get("source_object_bbox_xyxy") or bbox,
                        "source_object_center_xy": asset_meta.get("source_object_center_xy")
                        or [int(round((bbox[0] + bbox[2]) / 2)), int(round((bbox[1] + bbox[3]) / 2))],
                        "source_object_size_px": asset_meta.get("source_object_size_px") or source_size_px,
                        "physical_size_mm": physical_size,
                        "material_alpha_policy": alpha_policy,
                        "legacy_sprite_policy_rebuild_source_path": str(path),
                    }
                )
                metadata.update(self._metadata.footprint()(metadata["source_pose_family"], metadata["source_object_size_px"], physical_size))
                add_cutout((image_any[:, :, :3].copy(), alpha.copy()), image_any.shape, "legacy_clean_sprite_policy_rebuild", metadata)

        if not generated:
            for path in self._sources.images()(item):
                if path in pose_paths:
                    continue
                image_any = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
                if image_any is not None and image_any.ndim == 3 and image_any.shape[2] >= 4:
                    for cutout in self._components.cutouts()(image_any):
                        add_cutout(cutout, image_any.shape, "source_png_alpha", {"physical_size_mm": physical_size, "material_alpha_policy": alpha_policy})
                if generated:
                    break
                image = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if image is None:
                    continue
                if allow_ai_cutout:
                    add_cutout(self._cutouts.ai_plain()(image), image.shape, "source_one_time_ai_cutout", {"physical_size_mm": physical_size, "material_alpha_policy": alpha_policy})
                if not generated:
                    add_cutout(self._cutouts.lightweight()(image, rng), image.shape, "source_lightweight_cutout", {"physical_size_mm": physical_size, "material_alpha_policy": alpha_policy})
                if generated:
                    break

        if not generated:
            for path in self._sources.images()(item):
                if path in pose_paths:
                    continue
                image = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if image is None:
                    continue
                full_mask = np.full(image.shape[:2], 255, dtype=np.uint8)
                metadata = {
                    "physical_size_mm": physical_size,
                    "material_alpha_policy": alpha_policy,
                    "source_path": str(path),
                    "source_image_size_px": [int(image.shape[1]), int(image.shape[0])],
                    "source_image_width": int(image.shape[1]),
                    "source_image_height": int(image.shape[0]),
                    "source_region_bbox_xyxy": [0, 0, int(image.shape[1]), int(image.shape[0])],
                    "source_object_bbox_xyxy": [0, 0, int(image.shape[1]), int(image.shape[0])],
                    "source_object_center_xy": [int(image.shape[1] // 2), int(image.shape[0] // 2)],
                    "source_object_size_px": [int(image.shape[1]), int(image.shape[0])],
                    "pose_family": "lying",
                    "source_pose_family": "lying",
                    "pose_position": "center",
                    "source_position": "center",
                    "task_id": "source_full_image_fallback",
                    "source_pose_collection_job_id": "source_full_image_fallback",
                }
                out_path = sprite_dir / f"sprite_{len(generated) + 1:02d}.png"
                asset = self._artifacts.write()(out_path, image.copy(), full_mask, metadata)
                if asset:
                    asset["method"] = "source_full_image_fallback"
                    generated.append(asset)
                    break

        if not generated:
            return False

        retained = [
            asset
            for asset in item.get("normalized_assets", [])
            if asset.get("kind") != "clean_object_sprite"
        ]
        generated = generated[:18]
        self._metadata.normalize()(generated)
        self._metadata.scale()(generated, physical_size)
        self._metadata.laying()(generated)
        item["normalized_assets"] = retained + generated
        expected_pose_sprite_count = len(pose_jobs) * len(self._sources.positions())
        expected_clean_count = min(18, expected_pose_sprite_count) if expected_pose_sprite_count else len(generated)
        metadata_complete = self._policy.complete()(item, generated)
        item["clean_sprite_status"] = "ready" if (not expected_clean_count or len(generated) >= expected_clean_count) and not failed_cells and metadata_complete else "partial"
        item["clean_sprite_count"] = len(generated)
        item["clean_sprite_expected_count"] = expected_clean_count
        item["clean_sprite_failed_cells"] = failed_cells
        item["clean_sprite_preprocessed_at"] = int(self._runtime.now()())
        if failed_cells:
            item["preprocess"] = f"系统已预处理 {len(generated)}/{item['clean_sprite_expected_count']} 个无背景单体素材；失败格子已记录。"
        elif item["clean_sprite_status"] != "ready":
            item["preprocess"] = f"系统已预处理 {len(generated)}/{item['clean_sprite_expected_count']} 个无背景单体素材；元数据未完整，未标记 ready。"
        else:
            item["preprocess"] = "系统已预处理无背景单体素材，并记录原图坐标与物理尺寸；训练预览直接复用。"
        return True

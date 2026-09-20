"""Photo-highlight sprite coordination with explicit capabilities."""
from pathlib import Path
from typing import Any
import cv2
from .photo_highlight_builder_ports import PhotoBuildPolicy, PhotoBuildRuntime, PhotoBuildMasks, PhotoBuildModelPolicy, PhotoBuildPublication, PhotoBuildArtifacts, PoseSpriteMetadata, PoseImageProvider


class PhotoHighlightSpriteBuilder:
    def __init__(self, policy: PhotoBuildPolicy, runtime: PhotoBuildRuntime, masks: PhotoBuildMasks, model: PhotoBuildModelPolicy, publication: PhotoBuildPublication, artifacts: PhotoBuildArtifacts, metadata: PoseSpriteMetadata) -> None:
        self._policy = policy
        self._runtime = runtime
        self._masks = masks
        self._model = model
        self._publication = publication
        self._artifacts = artifacts
        self._metadata = metadata


    def build_clean_sprites_from_photo_highlight_masks(self,
        task: dict[str, Any],
        item: dict[str, Any],
        provider: PoseImageProvider,
        model: str,
        *,
        force: bool = False,
    ) -> tuple[bool, str]:
        if self._policy.material()(item) == "text":
            return True, ""
        source_paths = self._policy.sources()(item)
        if len(source_paths) < self._policy.minimum():
            return False, f"配件 {item.get('name') or self._runtime.identifier()(item)} 至少需要 {self._policy.minimum()} 张不同角度实拍图"
        if not force and self._policy.ready()(item, source_paths):
            return True, ""
        item["material_alpha_policy"] = self._policy.alpha()(item)
        physical_size = item.get("physical_size") if isinstance(item.get("physical_size"), dict) else {}
        alpha_policy = self._policy.alpha()(item)
        uid = self._runtime.identifier()(item)
        owner_id = str(task.get("owner_user_id") or "")
        sprite_dir = self._runtime.root() / uid / "clean_sprites"
        artifact_dir = self._runtime.output()("photo_highlight_masks", owner_id) / self._runtime.safe_id()(str(task.get("id") or "task")) / self._runtime.safe_id()(uid)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        generated: list[dict[str, Any]] = []
        failures: list[str] = []
        prompt = self._masks.prompt()(item)
        for ordinal, source_path in enumerate(source_paths, start=1):
            source_record_id = self._publication.sanitize()(
                f"pipeline_{task.get('id') or 'task'}_{uid}_{ordinal:02d}_{source_path.stem}"
            )

            def publish_photo_highlight_items(updates: list[dict[str, Any]]) -> None:
                try:
                    self._publication.publish()(
                        record_id=source_record_id,
                        task=task,
                        source_path=source_path,
                        accessory=item,
                        items=updates,
                    )
                except Exception:
                    pass

            source_started_at = int(self._runtime.now()())
            publish_photo_highlight_items(
                [
                    self._publication.item()(
                        item_id=f"{source_record_id}_source_photo",
                        item_type="source_photo",
                        status="completed",
                        label=str(item.get("name") or self._runtime.identifier()(item) or source_path.name),
                        url=str(source_path),
                        created_at=source_started_at,
                        updated_at=source_started_at,
                        metrics={"ordinal": ordinal, "source_filename": source_path.name},
                        record_id=source_record_id,
                        task_id=str(task.get("id") or ""),
                        accessory_id=uid,
                    ),
                    self._publication.item()(
                        item_id=f"{source_record_id}_ai_mask",
                        item_type="ai_mask",
                        status="queued",
                        label=str(item.get("name") or self._runtime.identifier()(item) or "AI mask"),
                        created_at=source_started_at,
                        updated_at=source_started_at,
                        record_id=source_record_id,
                        task_id=str(task.get("id") or ""),
                        accessory_id=uid,
                    ),
                ]
            )
            image_bgr = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
            if image_bgr is None:
                failures.append(f"{source_path.name}: source_unreadable")
                publish_photo_highlight_items(
                    [
                        self._publication.item()(
                            item_id=f"{source_record_id}_source_photo",
                            item_type="source_photo",
                            status="failed",
                            label=str(item.get("name") or self._runtime.identifier()(item) or source_path.name),
                            url=str(source_path),
                            created_at=source_started_at,
                            updated_at=int(self._runtime.now()()),
                            reason="source_unreadable",
                            record_id=source_record_id,
                            task_id=str(task.get("id") or ""),
                            accessory_id=uid,
                        )
                    ]
                )
                continue
            input_payload = self._masks.input()(image_bgr)
            if input_payload is None:
                failures.append(f"{source_path.name}: input_encode_failed")
                publish_photo_highlight_items(
                    [
                        self._publication.item()(
                            item_id=f"{source_record_id}_ai_mask",
                            item_type="ai_mask",
                            status="failed",
                            label=str(item.get("name") or self._runtime.identifier()(item) or "AI mask"),
                            created_at=source_started_at,
                            updated_at=int(self._runtime.now()()),
                            reason="input_encode_failed",
                            record_id=source_record_id,
                            task_id=str(task.get("id") or ""),
                            accessory_id=uid,
                        )
                    ]
                )
                continue
            ai_bgr, data_url, scale_x, scale_y = input_payload
            input_h, input_w = ai_bgr.shape[:2]
            user_content = [
                {"type": "text", "text": f"Input image dimensions for this segmentation request: {input_w}x{input_h}. Return the same aspect ratio."},
                {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
            ]
            orig_h, orig_w = image_bgr.shape[:2]
            selected: dict[str, Any] | None = None
            best_failed: dict[str, Any] | None = None
            source_attempt_failures: list[str] = []
            publish_photo_highlight_items(
                [
                    self._publication.item()(
                        item_id=f"{source_record_id}_ai_mask",
                        item_type="ai_mask",
                        status="running",
                        label=str(item.get("name") or self._runtime.identifier()(item) or "AI mask"),
                        created_at=source_started_at,
                        updated_at=int(self._runtime.now()()),
                        metrics={"max_attempts": self._model.attempts(), "model": str(model or "")},
                        record_id=source_record_id,
                        task_id=str(task.get("id") or ""),
                        accessory_id=uid,
                    )
                ]
            )
            for attempt in range(1, self._model.attempts() + 1):
                try:
                    result = provider.generate_image(prompt, user_content, model=model)
                except self._model.error() as exc:
                    source_attempt_failures.append(f"attempt {attempt}: {self._runtime.bounded()(str(exc), 120)}")
                    continue
                attempt_suffix = "" if self._model.attempts() <= 1 else f"_attempt{attempt:02d}"
                mask_path = artifact_dir / f"{ordinal:02d}_{self._runtime.safe_id()(source_path.stem)}_highlight{attempt_suffix}.png"
                mask_path.write_bytes(result["bytes"])
                mask_bgr = cv2.imread(str(mask_path), cv2.IMREAD_COLOR)
                if mask_bgr is None:
                    source_attempt_failures.append(f"attempt {attempt}: generated_mask_unreadable")
                    publish_photo_highlight_items(
                        [
                            self._publication.item()(
                                item_id=f"{source_record_id}_ai_mask",
                                item_type="ai_mask",
                                status="failed",
                                label=str(item.get("name") or self._runtime.identifier()(item) or "AI mask"),
                                url=str(mask_path),
                                created_at=source_started_at,
                                updated_at=int(self._runtime.now()()),
                                reason="generated_mask_unreadable",
                                metrics={"attempt": attempt},
                                record_id=source_record_id,
                                task_id=str(task.get("id") or ""),
                                accessory_id=uid,
                            )
                        ]
                    )
                    continue
                if mask_bgr.shape[1] != input_w or mask_bgr.shape[0] != input_h:
                    mask_bgr = cv2.resize(mask_bgr, (input_w, input_h), interpolation=cv2.INTER_NEAREST)
                    resized_mask_path = mask_path.with_name(mask_path.stem + "_resized.png")
                    cv2.imwrite(str(resized_mask_path), mask_bgr)
                    mask_path = resized_mask_path
                ai_mask, mask_meta = self._masks.decode()(mask_bgr)
                if not mask_meta.get("ok"):
                    source_attempt_failures.append(f"attempt {attempt}: {mask_meta.get('reason') or 'mask_decode_failed'}")
                    publish_photo_highlight_items(
                        [
                            self._publication.item()(
                                item_id=f"{source_record_id}_ai_mask",
                                item_type="ai_mask",
                                status="rejected",
                                label=str(item.get("name") or self._runtime.identifier()(item) or "AI mask"),
                                url=str(mask_path),
                                created_at=source_started_at,
                                updated_at=int(self._runtime.now()()),
                                reason=mask_meta.get("reason") or "mask_decode_failed",
                                metrics={"attempt": attempt, **mask_meta},
                                record_id=source_record_id,
                                task_id=str(task.get("id") or ""),
                                accessory_id=uid,
                            )
                        ]
                    )
                    continue
                full_mask = cv2.resize(ai_mask, (orig_w, orig_h), interpolation=cv2.INTER_NEAREST)
                bbox = self._masks.bounds()(full_mask, threshold=8)
                if bbox == [0, 0, 0, 0]:
                    source_attempt_failures.append(f"attempt {attempt}: empty_scaled_mask")
                    continue
                x1, y1, x2, y2 = bbox
                cut_bgr = image_bgr[y1:y2, x1:x2].copy()
                raw_cut_mask = full_mask[y1:y2, x1:x2].copy()
                auto_mask, auto_meta = self._masks.roi()(cut_bgr, raw_cut_mask)
                compare_meta = self._masks.compare()(raw_cut_mask, auto_mask)
                artifact_stem = f"{ordinal:02d}_{self._runtime.safe_id()(source_path.stem)}_attempt{attempt:02d}"
                roi_path = artifact_dir / f"{artifact_stem}_roi.png"
                ai_roi_mask_path = artifact_dir / f"{artifact_stem}_ai_roi_mask.png"
                auto_roi_mask_path = artifact_dir / f"{artifact_stem}_traditional_roi_mask.png"
                transparent_path = artifact_dir / f"{artifact_stem}_transparent_sprite.png"
                try:
                    cv2.imwrite(str(roi_path), cut_bgr)
                    cv2.imwrite(str(ai_roi_mask_path), raw_cut_mask)
                    if auto_mask is not None:
                        cv2.imwrite(str(auto_roi_mask_path), auto_mask)
                    preview_bgra = cv2.cvtColor(cut_bgr, cv2.COLOR_BGR2BGRA)
                    preview_bgra[:, :, 3] = raw_cut_mask
                    cv2.imwrite(str(transparent_path), preview_bgra)
                except Exception:
                    pass
                processing_artifacts = {
                    "source_roi_url": self._artifacts.public_url()(roi_path),
                    "ai_roi_mask_url": self._artifacts.public_url()(ai_roi_mask_path),
                    "traditional_roi_mask_url": self._artifacts.public_url()(auto_roi_mask_path),
                    "transparent_sprite_url": self._artifacts.public_url()(transparent_path),
                }
                mask_meta = dict(mask_meta)
                mask_meta.update(
                    {
                        "attempt": attempt,
                        "max_attempts": self._model.attempts(),
                        "auto_roi_mask": auto_meta,
                        "auto_compare": compare_meta,
                        "processing_artifacts": processing_artifacts,
                    }
                )
                now = int(self._runtime.now()())
                compare_status = "completed" if compare_meta.get("ok") else "rejected"
                publish_photo_highlight_items(
                    [
                        self._publication.item()(
                            item_id=f"{source_record_id}_ai_mask",
                            item_type="ai_mask",
                            status="completed",
                            label=str(item.get("name") or self._runtime.identifier()(item) or "AI mask"),
                            url=str(mask_path),
                            created_at=source_started_at,
                            updated_at=now,
                            metrics={"attempt": attempt, **mask_meta},
                            record_id=source_record_id,
                            task_id=str(task.get("id") or ""),
                            accessory_id=uid,
                        ),
                        self._publication.item()(
                            item_id=f"{source_record_id}_roi",
                            item_type="roi_crop",
                            status=compare_status,
                            label=str(item.get("name") or self._runtime.identifier()(item) or "ROI"),
                            url=processing_artifacts["source_roi_url"],
                            created_at=source_started_at,
                            updated_at=now,
                            metrics={"bbox_xyxy": bbox},
                            record_id=source_record_id,
                            task_id=str(task.get("id") or ""),
                            accessory_id=uid,
                        ),
                        self._publication.item()(
                            item_id=f"{source_record_id}_ai_roi_mask",
                            item_type="ai_roi_mask",
                            status=compare_status,
                            label=str(item.get("name") or self._runtime.identifier()(item) or "AI ROI mask"),
                            url=processing_artifacts["ai_roi_mask_url"],
                            created_at=source_started_at,
                            updated_at=now,
                            metrics={"bbox_xyxy": bbox},
                            record_id=source_record_id,
                            task_id=str(task.get("id") or ""),
                            accessory_id=uid,
                        ),
                        self._publication.item()(
                            item_id=f"{source_record_id}_traditional_roi_mask",
                            item_type="traditional_roi_mask",
                            status=compare_status if processing_artifacts["traditional_roi_mask_url"] else "rejected",
                            label=str(item.get("name") or self._runtime.identifier()(item) or "传统 ROI mask"),
                            url=processing_artifacts["traditional_roi_mask_url"],
                            created_at=source_started_at,
                            updated_at=now,
                            reason="" if compare_meta.get("ok") else compare_meta.get("reason") or "ai_mask_auto_crop_mismatch",
                            metrics=compare_meta,
                            record_id=source_record_id,
                            task_id=str(task.get("id") or ""),
                            accessory_id=uid,
                        ),
                        self._publication.item()(
                            item_id=f"{source_record_id}_transparent_sprite",
                            item_type="transparent_sprite",
                            status=compare_status,
                            label=str(item.get("name") or self._runtime.identifier()(item) or "透明 sprite"),
                            url=processing_artifacts["transparent_sprite_url"],
                            created_at=source_started_at,
                            updated_at=now,
                            reason="" if compare_meta.get("ok") else compare_meta.get("reason") or "ai_mask_auto_crop_mismatch",
                            metrics={"bbox_xyxy": bbox, "mask_compare_score": compare_meta.get("score")},
                            record_id=source_record_id,
                            task_id=str(task.get("id") or ""),
                            accessory_id=uid,
                        ),
                    ]
                )
                candidate = {
                    "result": result,
                    "mask_path": mask_path,
                    "mask_meta": mask_meta,
                    "bbox": bbox,
                    "cut_bgr": cut_bgr,
                    "cut_mask": cv2.GaussianBlur(raw_cut_mask, (3, 3), 0),
                    "score": float(compare_meta.get("score") or 0.0),
                }
                if compare_meta.get("ok"):
                    selected = candidate
                    break
                source_attempt_failures.append(
                    f"attempt {attempt}: auto_compare_failed "
                f"iou={compare_meta.get('mask_iou')} bbox_iou={compare_meta.get('bbox_iou')} "
                f"ai_extra={compare_meta.get('ai_extra_fraction')}"
                )
                if best_failed is None or candidate["score"] > float(best_failed.get("score") or -1.0):
                    best_failed = candidate
            if selected is None:
                detail = "；".join(source_attempt_failures[-self._model.attempts():]) or "no_valid_mask_attempt"
                if best_failed is not None:
                    best_compare = ((best_failed.get("mask_meta") or {}).get("auto_compare") or {})
                    detail += f"；best_score={best_compare.get('score')} iou={best_compare.get('mask_iou')}"
                failures.append(f"{source_path.name}: {self._runtime.bounded()(detail, 220)}")
                publish_photo_highlight_items(
                    [
                        self._publication.item()(
                            item_id=f"{source_record_id}_clean_sprite",
                            item_type="clean_sprite",
                            status="failed",
                            label=str(item.get("name") or self._runtime.identifier()(item) or "标准 sprite"),
                            created_at=source_started_at,
                            updated_at=int(self._runtime.now()()),
                            reason=self._runtime.bounded()(detail, 220),
                            record_id=source_record_id,
                            task_id=str(task.get("id") or ""),
                            accessory_id=uid,
                        )
                    ]
                )
                continue
            mask_path = Path(str(selected["mask_path"]))
            mask_meta = selected["mask_meta"]
            x1, y1, x2, y2 = [int(value) for value in selected["bbox"]]
            cut_bgr = selected["cut_bgr"]
            cut_mask = selected["cut_mask"]
            source_size_px = [int(x2 - x1), int(y2 - y1)]
            pose_family = "upright"
            source_center = [int(round((x1 + x2) / 2)), int(round((y1 + y2) / 2))]
            metadata = {
                "task_id": str(task.get("id") or "photo_highlight_mask"),
                "source_pose_collection_job_id": "real_photo_direct_source",
                "agent_mcp_sprite_build": self._model.pose_version(),
                "photo_highlight_sprite_build": self._model.photo_version(),
                "source_pose_collection": str(source_path),
                "source_path": str(source_path),
                "source_photo_path": str(source_path),
                "photo_highlight_mask_path": str(mask_path),
                "photo_highlight_mask_url": self._artifacts.public_url()(mask_path),
                "photo_highlight_prompt": prompt,
                "photo_highlight_model": str(model or ""),
                "photo_highlight_latency_ms": int((selected.get("result") or {}).get("latency_ms") or 0),
                "photo_highlight_mask_metrics": mask_meta,
                "mask_strategy": "ai_highlight_rgb_mask_with_auto_roi_compare",
                "pose_family": pose_family,
                "source_pose_family": pose_family,
                "pose_id": f"photo_highlight_{ordinal:02d}",
                "pose_position": "center",
                "source_position": "center",
                "source_image_size_px": [int(orig_w), int(orig_h)],
                "source_image_width": int(orig_w),
                "source_image_height": int(orig_h),
                "source_region_bbox_xyxy": [0, 0, int(orig_w), int(orig_h)],
                "source_object_bbox_xyxy": [int(x1), int(y1), int(x2), int(y2)],
                "source_object_center_xy": source_center,
                "source_object_size_px": source_size_px,
                "physical_size_mm": physical_size,
                "material_alpha_policy": alpha_policy,
                "photo_highlight_input_size_px": [int(input_w), int(input_h)],
                "photo_highlight_scale_xy": [round(float(scale_x), 6), round(float(scale_y), 6)],
                "photo_highlight_generation_attempts": int(mask_meta.get("attempt") or 1),
                "photo_highlight_max_attempts": self._model.attempts(),
                "training_label_policy": "bbox_from_photo_highlight_mask",
            }
            metadata.update(self._metadata.footprint()(pose_family, source_size_px, physical_size))
            out_path = sprite_dir / f"photo_highlight_{ordinal:02d}_{self._runtime.safe_id()(source_path.stem)}.png"
            sprite_asset = self._artifacts.write()(out_path, cut_bgr, cut_mask, metadata)
            if not sprite_asset:
                failures.append(f"{source_path.name}: clean_sprite_write_failed")
                publish_photo_highlight_items(
                    [
                        self._publication.item()(
                            item_id=f"{source_record_id}_clean_sprite",
                            item_type="clean_sprite",
                            status="failed",
                            label=str(item.get("name") or self._runtime.identifier()(item) or "标准 sprite"),
                            created_at=source_started_at,
                            updated_at=int(self._runtime.now()()),
                            reason="clean_sprite_write_failed",
                            metrics={"output_path": str(out_path)},
                            record_id=source_record_id,
                            task_id=str(task.get("id") or ""),
                            accessory_id=uid,
                        )
                    ]
                )
                continue
            sprite_asset["method"] = "real_photo_highlight_mask_sprite"
            publish_photo_highlight_items(
                [
                    self._publication.item()(
                        item_id=f"{source_record_id}_clean_sprite",
                        item_type="clean_sprite",
                        status="completed",
                        label=str(item.get("name") or self._runtime.identifier()(item) or "标准 sprite"),
                        url=(mask_meta.get("processing_artifacts") or {}).get("transparent_sprite_url") if isinstance(mask_meta, dict) else "",
                        created_at=source_started_at,
                        updated_at=int(self._runtime.now()()),
                        metrics={
                            "output_path": str(out_path),
                            "width": sprite_asset.get("width"),
                            "height": sprite_asset.get("height"),
                            "pose_id": sprite_asset.get("pose_id"),
                        },
                        record_id=source_record_id,
                        task_id=str(task.get("id") or ""),
                        accessory_id=uid,
                    )
                ]
            )
            generated.append(sprite_asset)
        if len(generated) < self._policy.minimum():
            return False, "AI 高亮抠图可用素材不足：" + "；".join(failures[:4])
        self._metadata.normalize()(generated)
        self._metadata.scale()(generated, physical_size)
        self._metadata.laying()(generated)
        retained = [asset for asset in item.get("normalized_assets", []) if asset.get("kind") != "clean_object_sprite"]
        item["normalized_assets"] = retained + generated
        item["clean_sprite_status"] = "ready" if self._policy.complete()(item, generated) else "partial"
        item["clean_sprite_count"] = len(generated)
        item["clean_sprite_expected_count"] = self._policy.minimum()
        item["clean_sprite_failed_cells"] = failures
        item["clean_sprite_preprocessed_at"] = int(self._runtime.now()())
        item["photo_highlight_sprite_status"] = {
            "status": item["clean_sprite_status"],
            "method": "real_photo_highlight_mask_sprite",
            "source_count": len(source_paths),
            "sprite_count": len(generated),
            "failed": failures[:8],
            "updated_at": int(self._runtime.now()()),
        }
        item["preprocess"] = "系统已从用户实拍图生成 AI 高亮 mask，并从原图抠出透明背景单体素材；训练样本复用该 sprite。"
        return self._policy.complete()(item, generated), "" if item["clean_sprite_status"] == "ready" else "photo_highlight_clean_sprite_incomplete"

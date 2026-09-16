"""Existing file-edit orchestration, preserving partial effects and provider boundaries."""
from pathlib import Path
import shutil
from typing import Any
import cv2
import numpy as np
from fastapi import HTTPException, UploadFile
from ..schemas.accessories import AccessoryTextCropRequest, AccessoryAiReferenceRequest, AccessoryFileDeleteRequest
from .file_ports import FileAccess, FileStore, FileMedia, FileProfiles
from .policy import accessory_uid, accessory_material_type
from .projection import AccessoryProjection


class AccessoryFiles:
    def __init__(self, access: FileAccess, store: FileStore, media: FileMedia,
                 profiles: FileProfiles, projection: AccessoryProjection):
        self.access, self.store, self.media = access, store, media
        self.profiles, self.projection = profiles, projection

    async def add_accessory_files(self, accessory_id: str, files: list[UploadFile]) -> dict[str, Any]:
        user = self.access.current_user()
        if not files:
            raise HTTPException(status_code=400, detail="No files uploaded")
        config = self.store.load_config()
        for item in config.get("accessories", []):
            if accessory_uid(item) != accessory_id:
                continue
            self.access.require_access(item, user, write=True)
            if accessory_material_type(item) == "text":
                self.media.validate_text_uploads(files, existing_count=self.media.text_source_count(item))
            target_dir = self.media.upload_directory() / "accessories" / accessory_id
            target_dir.mkdir(parents=True, exist_ok=True)
            saved_files: list[str] = []
            for upload in files:
                path = target_dir / self.media.safe_name(upload.filename)
                if path.suffix.lower() not in self.media.image_suffixes():
                    raise HTTPException(status_code=400, detail="Only image files can be added to accessory profiles")
                with path.open("wb") as f:
                    shutil.copyfileobj(upload.file, f)
                saved_files.append(str(path))
            item.setdefault("source_files", [])
            item["source_files"].extend(saved_files)
            if accessory_material_type(item) == "text":
                item.setdefault("original_source_files", [])
                item["original_source_files"].extend(saved_files)
            self.profiles.refresh(item, force_profile=True)
            self.profiles.save_cache({"entries": {}})
            self.store.save_item(item, config)
            return {
                "status": "saved",
                "item": self.projection.serialize_accessory_summary(item),
                "items": self.projection.serialize_accessory_items(self.store.scope_config(config, user)["accessories"]),
                "detail": self.media.detail(item),
            }
        raise HTTPException(status_code=404, detail="Accessory not found")

    def crop_accessory_text_image(self, accessory_id: str, request: AccessoryTextCropRequest) -> dict[str, Any]:
        user = self.access.current_user()
        target_raw = str(request.source_path or "").strip()
        if not target_raw:
            raise HTTPException(status_code=400, detail="source_path is required")
        if len(request.corners or []) != 4:
            raise HTTPException(status_code=400, detail="corners must contain tl,tr,br,bl")
        config = self.store.load_config()
        for item in config.get("accessories", []):
            if accessory_uid(item) != accessory_id:
                continue
            self.access.require_access(item, user, write=True)
            if accessory_material_type(item) != "text":
                raise HTTPException(status_code=400, detail="Only text accessories can be cropped")
            source_paths = {str(path): path for path in self.media.existing_source_paths(item)}
            if target_raw not in source_paths:
                raise HTTPException(status_code=404, detail="Photo is not registered on this accessory")
            source_path = source_paths[target_raw]
            if self.media.is_rectified(source_path):
                raise HTTPException(status_code=400, detail="This text image is already manually cropped")
            image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
            if image is None:
                raise HTTPException(status_code=400, detail="Source image is unreadable")
            height, width = image.shape[:2]
            points: list[list[float]] = []
            for corner in request.corners:
                x = max(0.0, min(100.0, float(corner.get("x", 0.0)))) * width / 100.0
                y = max(0.0, min(100.0, float(corner.get("y", 0.0)))) * height / 100.0
                points.append([x, y])
            src = np.array(points, dtype="float32")
            tl, tr, br, bl = src
            target_w = int(round(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl))))
            target_h = int(round(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl))))
            if target_w < 8 or target_h < 8:
                raise HTTPException(status_code=400, detail="Crop area is too small")
            dst = np.array(
                [[0, 0], [target_w - 1, 0], [target_w - 1, target_h - 1], [0, target_h - 1]],
                dtype="float32",
            )
            warped = cv2.warpPerspective(image, cv2.getPerspectiveTransform(src, dst), (target_w, target_h))
            target_dir = self.media.upload_directory() / "accessories" / accessory_id
            target_dir.mkdir(parents=True, exist_ok=True)
            base = self.media.crop_stem(source_path)
            out_path = target_dir / f"{base}_manual_rectified.png"
            suffix = 1
            while out_path.exists():
                out_path = target_dir / f"{base}_manual_rectified_{suffix}.png"
                suffix += 1
            if not cv2.imwrite(str(out_path), warped):
                raise HTTPException(status_code=500, detail="Failed to save cropped image")
            item.setdefault("source_files", [])
            item["source_files"].append(str(out_path))
            self.profiles.refresh(item, force_profile=True)
            self.profiles.save_cache({"entries": {}})
            self.store.save_item(item, config)
            return {
                "status": "saved",
                "accessory_id": accessory_id,
                "source_path": str(out_path),
                "item": self.projection.serialize_accessory_summary(item),
                "items": self.projection.serialize_accessory_items(self.store.scope_config(config, user)["accessories"]),
                "detail": self.media.detail(item),
            }
        raise HTTPException(status_code=404, detail="Accessory not found")

    def set_accessory_ai_reference(self, accessory_id: str, request: AccessoryAiReferenceRequest) -> dict[str, Any]:
        user = self.access.current_user()
        target_raw = str(request.source_path or "").strip()
        if not target_raw:
            raise HTTPException(status_code=400, detail="source_path is required")
        config = self.store.load_config()
        for item in config.get("accessories", []):
            if accessory_uid(item) != accessory_id:
                continue
            self.access.require_access(item, user, write=True)
            allowed = {
                str(asset.get("source_path") or "")
                for asset in self.media.detail(item).get("gallery", [])
                if isinstance(asset, dict) and asset.get("source_path")
            }
            if target_raw not in allowed or not Path(target_raw).exists():
                raise HTTPException(status_code=404, detail="Photo is not available on this accessory")
            item["ai_profile_reference_files"] = [target_raw]
            item["ai_profile"] = self.profiles.fallback(item)
            item["ai_profile_status"] = "ready"
            try:
                self.profiles.generate(item, allow_provider=True)
            except Exception as exc:
                item["ai_profile_status"] = {
                    "ok": False,
                    "status": "fallback",
                    "message": f"AI profile provider failed; using selected local reference. {self.profiles.bounded_text(str(exc), 120)}",
                }
            self.profiles.save_cache({"entries": {}})
            self.store.save_item(item, config)
            return {
                "status": "saved",
                "accessory_id": accessory_id,
                "source_path": target_raw,
                "item": self.projection.serialize_accessory_summary(item),
                "items": self.projection.serialize_accessory_items(self.store.scope_config(config, user)["accessories"]),
                "detail": self.media.detail(item),
            }
        raise HTTPException(status_code=404, detail="Accessory not found")

    def delete_accessory_file(self, accessory_id: str, request: AccessoryFileDeleteRequest) -> dict[str, Any]:
        user = self.access.current_user()
        target_raw = str(request.source_path or "").strip()
        if not target_raw:
            raise HTTPException(status_code=400, detail="source_path is required")
        config = self.store.load_config()
        for item in config.get("accessories", []):
            if accessory_uid(item) != accessory_id:
                continue
            self.access.require_access(item, user, write=True)
            source_paths = {str(path) for path in self.media.existing_source_paths(item)}
            normalized_paths = {
                str(asset.get("path") or "")
                for asset in item.get("normalized_assets", [])
                if isinstance(asset, dict) and asset.get("path")
            }
            pose_paths = {
                str(job.get("output_path") or "")
                for job in self.media.image_jobs(item)
                if isinstance(job, dict) and job.get("output_path")
            }
            allowed = source_paths | normalized_paths | pose_paths
            if target_raw not in allowed:
                raise HTTPException(status_code=404, detail="Photo is not registered on this accessory")
            removed_source = target_raw in source_paths
            removed_pose = target_raw in pose_paths
            for key in ("source_files", "original_source_files", "ai_profile_reference_files"):
                if isinstance(item.get(key), list):
                    item[key] = [path for path in item[key] if str(path) != target_raw]
            if isinstance(item.get("normalized_assets"), list):
                item["normalized_assets"] = [
                    asset
                    for asset in item["normalized_assets"]
                    if not isinstance(asset, dict)
                    or (
                        str(asset.get("path") or "") != target_raw
                        and (not removed_pose or str(asset.get("source_pose_collection") or "") != target_raw)
                    )
                ]
            if isinstance(item.get("codex_image_jobs"), list):
                item["codex_image_jobs"] = [
                    job
                    for job in item["codex_image_jobs"]
                    if not isinstance(job, dict) or str(job.get("output_path") or "") != target_raw
                ]
                item["codex_image_job"] = item["codex_image_jobs"][0] if item["codex_image_jobs"] else None
            target_path = Path(target_raw)
            try:
                resolved = target_path.resolve()
                if resolved.exists() and resolved.is_relative_to(self.media.data_directory().resolve()):
                    resolved.unlink()
            except OSError:
                pass
            if removed_source:
                self.profiles.refresh(item, force_profile=True)
                self.profiles.save_cache({"entries": {}})
            else:
                item["clean_sprite_count"] = len(self.media.clean_sprites(item))
                item["clean_sprite_status"] = "ready" if item["clean_sprite_count"] else item.get("clean_sprite_status", "")
            self.store.save_item(item, config)
            return {
                "status": "deleted",
                "accessory_id": accessory_id,
                "source_path": target_raw,
                "item": self.projection.serialize_accessory_summary(item),
                "items": self.projection.serialize_accessory_items(self.store.scope_config(config, user)["accessories"]),
                "detail": self.media.detail(item),
            }
        raise HTTPException(status_code=404, detail="Accessory not found")

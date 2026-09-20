"""Explicit pose sprite builder service without application imports."""
from typing import Any
from .pose_materialization_ports import PoseChromaSources, PoseSpritePolicy, PoseSpriteRuntime, PoseSpriteImages, PoseSpriteMetadata, PoseAssetMedia


class PoseSpriteBuilder:
    def __init__(self, chroma: PoseChromaSources, policy: PoseSpritePolicy, runtime: PoseSpriteRuntime, images: PoseSpriteImages, metadata: PoseSpriteMetadata, media: PoseAssetMedia) -> None:
        self._chroma = chroma
        self._policy = policy
        self._runtime = runtime
        self._images = images
        self._metadata = metadata
        self._media = media

    def dedup_agent_mcp_pose_references(self, item: dict[str, Any]) -> bool:
        """Keep a single AI pose image per pose_id on an accessory, removing the
    duplicates that earlier tasks accumulated. Returns True when anything was
    dropped so callers can rebuild the clean sprites from the deduplicated set."""
        assets = item.get("normalized_assets")
        if not isinstance(assets, list):
            return False
        seen: set[str] = set()
        kept: list[Any] = []
        removed = False
        for asset in assets:
            if isinstance(asset, dict) and asset.get("kind") == "agent_mcp_pose_reference":
                pose_id = str(asset.get("pose_id") or "")
                key = pose_id or str(asset.get("path") or "")
                if key in seen:
                    removed = True
                    continue
                seen.add(key)
            kept.append(asset)
        if removed:
            item["normalized_assets"] = kept
        return removed

    def build_clean_sprites_from_agent_mcp_poses(self, item: dict[str, Any], *, force: bool = False) -> bool:
        """Segment every cached AI-generated standard pose image into a clean,
    background-free object sprite. These sprites are what the sample compositor
    pastes (with rotation/scale/position variety) onto the task background."""
        if self._policy.material()(item) == "text":
            return False
        if self._policy.deduplicate()(item):
            force = True
        references = self._policy.references()(item)
        if not references:
            return False
        existing = self._policy.existing()(item)
        # Only reuse existing sprites when they were actually cut from the AI pose
        # images. Raw-photo fallback sprites (no agent_mcp provenance) must be
        # replaced once the AI standard images exist, otherwise the training set
        # would keep using the fallback cut-outs instead of the planned poses.
        existing_from_ai_poses = bool(existing) and all(
            bool(asset.get("agent_mcp_pose_reference_path") or asset.get("agent_mcp_pose_call_id"))
            for asset in existing
        )
        if existing and not force and existing_from_ai_poses and self._policy.complete()(item, existing):
            return False
        item["material_alpha_policy"] = self._policy.alpha()(item)
        physical_size = item.get("physical_size") if isinstance(item.get("physical_size"), dict) else {}
        alpha_policy = self._policy.alpha()(item)
        uid = self._runtime.identifier()(item)
        sprite_dir = self._runtime.root() / uid / "clean_sprites"
        rng = self._runtime.rng()(int(item.get("created_at") or self._runtime.now()()))
        generated: list[dict[str, Any]] = []
        for ref in references:
            path = self._media.resolve()(ref.get("path"))
            image = self._images.read()(str(path), self._images.read_mode())
            if image is None:
                continue
            chroma_screen = self._chroma.screen()(ref.get("chroma_screen"))
            seg = self._images.segment()(image, rng, chroma_screen)
            if not seg:
                continue
            cut_bgr, cut_mask, source_bbox = seg
            bbox = [int(source_bbox[0]), int(source_bbox[1]), int(source_bbox[2]), int(source_bbox[3])]
            source_size_px = [max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])]
            pose_id = str(ref.get("pose_id") or "")
            # AI standard pose images are a single object shot strictly straight
            # top-down on a green surface. Every one is a top-view sprite, so the
            # compositor must place it at any location with free planar rotation
            # (no grid/parallax remap). canonical_pose_family_name returns the raw
            # pose id for these names, which would break top-view detection, so we
            # pin the family explicitly.
            pose_family = "upright"
            # The unique token only drives the on-disk sprite filename. The grid
            # position id is forced to the non-grid "legacy_clean_sprite" sentinel so
            # load_object_preview_sprite never rejects the sprite for a missing grid
            # cell — that rejection is exactly what produced the black placeholder
            # boxes the compositor draws when no sprite is selectable.
            unique_token = str(ref.get("call_id") or pose_id or f"agent_mcp_{self._runtime.safe_id()(str(path))}")
            metadata = {
                "task_id": str(ref.get("task_id") or "agent_mcp_pose_reference"),
                "source_pose_collection_job_id": "legacy_clean_sprite",
                "agent_mcp_pose_call_id": unique_token,
                "agent_mcp_sprite_build": self._runtime.version(),
                "source_pose_collection": str(path),
                "source_path": str(path),
                "pose_family": pose_family,
                "source_pose_family": pose_family,
                "pose_id": pose_id,
                "pose_position": "center",
                "source_position": "center",
                "source_image_size_px": [int(image.shape[1]), int(image.shape[0])],
                "source_image_width": int(image.shape[1]),
                "source_image_height": int(image.shape[0]),
                "source_region_bbox_xyxy": [0, 0, int(image.shape[1]), int(image.shape[0])],
                "source_object_bbox_xyxy": bbox,
                "source_object_center_xy": [int(round((bbox[0] + bbox[2]) / 2)), int(round((bbox[1] + bbox[3]) / 2))],
                "source_object_size_px": source_size_px,
                "physical_size_mm": physical_size,
                "material_alpha_policy": alpha_policy,
                "agent_mcp_pose_reference_path": str(path),
                "chroma_screen": chroma_screen,
            }
            metadata.update(self._metadata.footprint()(pose_family, source_size_px, physical_size))
            out_path = sprite_dir / f"agent_mcp_{self._runtime.safe_id()(unique_token)}.png"
            sprite_asset = self._images.write()(out_path, cut_bgr, cut_mask, metadata)
            if sprite_asset:
                sprite_asset["method"] = "agent_mcp_pose_segmented_sprite"
                generated.append(sprite_asset)
        if not generated:
            return False
        generated = generated[:18]
        self._metadata.normalize()(generated)
        self._metadata.scale()(generated, physical_size)
        self._metadata.laying()(generated)
        retained = [
            asset
            for asset in item.get("normalized_assets", [])
            if asset.get("kind") != "clean_object_sprite"
        ]
        item["normalized_assets"] = retained + generated
        item["clean_sprite_status"] = "ready" if self._policy.complete()(item, generated) else "partial"
        item["clean_sprite_count"] = len(generated)
        item["clean_sprite_expected_count"] = len(references)
        item["clean_sprite_failed_cells"] = []
        item["clean_sprite_preprocessed_at"] = int(self._runtime.now()())
        item["preprocess"] = "系统已从 AI 生成的标准姿态图中分割出无背景单体素材；训练样本直接复用。"
        return True

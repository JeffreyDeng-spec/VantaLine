"""Accessory pose layout and candidate policies with explicit dependencies."""
from typing import Any
import numpy as np
from .pose_policy_ports import PoseLayoutValues, PoseRotationOperations, PoseRenderOperations, PoseAssetOperations, PoseCandidateOperations


def pose_collection_regions(image: np.ndarray, padded: bool = True) -> list[tuple[int, int, int, int]]:
    h, w = image.shape[:2]
    regions = []
    pad_x = int(round(w * 0.075)) if padded else 0
    pad_y = int(round(h * 0.075)) if padded else 0
    for row in range(3):
        for col in range(3):
            x1 = max(0, int(round(col * w / 3)) - pad_x)
            y1 = max(0, int(round(row * h / 3)) - pad_y)
            x2 = min(w, int(round((col + 1) * w / 3)) + pad_x)
            y2 = min(h, int(round((row + 1) * h / 3)) + pad_y)
            regions.append((x1, y1, x2, y2))
    return regions

def normalize_cardinal_rotation_degrees(angle: float) -> int:
    return int(round(float(angle) / 90.0) * 90) % 360

def source_object_major_axis_px(asset: dict[str, Any]) -> int | None:
    size = asset.get("source_object_size_px")
    if not isinstance(size, list) or len(size) < 2:
        return None
    try:
        return max(int(size[0]), int(size[1]))
    except (TypeError, ValueError):
        return None

class PoseGridPolicy:
    def __init__(self, layout: PoseLayoutValues, rotation: PoseRotationOperations, render: PoseRenderOperations) -> None:
        self._layout = layout
        self._rotation = rotation
        self._render = render

    def grid_position_for_center(self, center: tuple[int, int], roi: tuple[int, int, int, int]) -> str:
        x1, y1, x2, y2 = roi
        x, y = center
        col = int(np.clip(np.floor(((x - x1) / max(1, x2 - x1)) * 3), 0, 2))
        row = int(np.clip(np.floor(((y - y1) / max(1, y2 - y1)) * 3), 0, 2))
        return self._layout.grid()[row * 3 + col]

    def grid_row_col(self, position: str | None) -> tuple[int, int] | None:
        if position not in self._layout.grid():
            return None
        idx = self._layout.grid().index(position)
        return idx // 3, idx % 3

    def grid_position_from_row_col(self, row: int, col: int) -> str:
        row = int(np.clip(row, 0, 2))
        col = int(np.clip(col, 0, 2))
        return self._layout.grid()[row * 3 + col]

    def source_position_for_rotated_target(self, target_position: str | None, rotation_degrees: float) -> str | None:
        """Pick the source grid cell that rotates into the requested target cell."""
        row_col = self._rotation.row_col()(target_position)
        if row_col is None:
            return target_position
        row, col = row_col
        x = col - 1
        y = row - 1
        rotation = self._rotation.normalize()(rotation_degrees)
        if rotation == 0:
            sx, sy = x, y
        elif rotation == 90:
            sx, sy = -y, x
        elif rotation == 180:
            sx, sy = -x, -y
        else:
            sx, sy = y, -x
        return self._rotation.position()(sy + 1, sx + 1)

    def source_position_for_render_policy(self,
        target_position: str | None,
        rotation_degrees: float,
        pose_family: str | None,
        rng: np.random.Generator,
    ) -> str | None:
        if self._render.is_top()(pose_family or ""):
            return self._layout.upright()[int(rng.integers(0, len(self._layout.upright())))]
        return self._render.source()(target_position, rotation_degrees)

    def object_render_pose_policy(self, pose_family: str | None, rng: np.random.Generator) -> dict[str, Any]:
        rotation = float(rng.uniform(-180.0, 180.0))
        if self._render.is_top()(pose_family or ""):
            return {
                "render_pose_policy": "upright_random_planar_rotation",
                "perspective_rotation_degrees": rotation,
                "placement_angle_degrees": rotation,
                "desired_lie_direction": None,
                "desired_facing_direction": f"upright_top_down_{rotation:.1f}deg",
                "source_selection_rule": "upright_center_or_bottom_center_random_rotation",
            }
        normalized = self._rotation.normalize()(rotation)
        lie_direction = "horizontal" if normalized in {90, 270} else "vertical"
        return {
            "render_pose_policy": "lying_random_planar_rotation",
            "perspective_rotation_degrees": rotation,
            "placement_angle_degrees": rotation,
            "desired_lie_direction": lie_direction,
            "desired_facing_direction": f"lying_{lie_direction}_{rotation:.1f}deg",
            "source_selection_rule": "inverse_grid_position_for_random_planar_rotation",
        }

    def pose_selection_reason(self, target_position: str | None, source_position: str | None, rotation_degrees: float) -> str:
        rotation = self._rotation.normalize()(rotation_degrees)
        if not target_position or not source_position:
            return "position_unavailable"
        if rotation == 0 and source_position in self._layout.upright():
            return "upright_restricted_center_or_bottom_center"
        if rotation == 0:
            return "same_position_0" if source_position == target_position else "unrotated_position_remap"
        if rotation == 180:
            return "opposite_position_180" if source_position != target_position else "center_180_no_opposite"
        return f"inverse_position_{rotation}"

class PoseCandidatePolicy:
    def __init__(self, assets: PoseAssetOperations, candidates: PoseCandidateOperations) -> None:
        self._assets = assets
        self._candidates = candidates

    def object_pose_render_size_hint(self, item: dict[str, Any], pose_family: str | None) -> tuple[int, int]:
        canonical = self._assets.canonical()(pose_family)
        for asset in self._assets.assets()(item):
            if canonical and self._assets.canonical()(asset.get("source_pose_family") or asset.get("pose_family")) != canonical:
                continue
            hint = asset.get("render_size_hint_px") or asset.get("render_footprint_px")
            if isinstance(hint, list) and len(hint) >= 2:
                try:
                    return max(16, int(hint[0])), max(16, int(hint[1]))
                except (TypeError, ValueError):
                    continue
        metadata = self._assets.footprint()(str(pose_family or ""), [1, 1], item.get("physical_size"))
        return int(metadata["render_footprint_px"][0]), int(metadata["render_footprint_px"][1])

    def filter_complete_pose_candidates(self, candidates: list[dict[str, Any]], pose_family: str | None) -> list[dict[str, Any]]:
        if str(pose_family or "").lower() not in {"lying", "flat", "side", "side-facing"}:
            return candidates
        lengths = [value for value in (self._candidates.major_axis()(asset) for asset in candidates) if value]
        if len(lengths) < 4:
            return candidates
        median_length = float(np.median(lengths))
        min_length = median_length * 0.85
        filtered = [asset for asset in candidates if (self._candidates.major_axis()(asset) or median_length) >= min_length]
        return filtered or candidates

    def choose_object_pose_family(self, sprites: list[dict[str, Any]], rng: np.random.Generator) -> str | None:
        families = sorted({self._candidates.family()(asset) for asset in sprites if self._candidates.family()(asset)})
        if not families:
            return None
        return families[int(rng.integers(0, len(families)))]

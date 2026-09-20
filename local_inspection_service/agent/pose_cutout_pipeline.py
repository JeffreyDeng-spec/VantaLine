"""Explicit pose cutout pipeline service without application imports."""
from typing import Any
from .pose_materialization_ports import PoseCutoutSources
import numpy as np


class PoseCutoutPipeline:
    def __init__(self, cutouts: PoseCutoutSources) -> None:
        self._cutouts = cutouts

    def segment_agent_mcp_pose_object(self,
        image_bgr: np.ndarray,
        rng: np.random.Generator,
        chroma_screen: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int]] | None:
        """Cut the single foreground accessory out of an AI-generated top-down pose
    image (object resting on a solid chroma tabletop). The fixed chroma-key path
    runs first, then legacy green/rembg fallbacks handle older generated plates."""
        if image_bgr is None or image_bgr.ndim != 3:
            return None
        source_shape = image_bgr.shape
        # 0) Fixed chroma key for the new solid tabletop contract.
        keyed_chroma = self._cutouts.chroma()(image_bgr, chroma_screen)
        if keyed_chroma:
            usable = self._cutouts.usable()((keyed_chroma[0], keyed_chroma[1]), source_shape)
            if usable:
                return usable[0], usable[1], keyed_chroma[2]
        # 1) Precise AI matte (rembg/u2net) + bright-green halo trim — keeps the FULL
        #    silhouette including thin ends and corrugations (no erosion). Best edges.
        precise = self._cutouts.precise()(image_bgr)
        if precise:
            usable = self._cutouts.usable()((precise[0], precise[1]), source_shape)
            if usable:
                return usable[0], usable[1], precise[2]
        # 2) Green chroma-key tuned for old AI green-conveyor plates.
        keyed = self._cutouts.green()(image_bgr)
        if keyed:
            usable = self._cutouts.usable()((keyed[0], keyed[1]), source_shape)
            if usable:
                return usable[0], usable[1], keyed[2]
        # 3) generic rembg path (padded bbox) when available.
        rembg_result = self._cutouts.background()(image_bgr)
        if rembg_result:
            usable = self._cutouts.usable()((rembg_result[0], rembg_result[1]), source_shape)
            if usable:
                return usable[0], usable[1], rembg_result[2]
        # 4) Green-aware foreground heuristic — removes the green conveyor and keeps
        #    the largest non-green component (works for arbitrary object colors).
        fallback = self._cutouts.generic()(image_bgr, rng)
        if fallback:
            usable = self._cutouts.usable()(fallback, source_shape)
            if usable:
                return usable[0], usable[1], (0, 0, int(source_shape[1]), int(source_shape[0]))
        # 5) Green-screen key (anchor-oriented) as last resort.
        green_result = self._cutouts.final_green()(image_bgr, rng)
        if green_result:
            usable = self._cutouts.usable()((green_result[0], green_result[1]), source_shape)
            if usable:
                return usable[0], usable[1], green_result[2]
        return None

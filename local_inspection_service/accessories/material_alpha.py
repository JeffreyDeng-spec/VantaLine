"""Material alpha without application imports."""
from typing import Any
import numpy as np
from .material_alpha_ports import MaterialAlphaOperations


class MaterialAlphaProcessor:
    def __init__(self, operations: MaterialAlphaOperations) -> None:
        self._operations = operations


    def material_aware_object_alpha(self,
        asset: np.ndarray,
        mask: np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        policy = self._operations.policy()(None, metadata)
        if policy == "transparent":
            adjusted, stats = self._operations.transparent()(asset, mask)
            stats["object_alpha_material_policy"] = "transparent"
            return adjusted, stats
        adjusted, stats = self._operations.solid()(mask)
        stats["object_alpha_material_policy"] = "opaque"
        return adjusted, stats

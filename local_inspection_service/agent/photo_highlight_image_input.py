"""Explicit photo-highlight image helpers without application imports."""
from typing import Any
import base64
import cv2
import numpy as np
from .photo_highlight_image_ports import PhotoHighlightImagePolicy


class PhotoHighlightImageInput:
    def __init__(self, policy: PhotoHighlightImagePolicy) -> None:
        self._policy = policy


    def photo_highlight_mask_prompt(self, item: dict[str, Any]) -> str:
        name = str(item.get("name") or item.get("label") or self._policy.identifier()(item) or "the accessory")
        return "\n".join(
            [
                "Create a strict binary segmentation highlight map for the attached real product photo.",
                "This is not a creative product image and not a normal photo.",
                "Preserve the input camera framing and aspect ratio.",
                f"Accessory: {name}.",
                "Output a single RGB image where:",
                "- pixels belonging to the main rigid product body are filled with exact pure green RGB(0,255,0) / #00FF00;",
                "- every other pixel is exact black RGB(0,0,0);",
                "- the green mask must be tight to the physical outer contour of the rigid product body;",
                "- never include contact shadows, cast shadows, paper, tabletop, background, reflections on the background, or empty margin;",
                "- do not highlight movable or detachable parts: straps, lanyards, strings, cords, cables, loose tags, packaging ties, or detachable accessories;",
                "- do not generate a new product, do not alter viewpoint, do not add labels/text/shadows/background;",
                "- if uncertain, prefer excluding ambiguous edge pixels instead of including background;",
                "- output only pure green and pure black, with no gradients, feathering, gray edges, labels, annotations, or bounding boxes.",
                "The output should be a mask-like color map.",
            ]
        )

    def photo_highlight_input_data_url(self, image_bgr: np.ndarray) -> tuple[np.ndarray, str, float, float] | None:
        if image_bgr is None or image_bgr.ndim != 3:
            return None
        height, width = image_bgr.shape[:2]
        scale = min(1.0, self._policy.max_side() / float(max(height, width, 1)))
        if scale < 1.0:
            ai_bgr = cv2.resize(
                image_bgr,
                (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
                interpolation=cv2.INTER_AREA,
            )
        else:
            ai_bgr = image_bgr.copy()
        ok, encoded = cv2.imencode(".jpg", ai_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        if not ok:
            return None
        data_url = "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")
        scale_x = ai_bgr.shape[1] / float(max(1, width))
        scale_y = ai_bgr.shape[0] / float(max(1, height))
        return ai_bgr, data_url, scale_x, scale_y

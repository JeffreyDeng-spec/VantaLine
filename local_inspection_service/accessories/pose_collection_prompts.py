"""Pose collection prompt construction; preserves existing prompt bytes and camera math."""
from dataclasses import dataclass
import math
from typing import Any
from .pose_collection_prompt_ports import PoseCollectionPromptDependencies

@dataclass(frozen=True)
class PoseCollectionPrompts:
    dependencies: PoseCollectionPromptDependencies

    def pose_collection_dimension_text(self, item: dict[str, Any]) -> str:
        physical = item.get("physical_size") or {}
        length = physical.get("length_mm")
        width = physical.get("width_mm")
        height = physical.get("height_mm")
        long_short_rule = (
            "Durable dimension rule: in every source/reference image, the visible longer side of the object is its physical "
            "length, and the visible shorter side is its physical width. Preserve that source long:short aspect ratio; never "
            "swap length/width and never squash or stretch an elongated object to fill a square or anchor footprint. "
        )
        if length and width and height:
            return (
                f"{long_short_rule}"
                "Use these physical dimensions to infer the 3D form and perspective without overriding the source aspect: "
                f"length {length} mm, width {width} mm, height {height} mm. "
            )
        return f"{long_short_rule}Infer the object's approximate 3D form and proportions from the reference image. "


    def tabletop_scene_text(self, surface_mode: str = "white") -> str:
        if surface_mode == "reference":
            return (
                "Render the scene as one overhead photograph of nine real objects physically placed on the same tabletop/background "
                "material visible in the reference images. Preserve that reference table material, color, lighting, texture, and "
                "surface context, for example a green tabletop if the reference image uses a green tabletop. "
            )
        if surface_mode == "pure_white":
            return (
                "Render the scene as one overhead photograph of nine real objects physically placed on a 100% pure white tabletop. "
                "The tabletop must be flat, uniform white, textureless, shadow-free, and free of stains, gradients, color casts, or "
                "material patterns. "
            )
        return "Render the scene as one overhead photograph of nine real objects physically placed on a clean white tabletop. "


    def pose_collection_camera_grid_text(self, item: dict[str, Any], surface_mode: str = "white") -> str:
        physical = item.get("physical_size") or {}
        length = float(physical.get("length_mm") or 170.0)
        grid_pitch = max(40.0, length)
        camera_height = max(300.0, length * 5.0)
        axis_tilt = math.degrees(math.atan(grid_pitch / camera_height))
        corner_tilt = math.degrees(math.atan((grid_pitch * math.sqrt(2)) / camera_height))
        return (
            "Use this fixed camera geometry and write it visually into the 3x3 grid. "
            f"{self.dependencies.tabletop_scene_text()(surface_mode)}"
            "The nine objects form a regular 3x3 square grid with equal X spacing and equal Y spacing, like a neat tic-tac-toe/田字 layout. "
            f"Assume the real inspection camera is mounted {camera_height:.0f} mm above the conveyor/table plane. "
            f"The nine object positions are spaced {grid_pitch:.0f} mm apart in X/Y around the center. "
            "Use one physically consistent object scale across all nine positions; apparent size changes may come only from "
            "the specified camera perspective and must not be arbitrary resizing. "
            "The camera is above the 3x3 arrangement and looks downward. Use exactly two view-axis angles, not three object "
            "rotation angles: azimuth_xy is the direction angle in the horizontal X/Y plane, and tilt_from_z is the small "
            "angle between the camera ray and the vertical Z axis. These are camera/view-axis parameters, not bottle rotation. "
            "The bottle yaw/object orientation is fixed and identical in every cell; do not rotate the bottles themselves. "
            "Use this mandatory 3D view table: "
            f"top-left: azimuth_xy=135 deg, tilt_from_z={corner_tilt:.1f} deg; "
            f"top-center: azimuth_xy=90 deg, tilt_from_z={axis_tilt:.1f} deg; "
            f"top-right: azimuth_xy=45 deg, tilt_from_z={corner_tilt:.1f} deg; "
            f"middle-left: azimuth_xy=180 deg, tilt_from_z={axis_tilt:.1f} deg; "
            "center: azimuth_xy=none, tilt_from_z=0.0 deg, perfectly vertical optical-axis view; "
            f"middle-right: azimuth_xy=0 deg, tilt_from_z={axis_tilt:.1f} deg; "
            f"bottom-left: azimuth_xy=-135 deg, tilt_from_z={corner_tilt:.1f} deg; "
            f"bottom-center: azimuth_xy=-90 deg, tilt_from_z={axis_tilt:.1f} deg; "
            f"bottom-right: azimuth_xy=-45 deg, tilt_from_z={corner_tilt:.1f} deg. "
            "Because the camera is high, all non-center tilt_from_z values are intentionally small. These angle values are "
            "mandatory; do not invent a different camera layout and do not rotate the bottles."
        )


    def pose_collection_position_specs(self, item: dict[str, Any]) -> dict[str, str]:
        physical = item.get("physical_size") or {}
        length = float(physical.get("length_mm") or 170.0)
        grid_pitch = max(40.0, length)
        camera_height = max(300.0, length * 5.0)
        axis_tilt = math.degrees(math.atan(grid_pitch / camera_height))
        corner_tilt = math.degrees(math.atan((grid_pitch * math.sqrt(2)) / camera_height))
        return {
            "top-left": f"top-left: azimuth_xy=135 deg, tilt_from_z={corner_tilt:.1f} deg, camera shifted top/back + left, looking diagonally inward",
            "top-center": f"top-center: azimuth_xy=90 deg, tilt_from_z={axis_tilt:.1f} deg, camera shifted top/back, looking diagonally inward",
            "top-right": f"top-right: azimuth_xy=45 deg, tilt_from_z={corner_tilt:.1f} deg, camera shifted top/back + right, looking diagonally inward",
            "middle-left": f"middle-left: azimuth_xy=180 deg, tilt_from_z={axis_tilt:.1f} deg, camera shifted left, looking diagonally inward",
            "center": "center: azimuth_xy=none, tilt_from_z=0.0 deg, perfectly vertical optical-axis view with no perspective bias",
            "middle-right": f"middle-right: azimuth_xy=0 deg, tilt_from_z={axis_tilt:.1f} deg, camera shifted right, looking diagonally inward",
            "bottom-left": f"bottom-left: azimuth_xy=-135 deg, tilt_from_z={corner_tilt:.1f} deg, camera shifted bottom/front + left, looking diagonally inward",
            "bottom-center": f"bottom-center: azimuth_xy=-90 deg, tilt_from_z={axis_tilt:.1f} deg, camera shifted bottom/front, looking diagonally inward",
            "bottom-right": f"bottom-right: azimuth_xy=-45 deg, tilt_from_z={corner_tilt:.1f} deg, camera shifted bottom/front + right, looking diagonally inward",
        }


    def pose_collection_camera_batch_text(self, item: dict[str, Any], batch_key: str | None, surface_mode: str = "white") -> str:
        if not batch_key:
            return self.dependencies.pose_collection_camera_grid_text()(item, surface_mode)
        batch = next((entry for entry in self.dependencies.POSE_COLLECTION_BATCHES() if entry[0] == batch_key), None)
        if not batch:
            return self.dependencies.pose_collection_camera_grid_text()(item, surface_mode)
        _, batch_label, positions = batch
        physical = item.get("physical_size") or {}
        length = float(physical.get("length_mm") or 170.0)
        grid_pitch = max(40.0, length)
        camera_height = max(300.0, length * 5.0)
        specs = self.dependencies.pose_collection_position_specs()(item)
        spec_text = "; ".join(specs[position] for position in positions)
        return (
            f"This image is only the {batch_label} batch of the original 3x3 camera grid. "
            "Generate exactly three separated object cutouts, arranged left-to-right in this exact order: "
            f"{', '.join(positions)}. Do not generate the other six positions in this file. "
            f"Assume the real inspection camera is mounted {camera_height:.0f} mm above the conveyor/table plane. "
            f"{self.dependencies.tabletop_scene_text()(surface_mode)}"
            f"The nine original object positions are spaced {grid_pitch:.0f} mm apart in X/Y around the center; this file "
            "contains only the three listed positions from that grid. Use exactly two view-axis angles, not object rotation "
            "angles. Use one physically consistent object scale across all requested positions; apparent size changes may "
            "come only from the specified camera perspective and must not be arbitrary resizing. "
            "azimuth_xy is the direction angle in the horizontal X/Y plane, and tilt_from_z is the small angle between "
            "the camera ray and the vertical Z axis. These are camera/view-axis parameters, not bottle rotation. The bottle "
            "yaw/object orientation is fixed and identical in all three cutouts; do not rotate the bottles themselves. "
            f"Mandatory camera/view parameters for this file: {spec_text}. "
            "Because the camera is high, all non-center tilt_from_z values are intentionally small. These angle values are "
            "mandatory; do not invent a different camera layout and do not rotate the bottles."
        )


    def upright_spatial_relation_text(self) -> str:
        return (
            "Mandatory upright spatial-occlusion rule: imagine all nine upright bottles are physically standing on one flat "
            "table, evenly spaced, and one real camera is mounted above the center cell looking downward. The center bottle is "
            "directly under the optical axis, so it must show only the top/cap/nozzle and a nearly symmetrical bottle rim; it "
            "must not show a side-biased bottle body. For all surrounding bottles, the visible body must appear on the side "
            "toward the optical-axis center of the 3x3 grid, because the cap/rim occludes the far side. This is a parallax/"
            "occlusion relationship, not bottle rotation. Use this mandatory visual table: top-left bottle = body visible "
            "mostly down-right from the cap; top-center bottle = body visible mostly downward from the cap; top-right bottle = "
            "body visible mostly down-left from the cap; middle-left bottle = body visible mostly right of the cap; center "
            "bottle = top-only cap/nozzle/rim, no side bias; middle-right bottle = body visible mostly left of the cap; "
            "bottom-left bottle = body visible mostly up-right from the cap; bottom-center bottle = body visible mostly "
            "upward/front-side from the cap; bottom-right bottle = body visible mostly up-left from the cap. The black cap and "
            "red nozzle remain centered on the top of each bottle; only the visible bottle body/rim shifts according to the "
            "camera parallax. Do not make all nine bottles share the same side-body direction, and do not rotate the nozzle/"
            "cap mark to fake the effect."
        )


    def build_pose_collection_prompt(self,
        item: dict[str, Any],
        pose_family: str = "combined",
        batch_key: str | None = None,
        surface_mode: str = "reference",
    ) -> str:
        dimension_text = self.dependencies.pose_collection_dimension_text()(item)
        camera_grid_text = self.dependencies.pose_collection_camera_batch_text()(item, batch_key, surface_mode)
        batch = next((entry for entry in self.dependencies.POSE_COLLECTION_BATCHES() if entry[0] == batch_key), None)
        batch_label = batch[1] if batch else "完整九视角"
        positions = batch[2] if batch else ["top-left", "top-center", "top-right", "middle-left", "center", "middle-right", "bottom-left", "bottom-center", "bottom-right"]
        position_count = len(positions)
        arrangement_text = (
            f"Create exactly {position_count} separated object cutouts in this single image, arranged left-to-right as: "
            f"{', '.join(positions)}. "
            if batch
            else "Create exactly nine separated object cutouts in a 3x3 collection sheet: top-left, top-center, top-right, middle-left, center, middle-right, bottom-left, bottom-center, bottom-right. "
        )
        source_summary = (
            "Use all attached reference images together. Some attached images may be frames automatically extracted from an "
            "uploaded rotation/flip video; treat them as multi-view evidence of the same physical object. Fuse visible details "
            "from every reference image to infer the object's 3D structure: front/back, left/right sides, top/bottom, cap/nozzle "
            "shape, transparent wall thickness, ridges, seams, and material highlights. Do not copy one reference frame blindly; "
            "use the full reference set to reconstruct a consistent object identity. "
        )
        surface_sentence = (
            "All requested objects must be visibly resting on the same reference tabletop/background from the input images, "
            "with equal spacing and a stable regular grid arrangement. The reference tabletop/background is intentional in "
            "this Step 1 image; it will be replaced in Step 2. "
            if surface_mode == "reference"
            else "All requested objects must be visibly resting on the same clean pure-white tabletop, with equal spacing and a stable regular grid arrangement. "
        )
        background_sentence = (
            "Use only the reference tabletop/background material from the input images as the scene background. Do not add unrelated "
            "props, labels, arrows, captions, borders, measurement marks, or decorative graphics. Natural lighting and contact shadows "
            "from the reference tabletop are acceptable in this Step 1 image. "
            if surface_mode == "reference"
            else "Use only a 100% pure white tabletop as the background. Do not add conveyor, floor, props, colored backing, green-screen, "
            "black matte, labels, arrows, captions, borders, measurement marks, decorative graphics, shadows, texture, stains, gradients, "
            "or color casts. "
        )
        if pose_family == "lying":
            title = (
                f"Generate LYING-FLAT Pose Collection batch '{batch_label}'"
                if batch
                else "Generate LYING-FLAT Pose Collection"
            )
            return (
                f"{title} for accessory '{item.get('name', 'accessory')}'. "
                "This prompt is complete and self-contained; do not borrow requirements from another prompt. "
                f"{source_summary}"
                "This is an image-to-image photorealistic product cutout task, not an illustration task. "
                "The attached real reference images are the visual source of truth. "
                "The object must look like the same real "
                "photographed item from the reference, with the same transparent glass/plastic body, cap ridges, red nozzle "
                "geometry, black collar, edge softness, refraction, specular highlights, surface noise, seams, dirt, and "
                f"manufacturing imperfections. {dimension_text}"
                "The pose in this file is LYING-FLAT ONLY: the object is lying flat on its side on an imaginary table. "
                "Do not include any upright, standing, front-elevation, or tall-side-view pose in this image. "
                f"{arrangement_text}"
                f"{surface_sentence}"
                "All requested objects have the same physical pose and the same world yaw/orientation: the cap/nozzle points in "
                "the same world direction in every requested cutout, and the bottle itself is not rotated between cutouts. "
                "The only thing that changes between cutouts is the camera/view-axis direction. "
                f"{camera_grid_text} "
                "If this batch contains the center cutout, render it as a true straight-down overhead view of the lying bottle "
                "with zero perspective bias. For non-center cutouts, render natural top-down camera-offset views: left cells look from "
                "the left, right cells look from the right, top cells look from the top/back, bottom cells look from the "
                "bottom/front, and corner cells combine both offsets. The non-center cutouts must visibly differ through "
                "real perspective distortion, foreshortening, ellipse/rim changes, and side-edge visibility, but they must "
                "not become different object rotations. Do not copy-paste the same sprite across the cutouts. "
                f"{background_sentence}"
                "Because the object is transparent, preserve "
                "clean glass/plastic highlights and contours without green/cyan spill, matte halos, or colored background residue. "
                "Keep each object fully visible, sharply bounded, separated from the others, and easy to segment later."
            )
        elif pose_family == "upright":
            title = (
                f"Generate UPRIGHT/STANDING Pose Collection batch '{batch_label}'"
                if batch
                else "Generate UPRIGHT/STANDING Pose Collection"
            )
            return (
                f"{title} for accessory '{item.get('name', 'accessory')}'. "
                "This prompt is complete and self-contained; do not borrow requirements from another prompt. "
                f"{source_summary}"
                "This is an image-to-image photorealistic product cutout task, not an illustration task. "
                "The attached real reference images are the visual source of truth. "
                "The object must look like the same real "
                "photographed item from the reference, with the same transparent glass/plastic body, cap ridges, red nozzle "
                "geometry, black collar, edge softness, refraction, specular highlights, surface noise, seams, dirt, and "
                f"manufacturing imperfections. {dimension_text}"
                "The pose in this file is UPRIGHT/STANDING ONLY: the object is vertical, standing on its base on an imaginary "
                "table, while the camera is mounted above the 3x3 arrangement and looks downward. Do not include any lying-flat "
                "pose in this image. This must be an overhead/top-down standing view, not a front elevation and not a tall "
                "side view of the whole bottle. The dominant visible feature should be the cap/nozzle/top opening, with only "
                "a partial rim/edge of the bottle body visible around it. "
                f"{arrangement_text}"
                f"{surface_sentence}"
                "All requested objects have the same physical pose and the same world yaw/orientation: the nozzle/cap mark points "
                "in the same world direction in every requested cutout, and the bottle itself is not rotated between cutouts. "
                "The only thing that changes between cutouts is the camera/view-axis direction. "
                f"{camera_grid_text} "
                f"{self.dependencies.upright_spatial_relation_text()()} "
                "If this batch contains the center cutout, render it as a true straight-down optical-axis view of the upright "
                "bottle: mostly cap/nozzle/top opening, symmetrical rim, no side bias, no front elevation. For non-center cutouts, render "
                "natural overhead camera-offset views: left cells look from the left, right cells look from the right, top "
                "cells look from the top/back, bottom cells look from the bottom/front, and corner cells combine both offsets. "
                "The non-center cutouts must visibly differ through cap ellipse changes, rim perspective, side-edge visibility, "
                "and foreshortening, but they must not become different object rotations. Do not copy-paste the same sprite "
                "across the cutouts. "
                f"{background_sentence}"
                "Because the object is transparent, preserve "
                "clean glass/plastic highlights and contours without green/cyan spill, matte halos, or colored background residue. "
                "Keep each object fully visible, sharply bounded, separated from the others, and easy to segment later."
            )
        else:
            return (
                f"Create one object-only Pose Collection image for the accessory '{item.get('name', 'accessory')}' "
                "using the uploaded reference photo as the visual source of truth. Generate both physical pose families: "
                "lying flat on the side and upright standing on the base. Cover meaningfully different camera positions, "
                "not only planar rotations."
            )


    def build_white_table_replacement_prompt(self, item: dict[str, Any], pose_family: str) -> str:
        pose_text = "UPRIGHT/STANDING" if pose_family == "upright" else "LYING-FLAT"
        return (
            f"Step 2 cleanup for the {pose_text} Pose Collection of accessory '{item.get('name', 'accessory')}'. "
            "Use the attached Step 1 pose-collection image as the main source. Keep every object exactly the same: same nine "
            "object identities, same positions, same 3x3 spacing, same perspective/parallax, same object size, same cap/nozzle "
            "orientation, same transparent material details, same edges, and same visible body/rim geometry. Do not redraw, "
            "rotate, move, resize, replace, simplify, or stylize any object. "
            "Only replace the tabletop/background material. Convert the entire table/background into a 100% pure white surface "
            "with RGB #FFFFFF appearance: no texture, no grain, no green tint, no stains, no gradients, no shadows, no contact "
            "shadows, no reflection, no color spill, and no checkerboard/alpha pattern. The final image should look like the "
            "same overhead photograph after the table material was changed to perfectly clean flat white. "
            "Preserve clean segmentation-friendly object boundaries. Do not add labels, arrows, captions, borders, extra props, "
            "or any unrelated scene elements."
        )


    def build_anchor_replacement_pose_prompt(self, item: dict[str, Any], pose_family: str) -> str:
        long_short_rule = (
            "Mandatory size rule: infer the replacement object's length from the longer visible side of the attached "
                "reference object, and infer its width from the shorter visible side. Preserve the reference long:short aspect "
                "ratio exactly. Map the source long edge to the anchor/bar long direction and the source short edge to the "
                "anchor/bar short direction. Do not swap length and width, and do not non-uniformly stretch, squash, or compress "
                "a long object just to fill the anchor footprint. For watch-like or other non-cylindrical accessories, the strap/"
                "body long axis must remain visibly long. "
        )
        if pose_family == "upright":
            return (
                "Priority camera-facing rule: the object's top must face the camera, and the visible top is the part we "
                "should see. "
                f"{long_short_rule}"
                "The first attached image is the anchor image. It contains nine metal bars. The second attached image is a "
                "circular end-face target guide for the same 3x3 layout; use it to preserve round/cylindrical top footprints "
                "and do not omit it when the object has a circular cap, nozzle, bottle mouth, lens, wheel, washer, or other round end. "
                "Replace each metal bar with the "
                "object from the other attached reference image(s). For every replacement, copy the matched bar's center "
                "position, long-axis direction, end-face direction, and perspective. The object's "
                "main axis must follow the bar's main axis, and the object's end-facing part must sit where that bar's "
                "square end face appears. "
                "Keep the anchor image's 3x3 layout, spacing, tabletop, background, camera angle, and framing unchanged. "
                "Remove all metal bars from the final image. Do not add anything else."
            )
        return (
            "Priority camera-facing rule: the object's side must face the camera, and the visible side surface is the part "
            "we should see. "
            f"{long_short_rule}"
            "The first attached image is the anchor image. It contains nine horizontal metal bars. Replace each metal bar "
            "with the object from the other attached reference image(s). A horizontal metal bar means the replacement object "
            "must also be horizontal. Keep each replacement object's position, long-axis direction, and perspective matched "
            "to the metal bar it replaces while preserving the source object's own long:short aspect. "
            "Keep the anchor image's 3x3 layout, spacing, tabletop, background, camera angle, and framing unchanged. "
            "Remove all metal bars from the final image. Do not add anything else."
        )

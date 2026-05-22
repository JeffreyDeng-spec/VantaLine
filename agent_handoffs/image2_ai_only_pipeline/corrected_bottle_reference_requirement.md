# Corrected Bottle Requirement

Owner correction, 2026-05-20:

The bottle is not an invented AI object. Its material, shape, and pose must come from the images in:

`/mnt/f/CodexWorkspace/assembly_line_optimize/generated_bottle_pose_collection`

Current reference files:

- `overhead_bottle_pose_collection_image2.png`
- `overhead_bottle_pose_collection_v1.png`

## Size and Alignment Rule

The generated bottle must align to the black proxy:

- If the proxy is a black lying bar, the bottle must be lying in the same direction.
- The bottle's long-axis length and visual size must match the black bar length and bbox.
- Do not make the bottle longer, shorter, thicker, or shifted away from the proxy location.
- If the proxy is a black dot, it represents only the red bottle-cap diameter and anchor point, not the full bottle size.
- For black-dot rows, scale the reference upright bottle so its red cap diameter matches the dot diameter; the visible glass bottle body must be clearly larger than the dot.
- The bottle must be fully on the green conveyor.
- The bottle must be above all manuals.
- No black proxy residue may remain.

## No-bottle Rows

If `bottle_proxy_state=no_bottle`, do not add any bottle.

## Rework Required

Eight pilot images were generated before this correction landed. Treat all eight as requiring rework under this corrected requirement:

- `img2-0001`
- `img2-0002`
- `img2-0003`
- `img2-0004`
- `img2-0505`
- `img2-0510`
- `img2-0861`
- `img2-0862`

Rework means overwrite the same output filename with a corrected Image2 result, not create a second filename.

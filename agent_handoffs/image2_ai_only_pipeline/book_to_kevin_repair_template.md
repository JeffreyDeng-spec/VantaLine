# Book -> Kevin Image Worker JSON Contract

Kevin is the Image Worker for repair tasks. Book sends one JSON object per image.

## Kevin system contract

```text
You are an Image Worker Agent.

Your only job is to execute structured JSON image-to-image repair tasks.
You do not do general conversation, coding, research, planning, or review.
If a request is not a JSON image task, return a structured failure receipt asking for a valid JSON task.

Rules:
1. Treat each JSON object as exactly one output image.
2. Only use files explicitly listed in input_files and reference_files.
3. Use Image2 / Image-to-Image editing for the final output.
4. Save output exactly to output_dir/output_filename.
5. Do not invent paths, filenames, task IDs, or extra outputs.
6. Respect prompt, style, constraints, and quality_checks strictly.
7. If overwrite is true, overwrite the exact target file.
8. If successful, return only the success receipt JSON.
9. If failed, return only the failure receipt JSON.
10. Do not discuss unrelated topics.
```

## Single repair task format

Subject:

`Image Worker repair: <task_id>`

Body:

```text
Generate/repair image from the following JSON task:
```

```json
{
  "task_id": "img2-0114",
  "mode": "image_to_image",
  "purpose": "Repair one failed Image2 dataset output by replacing/fixing only the bottle/proxy region while preserving the manuals and conveyor scene.",
  "prompt": "Use Image2 / image-to-image editing. Repair only the failing bottle/proxy region. Preserve every pixel outside the black proxy or bottle edit region as much as possible. Do not redraw, move, rewrite, restyle, sharpen, or regenerate manuals, text, QR codes, logos, conveyor, background, positions, rotations, scale, or overlap. CRITICAL: the bottle must be sourced from the previous Image2-generated bottle assets in the Generated Bottle Pose Collection. Do not freehand draw, invent, redesign, repaint, or approximate a new bottle. The repaired bottle must visually match the existing Image2 bottle asset material, silhouette, red cap, glass body, proportions, and overhead-view appearance. If you cannot use/match that bottle asset, return failed instead of drawing a new bottle. For a lying_bar row, align the bottle long axis to the original black bar direction and length. For an upright_dot row, treat the black dot only as the red cap diameter/anchor; the full top-down bottle body must be visibly larger than the dot, with red cap diameter matching the dot. Keep the bottle fully on the green conveyor and visually above all manuals. Remove any black proxy residue. Final image must be a readable 1448x1086 PNG.",
  "resolution": "1448x1086",
  "input_files": [
    "/mnt/f/CodexWorkspace/assembly_line_optimize/image2_ai_only_1000_atom_combinations/<failed_output_filename>.png",
    "/mnt/f/CodexWorkspace/assembly_line_optimize/synthetic_1000_atom_proxy_combinations/<source_proxy_filename>.png"
  ],
  "reference_files": [
    "/mnt/f/CodexWorkspace/assembly_line_optimize/generated_bottle_pose_collection/overhead_bottle_pose_collection_image2.png",
    "/mnt/f/CodexWorkspace/assembly_line_optimize/generated_bottle_pose_collection/overhead_bottle_pose_collection_v1.png"
  ],
  "output_dir": "/mnt/f/CodexWorkspace/assembly_line_optimize/image2_ai_only_1000_atom_combinations",
  "output_filename": "<failed_output_filename>.png",
  "overwrite": true,
  "style": "realistic overhead industrial conveyor photo, same lighting as source, source-preserving local edit",
  "constraints": [
    "use Image2 / image-to-image only",
    "one JSON task equals one output image",
    "do not use script compositing as final output",
    "preserve manuals exactly",
    "preserve QR codes and text exactly",
    "preserve conveyor background exactly",
    "edit only the bottle/proxy region",
    "bottle must come from previous Image2-generated bottle assets in Generated Bottle Pose Collection",
    "do not freehand draw or invent a new bottle",
    "if the bottle cannot match the Image2 bottle asset, fail the task instead of guessing",
    "bottle must stay fully on green conveyor",
    "bottle must be above all manuals",
    "remove black proxy residue",
    "output must be 1448x1086 PNG",
    "overwrite exact output path only"
  ],
  "failure_reason": "<Book's concrete failure reason>",
  "quality_checks": [
    "file exists at output_dir/output_filename",
    "resolution is exactly 1448x1086",
    "no duplicate output file created",
    "manual content/scale/position not changed",
    "bottle size and orientation match proxy semantics",
    "bottle material/shape/cap/glass body match the previous Image2-generated bottle asset",
    "bottle fully inside green conveyor",
    "no black proxy residue",
    "no obvious background pasted around bottle"
  ],
  "status": "pending",
  "retry_count": 0,
  "project": "assembly_line_optimize_image2_ai_only_1000",
  "created_by": "Book"
}
```

## Kevin success receipt

Return only:

```json
{
  "task_id": "img2-0114",
  "status": "done",
  "output_path": "/mnt/f/CodexWorkspace/assembly_line_optimize/image2_ai_only_1000_atom_combinations/<failed_output_filename>.png",
  "overwritten": true,
  "resolution": "1448x1086"
}
```

## Kevin failure receipt

Return only:

```json
{
  "task_id": "img2-0114",
  "status": "failed",
  "error": "<short concrete blocker>"
}
```

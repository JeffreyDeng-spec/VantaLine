# Urgent Image2 Rework: Failed Bottle Replacement Images 16, 21, 26

Owner request: rework only the failed generated photos where the bottle did not fully replace the black proxy.

Use Image2 for the edits. Overwrite the exact target PNG files when done.

## Source and Output

Project root:
`/mnt/f/CodexWorkspace/assembly_line_optimize`

Output directory to overwrite:
`/mnt/f/CodexWorkspace/assembly_line_optimize/image2_optimized_31_item_combinations`

Backup of failed current versions:
`/mnt/f/CodexWorkspace/assembly_line_optimize/image2_optimized_31_item_combinations/_failed_before_rework_20260519`

Reference files:
- Bottle model / pose reference:
  `/mnt/f/CodexWorkspace/assembly_line_optimize/generated_bottle_pose_collection/overhead_bottle_pose_collection_v1.png`
- Proxy originals:
  `/mnt/f/CodexWorkspace/assembly_line_optimize/synthetic_31_item_proxy_combinations`
- QA crops showing failures:
  `/mnt/f/CodexWorkspace/assembly_line_optimize/image2_optimized_31_item_combinations/qa_bottle_replacement_crops.jpg`

## Images to Rework

1. `16__bottle_proxy__manual_warranty_service__manual_battery_instruction.png`
   - Failure: black bar remains visible near the bottle/manuals; bottle replacement is incomplete and has bad nearby fragments.
   - Required: replace the original diagonal black bar with one complete lying bottle aligned to the proxy direction. No black stick residue.

2. `21__bottle_proxy__manual_download_service__manual_service_qr.png`
   - Failure: upright bottle is missing; the black dot/proxy was removed or lost instead of becoming a bottle.
   - Required: add one upright bottle top view exactly where the original dot proxy was. It should look like a real upright bottle/cap seen from overhead.

3. `26__bottle_proxy__manual_warranty_service__manual_battery_instruction__manual_download_service.png`
   - Failure: black vertical proxy remains behind/above the bottle.
   - Required: replace the original vertical black bar with one complete lying bottle aligned vertically. No black stick residue.

## Hard Acceptance Criteria

- Use Image2, not a script-based reconstruction.
- Preserve image size: `1448x1086`.
- Preserve all manual pages, printed text, QR codes, logos, scale, and positions as much as possible.
- Do not add torn paper fragments, duplicated manuals, or extra background patches.
- Bottle must fully replace the black proxy:
  - no visible black bar/dot remains;
  - bottle must be complete, not clipped unless the original proxy was at the edge;
  - bottle boundary must be clean and crisp;
  - no large pasted-in bottle source background should be visible.
- Match the realism level of the fifth source/background image: natural tabletop/conveyor lighting and contact shadow.

After completion, report the exact overwritten file paths and any residual risk.

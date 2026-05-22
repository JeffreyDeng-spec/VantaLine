# Jesse urgent fill: missing Image2 files 28-31

T J. confirmed the 31-photo set is still missing the back half. Mandy verified the output directory currently contains 01-23 and is missing 24-31.

Your urgent range:
- `28__bottle_proxy__manual_warranty_service__manual_download_service__manual_service_qr.png`
- `29__bottle_proxy__manual_battery_instruction__manual_download_service__manual_service_qr.png`
- `30__manual_warranty_service__manual_battery_instruction__manual_download_service__manual_service_qr.png`
- `31__bottle_proxy__manual_warranty_service__manual_battery_instruction__manual_download_service__manual_service_qr.png`

Input directory:
`F:\CodexWorkspace\assembly_line_optimize\synthetic_31_item_proxy_combinations\`

Output directory:
`F:\CodexWorkspace\assembly_line_optimize\image2_optimized_31_item_combinations\`

Reference:
- Bottle pose collection: `F:\CodexWorkspace\assembly_line_optimize\generated_bottle_pose_collection\overhead_bottle_pose_collection_v1.png`
- Realism target: `C:\Users\Administrator\iCloudDrive\iCloud~md~obsidian\Jeffrey\assambly_line_optimize\data\5.jpg`
- Bottle photos: `data\10.jpg`, `data\11.jpg`, `data\12.jpg`

Must use Image2:
- Use Image2 image edit/optimization for each target image.
- Do not use local scripted compositing as the final output.

Edit rules:
- Replace black bars/dots with the real bottle.
- Black bar = lying bottle in the same planar direction as the bar.
- Black dot = upright bottle, top-down view: red/orange nozzle top, black cap ring, circular transparent shoulder.
- Do not change manual content. Do not redraw/hallucinate/translate manual text, QR, logos.
- Do not change manual size relationship or layout; only improve light/shadow realism.
- Preserve `1448x1086`.
- If an output file already exists, inspect it briefly and skip unless clearly broken.

Report back:
- Count of generated files.
- Any failed Image2 calls.
- Set issue to review when done.

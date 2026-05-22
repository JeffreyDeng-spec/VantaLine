# Jesse task: Image2 optimize 17-31

Owner request from T J.:
Use Image2 to optimize the second half of the 31 synthetic item-combination photos.

Your range:
- Input files: `F:\CodexWorkspace\assembly_line_optimize\synthetic_31_item_proxy_combinations\17*.png` through `31*.png`
- Output directory: `F:\CodexWorkspace\assembly_line_optimize\image2_optimized_31_item_combinations\`
- Output filenames must preserve the same basename, e.g. `17__bottle_proxy__manual_warranty_service__manual_download_service.png`

Critical requirement:
- You must use Image2 for the visual optimization/editing. Do not locally script the final visual replacement.
- Treat each existing PNG as the edit target/reference layout.

Reference images and assets:
- Input proxy set: `F:\CodexWorkspace\assembly_line_optimize\synthetic_31_item_proxy_combinations\`
- Manifest: `F:\CodexWorkspace\assembly_line_optimize\synthetic_31_item_proxy_combinations\manifest.json`
- Bottle visual reference: `F:\CodexWorkspace\assembly_line_optimize\generated_bottle_pose_collection\overhead_bottle_pose_collection_v1.png`
- Original bottle photos for reference: `C:\Users\Administrator\iCloudDrive\iCloud~md~obsidian\Jeffrey\assambly_line_optimize\data\10.jpg`, `11.jpg`, `12.jpg`
- Realism target/reference: `C:\Users\Administrator\iCloudDrive\iCloud~md~obsidian\Jeffrey\assambly_line_optimize\data\5.jpg`

Image2 edit instructions for every file:
1. Make the whole photo more realistic, matching the realism of `data\5.jpg`: real overhead conveyor/table lighting, contact shadows, subtle scratches, reflections, surface interaction.
2. Replace every black bottle proxy with the actual bottle.
3. A black line/bar means a lying bottle. The bottle must lie on the conveyor in the same planar direction as the bar:
   - horizontal bar -> horizontal lying bottle
   - vertical bar -> vertical lying bottle
   - diagonal bar -> diagonal lying bottle with the same angle
4. A black dot means the bottle is upright on the conveyor. It should be a top-down upright bottle view: red/orange nozzle top, black cap ring, circular transparent shoulder.
5. Do not change the manual content. Do not rewrite, blur, hallucinate, translate, or redraw the printed manual text/QR/logos.
6. Do not change the manual size relationship or positions except for tiny realism-only lighting/shadow integration.
7. Do not add extra objects, labels, arrows, text, people, or annotations.
8. Preserve image size `1448x1086`.

Acceptance checks before reporting back:
- Exactly 15 output PNGs exist for files 17-31.
- Every file with a proxy has the proxy replaced by a realistic bottle.
- Manual contents remain visually the same as the input.
- Output still looks like a top-down industrial inspection photo.
- Report output path, completed file count, and any files that failed or need manual retry.

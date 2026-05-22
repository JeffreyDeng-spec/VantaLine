# Single Image2 Job for Jesse: sample 0501

Use Image2 / AI image editing for exactly one image. Do not use scripts to create the final image.

Input:
`/mnt/f/CodexWorkspace/assembly_line_optimize/synthetic_1000_atom_proxy_combinations/0501__false__missing_1__combo_bottle_proxy__manual_battery_instruction__manual_download_service__manual_service_qr__copy_001.png`

Output:
`/mnt/f/CodexWorkspace/assembly_line_optimize/image2_ai_only_1000_atom_combinations/0501__false__missing_1__combo_bottle_proxy__manual_battery_instruction__manual_download_service__manual_service_qr__copy_001.png`

Bottle instruction:
This image contains a black bottle proxy. State: lying_bar. Proxy bbox: [338, 480, 486, 769]. Replace it with a realistic glass bottle. If it is a black bar, create a lying bottle aligned with that bar. If it is a black dot, create an upright top-down bottle/cap. The bottle must be fully on the green conveyor and visually above every manual.

Hard constraints:
- Produce exactly one PNG for this sample only.
- Keep exact filename.
- Keep resolution 1448x1086.
- Preserve manual count, layout, rotation, overlap, text, QR codes, and logos as much as possible.
- Bottle must not be outside the green conveyor.
- Bottle must not be under any paper.
- No black proxy residue.
- No pasted source-background patch.

After saving, report only: saved path, whether it passed QA, and any retry note.

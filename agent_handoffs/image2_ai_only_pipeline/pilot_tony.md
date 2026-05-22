# Tony Pilot: Image2 AI-only 10 Images

This is a pilot batch, not the full 500-image range.

Use:

- Queue source: `/mnt/f/CodexWorkspace/assembly_line_optimize/agent_handoffs/image2_ai_only_pipeline/tony_pilot_20_tasks.csv`
- Worker protocol: `/mnt/f/CodexWorkspace/assembly_line_optimize/agent_handoffs/image2_ai_only_pipeline/worker_protocol.md`
- Output folder: `/mnt/f/CodexWorkspace/assembly_line_optimize/image2_ai_only_1000_atom_combinations`

Assigned pilot rows:

- `img2-0001`
- `img2-0002`
- `img2-0003`
- `img2-0004`
- `img2-0005`
- `img2-0006`
- `img2-0501`
- `img2-0502`
- `img2-0503`
- `img2-0504`

Execution:

1. Process one row at a time through Image2 / AI image editing.
2. Save to the exact `output_path` from the CSV.
3. QA the file before moving to the next row.
4. Comment after every image with saved path, pass/fail, and retry note.
5. Stop and report immediately if your runtime cannot create/save the first AI-only image.

Do not use script compositing as a substitute.


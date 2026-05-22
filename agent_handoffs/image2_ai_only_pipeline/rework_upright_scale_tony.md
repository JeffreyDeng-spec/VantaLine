# Tony: Rework Upright-dot Bottle Scale

The task had a wrong upright-dot interpretation. The black dot is only the red cap diameter/anchor, not the full bottle size.

Read first:

- `/mnt/f/CodexWorkspace/assembly_line_optimize/agent_handoffs/image2_ai_only_pipeline/upright_dot_scale_correction.md`
- `/mnt/f/CodexWorkspace/assembly_line_optimize/agent_handoffs/image2_ai_only_pipeline/worker_protocol.md`

Task CSV:

`/mnt/f/CodexWorkspace/assembly_line_optimize/agent_handoffs/image2_ai_only_pipeline/tony_upright_scale_rework_tasks.csv`

Rework all assigned rows by overwriting the same output filenames.

Core requirement:

Use the Generated Bottle Pose Collection. For each upright-dot row, make the red cap diameter match the original black dot diameter, while the full upright bottle body is visibly larger than the dot and centered on the original anchor. Do not shrink the whole bottle to the black dot.

Report per image: saved path, pass/fail, retry note.


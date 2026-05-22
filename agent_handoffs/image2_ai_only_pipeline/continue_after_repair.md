# Continue Production After Repair

Owner instruction: after the current bad-output repair is complete, continue generating the remaining images in the 1000-image dataset.

Current count before this continuation plan:

- Generated files: `134`
- Missing files: `866`

Do not continue blindly if repair blockers remain. The order is:

1. Finish the current repair task:
   - fix previous upright-scale errors;
   - audit/repair wrong bottle shape/material outputs;
   - report unresolved blockers.
2. If no unresolved blocker remains, start the next controlled production batch.
3. Continue with exact queue rows and exact output filenames.

## Next Controlled Production Batch

Tony next batch:

`/mnt/f/CodexWorkspace/assembly_line_optimize/agent_handoffs/image2_ai_only_pipeline/tony_resume_after_repair_next50.csv`

Assigned rows: `img2-0107` through `img2-0156`.

Jesse next batch:

`/mnt/f/CodexWorkspace/assembly_line_optimize/agent_handoffs/image2_ai_only_pipeline/jesse_resume_after_repair_next50.csv`

Assigned rows: `img2-0171` through `img2-0220`.

## Generation Rules

- Use Image2 / AI edit per final image.
- Do not use scripted compositing as final output.
- Bottle material/shape must come from:

`/mnt/f/CodexWorkspace/assembly_line_optimize/generated_bottle_pose_collection`

- Lying bar: bottle long axis follows bar direction and length.
- Upright dot: black dot is red cap diameter/anchor only; full upright bottle body is larger than the dot.
- Bottle must be on green conveyor and above manuals.
- Preserve manuals, text, QR/logos, positions, rotations, scale, and overlap.
- Output must be exact `1448x1086`.

## Progress Reporting

During production continuation:

- comment every 10 completed files;
- stop immediately on a repeated Image2 blocker;
- do not fabricate fallback outputs;
- keep working through the assigned 50 unless a real blocker appears.


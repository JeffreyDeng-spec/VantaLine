# Upright-dot Scale Correction

Owner correction, 2026-05-20:

The black dot does not represent the full upright bottle size.

Correct interpretation:

- The black dot represents the red bottle-cap diameter and placement anchor.
- For upright/top-down bottles, scale the reference bottle so the red cap diameter matches the black dot diameter.
- The visible glass shoulder/body footprint must be clearly larger than the black dot, following the bottle proportions in:

`/mnt/f/CodexWorkspace/assembly_line_optimize/generated_bottle_pose_collection`

Do not shrink the whole bottle to the black dot size.

## Rework Scope

Existing generated upright-dot outputs needing rework: `33`.

Task CSV:

`/mnt/f/CodexWorkspace/assembly_line_optimize/agent_handoffs/image2_ai_only_pipeline/upright_scale_rework_existing_outputs.csv`

Split files:

- Tony: `tony_upright_scale_rework_tasks.csv`
- Jesse: `jesse_upright_scale_rework_tasks.csv`

## Acceptance

For every upright-dot rework:

- output filename is unchanged;
- output resolution is `1448x1086`;
- black dot is fully removed;
- red cap diameter aligns to the original black dot diameter;
- full upright bottle body is visibly larger than the dot according to the reference collection;
- bottle is centered at the original dot anchor;
- bottle stays on the green conveyor;
- bottle is visually above all manuals;
- manual count/layout/text/QR/logo remain stable.


# Image2 Optimize 1000 Atom Proxy Dataset: Jesse 0501-1000

Owner request: use AI/Image2 to optimize the randomized proxy sketches into realistic training photos.

You are not alone in this folder. Tony is handling `0001-0500`. Do not overwrite Tony's range. Do not revert or modify files outside your assigned range.

## Input

Input folder:

`/mnt/f/CodexWorkspace/assembly_line_optimize/synthetic_1000_atom_proxy_combinations`

Assigned input files:

`0501*.png` through `1000*.png`

Metadata:

- `/mnt/f/CodexWorkspace/assembly_line_optimize/synthetic_1000_atom_proxy_combinations/labels.csv`
- `/mnt/f/CodexWorkspace/assembly_line_optimize/synthetic_1000_atom_proxy_combinations/manifest.json`

Bottle reference:

`/mnt/f/CodexWorkspace/assembly_line_optimize/generated_bottle_pose_collection/overhead_bottle_pose_collection_v1.png`

## Output

Output folder:

`/mnt/f/CodexWorkspace/assembly_line_optimize/image2_optimized_1000_atom_proxy_combinations`

Save exactly 500 PNGs in this folder using the exact same filenames as the input files.

## Required AI Work

Use Image2 / AI image editing for the final visual output.

For each assigned image:

1. Preserve the randomized layout exactly:
   - same background framing;
   - same manual positions;
   - same manual angles;
   - same manual overlap/stacking;
   - same bottle proxy position and orientation.
2. Preserve all manual content:
   - text, QR codes, logos, page size, page orientation must not be rewritten or hallucinated.
3. If the image contains a black bottle proxy:
   - black bar = lying glass bottle, aligned with the bar direction;
   - black dot = upright bottle top-down view;
   - the glass bottle must completely replace the black proxy;
   - no black bar/dot residue may remain;
   - the bottle must be complete and have clean boundaries;
   - no pasted source-background patch around the bottle;
   - critical: the bottle must be visually above every manual page, never tucked under paper.
4. If the image does not contain a black bottle proxy:
   - do not add a bottle;
   - only make the image more realistic if needed while preserving the object set.

## Quality Failure Cases To Avoid

Reject and retry any output with:

- black stick/dot still visible;
- bottle missing or incomplete;
- bottle placed under paper;
- unclear bottle edge;
- obvious pasted-in background around bottle;
- changed manual text/QR/logo;
- added extra objects;
- removed an existing manual;
- wrong filename or wrong resolution.

Required resolution: `1448x1086`.

## Report Back

When done, report:

- number of PNGs written;
- any files you could not complete;
- any residual quality risks.

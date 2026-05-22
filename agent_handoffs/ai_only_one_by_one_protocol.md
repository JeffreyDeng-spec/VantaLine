# Mandatory One-by-One Image2 Protocol

Owner clarification: You do not need any API key. Use the available OpenAI/Image2 capability directly.

This overrides any previous ambiguity in the AI-only regeneration task.

## Execution Protocol

Process your assigned range one image at a time:

1. Take exactly one input PNG.
2. Use Image2 / AI generation or AI image editing to produce exactly one final PNG.
3. Save it to:
   `/mnt/f/CodexWorkspace/assembly_line_optimize/image2_ai_only_1000_atom_combinations`
4. Use the exact same filename as the input PNG.
5. Run a quick local QA on that one output:
   - resolution is `1448x1086`;
   - no black stick/dot remains if a bottle proxy existed;
   - generated bottle is fully on the green conveyor belt;
   - generated bottle is visually above all manuals;
   - if the input had no bottle proxy, do not add a bottle;
   - object count and manual layout are preserved.
6. Only after that single file passes, move to the next file.

Do not batch-composite with scripts. Do not create final images through scripted cutout/paste/drawing. Scripts are only allowed for file counting and QA.

## Progress Reporting

Keep working continuously until your assigned 500 files are complete. Every 25 completed files, add a short comment with:

- completed count in your range;
- latest filename;
- any failed/retried filenames.

If one file fails, retry it immediately before moving on.

## Existing Output

Do not delete or modify:

`/mnt/f/CodexWorkspace/assembly_line_optimize/image2_optimized_1000_atom_proxy_combinations`

Only write to:

`/mnt/f/CodexWorkspace/assembly_line_optimize/image2_ai_only_1000_atom_combinations`

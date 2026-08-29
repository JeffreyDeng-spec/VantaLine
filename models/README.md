# Model Artifacts

**Status: Authoritative**

This folder documents how VantaLine handles model artifacts.

Actual trained weights are not committed to Git. A model belongs to a task,
route, and training run, so it should be produced by the workflow and stored in
runtime storage or external artifact storage.

Generated task models are normally stored under:

```text
local_inspection_service/data/outputs/training_runs/<task_id>/
```

Each task-trained run should carry metadata that identifies:

- task id,
- selected accessory ids,
- required accessory counts,
- YOLO class-to-accessory mapping,
- model variant (`yolo` or `yolo_ocr`),
- artifact path,
- OCR accessory ids where relevant.

## Not Tracked In Git

- Full training datasets.
- Full YOLO run folders.
- Intermediate checkpoints.
- Temporary or experimental task models.
- Uploaded media and runtime/service outputs.
- Provider keys or runtime secret files.

If a deployment needs a base checkpoint or a promoted production model, provide
it through environment configuration or the runtime model library instead of
placing the binary in the source repository.

# Model Artifacts

This folder stores small deployable model artifacts that are safe to keep in the private repository.

Tracked:

- `current_2class_yolo26s_seg_best.pt`  
  Current deployed YOLO26 segmentation model. It detects two geometric classes:
  `bottle` and generic `manual`. The local service then uses OCR to map generic
  manual detections into four business manual classes.

Not tracked:

- Full training datasets.
- Full YOLO run folders.
- Intermediate checkpoints.
- Ongoing five-class training outputs.

Those larger artifacts remain in the local project workspace and are documented in the root README.

# Local Inspection Service

FastAPI prototype for local assembly-line inspection.

## Run

```bash
cd /mnt/f/CodexWorkspace/assembly_line_optimize
python3 -m uvicorn local_inspection_service.server:app --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765
```

## Features

- Upload one image and return a five-class pass/fail decision.
- Upload video and sample frames with the same rule engine.
- Chinese frontend UI with inspection progress bar.
- Rule editor for required classes, minimum counts, and confidence threshold.
- Parts/reference upload placeholder for future dataset generation.
- Reserved live-stream configuration for future camera/RTSP/folder-watch input.

## Current Inference Mode

The current deployed mode uses:

1. YOLO26 segmentation for bottle/manual localization.
2. PaddleOCR on detected manual crops.
3. Keyword matching to map manuals into four business manual classes.

The local service returns five business classes even though the deployed YOLO model itself has two geometric classes.

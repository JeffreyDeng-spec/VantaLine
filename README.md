# VantaLane

VantaLane is a local-first visual inspection toolflow for building inspection
tasks from user-defined accessories, generating training datasets, training or
selecting detection models, and checking images or videos against the selected
task rule.

The original bottle plus four manuals setup is now treated as the included
reference task. It remains useful for validation and examples, but it is not the
product boundary: VantaLane is intended to support arbitrary inspection
accessories and multiple detection methods.

## What VantaLane Does

- Maintains an accessory library with object and text/manual-like items.
- Stores reference images, normalized assets, AI profiles, and task metadata for
  each accessory.
- Builds task-specific training datasets from selected accessories, production
  backgrounds, pass/fail rules, and generated previews.
- Trains or loads task models for inspection.
- Runs image and video inspection through the selected task and model.
- Exposes a local web UI for accessory management, dataset generation, model
  training, training-library cleanup, AI detection settings, and inspection.

The core rule is task-centric: an inspection task defines the required
accessories and expected counts. The active detector then reports whether the
current image satisfies that task.

## Detection Methods

VantaLane supports several detection paths through the same inspection flow:

| Method | Purpose | Notes |
| --- | --- | --- |
| YOLO | Fast object or accessory detection from a trained task model. | Best when visual classes are sufficiently distinct or enough training data is available. |
| YOLO + OCR | YOLO localizes objects, OCR disambiguates text-heavy accessories. | Useful for manuals, cards, labels, QR sheets, and accessories that differ mainly by printed text. |
| AI Detection API | A stateless multimodal API checks the image against structured accessory profiles. | Useful as an API-backed option or fallback when a local model has not been trained yet. |

These are model choices for the same task model selector, not separate products.
A task may expose only the model variants that exist for that task.

## Typical Toolflow

1. Add accessories.
   - Upload source photos or documents.
   - Mark each accessory as an object-like or text-like item.
   - Let the service normalize assets and generate a structured AI profile.

2. Build a training dataset.
   - Select one or more accessories for a task.
   - Choose same-environment backgrounds and sample counts.
   - Preview generated pass/fail samples before creating the full dataset.
   - The current false-sample policy emphasizes missing-one cases and includes
     controlled extra-accessory negatives.

3. Train or select a model.
   - Train a YOLO or YOLO + OCR task model from a generated dataset.
   - Reuse completed training runs from the training library.
   - Keep the old built-in bottle/manual models as reference models.

4. Inspect images or videos.
   - Select a task and one available model method.
   - Upload an image or video.
   - Receive pass/fail status, detections, counts, rule evidence, and output
     imagery from the same API shape.

5. Iterate.
   - Add more accessory evidence.
   - Generate richer datasets.
   - Retrain task models.
   - Compare YOLO, YOLO + OCR, and AI Detection behavior.

## Repository Layout

```text
local_inspection_service/
  FastAPI service, Chinese web UI, accessory management, dataset generation,
  model training, AI detection config, and inspection APIs.

models/
  Small deployable reference weights that are safe to keep in the private repo.

scripts/
  Dataset-generation and asset-preparation scripts used by the reference task.

standardized_manuals/
  Canonical manual assets from the original reference task.

backgrounds/
  Same-environment conveyor/background assets and background-set metadata.

generated_bottle_pose_collection/
  Bottle pose reference images used by the historical reference dataset.

agent_handoffs/ and qa_reports/
  Historical implementation, review, and QA artifacts.
```

Generated datasets, uploads, training runs, temporary outputs, and full YOLO run
folders are intentionally ignored by Git.

## Local Service Quick Start

```bash
cd /mnt/f/CodexWorkspace/assembly_line_optimize
python3 -m pip install -r requirements.txt
python3 -m uvicorn local_inspection_service.server:app --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765
```

For LAN or Mac access, see `local_inspection_service/README.md`.

## Current Reference Configuration

The default committed reference task contains five historical accessories:

1. Bottle
2. Warranty Service Manual
3. Battery Instruction Manual
4. Download Service Manual
5. Service QR Manual

This setup demonstrates two important patterns:

- Object accessories, such as the bottle, can be detected directly.
- Text-heavy accessories, such as similar manuals, may need OCR or AI profile
  evidence because their shape and size are almost identical.

Reference model artifacts include:

- `models/current_2class_yolo26s_seg_best.pt`
  - Detects bottle and generic manual geometry.
  - The service uses OCR to map manual crops into business manual classes.
- `models/current_5class_yolo26s_seg_best.pt`
  - Detects the five reference classes directly.

New tasks should not copy the five-class assumption. They should define their
own selected accessories, expected counts, generated dataset, model variant, and
inspection rule metadata.

## AI Detection Configuration

AI Detection is configured locally through the web UI or environment variables.
Supported provider modes are:

- `gemini`
- `openai`
- `openai_compatible`

Useful environment variables:

```bash
INSPECTION_AI_PROVIDER=gemini
INSPECTION_AI_MODEL=gemini-2.5-flash
INSPECTION_AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
INSPECTION_AI_API_KEY=...
INSPECTION_AI_API_KEY_ENV=GEMINI_API_KEY
INSPECTION_AI_TIMEOUT_SECONDS=10
```

When no provider key is configured, accessory profile generation falls back to a
local deterministic profile so the rest of the toolflow can still run. Live AI
inspection requires a configured provider key.

## Development Checks

Use the targeted checks that match the files changed:

```bash
python3 -m py_compile local_inspection_service/server.py local_inspection_service/scripts/*.py
node --check local_inspection_service/static/app.js
python3 local_inspection_service/scripts/smoke_ai_detection.py
python3 local_inspection_service/scripts/verify_task_pipeline.py
python3 local_inspection_service/scripts/smoke_cross_device_upload.py --host 0.0.0.0 --port 8876
git diff --check
```

Some checks may require local model weights, PaddleOCR runtime compatibility,
or an available AI provider key.

## Runtime Notes

- Python 3.12 is the current local runtime.
- Core server dependencies are FastAPI, Uvicorn, OpenCV, NumPy, Ultralytics,
  PaddleOCR, PaddlePaddle, Pydantic, and Requests.
- PaddleOCR is sensitive to PaddlePaddle runtime versions in this environment;
  `paddlepaddle==3.2.2` is the known working version.
- The service stores local uploads and outputs under
  `local_inspection_service/data/`.
- Large generated artifacts should stay out of Git and be reproduced through the
  tracked scripts or the service UI.

## Project Status

VantaLane is a working local prototype, not a packaged production deployment.
The strongest current use case is rapid development and validation of visual
inspection workflows:

- define accessories,
- generate task datasets,
- train or select a detector,
- inspect images/videos,
- collect evidence,
- iterate on the task.

Production deployment still needs environment-specific validation for camera
calibration, lighting, real-photo datasets, model accuracy, AI provider
latency, and artifact packaging.

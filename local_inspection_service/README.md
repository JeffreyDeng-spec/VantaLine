# Inspection Service

This directory contains the FastAPI service and web UI for the VantaLine
inspection workflow.

The service is no longer limited to the original five fixed package components.
It supports user-defined accessories, task-specific training datasets, multiple
detection methods, and image/video inspection through a single web UI.

## Run

Install dependencies from a cloned repository, then choose the bind host and
port for the target environment:

```bash
git clone https://github.com/JeffreyDeng-spec/VantaLine.git
cd VantaLine
python3 -m pip install -r requirements.txt
python3 -m uvicorn local_inspection_service.server:app --host <host> --port <port>
```

Open the service URL configured by the operator:

```text
http://<service-host>:<port>
```

For remote access, expose the service through the operator's deployment
environment, reverse proxy, container platform, or network policy. Keep the
public endpoint and the API endpoint on the same origin when possible.

## Main UI Areas

- Inspect: choose a task and model method, then upload an image or video.
- Accessories: add object or text accessories, upload reference media, review
  normalized assets, and maintain AI profile references.
- Model Training: choose accessories, preview generated samples, generate full
  datasets, and train YOLO or YOLO + OCR task models.
- Training Library: inspect, rename, delete, or reuse generated datasets and
  trained model runs.
- AI Detection Settings: configure Gemini API access from the web UI. Backend
  environment settings also support OpenAI and OpenAI-compatible provider modes
  for structured AI inspection.

## Task And Model Selection

Inspection is task-centric:

1. The task menu selects the accessory set and expected counts.
2. The model menu shows only detection methods available for that task.
3. Image and video requests submit the selected `model_id`.

Supported model methods:

- YOLO: task model detects selected accessories directly.
- YOLO + OCR: YOLO localizes candidate accessory classes and OCR supplies text
  evidence. The bundled manual reference flow has OCR-to-manual resolution;
  task-trained `yolo_ocr` variants still use YOLO class/accessory IDs for
  pass/fail unless the task adds explicit OCR/profile-to-accessory resolution.
- AI Detection: a stateless provider call checks the image against structured
  accessory profiles.

The original bottle/manual models remain available as reference models, but new
tasks should use their own accessory selections and trained artifacts.

## Important API Endpoints

```text
GET    /api/status
GET    /api/config
GET    /api/accessories
POST   /api/accessories
POST   /api/accessories/preview
POST   /api/accessories/confirm/{candidate_id}
POST   /api/accessories/{accessory_id}/files
DELETE /api/accessories/{accessory_id}

POST   /api/training/preview
POST   /api/training/generate
POST   /api/training/start
GET    /api/training/status
GET    /api/training/resources

GET    /api/ai/config
POST   /api/ai/config
DELETE /api/ai/config/key

POST   /api/analyze/image
POST   /api/analyze/video
POST   /api/stream/config
```

Generated files are served from `/outputs/...` and stored under
`local_inspection_service/data/outputs/`.

## Accessory And Dataset Flow

1. Add an accessory with a name, material type, training role, and reference
   files.
2. The server stores source files under `data/uploads/`, normalizes reusable
   assets under `data/normalized_assets/`, and generates or falls back to an
   `ai_profile`.
3. The training view selects accessories and backgrounds, then creates a preview
   under `data/outputs/training_previews/`.
4. Dataset generation writes images, YOLO labels, boxed previews, and a manifest
   under `data/outputs/training_datasets/<task_id>/`.
5. Model training writes run artifacts under
   `data/outputs/training_runs/<task_id>/`.

The generated dataset manifest records selected accessories, exact-count
requirements, class maps, background metadata, false-sample policy, and model
variant details needed by inference.

## AI Detection

AI Detection uses a structured, stateless request:

- one inspection image,
- required accessory profiles,
- expected counts,
- optional reference descriptors,
- a strict JSON output schema.

Configure Gemini through the current web UI. Configure Gemini, OpenAI, or
OpenAI-compatible backend modes with environment variables or saved service
settings:

```bash
INSPECTION_AI_PROVIDER=gemini
INSPECTION_AI_MODEL=gemini-2.5-flash
INSPECTION_AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
INSPECTION_AI_API_KEY=...
INSPECTION_AI_API_KEY_ENV=GEMINI_API_KEY
INSPECTION_AI_TIMEOUT_SECONDS=10
```

If the provider is not configured, accessory profile generation falls back to a
deterministic profile. AI inspection itself reports structured provider status
rather than crashing the server.

## Cross-Origin And Remote Use

File inputs in the browser upload bytes with `multipart/form-data`; the service
stores uploaded streams under `local_inspection_service/data/uploads`. The server
never reads a path from the client filesystem.

Open the same URL that serves the web UI when possible, so browser requests are
same-origin and do not require CORS. For trusted proxy, tunnel, or separate
frontend deployments that call the API from another origin, add explicit
origins:

```bash
INSPECTION_CORS_ORIGINS=https://inspection.example.internal,https://frontend.example.internal \
python3 -m uvicorn local_inspection_service.server:app --host <host> --port <port>
```

Untrusted cross-origin write requests are rejected. This protects file-mutating
routes such as accessory preview and confirm from arbitrary browser origins.

## Smoke Checks

Run the checks that match the changed area:

```bash
cd VantaLine
python3 -m py_compile local_inspection_service/server.py local_inspection_service/scripts/*.py
npm --prefix local_inspection_service/frontend run typecheck
npm --prefix local_inspection_service/frontend run build:production-cutover
python3 local_inspection_service/scripts/smoke_phase1_core_cleanup.py
python3 local_inspection_service/scripts/smoke_ai_detection.py
python3 local_inspection_service/scripts/verify_task_pipeline.py
```

Run a multipart upload check:

```bash
cd VantaLine/local_inspection_service
python3 scripts/smoke_cross_device_upload.py --host <host> --port <port>
```

To verify an explicit trusted cross-origin frontend:

```bash
INSPECTION_CORS_ORIGINS=https://frontend.example.internal \
python3 scripts/smoke_cross_device_upload.py --host <host> --port <port> --origin https://frontend.example.internal --expect-cors allowed
```

To verify an untrusted origin is not allowed:

```bash
python3 scripts/smoke_cross_device_upload.py --host <host> --port <port> --origin https://untrusted.example --expect-cors denied
```

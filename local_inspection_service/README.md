# Local Inspection Service

This directory contains the FastAPI service and web UI for the VantaLane local
inspection toolflow.

The service is no longer limited to the original five fixed package components.
It supports user-defined accessories, task-specific training datasets, multiple
detection methods, and image/video inspection through a single local UI.

## Run

Same-machine use:

```bash
cd /mnt/f/CodexWorkspace/assembly_line_optimize
python3 -m uvicorn local_inspection_service.server:app --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765
```

Mac/LAN browser use:

```bash
cd /mnt/f/CodexWorkspace/assembly_line_optimize
python3 -m uvicorn local_inspection_service.server:app --host 0.0.0.0 --port 8765
```

Find this machine's LAN address:

```bash
hostname -I
```

Open from the client machine with the reachable host address:

```text
http://<this-machine-lan-ip>:8765
```

When the service runs inside WSL2, `hostname -I` returns the WSL internal IP,
not the Windows host LAN IP. A physical Mac usually cannot reach that WSL IP
directly. In that case, expose the WSL service through the Windows host with an
elevated PowerShell:

```powershell
$wslIp = (wsl.exe hostname -I).Trim().Split()[0]
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8765 connectaddress=$wslIp connectport=8765
New-NetFirewallRule -DisplayName "Alook Local Inspection 8765" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765
netsh interface portproxy show v4tov4
```

Then open from the Mac with the Windows host address, for example:

```text
http://192.168.1.40:8765
http://100.103.240.14:8765
```

## Main UI Areas

- Inspect: choose a task and model method, then upload an image or video.
- Accessories: add object or text accessories, upload reference media, review
  normalized assets, and maintain AI profile references.
- Model Training: choose accessories, preview generated samples, generate full
  datasets, and train YOLO or YOLO + OCR task models.
- Training Library: inspect, rename, delete, or reuse generated datasets and
  trained model runs.
- AI Detection Settings: configure Gemini, OpenAI, or OpenAI-compatible API
  access for structured AI inspection.

## Task And Model Selection

Inspection is task-centric:

1. The task menu selects the accessory set and expected counts.
2. The model menu shows only detection methods available for that task.
3. Image and video requests submit the selected `model_id`.

Supported model methods:

- YOLO: task model detects selected accessories directly.
- YOLO + OCR: YOLO localizes candidate regions and OCR resolves text-heavy
  accessories.
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

Generated files are served from `/outputs/...` and stored locally under
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

Configure it through the UI or with environment variables:

```bash
INSPECTION_AI_PROVIDER=gemini
INSPECTION_AI_MODEL=gemini-2.5-flash
INSPECTION_AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
INSPECTION_AI_API_KEY=...
INSPECTION_AI_API_KEY_ENV=GEMINI_API_KEY
INSPECTION_AI_TIMEOUT_SECONDS=10
```

If the provider is not configured, accessory profile generation falls back to a
local deterministic profile. AI inspection itself reports structured provider
status rather than crashing the server.

## Cross-Origin And LAN Use

File inputs in the browser upload bytes with `multipart/form-data`; the service
stores uploaded streams under `local_inspection_service/data/uploads`. The server
never reads a path from the client filesystem.

Direct LAN use should open the same URL that serves the web UI, so it is
same-origin and does not require CORS. For trusted proxy or tunnel frontends
that call the API from another origin, add explicit origins:

```bash
INSPECTION_CORS_ORIGINS=http://mac-hostname.local:8765,http://192.168.1.20:8765 \
python3 -m uvicorn local_inspection_service.server:app --host 0.0.0.0 --port 8765
```

Only use broad private-LAN CORS during trusted local debugging:

```bash
INSPECTION_ENABLE_LAN_CORS=1 python3 -m uvicorn local_inspection_service.server:app --host 0.0.0.0 --port 8765
```

Untrusted cross-origin write requests are rejected. This protects local
file-mutating routes such as accessory preview and confirm from arbitrary
browser origins.

## Smoke Checks

Run the checks that match the changed area:

```bash
cd /mnt/f/CodexWorkspace/assembly_line_optimize
python3 -m py_compile local_inspection_service/server.py local_inspection_service/scripts/*.py
node --check local_inspection_service/static/app.js
python3 local_inspection_service/scripts/smoke_ai_detection.py
python3 local_inspection_service/scripts/verify_task_pipeline.py
```

Run a local cross-device-style multipart check:

```bash
cd /mnt/f/CodexWorkspace/assembly_line_optimize/local_inspection_service
python3 scripts/smoke_cross_device_upload.py --host 0.0.0.0 --port 8876
```

To verify an explicit trusted cross-origin frontend:

```bash
INSPECTION_CORS_ORIGINS=http://trusted-mac.local:5173 \
python3 scripts/smoke_cross_device_upload.py --host 0.0.0.0 --port 8876 --origin http://trusted-mac.local:5173 --expect-cors allowed
```

To verify an untrusted origin is not allowed:

```bash
python3 scripts/smoke_cross_device_upload.py --host 0.0.0.0 --port 8876 --origin http://example.com --expect-cors denied
```

# Local Inspection Service

FastAPI prototype for local assembly-line inspection.

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

Open from the Mac with the LAN address, for example:

```text
http://<this-machine-lan-ip>:8765
```

When the service runs inside WSL2, `hostname -I` returns the WSL internal IP, not the Windows host LAN IP. A physical Mac usually cannot reach that WSL IP directly. In that case, expose the WSL service through the Windows host with an elevated PowerShell:

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

Use the Wi-Fi/LAN IP when both machines are on the same LAN, or the Tailscale IP when both devices are on the same tailnet. If the Windows firewall or portproxy command requires elevation, run the PowerShell commands as Administrator.

File inputs in the browser upload bytes with `multipart/form-data`; the service stores the uploaded streams under `local_inspection_service/data/uploads`. The server never reads a path from the Mac filesystem.

Direct Mac/LAN use should open the same LAN URL that serves the web UI, so it is same-origin and does not require CORS. For trusted proxy/tunnel frontends that call the API from another origin, add explicit origins:

```bash
INSPECTION_CORS_ORIGINS=http://mac-hostname.local:8765,http://192.168.1.20:8765 \
python3 -m uvicorn local_inspection_service.server:app --host 0.0.0.0 --port 8765
```

Only use broad private-LAN CORS during trusted local debugging:

```bash
INSPECTION_ENABLE_LAN_CORS=1 python3 -m uvicorn local_inspection_service.server:app --host 0.0.0.0 --port 8765
```

Untrusted cross-origin write requests are rejected. This protects local file-mutating routes such as accessory preview/confirm from arbitrary browser origins.

## Upload Smoke Test

Run a local cross-device-style multipart check:

```bash
cd /mnt/f/CodexWorkspace/assembly_line_optimize/local_inspection_service
python3 scripts/smoke_cross_device_upload.py --host 0.0.0.0 --port 8876
```

The test starts the service on all interfaces and sends multiple image files plus a video as HTTP multipart bytes. It does not rely on shared client/server filesystem paths.

To verify an explicit trusted cross-origin frontend:

```bash
INSPECTION_CORS_ORIGINS=http://trusted-mac.local:5173 \
python3 scripts/smoke_cross_device_upload.py --host 0.0.0.0 --port 8876 --origin http://trusted-mac.local:5173 --expect-cors allowed
```

To verify an untrusted origin is not allowed:

```bash
python3 scripts/smoke_cross_device_upload.py --host 0.0.0.0 --port 8876 --origin http://example.com --expect-cors denied
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

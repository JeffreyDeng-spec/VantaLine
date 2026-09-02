# Architecture

**Status: Authoritative**

## Components and boundaries

- **React frontend:** task/model selection, camera and upload workflows, administration, and workstation-local Web Serial.
- **FastAPI backend:** authentication, permissions, task/model orchestration, immutable PLC plans, audit receipts, static release serving, and `/api/version`.
- **PostgreSQL runtime repository:** shared application configuration, workstation identity/configuration, leases, dispatch state, and durable records.
- **Workers/model services:** training and inference integrations; they do not own PLC serial I/O.
- **Text inspection v2:** an account-scoped standard library and inspection workflow, independent from product/YOLO tasks. New label comparisons enter only through this workspace and accept a browser camera capture or uploaded image; both comparison previews can open an enlarged zoom view. The library uses a master/detail flow with modal import and collapsible order details; asset add, select, soft-disable and re-enable actions live directly in the expanded order beside each thumbnail and full-size preview. Selecting a confirmed library asset supplies the comparison reference without requiring a second upload. Reference and actual inputs are independent: replacing or selecting one preserves the other while invalidating stale output. A logical order standard remains editable, but confirmed history is append-only: initial confirmation and every later add, soft-delete or restore atomically record an immutable numbered asset snapshot, and each comparison binds to the exact revision and reference hash it used. Only assets in the current confirmed snapshot enter the comparison state. The former persistent scope-warning badge is not rendered, while the service-side verification gates and documented limits remain unchanged. Existing legacy incoming-text tasks remain readable, but their creation affordance is retired. PDF pages are rendered lazily. See `docs/text-inspection-v2.md`.
- **GitHub Actions:** required checks, one-commit release packaging, checksum/version generation, production installation, acceptance, release publication, and rollback on failure.

## Inspection flows

- Image upload and video requests perform detection only and never create a PLC plan.
- The text-comparison camera surface enumerates video inputs, exposes a labeled device selector, invalidates stale `getUserMedia` requests when a user switches devices, and refreshes on `devicechange`. If the selected device disappears, an available fallback may be opened only while that surface is active; permission denial or no remaining device leaves capture disabled and keeps the uploaded-image path available. Other camera surfaces retain their existing device lifecycle until separately hardened.
- File selection and drag/drop use one accessible frontend contract across the application. The chooser and drop path apply the same `accept`, single-versus-multiple and disabled rules; Enter or Space opens the chooser, rejected files are reported, and a disabled target cannot accept a drop. Domain-specific handlers still perform their stricter image, video or document validation after selection. These browser-only input conveniences do not change API authorization or PLC provenance.
- Camera detection uses a dedicated authenticated endpoint. Its final result may reserve one workstation-bound v4 dispatch.
- An enabled foreground workstation polls its configured D input locally through Web Serial. After observing reset, one non-trigger-to-trigger edge may invoke the same camera flow; sustained trigger values do not repeat and missed busy/not-ready edges are not replayed.
- The browser declares the attempt, writes D, waits for ACK, optionally writes Y only after D ACK, and submits one evidence receipt.
- Network/server failure after declaration cannot authorize automatic physical replay.

## Deployment and data ownership

`main` is packaged into `/opt/vantaline/releases/<release-id>` and production `current` atomically points to one immutable release. Mutable data, environment configuration, model artifacts, and database state remain outside release directories. A release contains backend source, one production frontend bundle, migration definitions, locked dependencies, `VERSION.json`, and `SHA256SUMS`.

The browser cookie identifies a workstation independently of login. User permissions still gate configuration, connection, camera inspection, attempt, and receipt operations. Secrets remain in GitHub Environment secrets or restricted server environment files and are never represented by real values in Git.

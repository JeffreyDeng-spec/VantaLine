# VantaLine React/Vite Migration Parity Checklist

Package manager: npm. The React preview project is rooted at `local_inspection_service/frontend`, uses `package-lock.json`, and builds to `local_inspection_service/frontend/dist` with Vite base `/react-preview/`.

Production safety rule: legacy `/` remains served by `local_inspection_service/static/index.html`; React preview is served separately from `/react-preview/`.

Deployment readiness instructions for repeatable preview deploy, gated future
production cutover, and rollback live in `docs/deployment-readiness.md`.

## Phase 0 Inventory

Current legacy frontend:

- `local_inspection_service/static/index.html`: monolithic HTML shell with auth, sidebar navigation, all workflow panels, modals, and image viewer.
- `local_inspection_service/static/app.js`: monolithic browser runtime for auth, status polling, uploads, camera flows, training pipeline, data analysis, LocateAnything, Label Sheet, and user management.
- `local_inspection_service/static/styles.css`: current visual language, dark sidebar plus light work surfaces.

Current visible views and migration order:

| View | Legacy id/view | Permission | Migration stage | React status |
| --- | --- | --- | --- | --- |
| Login/setup/logout | auth shell | public | Phase 1/2 | Phase 2 real login/setup/logout shell implemented |
| Home/status | `home`, `status` calls | authenticated | Phase 1/2 | Phase 2 dashboard/status cards implemented |
| Detection workbench | `inspect` | `inspection` | Phase 3B | Image/video/camera input, model selection, result rendering, and admin-only diagnostics implemented |
| AI detection | `aiInspect` | `ai_detection` | Phase 3B | AI task selection, image/video/camera analysis, result rendering, and admin-only diagnostics implemented |
| Label Sheet | `labelSheet` | `label_sheet` | Phase 3C | Reference library, upload/camera match input, result evidence, and admin-only diagnostics implemented |
| LocateAnything | `locateAnything` | `locate_anything` | Phase 3C | Runtime/status panel, recipe/prompt controls, file/camera inspect path, overlay result, and admin-only diagnostics implemented |
| Accessories library/detail | `accessories` | `accessory_library` | Phase 3A | List/detail/candidate/media/route actions implemented |
| Data analysis | `dataAnalysis` | `ai_detection` | Phase 3E | Records list, task filter, admin data-scope, locate actions, detail comparison, and admin-only diagnostics implemented |
| Training pipeline | `pipeline` | `training_pipeline` | Phase 3D | Four-lane React board, dnd-kit task/accessory movement, task modals, params/count controls, and model-library routing implemented |
| Training library | `trainingLibrary` | `model_library` | Phase 2/3A | List views plus dataset/model/AI-task detail, dataset/model destructive actions, and `ai_detection`-gated AI-task delete implemented |
| Rules/settings | `rules` | `system_settings` | Phase 2 | Rule, AI config, and Agent config forms implemented with panel-level permissions |
| User management | `userManagement` | `user_management` | Phase 2 | Create/edit/toggle/delete/password reset controls implemented |

## API Contract Inventory

Auth and user management:

- `GET /api/auth/status`
- `POST /api/auth/bootstrap`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/users`
- `POST /api/auth/users`
- `PATCH /api/auth/users/{user_id}`
- `POST /api/auth/users/{user_id}/password`
- `DELETE /api/auth/users/{user_id}`

Service, config, and workers:

- `GET /api/status`
- `GET /api/config`
- `GET /api/config/summary`
- `POST /api/config/rules`
- `GET /api/windows-worker/status`
- `GET /api/windows-worker/training/jobs/{job_id}`
- `GET /api/windows-worker/training/jobs/{job_id}/artifacts`
- `GET /api/agent/config`
- `POST /api/agent/config`
- `POST /api/agent/config/test`
- `POST /api/agent/recommend`

Detection and uploads:

- `POST /api/analyze/image`
- `POST /api/analyze/video`
- `POST /api/stream/config`
- `GET /api/image-jobs`
- `GET /api/image-jobs/{job_id}`
- `POST /api/image-jobs/{job_id}/stop`
- `POST /api/image-jobs/{job_id}/retry`
- `DELETE /api/image-jobs/{job_id}`
- `POST /api/image-job-candidates/{candidate_id}/stop`
- `DELETE /api/image-job-candidates/{candidate_id}`

AI detection:

- `GET /api/ai/config`
- `POST /api/ai/config`
- `DELETE /api/ai/config/key`
- `GET /api/ai/tasks`
- `POST /api/ai/tasks`
- `PUT /api/ai/tasks/{task_id}`
- `DELETE /api/ai/tasks/{task_id}`

Accessories:

- `GET /api/accessories`
- `POST /api/accessories`
- `GET /api/accessories/{accessory_id}/detail`
- `GET /api/accessories/candidates/{candidate_id}`
- `POST /api/accessories/preview`
- `POST /api/accessories/confirm/{candidate_id}`
- `POST /api/accessories/{accessory_id}/files`
- `POST /api/accessories/{accessory_id}/ai-reference`
- `DELETE /api/accessories/{accessory_id}/files`
- `DELETE /api/accessories/{accessory_id}`
- `POST /api/accessories/{accessory_id}/route`

Label Sheet and LocateAnything:

- `GET /api/label-sheets/references`
- `POST /api/label-sheets/references`
- `POST /api/label-sheets/match`
- `GET /api/locateanything/config`
- `POST /api/locateanything/config`
- `GET /api/locateanything/status`
- `POST /api/locateanything/runtime/start`
- `GET /api/locateanything/accessories`
- `POST /api/locateanything/inspect`
- `POST /api/locateanything/locate`

Training and pipeline:

- `GET /api/training/background-sets`
- `POST /api/training/background-sets`
- `POST /api/training/start`
- `POST /api/training/generate`
- `GET /api/training/status`
- `GET /api/training/resources`
- `GET /api/training/resources/datasets/{dataset_id}/detail`
- `PATCH /api/training/resources/datasets/{dataset_id}`
- `DELETE /api/training/resources/datasets/{dataset_id}`
- `DELETE /api/training/resources/datasets/{dataset_id}/samples/{sample_name}`
- `PATCH /api/training/resources/models/{run_id}`
- `DELETE /api/training/resources/models/{run_id}`
- `GET /api/training/plan`
- `POST /api/training/preview`
- `GET /api/pipeline/tasks`
- `POST /api/pipeline/tasks`
- `PATCH /api/pipeline/tasks/{task_id}`
- `DELETE /api/pipeline/tasks/{task_id}`
- `POST /api/pipeline/tasks/{task_id}/advance`
- `POST /api/pipeline/accessories/{accessory_id}`
- `DELETE /api/pipeline/accessories/{accessory_id}`

Data analysis:

- `GET /api/data-analysis/records`
- `GET /api/data-analysis/records/{record_id}`
- `POST /api/data-analysis/records/{record_id}/locate`
- `POST /api/data-analysis/locate`

Static/file routes:

- `GET /`
- `GET /react-preview/`
- `GET /static/*`
- `GET /outputs/*`
- `GET /api/backgrounds/{set_id}/{image_name}`

## Phase 1 Implemented

- Vite React TypeScript project scaffolded under `local_inspection_service/frontend`.
- TanStack Query powers auth/status/config/users server state.
- Zustand stores cross-page admin data-scope state.
- Radix Toast provides unified toast notifications.
- API client uses same-origin cookies, JSON requests, FormData upload support, unified error mapping, and admin `user_id` scoping.
- React Router shell defaults to basename `/react-preview`; production cutover
  builds set `VITE_ROUTER_BASENAME=/` so the root bundle is compatible with
  `/`.
- Permission guards mirror legacy permission names.
- FastAPI serves `/react-preview/` and `/react-preview/assets/*` separately from legacy `/`.

## Phase 2 Implemented

- Login/setup/logout remains fully functional through `/api/auth/status`, `/api/auth/login`, `/api/auth/bootstrap`, and `/api/auth/logout`.
- Home/status overview keeps live `/api/status` and `/api/config/summary` cards under the React shell.
- User management now supports create, display-name/role/permission saves, active toggles, delete, manual password reset, generated temporary passwords, and copy-once display.
- Settings now supports confidence threshold, required class toggles, min-count forms, AI provider/model/base-url/timeout/key selection, active-key deletion, Agent config save, and Agent connection test.
- Training library now supports list-level dataset/model/AI-task parity with dataset/model tabs, model type filter, counts, status badges, ownership audit metadata, missing-file indicators, and admin data-scope filtering.
- Vite preview builds no longer emit public source maps by default.
- Missing `/react-preview/assets/*` responses no longer inherit immutable cache headers; only successful preview/static asset responses receive immutable caching.
- Backend route inventory maps `/api/training/resources*` to `model_library`, matching the React training-library navigation permission; middleware also accepts `training_pipeline` there to preserve existing training workflow access.

## Phase 2 Deferred Detail Workflows

- Completed in Phase 3A: dataset thumbnail/sample detail, dataset/model rename forms, dataset/model deletion, sample deletion, AI-task detail, `ai_detection`-gated AI-task delete, and model-run detail path/log inspection.
- No navigation route remains wired to the generic placeholder after Phase 3E.

## Phase 3A Implemented

- `/accessories` now renders a real React page instead of the generic placeholder.
- Accessory list supports loading/error/empty states, name/ID search, material/status filters, status chips, thumbnail display, route/profile metadata, delete action, and admin data-scope filtering through the existing top scope selector.
- Accessory candidate flow uses `POST /api/accessories/preview`, shows generated image/job progress from candidate job metadata, polls active candidates, and confirms with `POST /api/accessories/confirm/{candidate_id}`.
- Accessory detail modal uses `GET /api/accessories/{accessory_id}/detail`, shows source/derived/generated gallery images, audit metadata, sprite counts, AI/Locate profile status, static/output URLs, image upload, AI reference selection, file delete, and detection-route save via existing APIs.
- Training library now supports dataset detail with thumbnails, dataset rename/note, sample delete, dataset delete, model-run detail with manifest/log/model paths, model rename/note, model delete, AI-task detail, and AI-task delete only for users with `ai_detection`.
- Added `local_inspection_service/scripts/smoke_phase3a_resources.py` to verify temp-root owner/admin scoping for accessories and training resources plus 3A detail/action contracts, including the model-library/read-only AI-task contract.

## Phase 3B Implemented

- `/inspect` now renders a React detection workbench instead of the generic placeholder.
- Regular detection supports task/model selection from `/api/status`, image upload via `/api/analyze/image`, video upload via `/api/analyze/video`, browser camera frame capture via `getUserMedia`, annotated preview rendering, pass/fail metrics, parts table rendering, video frame summary, loading/error states, and admin-only diagnostics.
- `/ai-inspect` now renders a React AI detection workbench instead of the generic placeholder.
- AI detection supports scoped AI task selection from `/api/ai/tasks`, AI image/video/camera analysis by passing the selected AI task model id into `/api/analyze/image` or `/api/analyze/video`, annotated preview rendering, pass/fail metrics, parts table rendering with task required counts, video frame summary, loading/error states, and admin-only diagnostics.
- Backend analyze permissions now allow `ai_detection` users through `/api/analyze/*` only when the selected model is an AI-detection model; default/non-AI analyze models still require `inspection`.
- Added `local_inspection_service/scripts/smoke_phase3b_detection.py` to verify React route replacement plus the `inspection` vs `ai_detection` analyze permission contract without requiring a real model or external provider.
- Browser camera code is implemented but remains unverified in authenticated HK browser QA because no disposable credential/browser runtime has been provided in this workspace.

## Phase 3C Implemented

- `/label-sheet` now renders a React Label Sheet workbench instead of the generic placeholder.
- Label Sheet supports reference-library refresh/list, reference upload through `POST /api/label-sheets/references`, image upload matching through `POST /api/label-sheets/match`, browser camera frame capture through `getUserMedia`, match result/score/review metrics, matched reference preview, input crop preview, sheet segmentation evidence preview, candidate table, loading/error states, and admin-only diagnostics.
- `/locate-anything` now renders a React LocateAnything workbench instead of the generic placeholder.
- LocateAnything supports service checks, `locate_config`-gated endpoint/runtime/config controls, read-only runtime summary for `locate_anything` users, source-item loading through `/api/locateanything/accessories`, recipe selection, per-item expected-present/count and prompt override controls, free-prompt `/api/locateanything/locate` runs, file upload inspection through `/api/locateanything/inspect`, browser camera frame capture, low-frequency continuous camera inspection, overlay preview, result metrics/table, and admin-only diagnostics.
- Added `local_inspection_service/scripts/smoke_phase3c_locate_label.py` to verify React route replacement plus Label Sheet and LocateAnything auth/request contracts without starting the heavy LocateAnything runtime.
- Browser camera code is implemented for both Phase 3C pages but remains unverified in authenticated HK browser QA because no disposable credential/browser runtime has been provided in this workspace.

## UI QA Rework 2026-06-15

- Normal user-facing pages no longer show raw JSON/debug payloads by default; detection, Label Sheet, LocateAnything, and system overview diagnostics are admin-only secondary affordances hidden unless explicitly opened.
- Visible metadata labels that previously used `状态` as a type/category label were renamed to result/progress/account/service wording while preserving loading, success, and error state semantics.
- LocateAnything source and rule descriptions are compacted and line-clamped so long profile/prompt/spec text cannot dominate picker rows or rule rows.
- Shared form/action alignment was tightened for panel buttons, toolbars, camera action rows, LocateAnything expected-present/count controls, and mobile single-column action grids.

## Phase 3D Implemented

- `/pipeline` now renders a React Training Pipeline page instead of the generic placeholder.
- The React page keeps the legacy four-lane board shape: in-flow accessories and pending candidates, draft task creation, sample generation, model training, and a model-library drop zone.
- Drag/drop uses `@dnd-kit/core` for accessory-to-task assignment, task movement to the next stage, training-to-library archiving, and accessory removal from the current flow.
- Pipeline task modals support the currently intended fields: task name, detection method, detail metadata, accessory counts with increment/decrement controls, and parameter confirmation for sample generation or training.
- Task cards preserve auto-advance toggles, parameter chips, progress bars, delete actions, AI/Locate routing, and no default raw/debug panels.
- Add-accessory modal supports joining existing accessories from the scoped accessory library into the current flow while the board continues to hide in-flow accessories already assigned to active tasks.
- Added `local_inspection_service/scripts/smoke_phase3d_pipeline.py` to verify React route replacement plus safe pipeline API contracts: in-flow accessory add/remove, task create/patch/delete, AI-route archive/link behavior, and permission denial for users without `training_pipeline`.

## Phase 3E Implemented

- `/data-analysis` now renders a real React data-analysis page instead of the generic placeholder.
- Records list supports loading/error/empty states, task filtering, current admin data-scope behavior through the top scope selector, row selection, selected-count feedback, and saved LocateAnything/comparison status display.
- Locate actions support one record, selected records, and the current filtered/list batch through the existing `/api/data-analysis/*` endpoints and enforce the backend batch limit in the UI.
- Detail modal shows record/task metrics, required accessory scope, AI result image beside the latest LocateAnything overlay, saved comparison summary, difference counts/details, and admin-only raw diagnostics.
- RBAC remains API-driven: route access is `ai_detection`; locate mutations are disabled unless the user also has `locate_anything`; user data isolation is delegated to the existing scoped data-analysis API and admin `user_id` scope handling.

## Remaining Parity Work

- Phase 4: browser QA, role-scope checks, upload/camera/security-context checks, long-running job polling checks, and desktop/mobile visual acceptance.
- Phase 5: production cutover proposal only; do not switch `/` without explicit approval.

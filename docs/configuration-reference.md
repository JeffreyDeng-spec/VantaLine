# Configuration reference

**Status: Authoritative**

This document lists ownership and names, never secret values or production endpoints.

## Configuration layers

- **Git-tracked defaults/contracts:** safe defaults, schemas, `release/plc-protocol.json`, dependency locks, migrations.
- **PostgreSQL runtime settings:** shared application records and workstation-specific PLC configuration/leases.
- **Restricted server environment:** database connection, provider credentials, runtime paths, trusted origins, release metadata overrides.
- **GitHub Environment secrets:** restricted deployment user/host, pinned SSH material, and deployment-only credentials.
- **Browser state:** workstation HttpOnly cookie, selected serial permission, active in-memory reader/writer and lease state.

Common backend variable families include `VANTALINE_POSTGRES_DSN`, `INSPECTION_AI_*`, `INSPECTION_CORS_ORIGINS`, and release/version inputs consumed by packaging. Exact accepted settings must be confirmed against typed server configuration before adding a value; examples are placeholders.

## Rules

Public navigation uses `/`, `/docs`, and protected `/workspace/*` on the same
origin; no new environment variable, domain or API credential is needed.
`VITE_ROUTER_BASENAME=/` remains the production setting; preview builds retain
their existing basename support. Public user documentation is static curated
content. API documentation is separate: `/api/docs` requires an authenticated
administrator (and keeps the handler's admin check), while `/openapi.json` and
`/redoc` remain admin-only. The website must not treat `/docs` as API tooling.

- Never commit `.env`, private keys, tokens, cookies, real DSNs, production addresses, customer data, or copied server environment files.
- Do not add a second configuration source for an existing setting.
- Server-wide settings belong in controlled environment/runtime configuration; workstation PLC addresses belong to the bound workstation record.
- Defaults must be fail-closed for external I/O.
- New configuration requires schema validation, permission definition, documentation, tests, and explicit behavior for missing/invalid values.

## Workstation PLC schema v5

The current preset is `mitsubishi_fx3ga_40mr` over browser Web Serial with fixed 9600/7E1, checksum including ETX, 500 ms timeout, zero retries, and a 200 ms input poll interval. Workstation-owned editable fields are `enabled`, `result_register`, optional `output_control_point`, `capture_trigger_enabled`, `capture_input_register`, and `capture_trigger_value`. Defaults are fail-closed: PLC and capture are disabled, input is D205, trigger is 1, result is D206, and Y is blank.

## Text inspection v2

`VANTALINE_QWEN_OCR_ACCOUNTS` is a separate default-empty allowlist selecting the
actual-image Qwen OCR evidence path. It also requires the existing external-media
gate and resolved Qwen credentials. It does not change standard preparation or
other model settings. The existing Key must explicitly permit both the pinned
OCR model and the configured correspondence model. Only approved HTTPS Beijing
DashScope/workspace endpoints are accepted, with redirects/retries disabled.
`min_pixels=3072` is required by the verified OCR API; the 12,582,912-pixel bound
is explicit. Invalid, incomplete or unavailable results remain review-required.
This release intentionally cannot emit automatic MATCH for this provider; the
older local MATCH allowlist does not commission it. Keep recognition disabled
until approved real-image testing and release verification. Unknown cache entries
are retained and block paid replay; changing the standard is not a retry consent.

`VANTALINE_STANDARD_PREPARATION_ACCOUNTS` is a default-empty account allowlist for
activation-time cleaning and reusable text/code templates. It additionally requires
the existing external-media authorization and configured visual model. Each source
gets at most one classification call; unknown calls are never replayed.
The same response may locate up to eight missing-text regions for local OCR,
with a shared 60-second supplementary budget; this adds no paid provider or key.
The region limit and area bounds are fixed validation constraints, not environment
overrides. Invalid responses remain reviewable without retries.
Manual edits call no external service. `VANTALINE_STANDARD_OCR_MODEL_DIR` must contain the
existing `PP-OCRv6_medium_det`, `PP-OCRv6_medium_rec` and
`PP-LCNet_x1_0_textline_ori` directories with inference.yml/json/pdiparams. Models
are not downloaded by requests. Missing local models leave the source reviewable.
`VANTALINE_STANDARD_ELEMENTS_MATCH_ACCOUNTS` separately commissions local MATCH;
keep it empty until independent accuracy and runtime gates pass. Neither switch
authorizes graphic matching or alters PLC/other inspection configurations.

`VANTALINE_DOCUMENT_CLASSIFICATION_ACCOUNTS` is a default-empty account allowlist
for DOC/DOCX classification. It also requires the external-media gate and the
existing configured Qwen visual model/key from `ai_detection_settings()`.
Each unique image has at most one call (60s timeout); two document workers per
application process are allowed. Busy/unconfigured imports show the reason and
allow explicit later start. PDF is unchanged. No other model/key fallback exists.

`VANTALINE_DOC_IMAGE_BUNDLE` points to the fixed POI 5.5.1 helper bundle built by
`scripts/build_doc_image_extractor.py --output <directory>`. Java 11+ is required
at runtime (use a supported patched JRE); building additionally needs javac/jar.
The bundle manifest verifies every jar's SHA-256 and the helper source version.
No download or model call occurs in the Java helper, and credentials/JVM injection
environment variables are not inherited by the helper. No LibreOffice, fonts,
bubblewrap or DOC-to-DOCX conversion is required. The earlier converter flag is
unused. Limits: 30MB DOC, 500 images, 30MB per image, 100MB total output, 256MiB Java
heap and 30s timeout; one concurrent import per application process. This is not
an OS security sandbox or a bound on total JVM RSS. Missing bundle returns 503.
DOCX/PDF retain their existing 100MB bound. Original DOC hashes govern deduplication.

`VANTALINE_LABEL_BBOX_ACCOUNTS` is a separate, default-empty account allowlist for `vlm_bbox`. An account must also be in `VANTALINE_LABEL_EXTRACTION_ACCOUNTS`. Availability requires the external-media gate and a configured Qwen result from the same `ai_detection_settings()` resolver used for label comparison. There is no new key/model source or browser-supplied endpoint. One task freezes these resolved settings; the experimental timeout is 180 seconds, one attempt, temperature 0.1, 512 output tokens and `enable_thinking=false`. The timeout overrides only this method, not the comparison settings. Never activate based on synthetic tests alone.

`VANTALINE_LABEL_EXTRACTION_ACCOUNTS` is a comma-separated allowlist of authenticated account IDs; empty disables the new extraction UI. The extraction capabilities route reports availability without keys. AI masks use the existing image-generation provider/model/key, require the existing external-media gate, and disable provider format-retry fallback for this one-call path. Missing image-generation configuration leaves explicit manual polygon extraction available. Qwen text comparison keeps its existing separate settings. Enable the initial account only after synthetic extraction and manual-confirmation acceptance; do not infer image-generation availability from the text model's configuration.

The feature uses the existing authenticated AI provider configuration and `inspection` permission. No provider key or media is stored in Git. Legacy `.doc` image extraction requires the configured POI bundle, not an office converter. External image sending defaults off and requires `VANTALINE_TEXT_INSPECTION_EXTERNAL_VLM_ENABLED=true`; automatic label match and manual-book pass have separate commissioning flags. Missing flags, provider failure, invalid JSON and uncertain charging always return review-required behavior.

The backend returns resolved protocol addresses and an immutable `capture_read_plan`; these are diagnostics/authorization output, never user input. Account logout does not delete the workstation cookie or configuration.

## WebMCP development commissioning

`VANTALINE_WEBMCP_ACCOUNTS` is a default-empty comma-separated account-ID allowlist.
The developing browser surface also requires an enabled policy in PostgreSQL;
admin-only `/api/agent/policy/{account_id}` GET/PUT manages versioned policy records.
The new migration must exist before an account is allowlisted. Keep production
activation off: existing business/worker paths do not yet all enforce this policy.
A persisted budget or provider ID list is not a platform-wide safety guarantee.
See [implementation status](agent-platform.md) for the remaining release gates.

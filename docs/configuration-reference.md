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

- Never commit `.env`, private keys, tokens, cookies, real DSNs, production addresses, customer data, or copied server environment files.
- Do not add a second configuration source for an existing setting.
- Server-wide settings belong in controlled environment/runtime configuration; workstation PLC addresses belong to the bound workstation record.
- Defaults must be fail-closed for external I/O.
- New configuration requires schema validation, permission definition, documentation, tests, and explicit behavior for missing/invalid values.

## Workstation PLC schema v5

The current preset is `mitsubishi_fx3ga_40mr` over browser Web Serial with fixed 9600/7E1, checksum including ETX, 500 ms timeout, zero retries, and a 200 ms input poll interval. Workstation-owned editable fields are `enabled`, `result_register`, optional `output_control_point`, `capture_trigger_enabled`, `capture_input_register`, and `capture_trigger_value`. Defaults are fail-closed: PLC and capture are disabled, input is D205, trigger is 1, result is D206, and Y is blank.

## Text inspection v2

Whole-sheet inspection uses default-empty account-ID allowlists:
`VANTALINE_SHEET_ELEMENTS_ACCOUNTS` exposes the opt-in experiment;
`VANTALINE_SHEET_ELEMENTS_VERIFIED_ACCOUNTS` permits automatic decisions after commissioning;
`VANTALINE_SHEET_ELEMENTS_GRAPHIC_VERIFIED_ACCOUNTS` separately permits verified
graphic matches; `VANTALINE_SHEET_ELEMENTS_VLM_ACCOUNTS` allows one optional Qwen
advisory using existing resolved settings and the existing external-media gate.
Keep verification allowlists empty until independent samples and performance pass.
No new key source or default GPU purchase is introduced.

`VANTALINE_SHEET_OCR_MODEL_DIR` points to pre-provisioned local directories
`PP-OCRv6_medium_det`, `PP-OCRv6_medium_rec`, `PP-LCNet_x1_0_textline_ori`.
`VANTALINE_SHEET_OCR_PROFILE=medium|small` defaults to `medium`; `small` selects the
corresponding pinned v6-small artifacts for isolated performance comparisons.
Changing profile requires fresh accuracy/performance commissioning. Inference uses
two CPU threads, one tiled text-detection pass, and local line-orientation correction
before recognition batches of 32. The legacy full-OCR helper remains for optional
bounded advisory verification, not the normal whole-page comparison path.
Missing artifacts fail explicitly without runtime downloads. The experiment uses
CPU and existing pinned Paddle dependencies. ZXing-C++ 2.3.0 is pinned in both
dependency files (https://pypi.org/project/zxing-cpp/2.3.0/); incomplete development
environments fall back to OpenCV QR only and do not claim barcode coverage.

`VANTALINE_LABEL_BBOX_ACCOUNTS` is a separate, default-empty account allowlist for `vlm_bbox`. An account must also be in `VANTALINE_LABEL_EXTRACTION_ACCOUNTS`. Availability requires the external-media gate and a configured Qwen result from the same `ai_detection_settings()` resolver used for label comparison. There is no new key/model source or browser-supplied endpoint. One task freezes these resolved settings; the experimental timeout is 180 seconds, one attempt, temperature 0.1, 512 output tokens and `enable_thinking=false`. The timeout overrides only this method, not the comparison settings. Never activate based on synthetic tests alone.

`VANTALINE_LABEL_EXTRACTION_ACCOUNTS` is a comma-separated allowlist of authenticated account IDs; empty disables the new extraction UI. The extraction capabilities route reports availability without keys. AI masks use the existing image-generation provider/model/key, require the existing external-media gate, and disable provider format-retry fallback for this one-call path. Missing image-generation configuration leaves explicit manual polygon extraction available. Qwen text comparison keeps its existing separate settings. Enable the initial account only after synthetic extraction and manual-confirmation acceptance; do not infer image-generation availability from the text model's configuration.

The feature uses the existing authenticated AI provider configuration and `inspection` permission. No provider key or media is stored in Git. Legacy `.doc` import is deliberately unavailable until the separately pinned LibreOffice production dependency passes its health gate. External image sending defaults off and requires `VANTALINE_TEXT_INSPECTION_EXTERNAL_VLM_ENABLED=true`; automatic label match and manual-book pass have separate commissioning flags. Missing flags, provider failure, invalid JSON and uncertain charging always return review-required behavior.

The backend returns resolved protocol addresses and an immutable `capture_read_plan`; these are diagnostics/authorization output, never user input. Account logout does not delete the workstation cookie or configuration.

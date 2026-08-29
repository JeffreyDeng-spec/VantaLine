# Text inspection v2

**Status: Authoritative**

The formal **文字检验** entry is account scoped and independent from product/YOLO tasks. It contains label comparison and a manual-page pilot. The previous `incoming_material_text` task workflow and its visibly marked “旧版” task-creation entry remain available throughout the expand/rollback window.

## Release stages

1. **Expand (this release):** add v2 tables, account-scoped APIs, safe DOCX candidate extraction, lazy PDF pages, confirmed immutable versions, idempotent comparison attempts, and the new UI. Old UI, tables and APIs are untouched.
2. **Migrate/observe:** tenant-by-tenant copy or cleanup is a separately authorized operation with backup/restore evidence, counts and hashes. It must not run from an automatic release.
3. **Contract:** after the observation and rollback windows, a separate PR may freeze and then remove old routes and permissions. Additive database policy keeps empty historical tables.

## Trust boundaries

- `owner_user_id` is always derived from the authenticated session; request IDs never select another account. Media downloads repeat the ownership check and validate the resolved path.
- DOCX imports are size/entry/ratio bounded, reject path traversal, external relationships and macros, and read only document XML plus `word/media`. OLE payloads are quarantined and never opened. Automatic classification only changes visibility; a user can restore every extracted candidate before confirmation.
- `.doc` conversion is not enabled until a pinned LibreOffice package, isolated runtime user, timeout/process-kill behavior and production health gate are reviewed in a separate dependency PR.
- PDF metadata is validated synchronously, but pages are rendered lazily with page and pixel limits. The complete action is the only time missing pages are calculated.
- The external VLM receives only one confirmed standard image and one capture. The service writes an `attempting` record before the call, uses one provider attempt, and never re-calls an uncertain comparison ID. Provider/schema/prompt failures become `REVIEW_REQUIRED`.

## API

The `/api/text-inspection` namespace requires `inspection`. Standards, assets, records, sessions and pages are limited to the current authenticated account. Main routes are standards import/list/detail/asset classification/confirm, label compare, manual session create/page/complete, and inspection review. Confirmed standard versions are immutable; changes require a new version.

The first classifier is a deterministic local context classifier with manual feedback. The customer fixture must keep `image1`–`image6` as label candidates and collapse `image7`–`image18` into packaging, dieline, manual/insert, carton, placement or photo categories. No classified asset is physically deleted.

## Remaining production gates

External media sending defaults off (`VANTALINE_TEXT_INSPECTION_EXTERNAL_VLM_ENABLED`). Even after consent enables sending, `MATCH` remains review-only until `VANTALINE_TEXT_INSPECTION_AUTOMATIC_MATCH_VERIFIED` is set after customer samples, account budgets/rate limits, prompt/model pinning and commissioning evidence pass. Manual completion cannot return PASS until `VANTALINE_TEXT_INSPECTION_MANUAL_PASS_VERIFIED` is set after page lease/fencing and multi-tab recovery tests pass.

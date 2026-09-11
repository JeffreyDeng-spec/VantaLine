# VantaLine release management

**Status: Authoritative**

`main` is the only production source of truth. Production is never built from a developer worktree, server checkout, backup directory, untracked bundle, or manually selected files.

## Change and release flow

1. Create `feature/*`, `fix/*`, `hotfix/*`, or `docs/*` from current `origin/main`.
2. Open a pull request using the production-change template and update mapped authoritative docs.
3. Merge only after every required CI job passes.
4. Successful push CI on `main` triggers `Release and deploy production`; no manual deployment approval/button is required.
5. The workflow builds one immutable artifact, creates a draft Release, deploys through the restricted account, verifies exact SHA/protocol/assets/service acceptance, then publishes the Release.

The required frontend job also runs `test:agent` for generated action drift,
registry lifecycle and browser-test waiting regressions. Experimental native
WebMCP browser acceptance remains a separate explicitly recorded check; this
unit-test gate does not certify full-platform Agent coverage.

The backend comparison gate includes standard-preparation geometry, real-route
fixtures and isolated PostgreSQL concurrent-claim/atomic-publication tests.
`scripts/test_standard_preparation_ui.cjs` is the local real-React mock-HTTP browser
acceptance runner. Customer-image cleaning and OCR accuracy remain separate from
these contracts, and the new preparation/MATCH allowlists default off.
The gate also covers local missing-region OCR geometry, strict no-generated-text
validation, owned evidence and late-result rejection after interruption. Real-image
coverage and local OCR accuracy remain independent commissioning requirements.

For PLC automatic-capture changes, the required frontend job executes `test:plc-capture` before typecheck and production build. Reset-before-arm, sustained-trigger latching, and reset/retrigger failures block merge and release.

For text-inspection changes, required CI runs the comparison/source contract, dependency-light document contract, endpoint smoke in fail-closed, external-only and enabled modes, the PostgreSQL revision contract, and the legacy incoming-text rollback suite. The gate must prove account isolation, append-only numbered standard revisions, reversible soft deletion, exact comparison-to-revision binding and preservation of the previous readable workflow; a frontend build alone is not sufficient.

For the text-comparison camera selector or any upload surface, required CI also runs the browser-media input contract. It blocks a release if any file input bypasses the shared accessible drag/drop behavior, or if text-comparison camera switching lacks device refresh, stale-request invalidation, track cleanup and unavailable-device fail-closed guards. This UI contract does not claim equivalent lifecycle hardening for other camera pages and does not relax domain-specific file validation or the separate PLC provenance checks.

## Artifact and production invariants

The required frontend job runs the pinned Playwright navigation suite and uploads
its screenshot evidence. The backend job checks actual public/workspace routes
and API-doc permission boundaries. Route/layout separation does not change the
single immutable bundle or PLC protocol verification contract.

Document classification adds authenticated job/deletion smoke tests and parser
checks to CI. Its separate account allowlist must be configured for rollout;
shipping the Java extractor alone does not enable VLM classification.

The DOC image helper is built in CI with Java 17 from the fixed Maven dependency
lock. Release packaging verifies its source and jar hashes, then includes only
the runtime jars and manifest under `workers/doc_image_extractor/bundle`.
Production requires a patched headless Java runtime and the configured bundle
path; it never compiles the helper or downloads Maven dependencies on import.

The optional whole-image rectangle experiment adds offline parser/geometry and real-route smoke checks to required CI. Its separate account gate remains empty if customer-image commissioning fails; shipping disabled code is not production algorithm acceptance.

Single-label extraction adds required geometry and real-route smoke checks to CI. Its additive migration and default-empty account allowlist permit staged activation while retaining the legacy input route for rollback. Synthetic geometry and API tests are not substitutes for customer-image commissioning or permission to automatically pass labels.

- Frontend and backend share one release, Git SHA, and PLC protocol contract.
- The artifact contains source, production bundle, migrations, locked dependencies, `VERSION.json`, and `SHA256SUMS`.
- Production uses `/opt/vantaline/releases/<release-id>` and an atomic `current` link; mutable state stays outside releases.
- Existing tags/releases are immutable. Failed drafts and deployment logs remain evidence.
- The installer requires at least 2 GiB free, healthy service/database preflight, and no unsafe PLC in-flight state.
- Destructive database changes cannot be part of one automatic deployment; use expand/migrate/contract phases.

## Failure, retry, and rollback

An unchanged failed workflow job may be rerun only after its external gate is safely corrected, such as restoring disk capacity or deployment connectivity. Never rebuild locally to bypass failure. Acceptance failure automatically points `current` back to the prior release and restarts. A post-acceptance regression is handled by a complete revert/release or previous immutable artifact, never a partial file rollback.

Protocol or bundle mismatch keeps ordinary website functions available but disables PLC leases and physical actions. See [Production runbook](production-runbook.md) for diagnosis.

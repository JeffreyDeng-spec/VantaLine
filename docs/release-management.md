# VantaLine release management

CI includes training input/state and immutable preview-fingerprint contracts. Source manifest v30
and all four cache/approval/dataset/status modules must travel together. This extraction changes no
route, schema, migration, model/prompt policy or worker topology. Whole-package rollback preserves
stored task snapshots, preview approvals and runtime task settlement records.

CI includes preview workflow and artifact contracts. Publish the four preview workflow modules
with source manifest v30 in one immutable release. No route/schema, migration, model policy or
worker topology change. Restore the previous complete package on failure; preserve preview files,
plan JSON, user state and historical task snapshots according to existing write semantics.

CI includes full preview renderer contracts and the original pixel/metadata/call fingerprints.
Ship renderer, its typed ports and source manifest v30 in one immutable package. No API, model,
prompt policy, dependency, migration or process topology changes. Whole-package rollback preserves
existing task snapshots and generated images/datasets; individual source files must not be copied.

CI includes preview layout contracts. Publish geometry, masks, placement and source manifest v30
in the same complete release. This batch changes no routes, dependency versions, migrations,
worker topology or rendering algorithm. Rollback restores the prior package and source manifest;
stored task snapshots and generated datasets remain intact.

CI includes deterministic background pixel and orchestration contracts. Ship both background
modules and source manifest v30 in the same immutable release. No dependency, migration, route,
worker topology or rendering algorithm changes. Rollback restores the complete prior package and
its matching source list, preserving historical snapshots and existing generated datasets.

CI adds the resource-mutation contract with an isolated PostgreSQL schema. Package mutation and
link services plus the five HTTP adapters in the complete immutable release. No migration, setting,
worker topology or source-manifest version change is introduced. Roll back the whole previous
package while retaining resource records, files and historical model references.

CI adds resource-catalog contracts. Ship the dataset catalog, resource query and HTTP adapters
with source manifest v30 in the complete immutable release. Routes, storage schema and process
topology retain their existing contracts. Rollback restores the entire previous package while
retaining task records and historical model snapshots.

CI includes the archive/artifact contract. Package all three new file-handling modules and
source manifest v30 with the whole release. No database migration, endpoint, deployment service,
worker contract or dependency is added. Restore the previous complete release and retain task
records, archives, imported artifacts and historical model references.

CI includes the offline RunPod flow contract. Ship submission, output-parser and flow modules
with source manifest v30. This batch changes no request/worker contract, dependency, service,
migration or deployment topology. Rollback restores the complete prior release while retaining
remote job identifiers, task evidence and stored model snapshots.

CI includes the training dataset contract. Ship all four sample-generation modules and source
manifest v30 as part of the same immutable release. There is no database migration, worker
switch, new dependency or training process change. Whole-release rollback retains task/model
snapshots and existing sample files; this extraction performs no media cleanup.

CI includes the offline training runner/submission contract. Package the three extracted
training modules together with source manifest v30. Training still runs through the existing
process/thread topology; no new service, dependency, environment key or migration is added.
Rollback restores the previous complete release while retaining frozen model references.

CI runs the training-state service contracts. Deploy all four completion/state modules
with source manifest v30 in the same immutable package. No migration, environment setting,
worker topology or release restart change accompanies this batch; rollback uses the prior
whole package and retains task/call records and frozen model references.

CI includes `smoke_training_executor_client.py` for the extracted executor settings and
active RunPod adapter. This batch changes neither release topology nor training payloads.
It requires no new environment variable or migration and rolls back as a complete release.

Training lifecycle CI adds synthetic process/permission contracts and an isolated
PostgreSQL deletion/late-update scenario. Ship the lifecycle, views and runtime owner
modules together. Existing startup callbacks and process topology remain; the model
source manifest advances to v30 to cover all three moved files. Rollback remains
a complete immutable release.

Pipeline store CI adds synthetic and isolated PostgreSQL contracts. The repository
source gate inspects all eight real task/state selections and thirteen root forwards,
without counting composition callbacks twice or lowering its original threshold.
Ship the two stores, pure state policy and source manifest v30 in the whole release.
Worker launch, migrations and rollback topology are unchanged.

Training storage CI now exercises its disposable PostgreSQL schema and eight moved
helpers. The database source gate counts the three actual extracted entries, excludes
the composition callback from totals and retains the original minimum threshold.
Ship both training modules as part of the immutable release; launch and rollback
commands and topology remain unchanged. Source manifest v30 now includes both
training identity and storage so relocated selection/binding inputs remain covered.

Backend CI now includes training discovery contracts with a disposable PostgreSQL
schema, and dependency checks admit the training/pipeline packages. Publish all three
new modules and source manifest v30 with the complete immutable release. This batch
does not change worker startup, release commands or rollback topology.

Warmup method, path resolver, model loader and error formatter use narrow callback
getters at their original expressions, after preceding work and before argument
conversion. Missing callbacks retain argument effects; new getter failures stop
before them. No retry, lock or thread admission policy is added.

Warmup CI adds synthetic policy, prediction and runtime contracts while retaining
the startup callback in the assembled application baseline. Ship the three relocated
warmup modules and manifest v30 together. Worker topology and release commands remain.

Local model factory lookup uses a narrow getter after path resolution and before
string conversion, preserving callback replacement and missing-callable argument
effects. Existing cache publication order and exception boundaries remain unchanged.

The local-model runtime batch adds synthetic selection/cache coverage and ships both
new modules with manifest v30. It retains the current warmup entry points, in-process
inference and immutable whole-release deployment/rollback.

Task projection/catalog CI adds the focused synthetic smoke and keeps the original
resource and detection endpoint checks. Manifest v30 records the new model-input
assembly sources. Whole-release rollout/rollback and worker startup are unchanged.

The detection task-store batch adds its synthetic and disposable-PostgreSQL smoke
to backend CI and updates the repository source gate to inspect the extracted store.
Deployment/rollback remains the complete immutable release with the current topology.
Row decoding and background callback getters resolve at the original expressions:
after preceding work and before fetch/string/mapping argument effects. Missing
callbacks preserve argument evaluation and TypeError. Source manifest v30 covers
the three task modules; no retry, cache policy or transaction change is introduced.


The detection OCR batch adds its synthetic smoke and ships `runtime.paddle` plus
five OCR modules with source manifest v30. Local factories never load real models in
these contracts. Keep the complete application and incoming/OCR regression checks;
release startup, worker topology and whole-package rollback remain unchanged.
Attachment crop, score and match getters capture the current callable at each
original expression, before argument effects. Missing callbacks still evaluate
arguments and raise the original TypeError. Single-image OCR retains its existing
Exception handling; batch failures retain the existing per-image fallback. No new
retry or model-initialization lock is introduced.


The detection-result extraction adds synthetic backend smoke and admits the new
`detection` package to dependency-direction checks. It preserves the HTTP contract,
model parameters, worker topology and release commands. Ship source manifest v30
with all five detection modules to retain their source coverage for new tasks.
Historical snapshots remain untouched; whole-release rollback is the recovery unit.

The legacy incoming workflow batch adds its focused smoke to backend CI, retains
both original incoming endpoint and repository checks, and compares the complete
assembled HTTP baseline. It does not change worker topology or launch commands.
Source manifest v30 records the relocated OCR input orchestrator for new snapshots.
Rollback remains the previous immutable release with existing persistent state.

OCR/Beta CI adds ten offline initialization, image, cache and composition groups.
Ship the analysis, comparison-cache and HTTP modules with manifest v30 and the root
state aliases. Model names, flags, business prompt versions and deployment topology
are unchanged. Full-runtime CI must retain the existing incoming/Beta endpoint and
model-snapshot checks before any sequential production rollout.

Incoming-store CI adds isolated file/JSON/SQL contracts, root composition checks and
an explicit disposable-schema PostgreSQL group. Existing incoming/text endpoints
remain required. Ship both the runtime file adapter and legacy store with the root
aliases in the immutable artifact; database schema and worker topology are unchanged.

Comparison/review CI adds eight offline boundary groups and six route-identity
checks. Ship the submission, review, API and port modules plus manifest v30 together;
the source list now includes the actual comparison input and strict-prompt files.
Business prompt text/version stays unchanged. Retain old task evidence on a normal
whole-release rollback; no new worker mode is enabled by this package.

Standard-workflow CI adds seven native HTTP and failure-boundary groups while
retaining original document review and real PostgreSQL checks. Include the API,
three business services and explicit ports with the matching root composition in
the immutable artifact. Runtime topology and complete-release rollback stay unchanged.

Revision/projection/diagnostic CI adds six isolated behavior contracts and assembled
application identity checks. Ship these modules and their root adapters together.
Manifest v30 and normal whole-release restart/rollback apply; no new topology or
model configuration is enabled by this structural batch.

Text-media CI adds real image/PDF and application-composition contracts. Package
both media/image modules with source manifest v30, which covers their migrated
model-input producers. Stored snapshot fingerprints are not rewritten. No runtime
dependency upgrade is needed; ordinary complete-release restart/rollback applies.
Media fault injection preserves first-error evidence without retries. Callback and
resize-policy contracts retain the original evaluation timing before publication.

Text-record CI adds isolated JSON/SQL contracts and real PostgreSQL competing
submissions/updates. Existing HTTP and source contracts remain required; source
checks follow the actual extracted repository instead of lowering coverage gates.
Ship the store module and its entry-point composition in one immutable package.

Prepared comparison CI adds submission/callback, late-CAS and paid-call dependency
contracts. The compatibility export and new comparison/media ports ship together;
Qwen, audit and preview consumers are updated in the same package. Source fingerprints
change normally without rewriting old snapshots. The paid diagnostic probe is only
adapted to the explicit settings signature, never executed by these checks.
Final-write and paid-stage fault injection must reject duplicate attempts, and
the previously deployed HTTP/worker timeout-capture contracts remain mandatory.

Preparation dependency CI adds isolated timeout, transaction, admission and
late-result contracts while preserving the original endpoint and PostgreSQL gates.
Ship API, job, policy and port modules with their compatibility module in one
immutable release. Preparation prompt and classification producers retain their
source locations. Changed tracked source bytes naturally produce a new fingerprint
for new tasks; historical fingerprints remain untouched. Use the existing
complete-release rollback.

Extraction dependency CI adds isolated identity, worker and evidence-retention
contracts alongside existing extraction/bbox and PostgreSQL race checks. Ship the
new API/port modules and compatibility export together in the immutable package;
existing restart and whole-release rollback remain the deployment procedure.

Agent dependency CI adds native-ASGI account/policy/cancellation contracts while
retaining the isolated PostgreSQL state-machine smoke. Complete application HTTP
and dependency-direction gates include the new modules; release topology and
whole-package rollback stay unchanged.

Document-job dependency CI adds synthetic admission, persistence and failure contracts
while retaining original document endpoint tests. Package the API, business and port
modules with their compatibility export. No prompt, schema or process-topology change
is introduced; ordinary immutable-release restart and rollback apply.

History dependency CI adds native ASGI and evidence-media contracts alongside the
original history and PostgreSQL label gates. Package `text_inspection.history`, its
ports and the compatibility export together; use normal complete-release rollback.

Codex API dependency CI adds explicit-composition and compatibility tests while
retaining all existing PostgreSQL, CLI and worker-exit tests. Include the request,
validation and dependency modules together in the immutable package; the worker
process topology and release start/stop procedure remain unchanged.

Label dependency CI adds explicit-port isolation and registrar lifecycle contracts,
while preserving the real PostgreSQL and complete-application gates. Include the new
label dependency module in the immutable package. Worker process separation remains
a later release after the publisher bridge; this batch changes no runtime topology.

Route-selection CI adds synthetic HTTP failure-order contracts. Package the new
service and route module together. No schema, source-manifest, process-topology or
PLC change is part of this extraction; preserve existing complete-release gates.

Preparation CI adds synthetic workflow contracts and source manifest v30 includes
the migrated prompt producer. Ship services and manifest together in the complete
immutable release. Existing snapshots are not rewritten during deployment or rollback.

Image-job metadata CI adds runtime contract checks and advances source provenance
to the versioned source manifest. Package the new metadata source with the complete immutable release.
No schema, prompt algorithm, concurrency or process topology change is introduced.

Gallery CI adds synthetic HTTP/image-byte contracts. Whole immutable releases
include the new gallery service; schema, prompts and process topology are unchanged.

Management CI adds the synthetic creation/confirmation/removal contract gate.
No schema, worker topology, model producer or task snapshot format changes. Keep
ordinary complete-release validation and rollback; the phase adds no cutover step.

Accessory file-edit CI adds synthetic real-HTTP regression without paid calls.
The immutable package includes the new services; deployment topology, schema and
prompt-source manifest remain unchanged. Existing frontend and PLC gates remain.

Candidate CI adds isolated PostgreSQL and actual-root job callback regression.
Read-time repair, prior snapshot references and runtime topology are unchanged;
the ordinary immutable package includes the new candidate service files.

Accessory catalog CI adds isolated PostgreSQL and synthetic HTTP/projection checks.
The prompt source manifest includes the moved policy file; the complete
immutable package includes that source. Runtime topology and schema are unchanged.

Record-context CI checks exercise real HTTP/thread identity plus owner assignment
and failure behavior. The full RBAC and assembled application gates remain required;
release topology and persistent data formats are unchanged.

The audit projection gate adds synthetic timestamp and file-fallback checks.
Existing cost, analysis and application contracts remain required. This batch
changes no release topology, database schema or runtime configuration.

The shared-ownership extraction adds a pure policy gate while keeping full RBAC,
analysis HTTP, model, PLC and frontend checks. It changes no deployment topology,
migration, runtime configuration or persisted record representation.

Authentication HTTP extraction adds service/transport failure checks and restores
the complete original auth/RBAC smoke as a CI gate, with explicit real-HTTP tests
for label-local permissions. It does not add deployment flags or change topology.

The request-authentication gate includes actual ASGI security/identity contracts
and real PostgreSQL indexed authentication through the extracted service. Required
HTTP snapshots remain unchanged; this adds no worker startup or deployment switch.

The authentication foundation gate adds synthetic JSON and isolated PostgreSQL
compatibility/failure tests. Existing HTTP, agent, navigation and frontend checks
remain required. This release changes no worker topology or deployment flags.

The analysis projection/publication gate adds synthetic service failure/cache
tests and keeps the assembled API, original analysis HTTP flow, PostgreSQL and
frontend checks. It introduces no deployment flags or service topology changes.

Analysis-domain CI includes real isolated PostgreSQL storage tests, the original
synthetic detection-to-analysis HTTP flow and an updated source-owner contract.
These are additional gates; existing PLC, frontend and model checks remain.

Cost-domain extraction adds `smoke_cost_ledger.py` to backend CI. It changes no
runtime topology, dependency pin, migration or pricing; the whole-release gate
and sequential deployment observation remain required.

Backend extraction changes must pass the assembled-application contract in CI.
The expected contract is checked in, never regenerated by the release job. This
adds no production flag, migration or change to the immutable deployment path.

**Status: Authoritative**

The runtime identity/connection extraction is a separate PR after model dependency
injection. Its native thread-pool and real PostgreSQL scope tests supplement the
unchanged HTTP baseline; no external-worker cutover occurs in this release.

Model dependency extraction is a separate release after the contract baseline. It
preserves the embedded label worker and existing database/HTTP contracts. CI also
requires the explicit dependency smoke; no worker cutover or model change is bundled.

`main` is the only production source of truth. Production is never built from a developer worktree, server checkout, backup directory, untracked bundle, or manually selected files.

## Change and release flow

The backend CI gate includes comparison-history route authorization and
non-mutation tests; the PostgreSQL preparation suite verifies summary projection
and cursor pagination against both existing JSON encodings. History commissioning
reads saved production evidence only, without paid inference or record migration.

Local OCR reread releases run offline independent-view/cache/geometry tests in
CI. The reread allowlist is separate from automatic acceptance; deploy the whole
immutable release before enabling an authorized trial account. Synthetic accuracy
is not a production acceptance gate or permission to enable automatic MATCH.

The Qwen evidence gate adds offline parser/matcher tests and authenticated
fake-provider comparison/cache tests to required backend CI; the PostgreSQL gate
also checks cache insert-once and owner/status CAS. These checks permit shipping
disabled code, not enabling actual-image processing or automatic MATCH without
the separately documented real-image acceptance.

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

## Optional Codex comparison worker

The release includes default-disabled comparison source and additive migrations.
The same-host systemd template is commissioned separately; it must point at the
selected immutable release and be drained/stopped before a release switch.
Linux isolation/transaction tests gate code; real-session and sample accuracy
acceptance gate enabling accounts. See [Codex beta](codex-text-compare.md).

Label-v2 CI additionally runs local QR decoding against frozen pixels using the
locked OpenCV package, and verifies the readonly skill mount in Linux namespaces.
The same immutable artifact carries CLI, skill and report schema changes.

The frontend CI job includes the synthetic full-screen batch workspace acceptance
runner. The Codex PostgreSQL job includes batch-v3 draft/scope/one-session tests.
Release and rollback must drain queued v3 work before switching worker versions;
passing deterministic gates does not establish real photographed-label accuracy.

The backend CI additionally exercises A + Evolving label task persistence and its two-call fail-closed contract in a disposable PostgreSQL schema, without a live provider key.

## Model profile release gate

Required CI includes isolated PostgreSQL registry tests and the real-React settings
acceptance runner. The additive registry migration and settings frontend ship in
one immutable artifact. Merge only after required checks and independent review
pass; the successful main CI triggers the existing release/deploy workflow.
No in-place production edits or separate frontend deployment are permitted.


## PDF multipart allowance

The immutable release includes `scripts/configure_pdf_proxy.py`. It changes only enabled nginx site files proxying localhost:8765, raising existing 200m request limits to 201m for multipart overhead; application PDF bytes stay capped at 200 MiB. It validates nginx before reload and restores files on failure. The installer calls it before committing deployment. The first release introducing this installer hook requires the authorized operator to run the script from the verified installed release, since the preceding installer promotes its successor only after installation. Whole-application rollback remains unchanged; the additive request allowance is compatible with old application limits.

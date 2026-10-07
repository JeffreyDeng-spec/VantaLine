Codex comparison list/event read-transaction separation is a schema-free, Web-compatible release. It changes no worker topology, model binding, paid-call retry or database write fence. Existing `get` and the HTTP events ownership lookup still serialize. CI requires isolated PostgreSQL visibility and lock-wait checks; restore only the previous complete immutable release on failure.

The ephemeral legacy label-record index is a Web-compatible, schema-free release with source manifest v133 (341 entries). The CI backend job reads the exact first-parent `api.py` for projection replay, and separately fetches and verifies the immutable v550 API blob for 1,000/10,000-record same-run performance benchmarks; future CI runs retain that benchmark baseline. It changes no worker topology, cursor, write transaction, model binding or paid-call behavior. Restore the previous complete immutable release on failure; leave records and snapshots intact.

Label read-transaction separation is a Web-compatible release with unchanged schema, cursor format, worker topology and business API. Only three list-oriented methods lose the advisory lock; write and model-snapshot paths retain it. Source manifest v132 has 341 entries. CI requires isolated PostgreSQL lock/visibility/rollback evidence and the existing label concurrency/pagination smoke. Restore the previous complete immutable release on failure without rewriting task, snapshot or paid-call evidence.

The v131 native-run batching release changed only first-page read/query grouping; at that point the advisory read lock was unchanged. The v132 release removes that lock from three pure-list reads while retaining the 15-minute cursor format, embedded worker, database schema and write lock. Accepted-source projection is replayed locally; CI runs candidate contract checks and isolated PostgreSQL benchmarks before merge. Roll back to the previous complete immutable release without rewriting task or call evidence.

The PLC diagnostic receipt extraction ships in a complete Web-compatible release with unchanged API, PostgreSQL mutation and browser serial ownership. Source manifest v130 retains 339 actual source entries. Replay accepted-original behavior locally; CI checks candidate isolated PostgreSQL and existing PLC/HTTP contracts. Rollback restores the previous complete immutable release without rewriting lease or browser evidence.

The PLC diagnostic confirmation extraction ships in a complete Web-compatible release with unchanged API, browser serial ownership and PostgreSQL mutation. Source manifest v129 keeps the same 339 actual source entries. Locally replay accepted-original behavior; CI runs candidate isolated PostgreSQL and existing PLC/HTTP checks. Restore the prior complete release for rollback without rewriting lease or ACK evidence.

The PLC diagnostic reservation extraction ships as one Web-compatible release with unchanged API, PostgreSQL mutation and browser serial topology. Source manifest v128 (339 entries) includes the two new business modules. Locally replay accepted-original behavior; CI runs candidate offline/isolated PostgreSQL plus existing PLC/HTTP contracts. Roll back the previous complete immutable release without rewriting lease or receipt evidence.

The PLC model-rebind extraction ships as one Web-compatible complete release with unchanged API, lease transaction and browser serial topology. Source manifest v127 (337 entries) covers the changed maintenance source. Local checks replay accepted-original behavior; CI runs candidate offline/isolated PostgreSQL contracts and existing PLC/HTTP gates; rollback restores only the previous complete release.

The PLC lease acquisition extraction is a complete Web-compatible release with unchanged route signatures and runtime topology. Source manifest v126 tracks the new business modules; deploy and roll back only the complete immutable package.

The PLC lease-maintenance extraction is a Web-compatible module move with unchanged route signatures and topology. Source manifest v125 adds the two actual modules (335 entries); new tasks use its new fingerprint, while historical snapshots remain unchanged. Publish and rollback only complete immutable releases.

The legacy PLC config diagnostic extraction ships as one compatible Web release with the original GET/POST signatures and route order, plus source manifest v124. The accepted-original replay runs locally; CI runs the candidate offline contract and existing PLC/HTTP checks. Rollback restores the previous complete release without rewriting workstation or model data.

PLC dispatch/diagnostic HTTP extraction ships in one compatible Web release with five original root signatures and route order, and source manifest v123. CI runs the offline dispatch/diagnostic contract and existing PLC/HTTP checks. Rollback restores the previous complete release; existing workstation and call evidence remains.

PLC connection-lease HTTP extraction ships as one compatible Web release with five original root signatures and route order, plus source manifest v122. CI runs the offline lease contract and existing PLC/HTTP checks. Rollback restores the previous complete release; station leases, dispatch evidence and model snapshots are not rewritten.

PLC workstation-management route/service extraction ships as one compatible Web release with the original five root endpoint signatures, route order, request models and source manifest v121. The accepted-original replay is local; CI runs the candidate synthetic and existing HTTP/PLC contracts. Rollback restores the previous complete release and keeps persisted workstation and dispatch evidence.

Pipeline stage-transition extraction ships as one compatible Web release with its existing public adapter and source manifest v120. The original behavior was replayed locally; CI runs the extracted candidate against the same offline contract. The previous complete release is the rollback unit; historical task/model snapshots are not rewritten.

Pipeline advance lifecycle extraction ships as one compatible Web release with the existing pinned root callable, Event registry and task storage. CI runs offline cancellation/runner contracts; source manifest v119 records the two moved modules. Rollback uses the previous complete release.

Pipeline auto-Agent runner/scheduler extraction ships as one compatible Web release, retaining its pinned root callable and current registry. CI runs the offline runner contract; source manifest v118 includes both moved modules. Rollback uses the previous complete release.

Pipeline recommendation pre-generation extraction is one compatible Web release. The original pinned root callable and registry remain, CI runs the offline runtime contract, and source manifest v117 records the moved implementation. Rollback uses the previous complete release.

# VantaLine release management

Pipeline trained-model linking extraction is a Web-only compatible release. It keeps the original callable adapter and uses the existing `pipeline/training_links.py` manifest entry; rollback uses the previous complete release.

Pipeline training-status extraction is a compatible Web release that leaves terminal training synchronization and rollback packages unchanged. Source manifest v115 records the two moved modules; existing task evidence remains intact.

Pipeline reconciliation extraction is a Web-only compatible release. The existing list route, background threads and rollback package remain in place; source manifest v114 records the two moved modules for new evidence only.

Pipeline accessory add/remove route extraction is a single route-compatible Web release without data or topology migration. Source manifest v113 adds the actual moved modules; historical task evidence remains intact.

Agent feedback extraction is one route-compatible Web release without a database or topology migration. Source manifest v112 adds the actual feedback modules; historical task evidence and rollback release packages remain intact.

The pipeline list route extraction ships as a route-compatible complete Web release with no database or topology migration. Source manifest v111 includes the moved list modules; historical task fingerprints and snapshots are retained.

The Agent chat extraction ships as one route-compatible release with no deployment topology change or data migration. Its three actual modules are recorded in source manifest v110 for new task evidence; historical task snapshots remain intact.

Manual pipeline advance/cancel route extraction ships in the existing complete Web release with matching source manifest. CI runs its focused offline contract. Rollback restores prior code and topology but does not undo tasks already marked advancing or paused.

The pipeline task-delete route extraction preserves the existing single-Web release topology and database schema. CI runs its offline deletion contract. Rollback restores the prior complete code release; it does not resurrect tasks or linked resources already deleted under the current release.

The pipeline task-create route extraction keeps the existing Web release topology and rollback process. CI runs its offline creation regression; rollback restores the previous complete release while retaining current database records.

The pipeline task-update route extraction ships with the existing single Web release topology. CI runs its offline task-update regression; rollback restores the prior complete release while retaining the current database state.

Ship pipeline dataset/model availability projection, its three reader capabilities and root adapters with the matching source manifest. CI runs offline contracts; rollback restores the previous complete release without rewriting tasks or copying individual files.

Ship pipeline task label/name projection, three late-resolved ports and root adapters with the matching source manifest. CI runs its focused synthetic contracts; rollback restores the previous complete release without rewriting saved tasks or copying individual files.

Pipeline recommendation helpers and their typed ports ship with the existing Web adapters in one complete package. CI runs the focused synthetic helper contracts. The pinned background runner, scheduler and existing rollback procedure remain unchanged.

The current source manifest is v109 (296 entries). Per-domain notes describe which sources belong in the complete release; they do not identify when each module first appeared. Deploy and roll back only a complete release with its matching bundled manifest.

The pipeline AI task synchronization extraction adds a focused offline CI contract and two source-manifest entries in v102. It retains the existing single-Web release topology and does not change deployment or rollback commands.

Ship pipeline background publication, typed ports, root adapters and source manifest in one immutable release. CI runs its synthetic 25-group contract. Rollback restores
the previous complete release while retaining media, task/call evidence and model
secret versions; do not copy individual files or reverse saved snapshots.

Package background-library selection, its typed ports, root adapters and manifest
together. Roll back through the previous complete release, retaining runtime state and
call evidence. Do not copy individual modules or reverse database state.

Package background evidence, typed ports, public adapters and manifest together.
Restore the previous complete release on failure, retaining media, tasks, model-secret
versions and call evidence. Do not copy individual modules or reverse database state.

Package profile generation, its typed ports, public adapters and source manifest
together. Restore the previous complete release on failure and retain tasks, media,
model-secret versions and call evidence. Do not copy individual source files or reverse
existing database state.

Package accessory profile payload services, typed ports, compatibility adapters and the
source manifest together. Restore complete prior releases for rollback while retaining
tasks, media, model-secret versions and call evidence; no individual source copying.

Ship physical dimension services, typed ports, root compatibility adapters and source
manifest together. Roll back the complete release while retaining task/model-secret
versions and call evidence; no reverse migration or individual source copying.

Ship accessory profile projection, its typed ports and compatibility adapters together
with the source manifest. Whole-release rollback preserves task/model-secret versions
and call evidence; no reverse migration or individual source copying.

Ship display label service, size projection, typed ports and compatible public adapters
together with the source manifest. Whole-release rollback retains media, tasks,
model-secret versions and call evidence without reverse migration or individual file
copying.

Ship reference evidence, its ports, public adapters and source manifest together.
Whole-release rollback preserves tasks, media, model-secret versions and paid-call
evidence; no reverse migration or individual file copying.

Ship preview asset loader, selector, ports and public adapters together with manifest. Whole-release rollback preserves task/call evidence, media and model-secret
versions; no reverse migration or individual source copying.

Ship compositing helpers, AssetCompositor, capability ports and adapters together with
manifest. Roll back the complete previous release while preserving task evidence,
media and model-secret versions; no reverse migration or individual source copying.

Ship preview sprite decoding, renderer, capability ports and adapters together with
manifest. Whole-release rollback preserves existing media, task/call evidence and
model-secret versions; no reverse migration or individual source copying is needed.

Ship the materialized asset services, typed ports, root adapters and manifest in one
complete release. Whole-release rollback preserves media, tasks and secret versions;
no reverse migration or individual source copying is required.

Release preview pose policy with its existing domain module, typed ports, root adapters
and manifest as a complete package. Roll back the whole release while preserving
tasks, media and secret versions; no reverse migration is needed.

Deploy the pose policy module and ports with their public adapters and manifest in
one complete release. Roll back the complete package while retaining tasks, media and
model-secret versions; no reverse migration or individual file copying is required.

Deploy the four cutout geometry modules and their adapters with manifest as one
complete release. Restore the previous complete package on failure, preserving tasks,
media and model-secret versions. No schema or physical-device change is included.

Ship the cutout runtime owner, both consumer workflows, local ports and root adapters
with manifest. Roll back the complete release, preserving tasks, media and call
evidence. The old private root cache/lock bindings are replaced, not mirrored; public
helper signatures remain compatible.

Ship accessory alpha masks, material dispatcher, local ports and root adapters together
with manifest. Restore the previous complete release for rollback; retain task,
media, configuration and call evidence without inverse migration.

Ship the sprite artifact writer, canvas normalizer, local ports and root adapters together
with manifest. Use whole-release rollback and retain task, media and model evidence;
no migration or installer topology change is introduced.

Ship all five sprite metadata sources and their adapters with manifest. Existing
installer and service topology remain unchanged; roll back the previous complete release
without copying individual source files or rewriting historical snapshots.

Ship sprite geometry modules, local typed operations and root adapters with manifest.
Installer and service topology remain unchanged. Restore the previous complete release if
validation fails; do not copy individual production source files.

Ship object preprocessing and its local typed capabilities with source manifest and
root adapter. Existing installer and rollback procedures remain; restore the previous
complete release rather than copying individual source files.

Ship crop analysis, selection and typed geometry ports with their root adapters and
source manifest. Existing installer, service topology and rollback procedure remain.
Restore the previous complete release if validation fails.

Photo-highlight sprite coordination and its typed ports ship with the root adapter and
source manifest. Existing lifecycle, worker topology and installer are unchanged.
Rollback restores the previous complete release without an inverse data migration.

Photo-highlight input/comparison services, pure mask functions and their ports ship in
the same release as the root adapters. Source manifest records their actual modules.
Rollback restores the previous complete release without rewriting historical evidence.

Photo-highlight workflow services and their source adapter ship together in the release.
Manifest includes their actual source files. Rollback restores the previous complete
release and preserves task, media and model-call evidence.

Pose chroma, cutout, sprite-build and materialization services ship with their typed ports and
root adapters in the same release. Manifest includes the actual source modules. Rollback
restores the previous complete release without rewriting historical snapshots or evidence.

Pose call registration, execution and sample preparation ship with explicit capabilities and
root adapters in one release, covered by source manifest. Restore the previous complete
release on rollback without changing historical task snapshots or model versions.

Pose render configuration, content and artifact services ship together with their narrow ports
and root adapters. Source manifest records the actual source files. Rollback restores
the previous complete release without rewriting historical task or model snapshots.

Backend CI runs the active phase3d decision helper through an isolated offline entry, alongside
the existing source-location contract. This restores three-result empty-sync coverage; it does
not assert full legacy workflow or physical-device acceptance.

Pose planning policy, generation/cache and task assembly ship with explicit ports and root
adapters in one release. Source manifest records actual prompt sources; rollback restores
the previous complete release without rewriting historical tasks or model versions.

Pose asset and template services ship with their narrow ports and application adapters in
one release. Source manifest includes all implementations. Restore the previous complete
release without rewriting historical evidence.

Agent orchestration state and call-record services ship with their typed ports and application
adapters in one release. Source manifest fingerprints the implementation. Restore the
previous complete release on rollback without rewriting task or model history.

Agent pipeline actions and turn commits ship with their explicit ports and root adapters in
one release, fingerprinted by source manifest. Rollback restores the complete previous
frontend/backend package and keeps task, model and call evidence.

Agent conversation and pipeline decision services ship together with their root adapters and
source manifest. The single task snapshot binding remains on the application entry. Existing
module-location smoke checks follow the moved implementations; rollback uses the whole prior
release without rewriting historical records.

Agent settings HTTP handlers, application adapters and source manifest ship together.
Route registration, authorization and terminal409 behavior remain compatible. Rollback uses
the previous complete release; do not replace individual files or rewrite historical snapshots.

Agent protocol, invocation, discovery and recommendation services and source manifest
deploy in one package. Offline contracts retain the original accounting boundary and fallback
scopes. Restore the previous complete release for rollback; do not replace individual modules
or rewrite model snapshots and usage evidence.

Agent settings policy, public projections, legacy persistence, typed capabilities and manifest ship together. Synthetic contracts cover permissions, callback ordering, failure evidence and
independent instances. Rollback restores the previous complete package and retains runtime state.

Key identity, local secret-file services, typed capabilities and source manifest deploy
as one package. Required offline tests cover persistence ordering, error evidence, safe references
and independent service instances. Rollback selects the prior complete release without reverting
or rewriting runtime secret material.

Provider key registry adapters, business module, capabilities and source manifest ship
together. Required CI verifies provider-specific normalization and public-key redaction without
using live credentials. Rollback uses the prior complete release.

Provider configuration defaults, validation, public URL formatting and manifest ship
together. CI preserves error contracts, eager fallback evaluation and dependency timing with
synthetic values. Rollback uses the previous complete immutable release.

Legacy JSON/image settings, root callbacks and manifest deploy together. Required CI
checks existing precedence, exception handling, callback timing and independent compositions
without paid requests. Rollback selects a complete prior immutable release.

Status projection services, root adapters and manifest deploy as one immutable release.
Offline CI covers restricted/admin views, unchanged field exclusions, callback timing and
independent compositions. Installation and rollback use complete release packages.

Provider orchestration, root adapters, explicit capabilities and manifest deploy together.
CI preserves model-selection guards, existing retry budgets, backoff, compatibility behavior and
failure evidence with synthetic providers. Installation and rollback select a complete immutable
release; no individual source file or historical snapshot is replaced separately.

Agnes/Qwen image transports and manifest deploy together with their root adapters.
CI checks request and download failures, the existing one-time Agnes compatibility fallback,
model accounting and dependency isolation using synthetic responses. The existing whole-release
installation and rollback procedure remains unchanged.

Gemini transport, explicit ports, root constructor/cache-default adapters and source manifest ship together. Offline checks preserve request, resource, dependency-capture and accounting
boundaries. Deployment and rollback continue to select a complete immutable release.

The OpenAI-compatible transport and its additive instance-accounting adapter ship together
with source manifest. Offline contracts check original requests, usage, failure evidence,
dependency capture and resource lifecycle. Existing provider families and release topology stay
unchanged; deployment and rollback always select the complete immutable release.

Provider-foundation modules, their root aliases/adapters and source manifest ship in one
immutable release. CI validates classification, payload parsing, dependency failures and exception
serialization with synthetic input. The existing deployment and worker topology remains unchanged.

Detection image encoding, inspection-image storage, reference collection/rendering and
source manifest ship together. CI runs synthetic media contracts with existing detection and
model checks. No publisher or service topology changes are introduced in this extraction.

Image/video upload services, video projections and manifest ship as one immutable package.
CI follows the actual moved upload implementations in the PLC no-dispatch guard and runs synthetic
upload contracts. Root HTTP route order and video snapshot binding remain part of acceptance.

Profile-cache policy, store, flow and manifest ship as a single immutable package. CI runs
the isolated cache suite plus existing accessory/detection callers. There is no file-format,
cache-key version, provider or runtime-topology migration. Rollback restores the previous complete
release while retaining existing cache, task, model and call evidence.

Presence inspection, its narrow ports and manifest are one immutable release unit. CI runs
the offline service contract alongside existing detection and model contracts. This extraction adds
no worker, schema, installer or provider change; rollback restores the prior complete release.

Detection orchestration, its ports and source manifest ship in one immutable package.
CI runs both offline suites and follows the moved implementations in the PLC contract. Model scope
remains on the root entry; there is no runtime topology, installer or schema change. Rollback restores
the previous complete release and retains task, model and call evidence.

The annotation module and source manifest are packaged with the existing web service.
CI includes synthetic geometry/rendering/output contracts. No service, migration or installer
change is needed; rollback restores the previous complete release and keeps stored task evidence.

The presence result module and manifest ship in the same immutable release. CI runs the
offline normalization contracts. This extraction needs no service, schema or installer change;
rollback restores the previous complete package while retaining task and model snapshots.

Failure projection/result modules ship with source manifest as part of the immutable package.
CI runs their offline contracts. There is no service, schema or installation change; rollback restores
the previous complete release and retains existing task records and model snapshots.

Presence payload/validation modules and source manifest are packaged together. CI adds their
offline contracts. No install command, worker service, schema or runtime switch changes; rollback
restores the previous complete package without rewriting stored task snapshots.

Accessory lookup and detection requirements ship with source manifest in the same immutable
package. CI runs their offline behavior contracts. There is no schema, service topology or install
command change; rollback restores the previous complete release and retains stored snapshots.

Retired task/refresh modules and source manifest ship together in the immutable release.
There is no schema, worker service, deployment switch or release-command change. Original failed
settlement and read-only historical views remain; rollback restores the previous whole package.

The retired request/status module ships with source manifest in the complete immutable
release. It changes no endpoint, environment switch, deployment command or enabled capability.
Historical snapshots remain unchanged and rollback restores the previous whole package.

The watcher module and source manifest ship with the full immutable package. Startup hook
registration remains at its original position; invocation is still a no-op. This change enables no
service and adds no migration or deployment command. Rollback restores the previous whole release.

Worker artifact import and source manifest ship with the complete immutable release. There
is no schema, worker service, model algorithm or release-command change. Existing runtime files
and historical snapshots are retained; rollback restores the previous complete release.

Worker bundle metadata/submission and source manifest ship as one immutable package.
Historical snapshots, worker topology and release commands remain. This extraction neither enables
retired worker execution nor changes fallback policy; rollback restores the previous whole release.

Streamed worker transport and progress modules ship with source manifest as one immutable
package. Existing worker topology and release commands remain. This is a structural extraction;
no worker is enabled, schema added or partial-file deployment introduced.

Remote training and worker compatibility modules ship with source manifest as one immutable
package. Historical model snapshots remain unchanged. No worker topology, schema, dependency,
release command or retired-feature behavior changes; rollback restores the previous whole package.

Background query, validation, upload services and HTTP adapters ship together with source manifest. The three relocated business source files are included for new task fingerprints; stored model
snapshots remain intact. No route, migration, worker topology or release command changes.

Background Codex transport, task runner and submission ship together with source manifest.
The manifest records the actual relocated sources without rewriting historical model bindings.
This batch does not enable a separate label worker or alter deployment/rollback commands.

The three background write modules ship together with source manifest, which records their
actual sources for new task fingerprints. Historical task bindings and fingerprints remain
unchanged. There is no topology, schema, model-provider or deployment-command change.

Background manifest, seeding, catalog and selection modules ship as one immutable-package change.
Source manifest includes their actual sources for new task fingerprints and leaves historical
bindings untouched. There is no schema or worker-mode change; rollback uses the previous whole
release while preserving background assets and manifests.

Jobs query, task mutation and HTTP adapter modules ship with the complete immutable package.
Source manifest tracks the moved query/mutation and image-control adapter sources for new fingerprints without rewriting
historical snapshots. This batch adds no schema, migration or worker topology; whole-release
rollback preserves task records and existing control-operation evidence.

RunPod transfer service/store/API move together in the immutable release. Source manifest
tracks the moved business and file-persistence sources for new task fingerprints; historical
snapshots remain unchanged. No migration or worker-topology change accompanies this batch, and
rollback uses the previous complete release while retaining transfer evidence and queued tasks.

The training launch/status module extraction is an immutable-package-only change. Source manifest includes the moved launch and status business files; historical task fingerprints remain intact.
No schema, migration, worker topology or training/model policy changes. Rollback restores the whole
prior release while retaining queued tasks and their model bindings.

CI includes training input/state and immutable preview-fingerprint contracts. Source manifest
and all four cache/approval/dataset/status modules must travel together. This extraction changes no
route, schema, migration, model/prompt policy or worker topology. Whole-package rollback preserves
stored task snapshots, preview approvals and runtime task settlement records.

CI includes preview workflow and artifact contracts. Publish the four preview workflow modules
with source manifest in one immutable release. No route/schema, migration, model policy or
worker topology change. Restore the previous complete package on failure; preserve preview files,
plan JSON, user state and historical task snapshots according to existing write semantics.

CI includes full preview renderer contracts and the original pixel/metadata/call fingerprints.
Ship renderer, its typed ports and source manifest in one immutable package. No API, model,
prompt policy, dependency, migration or process topology changes. Whole-package rollback preserves
existing task snapshots and generated images/datasets; individual source files must not be copied.

CI includes preview layout contracts. Publish geometry, masks, placement and source manifest
in the same complete release. This batch changes no routes, dependency versions, migrations,
worker topology or rendering algorithm. Rollback restores the prior package and source manifest;
stored task snapshots and generated datasets remain intact.

CI includes deterministic background pixel and orchestration contracts. Ship both background
modules and source manifest in the same immutable release. No dependency, migration, route,
worker topology or rendering algorithm changes. Rollback restores the complete prior package and
its matching source list, preserving historical snapshots and existing generated datasets.

CI adds the resource-mutation contract with an isolated PostgreSQL schema. Package mutation and
link services plus the five HTTP adapters in the complete immutable release. No migration, setting,
worker topology or source-manifest version change is introduced. Roll back the whole previous
package while retaining resource records, files and historical model references.

CI adds resource-catalog contracts. Ship the dataset catalog, resource query and HTTP adapters
with source manifest in the complete immutable release. Routes, storage schema and process
topology retain their existing contracts. Rollback restores the entire previous package while
retaining task records and historical model snapshots.

CI includes the archive/artifact contract. Package all three new file-handling modules and
source manifest with the whole release. No database migration, endpoint, deployment service,
worker contract or dependency is added. Restore the previous complete release and retain task
records, archives, imported artifacts and historical model references.

CI includes the offline RunPod flow contract. Ship submission, output-parser and flow modules
with source manifest. This batch changes no request/worker contract, dependency, service,
migration or deployment topology. Rollback restores the complete prior release while retaining
remote job identifiers, task evidence and stored model snapshots.

CI includes the training dataset contract. Ship all four sample-generation modules and source
manifest as part of the same immutable release. There is no database migration, worker
switch, new dependency or training process change. Whole-release rollback retains task/model
snapshots and existing sample files; this extraction performs no media cleanup.

CI includes the offline training runner/submission contract. Package the three extracted
training modules together with source manifest. Training still runs through the existing
process/thread topology; no new service, dependency, environment key or migration is added.
Rollback restores the previous complete release while retaining frozen model references.

CI runs the training-state service contracts. Deploy all four completion/state modules
with source manifest in the same immutable package. No migration, environment setting,
worker topology or release restart change accompanies this batch; rollback uses the prior
whole package and retains task/call records and frozen model references.

CI includes `smoke_training_executor_client.py` for the extracted executor settings and
active RunPod adapter. This batch changes neither release topology nor training payloads.
It requires no new environment variable or migration and rolls back as a complete release.

Training lifecycle CI adds synthetic process/permission contracts and an isolated
PostgreSQL deletion/late-update scenario. Ship the lifecycle, views and runtime owner
modules together. Existing startup callbacks and process topology remain; the model
current source manifest covers all three moved files. Rollback remains
a complete immutable release.

Pipeline store CI adds synthetic and isolated PostgreSQL contracts. The repository
source gate inspects all eight real task/state selections and thirteen root forwards,
without counting composition callbacks twice or lowering its original threshold.
Ship the two stores, pure state policy and source manifest in the whole release.
Worker launch, migrations and rollback topology are unchanged.

Training storage CI now exercises its disposable PostgreSQL schema and eight moved
helpers. The database source gate counts the three actual extracted entries, excludes
the composition callback from totals and retains the original minimum threshold.
Ship both training modules as part of the immutable release; launch and rollback
commands and topology remain unchanged. Source manifest now includes both
training identity and storage so relocated selection/binding inputs remain covered.

Backend CI now includes training discovery contracts with a disposable PostgreSQL
schema, and dependency checks admit the training/pipeline packages. Publish all three
new modules and source manifest with the complete immutable release. This batch
does not change worker startup, release commands or rollback topology.

Warmup method, path resolver, model loader and error formatter use narrow callback
getters at their original expressions, after preceding work and before argument
conversion. Missing callbacks retain argument effects; new getter failures stop
before them. No retry, lock or thread admission policy is added.

Warmup CI adds synthetic policy, prediction and runtime contracts while retaining
the startup callback in the assembled application baseline. Ship the three relocated
warmup modules and manifest together. Worker topology and release commands remain.

Local model factory lookup uses a narrow getter after path resolution and before
string conversion, preserving callback replacement and missing-callable argument
effects. Existing cache publication order and exception boundaries remain unchanged.

The local-model runtime batch adds synthetic selection/cache coverage and ships both
new modules with manifest. It retains the current warmup entry points, in-process
inference and immutable whole-release deployment/rollback.

Task projection/catalog CI adds the focused synthetic smoke and keeps the original
resource and detection endpoint checks. Manifest records the new model-input
assembly sources. Whole-release rollout/rollback and worker startup are unchanged.

The detection task-store batch adds its synthetic and disposable-PostgreSQL smoke
to backend CI and updates the repository source gate to inspect the extracted store.
Deployment/rollback remains the complete immutable release with the current topology.
Row decoding and background callback getters resolve at the original expressions:
after preceding work and before fetch/string/mapping argument effects. Missing
callbacks preserve argument evaluation and TypeError. Source manifest covers
the three task modules; no retry, cache policy or transaction change is introduced.


The detection OCR batch adds its synthetic smoke and ships `runtime.paddle` plus
five OCR modules with source manifest. Local factories never load real models in
these contracts. Keep the complete application and incoming/OCR regression checks;
release startup, worker topology and whole-package rollback remain unchanged.
Attachment crop, score and match getters capture the current callable at each
original expression, before argument effects. Missing callbacks still evaluate
arguments and raise the original TypeError. Single-image OCR retains its existing
Exception handling; batch failures retain the existing per-image fallback. No new
retry or model-initialization lock is introduced.


The detection-result extraction adds synthetic backend smoke and admits the new
`detection` package to dependency-direction checks. It preserves the HTTP contract,
model parameters, worker topology and release commands. Ship source manifest
with all five detection modules to retain their source coverage for new tasks.
Historical snapshots remain untouched; whole-release rollback is the recovery unit.

The legacy incoming workflow batch adds its focused smoke to backend CI, retains
both original incoming endpoint and repository checks, and compares the complete
assembled HTTP baseline. It does not change worker topology or launch commands.
Source manifest records the relocated OCR input orchestrator for new snapshots.
Rollback remains the previous immutable release with existing persistent state.

OCR/Beta CI adds ten offline initialization, image, cache and composition groups.
Ship the analysis, comparison-cache and HTTP modules with manifest and the root
state aliases. Model names, flags, business prompt versions and deployment topology
are unchanged. Full-runtime CI must retain the existing incoming/Beta endpoint and
model-snapshot checks before any sequential production rollout.

Incoming-store CI adds isolated file/JSON/SQL contracts, root composition checks and
an explicit disposable-schema PostgreSQL group. Existing incoming/text endpoints
remain required. Ship both the runtime file adapter and legacy store with the root
aliases in the immutable artifact; database schema and worker topology are unchanged.

Comparison/review CI adds eight offline boundary groups and six route-identity
checks. Ship the submission, review, API and port modules plus manifest together;
the source list now includes the actual comparison input and strict-prompt files.
Business prompt text/version stays unchanged. Retain old task evidence on a normal
whole-release rollback; no new worker mode is enabled by this package.

Standard-workflow CI adds seven native HTTP and failure-boundary groups while
retaining original document review and real PostgreSQL checks. Include the API,
three business services and explicit ports with the matching root composition in
the immutable artifact. Runtime topology and complete-release rollback stay unchanged.

Revision/projection/diagnostic CI adds six isolated behavior contracts and assembled
application identity checks. Ship these modules and their root adapters together.
Manifest and normal whole-release restart/rollback apply; no new topology or
model configuration is enabled by this structural batch.

Text-media CI adds real image/PDF and application-composition contracts. Package
both media/image modules with source manifest, which covers their migrated
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

Preparation CI adds synthetic workflow contracts and source manifest includes
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

The source-safety CI job runs the offline COS evacuation smoke. The operational
tool does not run during release installation and does not enable COS in the
application. Merging its tooling alone cannot authorize source-file removal or
disk retirement; use the independent cutover gates in the production runbook.

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


## Agent policy read transaction

The Agent policy read-path change has no topology or schema migration. Required backend CI now runs the original Agent operation PostgreSQL regression and a separate isolated-schema read concurrency regression. The production service remains on the existing immutable artifact and release/rollback process; no new worker is enabled by this change.


## Fixed-reference model read transaction

The fixed-reference model read change is compatible with the current single-service embedded-worker release. Backend CI runs a new isolated PostgreSQL concurrency regression alongside the existing registry test. There is no schema, secret migration, prompt-source update or topology change; use the ordinary immutable release and whole-release rollback process.


## Model registry initialization fast path

The model registry initialization fast path is a read-path-only change for already initialized installations. Cold migration and whole-release rollback use the existing topology and storage. Backend CI adds an isolated PostgreSQL cold-race/failure regression alongside the registry and fixed-reference tests; no worker or schema change ships with this PR.

## Model task snapshot read transactions

The snapshot read change has no schema, release topology, migration, or configuration change. The isolated PostgreSQL regression joins the backend CI gate; continue the normal immutable Web release and rollback procedure.

## Model admin public read transaction

This read-path change has no schema, topology, migration or configuration change. The isolated real-PostgreSQL projection regression joins backend CI; continue the normal immutable Web release and full-package rollback procedure.

## Label list-only run payloads

This read-only transfer change has no schema, topology, configuration or worker-mode change. The accepted v564 list source and isolated PostgreSQL 1,000/10,000-task comparison are CI gates. Release and rollback remain full immutable packages.

## Embedded release installer bridge

An embedded-only immutable package now declares `RUNTIME_TOPOLOGY.json` with the exact release commit and sole service `vantaline`. The installer rejects a missing or unsupported declaration before stopping the Web service. The successor controller additionally understands fixed schema-2 embedded/external declarations with runtime protocol 1, and the preceding repair bridges emitted schema 1 embedded; the current activation package emits schema 2 embedded with runtime protocol 1. The first bridge release is still applied by the preceding host installer; after health acceptance, that installer promotes the bundled successor. The release workflow verifies the promoted installer SHA-256 against the packaged file and checks the live `/api/version` commit before publishing. A later embedded release is required to exercise the new installer on the host. This bridge does not start, stop, or roll back an independent label worker.

An already-installed retry checks the live commit before installer promotion. It may validate an older package without a topology manifest, but it never promotes an installer from that legacy package. If the application has passed health checks and installer promotion then fails, the installer exits nonzero while preserving the accepted application; uploading and applying the same release again retries promotion. Do not publish the GitHub Release until the installer digest and live commit agree.


The COS compatibility stage adds a separate artifact-storage CI job, an additive
file-index migration and pinned official COS SDK dependencies. Default local mode
remains unchanged. The installer dependency check must pass before publishing the
complete package; this change preserves the existing topology, signal handling,
installer SHA promotion and same-release retry fixes. Enabling COS and retiring the
disk require the separate production-runbook gates and a complete COS rollback
release. Prompt source manifest v138 includes the storage adapter modules and native image adapter.

The COS compatibility release includes an operator-invoked temporary-volume provisioning script. Merely installing the release does not create volumes, enable COS, or unmount business data. Any commissioning and storage-mode change requires the separate runbook gates and a complete COS-compatible rollback artifact.
## Label consumer lifecycle

The label lifecycle controller ships in an embedded-only complete release. CI exercises real-thread drain contracts and the existing label/PostgreSQL, HTTP, frontend and package gates. No worker service is installed or enabled. Application shutdown waits at most 480 seconds, and the managed embedded installer writes its owned 500-second stop allowance, then checks effective TimeoutStopUSec and KillMode before stopping any service. Web may retain the commissioned exact 510-second administrator allowance; other unsupported effective values or kill modes abort before stop and restore the captured unit state. Rollback restores the prior complete release and retains all task/call evidence.

The label benchmark evidence correction changes CI diagnostics only. Main CI previously failed an existing payload P95 guard before emitting its summary, and automatic deployment correctly remained blocked. The corrected script prints all synthetic samples and original limits before asserting. Production code, schema, topology and rollback remain unchanged; a passing PR alone does not substitute for main CI and release acceptance.

The COS startup checksum correction ships as another complete compatibility release. Keep the installer SHA-promotion and same-release retry behavior intact. Verify the full dependency lock under each service account, then exercise a source-inaccessible application restart before selecting a COS rollback release.

## Runtime controller bridge, still embedded

The installed script is generated from the checked-in installer template and runtime modules. CI and packaging require byte-exact regeneration and reject dirty generation inputs. Promotion is still one atomic root-owned script replacement followed by a digest read-back. The deployment workflow also reads `--capabilities`; capability support is not evidence that a worker is enabled or accepted.

Schema-1 releases keep the existing Web restart path. A schema-2 transition journals the previous complete release, managed unit files and enable state before mutation. It checks live build/PID/instance/heartbeat/configuration identity, closes label admission, allows the existing queue to finish, and obtains a same-instance paused/empty acknowledgement. The 500-second shared controller budget covers drain and stopping all old roles; the managed unit template remains 500 seconds, with exact effective Web allowances of 500 or 510 seconds and worker allowance of 500 seconds. Effective systemd settings are verified. Inactive service state is not a drain acknowledgement. New roles are checked before admission is restored. Only the fixed Web drop-in and label-worker unit can be changed; unmanaged files are refused.

A failed transition stops candidate roles before restoring managed units, the previous complete release pointer and its declared roles. Failed stop/drain evidence fails rollback closed and retains the journal and releases; it never restarts an old consumer alongside an unverified new one. Managed embedded controls activate only in a schema-2 package after the accepted controller and additive state migration. The preceding recovery-storage repair package declared schema 1 and left these controls inactive; the current activation package turns on only the embedded controls. Private-namespace drills and real PostgreSQL/control-socket integration cover that bridge. Shared configuration and independent-worker acceptance are still required before publishing an external topology.

An unfinished managed journal is examined under the root release lock before requiring a live Web service. A stop before pointer replacement restores and verifies the previous release before retrying the exact archive; a verified pointer switch before startup starts the candidate in the paused state, then repeats full application acceptance. A same-release retry cannot promote a merely drained candidate: it must finish the journal-bound acceptance and preserve any preexisting maintenance/pause state. Interrupted rollback pointers are revision-bound and reusable. External-to-schema-1 downgrade is rejected before stopping services; its rollback partner must be a managed embedded bridge.

The rollback journal records restored pointer/units before restarting old roles and binds their verified instances before reopening admission. Same-transition recovery then resumes that restoration without stopping a live old consumer, including a crash after admission reopened. Retain the journal until the whole-release health check and final cleanup succeed.

Rollback pauses the candidate before waiting for its active runs and admitted iterations to finish; it preserves queued rows without starting paid work on an unaccepted build. A forward switch from an already-paused predecessor also retains its backlog and pause intent. An active predecessor still drains its queue before a normal forward switch. State-machine and rendered-installer faults cover queued legacy-to-managed rollback and paused-backlog transitions; queued work is not evidence of an active call.

## Label runtime state preparation

The label runtime-state preparation release adds only the idempotent `2026_10_04_label_runtime_state` migration, matching schema registries and synthetic checks. It neither starts a separate worker nor enables a maintenance gate. The previous complete release is compatible with the additional table; rollback preserves it and uses the existing full-package process.


## Managed embedded label control

The managed embedded label runtime requires the preceding controller and empty operational-state migration before activation in a schema-2 embedded package. It retains one Web service and two embedded label threads. Root control commands are bounded and peer-authenticated; duplicate role startup fails before operational state is changed. Real PostgreSQL, thread and HTTP tests cover admission races, pause, re-entry and restart. External worker/configuration activation remains a later independently validated package.

The control endpoint owns a dedicated PostgreSQL connection factory with explicit connect/TCP failure-detection settings; request and paid-task connections retain their configuration. SQL timeouts apply after connection, and the root client has a separate bounded acknowledgement deadline; these do not constitute a hard total deadline for every driver operation. A control-thread shutdown timeout retains its role lock and fails that controller generation until process restart. Regression probes block connection creation and verify no duplicate role, then release the old thread for cleanup. A real claim/processing-substitute/cleanup integration proves pause does not acknowledge drain until two admitted iterations finish, while queued task snapshots remain unchanged.


## Recovery storage repair bridge

The repair bridge is a new complete schema-1 embedded release. The previously
installed controller applies its ordinary Web restart and promotes the successor
only after application health passes. Use a fresh release identity: retrying an
already-installed package through the old controller still checks its old journal
parent and fails on an application-owned backups directory. The repair does not
change ownership or modes of the existing application tree or backups.

The successor creates only the absent fixed `/var/lib/vantaline-release` directory
as root with mode 0700 during installation. It validates every ancestor, rejects
symlinks, non-root owners and writable ancestors, and refuses unsafe existing
state without repairing it. Capabilities, topology validation and mode discovery
remain read-only. Recovery journals remain root-owned 0600 files written by atomic
replacement and fsync. The existing guard and PID lock retain their locations and
acquisition order for cross-version coordination. Any old-location journal, any
other-release new-location journal, or an invalid current journal blocks before
service stop; old evidence is never silently migrated or deleted.

If old-controller installer promotion fails after the application was accepted,
keep that accepted version running and collect the exact version and installed
script digest. Its same-release retry cannot repair this ownership mismatch.
Recovery requires another reviewed, CI-approved, newly identified complete
schema-1 release through the ordinary deployment process. Do not repack or replace
an existing release, copy an installer, change permissions, or clear locks/journals.
After the successor is promoted, normal same-release retries use its trusted state
location. Schema-2 commissioning remains a separate release; neither this bridge
nor capabilities alone enable an independent worker.


## Commissioned Web stop allowance compatibility

A separate schema-1 embedded bridge promotes the installer policy before any later
managed activation. It accepts only exact effective Web stop allowances of 500 or
510 seconds; a future independent worker must still use 500 seconds. Both roles
require `KillMode=control-group`. The controller writes its existing 500-second
managed template and neither rewrites nor deletes an administrator's later 510-second
drop-in. All other effective durations, including near values and infinity, fail
before stopping services.

The shared forward drain/stop deadline remains 500 seconds. The systemd allowance
is a fallback termination setting, not a promise that every process exits within
the controller deadline. After nonblocking stop, the controller requires inactive
or failed state and both MainPID and ControlPID zero. A deadline failure prevents
pointer switch and candidate startup; an unsuccessful whole-release rollback
retains recovery evidence and admission fencing. This bridge still declares
schema 1 and cannot activate an external worker. Installed-controller digest and
whole-release acceptance must precede the separate schema-2 activation package.

The stop-allowance bridge also prepares planner statistics in its isolated synthetic PostgreSQL benchmark before timing. This test-fixture correction does not execute ANALYZE on production or change business SQL, indexes, runtime configuration or performance thresholds. Required CI must pass again on the resulting exact head.

## Managed embedded activation after compatible installer promotion

This complete package declares schema 2, runtime protocol 1, embedded mode and the
sole `vantaline` service. It is eligible only after both preceding schema-1 bridges
are accepted and the installed installer supports root-owned recovery storage and
the commissioned Web stop allowance. The bundled installer is unchanged from that
accepted predecessor. Application, model/prompt, database and PLC code are unchanged.

The first schema-1-to-schema-2 installation validates root recovery storage and
effective units, then stops the sole Web service using its existing shutdown
lifecycle and 480-second consumer wait. The schema-1 predecessor has no managed
control protocol: this first switch cannot acknowledge a maintenance pause or
require its whole queue to drain before stop. Queued records may remain for the
accepted successor. The controller must verify service exit before switching the
immutable build; the candidate starts paused until application health and matching
build/process/control identity pass. Failure restores the previous complete
schema-1 bridge and retains all task/call/model evidence; no external worker starts.

Later managed-to-managed forward transitions pause admission and drain an active
predecessor through its control protocol; a failed drain aborts and restores prior
intent. An already-paused predecessor retains its queued backlog. Missing
prerequisites or uncertain service exit block either transition. Main CI and live
release acceptance remain mandatory before shared runtime configuration or a
standalone worker can be activated.

## Proposal: shared label runtime configuration preparation

The preceding embedded configuration bridge introduced a bounded data-only snapshot of the existing label/database/storage/network settings, exact existing model-secret environment references and data directory. Unset and explicit empty values remain distinct. COS credentials are represented by their byte digest and transferred only through a private root-authenticated path; a worker must receive its own systemd credential directory. The pure contract and private-file roundtrip tests use synthetic values. The candidate Web wiring can capture a configuration revision and export its immutable snapshot only through the private authenticated control socket; public status contains only the revision. A prepared root file publisher writes immutable private versions and restores one atomic current pointer. The installed helper now embeds the audited data-only contract, captures a peer/build/instance-bound private export before external transitions, and journals the previous configuration pointer before mutation. It restores that pointer with the complete release on rollback, derives escaped mount dependencies and provisions the worker own systemd credential from root-owned bytes. No candidate application module is imported by the isolated root helper. Tests cover pointer interruption, export tampering, private modes, standalone execution and synthetic installer recovery. That bridge release retained embedded execution. Its complete-release acceptance is a prerequisite for the external activation described below.

## Proposal: standalone label process

The candidate `label_inspection.runtime` bootstrap reads the root-owned immutable configuration and its own systemd credential, checks the active package build/topology, initializes local storage, and creates separate thread-owned business and control repository factories. It imports no Web application. The existing model service is reused through an existing-registry reader: missing registration fails startup rather than migrating legacy settings. Secret-file syntax, environment precedence, immutable version references and usage accounting remain unchanged. Manifest v141 names 366 actual sources; historic snapshots are not rewritten.

In external mode, Web composition owns admission/control only and constructs no label consumer. The standalone process owns the existing two-thread consumer and its exclusive role socket; SIGTERM/SIGINT stop new work and use the existing 480-second drain budget. Real isolated PostgreSQL tests cover old-model resolution after settings changes and reader recreation, actual child PID/peer checks, duplicate-role rejection, signal drain and controller-driven embedded-to-external acceptance, failure and complete rollback. Synthetic model values and local storage are used; no paid inference or PLC call occurs. The bootstrap-only predecessor did not enable an external release. External activation remains conditional on preceding complete-release acceptance and final exact-build validation as described below.

Standalone signal handlers only assign a monotonic stop latch. Normal control flow performs drain and cleanup; initialization checks the latch before consumer startup, and each consumer admission checks it even across the check/start boundary. Real child-process tests inject repeated SIGTERM/SIGINT before and during initialization and while native thread startup holds the worker lock; no post-stop iteration is admitted. Already admitted iterations retain the existing drain budget.

## Proposal: label runtime monitoring

Managed processes publish bounded heartbeats on the existing private control thread with a five-second target interval after the previous tick completes. Database work and control requests can delay a tick. Each uses the dedicated thread-owned connection factory. The operational table stores only build/configuration/process identity, worker state, process-lifetime counters and fixed recent-error codes. A blocked heartbeat retains the same role lock on shutdown timeout. The private deployment protocol remains unchanged.

`GET /api/label-inspection/runtime` requires administrator access before any database call. Its short unlocked READ COMMITTED transaction samples state, queue and heartbeat in separate statements; these are not an atomic health snapshot. It returns queue/active counts, oldest queue age, maintenance/pause intent and expected-role heartbeats; missing, mismatched or older-than-15-second samples are unhealthy. Heartbeat freshness is sampled liveness, not a guarantee against a subsequent crash. Lock acquisition counts/total/max wait include successful and timed-out acquisition attempts. These and rejected duplicate submission/stage-call counters belong to the process lifetime: process restart resets them, while a control restart within the same process changes the instance but retains counters. Idempotent replay is not counted as rejection. Errors never include exception strings, media, customer fields, secrets or filesystem paths. Real PostgreSQL/HTTP tests cover authorization, redaction, actual lock contention, duplicate refusals, stale generations and heartbeat shutdown. Manifest v142 names 367 actual sources. The observability-only predecessor retained embedded execution; the external activation below is a separate release and requires acceptance of every predecessor.

## Independent label worker activation

The package now declares schema 2/protocol 1 with `worker_mode=external` and exactly
`vantaline` plus `vantaline-label-worker`. Publish this activation only after the
managed embedded, shared configuration, standalone bootstrap and monitoring releases
have each passed CI, independent review and complete production acceptance. The
installer and application logic are unchanged by this activation.

The installed controller binds configuration export to the accepted Web identity,
persists recovery evidence, closes new detection admission, and drains an active
predecessor queue. Failure to drain restores the predecessor intent and aborts.
A predecessor already paused retains its queue and pause intent. After verified
exit of the old Web consumer, the controller selects the complete release and
configuration, starts Web with no consumer, then starts the two-thread label worker.
Both exact build/configuration/process identities must pass before public acceptance
and admission restoration. No embedded and separate consumers overlap.

Failure pauses/stops the candidate roles before restoring the previous complete
managed embedded release, units, configuration pointer and admission intent. An
uncertain stop or failed rollback retains both releases and journals and reports
failure. Preserve task/call evidence and secret versions; do not requeue unknown
paid calls, reverse migrations, or copy individual files.

The PLC structural batch integrates previously checked same-domain extractions and runs their twelve smoke commands in backend CI. Its prompt-source manifest appends only the actual twenty new PLC/schema source files under one new manifest version. Existing task snapshots and old provenance are not rewritten; new snapshots identify the new release source set.

The auto-optimization structural batch combines previously reviewed same-domain relocations into one independently deployable change. It registers nineteen focused smoke commands and appends thirty-seven actual source files under manifest v144. CI, exact-head independent review and whole-package release verification remain required.

The pipeline structural batch integrates six previously reviewed workflow boundaries, registers six CI smoke commands and appends twelve actual source files under manifest v145. Exact-head CI/review and whole-release artifact validation remain necessary.

The accessory image workflow structural batch integrates reviewed domain services, registers eleven smoke commands and appends twenty-two actual source files under manifest v146. Complete CI, independent exact-head review and whole-release artifact validation remain mandatory.

Configuration and status source modules ship in the complete release with Web and the declared label worker. Four focused CI contracts and the existing source/HTTP/model guards are retained. Source manifest v147 contains the nine added files; rollback restores a previous complete release and preserves runtime/model evidence.

The summary-state preparation adds a real PostgreSQL migration gate to backend
CI. Its additive table and invalidation trigger ship together in one immutable
release; no application cache reader or standalone-worker activation ships in
this slice. Retain the derived objects during whole-release rollback. A bounded
DDL lock failure aborts transactionally rather than partially installing the
trigger. Local synthetic verification does not satisfy production ReleaseGo.

The pure label projection structural slice is separate from summary publication and performance changes. One actual source is added under manifest v148 and its pure contract is registered in CI.

Post-settlement summary preparation preserves the predecessor topology and leaves all business
repository/paid-stage logic unchanged. CI adds pure proof, worker failure/drain
and real PostgreSQL publication checks. The complete release carries manifest
v149/470 and the previous additive cache migration; no cache read or backfill
is enabled. Exact-head CI and preceding release acceptance remain mandatory.

The derived-label list reader preserves the predecessor release topology. CI compares the actual full list endpoint and real PostgreSQL paging to the frozen pre-reader method, then measures 1,000/10,000 synthetic tasks with 0/50/100% cache hits. Exact-head review/CI and preceding complete-release acceptance remain necessary; local candidate evidence cannot authorize bypassing release gates.

Reader activation includes a first-startup prerequisite on the actual Web repository connection. Failed verification prevents candidate control readiness and separate-worker startup; the existing installed controller follows whole-release rollback. It runs after the ordinary switch and may extend a failed restart window. No new root-executed candidate validator or installer bridge is introduced. CI includes restricted-role startup rejection and controller rollback, and the HTTP contract baseline changes only by the explicit new first startup callback.

The reader evidence revision changes benchmark/CI diagnostics only, with three mandatory complete A/B repetitions and a separate A/A control. Existing latency/memory/query gates remain unchanged. A failure blocks release; an earlier failed main run must not be described as accepted. New passing CI remains empirical evidence, not proof that the original tail-latency failure was environmental. Whole-release rollback remains the recovery unit.

Package `runtime/service_paths.py` and its typed ports with callers and the updated prompt-source manifest. Require both-platform original/candidate path checks and neighboring media/auth/HTTP/model contracts, followed by exact-head review and managed complete-release validation. No independent file deployment is supported.

Read-cache ownership changes only cache composition and state placement. Original/candidate behavior and actual analytics/artifact/state/task/HTTP checks must pass, followed by exact-head CI and independent release verification. No performance or stronger consistency claim follows from this relocation.

Directory lifecycle owners and callers ship in the same complete package. Construction is side-effect free; existing initialization behavior runs only when invoked. Require original/candidate lifecycle concurrency/failure contracts and neighboring runtime/HTTP checks before exact-head CI, independent review and release acceptance.

Direct foundation policy imports ship with existing consumers and source manifest v158. Require original/candidate and consumer contracts, full exact-head CI and complete-release validation.

File digest and naming policies move into already fingerprinted modules under manifest v158. Require original/candidate streams and neighboring artifact/training contracts before exact-head CI and whole-release acceptance.

Runtime repository HTTP access ships as a structural module move under manifest v158. Require original/candidate error and identity contracts, endpoint source/probe guards and actual PostgreSQL lifecycle checks, then exact-head CI and whole-release acceptance.

Protected configuration ownership under manifest v158 requires original config regression, real PostgreSQL concurrency/rollback, source binding guards, full HTTP and PLC contracts. It has no data migration, new setting or topology change. Rollback uses the previous complete accepted Web/worker release.

Historical integration record (before PR266; not the current bundled architecture): That foundation integration followed the accepted reader-readiness source manifest and retained its prerequisite. Its bundled manifest was v157 with 479 unique sources (including `label_inspection/readiness.py`); historical slice counts above refer to their original isolated candidates. The existing fixed reader benchmark protocol remained mandatory; that historical candidate did not include native-history aggregation. The current integration retains the native-history implementation accepted in PR266.

CI also checks native count/latest against the frozen pre-change list endpoint on
real isolated PostgreSQL, including mixed historical ordering and original plus
repeated-run performance workloads. These checks use synthetic data and no paid
model/PLC activity. They do not activate the external worker or replace production
release observation and whole-package rollback verification.

The native history reader combines a same-statement current-proof gate with result-local column-name reuse. A batch with no current owned proof uses the ordered fallback branch without history windows; proven batches retain guarded count/latest aggregation. The gate and both source branches use the original typed owner comparison rather than converting the owner parameter to text. This is a new candidate combining two previously separately measured mechanisms, not a retry or acceptance of earlier failed candidates. Both fixed performance protocols and their original latency, memory and query limits remain mandatory; no universal speedup is claimed.

Native list-history fallback now compacts a nonempty `quality` object only when every immediate value is a JSON string, boolean or null. This matches the existing public checked marker while avoiding unnecessary evidence transfer. Numeric and nested values stay intact so JSON decoding errors remain visible; other fields, ordering, detail payloads and old snapshots are unchanged. PostgreSQL/HTTP regressions cover flat Unicode/string/bool/null, empty and other shapes, and bounded-decoder failures. The original complete performance protocols and thresholds remain mandatory; private diagnostics are not acceptance.

The current native-history integration retains the accepted foundation and readiness modules. Its bundled manifest is v158 with 480 unique sources. Historical counts above describe earlier isolated slices. The original 47 reader/history cases and both frozen baselines remain required; legacy/manual/Beta SQL aggregation is not completed by this native slice.

The account/name policy batch integrates two independently checked structural moves and retains their original method behavior. Exact-head CI/review and serial whole-release observation remain required. Source manifest163/488 records actual files; this slice is separate from list-query performance work.

Origin/status projection service and typed capabilities ship with callers under manifest v163. Require original/candidate policy, actual middleware/auth/status and full HTTP checks before exact-head review and whole-release acceptance.

The administrator documentation domain registrar is structural under manifest v163. Require original/candidate guard and HTTP/cache isolation tests, existing auth and whole-app HTTP contracts, exact-head CI and independent release acceptance. API visibility and deployment topology stay unchanged.

Authentication graph composition is structural under manifest v163. Require domain, RBAC, two-application isolation, real PostgreSQL and whole-app HTTP regressions, then exact-head CI, independent review and whole-release acceptance. This does not activate additional workers or change the release topology.

Prompt-source manifest version 163 includes `auth/http_composition.py` and records the new composition source for future task fingerprints (488 source files). Prior task snapshots and secret references remain unchanged; model/provider behavior and release topology are unchanged.

The earlier identity-only candidate used manifest v162/488 on fac841. Its PR265 latency failure remains a recorded NoGo; those results do not approve this new integration.

This identity integration is rebuilt on main734e5e0 after PR266. It retains native-history SQL, readiness and all47 fixed reader/history cases byte-for-byte from that main. The complete manifest is v163 with489 unique sources; earlier slice counts are historical. This changed prerequisite requires fresh integration, hostedCI and release acceptance and does not explain or waive PR265 performance failure.

Provider proxy implementation and interfaces ship together under source manifest v169. Require original/candidate transport contracts, provider regressions, exact-head CI and whole-release acceptance.

The optional MCP client is packaged from its real provider module under manifest v169. Require original/candidate protocol and process-substitute contracts plus existing MCP default/opt-in behavior, exact-head CI and whole-release verification. Worker topology and production settings are unchanged.

The MCP runtime policy relocation is structural under manifest v169. Require original/candidate environment/payload/warmup contracts and existing MCP dispatch/default/opt-in regressions, exact-head CI and independent complete-release acceptance. It does not alter paid-call fallback or lifecycle policy.

The model warmup HTTP/domain split is a structural release under manifest v169. Exact full HTTP and original local-model/warmup regressions plus independent release acceptance are required. Startup and worker topology remain unchanged; the two-app registrar fixture is not proof of full server application-factory isolation.

Prompt-source manifest version 168 retains the same 494 source files and records the actual modified `server.py` and `detection/local_models.py` bytes for new tasks. Existing snapshots and secret references remain immutable. The local selection refactor does not change prompts, models, provider limits or release topology.

Image payload codecs extend the existing fingerprinted provider module under manifest v169. Require original/candidate and neighboring image-provider contracts, exact-head CI and complete release verification. No model, retry or image-validation policy change is included.

Historical integration record (before PR266; not the current bundled architecture): That model/provider integration followed the accepted reader-readiness source manifest and retained its prerequisite. Its bundled manifest was v168 with 494 unique sources (including `label_inspection/readiness.py`); historical slice counts above refer to their original isolated candidates. The existing fixed reader benchmark protocol remained mandatory; that historical candidate did not include native-history aggregation. The current integration retains the native-history implementation accepted in PR266.

This model/provider integration is based on main ad1292a after PR267 and preserves the native-history and reader-readiness implementation accepted in PR266. Its production and test sources match the independently reviewed model candidate 63df072. The complete bundled manifest is v169 with495 unique sources; earlier slice counts describe isolated candidates. Both fixed reader19 and history28 benchmark gates remain mandatory. Publication requires acceptance of the identity release, followed by this candidate’s own CI and independent review; the prerequisite’s first main CI AA failure remains recorded.

Detection request services and typed capabilities ship together with application routes. Require original/candidate workflow contracts and existing HTTP/auth/detection/pipeline checks, then exact-head CI, independent review and whole-release verification. This structural change must not be combined with CRUD policy or concurrency changes.

Detection rule routes and the new service ship as one complete package with manifest v173. Original/candidate contracts and neighboring detection/HTTP/permission/model checks precede exact-head CI and independent review; whole-release deployment gates remain mandatory.

Camera route and its typed workflow ship together with source manifest v173. Original/candidate failure-path tests, HTTP/permissions and PLC browser/upload contracts precede exact-head CI and independent release validation. No protocol, frontend bundle or runtime topology change is intended.

Detection rule composition ships with manifest v173. Require unchanged HTTP/OpenAPI/route-order contracts, two-application request identity tests and existing rule/catalog behavior checks, then exact-head CI and independent release verification. This narrows private root rebinding compatibility without changing the business API.

This detection integration retains the native-history and reader-readiness implementation accepted in PR266 and the identity release accepted in PR267. It is based on actual main bea11ce from PR268, retaining its Python-version-independent model-binding test fix. Main CI and release acceptance for PR268 must precede publication. All detection production and test sources, including the ordered application entry, match the independently reviewed detection candidate183f739. The complete bundled manifest is v173 with502 unique sources; earlier slice counts are historical. Fixed reader19 and history28 protocols remain mandatory; prior performance failures remain recorded.

The analysis graph composition is structural under manifest v174. Require existing and composed analysis behavior, real PostgreSQL, full HTTP/source checks and exact-head CI plus independent release acceptance. No query optimization or worker topology change is included.

This analysis candidate retains the native-history/readiness implementation and accepted model composition from main bea11ce. It is prepared after detection candidate af8d242 in PR269; actual-main rebind and detection release acceptance must precede publication. Analysis production/tests and the ordered entry match reviewed59db3d3. The bundled manifest is v174 with503 unique sources. The original history28 and reader19 benchmark protocols remain mandatory; recorded prior performance failures are retained.

Dashboard shortcut task ownership requires exact-head backend/HTTP/model/PLC regression, independent review and complete release acceptance under source manifest v175. No model, prompt content, schema or frontend behavior changes are included.

Accessory policies extend existing catalog/physical-dimension modules under manifest v175. Require original/candidate and neighboring catalog/rendering contracts, exact-head CI and whole-release acceptance; no algorithm or performance change is claimed.

Manifest v175 tracks four accessory workflow additions to already registered source modules. Require original/candidate boundary tests and existing domain regressions, exact-head CI and independent release acceptance; no algorithm or performance change is included.

This accessory candidate retains the native-history/readiness implementation and detection composition from actual main dcb4805, and follows analysis candidate bb3afa6. Actual-main rebind and analysis release acceptance must precede publication. Accessory production/tests and the ordered entry match reviewed c43118e. The bundled manifest is v175 with 504 unique sources. Original history28 and reader19 benchmark protocols remain mandatory; prior recorded performance failures are retained.

Image worker runtime ownership ships with original callers and manifest v176. Require concurrent-start and job-management contracts, exact-head hosted CI and full-release acceptance. The structural move does not demonstrate production workload drainage.

Pipeline runtime ownership ships with existing orchestration and source manifest v176. Require full list/advance/registry regressions, exact CI and whole-release acceptance. No production concurrency or recovery improvement is inferred solely from moving state.

Auto-optimization owner and all consumers ship together under manifest v176. Require runtime/consumer regression, real PostgreSQL state-store checks, exact-head CI and independent whole-release acceptance.

The v176 source-manifest change removes temporary settings indirection without changing algorithms. Require direct-port composition tests, downstream behavior/identity and PostgreSQL regression, full exact-head CI, independent review and whole-release verification. Python entry-alias rebinding is deliberately no longer a consumer configuration mechanism.

This background candidate retains native-history/readiness and detection composition from actual main dcb4805, and follows accessory candidate f397a31. Actual-main rebind and accessory release acceptance must precede publication. Production/tests and the ordered entry match reviewed 5a44e61. The bundled manifest is v176 with 507 unique sources. Fixed history28 and reader19 protocols remain mandatory; prior recorded performance failures remain retained.

Manifest v177 records the retained legacy PLC worker owner. Require fake-thread/state regression plus current PLC v4, browser/source, lease, full HTTP and release checks, followed by exact-head CI and independent complete-release acceptance. No server serial process may be started by this change.

The station active-lease ownership change is a structural release under manifest v177. Require exact-head CI, independent review and complete release acceptance; existing PLC contracts and actual PostgreSQL rebind/diagnostic cases must pass before merge.

The six legacy PLC readiness helpers ship under source manifest v177 with the existing topology and disabled server-serial startup. Exact-head CI, independent review and full release acceptance remain required; the readiness import stub is not a physical-device test.

The PLC runtime coordination ownership slice is structure-only. Prompt source manifest 177 adds plc/legacy_coordination.py truthfully for new tasks; existing model snapshots keep their previous version and fingerprint. Publish and roll back the complete package, preserving the current external label-worker topology.

PLC dispatch record logic now has its own source entry in prompt manifest 177 (512 paths). New tasks record the actual source manifest; historical snapshots remain unchanged. Deploy and roll back the complete immutable package with its existing runtime topology.

Prompt manifest 177 includes plc/legacy_operations.py as the actual source of the retained workflows (512 paths). Historical task snapshots are unchanged. This ownership-only slice retains the existing installer, services and full-package rollback.

This PLC candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows the reviewed background ownership candidate. Actual-main rebind and predecessor release acceptance must precede publication. Production/tests and the ordered entry match reviewed a139e03. The bundled manifest is v177 with 512 unique sources. Fixed history28 and reader19 protocols remain mandatory; prior recorded performance failures remain retained. Browser-only physical IO, uncertain-write no-retry and inert retained startup remain unchanged.

Prompt-source manifest178/513 adds runtime/web_shell.py for new task fingerprints. Existing task snapshots remain unchanged. Shell composition requires full navigation/auth and HTTP-order regression, independent review and exact-head CI; deployment and rollback continue using the complete release.

This Web-shell candidate retains native-history/readiness and detection composition from actual main dcb4805, and follows PLC candidate e73394d. Actual-main rebind and predecessor release acceptance must precede publication. Production/tests and the ordered entry match reviewed 4b28b8e. The bundled manifest is v178 with 513 unique sources. Fixed history28 and reader19 protocols remain mandatory; earlier recorded performance failures remain retained.

The unreachable-tail cleanup retains all currently reachable endpoint behavior, uses one complete release and changes no topology or migration. Its frozen-parent/compiled-prefix and actual HTTP comparison run alongside the original full application contract. CI, independent exact-head review and preceding release acceptance remain mandatory.

This unreachable-tail candidate retains native-history/readiness and detection composition from actual main dcb4805, and follows Web-shell candidate 82cc0d0. Actual-main rebind and predecessor release acceptance must precede publication. Production and the ordered entry match reviewed ed9dc91; the retained-tail test explicitly handles Python 3.10 frame cells and Python 3.11+ compiler metadata without skipping behavior checks. The bundled manifest is v179 with 513 unique sources. Fixed history28 and reader19 protocols remain mandatory; prior performance failures remain retained. Existing endpoints and live behavior remain; only statements following unconditional exits are removed.

The repository composition slice binds its HTTP adapter to the same owned connection factory and migrates only test injection/source-location checks. New and existing native-thread/real-PostgreSQL/HTTP contracts remain required, as do exact-head review and serial whole-release acceptance. It is a prerequisite for per-application graph composition, not a complete create_app or lifecycle claim.

This repository candidate retains native-history/readiness and detection composition from actual main dcb4805, and follows the reviewed tails candidate. Actual-main rebind and predecessor release acceptance must precede publication. Repository production and the ordered entry match reviewed dd74e3e. The bundled manifest is v180 with 514 unique sources. Fixed history28 and reader19 protocols remain mandatory; earlier performance failures remain retained. This is scoped connection ownership, not a complete production application factory.

Authentication domain ownership ships as a structural composition change. It intentionally removes private entry-name rebinding as an internal wiring mechanism while retaining runtime API/settings defaults and route order. Require original/composed HTTP contracts, real PostgreSQL account/session checks, exact-head review and serial whole-release acceptance; this does not complete the full application factory.

This authentication candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows repository candidate 3ac769a. Actual-main rebind and predecessor release acceptance must precede publication. Authentication production/tests and ordered entry match reviewed a1933f3. The bundled manifest is v181 with 515 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Explicit startup captures intentionally narrow private root rebinding; this is not a complete application factory.

Require unchanged record ownership/audit/access regressions plus the composed ASGI identity tests, exact-head review, full CI and serial complete-release acceptance for record composition. No source file is copied independently to production.

This record composition candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows authentication candidate 552944a. Actual-main rebind and predecessor release acceptance must precede publication. Record production/tests and ordered entry match reviewed f5d759e. The bundled manifest is v182 with 516 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Explicit selected methods narrow private root rebinding; no new permission or persistence atomicity is claimed.

Bootstrap path composition requires differential checks against the frozen predecessor, original path/directory and full HTTP contracts, exact review/CI and sequential full-release acceptance. The explicit layout is a prerequisite for full application composition, not an independent runtime topology.

This bootstrap candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows record candidate bdbe2fa. Actual-main rebind and predecessor release acceptance must precede publication. Bootstrap production/tests and ordered entry match reviewed 4a4733a. The bundled manifest is v183 with 517 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Existing path resolution order and errors remain; no directory creation or complete application factory is introduced.

The cost composition slice packages selected-owner wiring and manifest v184/518 with the existing complete Web/label-worker release. No pricing, SQL, API, schema or topology change is introduced. Keep the original admin route order and require existing cost/HTTP and pipeline-store contracts. Rollback restores the complete preceding package while preserving task and call evidence.

This cost composition candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows bootstrap candidate f265821. Actual-main rebind and predecessor release acceptance must precede publication. Cost production/tests and ordered entry match reviewed 73a6a78. The bundled manifest is v184 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Selected source owners and paths are explicit; no atomic ledger snapshot, accounting algorithm change or complete application factory is introduced.

Image worker lifecycle verification now includes the owned admission/drain smoke in CI. The bundled source manifest advances to v185 with the same 518 paths. Queue workers enter their own repository scopes; owner drain reports timeout without cancellation or retry. This slice does not yet wire Web application shutdown or MCP drain, so managed release topology and stop deadlines remain unchanged. Whole-release rollback remains required.

This image-drain candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows cost candidate 9ffd4a0. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 1a286c0, including retained uncertain-start handles. The bundled manifest is v185 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. This scoped owner drain does not establish whole-application shutdown or final persistence success.

Image coordinator and child starts now retain uncertain-start handles even if `is_alive()` is false, child lists are pruned, or a later coordinator replaces the current handle. A failed start revokes an unentered target, and shutdown must join retained handles before reporting drained. A never-started handle may remain undrained; stored running evidence is preserved and never requeued. Deterministic interrupted-bootstrap tests cover both launch paths and later coordinator replacement.

MCP operations now have a client-owned admission boundary covering the complete tool dispatch, including the existing stdio failure fallback, and warmup cleanup. New operations are rejected before transport or fallback after shutdown begins; same-thread nested work belonging to an already admitted operation can finish. Startup and request serialization share the client lock, independently of the admission condition. The bounded shutdown waits for admitted work, then terminates and reaps owned transports; an expired deadline returns undrained without cancelling a blocked call or inducing fallback. Recoverable close retains terminated processes for later reaping. Existing provider selection, prompts, wire messages and transport-failure fallback behavior are unchanged. The client retains the startup warmup thread and admits it before construction/start. Shutdown drains this reserved startup operation, joins its owned thread, then retires transports. Application shutdown registration and full production factory integration remain pending.

MCP recovery retains both live and already-exited displaced processes by identity. An exited transport skips termination but still participates in final wait and stdin/stdout cleanup; EOF followed by the existing fallback cannot lose this cleanup ownership.

This MCP-drain candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows image-drain candidate f8e5dbc. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 008c167, including exited-transport ownership. The bundled manifest is v186 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. This client drain does not establish whole-application shutdown or business persistence success.

MCP warmup startup retains its enabled check and original callback, thread name and daemon setting, but now starts through its client owner. Duplicate live starts and starts after closing are rejected. Thread construction/start failures release reservations exactly once; a thread that started before a start error remains tracked. Already reserved warmup may finish nested client operations after closing begins; unrelated threads cannot inherit that admission. No join occurs under admission or client locks.

A failed or interrupted warmup `Thread.start()` cannot use `is_alive() == False` as proof that no OS thread exists. A target not yet entered is revoked, but its handle is retained and shutdown reports undrained until joining proves completion. A start that never actually created a thread can therefore remain conservatively undrained; no target or paid fallback is replayed. A deterministic interrupted-bootstrap regression covers the late-start window.

Uncertain warmup handles are also retained across a later warmup start. Replacing the current handle cannot erase a revoked thread that has not yet confirmed startup/completion; shutdown joins every retained handle.

This MCP-warmup candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows MCP-drain candidate 88cf6c3. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed ed5bda6, including all uncertain warmup handles. The bundled manifest is v187 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Warmup cleanup remains bounded and conservative; full application lifecycle acceptance is separate.

YOLO warmup starts now belong to their `YoloWarmup` instance, including pending thread construction and every admitted thread. Each thread enters and releases its repository scope on that same thread. Closing rejects later starts and waits outside lifecycle/status locks; a timeout reports undrained without cancelling inference, changing model selection, or requeuing work. Existing repeated-start behavior and per-model handling remain. Application-wide lifecycle registration and per-app graph construction remain separate pending work. Prompt source manifest v188 retains the same 518 ordered files.

Interrupted or failed warmup starts retain uncertain handles even across later starts. An unentered target is revoked and every retained handle must be joined; a never-started handle remains conservatively undrained. The tests cover delayed native bootstrap, interrupted startup, later thread replacement and same-thread scope exit.

This YOLO-warmup candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows MCP-warmup candidate 16e6733. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 4b1cfa5. The bundled manifest is v188 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Joining owned warmup threads does not prove inference success or complete application shutdown.

Training thread ownership is an in-process lifecycle prerequisite and does not change the declared Web/label-worker release topology. It cannot be used as evidence that training subprocesses or remote jobs are drained. Publish and roll back the complete immutable release; preserve task/model/call evidence and keep existing labels shutdown policy.

This training-drain candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows YOLO-warmup candidate 3325d48. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 89ea498. The bundled manifest is v189 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Native-thread drain does not certify task persistence, remote settlement or whole-application shutdown.

The Codex background thread owner is a local lifecycle prerequisite. It does not change Web/label-worker topology or add a process/service. This slice does not install a shutdown hook; whole-release rollback preserves runtime records and call evidence.

This Codex-background drain candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows training-drain candidate ad431e7. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 9634271. The bundled manifest is v190 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Only owner-started native threads are drained; synchronous callers and remote business settlement remain separate.

Transfer reporter admission/drain is an offline lifecycle prerequisite, without an enabled application shutdown hook. Publish only after the new real-thread regression, retained worker-transfer/bundle/retired-flow contracts and full CI pass. Rollback remains a complete immutable release; no data migration is involved.

This transfer-reporter drain candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows Codex-background candidate bb5e844. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 5d64dfe. The bundled manifest is v191 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Reporter drain does not cancel transfers or certify task persistence or whole-application shutdown.

The three auto-optimization thread owners are a lifecycle prerequisite with unchanged Web/label-worker topology. Require new ownership tests and existing auto-optimization regressions before publication. Rollback restores the complete immutable release and preserves task/model/call records; there is no data migration.

This auto-optimization starter-drain candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows transfer-reporter candidate 7f3f2a7. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 4e88155. The bundled manifest is v192 with 518 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Native-thread drain does not certify remote settlement or whole-application shutdown; the executor scope fix remains a separate successor.

Foundation construction is a structural composition change with no new service, migration or deployment option. Run actual-entry HTTP/auth/repository contracts and two-foundation isolation tests before publication. Continue whole-release rollback; retain existing task, call and model-secret evidence.

This application-foundation candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows auto-optimization starter candidate d81faba. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 66697fc. The bundled manifest is v193 with 519 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Three inert foundational owners are distinct; this does not complete the application factory or lifecycle.

Automatic-mask pool repository scoping is independently testable with model substitutes and adds no service or migration. Require the pool cleanup regression and retained batch/state tests, then publish or roll back the complete release.

This automatic-mask pool-scope candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows application-foundation candidate 8dd3e33. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests match reviewed c84e963 and the ordered entry is unchanged. The bundled manifest is v194 with 519 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Repository cleanup is scoped to executor work; model-binding propagation remains a separate successor.

Model-only mask-pool binding is separate from prior repository cleanup. Require the old-behavior counterexample and actual batch snapshot regression plus existing model-profile tests before release. Rollback restores the entire release; stored task snapshots and immutable secret references are retained.

This automatic-mask model-binding candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows pool-scope candidate 60a094b. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed b86a647. The bundled manifest is v195 with 519 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Only the selected model snapshot is propagated; later binding failure does not undo already submitted work.

Text document/preparation thread ownership and slot handoff require the new native-thread regression and retained document/preparation/model contracts before publication. No service, migration or new shutdown hook is introduced. Use whole-release deployment/rollback and preserve persisted job and call evidence; never use permit release as authorization to retry an uncertain call.

This text-job ownership candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows model-binding candidate 8302940. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 4491be2. The bundled manifest is v196 with 520 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Job permits retain capacity through thread and repository cleanup; direct synchronous calls remain caller-owned.

HTTP construction extraction is packaged with its actual source under prompt manifest v197 (521 files). Existing model snapshots stay immutable. Full HTTP/authentication/source and existing release checks remain required; this change does not activate a new runtime topology.

This HTTP-shell candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows text-job candidate a071786. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests and ordered entry match reviewed 5d1d582. The bundled manifest is v197 with 521 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. A fresh transport shell is not yet a complete isolated production application.

The HTTP upload-provider capability updates the fingerprinted constructor under manifest v198 while retaining the same 521 source paths. Require original HTTP-shell parity, injected-provider ASGI isolation, existing artifact integration contracts and normal immutable release acceptance. Roll back the complete release; no storage or database migration is included.

This HTTP upload-provider candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows HTTP-shell candidate fa14007. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests match reviewed 6f11bcd and the ordered entry is unchanged. The bundled manifest is v198 with 521 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Explicit provider injection is enabled for later composition; the current entry still uses the default provider.

Artifact runtime ownership updates the existing fingerprinted runtime module under manifest v199 with the same 521 source paths. The original selector is frozen as test evidence from the unchanged actual-main source. Require selector baseline/concurrency and existing artifact/HTTP contracts before immutable release acceptance. Internal module cache variables are replaced by the default owner and are not a supported external configuration API.

This artifact-runtime ownership candidate retains native-history/readiness and detection composition from actual main dcb4805 and follows HTTP upload-provider candidate 4ab91fe. Actual-main rebind and predecessor release acceptance must precede publication. Owned production/tests match reviewed 4c2b19e and the ordered entry is unchanged. The bundled manifest is v199 with 521 unique sources. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Owners isolate selector locks and caches, not underlying paths or resources; the default entry owner remains process-scoped.

Frozen HTTP constructor evidence is pinned to canonical Git LF bytes with an explicit checkout attribute. The raw SHA guard still rejects any changed fixture; this fixes platform-dependent test acceptance without changing application behavior or historical task snapshots.

Frozen artifact-runtime evidence is checked out as canonical Git LF bytes. The original raw SHA and immutable fixture Git blob remain unchanged; a CRLF working-copy mismatch is a test portability failure, not a runtime regression.

Pipeline scheduler ownership ships through the same immutable release and source manifest v206 (519 paths). No worker topology or automatic drain hook is activated in this slice. Parent-before-dependency shutdown wiring needs separate full-application acceptance.

Extraction thread ownership preserves current Web/label-worker topology and has no database migration. Require native extraction ownership tests, retained extraction behavior and full CI; deploy/rollback complete immutable releases while retaining extraction attempt evidence. Application shutdown integration is a separate remaining step.

Comparison cleanup is a bounded failure-handling fix with no migration or topology change. Require the fault/real-semaphore regression, retained comparison/model/HTTP contracts and full CI; roll back the complete release while retaining all call and task evidence.

Prepared comparison thread/timer ownership is staged independently under manifest v207. Require native lifecycle and cleanup fault tests, retained actual HTTP and model contracts, dependency and documentation checks before exact-head CI/review. This change adds no service and activates no shutdown hook; whole-release rollback and the existing Web/label topology remain mandatory.

PDF consumer ownership is a separate manifest v208 slice. Require its native startup/drain failure tests, unchanged label regression and real PostgreSQL HTTP checks before hosted CI and independent exact-head acceptance. It adds no service or automatic cancellation, and whole-release rollback remains the recovery path.

This offline lifecycle integration retains native-history/readiness and detection composition from actual main dcb4805 and follows artifact-owner candidate 6b648b5. Owned production/tests and ordered entry match reviewed 28de9fa; both canonical fixture corrections are already retained. The bundled manifest is v204 with 523 unique sources; earlier paragraph counts refer to their original individual candidates. Fixed history28 and reader19 protocols remain mandatory; previous performance failures remain retained. Publication must use independently reviewed domain-scoped PRs on accepted main, with full hosted and release gates; this offline combined tree is not a blanket grouped publication approval or complete application factory.

The two frozen HTTP-constructor and artifact-runtime Python fixtures use Git-enforced LF checkout bytes. Their tests hash the actual canonical Git content before executing it, so Windows checkout conversion cannot invalidate the frozen contract. The HTTP fixture expected hash is corrected from its original CRLF working-copy digest to the committed LF blob digest; fixture source content and the artifact fixture digest are unchanged. The integration verification retained both the initial private runner filename error and the subsequent observed CRLF artifact-baseline failure.

The Web teardown candidate changes the HTTP lifecycle contract to one shutdown_application callback while preserving its original PDF-stop and label/control-stop prefix. Native drain owners share the remaining 480-second cooperative allowance. No installer/service timeout, release topology, worker build, task deadline, automatic retry or rollback behavior changes. At the shutdown replay boundary, source manifest205 includes524 actual sources. Release acceptance must include the exact new lifecycle checks; idle synthetic teardown is not a live nonempty drain or rollback exercise.

This offline shutdown replay follows lifecycle candidate 7d7886a and preserves current native history, readiness, model/tail and canonical LF fixes. Four owned runtime/test/contract blobs match reviewed 82313c5. Manifest v205 lists 524 sources. The 480-second shutdown allowance remains cooperative and requires ASGI request quiescence; complete independent application composition is still pending. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

The detection artifact-port smoke is an additional backend CI gate using isolated synthetic stores. Existing package, frontend, PLC and deployment gates remain mandatory; runtime topology and installation steps are unchanged.

This offline detection artifact replay follows shutdown candidate 8618f7a and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 713010a. Manifest v206 lists 524 sources. Storage suppliers retain call-time selection; this does not yet switch the complete application graph. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

The detection media-port smoke is an additional required backend command. It verifies synthetic storage graphs without a real model, paid provider, PLC or remote object service; ordinary complete-release CI and managed rollout/rollback remain required.

This offline detection media replay follows artifact candidate e7e12b2 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 5e86530. Manifest v207 lists 524 sources. Explicit stores retain original cache, error and video cleanup behavior; this does not yet switch the complete application graph. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

The additional HTTP artifact-port smoke exercises synthetic ASGI applications with real artifact stores and in-memory object clients. Complete CI and managed release gates remain required; it is not a live storage or production account validation.

This offline HTTP artifact replay follows detection media candidate f2b4519 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 301b6c1. Manifest v208 lists 524 sources. Explicit missing file dependencies fail closed while genuinely omitted legacy arguments retain their documented default. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

Incoming artifact isolation adds one synthetic backend smoke command. Existing CI, managed release and actual-main gates stay required; the local workflow checks do not attest live OCR, customer accounts, remote object storage or production retention behavior.

This offline incoming workflow replay follows HTTP artifact candidate 2336193 and preserves current native history, readiness, model/tail and canonical LF fixes. Production and test blobs match reviewed 8e4d991. Manifest v209 lists 524 sources. Consistent captured files/images dependencies retain original partial-write, exception and retention semantics. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

The additional background-file-port backend smoke uses isolated synthetic storage and task callbacks. Complete hosted CI and managed rollout still gate publication; it does not verify a live generator, customer storage or nonempty shutdown.

This offline background file replay follows incoming candidate 841c4ba and preserves current native history, readiness, model/tail, shutdown documentation and canonical LF fixes. Production and test blobs match reviewed c80ed68. Manifest v210 lists 525 sources, with the corrected service-relative background capability path. Captured file capabilities retain original ordering and partial effects. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

The additional background-image capability smoke uses synthetic object clients and analysis callbacks. It retains the original image/RNG goldens, hosted regression gates and managed release acceptance; no live model/PLC is required for these tests.

This offline background image replay follows file candidate 89875c1 and preserves current native history, readiness, model/tail, shutdown documentation and canonical LF fixes. Production and test blobs match reviewed 09ef623. Manifest v211 lists 525 sources. Three image services use explicit adapters; generator and runner defaults remain outside this slice. Original algorithms and golden contracts remain unchanged. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

The background generation port smoke is an additional synthetic CI command. Hosted CI, immutable package review and managed release acceptance remain separate gates; local doubles do not attest live generation, nonempty worker shutdown or production object storage.

This offline background generation replay follows image candidate 9a2d333 and preserves current native history, readiness, model/tail, shutdown documentation and canonical LF fixes. Production and test blobs match reviewed 22986e9. Manifest v212 lists 525 sources. Generator and task runner now receive captured file adapters, retaining model snapshots, subprocess policy, partial outputs and exception behavior. Actual-main rebind, independent review and full CI/release acceptance remain required before publication; complete app composition is still pending.

Training file-capability injection deploys as one complete release. Verify dataset/input/preview contracts, explicit two-store ownership and the actual source manifest before merging; rollback restores the preceding whole release and keeps stored task and artifact evidence. No worker topology, migration or retry change is included.

This offline training file replay follows generation candidate 2fdb9ee and preserves current native history, readiness, model/tail, corrected boundary documentation and canonical LF fixes. Production and test blobs match reviewed 214fe9c. Manifest v213 lists 526 sources, appending training/file_ports.py. Five services capture matching file capabilities while preserving validation, cache, write ordering and partial effects. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Training image and YAML capability injection requires the existing pixel/metadata golden tests plus explicit artifact ownership checks. Publish and roll back the complete release; image codecs, dataset formats and runtime topology remain unchanged.

This offline training image replay follows file candidate 94c1eec and preserves current native history, readiness, model/tail, corrected boundary documentation and canonical LF fixes. Production and test blobs match reviewed 75d63a9. Manifest v214 lists 526 sources. Image adapters are captured and YAML selects its writer per call; arbitrary private rebinding is not preserved as an atomic hot swap. Algorithms, goldens and public signatures remain unchanged. Actual-main rebind, independent review and full CI/release acceptance remain required before publication.

Training resource and archive capability injection retains the established complete-release deployment and rollback. Acceptance includes isolated mutation conflicts, partial-failure evidence, archive contents and digest leases; no production cleanup, data migration or remote training is performed by validation.

This offline training resource replay follows image candidate 9063ace and preserves current history, readiness, model/tail, shutdown, corrected boundary documentation and canonical LF guards. Production and test blobs match reviewed fbf5434. At this replay boundary manifest v215 selects 526 sources. Explicit resource and archive capabilities preserve file operation ordering, strict digest failures, partial publication and archive formats. Current source changes require actual-main rebind, independent review and full CI/release acceptance before publication.

Accessory creation/provenance file capabilities ship in one complete release after their original business contracts, explicit ownership checks and actual-source manifest validation pass. Roll back the whole prior release and retain artifact/task evidence; runtime topology is unchanged.

This offline accessory file replay follows training resource candidate 7ae44bf and retains current history, readiness, model/tail, shutdown and canonical LF guards. All production and test blobs match reviewed eccc553, including ordered constructor bindings. At this replay boundary manifest v216 selects 526 sources. Upload ordering, partial publication, provenance collisions and sprite fallbacks remain unchanged. Actual-main rebind and complete independent CI/release acceptance remain required before publication.

Accessory evidence and preview port changes require their existing source-order/pixel/matching contracts and explicit storage ownership tests. Publish a complete release after exact-parent documentation and source-fingerprint checks; restore the complete prior release on failure.

This offline accessory evidence replay follows file candidate b368404 and retains current history, readiness, model/tail, shutdown and canonical LF guards. All production and test blobs match reviewed 466195b. At this replay boundary manifest v217 selects 526 sources. Decode and hashing selection, source mutation, partial publication and error propagation remain unchanged. Actual-main rebind and complete independent CI/release acceptance remain required before publication.

Catalog and sprite storage-port changes require retained metadata and pixel regression tests, explicit dependency checks and actual-source fingerprints. Merge only after the exact commit passes CI and independent review; rollback the complete release.

This offline accessory catalog replay follows evidence candidate 2d442b2. All owned production/test blobs and the complete ordered entry match reviewed 87ebec1; current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v218 selects 526 sources. Existing catalog mutation and decoder behavior are unchanged. Exact-source neighbor evidence is reused; current targeted, assembled HTTP and fingerprint checks are distinct. Actual-main rebind and independent full CI/release acceptance remain required.

Candidate/gallery explicit storage requires original permission, image-byte and operation-order checks plus synthetic store isolation. Publish only the exact CI-reviewed commit as a complete package; restore the complete prior release on failure.

This offline accessory gallery replay follows catalog candidate 8f453b3. Owned source/test blobs and ordered entry match reviewed 7f02e9d, including the single inert ImageFiles allocation relocation. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v219 selects 526 sources. Existing partial publication and failed-write behavior are unchanged. Neighbor evidence is reused only for exact source; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Accessory edit port changes require existing upload, crop, reference and deletion contracts plus real-adapter isolation tests. Publish only a CI-reviewed complete release; rollback the complete package without reversing artifact metadata or deleting evidence.

This offline accessory edit replay follows gallery candidate 1b5c003. Owned source/test blobs and ordered entry match reviewed 6f78019. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v220 selects 526 sources. Authorization order, crop geometry, partial publication and deletion failure behavior remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Preprocessing reader changes require retained source/pose/fallback and pixel/metadata regressions plus explicit-storage checks. Release only an exact CI-reviewed complete package and roll back to a complete prior version.

This offline accessory preprocessing replay follows edit candidate 96c7b23. Owned source/test blobs and ordered entry match reviewed dbcd8b5. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v221 selects 526 sources. Discovery, decode, publication, status and exception ordering remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Agent reference port changes require source order, generated reference content, retained prompt contracts and new explicit-storage tests. Publish only the exact CI-reviewed complete release; preserve snapshots and evidence on rollback.

This offline Agent reference replay follows accessory preprocessing candidate b1d835d. Owned source/test blobs and ordered entry match reviewed efa17b7. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v222 selects 527 sources. Reference selection, digest acceptance, path mutation and exception ordering are unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Pose storage ports require existing image/metadata/source-order tests and explicit storage ownership checks. Release only an exact CI-reviewed complete package; do not roll back individual files or artifact tables.

This offline Agent pose storage replay follows reference candidate 9a90408. Owned source/test blobs and ordered entry match reviewed 11919d9. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v223 selects 527 sources. Image and metadata publication ordering, local/remote callback timing and partial mutations remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Photo-highlight media ports require original attempt/pixel/metadata regression checks plus explicit-storage failure probes. Only an exact CI-reviewed complete package may be deployed; retain call and artifact evidence on rollback.

This offline Agent photo replay follows pose storage candidate a56b846. Owned source/test blobs and ordered entry match reviewed 6afd82e. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v224 selects 527 sources. Provider attempts, diagnostic failure handling, publication and item mutation order are unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Explicit pipeline background storage must pass original prompt/provider/order contracts and independent artifact isolation/fault probes before serial CI-reviewed publication. Roll back a complete accepted release and retain existing task/call/artifact evidence.

This offline Agent background replay follows photo candidate 5bcd15e. Owned source/test blobs and ordered entry match reviewed e8c63a3. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v225 selects 527 sources. Existing library fallback, partial file and manifest publication, callback timing and errors remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Pipeline availability ownership changes require original status/order regressions and explicit-storage tests before exact-head CI and serial publication. Preserve existing deployment topology and roll back the whole accepted release.

This offline pipeline availability replay follows Agent background candidate 37a1265. Owned source/test blobs and ordered entry match reviewed ed60859. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v226 selects 527 sources. First-match, pending-state, bypass and storage error behavior are unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Text cleanup dependency changes require the original conflict/expiration/worker contracts and isolated artifact failure probes before exact-head CI and serial release. Rollback restores the whole accepted package while retaining immutable revisions and artifact evidence.

This offline text cleanup replay follows pipeline availability candidate 6f13fd9. Owned source/test blobs and ordered entry match reviewed c89fbbd. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v227 selects 528 sources. Cleanup exception precedence, tombstone-before-deletion and partial effects remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Training catalog file injection requires original ordering/permission regressions and explicit-storage failure tests before exact-head CI and serial release. Keep the accepted runtime topology and use complete-release rollback.

This offline training catalog replay follows text cleanup candidate 1199028. Owned source/test blobs and ordered entry match reviewed 8f0715d. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v228 selects 528 sources. Local and indexed selection, permission ordering and repeated reads remain unchanged. Exact-source neighbor evidence is reused; current targeted, real PostgreSQL, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Text media runtime injection is a structural change requiring prior media regressions and explicit runtime isolation checks. Exact-head CI and normal complete-release deployment/rollback remain required; the label-worker topology is unchanged.

This offline text media replay follows training catalog candidate 920904d. Owned source/test blobs and ordered entry match reviewed f71e6c4. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v229 selects 528 sources. Local path, hybrid readiness, size, digest and publication rules remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Training runner file injection requires its retained execution/no-retry regressions and explicit storage tests, followed by exact-head CI and serial whole-release deployment. No RunPod request, model, prompt or worker topology change is included.

This offline training runner replay follows text media candidate da44932. Owned source/test blobs and ordered entry match reviewed 9b024f4. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v230 selects 528 sources. Running-state persistence, runtime mode, repeated existence reads, failure settlement and pinned model restoration remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

RunPod artifact runtime injection requires its original local archive/import contracts and synthetic indexed-store isolation checks. Normal exact-head CI and whole-release rollback apply with the existing runtime topology.

This offline RunPod artifact replay follows training runner candidate b7b8760. Owned source/test blobs and ordered entry match reviewed 671f233. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v231 selects 528 sources. Repeated runtime selection, cleanup exception masking, publication ordering and local replacement remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

RunPod transport runtime injection requires retained submission/transfer regressions and synthetic ownership tests before exact-head CI and normal complete-release deployment. The worker package and existing service topology remain unchanged.

This offline RunPod transport replay follows artifact candidate 97a9963. Owned source/test blobs and ordered entry match reviewed 12f1743. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v232 selects 528 sources. Durable claim ordering, ambiguous submit retention, streaming limits and partial upload publication remain unchanged. Exact-source neighbor evidence is reused; current targeted, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Codex HTTP storage injection requires retained API/batch PostgreSQL regressions and explicit runtime-isolation tests before exact-head CI and serial whole-release publication. Rollback restores the complete accepted release.

This offline Codex HTTP replay follows transport candidate 0beaefc. Owned source/test blobs and ordered entry match reviewed 42fcded. Current history, readiness, model/tail, shutdown and canonical LF guards remain. At this replay boundary manifest v233 selects 528 sources. Authorization, media exception mapping and partial publication ordering remain unchanged. Exact-source neighbor evidence is reused; current targeted, isolated PostgreSQL, HTTP and fingerprint checks are separate. Actual-main rebind and independent full CI/release acceptance remain required.

Label media ownership is a structural change to both Web and worker package code. Validate both existing topologies and whole-release rollback through the retained isolated fault suites before normal serial CI and release; do not copy individual worker files.

This offline label media replay follows Codex HTTP candidate 41743d5. The original provider-only delta from reviewed b696cba is applied while retaining current native history summaries and their test adapters. All other owned source/test blobs and ordered entry match the reviewed source. At this replay boundary manifest v234 selects 528 sources. Current history, readiness, model/tail, shutdown and canonical LF guards remain. Worker claims, PDF cleanup, provider identity and error ordering remain unchanged. Current isolated PostgreSQL and affected integration checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

Strict comparison media ownership requires retained Web/worker/media regressions and isolated PostgreSQL tests before serial CI and complete-release publication. No installed unit, storage-mode or rollout topology change is introduced.

This offline comparison media replay follows current-history label candidate f447c5d. Owned source/test blobs match reviewed 552cea1; the entry remains unchanged. Current native history and its explicit-provider fixture, readiness, model/tail, shutdown, scoped RunPod claim documentation and canonical LF guards remain. At this replay boundary manifest v235 selects 528 sources. Worker budget and reservation settlement ordering, ambiguous paid outcomes and CLI selection remain unchanged. Current isolated PostgreSQL and affected integration checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

Web artifact composition must pass original selector and file/image contracts plus per-owner isolation checks before exact-head CI and serial whole-release publication. This introduces no storage mode switch, media migration or installed topology change.

This offline Web artifact composition replay follows comparison candidate d2ae509. Owned source/test blobs and ordered entry match reviewed a0fa2ed, including the Python 3.10 structural source guard. Current native history and provider fixture, readiness, model/tail, shutdown, scoped RunPod claim documentation and canonical LF guards remain. At this replay boundary manifest v236 selects 529 sources. The Web graph owns a fresh lazy runtime provider and two focused views; this is not a complete application factory or proof of independent underlying resources. Current targeted, HTTP and fingerprint checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

Stream configuration extraction requires frozen-behavior, actual HTTP and existing PLC route-order contracts before serial publication. Restore a previous complete release on failure; no data migration or individual file replacement is introduced.

This offline stream configuration replay follows Web artifact candidate f2e481b. Owned source/test blobs and ordered entry match reviewed 14f6504. Current native history and provider fixture, readiness, model/tail, shutdown, scoped RunPod claim documentation and canonical LF guards remain. At this replay boundary manifest v237 selects 530 sources. Existing load, mutation, save and post-save response ordering remain unchanged; configuration is not given a new transaction or lock. Current targeted, HTTP and fingerprint checks are separate from reused exact-source evidence. Actual-main rebind and independent full CI/release acceptance remain required.

Text storage composition adds an inert per-composition shared lock and two record stores. CI runs the new storage composition HTTP/thread isolation suite plus the existing root and PostgreSQL store contracts. Release as one complete package with source manifest v238/531; use the previous accepted complete release and declared topology for rollback. No data migration or worker topology change is introduced. Full application factory isolation is not yet complete.

The incoming-text domain builder is released with the complete Web/label-worker package. Its CI command smoke_incoming_composition.py supplements existing incoming store, workflow and artifact contracts. The prompt source manifest includes the actual two new source files. Require fresh PR CI, independent review and actual-main release verification; rollback restores the previous complete package without copying individual modules.

The incoming domain owns its response-file capability and exposes separate catalog and inspection route registration methods. Application composition calls them at their original positions, preserving the intervening Beta comparison routes and the existing media authorization/error behavior. The actual domain-builder HTTP tests exercise these methods; this does not claim a completed whole-application factory.


Catalog composition uses actual source manifest v240 (534 paths). Require catalog/model/pipeline/media regressions, exact-head CI and independent review before whole-release publication. The domain composition changes no provider, model defaults or runtime service topology and does not complete the application factory.

The candidate image graph change adds its integrated ownership smoke to required backend CI. Each actual-main domain PR still needs its own complete CI and whole immutable release verification; offline domain tests do not approve an unpublished stack. Prompt source manifest version 241 includes accessories/image_composition.py as an actual new source; new task fingerprints change naturally and historical task snapshots are not rewritten.

The model-tool composition slice is a structural domain change with retained HTTP contracts and synthetic inference checks. Publish only through required CI and the complete versioned frontend/backend release; rollback restores the previous complete release and topology. The independent domain graph evidence is not actual-main or managed-deployment acceptance.

The detection/publication/capture graph is a structural domain change. Its integrated smoke supplements all existing HTTP, PLC, model-binding and publication/capture regression checks in required CI. Offline graph review does not approve a historical unpublished stack: publication requires an actual-main domain rebind, independent net-diff review, complete CI and managed immutable package validation. Roll back the whole previously accepted package and declared topology; do not copy individual modules.

> **Current backend composition:** The Web application is assembled by `runtime/application.py`; `server:app` retains the stable ASGI entry and compatibility exports. Earlier migration checkpoint statements about unfinished domain/application assembly describe their historical checkpoint and are superseded by [canonical application construction](architecture.md#canonical-web-application-construction). They do not establish current CI, performance or production acceptance; those remain separate release gates.

# Real-photo feedback

**Status: Authoritative**

## Foundation batch

The foundation introduces account-opt-in `real_photo_vlm` storage, API, source capture and strict localization contracts. Empty `VANTALINE_REAL_PHOTO_ACCOUNTS` preserves current behavior. Enabling requires an explicit fixed Doubao bbox binding and first disables legacy feedback admission; active legacy labeling must settle first. Initial AI-generated pretraining remains unchanged. Historical artifacts remain available through the old API and the owner-only history index; their frames are drafts and require explicit original-hash, first-frame geometry and source-group confirmation before reuse. Failed historical review records are not combined into labels.

Original source bytes are frozen separately from annotated previews. Exact source hashes and explicit lineages deduplicate candidates; approximate similarity never deletes different photos. Camera source groups derive from the existing station/session, videos from source upload identity, and ordinary uploads from the upload request. Historical missing groups block split admission until an owner supplies one. UI/labels retain decoded first-frame geometry and recorded EXIF orientation; VLM inputs may use the explicit recorded source-to-input scale described below. No implicit orientation conversion is applied.

`bbox_annotation` is independently bound to `doubao-seed-2-1-pro-260915`. The blind model context includes every task category/reference in an immutable provider prefix and only the current real original in the suffix, never previous detections, masks, review results or another original/answer. It uses normalized 0–1000 xyxy, visible tight boxes, temperature 0, thinking disabled, high detail and 4096 output tokens. Invalid/unknown/duplicate/out-of-bounds/truncated results fail as complete attempts and retain their bounded response and available usage. Each attempt is recorded before execution. A retry requires an explicit new version; there is no mask fallback.

The owner-only `/api/ai/tasks/{id}/real-photo` API exposes counters, private canonical image previews, source groups, history, restart and versioned relabel requests. Queued annotation/review jobs require the later independent worker. The foundation does not run automatic training. Masks requested through the new endpoint are queued supplemental artifacts and cannot change boxes, review keys or training admission.

## Independent review worker

The second batch ships `training_review.worker`, its own systemd unit, immutable report socket and the versioned training review skill. It reuses the bubblewrap launcher with separate tool/skill mounts; existing label comparison defaults remain unchanged. The serial worker claims initialize/annotation/review/assessment jobs with owner allowlisting, 600-second CLI deadlines, heartbeat fencing and per-version reports. At most ten originals enter one review invocation. Failed CLI exit, cancellation, expired tokens, missing reports or partial rounds block admission. A failed VLM localization can only be excluded/uncertain, never converted to a negative. Parent-only late receipts preserve usage/evidence without reopening a job.

Initialization independently sets review trigger and approved target to 20–50. A full round freezes its membership, preserves already completed decisions, and produces a training proposal or next 1–50 increment. At least twenty approved distinct originals, a positive and three valid source groups are enforced independently of class coverage. Missing classes are recorded without an extra per-class minimum. New arrivals wait for the next round. This batch freezes proposed train jobs but does not execute YOLO.

Real CLI business acceptance is still an operations gate. The dedicated login, pinned native runtime, cache/scratch mounts, read-only original/reference access, report-only tools and model connection must be verified before activation. Fixture reports and clean CLI exit are not visual-quality evidence.

## Accepted-original training loop

The third batch ships a server-side dispatcher and immutable YOLO dataset manifest. It reads only accepted real originals at their frozen annotation/review versions, retains the complete task category order, and writes one canonical first-frame PNG and one label file per distinct source. There is no generated-image, cutout, background-compositing or synthesized-negative call on this strategy. Source groups are assigned before export, remain fixed across later datasets, and cannot cross train/validation/test. The target is 80/10/10; indivisible groups can produce different actual proportions. A training positive and three groups are required. Conventional augmentation remains training-only and does not change real counts.

`VANTALINE_REAL_PHOTO_TRAINING_ENABLED=1` additionally enables the server's serial training dispatcher; absence keeps training proposals queued. The dataset and deterministic training task are reserved before submission. Multiple server processes cannot claim the same proposal. Restart monitoring reads an existing task and retains its metrics without resubmitting; an unknown submission outcome pauses for explicit reconciliation. Local and RunPod executors support the strategy, while legacy remote execution fails explicitly. Base-weight hash, executor, device and training parameters are frozen before publication; drift prevents execution. RunPod requires a configured base SHA256 and a worker image supporting held-out evaluation.

A completed real-photo task evaluates the held-out test set without augmentation. Per-class precision, recall and AP are recorded when evaluable; classes without accepted real support or test instances have unavailable metrics, never invented zero scores. The model remains a candidate in the existing detection picker. Completion does not disable collection or auto-promote it. The task detail card shows real counts, dynamic review targets/reasons, status/usage, candidates, original/bbox previews, source grouping, explicit versioned relabeling and optional mask/version history. Costs remain unavailable without verifiable pricing; elapsed/usage gaps are counted. Agent invocation counts mean CLI sessions, not inferred underlying API requests.

Optional masks run separately on explicit user request and append an attachment with its own profile/hash/geometry. They do not replace boxes or invalidate an accepted review. A same-size generated mask is still geometrically unverified. Historical masks remain readable through the legacy artifact APIs; confirmed historical boxes can enter the new pool as drafts for whole-image screening.

## Activation gates still requiring operations evidence

All code paths remain account-gated. Before enabling business admission or the training dispatcher, verify the dedicated CLI login, Linux native runtime and isolation, immutable released worker, fixed Doubao binding, private-business screening decisions, 4096-token localization, and the selected YOLO executor. Fixtures prove contracts, not visual screening quality or GPU training. This implementation does not claim those live checks have passed. Close admission before whole-release rollback; never revive legacy synthesis or replay an uncertain paid session.

## Verification and rollback

Foundation tests require an explicit disposable PostgreSQL DSN for locking/idempotency/owner isolation. Check migrations, generated schema, original-capture regressions, PLC camera invariants, boundaries and the documentation contract. No private samples, runtime credentials, API keys, receipts or model artifacts belong in Git.

Rollback closes new admission, settles running attempts and restores one previous complete immutable release. Keep additive tables and all evidence. Unknown paid attempts are never automatically replayed. Runtime flags, production `/api/version` and immutable release evidence remain separate from fixture verification.

Candidate reports include distinct real count, positive/negative count and actual train/validation/test sizes. Indivisible source groups can materially change the target ratio; inspect those counts alongside unavailable per-class metrics. Failed or interrupted dataset preparation/submission pauses further automatic training until the owner explicitly reconciles it.

Status/source admission reconciles current task class definitions and reference identities with the frozen class snapshot. A changed definition/reference identity revokes the old epoch and schedules one new initialization; unchanged polling does not reread image bytes. Incomplete definitions disable admission explicitly. Training submission independently compares current reference hashes and task definitions to the frozen snapshot, so a queued dataset cannot train after unnoticed category drift.

Automatic submission resolves the actual persisted owner identity and current permissions; it does not invent a username/role for the background thread. Removed accounts or revoked training permissions cannot be bypassed by an Agent proposal.

The existing task model picker additionally includes only completed candidate IDs returned by the exact owner/task feedback endpoint. This explicit association avoids a class-name heuristic and does not create a legacy pipeline auto-promotion link. Frozen task quantity rules accompany the dataset/training record rather than reverting to one item per class. Rule/reference drift before submission blocks training. Real-photo candidate uploads preserve original bytes and non-PLC capture-session grouping even in the standalone picker.

Review membership is frozen at the cumulative candidate trigger before annotation completion. The frozen sample IDs remain fixed while later originals wait for the next cohort. Ready review/assessment jobs precede later queued annotations. Explicit relabel versions enter a separate recheck list and do not increase real-photo counts or require unrelated new photos. Failed preparation retains its scope in round history and pauses for explicit recovery; failed assessment also blocks further automatic paid admission. Completed historical rounds without the new membership fields remain readable.

Assessment inputs freeze the initialization decision, current approved-real target and candidate trigger alongside reviewed decisions. The Agent can lower its approved target within 20–50 with a reason, but must distinguish that new target from the recorded initial value; prior reports remain immutable.

The dedicated review crop tool supports the system Pillow legacy `Image.LANCZOS` API and newer `Image.Resampling.LANCZOS` with identical pixel bounds and transform sidecars. Commission the actual sandbox interpreter under the final unit protections; a parent virtualenv crop or successful model exit does not verify the child tool. Keep original review receipts unchanged when fixing runtime compatibility.


The combined backend batch includes main 5bd0baf real-photo feedback stage3.
Image uploads retain capture-session grouping and exact original-byte hashes,
while selecting the application-owned file capability. Training retains frozen
executor, dataset and evaluation configuration checks; the runner selects its
owned artifact runtime. The new dispatcher stop hook precedes existing shutdown
hooks inside the ordered shutdown owner. These main changes are preserved, not
introduced as new behavior by the composition refactor. Current manifest v256
contains 566 actual files, including the new RunPod frozen-model settings module; historical source fingerprints are unchanged. The
source oracle records the exact two-region main root delta and the exact updated
runner/submission file digests. Whole current-head CI and deployment remain gates.


Real-photo mask/training dispatcher producers are tracked by the application-owned
DispatcherRuntime with a repository thread scope. Stop closes new loop iterations;
the first native shutdown step joins the actual producer threads and scope exits
before closing their training and model-MCP dependencies. A drain timeout keeps
those dependencies available and reports failure; it does not cancel an in-flight
call or repeat an uncertain start. Startup is once-only, including partial-start
failure; a stopped instance cannot restart. Existing two-second polling, enable
rules and task algorithms are retained. Synthetic lifecycle checks cover blocked
tick, blocked scope exit, startup/close races, partial/uncertain starts and two
independent owners. Current manifest v258 contains 568 actual sources. Complete
application assembly and current-head hosted/release gates remain pending.

The default entry now registers `RealPhotoWorkflows.feedback` from `training/real_photo_composition.py` at the original route position. Its bridge owns original-media freezing, legacy disable, owner-scoped training metadata and submission. Identity restoration, frozen class/reference/rule validation, sample counts and class order are unchanged. Dispatcher algorithms, repository transactions, allowlist policy and training/model topology are unchanged.

Real-photo feedback is composed by the canonical app with explicit app-owned environment and connector selection. The previous undefined `RUNTIME_REPOSITORY_CONNECTOR_FOR_TESTS` reference is removed from the actual runtime path. Repository selections still close in the feedback service's finally boundary; account allowlist remains the existing process policy. Native training submission, model/config snapshots, provenance, locking and dispatch behavior are unchanged. Canonical lifecycle preserves startup failures and retains bounded producer-before-dependency drain.

VLM 图片输入先限制长边：类别参考图 1024 像素、实拍原图 2048 像素，只等比缩放，不裁剪或隐式旋转。回执同时记录原图尺寸、输入尺寸、原图哈希、输入哈希及原图到输入的缩放矩阵；归一化框仍换算到原图像素坐标。准备阶段失败结算为失败标注版本，显示固定阶段代码，不记成已发生的付费调用；必须由用户主动重标，不自动重放。

训练审核 worker 区分 CLI 非零退出、未完成/失败的 turn、缺失报告和被拒绝的报告。每次尝试保留固定原因代码、退出状态、报告接纳状态、提示词 SHA-256 与已有 token 回执；报告拒绝只记录白名单分类及有界计数，不记录请求、异常原文或 CLI 输出。模型正常退出不能替代报告接纳，失败后仍要求前端主动恢复，不自动重放。所有 reason/gap 限制为非空且不超过 1000 字符，初始化理由需简洁，并明确 submit 返回 accepted 后才算提交。

豆包专用输入副本固定为 JPEG quality=90、4:4:4，不裁剪、不隐式旋转，不在超限时继续降质。参考图长边 1024、编码上限 2 MiB；实拍长边 2048、编码上限 6 MiB。参考前缀 JSON 上限 32 MiB，单图 JSON 上限 10 MiB。原图、Agent 复核和训练 PNG 不变。回执 bounded-first-frame-jpeg90-444-v3 保存源/输入字节数、质量、缩放矩阵、编码哈希和编码前后像素哈希；历史 v2/PNG 回执保留。JPEG 为有损副本，尺寸限制可能影响极小目标，真实业务质量仍需前端验证。

## Reference prefix caching and connection evidence

The dedicated bbox worker uses Ark `/api/v3/responses`, not the shared label/pretraining Chat transport. A durable `reference_cache` job uploads the task definitions, prompt and all compressed references with `caching={type:enabled,prefix:true}`, `store=true`, thinking disabled and a one-hour `expire_at`. The fixed model must have provider-side cache inference enabled; unsupported/permission failures block explicitly without another model or endpoint fallback. Prefix creation is a separate potentially charged request (at least 256 input tokens), generates no answer, and is owner/task/class/reference/profile/prompt/compression-version scoped. The opaque provider ID remains private. Model prompt source remains `training/real_photo_annotation.py:PROMPT`; Responses composition and suffix live in `training/real_photo_cache.py`.

Each annotation uses only that immutable prefix ID plus one compressed new original, with 4096 output tokens, temperature 0 and thinking disabled. It never reuses an annotation response ID. References are hash-checked again on a hit, without re-encoding/uploading them. Original hash/lineage dedup remains separate; explicit relabeling creates a new paid annotation version. The suffix retains `store=true`, `caching=enabled` and the same absolute expiry, following the provider's supported cache protocol; any suffix storage charges belong in billing evidence, not assumed zero. Provider prefix reuse and actual `usage.input_tokens_details.cached_tokens` are distinct facts, including zero/unknown hits.

Cached jobs are claimed only after a valid prefix has more than 180 seconds remaining. Known expiry refreshes only when pending work exists; idle tasks do not renew. Creation uses the existing PostgreSQL fence, epoch and attempt token. Failed/interrupted creation pauses and cannot requeue itself; frontend explicit restart authorizes a new generation after current attempts settle. Disabled/changed tasks revoke queued/running work; historical cache receipts remain. A transport or non-200 annotation pauses further automatic paid admission; failed images require explicit relabeling, not replay.

The serial worker reuses a bounded HTTP Session, disables ambient proxy inheritance, resolves the frozen profile proxy from its private secret file, refuses redirects and performs one POST with zero retries. The connection/request-upload timeout is bounded by the profile and 30 seconds (urllib3 applies this budget to socket body writes as well), and read timeout is bounded by the profile and 120 seconds; paid jobs have 180-second queue deadlines and heartbeat fencing. Responses are bounded to 1 MiB. Safe receipts distinguish send/wait-headers, body-read and validation stages, HTTP status when available, durations, request/response bytes, fixed nested exception types and allowlisted errno; raw exception messages, endpoints and secrets are excluded. A connection error still represents an uncertain paid outcome. The UI exposes cache generation/status/expiry and separate prefix/bbox attempts, failures, elapsed time and actual cached tokens; costs remain unknown without pricing/billing. Compression and fixture success do not prove live connection repair.

Connections idle for at least 30 seconds are retired before the next POST; any failed request also clears the pool for future explicit work. Recent successful requests retain pooling. Receipts add connect_upload_timeout_seconds, read_timeout_seconds, pool_idle_reset and pool_failure_reset without raw error text. Neither pool retirement nor the larger upload budget retries an uncertain call.

Explicit pause archives the active review round as cancelled, retaining frozen membership/job IDs and completed evidence, and revokes outstanding jobs in the same transaction. This releases source-group editing while disabled; pause never recreates cancelled annotations or retries an uncertain paid call. Re-enabling retains initialization; failed cache recovery and cancelled images still require explicit restart/relabel actions.

Incomplete-cohort checks match terminal annotation jobs by original sample ID and annotation version. A failed, interrupted, stale or cancelled older version remains auditable but cannot pause an explicitly requested newer queued version. A terminal current version still blocks admission; no old attempt is retried.

An explicit source-group edit on a disabled task also archives any revoked round left by older pause implementations. It neither enables admission nor queues work. Enabled active rounds and frozen dataset groups still reject edits; repeated edits do not duplicate archived history.

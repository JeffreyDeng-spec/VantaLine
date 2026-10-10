# Real-photo feedback

**Status: Authoritative**

## Foundation batch

The foundation introduces account-opt-in `real_photo_vlm` storage, API, source capture and strict localization contracts. Empty `VANTALINE_REAL_PHOTO_ACCOUNTS` preserves current behavior. Enabling requires an explicit fixed Doubao bbox binding and first disables legacy feedback admission; active legacy labeling must settle first. Initial AI-generated pretraining remains unchanged. Historical artifacts remain available through the old API and the owner-only history index; their frames are drafts and require explicit original-hash, first-frame geometry and source-group confirmation before reuse. Failed historical review records are not combined into labels.

Original source bytes are frozen separately from annotated previews. Exact source hashes and explicit lineages deduplicate candidates; approximate similarity never deletes different photos. Camera source groups derive from the existing station/session, videos from source upload identity, and ordinary uploads from the upload request. Historical missing groups block split admission until an owner supplies one. UI/labels retain decoded first-frame geometry and recorded EXIF orientation; VLM inputs may use the explicit recorded source-to-input scale described below. No implicit orientation conversion is applied.

`bbox_annotation` is independently bound to `doubao-seed-2-1-pro-260915`. The blind request includes every task category/reference and the real original, never previous detections, masks or review results. It uses normalized 0–1000 xyxy, visible tight boxes, temperature 0, thinking disabled, high detail and 4096 output tokens. Invalid/unknown/duplicate/out-of-bounds/truncated results fail as complete attempts and retain their bounded response and available usage. Each attempt is recorded before execution. A retry requires an explicit new version; there is no mask fallback.

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


VLM 图片输入先限制长边：类别参考图 1024 像素、实拍原图 2048 像素，只等比缩放，不裁剪或隐式旋转。回执同时记录原图尺寸、输入尺寸、原图哈希、输入哈希及原图到输入的缩放矩阵；归一化框仍换算到原图像素坐标。准备阶段失败结算为失败标注版本，显示固定阶段代码，不记成已发生的付费调用；必须由用户主动重标，不自动重放。

训练审核 worker 区分 CLI 非零退出、未完成/失败的 turn、缺失报告和被拒绝的报告。每次尝试保留固定原因代码、退出状态、报告接纳状态、提示词 SHA-256 与已有 token 回执；报告拒绝只记录白名单分类及有界计数，不记录请求、异常原文或 CLI 输出。模型正常退出不能替代报告接纳，失败后仍要求前端主动恢复，不自动重放。所有 reason/gap 限制为非空且不超过 1000 字符，初始化理由需简洁，并明确 submit 返回 accepted 后才算提交。

豆包专用输入副本采用 JPEG quality=90，保持原有等比尺寸限制和坐标映射。原始文件、Agent 复核与训练导出的完整第一帧 PNG 不变。回执版本为 bounded-first-frame-jpeg-v2，记录编码字节哈希、解码输入像素哈希、编码前像素哈希及 JPEG 质量；旧 PNG 回执保留。失败区分 transport_failed 与 response_validation_failed，只保存固定异常类型，不能作为自动重放依据。图片压缩改善请求体大小，但真实出框质量和连接可靠性仍须前端调用验证。

# Batch CLI v3

**Status: Authoritative**

Read [per-label schemas](cli.md) for element/check/issue/summary JSON. All those
commands require `--label ID` in a batch. IDs come from `vantaline batch show`;
CLI cannot create/delete actual labels or operate outside its batch. Originals
are /input/media/{image_hash}.png; contact sheets are navigation only.

```sh
vantaline batch show
vantaline batch progress --message '正在匹配全部实拍标签'
vantaline reference upsert --file /work/reference.json
vantaline label match set --label label_123 --file /work/match.json
vantaline card show --label label_123
vantaline element upsert --label label_123 --file /work/element.json
vantaline checklist set --label label_123 --file /work/checklist.json
vantaline check upsert --label label_123 --file /work/check.json
vantaline issue upsert --label label_123 --file /work/issue.json
vantaline image crop --label label_123 --source actual --box '[0,0,1,1]' --file /work/crop.png
vantaline artifact add --label label_123 --source actual --box '[0,0,1,1]' --file /work/crop.png
vantaline image decode --label label_123 --source reference
vantaline card summary set --label label_123 --file /work/summary.json
vantaline card finalize --label label_123
vantaline batch summary set --file /work/batch-summary.json
vantaline batch finalize
```

Reference region JSON: `id` is a stable region ID, `asset_id` comes from batch
inputs.references. Multiple distinct single-label regions can use the same image.

```json
{"id":"R1","asset_id":"ast_example","name":"电池标签","region":[0.1,0.2,0.8,0.5]}
```

Match JSON (publish after references, before inspection):

```json
{"status":"matched","reference_id":"R1","candidate_ids":["R1"],"reason":"轮廓、型号结构和图标组合对应；颜色仍需单独检查"}
```

Or uncertain; reference_id must be null. Explain the obstacle and possible candidates:

```json
{"status":"needs_confirmation","reference_id":null,"candidate_ids":[],"reason":"未能可靠确定标准，需要人工指定；该实拍仍保留在本批次"}
```

Each image is intended to be one physical label. A multi-label actual or unreadable
capture requires manual confirmation/replacement, not an arbitrary chosen label.
Human correspondence in a retry is frozen; inspect it and record uncertainty if
it cannot be verified, without overriding the human selection.

All per-label JSON schemas and ten-dimension/element coverage rules match v2.
Artifact/decode responses wrap their persisted record in `value` beside label_id.
IDs for elements/checks/issues are local to the label. No batch-global fallback
for label evidence is allowed. You may script repeated CLI calls for efficiency,
but observations must come from actual image inspection, not copied standard answers.

Every actual needs a match outcome. Matched labels need all planned checks settled
and valid summaries; needs_confirmation labels can be structurally reported without
a fabricated inspection. Batch summary uses the same summary JSON schema: any
confirmed difference requires DIFFERENCES; otherwise unresolved matches/scope need
REVIEW_REQUIRED. MATCH requires every actual fully matched and inspected. All
uncertainty remains in unchecked_scope even if differences are present.

If the deadline prevents inspection, retain pending checks and publish a provisional
summary identifying remaining label IDs. Do not finalize; the worker will preserve
the partial report and mark failure/timeout. Uncertainty is for an inspected but
unverifiable condition, not a substitute for work never performed.

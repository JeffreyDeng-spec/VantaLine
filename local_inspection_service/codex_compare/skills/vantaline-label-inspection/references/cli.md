# Task-bound CLI contract v2

**Status: Authoritative**

Commands return JSON; nonzero exit means validation or transport failed. On transport
retry retain `vantaline --request-id UNIQUE_ID ...` with the exact original payload.
`card show` returns the website-created card; CLI cannot create or select other cards.

```sh
vantaline card show
vantaline card progress --message '正在拆解标签元素'
vantaline element upsert --file /work/element.json
vantaline checklist set --file /work/plan.json
vantaline check upsert --file /work/check.json
vantaline issue upsert --file /work/issue.json
vantaline image crop --source actual --box '[0.1,0.2,0.3,0.2]' --scale 2 --file /work/crop.png
vantaline image map --crop '[0.1,0.2,0.3,0.2]' --box '[0,0,0.5,1]'
vantaline artifact add --file /work/crop.png --source actual --box '[0.1,0.2,0.3,0.2]'
vantaline image decode --source reference --box '[0,0,1,1]'
vantaline card summary set --file /work/summary.json
vantaline card finalize
```

All geometry is normalized to the frozen EXIF-oriented original, NOT a crop/preview.
A region is null, `{"box":[x,y,w,h]}` or `{"polygon":[[x,y],...]}` (3–64 points).
Artifact responses include the persisted ID and server-generated crop transform.
Decode responses include the persisted ID, decoded values and decoder metadata/error.
No decoded value means uncertain, not proof that the printed code is invalid.

Element JSON (categories: text/logo/symbol/diagram/code/color_block/outline/engineering):

```json
{"id":"E1","category":"text","name":"型号","description":"标签上方型号文字","reference":{"box":[0.1,0.2,0.3,0.1]},"actual":{"box":[0.1,0.22,0.3,0.1]}}
```

Checklist JSON, publish before check results; repeated `set` only adds IDs, never
removes checks or resets results. `element_ids: []` means the whole label.
Publish all ten overall dimensions even when some are inapplicable, then explain
inapplicability through a result. Split large plans across multiple set commands.

```json
{"checks":[{"id":"C1","element_ids":["E1"],"dimension":"text","expected":"型号 CDAL-2004"}]}
```

Check result, preserve id/element_ids/dimension/expected from plan:

```json
{"id":"C1","element_ids":["E1"],"dimension":"text","expected":"型号 CDAL-2004","observed":"CDAL-2005","status":"difference","explanation":"末位数字不同","artifact_ids":[],"decode_ids":[]}
```

States: pending/running/match/difference/uncertain/not_applicable. Settled states
require both observed and explanation. For code matches include local decode_ids
on both sides. Other evidence IDs are optional when originals suffice.

Issue JSON; one required for each difference check. Null location is permitted
only with an explanation, e.g. missing element with reliable reference location.

```json
{"id":"I1","check_id":"C1","title":"型号末位不同","explanation":"标准为 4，实拍为 5","reference":{"box":[0.1,0.2,0.3,0.1]},"actual":{"box":[0.1,0.22,0.3,0.1]},"artifact_ids":[],"resolved":false}
```

Summary JSON, decision MATCH / DIFFERENCES / REVIEW_REQUIRED:

```json
{"decision":"DIFFERENCES","message":"型号存在差异，其余待核实内容见清单","checked_scope":"型号文字及已逐项记录的维度","unchecked_scope":"未能确认的小字、材料和实际毫米尺寸"}
```

Limits: 200 elements, 500 checks/issues, 200 crops/decodes, 2000 events, 64 KiB
per JSON write, 4000 characters per description. Finalize validates coverage and
freezes model writes; worker separately verifies successful session termination.

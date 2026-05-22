# Book Image2 Review Report - 2026-05-20 Refresh

## Summary
- reviewed_pngs: 155
- new_since_previous_review: 13
- deterministic_failures: 0
- visual_failures: 48
- warnings: 28
- passes_or_low_drift: 79
- failure_by_state: {'upright_dot': 27, 'lying_bar': 17, 'no_bottle': 4}
- warning_by_state: {'lying_bar': 16, 'upright_dot': 12}
- new_failures: [{'task_id': 'img2-0114', 'bottle_proxy_state': 'lying_bar', 'outside_proxy_pct_gt25': '0.1745', 'failure_reasons': 'major source-scene drift outside proxy region (pct_gt25=0.1745); manual layout/text not reliably preserved'}, {'task_id': 'img2-0115', 'bottle_proxy_state': 'upright_dot', 'outside_proxy_pct_gt25': '0.1991', 'failure_reasons': 'major source-scene drift outside proxy region (pct_gt25=0.1991); manual layout/text not reliably preserved'}, {'task_id': 'img2-0116', 'bottle_proxy_state': 'lying_bar', 'outside_proxy_pct_gt25': '0.2109', 'failure_reasons': 'major source-scene drift outside proxy region (pct_gt25=0.2109); manual layout/text not reliably preserved'}, {'task_id': 'img2-0117', 'bottle_proxy_state': 'lying_bar', 'outside_proxy_pct_gt25': '0.1855', 'failure_reasons': 'major source-scene drift outside proxy region (pct_gt25=0.1855); manual layout/text not reliably preserved'}, {'task_id': 'img2-0176', 'bottle_proxy_state': 'lying_bar', 'outside_proxy_pct_gt25': '0.1533', 'failure_reasons': 'major source-scene drift outside proxy region (pct_gt25=0.1533); manual layout/text not reliably preserved'}, {'task_id': 'img2-0178', 'bottle_proxy_state': 'lying_bar', 'outside_proxy_pct_gt25': '0.1576', 'failure_reasons': 'major source-scene drift outside proxy region (pct_gt25=0.1576); manual layout/text not reliably preserved'}, {'task_id': 'img2-0180', 'bottle_proxy_state': 'lying_bar', 'outside_proxy_pct_gt25': '0.1673', 'failure_reasons': 'major source-scene drift outside proxy region (pct_gt25=0.1673); manual layout/text not reliably preserved'}]
- new_warnings: [{'task_id': 'img2-0111', 'bottle_proxy_state': 'lying_bar', 'outside_proxy_pct_gt25': '0.0619'}, {'task_id': 'img2-0112', 'bottle_proxy_state': 'lying_bar', 'outside_proxy_pct_gt25': '0.0753'}, {'task_id': 'img2-0113', 'bottle_proxy_state': 'upright_dot', 'outside_proxy_pct_gt25': '0.0768'}, {'task_id': 'img2-0175', 'bottle_proxy_state': 'lying_bar', 'outside_proxy_pct_gt25': '0.0693'}, {'task_id': 'img2-0177', 'bottle_proxy_state': 'upright_dot', 'outside_proxy_pct_gt25': '0.067'}, {'task_id': 'img2-0179', 'bottle_proxy_state': 'upright_dot', 'outside_proxy_pct_gt25': '0.1241'}]
- new_failure_ratio: 7/13
- recommended_prompt_change: Producer prompt must explicitly instruct Image2 to preserve every pixel outside the black proxy bbox/anchor area and reject full-scene regeneration; use proxy-local edit/mask if Image2 supports it.
- production_recommendation: Continue only if Mandy accepts Book repairing drift rows later; otherwise pause broad production because >50% of the latest increment hard-failed source-scene preservation.
- qa_dir: /mnt/f/CodexWorkspace/assembly_line_optimize/qa_reports/book_image2_review_20260520

## Failed Task IDs
- img2-0006 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.1767); manual layout/text not reliably preserved
- img2-0025 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.3420); manual layout/text not reliably preserved
- img2-0032 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.2870); manual layout/text not reliably preserved
- img2-0038 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.3746); manual layout/text not reliably preserved
- img2-0040 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.3078); manual layout/text not reliably preserved
- img2-0045 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.3166); manual layout/text not reliably preserved
- img2-0046 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.3411); manual layout/text not reliably preserved
- img2-0047 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.2955); manual layout/text not reliably preserved
- img2-0056 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.3183); manual layout/text not reliably preserved
- img2-0058 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.3888); manual layout/text not reliably preserved
- img2-0061 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.3682); manual layout/text not reliably preserved
- img2-0063 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.2705); manual layout/text not reliably preserved
- img2-0072 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.3536); manual layout/text not reliably preserved
- img2-0075 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.3174); manual layout/text not reliably preserved
- img2-0085 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.4244); manual layout/text not reliably preserved
- img2-0095 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.1892); manual layout/text not reliably preserved
- img2-0097 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.3345); manual layout/text not reliably preserved
- img2-0101 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.1596); manual layout/text not reliably preserved
- img2-0114 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.1745); manual layout/text not reliably preserved
- img2-0115 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.1991); manual layout/text not reliably preserved
- img2-0116 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.2109); manual layout/text not reliably preserved
- img2-0117 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.1855); manual layout/text not reliably preserved
- img2-0157 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.2658); manual layout/text not reliably preserved
- img2-0159 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.3204); manual layout/text not reliably preserved
- img2-0161 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.2706); manual layout/text not reliably preserved
- img2-0163 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.1629); manual layout/text not reliably preserved
- img2-0164 (upright_dot): upright-dot output remains visually under-scaled/anchor quality questionable from prior blocker
- img2-0165 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.2057); manual layout/text not reliably preserved
- img2-0166 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.3355); manual layout/text not reliably preserved
- img2-0167 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.3199); manual layout/text not reliably preserved
- img2-0168 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.2184); manual layout/text not reliably preserved
- img2-0169 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.2906); manual layout/text not reliably preserved
- img2-0170 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.3133); manual layout/text not reliably preserved
- img2-0176 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.1533); manual layout/text not reliably preserved
- img2-0178 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.1576); manual layout/text not reliably preserved
- img2-0180 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.1673); manual layout/text not reliably preserved
- img2-0501 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.1851); manual layout/text not reliably preserved
- img2-0502 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.2445); manual layout/text not reliably preserved
- img2-0503 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.2006); manual layout/text not reliably preserved
- img2-0504 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.2659); manual layout/text not reliably preserved
- img2-0510 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.2353); manual layout/text not reliably preserved
- img2-0861 (no_bottle): no_bottle row changed/regenerated manual layout instead of preserving source scene
- img2-0862 (no_bottle): no_bottle row changed/regenerated manual layout instead of preserving source scene
- img2-0952 (upright_dot): major source-scene drift outside proxy region (pct_gt25=0.1969); manual layout/text not reliably preserved
- img2-0953 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.2018); manual layout/text not reliably preserved
- img2-0974 (no_bottle): no_bottle row changed/regenerated manual layout instead of preserving source scene
- img2-0986 (lying_bar): major source-scene drift outside proxy region (pct_gt25=0.1586); manual layout/text not reliably preserved
- img2-0994 (no_bottle): no_bottle row changed/regenerated manual layout instead of preserving source scene

## New Failure Ratio
Latest increment hard failures: 7/13. New failed rows: img2-0114, img2-0115, img2-0116, img2-0117, img2-0176, img2-0178, img2-0180.

## Repair Attempt - Seven New Hard Failures
Status: unresolved repair blocker for all seven requested rows. No output overwritten.

- img2-0114: major source-scene/manual drift outside proxy region (outside_proxy_pct_gt25=0.1745); repair blocked because Image2/AI edit endpoint returned FORBIDDEN.
- img2-0115: major source-scene/manual drift outside proxy region (outside_proxy_pct_gt25=0.1991); repair blocked because Image2/AI edit endpoint returned FORBIDDEN.
- img2-0116: major source-scene/manual drift outside proxy region (outside_proxy_pct_gt25=0.2109); repair blocked because Image2/AI edit endpoint returned FORBIDDEN.
- img2-0117: major source-scene/manual drift outside proxy region (outside_proxy_pct_gt25=0.1855); repair blocked because Image2/AI edit endpoint returned FORBIDDEN.
- img2-0176: major source-scene/manual drift outside proxy region (outside_proxy_pct_gt25=0.1533); repair blocked because Image2/AI edit endpoint returned FORBIDDEN.
- img2-0178: major source-scene/manual drift outside proxy region (outside_proxy_pct_gt25=0.1576); repair blocked because Image2/AI edit endpoint returned FORBIDDEN.
- img2-0180: major source-scene/manual drift outside proxy region (outside_proxy_pct_gt25=0.1673); repair blocked because Image2/AI edit endpoint returned FORBIDDEN.

## Continued Review After img2-0180
- img2-0181: FAIL, major source-scene/manual drift outside proxy region; outside_proxy_pct_gt25=0.2797.

## Kevin Recheck And JSON Dispatch - 2026-05-20 16:59
PASS after Kevin repair: img2-0114, img2-0115, img2-0116, img2-0117, img2-0176, img2-0178, img2-0181.

Retry after Kevin repair: img2-0180 (visible green repair patch/artifact remains in proxy region).

New hard failures reviewed and sent to Kevin as canonical JSON tasks: img2-0118, img2-0119, img2-0120, img2-0121, img2-0122, img2-0123, img2-0182, img2-0183, img2-0184, img2-0185.

JSON dispatch batch: img2-0118, img2-0119, img2-0120, img2-0121, img2-0122, img2-0123, img2-0180, img2-0182, img2-0183, img2-0184, img2-0185.

## Kevin Recheck Delta - 2026-05-20 17:12
PASS after Kevin JSON repair: img2-0120, img2-0123. No retry or new-hard-fail delta in this receipt batch.

## Kevin Recheck Delta - 2026-05-20 17:40
PASS after Kevin repair: img2-0118, img2-0119, img2-0121, img2-0122, img2-0180, img2-0185.

New hard failures sent to Kevin as JSON repair tasks: img2-0124, img2-0125, img2-0126, img2-0186, img2-0187, img2-0188, img2-0189, img2-0190.

Still awaiting Kevin receipts from prior dispatch: img2-0182, img2-0183, img2-0184.


## Kevin Recheck Delta - 2026-05-20 18:18
PASS after Kevin repair/retry and Book visual/deterministic recheck: img2-0124, img2-0126, img2-0186, img2-0188, img2-0189.

Focused retries sent and awaiting Kevin receipt: img2-0125, img2-0182, img2-0187.

Still awaiting first Kevin receipt from the 17:42 dispatch: img2-0190.

Clean current status source: book_kevin_status_current.csv. Earlier aggregate CSVs contain stale historical rows and have correction rows appended; use the current CSV for Mandy-facing state.


## Repair Workflow Stop - 2026-05-20 18:26
Mandy relayed T J.'s cancellation of the current Book/Kevin Image2 repair workflow. Book stopped repair dispatch and repair acceptance work immediately.

Do not treat any Kevin-repaired output as final from this workflow unless explicitly reassigned later. Mandy is restoring Kevin-modified files back to pre-repair versions where backups exist.

Non-final receipts present at stop time: img2-0125, img2-0187, img2-0190. The img2-0190 asset-rule retry ticket was sent before the urgent stop email timestamp and is recorded as non-final.

Clean current status source after stop: book_kevin_status_current.csv, with rows marked WORKFLOW_STOPPED_NOT_FINAL.

Post-stop Kevin receipt logged as non-final: img2-0190 at 2026-05-20T10:31:59Z. No Book recheck or acceptance performed.

Post-stop Kevin receipt logged as non-final: img2-0182 at 2026-05-20T10:39:40Z. No Book recheck or acceptance performed.

Post-stop Kevin receipt logged as non-final: img2-0188 at 2026-05-20T10:41:22Z. No Book recheck or acceptance performed.

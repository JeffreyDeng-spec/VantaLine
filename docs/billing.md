# Administrator usage and costs

**Status: Authoritative**

## Ownership and access

Settings → 用量与成本 is available only to `role=admin`, independent of ordinary
feature grants or usernames. Every billing route runs the same request identity
role check as a FastAPI dependency before payload validation and again before
domain access. Financial GETs read durable caches only; they never enqueue work
or call a supplier. Responses are private/no-store. Logout, identity or role
change clears private frontend caches; 401/403 suppresses stale financial data.

`analytics/billing/` owns validated payer configuration, supplier reads,
synchronization and projections. `storage/billing_repository.py` owns PostgreSQL
transactions. Canonical analytics wiring supplies repository, private secret
resolution and thread scope; HTTP registration mounts routes and the inert
startup hook. The financial producer drains before repository shutdown. No
business service imports `server` or submits model/Agent/training/resource work.

## Data and accuracy

One card represents one provider/site/payer identity; distinct payers are never
merged. Six provider families are retained: Volcengine, Alibaba Cloud, Tencent
Cloud, RunPod, Gemini and Codex. Cursor/Agnes are absent from active payer cards;
legacy cost evidence is retained separately. Ali `AvailableAmount` is explicitly
labelled available credit; cash, credit, gifted balances, freezes and arrears stay
in the detail view and are not added to the primary balance.

All monetary parsing, totals and reconciliation use Decimal; JSON amounts are
decimal strings with the original currency. Tencent balance amounts in cents
are divided by 100 exactly. Missing data is null, not zero. Currencies are never
combined or converted. Balances are official snapshots and are not reconstructed
from task prices or month-to-date fees. Recharge is not consumption.

Volcengine reads `QueryBalanceAcct`, `ListBillOverviewByCategory` and
`ListBillDetail`. The single total-category row is selected without adding its
already included categories again; legacy `PayableAmount/Currency` and explicit
settlement `SettlePayableAmount/CurrencySettlement` pairings are supported without
cross-currency fallback. Alibaba reads `QueryAccountBalance`, `QueryBillOverview`
and token-paginated `DescribeInstanceBill`, avoiding the old 50,000-row API limit.
Monthly Alibaba resources are labelled monthly aggregates, not dated individual
transactions. Tencent reads `DescribeAccountBalance`,
`DescribeBillSummaryByProduct` and `DescribeBillDetail`; pagination continues to
a short page rather than stopping at its 24-hour cached Total. Principal IDs and
currencies are validated before publication. Unknown schemas fail explicitly.

RunPod GraphQL validates `myself.id` and reads `clientBalance`. Official REST
`/billing/pods`, `/billing/endpoints` and `/billing/networkvolumes` provide ranged
resource records. These do **not** prove complete payer coverage of public APIs,
savings plans or clusters. Their details are labelled supported-resources-only;
official account total, reconciliation delta and runway remain null. Gemini and
Codex remain unverified until an official financial source and payer are defined;
API inference credentials and subscription quotas are not cash balances.

Network-volume records accept the documented `time` or the observed live
`startDate` billing date; both must agree when present. Other resource families
still require `time`. Missing, invalid or out-of-period dates fail the complete
snapshot instead of being guessed from the request. Aggregation identity uses
the normalized billing day so equivalent schema variants deduplicate, while
conflicting amounts reject publication.

Every bills snapshot publishes only after all required pages succeed. Entries
deduplicate by provider identity or documented resource aggregation keys;
conflicting identities reject publication. Partial failure retains the previous
snapshot. Official totals and entry totals remain separate, including a nonzero
delta; unknown coverage is “待对账”, never a manufactured zero delta. Current
month figures remain provisional despite a zero current-snapshot delta.

Recent consumption uses seven complete source billing days, with a conservative
two-day lag, original source timezone and explicit from/to dates. Missing days,
partial coverage, stale/failed sources or unknown balances suppress runway.
Complete zero consumption is “无消耗”; net refunds do not produce negative or
infinite runway. Runway is a reference estimate using available balance/credit
divided by posted expense, not a guaranteed remaining uptime or real-time cash
deduction rate. Historical month selection does not change current balance or
the current consumption window. Red means under three days or depleted known
balance; amber means under fourteen days or failed/stale data; grey means data
insufficient. Known urgent evidence is not hidden by a sync-failure badge.

## Synchronization and API

- `GET /api/admin/billing/overview?period=YYYY-MM`: cards, separate currency
  totals, exact aggregated daily trends and source completeness.
- `GET /api/admin/billing/accounts/{id}?period=YYYY-MM`: snapshots, component
  balances, resource/project breakdowns, source/time and reconciliation.
- `GET /api/admin/billing/accounts/{id}/entries`: `period`, optional
  `snapshot_id`, `cursor`, and `limit` (default 50, maximum 100). Cursors bind
  payer, period, immutable snapshot and descending `(day,id)` boundary. New
  snapshots cannot move existing pages. A mismatched cursor is 400.
- `POST /api/admin/billing/refresh`: strict JSON `{account_id?: string,
  period?: YYYY-MM}`; returns `job_ids`, period and pending-account count.
- `GET /api/admin/billing/jobs/{id}`: bounded public job status and fixed error
  code. No actor, credentials or supplier payload is exposed.

Unknown accounts/jobs return 404, unavailable storage returns 503 and invalid
periods return 400. Periods cover the current and previous 17 months. The legacy
`/api/admin/api-cost-ledger` response is unchanged; its unit-price-based monetary
figures are presented as project estimates, never official bills.

The owned worker wakes every five seconds, admits balances every 60 seconds and
current bills every 900 seconds. It additionally syncs the previous month during
the first nine days to cover the rolling window. Historic periods are synced on
explicit refresh. Requests coalesce across processes using per-lane PostgreSQL
locks; only one supplier reader per payer owns a 600-second lease. Publication
checks the exact lease token and deadline. Expired claims can be reclaimed;
stale workers cannot overwrite data. Refresh failures are also throttled.

Transport is financial-only with fixed action/endpoint allowlists, no provider
mutations, redirects, ambient proxy or automatic request replay. Requests pace
at no more than four per second, use 5-second connect/12-second read bounds, an
8 MiB response bound and a 480-second/300-request work bound. More than 100,000
rows rejects the sync; it never publishes a truncated ledger. Errors are fixed
codes, not raw messages, URLs, signatures or account records.

Visible pages poll durable snapshots every 30 seconds and submitted job status
every three seconds; hidden pages pause polling. Frontend money display rounds
decimal strings without binary summation; only chart geometry/ratios use Number.

## Configuration, acceptance and rollback

`VANTALINE_BILLING_ACCOUNTS_JSON` is a server-only JSON list (maximum 32 payers).
Each entry accepts `provider`, `payer_id`, `alias`, `site` (`cn` or
`international`), `currency`, `key_ref`, `secret_ref` and optional
`resource_projects` mapping resource IDs to `vantaline` or `other`. Credential
references are existing secret-environment names, not values or URLs. RunPod
needs `key_ref` only. Volcengine international balance is currently unverified
and is rejected explicitly. Resource associations require operator-verified
evidence; no filename, time or proportional guesses are allowed.

When the runtime variable is absent, operators may atomically publish the same
JSON list to the private data file `billing_accounts.local.json`. Explicit runtime
values, including `[]`, always take precedence. The reader reloads this file on
queries and scheduler ticks without restarting services. Files must be bounded,
private regular single-link files owned by root or the service user; terminal
symlinks, public modes, duplicate JSON keys and invalid payer mappings fail with
a fixed error. This is configuration only, never a filesystem financial ledger.

After explicit operator authorization and a successful official financial query,
a Tencent payer may use the reserved references `VANTALINE_BILLING_COS_SECRET_ID`
and `VANTALINE_BILLING_COS_SECRET_KEY`. They resolve only from the Web service's
existing private `CREDENTIALS_DIRECTORY/cos-credentials.json`; they never copy
credentials into the payer file or expand supplier permissions. Both references
must be paired on Tencent only. Temporary COS session credentials are currently
unsupported and remain unconnected. RunPod can explicitly reference its existing
`VANTALINE_RUNPOD_API_KEY`. Missing/denied capabilities remain pending; no business
or inference key is silently selected or tested in the background.

Missing configuration retains provider placeholders. Missing permissions keep
old snapshots with a reason; credentials and source permission are not created
or expanded automatically. PostgreSQL is required for durable billing; JSON
runtime does not fall back to a filesystem financial ledger. Construction does
no supplier or database I/O.

Use dedicated least-privilege financial query credentials. Before enabling a
payer, independently confirm its identity/currency and compare the primary
amount with the corresponding official console field at the same capture time.
Compare the same-period net fee with its official summary and complete imported
records. Mock/browser fixtures prove interfaces, not actual financial accuracy.
An unavailable/unverified account is not certified as connected.

`python scripts/check_billing_connection.py --expected-file PRIVATE_JSON
--secret-env-file EXISTING_PRIVATE_SECRET_ENV` performs explicit read-only
commissioning without importing the Web application or accessing a database.
The private expected file is a list containing provider, payer_id, site, currency,
period, the official console balance/net total and timezone-aware captured_at;
the console evidence must be at most 180 seconds old when the check begins.
The command emits only fixed status codes, currencies, capture times and match
booleans, never amounts, payer IDs, secrets or supplier payloads. A nonzero exit
means acceptance is incomplete. Never commit its private input or raw evidence.

Migration `2026_10_13_billing.sql` is additive and transactional. Whole immutable
release rollback retains all financial tables, sync evidence and snapshots;
never delete records, modify old snapshots or copy individual production files.

Primary references: [Volcengine billing](https://docs.volcengine.com/docs/BillingCenter/APIOverview-10?lang=en),
[Alibaba instance bills](https://www.alibabacloud.com/help/en/user-center/developer-reference/api-bssopenapi-2017-12-14-describeinstancebill),
[Tencent balance](https://cloud.tencent.com/document/api/555/20253),
[RunPod GraphQL](https://graphql-spec.runpod.io/) and
[RunPod REST schema](https://github.com/runpod/docs/blob/main/api-reference/openapi.json).

## Global range menu retirement

The workspace no longer has a selected-user data-range menu. Billing continues to show the configured payer accounts to administrators; its heading describes that payer-based view without referring to a removed range selector.

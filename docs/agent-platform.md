# Agent platform implementation status

**Status: Authoritative — development foundation, not full-platform acceptance**

The target remains every effective business operation through structured tools,
with the operator's existing account permissions and the same business state as
the UI. This branch does **not** yet meet that target and must not be released as
the completed industrial Agent platform. The API-adapter inventory is not a
full-site action manifest or a coverage percentage.

## Implemented behavior

- `frontend/src/features/agent/registry.ts` provides account-gated registration,
  bounded input validation, compact results, sensitive-key redaction, concurrent
  mutation rejection and session-epoch checks. Domain API adapters call the
  existing frontend query functions and invalidate relevant query families.
- `AgentToolsProvider` adds context, paginated capability discovery, workspace
  navigation, file-handle discovery, and durable operation read/cancel tools.
  Workspace hooks share existing page callbacks for text selection/import,
  extraction geometry, accessory crop sessions, detection, native permissions,
  settings credential dialogs and account password-entry preparation.
- Accessory tools resolve opaque asset IDs against a freshly authenticated
  accessory gallery. Tool arguments do not accept server source paths for these
  actions. File handles exist only for the signed-in page lifetime.
- Browser registration uses `document.modelContext.registerTool(tool, {signal})`.
  Results are JSON strings for Chrome interoperability. One document-level queue
  handles React remounts and module changes; in-flight results are preserved
  before removing registrations, including on Chrome 152. The page reports tool
  readiness only after registration finishes. Legacy
  `unregisterTool` is used only when present. See the
  [Chrome imperative API documentation](https://developer.chrome.com/docs/ai/webmcp/imperative-api),
  verified September 11, 2026. Registration hints are not authorization.
- `GET /api/agent/capabilities` is authenticated and default-disabled. Enabling
  the developing browser surface requires both an explicit account ID in
  `VANTALINE_WEBMCP_ACCOUNTS` and that account's persisted enabled policy.
  The policy API requires the existing `agent_config` permission and admin role.
- `GET /api/operations/{id}` and `POST /api/operations/{id}/cancel` are scoped to
  the authenticated account. Cancellation requires the current operation version.
  A running task becomes `cancel_requested`, not `cancelled`.
- `storage/agent_operations.py` implements PostgreSQL admission, account/key
  idempotency, parameter conflicts, budget reservation, attempt-before-I/O state,
  policy checks for external attempts, versioned transitions and append-only
  audit writes in the same transaction. Unknown outcomes retain reservations and
  cannot be claimed again. Budgets currently use integer reservation units;
  provider-specific monetary estimation/settlement is not integrated.
- Protected PostgreSQL requests look up the session hash and account with indexed
  queries. Session refresh updates an existing locked row and cannot recreate a
  deleted session. Auth-management/bootstrap keeps the prior store workflow.
  Analysis detail lookup now uses the existing record-primary-key loader and
  preserves the existing record access check. The legacy text-comparison route
  now has an explicit `inspection` permission mapping.

## Not implemented or accepted yet

These are outstanding work, not exclusions from the agreed scope:

1. A reviewed mapping of every effective UI/form/local-state/API operation to a
   stable action ID, schema, permissions, prerequisites and acceptance tests.
   `api-manifest.generated.json` only inventories the exported query functions.
   Some multipart contracts and retired-function classifications still need a
   full source-to-UI review. Native file-tool instance names are page-local.
2. Complete UI/tool state equivalence in every domain, including task editors,
   resource-library filters/detail selection, all current pipeline transitions,
   verification/review flows, and interrupted native-input recovery.
3. `POST /api/operations`, domain admission integration, independently bounded
   inference/training workers, provider-job recovery and verified settlement.
   No production business handler currently submits through the new operation
   repository; discovery reports `operation_submission: false`.
4. Enforcing policies, quotas and egress restrictions at all existing UI, API,
   indirect and background entry points. Persisting a policy is **not** proof
   that existing paths obey it. No global policy/security guarantee is made by
   this foundation. Enable it only in isolated development until this is closed.
5. Version/parameter-bound confirmation intents for destructive and privilege
   changes; cross-process rate limits and all required concurrency budgets.
6. Indexed cursor lists, transactionally consistent projections/aggregates, the
   million-record/20-workspace/50-QPS workload, acceptance latency percentiles and
   training-load isolation. No latency or complexity target is claimed as met.
7. A real external Agent's complete business chains and authorized physical
   camera/PLC commissioning. Native browser fixture execution and protocol tests
   do not establish either of those results.
8. CI enforcement of the full reviewed action manifest, single-account rollout,
   immutable release deployment and post-release acceptance.

## Verification

`npm --prefix local_inspection_service/frontend run test:agent` checks generated
adapter drift, strict validation, secret redaction, session changes, duplicate
submissions, cache-refresh failure, signal-based registration, remount races and
workspace cleanup. It does not certify the generated adapters' entire behavior.

`local_inspection_service/scripts/smoke_agent_operations_postgres.py` requires an
explicit `AGENT_TEST_DATABASE_URL`. It creates a random disposable schema, tests
real PostgreSQL concurrency/idempotency, budget retention, revocation, cancellation,
unknown outcomes, audit rollback and indexed authentication, then deletes only
that schema. It never falls back to the service's production `DATABASE_URL`.

For the native browser fixture, build and preview from the frontend with
`VITE_ROUTER_BASENAME=/ npx vite build --base / --outDir /private/tmp/vantaline-agent-browser-dist`, then
`npx vite preview --base / --outDir /private/tmp/vantaline-agent-browser-dist --host 127.0.0.1 --port 5173`.
Use a temporary output directory; never serve production credentials.
Run `scripts/test_agent_webmcp.cjs` with `PLAYWRIGHT_MODULE`, `AGENT_CHROME_PATH`
and optionally `AGENT_UI_BASE` pointing to the local test setup. The script blocks
external requests and replaces all APIs/media with fixtures. It uses the browser's
native `getTools`/`executeTool` for operations, without DOM clicks or screenshot
coordinates. Successful Chrome 152.0.7977.83 runs covered discovery, paginated menus, live React
selection/form updates, native-permission waiting, module cleanup and logout
revocation locally. The fixture waits for the page's published-tool readiness
signal; optional `AGENT_TRACE_REGISTRATION=1` records lifecycle diagnostics.
An external model is not involved in that test.

### Lifecycle investigation and regression evidence

The previously reported startup disappearance was a premature test invocation,
not established evidence of a disappearing application registry. In Playwright
1.62.1, `page.waitForFunction(async () => false)` returned false immediately
instead of waiting until timeout. Its polling code checks the Promise object as
truthy before adopting its resolved value. The fixture now explicitly awaits
native discovery snapshots in Node, checks actual names/readiness, and fails on
a bounded timeout. Business operations are executed once; they are not retried.
No browser API wrapping or registration tracing is needed for the passing tests.

A separate real adapter defect was then reproduced in the native lifecycle test:
after the last callback finished, microtask reconciliation could abort its
registration before Chrome 152 delivered the native result, yielding
`UnknownError`. The adapter now retains each in-flight result-channel lease until
the next event-loop task. Session revocation still rejects new execution
immediately; it does not wait for deferred menu cleanup or replay an operation.

Local final verification on Chrome 152.0.7977.83: 10 independent full-application
runs and 10 independent native lifecycle runs passed without registration
instrumentation. The lifecycle fixture uses the actual production registry and
adapter and tests delayed registration, negative timeout, concurrent reads during
module switching, revocation, result redaction and repeated remounts. This is
finite regression evidence, not a claim about all browser versions or physical
industrial workflows.

Run `node scripts/test_agent_webmcp_lifecycle.cjs` with `PLAYWRIGHT_MODULE` and
`AGENT_CHROME_PATH`. It serves only intercepted synthetic pages/modules and needs
no live service. The required frontend CI job runs `test:agent`, including the
async-discovery helper and result-delivery regressions. Native browser suites are
explicit local checks until the supported experimental browser is pinned in CI.

Primary references checked during diagnosis:

- [Playwright polling implementation](https://github.com/microsoft/playwright/blob/main/packages/playwright-core/src/server/frames.ts): `waitForFunctionExpression` checks the predicate value before resolving it; verified against the installed 1.62.1 bundle and a minimal empty-page reproduction.
- [Chrome imperative API](https://developer.chrome.com/docs/ai/webmcp/imperative-api): signal-based unregistration and the Chrome 153 change preserving in-flight executions.
- [WebMCP draft](https://webmachinelearning.github.io/webmcp/): asynchronous discovery, tool lifecycle and event-loop integration; this remains an evolving draft.
- [Chrome-maintained React hook](https://github.com/GoogleChromeLabs/use-webmcp-tool/blob/main/useWebMCP.js): stable callback references and lifecycle cleanup; reviewed for comparison, not added as a dependency.

## Release boundary

The additive `2026_09_11_agent_operations.sql` migration creates independent
policy/operation/attempt/audit tables. Previous releases ignore these tables;
do not drop them during whole-release rollback. Unknown attempts must remain
available for reconciliation. This foundation may be deployed as disabled code
through the normal immutable release workflow. Keep the commissioning allowlist
empty; deployment does not establish full-platform acceptance or authorize
activation while the outstanding items remain.

The full browser page continues to expose everything the account can access.
Neither a tool marker nor a confirmation proves human identity. Revoking the
account session is required to block that browser's existing API access; hiding
the tool menu alone is insufficient.

import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";

const compiledModule = process.argv[2];
if (!compiledModule) throw new Error("usage: node smoke_task_navigation_preferences.mjs <compiled-taskNavigation.js>");

const values = new Map();
globalThis.window = {
  localStorage: {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key)
  },
  dispatchEvent: () => true
};
globalThis.CustomEvent = class CustomEvent {
  constructor(type, init) { this.type = type; this.detail = init?.detail; }
};

const nav = await import(pathToFileURL(compiledModule).href);
values.set(nav.PINNED_TASK_IDS_KEY, JSON.stringify(["pipeline:legacy-a"]));
values.set(nav.ARCHIVED_TASK_IDS_KEY, JSON.stringify(["ai:legacy-a"]));

const claimedByA = nav.claimLegacyTaskPreferences("user-a");
assert.deepEqual(claimedByA.pinnedTaskIds, ["pipeline:legacy-a"]);
assert.equal(claimedByA.claimed, true);
assert.equal(nav.claimLegacyTaskPreferences("user-b").claimed, false, "user B must not inherit user A's legacy cache");

nav.writeStoredTaskIdsForUser(nav.PINNED_TASK_IDS_KEY, "user-a", ["pipeline:a", "pipeline:a"]);
nav.writeStoredTaskIdsForUser(nav.PINNED_TASK_IDS_KEY, "user-b", ["pipeline:b"]);
assert.deepEqual(nav.readStoredTaskIdsForUser(nav.PINNED_TASK_IDS_KEY, "user-a"), ["pipeline:a"]);
assert.deepEqual(nav.readStoredTaskIdsForUser(nav.PINNED_TASK_IDS_KEY, "user-b"), ["pipeline:b"]);

nav.clearClaimedLegacyTaskPreferences("user-b");
assert.ok(values.has(nav.PINNED_TASK_IDS_KEY), "non-owner must not clear legacy state");
nav.clearClaimedLegacyTaskPreferences("user-a");
assert.ok(!values.has(nav.PINNED_TASK_IDS_KEY));
assert.ok(!values.has(nav.ARCHIVED_TASK_IDS_KEY));

console.log("PASS: task navigation preference storage is user-isolated and legacy migration is single-owner");

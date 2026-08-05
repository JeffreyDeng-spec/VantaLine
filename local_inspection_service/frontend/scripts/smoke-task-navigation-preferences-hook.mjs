import assert from "node:assert/strict";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createServer } from "vite";

const storage = new Map();
globalThis.window = {
  localStorage: {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key)
  },
  dispatchEvent: () => true
};
globalThis.CustomEvent = class CustomEvent {
  constructor(type, init) { this.type = type; this.detail = init?.detail; }
};

let sessionUser = "user-a";
const serverPreferences = new Map([
  ["user-a", { pinned_task_ids: [], archived_task_ids: [], updated_at: 1, exists: true }],
  ["user-b", { pinned_task_ids: [], archived_task_ids: [], updated_at: 1, exists: true }]
]);
const pendingPosts = [];

globalThis.fetch = async (path, options = {}) => {
  assert.equal(path, "/api/user/preferences/tasks");
  if (options.method === "GET") {
    return Response.json(serverPreferences.get(sessionUser), { status: 200 });
  }
  assert.equal(options.method, "POST");
  const requestUser = sessionUser;
  const payload = JSON.parse(String(options.body));
  return new Promise((resolve) => {
    pendingPosts.push({
      userId: requestUser,
      payload,
      resolve() {
        const response = { ...payload, updated_at: Date.now(), exists: true };
        serverPreferences.set(requestUser, response);
        resolve(Response.json(response, { status: 200 }));
      }
    });
  });
};

const vite = await createServer({
  server: { middlewareMode: true, hmr: false, ws: false },
  optimizeDeps: { noDiscovery: true },
  appType: "custom",
  logLevel: "error"
});
try {
  const { useTaskNavigationPreferences } = await vite.ssrLoadModule("/src/features/tasks/useTaskNavigationPreferences.ts");
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  let latest;
  function Probe({ userId }) {
    latest = useTaskNavigationPreferences(userId, (error) => { throw error; });
    return null;
  }
  function tree(userId) {
    return React.createElement(QueryClientProvider, { client: queryClient }, React.createElement(Probe, { userId }));
  }
  const flush = async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));
  };

  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(tree("user-a"));
    await flush();
  });
  assert.equal(latest.preferencesReady, true);

  await act(async () => {
    latest.persistTaskPreferences((current) => ({
      pinnedTaskIds: [...current.pinnedTaskIds, "pipeline:a1"],
      archivedTaskIds: current.archivedTaskIds
    }));
    latest.persistTaskPreferences((current) => ({
      pinnedTaskIds: [...current.pinnedTaskIds, "pipeline:a2"],
      archivedTaskIds: [...current.archivedTaskIds, "ai:a2"]
    }));
    await flush();
  });
  assert.equal(pendingPosts.length, 1, "same-scope mutations must be serialized");
  assert.deepEqual(latest.pinnedTaskIds, ["pipeline:a1", "pipeline:a2"], "same-render updates must compose through the synchronous preference ref");

  await act(async () => {
    pendingPosts.shift().resolve();
    await flush();
  });
  assert.equal(pendingPosts.length, 1, "second mutation should start only after the first settles");
  assert.deepEqual(latest.pinnedTaskIds, ["pipeline:a1", "pipeline:a2"], "older response must not roll optimistic state back");
  assert.deepEqual(pendingPosts[0].payload.pinned_task_ids, ["pipeline:a1", "pipeline:a2"]);
  await act(async () => {
    pendingPosts.shift().resolve();
    await flush();
  });

  await act(async () => {
    latest.persistTaskPreferences({ pinnedTaskIds: ["pipeline:a3"], archivedTaskIds: [] });
    latest.persistTaskPreferences((current) => ({
      pinnedTaskIds: [...current.pinnedTaskIds, "pipeline:a4"],
      archivedTaskIds: current.archivedTaskIds
    }));
    await flush();
  });
  assert.equal(pendingPosts.length, 1);
  sessionUser = "user-b";
  await act(async () => {
    renderer.update(tree("user-b"));
    await flush();
  });
  assert.deepEqual(latest.pinnedTaskIds, [], "switching accounts must reset user A state");
  await act(async () => {
    pendingPosts.shift().resolve();
    await flush();
  });
  assert.equal(pendingPosts.length, 0, "queued user A mutation must be cancelled before sending under user B session");

  await act(async () => {
    latest.persistTaskPreferences({ pinnedTaskIds: ["pipeline:b1"], archivedTaskIds: [] });
    await flush();
  });
  assert.equal(pendingPosts.length, 1);
  assert.equal(pendingPosts[0].userId, "user-b");
  await act(async () => {
    pendingPosts.shift().resolve();
    await flush();
    renderer.unmount();
  });
  assert.deepEqual(serverPreferences.get("user-b").pinned_task_ids, ["pipeline:b1"]);
  assert.notDeepEqual(serverPreferences.get("user-a").pinned_task_ids, ["pipeline:a4"]);
  console.log("PASS: task preference hook serializes writes, ignores stale responses, and blocks cross-account queued writes");
} finally {
  await vite.close();
}

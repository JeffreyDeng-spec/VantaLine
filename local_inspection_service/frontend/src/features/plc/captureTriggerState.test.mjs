import assert from "node:assert/strict";
import test from "node:test";
import { nextCaptureTriggerState } from "./captureTriggerState.mjs";

function actions(values, triggerValue = 1) {
  let armed = false;
  return values.map((value) => {
    const next = nextCaptureTriggerState(armed, value, triggerValue);
    armed = next.armed;
    return next.action;
  });
}

test("startup high stays latched until reset", () => {
  assert.deepEqual(actions([1, 1, 1]), ["latched", "latched", "latched"]);
});

test("one reset-to-trigger edge fires once and sustained high does not repeat", () => {
  assert.deepEqual(actions([0, 1, 1, 1]), ["armed", "trigger", "latched", "latched"]);
});

test("reset rearms a second trigger", () => {
  assert.deepEqual(actions([0, 1, 1, 0, 1]), ["armed", "trigger", "latched", "armed", "trigger"]);
});

test("configured non-default trigger value uses exact equality", () => {
  assert.deepEqual(actions([1, 6, 6, 2, 6], 6), ["armed", "trigger", "latched", "armed", "trigger"]);
});

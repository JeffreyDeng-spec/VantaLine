export function nextCaptureTriggerState(armed, value, triggerValue) {
  if (!Number.isInteger(value) || !Number.isInteger(triggerValue)) throw new Error("PLC trigger values must be integers");
  if (value !== triggerValue) return { armed: true, action: "armed" };
  if (armed) return { armed: false, action: "trigger" };
  return { armed: false, action: "latched" };
}

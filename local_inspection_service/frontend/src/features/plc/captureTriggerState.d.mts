export type PlcCaptureEdgeAction = "armed" | "trigger" | "latched";
export function nextCaptureTriggerState(
  armed: boolean,
  value: number,
  triggerValue: number
): { armed: boolean; action: PlcCaptureEdgeAction };

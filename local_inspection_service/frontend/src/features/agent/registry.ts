import type { ActionDefinition, ActionResult } from "./contracts";
import { safeResult, validate } from "./validation";

export class ActionRegistry {
  private actions = new Map<string, { action: ActionDefinition; owner: symbol }>();
  private listeners = new Set<() => void>();
  private active = new Set<string>();
  private epoch = 0;
  private authorize: (action: ActionDefinition) => boolean = () => false;
  private after: (action: ActionDefinition) => Promise<void> = async () => {};
  configure(authorize: (action: ActionDefinition) => boolean, after: (action: ActionDefinition) => Promise<void>) { this.authorize = authorize; this.after = after; this.emit(); }
  reset() { this.epoch++; this.active.clear(); this.authorize = () => false; this.emit(); }
  subscribe(listener: () => void) { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; }
  refresh() { this.emit(); }
  private emit() { this.listeners.forEach(listener => listener()); }
  register(actions: ActionDefinition[]) {
    const owner = Symbol();
    const names = new Set<string>();
    for (const action of actions) {
      if (!/^[a-z][a-z0-9_]{0,100}$/.test(action.name)) throw new Error(`Invalid action name: ${action.name}`);
      if (this.actions.has(action.name) || names.has(action.name)) throw new Error(`Duplicate action: ${action.name}`);
      names.add(action.name);
    }
    for (const action of actions) this.actions.set(action.name, { action, owner });
    this.emit();
    return () => { for (const action of actions) if (this.actions.get(action.name)?.owner === owner) this.actions.delete(action.name); this.emit(); };
  }
  list() {
    return [...this.actions.values()].map(({ action }) => ({
      name: action.name, domain: action.domain, description: action.description,
      inputSchema: action.inputSchema, readOnly: action.readOnly,
      workspaceLocal: Boolean(action.workspaceLocal),
      available: this.authorize(action) && !action.available?.(),
      reason: !this.authorize(action) ? "FORBIDDEN" : action.available?.() ?? null,
      preconditions: action.preconditions ?? []
    }));
  }
  async execute(name: string, input: Record<string, unknown>): Promise<ActionResult> {
    const action = this.actions.get(name)?.action;
    if (!action) return { status: "failed", error: { code: "NOT_AVAILABLE", message: "Open the action's workspace and refresh capabilities." } };
    if (!this.authorize(action)) return { status: "failed", error: { code: "FORBIDDEN", message: "Current account cannot execute this action." } };
    const reason = action.available?.();
    if (reason) return { status: "failed", error: { code: "NOT_READY", message: reason } };
    try {
      if (new TextEncoder().encode(JSON.stringify(input)).length > 65536) throw new Error("Input exceeds 64KiB; use the file transfer workflow.");
      validate(action.inputSchema, input);
    } catch (error) { return { status: "failed", error: { code: "INVALID_ARGUMENT", message: (error as Error).message } }; }
    if (!action.readOnly && this.active.has(name)) return { status: "failed", error: { code: "BUSY", message: "This action is already running. Query its state before resubmitting." } };
    const epoch = this.epoch;
    if (!action.readOnly) this.active.add(name);
    try {
      const output = await action.execute(input);
      if (action.endsSession && epoch !== this.epoch) return {status:"completed",data:{authenticated:false}};
      if (epoch !== this.epoch) return { status: "outcome_unknown", error: { code: "SESSION_CHANGED", message: "Session changed during execution. Query the operation in the authorized session; do not replay." } };
      // A refresh failure must never turn an acknowledged write into a retryable write.
      if (!action.readOnly) { try { await this.after(action); } catch { /* query cache retains its error state */ } }
      if (epoch !== this.epoch) return {status:"outcome_unknown",error:{code:"SESSION_CHANGED",message:"Session changed while refreshing. Do not replay the operation."}};
      const clean = safeResult(output);
      if (new TextEncoder().encode(JSON.stringify(clean)).length > 60000) return { status: action.readOnly ? "failed" : "outcome_unknown", error: {code:"RESULT_TOO_LARGE", message:"Result exceeds 64KiB. Use a narrower query to verify state; do not replay a mutation."} };
      const result = clean as ActionResult | null;
      if (result && typeof result === "object" && ["completed", "accepted", "requires_user_input", "requires_confirmation", "failed", "outcome_unknown"].includes(result.status)) return result;
      return { status: "completed", data: clean };
    } catch (error) {
      const status = (error as { status?: number }).status;
      const code = status === 400 || status === 422 ? "INVALID_ARGUMENT" : status === 401 ? "AUTH_REQUIRED" : status === 402 ? "BUDGET_EXCEEDED" : status === 403 ? "FORBIDDEN" : status === 404 ? "NOT_FOUND" : status === 409 || status === 412 ? "STALE_STATE" : status === 429 ? "RATE_LIMITED" : "EXECUTION_FAILED";
      return { status: !action.readOnly && (!status || status >= 500) ? "outcome_unknown" : "failed", error: { code, message: status ? `Request rejected (${status}). Check the current application state.` : "Execution did not return a verified result. Do not automatically replay a mutation." } };
    } finally { if (epoch === this.epoch) this.active.delete(name); }
  }
}
export const actionRegistry = new ActionRegistry();

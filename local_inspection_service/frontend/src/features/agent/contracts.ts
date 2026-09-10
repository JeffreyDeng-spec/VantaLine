export type Schema = {
  type?: string; properties?: Record<string, Schema>; required?: string[];
  additionalProperties?: boolean | Schema; items?: Schema; enum?: unknown[];
  anyOf?: Schema[]; minimum?: number; maximum?: number; minLength?: number;
  maxLength?: number; minItems?: number; maxItems?: number; description?: string;
};
export type ActionStatus = "completed" | "accepted" | "requires_user_input" | "requires_confirmation" | "failed" | "outcome_unknown";
export interface ActionResult {
  status: ActionStatus;
  data?: unknown;
  error?: { code: string; message: string };
  operation_id?: string;
  next_action?: string;
}
export interface ActionDefinition {
  name: string;
  domain: string;
  description: string;
  inputSchema: Schema;
  readOnly: boolean;
  permissions?: string[];
  invalidates?: string[];
  workspaceLocal?: boolean;
  endsSession?: boolean;
  preconditions?: string[];
  available?: () => string | null;
  execute: (input: Record<string, unknown>) => unknown | Promise<unknown>;
}
export interface SiteTool {
  name: string; description: string; inputSchema: Schema;
  annotations: { readOnlyHint: boolean; untrustedContentHint: boolean };
  execute: (input: Record<string, unknown>, options?: {signal?: AbortSignal}) => Promise<string>;
}
export interface ModelContext {
  registerTool(tool: SiteTool, options?: {signal: AbortSignal}): unknown | Promise<unknown>;
  unregisterTool?: (name: string) => unknown | Promise<unknown>;
}
declare global { interface Document { modelContext?: ModelContext } }

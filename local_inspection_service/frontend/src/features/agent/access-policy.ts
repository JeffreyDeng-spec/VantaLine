import type { AuthUser } from "../../api/types";
import { hasPermission } from "../../app/permissions";
import type { ActionDefinition } from "./contracts";

export function canUseAgentAction(user: AuthUser | null | undefined, action: ActionDefinition, enabled: boolean) {
  return Boolean(enabled && user && (!action.requiresAdmin || user.role === "admin") &&
    (!action.permissions?.length || action.permissions.some(permission => hasPermission(user, permission))));
}

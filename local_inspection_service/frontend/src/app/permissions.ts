import type { AuthUser } from "../api/types";

export const ADMIN_ONLY_PERMISSIONS = new Set(["user_management"]);

export function hasPermission(user: AuthUser | null | undefined, permission?: string) {
  if (!permission) return true;
  if (!user) return false;
  if (ADMIN_ONLY_PERMISSIONS.has(permission)) return user.role === "admin";
  if (user.role === "admin") return true;
  return (user.permissions || []).includes(permission);
}

export function permissionForView(view: string) {
  return (
    {
      inspect: "inspection",
      aiInspect: "ai_detection",
      dataAnalysis: "ai_detection",
      accessories: "accessory_library",
      pipeline: "training_pipeline",
      trainingLibrary: "model_library",
      rules: "system_settings",
      userManagement: "user_management"
    } as Record<string, string>
  )[view];
}

import { AlertTriangle, Loader2 } from "lucide-react";
import { ApiError } from "../api/client";

export function LoadingState({ label = "加载中" }: { label?: string }) {
  return (
    <div className="state-panel">
      <Loader2 className="spin" size={20} aria-hidden="true" />
      <strong>{label}</strong>
    </div>
  );
}

export function ErrorState({ error, action }: { error: unknown; action?: React.ReactNode }) {
  const message = error instanceof ApiError || error instanceof Error ? error.message : "请求失败";
  return (
    <div className="state-panel error">
      <AlertTriangle size={20} aria-hidden="true" />
      <strong>{message}</strong>
      {action}
    </div>
  );
}

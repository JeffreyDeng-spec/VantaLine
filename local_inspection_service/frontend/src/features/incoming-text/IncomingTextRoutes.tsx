import { useQuery } from "@tanstack/react-query";
import { Navigate, useParams } from "react-router-dom";
import { getPipeline, queryKeys } from "../../api/queries";
import { hasPermission } from "../../app/permissions";
import { useAuth } from "../auth/auth-context";
import { DetectionWorkbenchPage } from "../detection/DetectionWorkbenchPage";
import { TaskDetailPage } from "../tasks/TaskDetailPage";
import { IncomingTextInspectionPage } from "./IncomingTextInspectionPage";
import { IncomingTextTaskPage } from "./IncomingTextTaskPage";

function sourceTaskId(routeTaskId: string) {
  const decoded = decodeURIComponent(routeTaskId || "");
  return decoded.startsWith("pipeline:") ? decoded.slice("pipeline:".length) : decoded;
}

function useRoutePipelineTask() {
  const auth = useAuth();
  const { taskId = "" } = useParams();
  const decodedTaskId = decodeURIComponent(taskId || "");
  const isPipelineRoute = decodedTaskId.startsWith("pipeline:");
  const pipelineQuery = useQuery({
    queryKey: queryKeys.pipeline(auth.dataUserId),
    queryFn: () => getPipeline(auth),
    enabled: Boolean(taskId) && isPipelineRoute
  });
  return { auth, pipelineQuery, isPipelineRoute, task: (pipelineQuery.data?.items || []).find((item) => item.id === sourceTaskId(taskId)) };
}

export function TaskDetailRoute() {
  const { auth, pipelineQuery, isPipelineRoute, task } = useRoutePipelineTask();
  if (!isPipelineRoute) {
    if (!hasPermission(auth.user, "model_library")) return <Navigate to="/" replace />;
    return <TaskDetailPage />;
  }
  if (pipelineQuery.isLoading) return <section className="view active incoming-text-loading">正在载入任务…</section>;
  if (task?.task_kind === "incoming_material_text") {
    if (hasPermission(auth.user, "incoming_material_config")) return <IncomingTextTaskPage task={task} />;
    if (hasPermission(auth.user, "inspection")) return <Navigate to={`/tasks/${encodeURIComponent(`pipeline:${task.id}`)}/inspect`} replace />;
    return <Navigate to="/" replace />;
  }
  if (!hasPermission(auth.user, "model_library")) return <Navigate to="/" replace />;
  return <TaskDetailPage />;
}

export function TaskInspectionRoute() {
  const { auth, pipelineQuery, isPipelineRoute, task } = useRoutePipelineTask();
  if (!hasPermission(auth.user, "inspection")) return <Navigate to="/" replace />;
  if (!isPipelineRoute) return <DetectionWorkbenchPage mode="inspect" />;
  if (pipelineQuery.isLoading) return <section className="view active incoming-text-loading">正在载入检验任务…</section>;
  if (pipelineQuery.isError || !task) return <section className="view active"><div className="empty-panel"><strong>任务不存在或没有访问权限</strong></div></section>;
  if (task?.task_kind === "incoming_material_text") return <IncomingTextInspectionPage task={task} />;
  return <DetectionWorkbenchPage mode="inspect" />;
}

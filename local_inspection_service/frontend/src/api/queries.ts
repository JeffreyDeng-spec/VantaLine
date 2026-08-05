import { apiClient, withAuthScope } from "./client";
import type {
  AgentConfigResponse,
  AiAutoOptimizeStatus,
  AiConfigResponse,
  ApiCostLedgerResponse,
  AiTasksResponse,
  AccessoriesResponse,
  AccessoryCandidateResponse,
  AccessoryDetailResponse,
  AccessoryMutationResponse,
  AccessoryTextCropPayload,
  ApiRequestOptions,
  AuthStatusResponse,
  ConfigSummaryResponse,
  DataAnalysisRecordResponse,
  DataAnalysisRecordsResponse,
  DetectionResult,
  AgentRecommendationResponse,
  PipelineAccessoryMutationResponse,
  PipelineResponse,
  PipelineTask,
  PipelineTaskMutationResponse,
  PipelineTaskPayload,
  PlcConfig,
  PlcConfigResponse,
  RuleConfigPayload,
  ServiceStatusResponse,
  TaskNavigationPreferences,
  TaskRuleConfig,
  TaskRuleConfigPayload,
  TrainingDatasetDetailResponse,
  TrainingResourceMutationResponse,
  TrainingResourcesResponse,
  UserMutationResponse,
  UserPasswordResetResponse,
  UsersResponse
} from "./types";
import type { AuthContextValue } from "../features/auth/auth-context";

export const queryKeys = {
  authStatus: ["auth", "status"] as const,
  users: ["auth", "users"] as const,
  serviceStatus: (scope: string) => ["service", "status", scope] as const,
  configSummary: (scope: string) => ["config", "summary", scope] as const,
  agentConfig: ["agent", "config"] as const,
  aiConfig: ["ai", "config"] as const,
  plcConfig: ["plc", "config"] as const,
  apiCostLedger: ["admin", "apiCostLedger"] as const,
  aiTasks: (scope: string) => ["ai", "tasks", scope] as const,
  aiAutoOptimize: (scope: string, taskId: string) => ["ai", "autoOptimize", scope, taskId] as const,
  accessories: (scope: string) => ["accessories", scope] as const,
  accessoryDetail: (accessoryId: string) => ["accessories", "detail", accessoryId] as const,
  accessoryCandidate: (candidateId: string) => ["accessories", "candidate", candidateId] as const,
  trainingResources: (scope: string) => ["training", "resources", scope] as const,
  trainingDatasetDetail: (datasetId: string) => ["training", "dataset", datasetId] as const,
  pipeline: (scope: string) => ["pipeline", "tasks", scope] as const,
  taskNavigationPreferences: (userId: string) => ["user", "preferences", "tasks", userId] as const,
  dataAnalysisRecords: (scope: string, taskId: string) => ["dataAnalysis", "records", scope, taskId] as const,
  dataAnalysisRecord: (recordId: string) => ["dataAnalysis", "record", recordId] as const
};

export function getAuthStatus() {
  return apiClient.get<AuthStatusResponse>("/api/auth/status");
}

export function getUsers() {
  return apiClient.get<UsersResponse>("/api/auth/users");
}

export function getTaskNavigationPreferences() {
  return apiClient.get<TaskNavigationPreferences>("/api/user/preferences/tasks");
}

export function saveTaskNavigationPreferences(payload: Pick<TaskNavigationPreferences, "pinned_task_ids" | "archived_task_ids">) {
  return apiClient.post<TaskNavigationPreferences>("/api/user/preferences/tasks", payload);
}

export function getServiceStatus(auth: AuthContextValue) {
  return apiClient.get<ServiceStatusResponse>(withAuthScope("/api/status", auth.user, auth.dataUserId));
}

export function warmupYoloModel(modelId: string) {
  return apiClient.post<ServiceStatusResponse["yolo_warmup"]>("/api/models/warmup", { model_id: modelId });
}

export function getConfigSummary(auth: AuthContextValue) {
  return apiClient.get<ConfigSummaryResponse>(withAuthScope("/api/config/summary", auth.user, auth.dataUserId));
}

export function updateRules(payload: RuleConfigPayload) {
  return apiClient.post<{ status: string; rule: ConfigSummaryResponse }>("/api/config/rules", payload);
}

export function updateTaskRules(taskId: string, payload: TaskRuleConfigPayload) {
  return apiClient.post<{ status: string; task_id: string; rule: TaskRuleConfig }>(
    `/api/config/task-rules/${encodeURIComponent(taskId)}`,
    payload
  );
}

export function getAgentConfig() {
  return apiClient.get<AgentConfigResponse>("/api/agent/config");
}

export function saveAgentConfig(payload: Partial<AgentConfigResponse> & { api_key?: string; api_key_env?: string; active_key_id?: string }) {
  return apiClient.post<AgentConfigResponse>("/api/agent/config", payload);
}

export function testAgentConfig() {
  return apiClient.post<AgentConfigResponse>("/api/agent/config/test");
}

export function getAiConfig() {
  return apiClient.get<AiConfigResponse>("/api/ai/config");
}

export function getPlcConfig() {
  return apiClient.get<PlcConfigResponse>("/api/plc/config");
}

export function savePlcConfig(payload: Partial<PlcConfig>) {
  return apiClient.post<PlcConfigResponse>("/api/plc/config", payload);
}

export function getApiCostLedger() {
  return apiClient.get<ApiCostLedgerResponse>("/api/admin/api-cost-ledger");
}

export function getAiTasks(auth: AuthContextValue) {
  return apiClient.get<AiTasksResponse>(withAuthScope("/api/ai/tasks", auth.user, auth.dataUserId));
}

export function getAiTaskAutoOptimize(auth: AuthContextValue, taskId: string) {
  return apiClient.get<AiAutoOptimizeStatus>(
    withAuthScope(`/api/ai/tasks/${encodeURIComponent(taskId)}/auto-optimize`, auth.user, auth.dataUserId)
  );
}

export function updateAiTaskAutoOptimize(
  taskId: string,
  payload: {
    enabled?: boolean;
    samples_per_real_image?: number;
    negative_samples_per_real_image?: number;
    training_epochs?: number;
    training_image_size?: number;
    min_trainable_samples?: number;
    min_positive_samples?: number;
    min_negative_samples?: number;
    max_label_jobs_per_cycle?: number;
    mask_compare_min_score?: number;
    shadow_min_samples?: number;
    shadow_min_agreement?: number;
    auto_promote?: boolean;
  }
) {
  return apiClient.patch<AiAutoOptimizeStatus>(`/api/ai/tasks/${encodeURIComponent(taskId)}/auto-optimize`, payload);
}

export function uploadAiTaskEnvironmentBackground(taskId: string, form: FormData, options?: ApiRequestOptions) {
  return apiClient.upload<AiAutoOptimizeStatus>(`/api/ai/tasks/${encodeURIComponent(taskId)}/environment-background`, form, options);
}

export function deleteAiTaskAutoOptimizeSample(taskId: string, sampleId: string) {
  return apiClient.delete<AiAutoOptimizeStatus>(
    `/api/ai/tasks/${encodeURIComponent(taskId)}/auto-optimize/samples/${encodeURIComponent(sampleId)}`
  );
}

export function retryAiTaskAutoOptimizeSample(taskId: string, sampleId: string) {
  return apiClient.post<AiAutoOptimizeStatus>(
    `/api/ai/tasks/${encodeURIComponent(taskId)}/auto-optimize/samples/${encodeURIComponent(sampleId)}/retry`
  );
}

export function approveAiTaskAutoOptimizeSample(taskId: string, sampleId: string, mode: "sprite" | "bbox_only" = "sprite") {
  return apiClient.post<AiAutoOptimizeStatus>(
    `/api/ai/tasks/${encodeURIComponent(taskId)}/auto-optimize/samples/${encodeURIComponent(sampleId)}/approve`,
    { mode }
  );
}

export function saveAiConfig(
  payload: Partial<AiConfigResponse> & {
    api_key?: string;
    image_provider?: string;
    image_model?: string;
    image_base_url?: string;
    image_timeout_seconds?: number;
    image_api_key?: string;
    image_active_key_id?: string;
    image_api_key_env?: string;
  }
) {
  return apiClient.post<AiConfigResponse>("/api/ai/config", payload);
}

export function deleteActiveAiKey() {
  return apiClient.delete<AiConfigResponse>("/api/ai/config/key");
}

export function getTrainingResources(auth: AuthContextValue) {
  return apiClient.get<TrainingResourcesResponse>(
    withAuthScope("/api/training/resources", auth.user, auth.dataUserId)
  );
}

export function getPipeline(auth: AuthContextValue) {
  return apiClient.get<PipelineResponse>(withAuthScope("/api/pipeline/tasks", auth.user, auth.dataUserId));
}

export function createPipelineTask(payload: PipelineTaskPayload, auth?: AuthContextValue) {
  return apiClient.post<PipelineTask>(
    auth ? withAuthScope("/api/pipeline/tasks", auth.user, auth.dataUserId) : "/api/pipeline/tasks",
    payload
  );
}

export function updatePipelineTask(taskId: string, payload: PipelineTaskPayload) {
  return apiClient.patch<PipelineTask>(`/api/pipeline/tasks/${encodeURIComponent(taskId)}`, payload);
}

export function deletePipelineTask(taskId: string) {
  return apiClient.delete<PipelineTaskMutationResponse>(`/api/pipeline/tasks/${encodeURIComponent(taskId)}`);
}

export function advancePipelineTask(taskId: string) {
  return apiClient.post<PipelineTask>(`/api/pipeline/tasks/${encodeURIComponent(taskId)}/advance`);
}

export function pausePipelineTask(taskId: string) {
  return apiClient.post<PipelineTask>(`/api/pipeline/tasks/${encodeURIComponent(taskId)}/cancel-advance`);
}

export function sendPipelineAgentFeedback(
  taskId: string,
  payload: { action: string; decision?: string; message?: string; updated_plan?: Record<string, unknown> }
) {
  return apiClient.post<PipelineTask>(`/api/pipeline/tasks/${encodeURIComponent(taskId)}/agent-feedback`, payload);
}

export function sendPipelineAgentChat(taskId: string, message: string) {
  return apiClient.post<PipelineTask>(`/api/pipeline/tasks/${encodeURIComponent(taskId)}/chat`, { message });
}

export function addPipelineAccessory(accessoryId: string) {
  return apiClient.post<PipelineAccessoryMutationResponse>(
    `/api/pipeline/accessories/${encodeURIComponent(accessoryId)}`
  );
}

export function removePipelineAccessory(accessoryId: string) {
  return apiClient.delete<PipelineAccessoryMutationResponse>(
    `/api/pipeline/accessories/${encodeURIComponent(accessoryId)}`
  );
}

export function getAgentRecommendation(payload: { stage: "samples" | "training"; accessory_ids: string[]; sample_count?: number | null }) {
  return apiClient.post<AgentRecommendationResponse>("/api/agent/recommend", payload);
}

export function getAccessories(auth: AuthContextValue) {
  return apiClient.get<AccessoriesResponse>(withAuthScope("/api/accessories", auth.user, auth.dataUserId));
}

export function getAccessoryDetail(accessoryId: string) {
  return apiClient.get<AccessoryDetailResponse>(`/api/accessories/${encodeURIComponent(accessoryId)}/detail`);
}

export function getAccessoryCandidate(candidateId: string) {
  return apiClient.get<AccessoryCandidateResponse>(`/api/accessories/candidates/${encodeURIComponent(candidateId)}`);
}

export function previewAccessory(form: FormData) {
  return apiClient.upload<AccessoryCandidateResponse>("/api/accessories/preview", form);
}

export function createAccessory(form: FormData) {
  return apiClient.upload<AccessoryMutationResponse>("/api/accessories", form);
}

export function confirmAccessory(candidateId: string) {
  return apiClient.post<AccessoryMutationResponse>(`/api/accessories/confirm/${encodeURIComponent(candidateId)}`);
}

export function addAccessoryFiles(accessoryId: string, form: FormData) {
  return apiClient.upload<AccessoryMutationResponse>(`/api/accessories/${encodeURIComponent(accessoryId)}/files`, form);
}

export function cropAccessoryTextImage(accessoryId: string, payload: AccessoryTextCropPayload) {
  return apiClient.post<AccessoryMutationResponse>(`/api/accessories/${encodeURIComponent(accessoryId)}/text-crop`, payload);
}

export function setAccessoryAiReference(accessoryId: string, sourcePath: string) {
  return apiClient.post<AccessoryMutationResponse>(`/api/accessories/${encodeURIComponent(accessoryId)}/ai-reference`, {
    source_path: sourcePath
  });
}

export function deleteAccessoryFile(accessoryId: string, sourcePath: string) {
  return apiClient.delete<AccessoryMutationResponse>(`/api/accessories/${encodeURIComponent(accessoryId)}/files`, {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_path: sourcePath })
  });
}

export function deleteAccessory(accessoryId: string) {
  return apiClient.delete<AccessoryMutationResponse>(`/api/accessories/${encodeURIComponent(accessoryId)}`);
}

export function setAccessoryRoute(accessoryId: string, payload: { route: string; apply: boolean }) {
  return apiClient.post<AccessoryMutationResponse>(`/api/accessories/${encodeURIComponent(accessoryId)}/route`, payload);
}

export function analyzeImage(form: FormData, options?: ApiRequestOptions) {
  return apiClient.upload<DetectionResult>("/api/analyze/image", form, options);
}

export function analyzeVideo(form: FormData, options?: ApiRequestOptions) {
  return apiClient.upload<DetectionResult>("/api/analyze/video", form, options);
}

export function getDataAnalysisRecords(
  auth: AuthContextValue,
  params: { taskId?: string; limit?: number; offset?: number } = {}
) {
  const query = new URLSearchParams({
    limit: String(params.limit ?? 200),
    offset: String(params.offset ?? 0)
  });
  if (params.taskId) query.set("task_id", params.taskId);
  return apiClient.get<DataAnalysisRecordsResponse>(
    withAuthScope(`/api/data-analysis/records?${query.toString()}`, auth.user, auth.dataUserId)
  );
}

export function getDataAnalysisRecord(recordId: string) {
  return apiClient.get<DataAnalysisRecordResponse>(
    `/api/data-analysis/records/${encodeURIComponent(recordId)}`
  );
}

export function getTrainingDatasetDetail(datasetId: string) {
  return apiClient.get<TrainingDatasetDetailResponse>(
    `/api/training/resources/datasets/${encodeURIComponent(datasetId)}/detail`
  );
}

export function updateTrainingDataset(datasetId: string, payload: { display_name?: string; note?: string }) {
  return apiClient.patch<TrainingResourceMutationResponse>(
    `/api/training/resources/datasets/${encodeURIComponent(datasetId)}`,
    payload
  );
}

export function deleteTrainingDataset(datasetId: string) {
  return apiClient.delete<TrainingResourceMutationResponse>(
    `/api/training/resources/datasets/${encodeURIComponent(datasetId)}`
  );
}

export function deleteTrainingDatasetSample(datasetId: string, sampleName: string) {
  return apiClient.delete<TrainingResourceMutationResponse>(
    `/api/training/resources/datasets/${encodeURIComponent(datasetId)}/samples/${encodeURIComponent(sampleName)}`
  );
}

export function updateTrainingModel(runId: string, payload: { display_name?: string; note?: string }) {
  return apiClient.patch<TrainingResourceMutationResponse>(
    `/api/training/resources/models/${encodeURIComponent(runId)}`,
    payload
  );
}

export function deleteTrainingModel(runId: string) {
  return apiClient.delete<TrainingResourceMutationResponse>(
    `/api/training/resources/models/${encodeURIComponent(runId)}`
  );
}

export function updateTrainingTask(jobId: string, payload: { label?: string; note?: string }) {
  return apiClient.patch<Record<string, unknown>>(`/api/training/tasks/${encodeURIComponent(jobId)}`, payload);
}

export function deleteAiTask(taskId: string) {
  return apiClient.delete<Record<string, unknown>>(`/api/ai/tasks/${encodeURIComponent(taskId)}`);
}

export function createUser(payload: {
  username: string;
  display_name?: string;
  password: string;
  role: string;
  permissions: string[];
}) {
  return apiClient.post<UserMutationResponse>("/api/auth/users", payload);
}

export function updateUser(
  userId: string,
  payload: {
    display_name?: string;
    role?: string;
    permissions?: string[];
    active?: boolean;
  }
) {
  return apiClient.patch<UserMutationResponse>(`/api/auth/users/${encodeURIComponent(userId)}`, payload);
}

export function resetUserPassword(
  userId: string,
  payload: {
    password?: string;
    generate?: boolean;
    revoke_sessions?: boolean;
  }
) {
  return apiClient.post<UserPasswordResetResponse>(
    `/api/auth/users/${encodeURIComponent(userId)}/password`,
    payload
  );
}

export function deleteUser(userId: string) {
  return apiClient.delete<UserMutationResponse>(`/api/auth/users/${encodeURIComponent(userId)}`);
}

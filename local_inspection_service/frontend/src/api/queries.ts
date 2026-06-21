import { apiClient, withAuthScope } from "./client";
import type {
  AgentConfigResponse,
  AiConfigResponse,
  AiTasksResponse,
  AccessoriesResponse,
  AccessoryCandidateResponse,
  AccessoryDetailResponse,
  AccessoryMutationResponse,
  AccessoryTextCropPayload,
  AuthStatusResponse,
  ConfigSummaryResponse,
  DataAnalysisLocateRequest,
  DataAnalysisLocateResponse,
  DataAnalysisRecordResponse,
  DataAnalysisRecordsResponse,
  DetectionResult,
  LabelSheetMatchResult,
  LabelSheetReferencesResponse,
  LocateAccessoriesResponse,
  LocateConfigResponse,
  LocateInspectResult,
  AgentRecommendationResponse,
  PipelineAccessoryMutationResponse,
  PipelineResponse,
  PipelineTask,
  PipelineTaskMutationResponse,
  PipelineTaskPayload,
  RuleConfigPayload,
  ServiceStatusResponse,
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
  aiTasks: (scope: string) => ["ai", "tasks", scope] as const,
  accessories: (scope: string) => ["accessories", scope] as const,
  accessoryDetail: (accessoryId: string) => ["accessories", "detail", accessoryId] as const,
  accessoryCandidate: (candidateId: string) => ["accessories", "candidate", candidateId] as const,
  trainingResources: (scope: string) => ["training", "resources", scope] as const,
  trainingDatasetDetail: (datasetId: string) => ["training", "dataset", datasetId] as const,
  pipeline: (scope: string) => ["pipeline", "tasks", scope] as const,
  labelSheetReferences: (scope: string) => ["labelSheet", "references", scope] as const,
  locateConfig: ["locateAnything", "config"] as const,
  locateStatus: (endpointUrl: string) => ["locateAnything", "status", endpointUrl] as const,
  locateAccessories: (scope: string) => ["locateAnything", "accessories", scope] as const,
  dataAnalysisRecords: (scope: string, taskId: string) => ["dataAnalysis", "records", scope, taskId] as const,
  dataAnalysisRecord: (recordId: string) => ["dataAnalysis", "record", recordId] as const
};

export function getAuthStatus() {
  return apiClient.get<AuthStatusResponse>("/api/auth/status");
}

export function getUsers() {
  return apiClient.get<UsersResponse>("/api/auth/users");
}

export function getServiceStatus(auth: AuthContextValue) {
  return apiClient.get<ServiceStatusResponse>(withAuthScope("/api/status", auth.user, auth.dataUserId));
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

export function saveAgentConfig(payload: Partial<AgentConfigResponse> & { api_key?: string }) {
  return apiClient.post<AgentConfigResponse>("/api/agent/config", payload);
}

export function testAgentConfig() {
  return apiClient.post<AgentConfigResponse>("/api/agent/config/test");
}

export function getAiConfig() {
  return apiClient.get<AiConfigResponse>("/api/ai/config");
}

export function getAiTasks(auth: AuthContextValue) {
  return apiClient.get<AiTasksResponse>(withAuthScope("/api/ai/tasks", auth.user, auth.dataUserId));
}

export function saveAiConfig(payload: Partial<AiConfigResponse> & { api_key?: string }) {
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

export function createPipelineTask(payload: PipelineTaskPayload) {
  return apiClient.post<PipelineTask>("/api/pipeline/tasks", payload);
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

export function analyzeImage(form: FormData) {
  return apiClient.upload<DetectionResult>("/api/analyze/image", form);
}

export function analyzeVideo(form: FormData) {
  return apiClient.upload<DetectionResult>("/api/analyze/video", form);
}

export function getLabelSheetReferences(auth: AuthContextValue) {
  return apiClient.get<LabelSheetReferencesResponse>(
    withAuthScope("/api/label-sheets/references", auth.user, auth.dataUserId)
  );
}

export function addLabelSheetReferences(form: FormData) {
  return apiClient.upload<LabelSheetReferencesResponse>("/api/label-sheets/references", form);
}

export function matchLabelSheet(form: FormData) {
  return apiClient.upload<LabelSheetMatchResult>("/api/label-sheets/match", form);
}

export function getLocateConfig() {
  return apiClient.get<LocateConfigResponse>("/api/locateanything/config");
}

export function saveLocateConfig(payload: Partial<LocateConfigResponse>) {
  return apiClient.post<LocateConfigResponse>("/api/locateanything/config", payload);
}

export function getLocateStatus(endpointUrl = "") {
  const suffix = endpointUrl ? `?endpoint_url=${encodeURIComponent(endpointUrl)}` : "";
  return apiClient.get<LocateConfigResponse>(`/api/locateanything/status${suffix}`);
}

export function startLocateRuntime() {
  return apiClient.post<LocateConfigResponse>("/api/locateanything/runtime/start");
}

export function getLocateAccessories(auth: AuthContextValue) {
  return apiClient.get<LocateAccessoriesResponse>(
    withAuthScope("/api/locateanything/accessories", auth.user, auth.dataUserId)
  );
}

export function inspectLocateAnything(form: FormData) {
  return apiClient.upload<LocateInspectResult>("/api/locateanything/inspect", form);
}

export function locateAnythingPrompt(form: FormData) {
  return apiClient.upload<LocateInspectResult>("/api/locateanything/locate", form);
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

export function locateDataAnalysisRecord(recordId: string, payload: DataAnalysisLocateRequest = {}) {
  return apiClient.post<DataAnalysisLocateResponse>(
    `/api/data-analysis/records/${encodeURIComponent(recordId)}/locate`,
    payload
  );
}

export function locateDataAnalysisRecords(payload: DataAnalysisLocateRequest) {
  return apiClient.post<DataAnalysisLocateResponse>("/api/data-analysis/locate", payload);
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

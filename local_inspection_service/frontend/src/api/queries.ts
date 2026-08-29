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
  PlcSyncStatus,
  PlcWebSerialAttempt,
  PlcWebSerialDiagnosticPlan,
  PlcWebSerialConfig,
  PlcWebSerialOperation,
  PlcWorkstationLease,
  PlcWorkstationResponse,
  RuleConfigPayload,
  ServiceStatusResponse,
  TaskNavigationPreferences,
  TaskRuleConfig,
  TaskRuleConfigPayload,
  TrainingDatasetDetailResponse,
  TrainingResourceMutationResponse,
  TrainingResourcesResponse,
  IncomingTextInspection,
  IncomingTextInspectorsResponse,
  IncomingTextInspectionsResponse,
  TextCompareBetaResult,
  TextInspectionAsset,
  TextInspectionStandard,
  TextInspectionStandardsResponse,
  IncomingTextReference,
  IncomingTextTaskResponse,
  IncomingTextFieldRule,
  LabelSheetMatchResult,
  LabelSheetReferencesResponse,
  LocateConfigResponse,
  LocateInspectResult,
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
  plcWorkstation: ["plc", "workstation"] as const,
  plcWorkstations: ["plc", "workstations"] as const,
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
  dataAnalysisRecord: (recordId: string) => ["dataAnalysis", "record", recordId] as const,
  incomingTextTask: (taskId: string) => ["incomingText", "task", taskId] as const,
  incomingTextInspectors: ["incomingText", "inspectors"] as const,
  incomingTextInspections: (scope: string, taskId = "") => ["incomingText", "inspections", scope, taskId] as const,
  locateConfig: ["locate", "config"] as const,
  locateStatus: (endpoint = "") => ["locate", "status", endpoint] as const,
  locateAccessories: (scope: string) => ["locate", "accessories", scope] as const,
  labelSheetReferences: (scope: string) => ["labelSheets", "references", scope] as const,
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

export function getPlcWorkstation() {
  return apiClient.get<PlcWorkstationResponse>("/api/plc/workstation");
}

export function listPlcWorkstations() {
  return apiClient.get<{ items: Array<{ id: string; name: string; status: string; profile_verified: boolean; updated_at: number }> }>("/api/plc/workstations");
}

export function pairPlcWorkstation(payload: { name: string; station_id?: string }) {
  return apiClient.post<PlcWorkstationResponse>("/api/plc/workstations/pair", payload);
}

export function savePlcWorkstationConfig(payload: PlcWebSerialConfig) {
  return apiClient.post<PlcWorkstationResponse>("/api/plc/workstation/config", payload);
}

export function verifyPlcWorkstationProfile(verified: boolean) {
  return apiClient.post<PlcWorkstationResponse>("/api/plc/workstation/profile-verification", { verified });
}

export function claimPlcWorkstationConnection(payload: {
  client_instance_id: string;
  model_id: string;
  bundle_version: string;
}) {
  return apiClient.post<PlcWorkstationLease>("/api/plc/workstation/connect", payload);
}

export function activatePlcWorkstationConnection(payload: {
  session_id: string;
  lease_epoch: number;
  usb_vendor_id?: number;
  usb_product_id?: number;
}) {
  return apiClient.post<PlcWorkstationLease>("/api/plc/workstation/connect/activate", payload);
}

export function heartbeatPlcWorkstationConnection(sessionId: string, leaseEpoch: number) {
  return apiClient.post<PlcWorkstationLease>("/api/plc/workstation/lease/heartbeat", {
    session_id: sessionId,
    lease_epoch: leaseEpoch
  });
}

export function rebindPlcWorkstationModel(sessionId: string, leaseEpoch: number, modelId: string) {
  return apiClient.post<PlcWorkstationLease>("/api/plc/workstation/lease/rebind-model", {
    session_id: sessionId,
    lease_epoch: leaseEpoch,
    model_id: modelId
  });
}

export function disconnectPlcWorkstationConnection(sessionId: string, leaseEpoch: number) {
  return apiClient.post<PlcWorkstationLease>("/api/plc/workstation/lease/disconnect", {
    session_id: sessionId,
    lease_epoch: leaseEpoch
  });
}

export function declarePlcWebSerialAttempt(
  dispatchId: string,
  payload: { session_id: string; lease_epoch: number; config_generation: number }
) {
  return apiClient.post<PlcWebSerialAttempt>(
    `/api/plc/workstation/dispatches/${encodeURIComponent(dispatchId)}/attempt`,
    payload
  );
}

export function sendPlcWebSerialReceipt(
  dispatchId: string,
  payload: {
    session_id: string;
    lease_epoch: number;
    attempt_token: string;
    outcome: string;
    operations: PlcWebSerialOperation[];
  }
) {
  return apiClient.post<PlcSyncStatus>(
    `/api/plc/workstation/dispatches/${encodeURIComponent(dispatchId)}/receipt`,
    payload
  );
}

export function getPlcWebSerialDiagnosticPlan(payload: {
  session_id: string;
  lease_epoch: number;
  config_generation: number;
}) {
  return apiClient.post<PlcWebSerialDiagnosticPlan>("/api/plc/workstation/diagnostic-plan", payload);
}

export function finishPlcWebSerialDiagnostic(payload: {
  session_id: string;
  lease_epoch: number;
  diagnostic_id: string;
  attempt_token: string;
  outcome: "success" | "failed" | "uncertain";
}) {
  return apiClient.post<{ released: boolean; diagnostic_id: string }>("/api/plc/workstation/diagnostic-receipt", payload);
}

export function confirmPlcWebSerialDiagnostic(payload: {
  session_id: string;
  lease_epoch: number;
  diagnostic_id: string;
  attempt_token: string;
}) {
  return apiClient.post<{ confirmed: boolean; diagnostic_id: string }>("/api/plc/workstation/diagnostic-confirm", payload);
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

export function getIncomingTextTask(taskId: string) {
  return apiClient.get<IncomingTextTaskResponse>(`/api/incoming-text/tasks/${encodeURIComponent(taskId)}`);
}

export function getIncomingTextInspectors() {
  return apiClient.get<IncomingTextInspectorsResponse>("/api/incoming-text/inspectors");
}

export function uploadIncomingTextReference(taskId: string, form: FormData) {
  return apiClient.upload<IncomingTextReference>(`/api/incoming-text/tasks/${encodeURIComponent(taskId)}/references`, form);
}

export function saveIncomingTextRules(referenceId: string, rules: IncomingTextFieldRule[], activate: boolean) {
  return apiClient.put<IncomingTextReference>(`/api/incoming-text/references/${encodeURIComponent(referenceId)}/rules`, { rules, activate });
}

export function cloneIncomingTextReference(referenceId: string, versionLabel: string) {
  const form = new FormData();
  form.set("version_label", versionLabel);
  return apiClient.upload<IncomingTextReference>(`/api/incoming-text/references/${encodeURIComponent(referenceId)}/clone`, form);
}

export function inspectIncomingText(taskId: string, form: FormData, options?: ApiRequestOptions) {
  return apiClient.upload<IncomingTextInspection>(`/api/incoming-text/tasks/${encodeURIComponent(taskId)}/inspect`, form, options);
}

export function reviewIncomingTextInspection(inspectionId: string, decision: "RELEASED" | "REJECTED", reason: string) {
  return apiClient.post<IncomingTextInspection>(`/api/incoming-text/inspections/${encodeURIComponent(inspectionId)}/review`, { decision, reason });
}

export function getIncomingTextInspections(auth: AuthContextValue, taskId = "") {
  const params = new URLSearchParams();
  if (taskId) params.set("task_id", taskId);
  const path = `/api/incoming-text/inspections${params.size ? `?${params}` : ""}`;
  return apiClient.get<IncomingTextInspectionsResponse>(withAuthScope(path, auth.user, auth.dataUserId));
}

export function analyzeTextCompareBeta(form: FormData, options?: ApiRequestOptions) {
  return apiClient.upload<TextCompareBetaResult>("/api/text-compare-beta/analyze", form, options);
}

export function listTextInspectionStandards() {
  return apiClient.get<TextInspectionStandardsResponse>("/api/text-inspection/standards");
}

export function getTextInspectionStandard(id: string) {
  return apiClient.get<TextInspectionStandard>(`/api/text-inspection/standards/${encodeURIComponent(id)}`);
}

export function importTextInspectionStandard(form: FormData) {
  return apiClient.upload<TextInspectionStandard>("/api/text-inspection/standards/import", form);
}

export function patchTextInspectionAsset(standardId: string, assetId: string, action: "restore" | "exclude" | "confirm") {
  return apiClient.patch<TextInspectionAsset>(`/api/text-inspection/standards/${encodeURIComponent(standardId)}/assets/${encodeURIComponent(assetId)}`, { action });
}

export function confirmTextInspectionStandard(id: string) {
  return apiClient.post<TextInspectionStandard>(`/api/text-inspection/standards/${encodeURIComponent(id)}/confirm`);
}

export function compareTextInspectionLabel(form: FormData, options?: ApiRequestOptions) {
  return apiClient.upload<TextCompareBetaResult>("/api/text-inspection/label/compare", form, options);
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

export function getLocateConfig() {
  return apiClient.get<LocateConfigResponse>("/api/locateanything/config");
}

export function saveLocateConfig(payload: Record<string, unknown>) {
  return apiClient.post<LocateConfigResponse>("/api/locateanything/config", payload);
}

export function getLocateStatus(endpointUrl = "") {
  const suffix = endpointUrl ? `?endpoint_url=${encodeURIComponent(endpointUrl)}` : "";
  return apiClient.get<LocateConfigResponse>(`/api/locateanything/status${suffix}`);
}

export function startLocateRuntime() {
  return apiClient.post<LocateConfigResponse>("/api/locateanything/runtime/start", {});
}

export function getLocateAccessories(auth: AuthContextValue) {
  return apiClient.get<{ items: import("./types").LocateSourceItem[] }>(
    withAuthScope("/api/locateanything/accessories", auth.user, auth.dataUserId)
  );
}

export function inspectLocateAnything(form: FormData) {
  return apiClient.upload<LocateInspectResult>("/api/locateanything/inspect", form);
}

export function locateAnythingPrompt(form: FormData) {
  return apiClient.upload<LocateInspectResult>("/api/locateanything/locate", form);
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

export function analyzeCamera(form: FormData, options?: ApiRequestOptions) {
  return apiClient.upload<DetectionResult>("/api/analyze/camera", form, options);
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

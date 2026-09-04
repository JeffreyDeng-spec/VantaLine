export type UserRole = "admin" | "user" | string;

export interface AuthUser {
  id: string;
  username: string;
  display_name?: string;
  role: UserRole;
  permissions?: string[];
  active?: boolean;
  created_at?: number;
  updated_at?: number;
}

export interface AuthStatusResponse {
  authenticated: boolean;
  setup_required: boolean;
  user: AuthUser | null;
  features: Record<string, string>;
  default_user_permissions: string[];
  legacy_owner_id: string;
}

export interface AuthMutationResponse {
  status: string;
  user: AuthUser;
  features: Record<string, string>;
}

export interface UsersResponse {
  users: AuthUser[];
  features: Record<string, string>;
  default_user_permissions: string[];
}

export interface UserMutationResponse extends UsersResponse {
  status: string;
  user?: AuthUser;
  deleted_user_id?: string;
}

export interface UserPasswordResetResponse extends UserMutationResponse {
  temporary_password?: string;
  revoked_sessions?: number;
}

export interface TaskNavigationPreferences {
  pinned_task_ids: string[];
  archived_task_ids: string[];
  updated_at?: number;
  exists?: boolean;
}

export interface ConfigSummaryResponse {
  confidence_threshold?: number;
  required_classes?: number[];
  min_counts?: Record<string, number>;
  task_rules?: Record<string, TaskRuleConfig>;
  training?: Record<string, unknown>;
  video?: Record<string, unknown>;
  stream?: Record<string, unknown>;
  ocr?: Record<string, unknown>;
}

export interface RuleConfigPayload {
  confidence_threshold: number;
  required_classes: number[];
  min_counts: Record<string, number>;
}

export interface TaskRuleConfig {
  confidence_threshold: number;
  required_accessory_counts: Record<string, number>;
  updated_at?: number;
}

export interface TaskRuleConfigPayload {
  confidence_threshold: number;
  required_accessory_counts: Record<string, number>;
}

export interface StatusModel {
  id: string;
  label?: string;
  description?: string;
  exists?: boolean;
  variant?: string;
  is_ai_detection?: boolean;
  uses_ocr?: boolean;
  provider_status?: Record<string, unknown>;
  confidence_threshold?: number;
  task_id?: string;
  task_label?: string;
  task_source?: string;
  required_accessory_counts?: Record<string, number>;
  accessory_labels?: Record<string, string>;
  selected_accessory_ids?: string[];
  accessory_names?: string[];
  missing_accessory_ids?: string[];
  owner_user_id?: string;
  owner_username?: string;
}

export interface SpecializedModelTask {
  task_id: string;
  label?: string;
  accessory_names?: string[];
  accessory_labels?: Record<string, string>;
  required_accessory_counts?: Record<string, number>;
  confidence_threshold?: number;
  models?: StatusModel[];
}

export interface ServiceStatusResponse {
  service: string;
  model_exists: boolean;
  model_path?: string;
  active_model_id?: string;
  available_models?: StatusModel[];
  specialized_models?: StatusModel[];
  specialized_model_tasks?: SpecializedModelTask[];
  ai_detection_tasks?: AiDetectionLibraryTask[];
  ai_detection?: Record<string, unknown>;
  yolo_warmup?: YoloWarmupStatus;
  training_execution?: Record<string, unknown>;
  cursor_image2?: Record<string, unknown>;
  classes?: Array<{ class_id: number; name: string; label: string }>;
  rule?: {
    confidence_threshold?: number;
    required_classes?: number[];
    min_counts?: Record<string, number>;
  };
  ocr?: Record<string, unknown>;
}

export interface YoloWarmupStatus {
  enabled?: boolean;
  status?: string;
  reason?: string;
  model_ids?: string[];
  completed_model_ids?: string[];
  failed_model_ids?: Array<{ model_id?: string; error?: string }> | string[];
  loaded_model_ids?: string[];
  selected_model_id?: string;
  selected_model_ready?: boolean;
  skipped?: boolean;
  started_at?: number;
  completed_at?: number;
  error?: string;
}

export interface ModelOption {
  id: string;
  label?: string;
}

export interface AgentConfigResponse {
  enabled: boolean;
  provider: string;
  provider_label?: string;
  base_url: string;
  model: string;
  model_options?: ModelOption[];
  timeout_seconds: number;
  auto_advance_default: boolean;
  api_key_env?: string;
  api_keys?: AiKeySummary[];
  active_key_id?: string;
  api_key_masked?: string;
  has_api_key?: boolean;
  configured?: boolean;
  connection_status?: string;
  connection_message?: string;
  last_tested_at?: number;
  last_model_count?: number;
  recommendation_supported?: boolean;
  ok?: boolean;
  message?: string;
}

export interface AiKeySummary {
  id: string;
  label: string;
  masked_key: string;
  env_name?: string;
  provider?: string;
}

export interface ImageGenerationConfigResponse {
  enabled: boolean;
  configured: boolean;
  provider: string;
  provider_key?: string;
  provider_label?: string;
  model: string;
  model_options?: ModelOption[];
  timeout_seconds: number;
  api_key_env?: string;
  api_key_present?: boolean;
  key_present?: boolean;
  local_key_present?: boolean;
  api_keys?: AiKeySummary[];
  active_key_id?: string;
  key_source?: string;
  key_source_name?: string;
  masked_key?: string;
  base_url: string;
  proxy_configured?: boolean;
  proxy_url?: string;
  proxy_source_name?: string;
  status: string;
  message?: string;
}

export interface AiConfigResponse {
  enabled: boolean;
  configured: boolean;
  provider: string;
  provider_label?: string;
  model: string;
  model_options?: ModelOption[];
  timeout_seconds: number;
  api_key_env?: string;
  api_key_present?: boolean;
  key_present?: boolean;
  local_key_present?: boolean;
  api_keys?: AiKeySummary[];
  active_key_id?: string;
  key_source?: string;
  key_source_name?: string;
  masked_key?: string;
  base_url: string;
  proxy_configured?: boolean;
  proxy_url?: string;
  proxy_source_name?: string;
  status: string;
  message?: string;
  image_generation?: ImageGenerationConfigResponse;
}

export interface ApiCostSubcategory {
  label: string;
  call_count: number;
  cost_usd: number;
}

export interface ApiCostCategory {
  key: string;
  label: string;
  call_count: number;
  priced_call_count: number;
  estimated_call_count: number;
  unpriced_call_count: number;
  cost_usd: number;
  avg_cost_usd: number;
  subcategories?: ApiCostSubcategory[];
}

export interface ApiCostDailyPoint {
  date: string;
  total_cost_usd: number;
  image_generation?: number;
  structured_output?: number;
  agent?: number;
  call_count: number;
}

export interface ApiCostRecentCall {
  id: string;
  day: string;
  category: string;
  subcategory: string;
  model: string;
  cost_usd: number;
  priced: boolean;
  estimated: boolean;
}

export interface ApiCostLedgerResponse {
  currency: string;
  updated_at: number;
  pricing_source: string;
  summary: {
    total_cost_usd: number;
    known_cost_usd: number;
    estimated_cost_usd: number;
    call_count: number;
    priced_call_count: number;
    estimated_call_count: number;
    unpriced_call_count: number;
    avg_cost_per_call_usd: number;
    avg_image_generation_cost_usd: number;
    training_sample_count: number;
    avg_cost_per_training_sample_usd: number;
  };
  categories: ApiCostCategory[];
  daily: ApiCostDailyPoint[];
  recent_calls: ApiCostRecentCall[];
}

export interface TrainingDataset {
  id: string;
  kind?: string;
  display_name?: string;
  note?: string;
  path?: string;
  manifest_path?: string;
  sample_count?: number;
  created_at?: number;
  updated_at?: number;
  selected_accessory_ids?: string[];
  background_set_id?: string;
  owner_user_id?: string;
  owner_username?: string;
  samples_loaded?: boolean;
  missing_files?: boolean;
  samples?: TrainingSample[];
}

export interface TrainingModel {
  id: string;
  run_id?: string;
  task_id?: string;
  variant?: string;
  kind?: string;
  label?: string;
  note?: string;
  path?: string;
  run_dir?: string;
  exists?: boolean;
  uses_ocr?: boolean;
  created_at?: number;
  updated_at?: number;
  accessory_names?: string[];
  selected_accessory_ids?: string[];
  owner_user_id?: string;
  owner_username?: string;
}

export interface TrainingTask {
  job_id?: string;
  task_id?: string;
  action?: string;
  label?: string;
  note?: string;
  status?: string;
  sample_count?: number;
  completed_samples?: number;
  created_at?: number;
  updated_at?: number;
  current_epoch?: number;
  total_epochs?: number;
  epochs?: number;
  image_size?: number;
  progress?: number;
  generated_image_count?: number;
  manifest_path?: string;
  training_log_path?: string;
  background_set_id?: string;
  accessory_names?: string[];
  selected_accessory_ids?: string[];
  dataset?: TrainingDataset | null;
  models?: TrainingModel[];
  owner_user_id?: string;
  owner_username?: string;
}

export interface AiDetectionLibraryTask {
  id: string;
  name?: string;
  model_id?: string;
  source?: string;
  task_type?: string;
  accessory_count?: number;
  selected_accessory_ids?: string[];
  accessory_names?: string[];
  accessory_labels?: Record<string, string>;
  required_accessory_counts?: Record<string, number>;
  missing_accessory_ids?: string[];
  created_at?: number;
  updated_at?: number;
  background_set_id?: string;
  environment_background?: Record<string, unknown>;
  owner_user_id?: string;
  owner_username?: string;
}

export interface AiTasksResponse {
  status?: string;
  selected_task_id?: string;
  tasks: AiDetectionLibraryTask[];
  task?: AiDetectionLibraryTask;
  deleted_task_id?: string;
}

export interface AiAutoOptimizeStatus {
  task_id: string;
  enabled?: boolean;
  serving_mode?: string;
  active_model_id?: string;
  phase?: string;
  samples_total?: number;
  captured_samples?: number;
  pending_labels?: number;
  trainable_samples?: number;
  bbox_only_samples?: number;
  review_required_samples?: number;
  negative_samples?: number;
  generated_negative_sample_count?: number;
  projected_negative_training_samples?: number;
  negative_samples_per_real_image?: number;
  positive_derivatives_per_real_image?: number;
  usable_training_samples?: number;
  projected_positive_training_samples?: number;
  projected_training_samples?: number;
  samples_per_real_image?: number;
  background_set_id?: string;
  environment_background?: Record<string, unknown>;
  background_set?: Record<string, unknown>;
  sprite_pool_count?: number;
  sprite_pool?: Array<Record<string, unknown>>;
  synthetic_sample_count?: number;
  generated_synthetic_sample_count?: number;
  dataset_synthetic_sample_count?: number;
  rejected_samples?: number;
  candidate_model_count?: number;
  shadow_runs?: number;
  shadow_agreement?: number;
  latest_sample_at?: number;
  settings?: Record<string, unknown>;
  training_requirements?: Record<string, unknown>;
  training_parameters?: Record<string, unknown>;
  expected_production_count?: number;
  initialization?: Record<string, unknown>;
  latest_dataset?: Record<string, unknown>;
  latest_candidate_model?: Record<string, unknown>;
  samples?: AiAutoOptimizeSample[];
}

export interface AiAutoOptimizeSample {
  sample_id: string;
  record_id?: string;
  request_id?: string;
  task_id?: string;
  sample_type?: string;
  label_status?: string;
  label_reject_reason?: string;
  created_at?: number;
  updated_at?: number;
  retry_requested_at?: number;
  retried_at?: number;
  source_image?: {
    url?: string;
    path?: string;
    filename?: string;
  };
  ai_result?: {
    passed?: boolean;
    rule?: Record<string, unknown>;
    detections?: Array<Record<string, unknown>>;
    model?: Record<string, unknown>;
    provider_model?: string;
    annotated_url?: string;
    preview_url?: string;
    output_url?: string;
    request_id?: string;
  };
  candidate_accessories?: Array<Record<string, unknown>>;
  labels?: Array<Record<string, unknown>>;
  label_failures?: Array<Record<string, unknown>>;
  label_artifacts?: Record<string, unknown>;
  bbox_labels?: Array<Record<string, unknown>>;
  manual_review?: Record<string, unknown>;
  manual_approved_at?: number;
  manual_approved_by?: string;
  synthetic_status?: string;
  synthetic_count?: number;
  synthetic_samples?: Array<Record<string, unknown>>;
  synthetic_error?: string;
}

export type PipelineDetectionMethod = "yolo_ocr" | "yolo" | "ai" | string;
export type PipelineStage = "draft" | "samples" | "training" | "library" | string;

export interface PipelineTaskAccessory {
  id: string;
  name?: string;
  material_type?: string;
  count?: number;
}

export interface PipelineTask {
  id: string;
  name?: string;
  task_kind?: string;
  material_code?: string;
  material_name?: string;
  active_reference_id?: string;
  reference_version_label?: string;
  shared_with_user_ids?: string[];
  accessory_ids?: string[];
  accessory_counts?: Record<string, number>;
  accessory_names?: string[];
  accessories?: PipelineTaskAccessory[];
  detection_method?: PipelineDetectionMethod;
  optimization_route?: "yolo" | "yolo_ocr" | string;
  uses_training_flow?: boolean;
  stage?: PipelineStage;
  status?: string;
  progress?: number;
  params?: Record<string, string | number | boolean | null | undefined>;
  expected_production_count?: number;
  auto_optimize_initialization?: Record<string, unknown>;
  auto_optimize_task_id?: string;
  ai_baseline_task_id?: string;
  ai_baseline_model_id?: string;
  auto_optimize_link?: Record<string, unknown>;
  background_set_id?: string;
  environment_background?: Record<string, unknown>;
  recommended_params?: {
    stage?: string;
    params?: Record<string, string | number | boolean | null | undefined>;
    reason?: string;
    source?: string;
    signature?: string;
    created_at?: number;
  };
  auto_advance?: boolean;
  samples_task_id?: string;
  training_task_id?: string;
  dataset_id?: string;
  dataset_status?: "none" | "pending" | "available" | "missing" | "deleted" | string;
  dataset_exists?: boolean;
  ai_task_id?: string;
  ai_model_id?: string;
  model_run_id?: string;
  model_label?: string;
  model_status?: "none" | "pending" | "available" | "missing" | "deleted" | string;
  model_exists?: boolean;
  linked_view?: string;
  agent_reason?: string;
  agent_source?: string;
  agent_mcp?: Record<string, unknown>;
  last_error?: string;
  job_note?: string;
  advancing?: boolean;
  pause_requested?: boolean;
  advance_started_at?: number;
  current_epoch?: number;
  total_epochs?: number;
  worker_bundle_size_mb?: number;
  worker_upload_status?: string;
  worker_upload_started_at?: number;
  worker_upload_completed_at?: number;
  worker_upload_total_bytes?: number;
  worker_upload_sent_bytes?: number;
  worker_download_status?: string;
  worker_download_started_at?: number;
  worker_download_completed_at?: number;
  worker_download_total_bytes?: number;
  worker_download_received_bytes?: number;
  created_at?: number;
  updated_at?: number;
  owner_user_id?: string;
  owner_username?: string;
}

export interface PipelineCandidate {
  id: string;
  name?: string;
  material_type?: string;
  status?: string;
  status_text?: string;
  progress?: number;
  created_at?: number;
  updated_at?: number;
  owner_user_id?: string;
  owner_username?: string;
}

export interface PipelineResponse {
  items: PipelineTask[];
  accessories: AccessorySummary[];
  pending_candidates?: PipelineCandidate[];
  agent?: AgentConfigResponse | null;
}

export interface PipelineAccessoryMutationResponse {
  status: string;
  accessory_id: string;
  accessories: AccessorySummary[];
  pending_candidates?: PipelineCandidate[];
}

export interface PipelineTaskMutationResponse extends PipelineTask {
  deleted_task_id?: string;
}

export interface PipelineTaskPayload {
  name?: string;
  accessory_ids?: string[];
  accessory_counts?: Record<string, number>;
  detection_method?: PipelineDetectionMethod;
  auto_advance?: boolean;
  expected_production_count?: number;
  params?: Record<string, string | number | boolean | null | undefined>;
  task_kind?: "product_inspection" | "incoming_material_text" | string;
  material_code?: string;
  material_name?: string;
  inspection_user_ids?: string[];
}

export interface IncomingTextInspector {
  id: string;
  username: string;
  display_name: string;
}

export interface IncomingTextInspectorsResponse {
  items: IncomingTextInspector[];
}

export type IncomingTextDecision = "PASS" | "FAIL" | "REVIEW_REQUIRED" | "RELEASED" | "REJECTED" | "";

export interface IncomingTextRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface IncomingTextFieldRule {
  field_id: string;
  name: string;
  region_normalized: IncomingTextRegion;
  expected_text: string;
  match_mode: "exact" | "regex";
  importance: "critical" | "normal";
  case_sensitive: boolean;
  ignore_whitespace: boolean;
}

export interface IncomingTextReference {
  id: string;
  task_id: string;
  version_label: string;
  material_code: string;
  material_name?: string;
  status: "draft" | "active" | "archived" | string;
  source_sha256: string;
  canonical_sha256?: string;
  width: number;
  height: number;
  rules: IncomingTextFieldRule[];
  source_url?: string;
  canonical_url?: string;
  created_at: number;
  activated_at?: number;
}

export interface IncomingTextTaskResponse {
  task: PipelineTask;
  references: IncomingTextReference[];
  active_reference?: IncomingTextReference | null;
  automatic_decisions_verified?: boolean;
}

export interface IncomingTextFieldResult extends IncomingTextFieldRule {
  observed_text: string;
  confidence: number;
  matched: boolean;
  outcome: "PASS" | "FAIL" | "REVIEW_REQUIRED";
  reasons: string[];
  visual_similarity?: number | null;
}

export interface IncomingTextInspection {
  id: string;
  capture_id: string;
  task_id: string;
  reference_id: string;
  reference_version_label: string;
  material_code: string;
  material_name?: string;
  status: string;
  auto_decision: IncomingTextDecision;
  final_decision: IncomingTextDecision;
  source_url?: string;
  corrected_url?: string;
  annotated_url?: string;
  quality?: { accepted?: boolean; reasons?: string[]; metrics?: Record<string, number> };
  fields?: IncomingTextFieldResult[];
  reasons?: string[];
  review_reason?: string;
  created_at: number;
  updated_at: number;
}

export interface IncomingTextInspectionsResponse {
  items: IncomingTextInspection[];
  total: number;
  summary: Record<string, number>;
}

export interface TextCompareBetaDifference {
  id: string;
  reference_text: string;
  actual_text: string;
  confidence: number;
  type: "changed" | "missing" | "extra" | "wrong_text" | "case" | "number" | "unit" | "punctuation" | "spacing" | "hyphen" | "blank";
  box?: [number, number, number, number];
  region_normalized?: { x: number; y: number; width: number; height: number } | null;
}

export interface TextInspectionDiagnostics {
  provider_result?: {
    parsed_response?: unknown;
    response_preview?: string;
    [key: string]: unknown;
  };
  normalized_response?: unknown;
  [key: string]: unknown;
}

export interface TextCompareBetaResult {
  comparison_id: string;
  decision: "MATCH" | "DIFFERENCES" | "REVIEW_REQUIRED";
  message: string;
  differences: TextCompareBetaDifference[];
  annotated_image_data_url?: string;
  reference_lines?: number;
  captured_lines?: number;
  reference_quality?: { accepted?: boolean; reasons?: string[] };
  captured_quality?: { accepted?: boolean; reasons?: string[] };
  alignment?: { accepted?: boolean; reason?: string };
  error_code?: string;
  diagnostics?: TextInspectionDiagnostics;
}

export interface TextInspectionAsset {
  id: string;
  standard_id: string;
  asset_kind: "label_candidate" | "manual_page";
  ordinal: number;
  status: "candidate" | "excluded" | "needs_confirmation" | "page";
  category?: string;
  context?: string;
  classification_confidence?: number;
  content_url?: string;
}

export interface TextInspectionStandard {
  id: string;
  name: string;
  material_code: string;
  version_label: string;
  standard_type: "label" | "manual";
  status: "draft" | "confirmed";
  source_sha256: string;
  created_at: number;
  asset_count: number;
  revision_number?: number;
  current_revision_id?: string;
  assets?: TextInspectionAsset[];
}

export interface TextInspectionStandardsResponse { items: TextInspectionStandard[]; }
export interface TextInspectionAssetAddResponse { asset: TextInspectionAsset; standard: TextInspectionStandard; }
export interface TextInspectionAssetMutationResponse extends TextInspectionAsset { standard: TextInspectionStandard; }

export interface AgentRecommendationResponse {
  source?: string;
  reason?: string;
  params?: Record<string, string | number | boolean | null | undefined>;
}

export interface DetectionRuleItem {
  class_id?: number | string;
  label?: string;
  found?: number | string | boolean;
  required?: number | string | boolean;
  max_confidence?: number;
  [key: string]: unknown;
}

export interface DetectionRuleResult {
  passed?: boolean;
  match_policy?: string;
  label?: string;
  present?: Array<DetectionRuleItem | string>;
  missing?: Array<DetectionRuleItem | string>;
  extra?: Array<DetectionRuleItem | string>;
  counts?: Record<string, number>;
  count_mismatches?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface DetectionItem {
  class_id?: number | string;
  class_name?: string;
  label?: string;
  accessory_id?: string;
  present?: boolean;
  found?: number | string | boolean;
  required?: number | string | boolean;
  confidence?: number;
  max_confidence?: number;
  evidence?: string;
  observed_text?: string[];
  count?: number;
  ocr?: {
    manual_label?: string;
    manual_type?: string;
    texts?: string[];
    mean_text_score?: number;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface DetectionVideoFrame {
  frame_index?: number;
  timestamp_seconds?: number;
  passed?: boolean;
  missing?: Array<DetectionRuleItem | string>;
  detections?: number;
  detection_items?: DetectionItem[];
  annotated_url?: string;
  model?: StatusModel | Record<string, unknown>;
  ai?: Record<string, unknown>;
  rule?: DetectionRuleResult;
}

export type PlcSyncState =
  | "disabled"
  | "queued"
  | "attempting"
  | "sent"
  | "detecting"
  | "planned"
  | "browser_attempt_declared"
  | "acknowledged"
  | "partial_success"
  | "uncertain"
  | "failed";

export interface PlcSyncStatus {
  dispatch_id: string;
  source: "image" | "video" | string;
  request_id?: string;
  passed?: boolean;
  enabled: boolean;
  attempted: boolean;
  duplicate?: boolean;
  protocol?: "fx_programming_port_ascii" | string;
  checksum_mode?: PlcChecksumMode;
  status: PlcSyncState;
  error_code?: string;
  physical_status?: string;
  outcome?: string;
  audit_status?: string;
  diagnostic_source?: string;
  attempts?: number;
  targets?: string[];
  acknowledged_targets?: string[];
  failed_target?: string;
  cancelled_after_disable?: boolean;
  frames?: Array<{ target: string; frame_hex: string; attempts: number }>;
  message?: string;
  updated_at?: number;
}

export type PlcChecksumMode = "exclude_etx_legacy_vb" | "include_etx_documented_comment" | "include_etx";

export interface PlcConfig {
  enabled: boolean;
  protocol: "fx_programming_port_ascii";
  checksum_mode: PlcChecksumMode;
  serial_port: string;
  baudrate: number;
  parity: "E" | "O" | "N";
  data_bits: 7 | 8;
  stop_bits: 1 | 2;
  result_register: string;
  output_control_point: string;
  capture_trigger_enabled: boolean;
  capture_input_register: string;
  capture_trigger_value: number;
  timeout: number;
  retries: number;
}

export interface PlcConfigResponse {
  config: PlcConfig;
  resolved_addresses: {
    result_register: string;
    output_control_point: string;
    capture_input_register: string;
  };
  device_profile_verified: boolean;
  read_profile_verified: boolean;
  protocol_options: Array<{ id: "fx_programming_port_ascii"; label: string }>;
  recent_dispatches: PlcSyncStatus[];
  validation_error?: string;
  validation_errors: Array<{ code: string; message: string }>;
  effective_enabled: boolean;
  control_generation: number;
  in_flight_attempts: Array<{
    dispatch_id: string;
    target: string;
    attempt: number;
    generation: number;
    started_at: number;
    disable_revokes_started_io: false;
  }>;
  disable_notice: string;
  queue_wait_seconds: number;
  worker_total_timeout_seconds: number;
}

export interface PlcCaptureSession {
  session_id: string;
  user_id: string;
  model_id: string;
  generation: number;
  busy: boolean;
  heartbeat_at: number;
  expires_at: number;
}

export interface PlcCaptureEvent {
  trigger_id: string;
  value: number;
  model_id: string;
  created_at: number;
  expires_at: number;
  status: "pending" | "claimed";
}

export interface PlcWebSerialConfig {
  schema_version: 5;
  transport_mode: "web_serial";
  profile_id: "mitsubishi_fx3ga_40mr";
  enabled: boolean;
  protocol: "fx_programming_port_ascii";
  checksum_mode: "include_etx";
  baudrate: 9600;
  parity: "E";
  data_bits: 7;
  stop_bits: 1;
  result_register: string;
  output_control_point: string;
  capture_trigger_enabled: boolean;
  capture_input_register: string;
  capture_trigger_value: number;
  capture_poll_interval_ms: 200;
  ack_timeout_ms: 500;
  retries: 0;
}

export interface PlcWorkstationLease {
  station_id: string;
  session_id: string;
  state: "connecting" | "active" | "released" | string;
  lease_epoch: number;
  model_id: string;
  config_generation: number;
  expires_at: number;
  heartbeat_at: number;
  serial_info?: { usb_vendor_id?: number; usb_product_id?: number };
}

export interface PlcWorkstationResponse {
  paired: boolean;
  protocol_version: "plc-web-serial-v4";
  station: null | {
    id: string;
    name: string;
    status: "commissioning" | "production" | string;
    profile_verified: boolean;
  };
  config: PlcWebSerialConfig | null;
  config_generation: number;
  resolved_addresses: { result_register: string; output_control_point: string; capture_input_register: string };
  capture_read_plan: PlcWebSerialCaptureReadPlan | null;
  lease: PlcWorkstationLease | null;
  effective_enabled: boolean;
  production_ready: boolean;
  release_consistent: boolean;
  heartbeat_seconds: number;
  lease_ttl_seconds: number;
  recent_dispatches: PlcSyncStatus[];
}

export interface PlcWebSerialFrame {
  target: string;
  operation: "write_result" | "set_output_on" | "set_output_off" | "diagnostic_write" | "diagnostic_read";
  frame_hex: string;
  frame_sha256: string;
  expected_response_hex: string;
}

export interface PlcWebSerialCaptureReadPlan {
  target: string;
  operation: "read_capture_input";
  frame_hex: string;
  frame_sha256: string;
  expected_response_bytes: 8;
  read_timeout_ms: 500;
  poll_interval_ms: 200;
  trigger_value: number;
  config_generation: number;
  protocol_version: "plc-web-serial-v4";
}

export interface PlcCaptureInputReadResult {
  value: number;
  request_hex: string;
  response_hex: string;
  read_at: number;
}

export interface PlcWebSerialDiagnosticPlan {
  diagnostic_id: string;
  attempt_token: string;
  protocol_version: "plc-web-serial-v4";
  register: "D206";
  write_value: 6;
  issued_at: number;
  deadline_at_ms: number;
  execution_window_ms: number;
  ack_timeout_ms: number;
  read_timeout_ms: number;
  frames: [PlcWebSerialFrame, PlcWebSerialFrame];
}

export interface PlcWebSerialDiagnosticResult {
  status: "success" | "failed";
  conclusion: string;
  write_frame_hex: string;
  write_response_hex: string;
  read_frame_hex: string;
  read_response_hex: string;
  read_value: number | null;
}

export interface PlcWebSerialAttempt extends Omit<PlcSyncStatus, "frames"> {
  attempt_token: string;
  deadline_at: number;
  execution_window_ms: number;
  ack_timeout_ms: number;
  frames: PlcWebSerialFrame[];
  serial_options: {
    baudRate: number;
    dataBits: 7 | 8;
    stopBits: 1 | 2;
    parity: "even" | "odd" | "none";
    flowControl: "none" | "hardware";
  };
}

export interface PlcWebSerialOperation {
  target: string;
  frame_sha256: string;
  status: "acknowledged" | "nak" | "timeout" | "serial_error" | "unexpected_response";
  response_hex: string;
  completed_at: number;
}

export interface DetectionResult {
  request_id?: string;
  passed: boolean;
  model?: StatusModel | Record<string, unknown>;
  rule?: DetectionRuleResult;
  detections?: DetectionItem[];
  annotated_url?: string;
  preview_url?: string;
  ai?: Record<string, unknown> | null;
  sampled_frames?: number;
  passed_frames?: number;
  pass_rate?: number;
  frames?: DetectionVideoFrame[];
  plc_sync?: PlcSyncStatus;
}

export interface DataAnalysisTaskGroup {
  id: string;
  name?: string;
  type?: string;
  count?: number;
  latest_at?: number;
  image_processing_summary?: DataAnalysisImageProcessingSummary;
}

export interface DataAnalysisAiSummary {
  passed?: boolean;
  detection_count?: number;
  present_count?: number;
  missing_count?: number;
  extra_count?: number;
  count_mismatch_count?: number;
  counts?: Record<string, number>;
  missing?: string[];
  extra?: string[];
  provider_status?: string;
  latency_ms?: number;
}

export interface DataAnalysisRequiredAccessory {
  accessory_id: string;
  label?: string;
  required_count?: number;
  ai_detection_count?: number;
}

export interface DataAnalysisRequiredScope {
  source?: string;
  required_accessories?: DataAnalysisRequiredAccessory[];
}

export interface DataAnalysisComparisonDifference {
  accessory_id?: string;
  label?: string;
  required_count?: number;
  ai_count?: number;
  delta?: number;
}

export interface DataAnalysisComparisonSummary {
  status?: string;
  ai_passed?: boolean;
  ai_counts?: Record<string, number>;
  required_counts?: Record<string, number>;
  difference_count?: number;
  differences?: DataAnalysisComparisonDifference[];
  latest_run_id?: string;
  updated_at?: number;
}

export interface DataAnalysisImageProcessingSummary {
  total?: number;
  queued?: number;
  running?: number;
  completed?: number;
  rejected?: number;
  failed?: number;
  active?: number;
  by_status?: Record<string, number>;
}

export interface DataAnalysisImageProcessingItem {
  id: string;
  type?: string;
  type_label?: string;
  status?: string;
  label?: string;
  url?: string;
  created_at?: number;
  updated_at?: number;
  reason?: string;
  metrics?: Record<string, unknown>;
  sample_id?: string;
  accessory_id?: string;
  record_id?: string;
  task_id?: string;
}

export interface DataAnalysisRecord {
  record_id: string;
  owner_user_id?: string;
  owner_username?: string;
  created_at?: number;
  updated_at?: number;
  task?: {
    id?: string;
    name?: string;
    type?: string;
    [key: string]: unknown;
  };
  source_image?: {
    filename?: string;
    url?: string;
    path?: string;
    [key: string]: unknown;
  };
  image_url?: string;
  ai_summary?: DataAnalysisAiSummary;
  required_accessory_scope?: DataAnalysisRequiredScope;
  comparison_summary?: DataAnalysisComparisonSummary;
  image_processing_summary?: DataAnalysisImageProcessingSummary;
  image_processing_items?: DataAnalysisImageProcessingItem[];
  ai_detection_result?: DetectionResult & Record<string, unknown>;
}

export interface DataAnalysisRecordsResponse {
  records: DataAnalysisRecord[];
  tasks: DataAnalysisTaskGroup[];
  total: number;
  limit: number;
  offset: number;
  batch_limit: number;
  image_processing_summary?: DataAnalysisImageProcessingSummary;
}

export interface DataAnalysisRecordResponse {
  record: DataAnalysisRecord;
}

export interface TrainingResourcesResponse {
  datasets?: TrainingDataset[];
  models?: TrainingModel[];
  tasks?: TrainingTask[];
  training_tasks?: TrainingTask[];
  ai_detection_tasks?: AiDetectionLibraryTask[];
}

export interface TrainingSample {
  image?: string;
  labels?: string;
  url?: string;
  annotated_url?: string;
  split?: string;
  is_true?: boolean;
  missing_count?: number;
  created_at?: number;
  updated_at?: number;
  owner_user_id?: string;
  owner_username?: string;
}

export interface TrainingDatasetDetailResponse {
  status: string;
  dataset: TrainingDataset;
}

export interface TrainingResourceMutationResponse extends TrainingResourcesResponse {
  status: string;
  dataset_id?: string;
  run_id?: string;
  sample?: string;
}

export interface AccessoryPhysicalSize {
  kind?: "paper" | "object" | string;
  preset?: string;
  width_mm?: number;
  height_mm?: number;
  length_mm?: number;
}

export interface AccessoryProfileStatus {
  status?: string;
  source?: string;
  message?: string;
  updated_at?: number;
  profile_version?: string;
}

export interface AccessorySummary {
  id: string;
  class_id?: number;
  name?: string;
  label?: string;
  material_type?: "text" | "object" | string;
  material_alpha_policy?: string;
  object_alpha_policy_label?: string;
  training_role?: string;
  detection_route?: string;
  physical_size?: AccessoryPhysicalSize;
  status?: string;
  manual_crop_required?: boolean;
  manual_crop_reason?: string;
  preprocess?: string;
  source_files?: string[];
  original_source_files?: string[];
  source_file_count?: number;
  normalized_asset_count?: number;
  clean_sprite_status?: string;
  clean_sprite_count?: number;
  clean_sprite_expected_count?: number;
  clean_sprite_failed_cells?: unknown[];
  ai_profile_status?: AccessoryProfileStatus | string;
  ai_profile_ready?: boolean;
  thumbnail_url?: string;
  thumbnails?: AccessoryGalleryAsset[];
  created_at?: number;
  updated_at?: number;
  confirmed_at?: number;
  owner_user_id?: string;
  owner_username?: string;
}

export interface AccessoryDetail extends AccessorySummary {
  original_source_files?: string[];
  normalized_assets?: unknown[];
  ai_profile?: unknown;
}

export interface AccessoryGalleryAsset {
  label?: string;
  kind?: string;
  url?: string;
  source_path?: string;
  deletable?: boolean;
  ai_reference?: boolean;
  width?: number;
  height?: number;
  created_at?: number;
  updated_at?: number;
  owner_user_id?: string;
  owner_username?: string;
  [key: string]: unknown;
}

export interface AccessoriesResponse {
  items: AccessorySummary[];
}

export interface AccessoryDetailResponse {
  item: AccessoryDetail;
  gallery: AccessoryGalleryAsset[];
}

export interface AccessoryImageJob {
  job_id?: string;
  task_id?: string;
  label?: string;
  status?: string;
  progress?: number;
  note?: string;
  error?: string;
  output_url?: string;
  created_at?: number;
  updated_at?: number;
}

export interface AccessoryCandidate {
  id: string;
  name?: string;
  class_id?: number;
  material_type?: string;
  material_alpha_policy?: string;
  object_alpha_policy_label?: string;
  training_role?: string;
  status?: string;
  source_files?: string[];
  codex_image_job?: AccessoryImageJob;
  codex_image_jobs?: AccessoryImageJob[];
  confirmed_accessory_id?: string;
  confirmed_at?: number;
  created_at?: number;
  updated_at?: number;
  owner_user_id?: string;
  owner_username?: string;
}

export interface AccessoryCandidateResponse {
  status: string;
  candidate: AccessoryCandidate;
}

export interface AccessoryMutationResponse extends AccessoriesResponse {
  status: string;
  item?: AccessorySummary;
  detail?: AccessoryDetailResponse;
  accessory_id?: string;
  source_path?: string;
  route?: string;
  profile_status?: string;
  candidate?: AccessoryCandidate;
  pipeline?: PipelineAccessoryMutationResponse;
}

export interface AccessoryTextCropPayload {
  source_path: string;
  corners: Array<{ x: number; y: number }>;
}

export interface LocateInspectionRule {
  id: string;
  label?: string;
  display_label?: string;
  source?: string;
  material_type?: string;
  task_type?: string;
  visual_prompt?: string;
  expected_present?: boolean;
  expected_count?: number;
  default_expected_present?: boolean;
  default_expected_count?: number;
  default_selected?: boolean;
  prompt_override?: string;
  search_terms?: string[];
}

export interface LocateSourceItem extends LocateInspectionRule {}

export interface LocateConfigResponse {
  ok?: boolean;
  configured?: boolean;
  status?: string;
  message?: string;
  enabled?: boolean;
  endpoint_url?: string;
  generation_mode?: string;
  max_side?: number;
  max_new_tokens?: number;
  timeout_seconds?: number;
  license?: string;
  items?: LocateSourceItem[];
  [key: string]: unknown;
}

export interface LocateInspectItem {
  box_count?: number;
  [key: string]: unknown;
}

export interface LocateInspectResult {
  ok?: boolean;
  configured?: boolean;
  overall_pass?: boolean;
  boxes?: unknown[];
  items?: LocateInspectItem[];
  error?: string;
  overlay_url?: string;
  diagnostic_url?: string;
  latency_ms?: number;
  prompt?: string;
  [key: string]: unknown;
}

export interface LabelSheetReference {
  reference_id?: string;
  name?: string;
  label?: string;
  annotation?: string;
  image_url?: string;
  accessory_id?: string;
  [key: string]: unknown;
}

export interface LabelSheetCandidate {
  metrics?: Record<string, unknown>;
  matched_reference_name?: string;
  matched_reference_label?: string;
  reference_id?: string;
  candidate_id?: string;
  [key: string]: unknown;
}

export interface LabelSheetMatchResult {
  status: string;
  passed?: boolean;
  error?: string;
  request_id?: string;
  score?: number;
  matched_reference_image_url?: string;
  best_reference_image_url?: string;
  matched_reference_name?: string;
  matched_reference_label?: string;
  best_reference_name?: string;
  best_reference_label?: string;
  low_confidence_reason?: string;
  review_status?: string;
  thresholds?: { match_score?: number; [key: string]: unknown };
  input_crop_image_url?: string;
  sheet_overlay_url?: string;
  candidates?: LabelSheetCandidate[];
  [key: string]: unknown;
}

export interface LabelSheetReferencesResponse {
  references: LabelSheetReference[];
  doc_filter_stats?: Record<string, unknown>;
}

export interface ApiRequestOptions extends RequestInit {
  parseAs?: "json" | "text" | "void";
}

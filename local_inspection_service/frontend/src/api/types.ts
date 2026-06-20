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
  is_label_sheet_match?: boolean;
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

export type PipelineDetectionMethod = "yolo_ocr" | "yolo" | "ai" | "locate" | string;
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
  accessory_ids?: string[];
  accessory_counts?: Record<string, number>;
  accessory_names?: string[];
  accessories?: PipelineTaskAccessory[];
  detection_method?: PipelineDetectionMethod;
  uses_training_flow?: boolean;
  stage?: PipelineStage;
  status?: string;
  progress?: number;
  params?: Record<string, string | number | boolean | null | undefined>;
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
  ai_task_id?: string;
  ai_model_id?: string;
  model_run_id?: string;
  model_label?: string;
  model_exists?: boolean;
  linked_view?: string;
  agent_reason?: string;
  agent_source?: string;
  agent_mcp?: Record<string, unknown>;
  last_error?: string;
  job_note?: string;
  advancing?: boolean;
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
  params?: Record<string, string | number | boolean | null | undefined>;
}

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
}

export interface LabelSheetReference {
  reference_id?: string;
  accessory_id?: string;
  class_id?: number;
  label?: string;
  name?: string;
  annotation?: string;
  source_path?: string;
  image_url?: string;
  owner_user_id?: string;
  owner_username?: string;
  [key: string]: unknown;
}

export interface LabelSheetReferencesResponse {
  status: string;
  references: LabelSheetReference[];
  doc_filter_stats?: Record<string, unknown>;
  item?: AccessorySummary;
}

export interface LabelSheetCandidate {
  reference_id?: string;
  matched_reference_id?: string;
  matched_reference_label?: string;
  matched_reference_name?: string;
  matched_reference_image_url?: string;
  score?: number;
  candidate_id?: string;
  candidate_bbox?: Record<string, number> | null;
  metrics?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface LabelSheetMatchResult extends DetectionResult {
  status: string;
  review_status?: string;
  matched_reference_id?: string;
  matched_reference_label?: string;
  matched_reference_name?: string;
  matched_reference_image_url?: string;
  best_reference_id?: string;
  best_reference_label?: string;
  best_reference_name?: string;
  best_reference_image_url?: string;
  input_crop_image_url?: string;
  sheet_overlay_url?: string;
  score?: number;
  confidence?: number;
  low_confidence_reason?: string;
  candidates?: LabelSheetCandidate[];
  doc_filter_stats?: Record<string, unknown>;
  thresholds?: Record<string, unknown>;
  error?: string;
}

export interface LocateConfigResponse {
  enabled?: boolean;
  configured?: boolean;
  endpoint_url?: string;
  generation_mode?: string;
  max_side?: number;
  max_new_tokens?: number;
  timeout_seconds?: number;
  ok?: boolean;
  status?: string;
  message?: string;
  latency_ms?: number;
  model?: string;
  license?: string;
  role?: string;
  worker_configured?: boolean;
  worker_status?: string;
  worker_base_url?: string;
  [key: string]: unknown;
}

export interface LocateSourceItem {
  id: string;
  source?: string;
  accessory_id?: string;
  class_id?: number;
  label?: string;
  display_label?: string;
  material_type?: string;
  task_type?: string;
  visual_prompt?: string;
  search_terms?: string[];
  default_expected_present?: boolean;
  default_expected_count?: number;
  default_selected?: boolean;
  locateanything_profile?: Record<string, unknown>;
  target_scope?: string;
  reject_cues?: string[];
  packaging_exclusions?: string[];
  subpart_text_logo_exclusions?: string[];
  count_strategy?: string;
  box_constraints?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface LocateAccessoriesResponse {
  items: LocateSourceItem[];
  required_classes?: number[];
  min_counts?: Record<string, number>;
}

export interface LocateInspectionRule {
  id: string;
  label?: string;
  display_label?: string;
  source?: string;
  material_type?: string;
  visual_prompt?: string;
  expected_present?: boolean;
  expected_count?: number;
  prompt_override?: string;
}

export interface LocateInspectionItem {
  id?: string;
  label?: string;
  display_label?: string;
  status?: string;
  passed?: boolean;
  expected_present?: boolean;
  expected_count?: number;
  box_count?: number;
  error?: string;
  prompt?: string;
  raw_answer_snippet?: string;
  boxes?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface LocateDiagnosticItem {
  id?: string;
  label?: string;
  prompt?: string;
  raw_answer_snippet?: string;
  error?: string;
  box_count?: number;
  [key: string]: unknown;
}

export interface LocateInspectResult {
  ok?: boolean;
  configured?: boolean;
  overall_pass?: boolean;
  decision?: string;
  items?: LocateInspectionItem[];
  source_image_size?: Record<string, number>;
  sent_image_size?: Record<string, number>;
  latency_ms?: number;
  overlay_url?: string;
  diagnostic_url?: string;
  diagnostics?: LocateDiagnosticItem[];
  error?: string;
  prompt?: string;
  raw_answer?: string;
  boxes?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface DataAnalysisTaskGroup {
  id: string;
  name?: string;
  type?: string;
  count?: number;
  latest_at?: number;
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

export interface DataAnalysisLocateRun {
  run_id?: string;
  created_at?: number;
  status?: string;
  configured?: boolean;
  overall_pass?: boolean;
  decision?: string;
  box_count?: number;
  latency_ms?: number;
  error?: string;
  overlay_url?: string;
  diagnostic_url?: string;
  items?: LocateInspectionItem[];
  diagnostics?: LocateDiagnosticItem[];
  required_accessory_ids?: string[];
  required_counts?: Record<string, number>;
  source_image_size?: Record<string, number>;
  sent_image_size?: Record<string, number>;
}

export interface DataAnalysisComparisonDifference {
  accessory_id?: string;
  label?: string;
  required_count?: number;
  ai_count?: number;
  locateanything_count?: number;
  delta?: number;
  locate_status?: string;
}

export interface DataAnalysisComparisonSummary {
  status?: string;
  ai_passed?: boolean;
  locateanything_passed?: boolean;
  ai_counts?: Record<string, number>;
  locateanything_counts?: Record<string, number>;
  required_counts?: Record<string, number>;
  difference_count?: number;
  differences?: DataAnalysisComparisonDifference[];
  latest_run_id?: string;
  updated_at?: number;
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
  locateanything_run_count?: number;
  latest_locateanything_run?: DataAnalysisLocateRun;
  ai_detection_result?: DetectionResult & Record<string, unknown>;
  locateanything_runs?: DataAnalysisLocateRun[];
}

export interface DataAnalysisRecordsResponse {
  records: DataAnalysisRecord[];
  tasks: DataAnalysisTaskGroup[];
  total: number;
  limit: number;
  offset: number;
  batch_limit: number;
  locateanything?: LocateConfigResponse;
}

export interface DataAnalysisRecordResponse {
  record: DataAnalysisRecord;
}

export interface DataAnalysisLocateRequest {
  record_ids?: string[];
  endpoint_url?: string;
  max_side?: number;
  max_new_tokens?: number;
  timeout_seconds?: number;
}

export interface DataAnalysisLocateResponse {
  status?: string;
  count?: number;
  batch_limit?: number;
  record?: DataAnalysisRecord;
  run?: DataAnalysisLocateRun;
  comparison?: DataAnalysisComparisonSummary;
  results?: Array<{
    record: DataAnalysisRecord;
    run: DataAnalysisLocateRun;
    comparison: DataAnalysisComparisonSummary;
  }>;
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
  source_files?: string[];
  source_file_count?: number;
  normalized_asset_count?: number;
  clean_sprite_status?: string;
  clean_sprite_count?: number;
  clean_sprite_expected_count?: number;
  clean_sprite_failed_cells?: unknown[];
  ai_profile_status?: AccessoryProfileStatus | string;
  ai_profile_ready?: boolean;
  locateanything_profile_status?: AccessoryProfileStatus | string;
  locateanything_profile_ready?: boolean;
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
  locateanything_profile?: unknown;
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

export interface ApiRequestOptions extends RequestInit {
  parseAs?: "json" | "text" | "void";
}

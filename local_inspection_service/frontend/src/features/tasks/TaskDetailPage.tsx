import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { CheckCircle2, ChevronRight, Eye, Loader2, PauseCircle, Play, RefreshCw, RotateCcw, Save, SlidersHorizontal, Trash2, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  advancePipelineTask,
  approveAiTaskAutoOptimizeSample,
  deleteAiTaskAutoOptimizeSample,
  deleteTrainingDatasetSample,
  getAiTaskAutoOptimize,
  getDataAnalysisRecords,
  getPipeline,
  getTrainingDatasetDetail,
  getTrainingResources,
  pausePipelineTask,
  queryKeys,
  retryAiTaskAutoOptimizeSample,
  updateAiTaskAutoOptimize,
  updatePipelineTask
} from "../../api/queries";
import type { AiAutoOptimizeSample, AiAutoOptimizeStatus, DataAnalysisImageProcessingItem, DataAnalysisRecord, TrainingDataset, TrainingSample } from "../../api/types";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { MetricCard } from "../../components/MetricCard";
import { useToast } from "../../components/ToastProvider";
import { taskEntriesFromTrainingResources, taskStatusTone, type TaskEntry } from "../../utils/taskNavigation";
import { AccessoryDetailModal } from "../accessories/AccessoriesPage";
import { useAuth } from "../auth/auth-context";

function cacheUrl(url = "", token = "") {
  if (!url) return "";
  const suffix = token || String(Date.now());
  return `${url}${url.includes("?") ? "&" : "?"}t=${encodeURIComponent(suffix)}`;
}

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function isAiDrivenTask(task: TaskEntry | undefined) {
  return Boolean(task && (task.kind === "ai" || task.detectionMethod === "ai" || task.aiTaskId || task.aiModelId));
}

function autoOptimizeTaskIdFor(task: TaskEntry | undefined) {
  if (!task) return "";
  return task.autoOptimizeTaskId || task.aiBaselineTaskId || task.aiTaskId || (isAiDrivenTask(task) ? task.sourceId : "");
}

function detectionAccessModes(task: TaskEntry | undefined, autoOptimize?: AiAutoOptimizeStatus) {
  if (!task) return [];
  const method = String(task.detectionMethod || task.optimizationRoute || "").toLowerCase();
  const aiDriven = isAiDrivenTask(task);
  const promotedYolo = isAutoOptimizePromoted(autoOptimize);
  const hasYoloModel = aiDriven ? promotedYolo : Boolean(task.modelExists || task.modelRunId);
  return unique([
    task.aiTaskId || task.aiBaselineTaskId || task.aiBaselineModelId || task.autoOptimizeTaskId ? "AI baseline" : "",
    hasYoloModel ? "YOLO" : "",
    hasYoloModel && method.includes("ocr") ? "YOLO + OCR" : ""
  ]);
}

function progressValue(task: TaskEntry | undefined, recordsCount = 0, sampleCount = 0, rejectedCount = 0) {
  if (!task) return 0;
  const aiDriven = isAiDrivenTask(task);
  if (aiDriven) {
    const hasTrainingStarted = Boolean(task.trainingTaskId || task.currentEpoch || task.totalEpochs);
    const hasYoloCandidate = Boolean(task.modelRunId || task.modelLabel);
    if (task.stage === "library" && hasYoloCandidate && task.status === "已上线") return 100;
    if (task.stage === "training") {
      const current = Number(task.currentEpoch || 0);
      const total = Number(task.totalEpochs || 0);
      if (current > 0 && total > 0) return Math.min(75, Math.max(45, Math.round((current / total) * 70)));
      return 52;
    }
    if (hasYoloCandidate) return 82;
    if (hasTrainingStarted) return 42;
    const sampleSignal = Math.min(12, recordsCount * 2 + Math.floor(sampleCount / 6));
    const penalty = Math.min(8, rejectedCount * 3);
    if (task.stage === "samples") return Math.max(5, Math.min(24, 8 + sampleSignal - penalty));
    return Math.max(4, Math.min(18, 6 + sampleSignal - penalty));
  }
  const explicit = Number(task.progress);
  if (Number.isFinite(explicit) && explicit > 0) return Math.min(100, explicit <= 1 ? explicit * 100 : explicit);
  if (task.status === "已上线" || task.stage === "library") return 100;
  if (task.stage === "training") {
    const current = Number(task.currentEpoch || 0);
    const total = Number(task.totalEpochs || 0);
    if (current > 0 && total > 0) return Math.min(95, Math.round((current / total) * 100));
    return 72;
  }
  if (task.stage === "samples") return 45;
  if (task.stage === "ai_detection") return 35;
  if (task.stage === "draft") return 15;
  return 25;
}

function accessoryRows(task: TaskEntry) {
  return task.accessoryIds.length
    ? task.accessoryIds.map((id, index) => ({
        id,
        name: task.accessoryNames[index] || id,
        count: task.accessoryCounts[id] || 1
      }))
    : task.accessoryNames.map((name) => ({ id: name, name, count: 1 }));
}

function stageText(task: TaskEntry) {
  if (task.stage === "library" && task.modelExists && !isAiDrivenTask(task) && (task.autoOptimizeTaskId || task.aiBaselineTaskId)) return "模型已上线 / 自动优化采集停止";
  if (isAiDrivenTask(task) && task.stage === "library") return "AI 检测可用 / 样本采集";
  if (task.stage === "draft") return "任务定义";
  if (task.stage === "samples") return "样本采集 / 生成";
  if (task.stage === "training") return "模型训练";
  if (task.stage === "library") return "模型上线";
  if (task.stage === "ai_detection") return "AI 检测与样本采集";
  return task.stage || task.status;
}

function samplePublicUrl(sample: TrainingSample) {
  if (sample.annotated_url) return sample.annotated_url;
  if (sample.url) return sample.url;
  const image = String(sample.image || "");
  const marker = "/data/outputs/";
  if (image.includes(marker)) return `/outputs/${image.split(marker).pop()}`;
  return "";
}

function sampleDisplayName(sample: TrainingSample) {
  const raw = String(sample.image || sample.url || "sample");
  return raw.split(/[\\/]/).pop() || "sample";
}

function datasetMatchesTask(dataset: TrainingDataset, task: TaskEntry | undefined) {
  if (!task) return false;
  if (task.datasetId) return dataset.id === task.datasetId;
  if (isAiDrivenTask(task) || task.autoOptimizeTaskId) return false;
  const datasetAccessories = dataset.selected_accessory_ids || [];
  if (!task.accessoryIds.length || !datasetAccessories.length) return false;
  return task.accessoryIds.every((id) => datasetAccessories.includes(id));
}

function resourceStatusLabel(status = "", fallback = "") {
  const labels: Record<string, string> = {
    none: "未生成",
    pending: "生成中",
    available: "可用",
    missing: "文件缺失",
    deleted: "已删除"
  };
  return labels[status] || fallback || status || "未生成";
}

function resourceStatusTone(status = ""): "neutral" | "ok" | "warn" | "fail" {
  if (status === "available") return "ok";
  if (status === "deleted" || status === "missing") return "warn";
  if (status === "pending") return "neutral";
  return "neutral";
}

function autoOptimizePhaseText(status?: AiAutoOptimizeStatus) {
  const phase = status?.phase || (status?.enabled ? "capture" : "paused");
  return {
    paused: "未开启",
    capture: "采集中",
    weak_labeling: "弱标注",
    training_candidate: "训练候选",
    shadow_compare: "影子对比",
    promoted: "模型已上线 / 采集停止"
  }[phase] || "等待";
}

function autoOptimizeDetailText(status?: AiAutoOptimizeStatus) {
  if (!status) return "开启后后台采集 AI 检测图，自动生成弱标注并训练 YOLO 候选。";
  if (status.phase === "promoted" || (!status.enabled && status.active_model_id)) {
    return `模型 ${status.active_model_id || "-"} 已上线，自动优化采集已停止，后续检测不会继续保存新的训练图片。`;
  }
  const threshold = Number(status.settings?.min_trainable_samples || 0);
  const expected = Number(status.expected_production_count || 0);
  const init = status.initialization || {};
  const reason = typeof init.reason === "string" ? init.reason : "";
  const parts = [
    expected ? `预计产量 ${expected}` : "",
    threshold ? `训练阈值 ${threshold}` : "",
    `真实样本 ${Number(status.captured_samples || 0)}`,
    `预计训练图 ${Number(status.projected_training_samples || 0)}`,
    `负样本 ${Number(status.negative_samples || 0)}`,
    `可用 sprite ${Number(status.sprite_pool_count || 0)}`,
    `待标注 ${Number(status.pending_labels || 0)}`,
    `待复核 ${Number(status.review_required_samples || 0)}`,
    `候选 ${Number(status.candidate_model_count || 0)}`,
    `影子 ${Number(status.shadow_runs || 0)}`
  ];
  if (status.active_model_id) parts.push(`当前 ${status.active_model_id}`);
  return [parts.filter(Boolean).join(" · "), reason].filter(Boolean).join("。");
}

function latestAutoOptimizeCandidate(status?: AiAutoOptimizeStatus) {
  const candidate = status?.latest_candidate_model;
  return candidate && typeof candidate === "object" ? candidate : {};
}

function latestAutoOptimizeDataset(status?: AiAutoOptimizeStatus) {
  const dataset = status?.latest_dataset;
  return dataset && typeof dataset === "object" ? dataset : {};
}

function autoOptimizeCandidateStatus(status?: AiAutoOptimizeStatus) {
  return String(latestAutoOptimizeCandidate(status).status || "").toLowerCase();
}

function autoOptimizeCandidateProgress(status?: AiAutoOptimizeStatus) {
  const progress = Number(latestAutoOptimizeCandidate(status).progress || 0);
  if (!Number.isFinite(progress) || progress <= 0) return 0;
  return progress <= 1 ? Math.round(progress * 100) : Math.round(progress);
}

function isAutoOptimizePromoted(status?: AiAutoOptimizeStatus) {
  return Boolean(status?.active_model_id && (status.phase === "promoted" || status.serving_mode === "promoted_yolo"));
}

function isAutoOptimizeTraining(status?: AiAutoOptimizeStatus) {
  const candidateStatus = autoOptimizeCandidateStatus(status);
  return Boolean(
    !isAutoOptimizePromoted(status) &&
      (status?.phase === "training_candidate" ||
        status?.phase === "shadow_compare" ||
        ["queued", "pending", "running"].includes(candidateStatus))
  );
}

function autoOptimizeDisplayStatus(task: TaskEntry, status?: AiAutoOptimizeStatus) {
  const candidateStatus = autoOptimizeCandidateStatus(status);
  if (isAutoOptimizePromoted(status)) return "已上线";
  if (isAutoOptimizeTraining(status)) return candidateStatus === "queued" || candidateStatus === "pending" ? "排队训练" : "训练中";
  return task.status;
}

function autoOptimizeDisplayStage(task: TaskEntry, status?: AiAutoOptimizeStatus) {
  const progress = autoOptimizeCandidateProgress(status);
  if (isAutoOptimizePromoted(status)) return "模型已上线 / 自动优化采集停止";
  if (isAutoOptimizeTraining(status)) return progress ? `模型训练 · ${progress}%` : "模型训练";
  if (status?.phase === "weak_labeling") return "自动弱标注";
  if (status?.phase === "capture") return "AI 检测可用 / 样本采集";
  if (status?.phase === "paused" && status.active_model_id) return "模型已上线 / 自动优化采集停止";
  return stageText(task);
}

function autoOptimizeDisplayProgress(task: TaskEntry, status: AiAutoOptimizeStatus | undefined, fallbackProgress: number) {
  const candidateProgress = autoOptimizeCandidateProgress(status);
  if (isAutoOptimizePromoted(status)) return 100;
  if (isAutoOptimizeTraining(status)) return Math.max(45, Math.min(95, candidateProgress || (status?.phase === "shadow_compare" ? 82 : 55)));
  if (status?.phase === "weak_labeling") return Math.max(fallbackProgress, 28);
  if (status?.phase === "capture" && isAiDrivenTask(task)) return Math.max(fallbackProgress, 12);
  return fallbackProgress;
}

function autoOptimizeNumber(status: AiAutoOptimizeStatus | undefined, key: keyof AiAutoOptimizeStatus) {
  return Number(status?.[key] || 0);
}

function autoOptimizeSettingNumber(status: AiAutoOptimizeStatus | undefined, key: string, fallback: number) {
  const value = Number(status?.settings?.[key] ?? status?.training_parameters?.[key] ?? status?.training_requirements?.[key] ?? fallback);
  return Number.isFinite(value) ? value : fallback;
}

function autoOptimizeRecommendationNumber(status: AiAutoOptimizeStatus | undefined, key: string, fallback: number) {
  const value = Number(status?.initialization?.[key] ?? fallback);
  return Number.isFinite(value) ? value : fallback;
}

function autoOptimizeStatusNumber(status: AiAutoOptimizeStatus | undefined, key: keyof AiAutoOptimizeStatus, fallback = 0) {
  const value = Number(status?.[key] ?? fallback);
  return Number.isFinite(value) ? value : fallback;
}

function autoOptimizeRecommendationBoolean(status: AiAutoOptimizeStatus | undefined, key: string, fallback: boolean) {
  const value = status?.initialization?.[key];
  return typeof value === "boolean" ? value : fallback;
}

function recommendedAutoOptimizePayload(status: AiAutoOptimizeStatus | undefined) {
  const minTrainableSamples = Math.max(1, autoOptimizeRecommendationNumber(status, "min_trainable_samples", 200));
  return {
    enabled: autoOptimizeRecommendationBoolean(status, "enabled", true),
    auto_promote: autoOptimizeRecommendationBoolean(status, "auto_promote", true),
    samples_per_real_image: Math.max(1, autoOptimizeRecommendationNumber(status, "samples_per_real_image", Number(status?.samples_per_real_image || 12))),
    negative_samples_per_real_image: Math.max(0, autoOptimizeRecommendationNumber(status, "negative_samples_per_real_image", Number(status?.negative_samples_per_real_image || 0))),
    training_epochs: Math.max(1, autoOptimizeRecommendationNumber(status, "training_epochs", autoOptimizeSettingNumber(status, "training_epochs", 60))),
    training_image_size: Math.max(320, autoOptimizeRecommendationNumber(status, "training_image_size", autoOptimizeSettingNumber(status, "training_image_size", 640))),
    min_trainable_samples: minTrainableSamples,
    min_positive_samples: Math.max(1, autoOptimizeRecommendationNumber(status, "min_positive_samples", minTrainableSamples)),
    min_negative_samples: Math.max(0, autoOptimizeRecommendationNumber(status, "min_negative_samples", 0)),
    max_label_jobs_per_cycle: Math.max(1, autoOptimizeRecommendationNumber(status, "max_label_jobs_per_cycle", 3)),
    mask_compare_min_score: Math.max(0, Math.min(1, autoOptimizeRecommendationNumber(status, "mask_compare_min_score", 0.72))),
    shadow_min_samples: Math.max(1, autoOptimizeRecommendationNumber(status, "shadow_min_samples", 80)),
    shadow_min_agreement: Math.max(0, Math.min(1, autoOptimizeRecommendationNumber(status, "shadow_min_agreement", 0.98)))
  };
}

function readAutoOptimizePayload(form: HTMLFormElement) {
  const data = new FormData(form);
  const minTrainableSamples = Math.max(1, Number(data.get("min_trainable_samples") || 200));
  return {
    enabled: data.get("enabled") === "on",
    auto_promote: data.get("auto_promote") === "on",
    samples_per_real_image: Math.max(1, Number(data.get("samples_per_real_image") || 12)),
    negative_samples_per_real_image: Math.max(0, Math.min(20, Number(data.get("negative_samples_per_real_image") || 0))),
    training_epochs: Math.max(1, Math.min(500, Number(data.get("training_epochs") || 60))),
    training_image_size: Math.max(320, Math.min(2048, Number(data.get("training_image_size") || 640))),
    min_trainable_samples: minTrainableSamples,
    min_positive_samples: Math.max(1, Number(data.get("min_positive_samples") || minTrainableSamples)),
    min_negative_samples: Math.max(0, Number(data.get("min_negative_samples") || 0)),
    max_label_jobs_per_cycle: Math.max(1, Number(data.get("max_label_jobs_per_cycle") || 3)),
    mask_compare_min_score: Math.max(0, Math.min(1, Number(data.get("mask_compare_min_score") || 0.72))),
    shadow_min_samples: Math.max(1, Number(data.get("shadow_min_samples") || 80)),
    shadow_min_agreement: Math.max(0, Math.min(1, Number(data.get("shadow_min_agreement") || 0.98)))
  };
}

function autoOptimizeSampleStatusLabel(status = "", sampleType = "") {
  const labels: Record<string, string> = {
    negative: "负样本",
    pending: "待 AI mask",
    labeling: "生成 mask 中",
    trainable: "可训练",
    trainable_bbox_only: "仅框可训练",
    review_required: "待人工复核",
    rejected: "未通过",
    failed: "失败",
    retrying: "重试中",
    retried: "已重试"
  };
  if (labels[status]) return labels[status];
  if (sampleType === "negative_candidate") return "负样本";
  if (sampleType === "failed_detection") return "检测未通过";
  return status || "待处理";
}

function autoOptimizeRejectReasonText(reason = "") {
  const labels: Record<string, string> = {
    ai_detection_not_passed: "AI 检测未通过，已跳过 AI mask，不作为负样本。",
    ai_detection_no_positive_candidates: "AI 检测通过但没有可用于标注的候选目标，已跳过 AI mask。",
    ai_detection_provider_failed: "AI provider 调用失败，未进入 AI mask。",
    ai_detection_absent_negative_sample: "历史记录：AI 检测未发现目标，旧逻辑按负样本处理。"
  };
  return labels[reason] || reason;
}

function autoOptimizeSampleTone(status = ""): "neutral" | "ok" | "warn" | "fail" {
  if (status === "trainable" || status === "trainable_bbox_only" || status === "negative") return "ok";
  if (status === "review_required" || status === "pending" || status === "labeling" || status === "retrying") return "warn";
  if (status === "rejected" || status === "failed") return "fail";
  return "neutral";
}

function autoOptimizeSampleImageUrl(sample: AiAutoOptimizeSample | null | undefined) {
  return sample?.source_image?.url || "";
}

function stringValue(value: unknown) {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function autoOptimizeSampleAiImageUrl(sample: AiAutoOptimizeSample | null | undefined) {
  const result = sample?.ai_result || {};
  return (
    stringValue(result.annotated_url) ||
    stringValue(result.preview_url) ||
    stringValue(result.output_url) ||
    autoOptimizeSampleImageUrl(sample)
  );
}

function autoOptimizeSampleReviewImageUrl(sample: AiAutoOptimizeSample | null | undefined) {
  const artifacts = sample?.label_artifacts || {};
  return stringValue(artifacts.review_overlay_url) || autoOptimizeSampleAiImageUrl(sample) || autoOptimizeSampleImageUrl(sample);
}

function autoOptimizeSampleTitle(sample: AiAutoOptimizeSample) {
  return sample.source_image?.filename || sample.record_id || sample.sample_id || "自动优化样本";
}

function manualReviewPreviousFailures(sample: AiAutoOptimizeSample) {
  const manualReview = sample.manual_review || {};
  const previous = manualReview.previous_label_failures;
  return Array.isArray(previous) ? previous.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object")) : [];
}

function autoOptimizeSampleFailureText(sample: AiAutoOptimizeSample) {
  const failures = sample.label_failures?.length ? sample.label_failures : manualReviewPreviousFailures(sample);
  return failures.map((item) => String(item.reason || item.status || "")).filter(Boolean).join("；");
}

function autoOptimizeSampleReason(sample: AiAutoOptimizeSample) {
  const manualReview = sample.manual_review || {};
  if (manualReview.status === "approved") {
    const modeText = manualReview.mode === "bbox_only" ? "仅当前图已通过" : "图片+sprite 已通过";
    const previousReason = stringValue(manualReview.previous_label_reject_reason) || autoOptimizeSampleFailureText(sample);
    return previousReason ? `${modeText}；原拦截原因：${previousReason}` : `${modeText}，会进入训练样本。`;
  }
  if (sample.label_reject_reason) return autoOptimizeRejectReasonText(sample.label_reject_reason);
  const failures = sample.label_failures || [];
  const firstFailure = failures.find((item) => item && typeof item === "object");
  if (firstFailure?.reason) return String(firstFailure.reason);
  if (sample.label_status === "negative") return "AI 检测认为目标配件不存在，作为负样本进入训练集。";
  return "AI 检测结果与 AI mask 结果需要人工确认。";
}

function autoOptimizeReviewHasBbox(sample: AiAutoOptimizeSample | null | undefined) {
  if (!sample) return false;
  const entries = [...(sample.bbox_labels || []), ...(sample.labels || []), ...(sample.label_failures || []), ...manualReviewPreviousFailures(sample)];
  return entries.some((item) => Array.isArray(item.bbox_xyxy) && item.bbox_xyxy.length >= 4 && stringValue(item.accessory_id));
}

function autoOptimizeBboxEntryCount(sample: AiAutoOptimizeSample | null | undefined) {
  if (!sample) return 0;
  const entries = [...(sample.bbox_labels || []), ...(sample.labels || []), ...(sample.label_failures || []), ...manualReviewPreviousFailures(sample)];
  const seen = new Set<string>();
  entries.forEach((item) => {
    if (!Array.isArray(item.bbox_xyxy) || item.bbox_xyxy.length < 4) return;
    const accessoryId = stringValue(item.accessory_id);
    if (!accessoryId) return;
    const bboxKey = item.bbox_xyxy.slice(0, 4).map((value) => String(Math.round(Number(value) || 0))).join(",");
    seen.add(`${accessoryId}:${bboxKey}`);
  });
  return seen.size;
}

function canApproveAutoOptimizeSample(sample: AiAutoOptimizeSample | null | undefined, mode: "sprite" | "bbox_only") {
  if (!sample) return false;
  if (!new Set(["review_required", "rejected", "failed"]).has(String(sample.label_status || ""))) return false;
  if (mode === "bbox_only") return autoOptimizeReviewHasBbox(sample);
  const labels = sample.labels || [];
  if (!labels.length) return false;
  const artifacts = sample.label_artifacts || {};
  return Boolean(
    stringValue(artifacts.color_mask_url) ||
      stringValue(artifacts.mask_url) ||
      stringValue(artifacts.review_overlay_url) ||
      labels.some((label) => {
        const sprite = label.sprite && typeof label.sprite === "object" ? (label.sprite as Record<string, unknown>) : {};
        return Boolean(stringValue(sprite.url) || stringValue(sprite.raw_url) || stringValue(sprite.path) || stringValue(sprite.raw_path));
      })
  );
}

type ReviewArtifactCard = {
  key: string;
  title: string;
  status?: string;
  url?: string;
  detail?: string;
};

function autoOptimizeSampleIntermediateArtifacts(sample: AiAutoOptimizeSample): ReviewArtifactCard[] {
  const cards: ReviewArtifactCard[] = [];
  const seen = new Set<string>();
  const add = (card: ReviewArtifactCard) => {
    const identity = `${card.title}:${card.url || card.detail || card.key}`;
    if (!card.url && !card.detail) return;
    if (seen.has(identity)) return;
    seen.add(identity);
    cards.push(card);
  };
  const artifacts = sample.label_artifacts || {};
  add({ key: "review-overlay", title: "复合叠加图", status: stringValue(artifacts.review_overlay_url) ? "completed" : "failed", url: stringValue(artifacts.review_overlay_url), detail: autoOptimizeSampleReason(sample) });
  add({ key: "source", title: "原始检测图片", status: "completed", url: autoOptimizeSampleImageUrl(sample), detail: sample.source_image?.filename });
  add({ key: "ai", title: "AI 检测结果", status: "completed", url: autoOptimizeSampleAiImageUrl(sample), detail: stringValue(sample.ai_result?.request_id) });
  add({ key: "all-target-mask", title: "全目标 AI mask", status: stringValue(artifacts.pre_verifier_mask_url || artifacts.all_targets_mask_url) ? "completed" : "failed", url: stringValue(artifacts.pre_verifier_mask_url || artifacts.all_targets_mask_url), detail: "verifier 前保留全部目标" });
  add({ key: "color-mask", title: "最终可训练 mask", status: stringValue(artifacts.color_mask_url) ? "completed" : "failed", url: stringValue(artifacts.color_mask_url || artifacts.mask_url), detail: "verifier 后通过目标" });
  (sample.labels || []).forEach((label, index) => {
    const sprite = label.sprite && typeof label.sprite === "object" ? (label.sprite as Record<string, unknown>) : {};
    const labelName = String(label.label || label.accessory_id || `目标 ${index + 1}`);
    add({
      key: `label-mask-${index}`,
      title: `${labelName} mask`,
      status: "completed",
      url: stringValue(label.mask_url),
      detail: stringValue(label.accessory_id)
    });
    add({
      key: `sprite-${index}`,
      title: `${labelName} sprite`,
      status: stringValue(sprite.status) || "completed",
      url: stringValue(sprite.url || sprite.raw_url),
      detail: "训练抠图"
    });
  });
  (sample.label_failures || manualReviewPreviousFailures(sample)).forEach((failure, index) => {
    const processing = failure.processing_artifacts && typeof failure.processing_artifacts === "object" ? (failure.processing_artifacts as Record<string, unknown>) : {};
    const labelName = String(failure.label || failure.accessory_id || `失败项 ${index + 1}`);
    add({ key: `failure-mask-${index}`, title: `${labelName} 失败 mask`, status: stringValue(failure.status) || "failed", url: stringValue(failure.mask_url), detail: stringValue(failure.reason) });
    add({ key: `failure-overlay-${index}`, title: `${labelName} 失败叠加图`, status: stringValue(failure.status) || "failed", url: stringValue(processing.ai_mask_box_overlay_url), detail: stringValue(failure.reason) });
  });
  (sample.synthetic_samples || []).slice(0, 12).forEach((item, index) => {
    add({
      key: `synthetic-${index}`,
      title: `合成训练图 ${index + 1}`,
      status: "completed",
      url: stringValue(item.annotated_url || item.url || item.image_url),
      detail: `box ${stringValue(item.label_count) || "-"}`
    });
  });
  return cards;
}

function autoOptimizeReviewSamples(status?: AiAutoOptimizeStatus) {
  const samples = status?.samples || [];
  const reviewStatuses = new Set(["review_required", "rejected", "failed"]);
  return samples.filter((sample) => reviewStatuses.has(String(sample.label_status || "")));
}

function autoOptimizeManualSamples(status?: AiAutoOptimizeStatus) {
  const samples = status?.samples || [];
  const manualStatuses = new Set(["", "pending", "labeling", "retrying", "review_required", "rejected", "failed"]);
  return samples.filter((sample) => manualStatuses.has(String(sample.label_status || "")));
}

function syntheticTrainingSamples(status?: AiAutoOptimizeStatus) {
  const samples = status?.samples || [];
  return samples.flatMap((sample) =>
    (sample.synthetic_samples || []).map((item, index) => {
      const sourceSampleId = sample.sample_id;
      const url = String(item.url || item.image_url || "");
      const annotatedUrl = String(item.annotated_url || "");
      const labelPath = String(item.labels || item.label_url || "");
      return {
        key: `${sourceSampleId}-${index}-${url || labelPath}`,
        title: `synthetic_${String(index + 1).padStart(4, "0")}`,
        sourceSampleId,
        url,
        annotatedUrl,
        labelPath,
        split: String(item.split || "-"),
        labelCount: Number(item.label_count || 0),
        sampleType: String(item.sample_type || "synthetic")
      };
    })
  );
}

function realBboxTrainingSamples(status?: AiAutoOptimizeStatus) {
  const trainableStatuses = new Set(["trainable", "trainable_bbox_only"]);
  return (status?.samples || [])
    .filter((sample) => trainableStatuses.has(String(sample.label_status || "")) && autoOptimizeReviewHasBbox(sample))
    .map((sample, index) => {
      const sourceSampleId = sample.sample_id;
      const annotatedUrl = autoOptimizeSampleReviewImageUrl(sample);
      return {
        key: `${sourceSampleId}-real-bbox`,
        title: `real_bbox_${String(index + 1).padStart(4, "0")}`,
        sourceSampleId,
        url: autoOptimizeSampleImageUrl(sample),
        annotatedUrl,
        labelPath: "",
        split: "train x3",
        labelCount: autoOptimizeBboxEntryCount(sample),
        sampleType: String(sample.label_status || "real_bbox")
      };
    });
}

function processingItemByType(record: DataAnalysisRecord | null | undefined, type: string) {
  const items = record?.image_processing_items || [];
  if (type === "ai_mask_box_overlay") {
    return items.find((item) => item.type === type && item.metrics?.review_unit === true) || items.find((item) => item.type === type);
  }
  return items.find((item) => item.type === type);
}

function aiImageUrl(record: DataAnalysisRecord) {
  const result = (record.ai_detection_result || {}) as Record<string, unknown>;
  return String(result.annotated_url || result.preview_url || result.output_url || record.image_url || record.source_image?.url || "");
}

function reviewAiImageUrl(record: DataAnalysisRecord) {
  return processingItemByType(record, "ai_detection_overlay")?.url || aiImageUrl(record) || processingItemByType(record, "source_photo")?.url || "";
}

function reviewMaskBoxUrl(record: DataAnalysisRecord) {
  return processingItemByType(record, "ai_mask_box_overlay")?.url || "";
}

function processingStatusLabel(value = "") {
  const labels: Record<string, string> = {
    queued: "排队中",
    pending: "等待中",
    running: "处理中",
    completed: "通过",
    review_required: "需要 review",
    rejected: "待人工确认",
    failed: "失败"
  };
  return labels[value] || value || "未处理";
}

function processingTone(status = ""): "neutral" | "ok" | "warn" | "fail" {
  if (status === "completed") return "ok";
  if (status === "failed") return "fail";
  if (status === "rejected" || status === "review_required") return "warn";
  if (status === "running" || status === "queued" || status === "pending") return "warn";
  return "neutral";
}

function recordTitle(record: DataAnalysisRecord) {
  return record.source_image?.filename || record.record_id || "采集样本";
}

function hiddenItems(record: DataAnalysisRecord) {
  const visibleTypes = new Set(["ai_detection_overlay", "ai_mask_box_overlay", "source_photo"]);
  return (record.image_processing_items || []).filter((item) => !visibleTypes.has(String(item.type || "")));
}

function ImageProcessingMiniTimeline({ items }: { items: DataAnalysisImageProcessingItem[] }) {
  if (!items.length) return <div className="empty-panel compact-empty">没有隐藏的中间产物。</div>;
  return (
    <div className="task-hidden-processing-list">
      {items.map((item) => (
        <article className="image-processing-card" key={item.id}>
          <div className="image-processing-preview">
            {item.url ? <img src={cacheUrl(item.url, String(item.updated_at || item.created_at || ""))} alt={item.label || item.type || "处理图"} /> : <span>无预览</span>}
          </div>
          <div className="image-processing-card-body">
            <div className="image-processing-card-head">
              <strong>{item.label || item.type_label || item.type || "处理项"}</strong>
              <span className={`pill ${processingTone(item.status || "")}`}>{processingStatusLabel(item.status || "")}</span>
            </div>
            <span className="record-meta">{item.reason || item.type || item.id}</span>
          </div>
        </article>
      ))}
    </div>
  );
}

export function TaskDetailPage() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const { taskId = "" } = useParams();
  const decodedTaskId = decodeURIComponent(taskId);
  const [detailAccessoryId, setDetailAccessoryId] = useState("");
  const [reviewSample, setReviewSample] = useState<AiAutoOptimizeSample | null>(null);
  const [pendingReviewAction, setPendingReviewAction] = useState("");
  const [autoOptimizeSettingsOpen, setAutoOptimizeSettingsOpen] = useState(false);
  const [activeDrawer, setActiveDrawer] = useState<"collection" | "manual" | "synthetic" | "dataset" | null>(null);
  const autoOptimizeFormRef = useRef<HTMLFormElement>(null);
  const resourcesQuery = useQuery({
    queryKey: queryKeys.trainingResources(auth.dataUserId),
    queryFn: () => getTrainingResources(auth),
    refetchInterval: 15_000
  });
  const pipelineQuery = useQuery({
    queryKey: queryKeys.pipeline(auth.dataUserId),
    queryFn: () => getPipeline(auth),
    refetchInterval: 15_000
  });

  const task = useMemo(
    () => taskEntriesFromTrainingResources(resourcesQuery.data, pipelineQuery.data).find((entry) => entry.id === decodedTaskId),
    [decodedTaskId, pipelineQuery.data, resourcesQuery.data]
  );
  const relatedDatasets = useMemo(
    () => (resourcesQuery.data?.datasets || []).filter((dataset) => datasetMatchesTask(dataset, task)),
    [resourcesQuery.data?.datasets, task]
  );
  const primaryDatasetId = task?.datasetId || relatedDatasets[0]?.id || "";
  const analysisTaskIds = useMemo(() => {
    if (!task) return [];
    return unique([
      task.sourceId,
      task.aiTaskId || "",
      task.aiModelId || "",
      task.autoOptimizeTaskId || "",
      task.aiBaselineTaskId || "",
      task.aiBaselineModelId || "",
      task.modelRunId || "",
      task.trainingTaskId || "",
      task.sampleTaskId || ""
    ]);
  }, [task]);
  const autoOptimizeTaskId = autoOptimizeTaskIdFor(task);

  const datasetStatus = task?.datasetStatus || "";
  // Frequent polling is only useful while background work can still change the
  // payloads (sample generation / training / auto-optimize capture).
  const taskWorkActive = Boolean(task && ["samples", "training"].includes(task.stage || ""));
  const shouldLoadDataset = Boolean(primaryDatasetId && !["deleted", "missing", "none", "pending"].includes(datasetStatus));
  const datasetQuery = useQuery({
    queryKey: queryKeys.trainingDatasetDetail(primaryDatasetId),
    queryFn: () => getTrainingDatasetDetail(primaryDatasetId),
    enabled: shouldLoadDataset,
    refetchInterval: shouldLoadDataset ? (taskWorkActive ? 10_000 : 30_000) : false
  });
  const autoOptimizeQuery = useQuery({
    queryKey: queryKeys.aiAutoOptimize(auth.dataUserId, autoOptimizeTaskId),
    queryFn: () => getAiTaskAutoOptimize(auth, autoOptimizeTaskId),
    enabled: Boolean(autoOptimizeTaskId),
    refetchInterval: autoOptimizeTaskId ? 10_000 : false
  });
  const autoOptimizeActive = Boolean(autoOptimizeQuery.data?.enabled);
  const analysisQuery = useQuery({
    queryKey: [...queryKeys.dataAnalysisRecords(auth.dataUserId, decodedTaskId), analysisTaskIds.join("|")] as const,
    queryFn: async () => {
      const responses = await Promise.all(analysisTaskIds.map((id) => getDataAnalysisRecords(auth, { taskId: id, limit: 80 })));
      const byId = new Map<string, DataAnalysisRecord>();
      responses.flatMap((response) => response.records || []).forEach((record) => byId.set(record.record_id, record));
      return Array.from(byId.values()).sort((a, b) => Number(b.updated_at || b.created_at || 0) - Number(a.updated_at || a.created_at || 0));
    },
    enabled: Boolean(task && analysisTaskIds.length),
    refetchInterval: task && analysisTaskIds.length ? (taskWorkActive || autoOptimizeActive ? 15_000 : 45_000) : false
  });
  const deleteSampleMutation = useMutation({
    mutationFn: ({ datasetId, sampleName }: { datasetId: string; sampleName: string }) => deleteTrainingDatasetSample(datasetId, sampleName),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.trainingDatasetDetail(primaryDatasetId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.trainingResources(auth.dataUserId) });
      notify({ title: "样本已删除", tone: "success" });
    },
    onError: (error: Error) => notify({ title: "删除样本失败", description: error.message, tone: "error" })
  });
  const pipelineActionMutation = useMutation({
    mutationFn: async ({ action, checked }: { action: "advance" | "pause" | "auto"; checked?: boolean }) => {
      if (!task || task.kind !== "pipeline") throw new Error("当前任务不支持流水线操作");
      if (action === "advance") return advancePipelineTask(task.sourceId);
      if (action === "pause") return pausePipelineTask(task.sourceId);
      return updatePipelineTask(task.sourceId, { auto_advance: Boolean(checked) });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.pipeline(auth.dataUserId) });
      notify({ title: "任务状态已更新", tone: "success" });
    },
    onError: (error: Error) => notify({ title: "任务操作失败", description: error.message, tone: "error" })
  });
  const autoOptimizeMutation = useMutation({
    mutationFn: ({ taskId: nextTaskId, payload }: { taskId: string; payload: Partial<ReturnType<typeof readAutoOptimizePayload>> }) =>
      updateAiTaskAutoOptimize(nextTaskId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.aiAutoOptimize(auth.dataUserId, autoOptimizeTaskId) });
      notify({ title: "自动优化设置已更新", tone: "success" });
    },
    onError: (error: Error) => notify({ title: "自动优化设置失败", description: error.message, tone: "error" })
  });
  const deleteAutoOptimizeSampleMutation = useMutation({
    mutationFn: ({ taskId: nextTaskId, sampleId }: { taskId: string; sampleId: string }) => deleteAiTaskAutoOptimizeSample(nextTaskId, sampleId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.aiAutoOptimize(auth.dataUserId, autoOptimizeTaskId) });
      setReviewSample(null);
      notify({ title: "样本已删除", tone: "success" });
    },
    onError: (error: Error) => notify({ title: "删除样本失败", description: error.message, tone: "error" })
  });
  const retryAutoOptimizeSampleMutation = useMutation({
    mutationFn: ({ taskId: nextTaskId, sampleId }: { taskId: string; sampleId: string }) => retryAiTaskAutoOptimizeSample(nextTaskId, sampleId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.aiAutoOptimize(auth.dataUserId, autoOptimizeTaskId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.dataAnalysisRecords(auth.dataUserId, decodedTaskId) });
      setReviewSample(null);
      notify({ title: "已重新提交检测与标注", tone: "success" });
    },
    onError: (error: Error) => notify({ title: "重试失败", description: error.message, tone: "error" })
  });
  const approveAutoOptimizeSampleMutation = useMutation({
    mutationFn: ({ taskId: nextTaskId, sampleId, mode }: { taskId: string; sampleId: string; mode: "sprite" | "bbox_only" }) =>
      approveAiTaskAutoOptimizeSample(nextTaskId, sampleId, mode),
    onSettled: (_data, _error, variables) => {
      const pendingKey = variables ? `${variables.sampleId}:${variables.mode}` : "";
      setPendingReviewAction((current) => (pendingKey && current === pendingKey ? "" : current));
    },
    onSuccess: (_data, variables) => {
      setReviewSample(null);
      notify({
        title: variables.mode === "bbox_only" ? "当前图片已通过" : "图片和 sprite 已通过",
        description: variables.mode === "bbox_only" ? "它会作为真实框训练样本，不生成 sprite 扩增。" : "它会进入 sprite 扩增训练流程。",
        tone: "success"
      });
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.aiAutoOptimize(auth.dataUserId, autoOptimizeTaskId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dataAnalysisRecords(auth.dataUserId, decodedTaskId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.trainingResources(auth.dataUserId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.pipeline(auth.dataUserId) })
      ]);
    },
    onError: (error: Error) => notify({ title: "人工通过失败", description: error.message, tone: "error" })
  });
  const autoOptimizeLiveSyncKey = [
    autoOptimizeQuery.data?.phase || "",
    autoOptimizeQuery.data?.serving_mode || "",
    autoOptimizeQuery.data?.active_model_id || "",
    autoOptimizeCandidateStatus(autoOptimizeQuery.data),
    autoOptimizeCandidateProgress(autoOptimizeQuery.data),
    Number(autoOptimizeQuery.data?.captured_samples || 0),
    Number(autoOptimizeQuery.data?.projected_training_samples || 0),
    Number(autoOptimizeQuery.data?.candidate_model_count || 0)
  ].join("|");

  useEffect(() => {
    if (!autoOptimizeTaskId || !autoOptimizeQuery.data) return;
    queryClient.invalidateQueries({ queryKey: queryKeys.trainingResources(auth.dataUserId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.pipeline(auth.dataUserId) });
    if (primaryDatasetId) queryClient.invalidateQueries({ queryKey: queryKeys.trainingDatasetDetail(primaryDatasetId) });
  }, [auth.dataUserId, autoOptimizeLiveSyncKey, autoOptimizeQuery.data, autoOptimizeTaskId, primaryDatasetId, queryClient]);

  function handleAutoOptimizeSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const autoTaskId = autoOptimizeTaskId;
    if (!autoTaskId) {
      notify({ title: "当前任务没有可配置的自动优化对象", tone: "error" });
      return;
    }
    autoOptimizeMutation.mutate(
      { taskId: autoTaskId, payload: readAutoOptimizePayload(event.currentTarget) },
      { onSuccess: () => setAutoOptimizeSettingsOpen(false) }
    );
  }

  function handleRestoreAutoOptimizeRecommended() {
    const autoTaskId = autoOptimizeTaskId;
    if (!autoTaskId) {
      notify({ title: "当前任务没有可配置的自动优化对象", tone: "error" });
      return;
    }
    autoOptimizeMutation.mutate(
      { taskId: autoTaskId, payload: recommendedAutoOptimizePayload(autoOptimize) },
      { onSuccess: () => setAutoOptimizeSettingsOpen(false) }
    );
  }

  if (resourcesQuery.isLoading || pipelineQuery.isLoading) return <LoadingState label="正在加载任务详情" />;
  if (resourcesQuery.isError) return <ErrorState error={resourcesQuery.error} action={<button onClick={() => resourcesQuery.refetch()}>重试</button>} />;
  if (pipelineQuery.isError) return <ErrorState error={pipelineQuery.error} action={<button onClick={() => pipelineQuery.refetch()}>重试</button>} />;

  if (!task) return <Navigate to="/training-library?tab=tasks" replace />;

  const records = analysisQuery.data || [];
  const autoOptimize = autoOptimizeQuery.data;
  const dataset = datasetQuery.data?.dataset || relatedDatasets[0] || null;
  const samples = dataset?.samples || [];
  const autoOptimizeDataset = latestAutoOptimizeDataset(autoOptimize);
  const autoOptimizeDatasetId = String(autoOptimizeDataset.id || "");
  const reviewSampleArtifacts = reviewSample ? autoOptimizeSampleIntermediateArtifacts(reviewSample) : [];
  const reviewSampleCanApproveSprite = canApproveAutoOptimizeSample(reviewSample, "sprite");
  const reviewSampleCanApproveBbox = canApproveAutoOptimizeSample(reviewSample, "bbox_only");
  const reviewSampleTaskId = task.aiTaskId || task.sourceId;
  const currentReviewPending = Boolean(reviewSample?.sample_id && pendingReviewAction.startsWith(`${reviewSample.sample_id}:`));
  const reviewSpritePending = pendingReviewAction === `${reviewSample?.sample_id || ""}:sprite`;
  const reviewBboxPending = pendingReviewAction === `${reviewSample?.sample_id || ""}:bbox_only`;
  const autoOptimizeDatasetName = String(autoOptimizeDataset.display_name || autoOptimizeDatasetId || "");
  const autoOptimizeDatasetCount = Number(
    autoOptimizeDataset.sample_count ||
      autoOptimizeDataset.synthetic_sample_count ||
      autoOptimize?.dataset_synthetic_sample_count ||
      autoOptimize?.generated_synthetic_sample_count ||
      autoOptimize?.synthetic_sample_count ||
      0
  );
  const supportsAutoOptimize = Boolean(autoOptimizeTaskId);
  const autoOptimizeLocked = Boolean(autoOptimizeTaskId && (autoOptimize?.phase === "promoted" || autoOptimize?.serving_mode === "promoted_yolo"));
  const reviewSamples = autoOptimizeReviewSamples(autoOptimizeQuery.data);
  const manualSamples = autoOptimizeManualSamples(autoOptimizeQuery.data);
  const syntheticSamples = syntheticTrainingSamples(autoOptimizeQuery.data);
  const realBboxSamples = realBboxTrainingSamples(autoOptimizeQuery.data);
  const trainingPreviewSamples = [...realBboxSamples, ...syntheticSamples];
  const autoOptimizeSamples = autoOptimize?.samples || [];
  const autoOptimizeRecordIds = new Set(autoOptimizeSamples.map((sample) => sample.record_id).filter(Boolean));
  const displayRecords = autoOptimizeTaskId && autoOptimizeQuery.data
    ? records.filter((record) => autoOptimizeRecordIds.has(record.record_id))
    : records;
  const manualRecordIds = new Set(manualSamples.map((sample) => sample.record_id).filter(Boolean));
  const collectionRecords = displayRecords.filter((record) => !manualRecordIds.has(record.record_id));
  const autoOptimizeThreshold = autoOptimizeSettingNumber(autoOptimize, "min_trainable_samples", 200);
  const autoOptimizePositiveRequired = autoOptimizeSettingNumber(autoOptimize, "min_positive_samples", autoOptimizeThreshold);
  const autoOptimizeNegativeRequired = autoOptimizeSettingNumber(autoOptimize, "min_negative_samples", 0);
  const autoOptimizeSamplesPerRealImage = autoOptimizeSettingNumber(autoOptimize, "samples_per_real_image", Number(autoOptimize?.samples_per_real_image || 12));
  const autoOptimizeNegativePerRealImage = autoOptimizeSettingNumber(autoOptimize, "negative_samples_per_real_image", Number(autoOptimize?.negative_samples_per_real_image || 0));
  const autoOptimizePositiveDerivativesPerRealImage = autoOptimizeStatusNumber(
    autoOptimize,
    "positive_derivatives_per_real_image",
    Math.max(0, autoOptimizeSamplesPerRealImage - autoOptimizeNegativePerRealImage)
  );
  const autoOptimizeDerivativeSplit = autoOptimizeNegativePerRealImage > 0
    ? `派生 ${autoOptimizeSamplesPerRealImage} 张/图：正 ${autoOptimizePositiveDerivativesPerRealImage} / 负 ${autoOptimizeNegativePerRealImage}`
    : `派生 ${autoOptimizeSamplesPerRealImage} 张/图`;
  const autoOptimizeTrainingEpochs = autoOptimizeSettingNumber(autoOptimize, "training_epochs", 60);
  const autoOptimizeTrainingImageSize = autoOptimizeSettingNumber(autoOptimize, "training_image_size", 640);
  const autoOptimizeLabelBatchSize = autoOptimizeSettingNumber(autoOptimize, "max_label_jobs_per_cycle", 3);
  const autoOptimizeMaskScore = autoOptimizeSettingNumber(autoOptimize, "mask_compare_min_score", 0.72);
  const autoOptimizeShadowSamples = autoOptimizeSettingNumber(autoOptimize, "shadow_min_samples", 80);
  const autoOptimizeShadowAgreement = autoOptimizeSettingNumber(autoOptimize, "shadow_min_agreement", 0.98);
  const maskReviewCount = displayRecords.filter((record) => {
    const box = processingItemByType(record, "ai_mask_box_overlay");
    return box?.status === "rejected" || box?.status === "failed";
  }).length;
  const rejectedCount = maskReviewCount + reviewSamples.length;
  const baseProgress = progressValue(task, displayRecords.length, Number(dataset?.sample_count || samples.length || 0), rejectedCount);
  const progress = autoOptimizeDisplayProgress(task, autoOptimize, baseProgress);
  const displayStatus = autoOptimizeDisplayStatus(task, autoOptimize);
  const displayStage = autoOptimizeDisplayStage(task, autoOptimize);
  const progressLabel = isAiDrivenTask(task) ? "YOLO 可接管成熟度" : "任务推进进度";
  const showPipelineAutoAdvance = task.kind === "pipeline" && !isAiDrivenTask(task);
  const rows = accessoryRows(task);
  const spritePool = (autoOptimize?.sprite_pool || []).filter((item) => item && typeof item === "object") as Array<Record<string, unknown>>;
  const datasetDeleted = Boolean(task.datasetId && ["deleted", "missing"].includes(task.datasetStatus || ""));
  const modelDeleted = Boolean((task.modelRunId || task.trainingTaskId) && ["deleted", "missing"].includes(task.modelStatus || ""));
  const datasetDetail = autoOptimizeDatasetName
    ? autoOptimizeDatasetName
    : datasetDeleted
    ? `${task.datasetId} · ${resourceStatusLabel(task.datasetStatus)}`
    : dataset?.display_name || dataset?.id || (task.datasetId ? resourceStatusLabel(task.datasetStatus) : "未绑定样本库");
  const candidateModel = latestAutoOptimizeCandidate(autoOptimize);
  const candidateStatus = autoOptimizeCandidateStatus(autoOptimize);
  const candidateProgress = autoOptimizeCandidateProgress(autoOptimize);
  const liveModelValue = isAutoOptimizePromoted(autoOptimize)
    ? autoOptimize?.active_model_id || ""
    : isAutoOptimizeTraining(autoOptimize)
      ? String(candidateModel.model_id || candidateModel.job_id || "训练候选")
      : "";
  const liveModelDetail = isAutoOptimizePromoted(autoOptimize)
    ? "自动优化模型已上线，采集已停止"
    : isAutoOptimizeTraining(autoOptimize)
      ? [candidateStatus || autoOptimize?.phase || "training", candidateProgress ? `${candidateProgress}%` : ""].filter(Boolean).join(" · ")
      : "";
  const fallbackModelValue = isAiDrivenTask(task)
    ? task.modelLabel || task.modelRunId || "-"
    : task.modelLabel || task.modelRunId || task.aiModelId || "-";
  const fallbackModelDetail = isAiDrivenTask(task) && !task.modelRunId
    ? "等待样本训练"
    : task.optimizationRoute || task.detectionMethod || "自动路由";
  const modelValue = liveModelValue || (modelDeleted ? resourceStatusLabel(task.modelStatus) : fallbackModelValue);
  const modelDetail = liveModelDetail || (modelDeleted ? `${task.modelRunId || task.trainingTaskId} · ${resourceStatusLabel(task.modelStatus)}` : fallbackModelDetail);
  const detectionModes = detectionAccessModes(task, autoOptimize);
  const modelTone = isAutoOptimizePromoted(autoOptimize) ? "ok" : isAutoOptimizeTraining(autoOptimize) ? "warn" : resourceStatusTone(task.modelStatus);

  return (
    <section className="view active task-detail-view">
      <header className="page-head">
        <div>
          <h2>{task.label}</h2>
          <p className="page-desc">任务详情会汇总当前进度、检测入口、采集样本、自动标注结果和训练集。</p>
        </div>
        <div className="page-head-actions">
          <Link className="secondary compact-action" to="/training-library?tab=tasks">
            返回任务库
          </Link>
          <Link className="primary compact-action" to={task.path}>
            <Play size={15} aria-hidden="true" />
            开始检测
          </Link>
        </div>
      </header>

      <section className="panel page-panel task-detail-panel">
        <div className="task-detail-head">
          <div>
            <span className="record-meta">{task.kind === "pipeline" ? "配件组合任务" : "AI 检测任务"}</span>
            <h3>{task.label}</h3>
            <p>{task.meta}</p>
          </div>
          <span className={`pill ${taskStatusTone(displayStatus)}`}>{displayStatus}</span>
        </div>

        <div className="task-progress-block">
          <div className="progress-copy">
            <strong>{progressLabel} · {displayStage}</strong>
            <span>{Math.round(progress)}%</span>
          </div>
          <div className="native-progress" aria-hidden="true">
            <span style={{ width: `${progress}%` }} />
          </div>
          <p>{isAiDrivenTask(task) ? "AI 任务的进度表示 YOLO 从无到可生产接管的成熟度；只有候选模型质量达标并上线后才会跑满。" : "进度表示当前任务在样本、训练和模型上线流程中的推进状态。"}</p>
        </div>

        <div className="metric-grid">
          <MetricCard label="当前状态" value={displayStatus} detail={displayStage} tone={taskStatusTone(displayStatus)} />
          <MetricCard label="采集记录" value={displayRecords.length} detail={analysisQuery.isFetching ? "刷新中" : `待人工确认 ${rejectedCount}`} tone={rejectedCount ? "warn" : "neutral"} />
          <MetricCard label="训练样本" value={datasetDeleted ? resourceStatusLabel(task.datasetStatus) : autoOptimizeDatasetCount || dataset?.sample_count || samples.length || 0} detail={datasetDetail} tone={resourceStatusTone(task.datasetStatus)} />
          <MetricCard label="训练模型" value={modelValue} detail={modelDetail} tone={modelTone} />
        </div>

        <div className="task-detail-grid">
          <p><strong>当前阶段</strong><span>{displayStage}</span></p>
          <p><strong>状态指标</strong><span>{task.lastError || displayStatus}</span></p>
          {task.expectedProductionCount ? <p><strong>预计产量</strong><span>{task.expectedProductionCount}</span></p> : null}
          <p><strong>检测台方式</strong><span>{detectionModes.length ? detectionModes.join(" / ") : "-"}</span></p>
          {showPipelineAutoAdvance ? <p><strong>自动推进</strong><span>{task.autoAdvance === false ? "已关闭" : "开启"}</span></p> : null}
          <p><strong>任务 ID</strong><span>{task.sourceId}</span></p>
        </div>

        <div className="task-detail-section">
          <strong>检测配件与数量</strong>
          <div className="task-accessory-requirements">
            {rows.length ? (
              rows.map((row) => (
                <button className="task-accessory-requirement task-accessory-link" key={row.id} type="button" onClick={() => setDetailAccessoryId(row.id)}>
                  <strong>{row.name}</strong>
                  <em>x{row.count}</em>
                </button>
              ))
            ) : (
              <span className="pill neutral">配件信息待同步</span>
            )}
          </div>
        </div>

        {showPipelineAutoAdvance ? (
          <div className="task-detail-section task-inline-controls">
            <strong>任务操作</strong>
            <div className="card-action-row">
              <button
                className="secondary compact-action"
                type="button"
                disabled={pipelineActionMutation.isPending || task.status === "completed" || task.status === "已上线"}
                onClick={() => pipelineActionMutation.mutate({ action: "advance" })}
              >
                {pipelineActionMutation.isPending ? <Loader2 className="spin" size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
                推进下一步
              </button>
              <button
                className="secondary compact-action"
                type="button"
                disabled={pipelineActionMutation.isPending}
                onClick={() => pipelineActionMutation.mutate({ action: "pause" })}
              >
                <PauseCircle size={14} aria-hidden="true" />
                暂停
              </button>
              <label className="pipeline-auto-mini task-auto-toggle">
                <input
                  type="checkbox"
                  checked={task.autoAdvance !== false}
                  disabled={pipelineActionMutation.isPending}
                  onChange={(event) => pipelineActionMutation.mutate({ action: "auto", checked: event.currentTarget.checked })}
                />
                自动推进
              </label>
            </div>
          </div>
        ) : null}

        {supportsAutoOptimize ? (
          <div className="task-detail-section task-inline-controls">
            <strong>自动优化训练</strong>
            <div className="resource-card-head">
              <span className={`pill ${autoOptimizeLocked || autoOptimize?.enabled ? "ok" : "neutral"}`}>
                {autoOptimizePhaseText(autoOptimize)}
              </span>
              <span className="record-meta">模式：{autoOptimize?.serving_mode || "api_primary"} · 接管模型：{autoOptimize?.active_model_id || "-"}</span>
              <button
                className="secondary compact-action"
                type="button"
                disabled={autoOptimizeQuery.isLoading || !autoOptimizeTaskId}
                onClick={() => setAutoOptimizeSettingsOpen(true)}
              >
                <SlidersHorizontal size={14} aria-hidden="true" />
                训练设置
              </button>
              <button
                className="secondary compact-action"
                type="button"
                disabled={autoOptimizeMutation.isPending || !autoOptimizeTaskId || autoOptimizeLocked}
                onClick={() => autoOptimizeMutation.mutate({ taskId: autoOptimizeTaskId, payload: { enabled: !Boolean(autoOptimize?.enabled) } })}
              >
                {autoOptimizeLocked ? "已停止采集" : autoOptimize?.enabled ? "关闭自动优化" : "开启自动优化"}
              </button>
            </div>
            <div className="metric-grid compact-metric-grid">
              <MetricCard label="真实样本" value={String(autoOptimizeNumber(autoOptimize, "captured_samples"))} detail={autoOptimizeDerivativeSplit} />
              <MetricCard label="预计训练图" value={String(autoOptimizeStatusNumber(autoOptimize, "projected_training_samples"))} detail={`阈值 ${autoOptimizeThreshold}`} />
              <MetricCard label="Sprite Pool" value={String(autoOptimizeStatusNumber(autoOptimize, "sprite_pool_count"))} detail={`合成 ${autoOptimizeStatusNumber(autoOptimize, "synthetic_sample_count")} 张`} />
              <MetricCard label="负样本" value={String(autoOptimizeNumber(autoOptimize, "negative_samples"))} detail={`要求 ${autoOptimizeNegativeRequired}`} />
              <MetricCard label="训练参数" value={`${autoOptimizeTrainingEpochs} epochs`} detail={`${autoOptimizeTrainingImageSize}px`} />
              <MetricCard label="Shadow" value={`${Math.round(autoOptimizeNumber(autoOptimize, "shadow_agreement") * 1000) / 10}%`} detail={`${autoOptimizeNumber(autoOptimize, "shadow_runs")} 次对比`} />
            </div>
            <div className="auto-optimize-settings-summary">
              <span>
                单图派生 <strong>{autoOptimizeSamplesPerRealImage}</strong>
              </span>
              <span>
                派生负样本 <strong>{autoOptimizeNegativePerRealImage}</strong>
              </span>
              <span>
                并行标注 <strong>{autoOptimizeLabelBatchSize}</strong>
              </span>
              <span>
                Mask 分 <strong>{autoOptimizeMaskScore}</strong>
              </span>
              <span>
                Epoch <strong>{autoOptimizeTrainingEpochs}</strong>
              </span>
              <span>
                尺寸 <strong>{autoOptimizeTrainingImageSize}</strong>
              </span>
              <span>
                Shadow 样本 <strong>{autoOptimizeShadowSamples}</strong>
              </span>
              <span>
                Shadow 一致率 <strong>{autoOptimizeShadowAgreement}</strong>
              </span>
            </div>
            <p className="hint-line">{autoOptimizeDetailText(autoOptimize)}</p>
          </div>
        ) : null}

        <div className="task-detail-section">
          <strong>自动化路线</strong>
          <div className="task-route-steps">
            <span>VLM 初始检测</span>
            <ChevronRight size={14} aria-hidden="true" />
            <span>生产采样</span>
            <ChevronRight size={14} aria-hidden="true" />
            <span>自动标注</span>
            <ChevronRight size={14} aria-hidden="true" />
            <span>YOLO 训练</span>
            <ChevronRight size={14} aria-hidden="true" />
            <span>影子对比 / 自动切换</span>
          </div>
        </div>
      </section>

      <section className="panel page-panel task-detail-panel task-drawer-entry-panel">
        <div className="section-title">
          <div>
            <h3>任务过程数据</h3>
            <p>过程图和训练图片默认收起，需要时打开对应入口查看。</p>
          </div>
          <span className="pill neutral">{displayRecords.length + syntheticSamples.length + samples.length} 项</span>
        </div>
        <div className="task-drawer-entry-grid">
          <button className="task-drawer-entry" type="button" onClick={() => setActiveDrawer("collection")}>
            <span>采集样本与自动标注</span>
            <strong>{collectionRecords.length} 张实拍图</strong>
            <em>仅展示正常进入自动标注链路的数据</em>
          </button>
          <button className="task-drawer-entry" type="button" onClick={() => setActiveDrawer("manual")}>
            <span>需要人工处理</span>
            <strong>{manualSamples.length} 张</strong>
            <em>未处理 / 失败 / 需要 review</em>
          </button>
          <button className="task-drawer-entry" type="button" onClick={() => setActiveDrawer("synthetic")}>
            <span>合成训练图</span>
            <strong>{syntheticSamples.length} 张</strong>
            <em>{spritePool.length} 个 sprite · {autoOptimizeDerivativeSplit}</em>
          </button>
          <button className="task-drawer-entry" type="button" onClick={() => setActiveDrawer("dataset")}>
            <span>正式训练集</span>
            <strong>{datasetDeleted ? resourceStatusLabel(task.datasetStatus) : `${samples.length || dataset?.sample_count || autoOptimizeDatasetCount || 0} 张`}</strong>
            <em>{dataset ? dataset.display_name || dataset.id : autoOptimizeDatasetName || "尚未打包"}</em>
          </button>
        </div>
      </section>

      {activeDrawer === "collection" ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="采集样本与自动标注">
          <section className="modal-panel wide task-drawer-modal">
            <header className="modal-head">
              <div>
                <span>{task.label}</span>
                <h2>采集样本与自动标注</h2>
              </div>
              <div className="modal-head-actions">
                <Link className="secondary compact-action" to={`/data-analysis?task_id=${encodeURIComponent(task.aiTaskId || task.sourceId)}`}>
                  <Eye size={15} aria-hidden="true" />
                  数据分析
                </Link>
                <button className="icon-button" type="button" aria-label="关闭" onClick={() => setActiveDrawer(null)}>
                  <X size={18} aria-hidden="true" />
                </button>
              </div>
            </header>
            <div className="modal-body task-drawer-modal-body">
              <div className="task-drawer-summary">
                <MetricCard label="实拍记录" value={collectionRecords.length} detail={analysisQuery.isFetching ? "刷新中" : "当前任务"} />
                <MetricCard label="已隔离人工处理" value={manualSamples.length} detail="不在此窗口展示" tone={manualSamples.length ? "warn" : "neutral"} />
                <MetricCard label="自动标注通过链路" value={String(Math.max(0, collectionRecords.length))} detail="AI 检测 + AI mask box" />
              </div>
              {analysisQuery.isLoading ? <LoadingState label="正在加载样本处理记录" /> : null}
              {analysisQuery.isError ? <ErrorState error={analysisQuery.error} action={<button onClick={() => analysisQuery.refetch()}>重试</button>} /> : null}
              {!analysisQuery.isLoading && !collectionRecords.length ? (
                <div className="empty-panel compact-empty">这个任务还没有采集到可展示的检测样本。</div>
              ) : (
                <div className="image-processing-review-list drawer-review-list">
                  {collectionRecords.map((record) => {
                    const aiUrl = reviewAiImageUrl(record);
                    const boxUrl = reviewMaskBoxUrl(record);
                    const boxItem = processingItemByType(record, "ai_mask_box_overlay");
                    const sampleForRecord = autoOptimizeSamples.find((sample) => sample.record_id && sample.record_id === record.record_id);
                    const statusForRecord = sampleForRecord?.label_status || boxItem?.status || "";
                    const token = String(record.updated_at || record.created_at || record.record_id);
                    return (
                      <article className="image-processing-review-card" key={record.record_id}>
                        <div className="image-processing-review-head">
                          <div>
                            <strong>{recordTitle(record)}</strong>
                            <span>{record.task?.name || record.task?.id || task.label}</span>
                          </div>
                          <span className={`pill ${sampleForRecord ? autoOptimizeSampleTone(sampleForRecord.label_status || "") : processingTone(statusForRecord)}`}>
                            {sampleForRecord ? autoOptimizeSampleStatusLabel(sampleForRecord.label_status || "", sampleForRecord.sample_type || "") : processingStatusLabel(statusForRecord)}
                          </span>
                        </div>
                        <div className="image-processing-review-pair">
                          <section>
                            <div className="image-processing-review-label"><span>AI 检测结果</span></div>
                            <div className="image-processing-review-frame">
                              {aiUrl ? <img src={cacheUrl(aiUrl, token)} alt="AI 检测结果" /> : <span>AI 检测图未保存</span>}
                            </div>
                          </section>
                          <section>
                            <div className="image-processing-review-label"><span>生成检测框</span></div>
                            <div className="image-processing-review-frame">
                              {boxUrl ? <img src={cacheUrl(boxUrl, String(boxItem?.updated_at || token))} alt="生成检测框" /> : <span>{boxItem?.reason || "等待 AI mask 生成 bbox 图"}</span>}
                            </div>
                          </section>
                        </div>
                        {sampleForRecord ? (
                          <div className="image-processing-review-actions">
                            <button className="secondary compact-action" type="button" onClick={() => setReviewSample(sampleForRecord)}>
                              <Eye size={15} aria-hidden="true" />
                              处理样本
                            </button>
                            <span className="record-meta">{autoOptimizeSampleReason(sampleForRecord)}</span>
                          </div>
                        ) : null}
                        <details className="image-processing-hidden-detail">
                          <summary>查看隐藏中间产物</summary>
                          <ImageProcessingMiniTimeline items={hiddenItems(record)} />
                        </details>
                      </article>
                    );
                  })}
                </div>
              )}
            </div>
          </section>
        </div>
      ) : null}

      {activeDrawer === "manual" ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="需要人工处理">
          <section className="modal-panel wide task-drawer-modal">
            <header className="modal-head">
              <div>
                <span>{task.label}</span>
                <h2>需要人工处理</h2>
              </div>
              <button className="icon-button" type="button" aria-label="关闭" onClick={() => setActiveDrawer(null)}>
                <X size={18} aria-hidden="true" />
              </button>
            </header>
            <div className="modal-body task-drawer-modal-body">
              <div className="task-drawer-summary">
                <MetricCard label="待处理" value={manualSamples.length} detail="从正常采集窗口隔离" tone={manualSamples.length ? "warn" : "neutral"} />
                <MetricCard label="待 Review" value={reviewSamples.length} detail="AI 结果与 mask 需确认" tone={reviewSamples.length ? "warn" : "neutral"} />
                <MetricCard label="可操作" value="删除 / 重试" detail="后续可接 Agent 审阅" />
              </div>
              {manualSamples.length ? (
                <div className="manual-review-grid">
                  {manualSamples.map((sample) => {
                    const record = sample.record_id ? records.find((item) => item.record_id === sample.record_id) : undefined;
                    const aiUrl = record ? reviewAiImageUrl(record) : autoOptimizeSampleImageUrl(sample);
                    const boxUrl = record ? reviewMaskBoxUrl(record) : String(sample.label_artifacts?.review_overlay_url || "");
                    const token = String(sample.updated_at || sample.created_at || sample.sample_id);
                    return (
                      <article className="manual-review-card" key={sample.sample_id}>
                        <div className="image-processing-review-head">
                          <div>
                            <strong>{autoOptimizeSampleTitle(sample)}</strong>
                            <span>{sample.sample_id}</span>
                          </div>
                          <span className={`pill ${autoOptimizeSampleTone(sample.label_status || "")}`}>
                            {autoOptimizeSampleStatusLabel(sample.label_status || "", sample.sample_type || "")}
                          </span>
                        </div>
                        <div className="manual-review-preview-pair">
                          <div className="image-processing-review-frame">
                            {aiUrl ? <img src={cacheUrl(aiUrl, token)} alt="AI 检测结果" /> : <span>没有原图预览</span>}
                          </div>
                          <div className="image-processing-review-frame">
                            {boxUrl ? <img src={cacheUrl(boxUrl, token)} alt="AI mask 生成框" /> : <span>没有生成框预览</span>}
                          </div>
                        </div>
                        <p className="record-meta">{autoOptimizeSampleReason(sample)}</p>
                        <div className="image-processing-review-actions">
                          <button className="secondary compact-action" type="button" onClick={() => setReviewSample(sample)}>
                            <Eye size={15} aria-hidden="true" />
                            打开处理
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              ) : (
                <div className="empty-panel compact-empty">没有需要人工处理的数据。</div>
              )}
            </div>
          </section>
        </div>
      ) : null}

      {activeDrawer === "synthetic" ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="合成训练图">
          <section className="modal-panel wide task-drawer-modal">
            <header className="modal-head">
              <div>
                <span>{task.label}</span>
                <h2>合成训练图</h2>
              </div>
              <button className="icon-button" type="button" aria-label="关闭" onClick={() => setActiveDrawer(null)}>
                <X size={18} aria-hidden="true" />
              </button>
            </header>
            <div className="modal-body task-drawer-modal-body">
              <div className="task-drawer-summary">
                <MetricCard label="可用 Sprite" value={String(spritePool.length)} detail="来自真实图 AI mask" />
                <MetricCard label="真实画框原图" value={String(realBboxSamples.length)} detail="通过 / 人工通过 · train x3" />
                <MetricCard label="Sprite 合成图" value={String(syntheticSamples.length)} detail={`${autoOptimizeSamplesPerRealImage} 张/真实图`} />
                <MetricCard label="预计训练样本" value={String(autoOptimizeStatusNumber(autoOptimize, "projected_positive_training_samples"))} detail="含真实原图权重" />
              </div>
              {autoOptimizeSamples.length ? (
                <div className="task-synthetic-sample-list drawer-synthetic-status-list">
                  {autoOptimizeSamples.map((sample) => (
                    <button className="task-synthetic-sample-row" key={sample.sample_id} type="button" onClick={() => setReviewSample(sample)}>
                      <span>{autoOptimizeSampleTitle(sample)}</span>
                      <strong>{sample.synthetic_status === "completed" ? `已生成 ${sample.synthetic_count || 0} 张` : sample.synthetic_status === "running" ? `生成中 ${sample.synthetic_count || 0}` : sample.synthetic_status === "failed" ? "生成失败" : sample.label_status === "trainable" ? "等待生成" : autoOptimizeSampleStatusLabel(sample.label_status || "", sample.sample_type || "")}</strong>
                      {sample.synthetic_error ? <em>{sample.synthetic_error}</em> : null}
                    </button>
                  ))}
                </div>
              ) : null}
              {trainingPreviewSamples.length ? (
                <section className="training-resource-thumb-grid drawer-training-grid">
                  {trainingPreviewSamples.map((item) => (
                    <figure className="gallery-card" key={item.key}>
                      {item.annotatedUrl || item.url ? (
                        <img src={cacheUrl(item.annotatedUrl || item.url, item.key)} alt={item.title} loading="lazy" />
                      ) : (
                        <div className="asset-empty">无预览</div>
                      )}
                      <figcaption>
                        <strong>{item.title}</strong>
                        <span>{item.split} · box {item.labelCount} · {item.sourceSampleId}</span>
                      </figcaption>
                    </figure>
                  ))}
                </section>
              ) : (
                <div className="empty-panel compact-empty">还没有可展示的训练图。真实检测图通过 AI mask 或人工通过后会显示画框原图，sprite 完成后会显示合成图。</div>
              )}
              {spritePool.length ? (
                <details className="image-processing-hidden-detail">
                  <summary>查看 Sprite Pool</summary>
                  <div className="training-resource-thumb-grid task-sprite-pool-grid">
                    {spritePool.map((sprite, index) => {
                      const url = String(sprite.url || sprite.raw_url || "");
                      const label = String(sprite.label || sprite.accessory_id || `sprite ${index + 1}`);
                      return (
                        <figure className="gallery-card" key={`${String(sprite.source_sample_id || "")}-${String(sprite.accessory_id || "")}-${index}`}>
                          {url ? <img src={cacheUrl(url, String(sprite.source_sample_id || index))} alt={label} loading="lazy" /> : <div className="asset-empty">无预览</div>}
                          <figcaption>
                            <strong>{label}</strong>
                            <span>{String(sprite.status || "available")} · {String(sprite.source_sample_id || "-")}</span>
                          </figcaption>
                        </figure>
                      );
                    })}
                  </div>
                </details>
              ) : null}
            </div>
          </section>
        </div>
      ) : null}

      {activeDrawer === "dataset" ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="正式训练集">
          <section className="modal-panel wide task-drawer-modal">
            <header className="modal-head">
              <div>
                <span>{task.label}</span>
                <h2>正式训练集</h2>
              </div>
              <button className="icon-button" type="button" aria-label="关闭" onClick={() => setActiveDrawer(null)}>
                <X size={18} aria-hidden="true" />
              </button>
            </header>
            <div className="modal-body task-drawer-modal-body">
              <div className="task-drawer-summary">
                <MetricCard label="训练集状态" value={datasetDeleted ? resourceStatusLabel(task.datasetStatus) : dataset ? "可用" : "未生成"} detail={dataset?.display_name || task.datasetId || "-"} tone={resourceStatusTone(task.datasetStatus)} />
                <MetricCard label="图片数" value={String(samples.length || dataset?.sample_count || 0)} detail="正式 dataset manifest" />
                <MetricCard label="相关数据集" value={String(relatedDatasets.length)} detail="与任务配件匹配" />
              </div>
              {primaryDatasetId && datasetQuery.isLoading ? <LoadingState label="正在加载训练集" /> : null}
              {primaryDatasetId && datasetQuery.isError && !datasetDeleted ? <ErrorState error={datasetQuery.error} action={<button onClick={() => datasetQuery.refetch()}>重试</button>} /> : null}
              {datasetDeleted ? (
                <div className="empty-panel compact-empty">
                  这个任务绑定的样本库 {task.datasetId} {resourceStatusLabel(task.datasetStatus)}，任务本身已保留。
                </div>
              ) : !dataset ? (
                <div className="empty-panel compact-empty">这个任务还没有绑定正式训练集。合成训练图达到阈值后会打包成 dataset。</div>
              ) : samples.length ? (
                <section className="training-resource-thumb-grid drawer-training-grid">
                  {samples.map((sample) => {
                    const url = samplePublicUrl(sample);
                    const name = sampleDisplayName(sample);
                    return (
                      <figure className="gallery-card" key={`${name}-${sample.split || ""}`}>
                        {url ? <img src={cacheUrl(url, name)} alt={name} loading="lazy" /> : <div className="asset-empty">无预览</div>}
                        <figcaption>
                          <strong>{name}</strong>
                          <span>{sample.is_true ? "True" : "False"} · {sample.split || "-"} · 缺 {sample.missing_count || 0}</span>
                        </figcaption>
                        <button
                          className="secondary compact-action danger"
                          type="button"
                          disabled={deleteSampleMutation.isPending}
                          onClick={() => {
                            if (!window.confirm(`删除样本 ${name}？`)) return;
                            deleteSampleMutation.mutate({ datasetId: dataset.id, sampleName: name });
                          }}
                        >
                          <Trash2 size={15} aria-hidden="true" />
                          删除样本
                        </button>
                      </figure>
                    );
                  })}
                </section>
              ) : (
                <div className="empty-panel compact-empty">训练集已存在，但还没有加载样本缩略图。</div>
              )}
              {relatedDatasets.length > 1 ? (
                <div className="task-related-datasets">
                  {relatedDatasets.map((item) => (
                    <span className="pill neutral" key={item.id}>{item.display_name || item.id} · {item.sample_count || item.samples?.length || 0}</span>
                  ))}
                </div>
              ) : null}
            </div>
          </section>
        </div>
      ) : null}

      {autoOptimizeSettingsOpen ? (
        <div className="modal-backdrop" role="presentation">
          <form
            className="modal-panel auto-optimize-settings-modal"
            role="dialog"
            aria-modal="true"
            aria-label="自动优化训练设置"
            ref={autoOptimizeFormRef}
            onSubmit={handleAutoOptimizeSubmit}
          >
            <header className="modal-head">
              <div>
                <h3>自动优化训练设置</h3>
                <span>当前任务：{task.label}</span>
              </div>
              <button className="secondary compact-action" type="button" onClick={() => setAutoOptimizeSettingsOpen(false)} disabled={autoOptimizeMutation.isPending}>
                取消
              </button>
            </header>
            <div className="modal-body settings-form">
              <div className="form-grid settings-option-grid">
                <label className="toggle-row">
                  <input name="enabled" type="checkbox" defaultChecked={Boolean(autoOptimize?.enabled)} key={`enabled-${autoOptimizeTaskId}-${autoOptimize?.enabled}`} />
                  <span>开启自动优化</span>
                </label>
                <label className="toggle-row">
                  <input name="auto_promote" type="checkbox" defaultChecked={autoOptimize?.settings?.auto_promote !== false} key={`promote-${autoOptimizeTaskId}-${String(autoOptimize?.settings?.auto_promote)}`} />
                  <span>通过阈值后自动接管</span>
                </label>
              </div>
              <div className="form-grid">
                <label className="field">
                  单张真实图派生总数
                  <input name="samples_per_real_image" type="number" min="1" max="50" defaultValue={autoOptimizeSamplesPerRealImage} key={`spr-${autoOptimizeTaskId}-${autoOptimizeSamplesPerRealImage}`} />
                </label>
                <label className="field">
                  派生负样本数
                  <input name="negative_samples_per_real_image" type="number" min="0" max="20" defaultValue={autoOptimizeNegativePerRealImage} key={`npr-${autoOptimizeTaskId}-${autoOptimizeNegativePerRealImage}`} />
                </label>
                <label className="field">
                  训练触发总阈值
                  <input name="min_trainable_samples" type="number" min="1" max="20000" defaultValue={autoOptimizeThreshold} key={`min-${autoOptimizeTaskId}-${autoOptimizeThreshold}`} />
                </label>
                <label className="field">
                  正样本最低数
                  <input name="min_positive_samples" type="number" min="1" max="20000" defaultValue={autoOptimizePositiveRequired} key={`positive-${autoOptimizeTaskId}-${autoOptimizePositiveRequired}`} />
                </label>
                <label className="field">
                  负样本最低数
                  <input name="min_negative_samples" type="number" min="0" max="20000" defaultValue={autoOptimizeNegativeRequired} key={`negative-${autoOptimizeTaskId}-${autoOptimizeNegativeRequired}`} />
                </label>
              </div>
              <div className="form-grid">
                <label className="field">
                  训练 Epoch
                  <input name="training_epochs" type="number" min="1" max="500" defaultValue={autoOptimizeTrainingEpochs} key={`epochs-${autoOptimizeTaskId}-${autoOptimizeTrainingEpochs}`} />
                </label>
                <label className="field">
                  训练图像尺寸
                  <input name="training_image_size" type="number" min="320" max="2048" step="32" defaultValue={autoOptimizeTrainingImageSize} key={`image-size-${autoOptimizeTaskId}-${autoOptimizeTrainingImageSize}`} />
                </label>
              </div>
              <div className="form-grid">
                <label className="field">
                  每轮 AI mask 数
                  <input name="max_label_jobs_per_cycle" type="number" min="1" max="50" defaultValue={autoOptimizeLabelBatchSize} key={`jobs-${autoOptimizeTaskId}-${autoOptimizeLabelBatchSize}`} />
                </label>
                <label className="field">
                  Mask 对比最低分
                  <input name="mask_compare_min_score" type="number" min="0" max="1" step="0.01" defaultValue={autoOptimizeMaskScore} key={`mask-${autoOptimizeTaskId}-${autoOptimizeMaskScore}`} />
                </label>
                <label className="field">
                  Shadow 样本数
                  <input name="shadow_min_samples" type="number" min="1" max="20000" defaultValue={autoOptimizeShadowSamples} key={`shadow-${autoOptimizeTaskId}-${autoOptimizeShadowSamples}`} />
                </label>
                <label className="field">
                  Shadow 一致率
                  <input name="shadow_min_agreement" type="number" min="0" max="1" step="0.001" defaultValue={autoOptimizeShadowAgreement} key={`agree-${autoOptimizeTaskId}-${autoOptimizeShadowAgreement}`} />
                </label>
              </div>
              <p className="hint-line">训练阈值按合成训练图计算；Epoch 和图像尺寸会随下一次自动优化候选训练一起提交。</p>
            </div>
            <footer className="modal-footer">
              <button
                className="secondary compact-action auto-optimize-restore-action"
                type="button"
                onClick={handleRestoreAutoOptimizeRecommended}
                disabled={autoOptimizeMutation.isPending || !autoOptimizeTaskId}
              >
                {autoOptimizeMutation.isPending ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <RotateCcw size={16} aria-hidden="true" />}
                恢复推荐配置
              </button>
              <button className="secondary compact-action" type="button" onClick={() => setAutoOptimizeSettingsOpen(false)} disabled={autoOptimizeMutation.isPending}>
                取消
              </button>
              <button className="primary compact-action" type="submit" disabled={autoOptimizeMutation.isPending || !autoOptimizeTaskId}>
                <Save size={16} aria-hidden="true" />
                保存训练设置
              </button>
            </footer>
          </form>
        </div>
      ) : null}

      {reviewSample ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="人工 Review 样本">
          <section className="modal-panel wide task-review-modal">
            <header className="modal-head">
              <div>
                <span>{reviewSample.sample_id}</span>
                <h2>{autoOptimizeSampleTitle(reviewSample)}</h2>
              </div>
              <button className="icon-button" type="button" aria-label="关闭" onClick={() => setReviewSample(null)}>
                <X size={18} aria-hidden="true" />
              </button>
            </header>
            <div className="modal-body task-review-modal-body">
              <div className="task-review-modal-grid">
                <section className="task-review-image-pane">
                  <div className="image-processing-review-label"><span>复合叠加图</span></div>
                  <div className="task-review-image-frame">
                    {autoOptimizeSampleReviewImageUrl(reviewSample) ? (
                      <img src={cacheUrl(autoOptimizeSampleReviewImageUrl(reviewSample), reviewSample.sample_id)} alt="复合叠加图" />
                    ) : (
                      <span>没有可展示的叠加图</span>
                    )}
                  </div>
                </section>
                <section className="task-review-info-pane">
                  <div className="task-review-info-head">
                    <span className={`pill ${autoOptimizeSampleTone(reviewSample.label_status || "")}`}>
                      {autoOptimizeSampleStatusLabel(reviewSample.label_status || "", reviewSample.sample_type || "")}
                    </span>
                    <strong>{autoOptimizeSampleReason(reviewSample)}</strong>
                  </div>
                  <div className="task-review-info-list">
                    <p><strong>样本类型</strong><span>{reviewSample.sample_type || "-"}</span></p>
                    <p><strong>候选配件</strong><span>{(reviewSample.candidate_accessories || []).map((item) => String(item.label || item.accessory_id || "")).filter(Boolean).join("、") || "无，作为负样本"}</span></p>
                    <p><strong>AI mask 标签</strong><span>{(reviewSample.labels || []).map((item) => String(item.label || item.accessory_id || "")).filter(Boolean).join("、") || "无"}</span></p>
                    <p><strong>失败原因</strong><span>{autoOptimizeSampleFailureText(reviewSample) || "-"}</span></p>
                    {reviewSample.manual_review?.status === "approved" ? (
                      <p><strong>人工处理</strong><span>{`已通过${reviewSample.manual_approved_by ? ` · ${reviewSample.manual_approved_by}` : ""}`}</span></p>
                    ) : null}
                  </div>
                </section>
              </div>
              <section className="task-review-artifacts-section">
                <div className="image-processing-review-label"><span>中间产物</span></div>
                {reviewSampleArtifacts.length ? (
                  <div className="task-hidden-processing-list task-review-artifact-list">
                    {reviewSampleArtifacts.map((artifact) => (
                      <article className="image-processing-card" key={artifact.key}>
                        <div className="image-processing-preview">
                          {artifact.url ? <img src={cacheUrl(artifact.url, `${reviewSample.sample_id}-${artifact.key}-${reviewSample.updated_at || ""}`)} alt={artifact.title} loading="lazy" /> : <span>无预览</span>}
                        </div>
                        <div className="image-processing-card-body">
                          <div className="image-processing-card-head">
                            <strong>{artifact.title}</strong>
                            {artifact.status ? <span className={`pill ${processingTone(artifact.status)}`}>{processingStatusLabel(artifact.status)}</span> : null}
                          </div>
                          {artifact.detail ? <span className="record-meta">{artifact.detail}</span> : null}
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="empty-panel compact-empty">这个样本还没有可展示的中间产物。</div>
                )}
                <details className="image-processing-hidden-detail task-review-debug-detail">
                  <summary>查看判定详情</summary>
                  <pre>{JSON.stringify({
                    label_status: reviewSample.label_status,
                    label_reject_reason: reviewSample.label_reject_reason,
                    label_failures: reviewSample.label_failures || [],
                    manual_review: reviewSample.manual_review || {},
                    class_check: reviewSample.label_artifacts?.class_check || {},
                    review_meta: reviewSample.label_artifacts?.review_meta || {},
                    synthetic_status: reviewSample.synthetic_status || "",
                    synthetic_count: reviewSample.synthetic_count || 0,
                    synthetic_error: reviewSample.synthetic_error || ""
                  }, null, 2)}</pre>
                </details>
              </section>
            </div>
            <footer className="modal-footer">
              <button className="secondary compact-action" type="button" onClick={() => setReviewSample(null)}>
                关闭
              </button>
              <button
                className="primary compact-action"
                type="button"
                disabled={currentReviewPending || !reviewSampleTaskId || !reviewSampleCanApproveBbox}
                onClick={() => {
                  setPendingReviewAction(`${reviewSample.sample_id}:bbox_only`);
                  approveAutoOptimizeSampleMutation.mutate({ taskId: reviewSampleTaskId, sampleId: reviewSample.sample_id, mode: "bbox_only" });
                }}
              >
                {reviewBboxPending ? <Loader2 className="spin" size={14} aria-hidden="true" /> : <CheckCircle2 size={14} aria-hidden="true" />}
                仅通过当前图
              </button>
              <button
                className="secondary compact-action"
                type="button"
                disabled={currentReviewPending || !reviewSampleTaskId || !reviewSampleCanApproveSprite}
                onClick={() => {
                  setPendingReviewAction(`${reviewSample.sample_id}:sprite`);
                  approveAutoOptimizeSampleMutation.mutate({ taskId: reviewSampleTaskId, sampleId: reviewSample.sample_id, mode: "sprite" });
                }}
              >
                {reviewSpritePending ? <Loader2 className="spin" size={14} aria-hidden="true" /> : <CheckCircle2 size={14} aria-hidden="true" />}
                图片 + sprite
              </button>
              <button
                className="secondary compact-action"
                type="button"
                disabled={retryAutoOptimizeSampleMutation.isPending || !reviewSampleTaskId}
                onClick={() => retryAutoOptimizeSampleMutation.mutate({ taskId: reviewSampleTaskId, sampleId: reviewSample.sample_id })}
              >
                {retryAutoOptimizeSampleMutation.isPending ? <Loader2 className="spin" size={14} aria-hidden="true" /> : <RefreshCw size={14} aria-hidden="true" />}
                重试
              </button>
              <button
                className="secondary compact-action danger"
                type="button"
                disabled={deleteAutoOptimizeSampleMutation.isPending || !reviewSampleTaskId}
                onClick={() => {
                  if (!window.confirm("确认删除这个自动优化样本？")) return;
                  deleteAutoOptimizeSampleMutation.mutate({ taskId: reviewSampleTaskId, sampleId: reviewSample.sample_id });
                }}
              >
                <Trash2 size={14} aria-hidden="true" />
                删除
              </button>
            </footer>
          </section>
        </div>
      ) : null}

      {detailAccessoryId ? (
        <AccessoryDetailModal
          accessoryId={detailAccessoryId}
          onClose={() => setDetailAccessoryId("")}
          onChanged={() => {
            queryClient.invalidateQueries({ queryKey: queryKeys.trainingResources(auth.dataUserId) });
            queryClient.invalidateQueries({ queryKey: queryKeys.pipeline(auth.dataUserId) });
          }}
          onTextCrop={() => {
            notify({ title: "文字裁剪请在配件库完成", description: "任务详情里会保持当前页面，不跳转。", tone: "info" });
          }}
        />
      ) : null}
    </section>
  );
}

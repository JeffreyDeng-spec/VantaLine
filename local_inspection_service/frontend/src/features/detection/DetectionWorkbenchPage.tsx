import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Camera, FileImage, Play, RefreshCw, Save, Settings, Video, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { analyzeImage, analyzeVideo, getAiTasks, getServiceStatus, queryKeys, updateRules, updateTaskRules } from "../../api/queries";
import type {
  AiDetectionLibraryTask,
  DetectionItem,
  DetectionResult,
  DetectionRuleItem,
  DetectionVideoFrame,
  ServiceStatusResponse,
  SpecializedModelTask,
  StatusModel
} from "../../api/types";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { MetricCard } from "../../components/MetricCard";
import { useToast } from "../../components/ToastProvider";
import { modelVariantLabel } from "../../utils/format";
import { useAuth } from "../auth/auth-context";

type WorkbenchMode = "inspect" | "ai";
type SourceMode = "image" | "video" | "camera";

const AI_TASK_MODEL_PREFIX = "ai_detection__task_";
const SOURCE_TABS: Array<{ value: SourceMode; label: string; Icon: LucideIcon }> = [
  { value: "image", label: "图片", Icon: FileImage },
  { value: "video", label: "视频", Icon: Video },
  { value: "camera", label: "摄像头", Icon: Camera }
];

function isAiModel(model: StatusModel | Record<string, unknown> | null | undefined) {
  return Boolean(model?.is_ai_detection || model?.variant === "ai_detection" || String(model?.id || "").startsWith(AI_TASK_MODEL_PREFIX));
}

function aiTaskModelId(task: AiDetectionLibraryTask | null | undefined) {
  if (!task?.id) return "";
  return task.model_id || `${AI_TASK_MODEL_PREFIX}${task.id}`;
}

function formatPercent(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return `${Math.round(numeric * 1000) / 10}%`;
}

function formatConfidence(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return numeric.toFixed(3);
}

function formatAiStatus(value: unknown) {
  const status = String(value || "");
  if (status === "ready") return "就绪";
  if (status === "missing_api_key") return "缺少 Key";
  if (status === "disabled") return "未启用";
  if (status === "restricted") return "受限";
  return status || "检查中";
}

function modelOptionLabel(model: StatusModel) {
  return modelVariantLabel(model) || model.label || model.id;
}

function modelOptionMeta(model: StatusModel) {
  if (isAiModel(model)) return "AI 检测";
  if (model.exists) return model.label || model.description || "可用";
  return `${model.label || model.description || ""} 文件缺失`.trim() || "文件缺失";
}

function classLabel(item: { class_id: number; label?: string; name?: string }) {
  return item.label || item.name || `Class ${item.class_id}`;
}

function taskLabel(task: SpecializedModelTask, fallback = "训练任务") {
  const names = (task.accessory_names || []).filter(Boolean);
  return task.label || (names.length ? names.join(" + ") : task.task_id || fallback);
}

function defaultTaskLabel(status: ServiceStatusResponse | undefined) {
  const requiredNames = (status?.rule?.required_classes || [])
    .map((classId) => status?.classes?.find((item) => Number(item.class_id) === Number(classId))?.label)
    .filter(Boolean);
  return requiredNames.length ? requiredNames.join(" + ") : "通用配件合集";
}

function uniqueRows<T>(items: T[], keyFor: (item: T) => string) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = keyFor(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function ruleItemKey(item: DetectionRuleItem | string) {
  return typeof item === "string" ? item : String(item.class_id ?? item.label ?? "");
}

function ruleItemLabel(item: DetectionRuleItem | string) {
  return typeof item === "string" ? item : String(item.label ?? item.class_name ?? item.class_id ?? "-");
}

function ruleItemValue(item: DetectionRuleItem | string, key: "found" | "required") {
  if (typeof item === "string") return key === "found" ? "是" : "是";
  const value = item[key];
  if (value === true) return "是";
  if (value === false) return "否";
  return value === undefined || value === null || value === "" ? "-" : String(value);
}

function detectionRows(result: DetectionResult | null, requiredCounts?: Record<string, number>) {
  const rule = result?.rule;
  if (!rule) {
    return (result?.detections || []).map((item) => ({
      key: String(item.accessory_id ?? item.class_id ?? item.label ?? item.class_name ?? Math.random()),
      label: String(item.label ?? item.class_name ?? item.accessory_id ?? item.class_id ?? "-"),
      found: item.present === false ? "否" : String(item.found ?? item.count ?? "是"),
      required: String(item.required ?? (item.accessory_id ? requiredCounts?.[String(item.accessory_id)] : undefined) ?? "-"),
      confidence: formatConfidence(item.confidence ?? item.max_confidence)
    }));
  }

  if (rule.match_policy === "ai_presence") {
    const present = (rule.present || []).map((item) => String(item));
    const missing = (rule.missing || []).map((item) => String(item));
    return uniqueRows([...present, ...missing], String).map((accessoryId) => {
      const detection = (result?.detections || []).find((item) => String(item.accessory_id || "") === accessoryId);
      const isMissing = missing.includes(accessoryId);
      return {
        key: accessoryId,
        label: String(detection?.label || accessoryId),
        found: isMissing ? "否" : "是",
        required: String(requiredCounts?.[accessoryId] ?? "是"),
        confidence: formatConfidence(detection?.confidence)
      };
    });
  }

  const missingKeys = new Set((rule.missing || []).map(ruleItemKey));
  return uniqueRows([...(rule.present || []), ...(rule.missing || [])], ruleItemKey).map((item) => ({
    key: ruleItemKey(item),
    label: ruleItemLabel(item),
    found: typeof item === "string" ? (missingKeys.has(item) ? "否" : "是") : ruleItemValue(item, "found"),
    required: typeof item === "string" ? "是" : ruleItemValue(item, "required"),
    confidence: typeof item === "string" ? "-" : formatConfidence(item.max_confidence)
  }));
}

function videoMissingRows(result: DetectionResult | null, requiredCounts?: Record<string, number>) {
  const frames = result?.frames || [];
  if (!frames.length) return [];
  const missing = uniqueRows(
    frames.flatMap((frame) => frame.missing || []),
    ruleItemKey
  );
  if (!missing.length) return detectionRows(result, requiredCounts);
  return missing.map((item) => ({
    key: ruleItemKey(item),
    label: ruleItemLabel(item),
    found: "否",
    required: typeof item === "string" ? String(requiredCounts?.[item] ?? "是") : ruleItemValue(item, "required"),
    confidence: typeof item === "string" ? "-" : formatConfidence(item.max_confidence)
  }));
}

function aiMetaText(result: DetectionResult | null) {
  const ai = result?.ai || {};
  if (ai.timed_out) return `AI 超时：${String(ai.error || "超过检测时间")}`;
  if (ai.error) return `AI 错误：${String(ai.error)}`;
  if (ai.frame_count !== undefined) {
    const pieces = [`${ai.frame_count} 帧`];
    if (ai.first_error) pieces.push(String(ai.first_error));
    if (ai.total_latency_ms !== undefined) pieces.push(`${ai.total_latency_ms} ms`);
    return pieces.join(" / ");
  }
  const pieces: string[] = [];
  if (ai.provider_status) pieces.push(String(ai.provider_status));
  if (ai.latency_ms !== undefined) pieces.push(`${ai.latency_ms} ms`);
  if (ai.fallback_model) pieces.push(`备用 ${String(ai.fallback_model)}`);
  return pieces.join(" / ") || "-";
}

function previewUrl(result: DetectionResult | null) {
  const url = result?.annotated_url || result?.preview_url || result?.frames?.find((frame) => frame.annotated_url)?.annotated_url || "";
  if (!url) return "";
  const token = encodeURIComponent(result?.request_id || String(Date.now()));
  return `${url}${url.includes("?") ? "&" : "?"}t=${token}`;
}

function resultDebugPayload(result: DetectionResult | null) {
  if (!result) return { message: "暂无检测结果。" };
  return {
    request_id: result.request_id,
    passed: result.passed,
    model: result.model,
    ai: result.ai || null,
    rule: result.rule || null,
    detections: result.detections || [],
    annotated_url: result.annotated_url || result.preview_url || "",
    video: Array.isArray(result.frames)
      ? {
          sampled_frames: result.sampled_frames || 0,
          passed_frames: result.passed_frames || 0,
          pass_rate: result.pass_rate || 0,
          frames: result.frames
        }
      : null
  };
}

async function captureVideoFrame(video: HTMLVideoElement | null, prefix: string) {
  if (!video) throw new Error("摄像头画面尚未准备好");
  if (video.paused && video.srcObject) await video.play().catch(() => undefined);
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  if (!video.videoWidth || !video.videoHeight) throw new Error("摄像头画面尚未准备好");
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("无法读取摄像头画面");
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((next) => (next ? resolve(next) : reject(new Error("拍照失败"))), "image/jpeg", 0.92);
  });
  return new File([blob], `${prefix}_${Date.now()}.jpg`, { type: "image/jpeg" });
}

function DetectionMetrics({
  result,
  mode,
  source,
  requiredCounts
}: {
  result: DetectionResult | null;
  mode: WorkbenchMode;
  source: SourceMode;
  requiredCounts?: Record<string, number>;
}) {
  const rows = source === "video" ? videoMissingRows(result, requiredCounts) : detectionRows(result, requiredCounts);
  const detectionCount = result?.frames?.length
    ? `${result.passed_frames || 0}/${result.sampled_frames || result.frames.length} 帧`
    : result?.detections?.length ?? "-";
  const passRate = result?.frames?.length ? formatPercent(result.pass_rate) : mode === "ai" ? aiMetaText(result) : "-";
  return (
    <section className="panel page-panel detection-metrics-panel">
      <div className="metric-grid">
        <MetricCard label="结论" value={result ? (result.passed ? "通过" : "不通过") : "-"} tone={result ? (result.passed ? "ok" : "fail") : "neutral"} />
        <MetricCard label="检测数量" value={detectionCount} detail={source === "video" ? "采样帧" : "检测项"} />
        <MetricCard label={mode === "ai" ? "AI 响应" : "通过率"} value={passRate} />
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>配件</th>
              <th>检测到</th>
              <th>要求</th>
              <th>置信度</th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              rows.map((row) => (
                <tr key={row.key}>
                  <td>{row.label}</td>
                  <td>{row.found}</td>
                  <td>{row.required}</td>
                  <td>{row.confidence}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={4}>暂无检测结果。</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {result?.frames?.length ? (
        <div className="frame-summary-list">
          {result.frames.slice(0, 24).map((frame: DetectionVideoFrame) => (
            <span className={`pill ${frame.passed ? "ok" : "fail"}`} key={`${frame.frame_index}-${frame.timestamp_seconds}`}>
              #{frame.frame_index ?? "-"} · {frame.timestamp_seconds ?? 0}s · {frame.passed ? "通过" : "不通过"} · {frame.detections ?? 0}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export function DetectionWorkbenchPage({ mode }: { mode: WorkbenchMode }) {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [source, setSource] = useState<SourceMode>("image");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState("__default__");
  const [selectedModelId, setSelectedModelId] = useState("");
  const [selectedAiTaskId, setSelectedAiTaskId] = useState("");
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [cameraStatus, setCameraStatus] = useState("支持本机摄像头和已连接的 USB / 外接摄像头。");
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState<DetectionResult | null>(null);
  const [error, setError] = useState("");
  const [debugOpen, setDebugOpen] = useState(false);
  const [rulesOpen, setRulesOpen] = useState(false);
  const isAi = mode === "ai";
  const canViewDiagnostics = auth.user.role === "admin";

  const statusQuery = useQuery({
    queryKey: queryKeys.serviceStatus(auth.dataUserId),
    queryFn: () => getServiceStatus(auth),
    refetchInterval: 30_000
  });
  const aiTasksQuery = useQuery({
    queryKey: queryKeys.aiTasks(auth.dataUserId),
    queryFn: () => getAiTasks(auth),
    enabled: isAi
  });
  const globalRuleMutation = useMutation({
    mutationFn: updateRules,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.serviceStatus(auth.dataUserId) });
      notify({ title: "规则已保存", tone: "success" });
      setRulesOpen(false);
    },
    onError: (nextError: Error) => notify({ title: "规则保存失败", description: nextError.message, tone: "error" })
  });
  const taskRuleMutation = useMutation({
    mutationFn: ({ taskId, payload }: { taskId: string; payload: { confidence_threshold: number; required_accessory_counts: Record<string, number> } }) =>
      updateTaskRules(taskId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.serviceStatus(auth.dataUserId) });
      notify({ title: "任务规则已保存", tone: "success" });
      setRulesOpen(false);
    },
    onError: (nextError: Error) => notify({ title: "任务规则保存失败", description: nextError.message, tone: "error" })
  });

  const status = statusQuery.data;
  const taskOptions = useMemo(() => {
    const defaults = status?.available_models || [];
    return [
      {
        id: "__default__",
        label: defaultTaskLabel(status),
        meta: "通用检测任务",
        models: defaults,
        accessory_names: [],
        accessory_labels: {},
        required_accessory_counts: {},
        confidence_threshold: status?.rule?.confidence_threshold
      },
      ...(status?.specialized_model_tasks || []).map((task) => ({
        id: task.task_id,
        label: taskLabel(task),
        meta: `${task.models?.length || 0} 个模型`,
        models: task.models || [],
        accessory_names: task.accessory_names || [],
        accessory_labels: task.accessory_labels || task.models?.[0]?.accessory_labels || {},
        required_accessory_counts: task.required_accessory_counts || task.models?.[0]?.required_accessory_counts || {},
        confidence_threshold: task.confidence_threshold ?? task.models?.[0]?.confidence_threshold
      }))
    ];
  }, [status]);
  const currentTask = taskOptions.find((task) => task.id === selectedTaskId) || taskOptions[0];
  const modelOptions = currentTask?.models || [];
  const aiTasks = aiTasksQuery.data?.tasks || status?.ai_detection_tasks || [];
  const selectedAiTask = aiTasks.find((task) => task.id === selectedAiTaskId) || null;
  const selectedModel = modelOptions.find((model) => model.id === selectedModelId) || null;
  const selectedAiModelId = aiTaskModelId(selectedAiTask);
  const activeModelId = isAi ? selectedAiModelId : selectedModelId;
  const requiredCounts = isAi ? selectedAiTask?.required_accessory_counts : undefined;
  const resultImage = previewUrl(result);
  const title = isAi ? "AI 检测" : "检测工作台";
  const statusBadge = isAi
    ? formatAiStatus(status?.ai_detection && typeof status.ai_detection === "object" ? status.ai_detection.status : "")
    : status?.model_exists
      ? "模型已加载"
      : "模型未就绪";
  const rulesBusy = globalRuleMutation.isPending || taskRuleMutation.isPending;
  const isDefaultTask = !isAi && selectedTaskId === "__default__";
  const defaultRequiredClasses = new Set((status?.rule?.required_classes || []).map(Number));
  const defaultMinCounts = status?.rule?.min_counts || {};
  const taskRequiredCounts = currentTask?.required_accessory_counts || selectedModel?.required_accessory_counts || {};
  const taskAccessoryLabels = currentTask?.accessory_labels || selectedModel?.accessory_labels || {};
  const taskAccessoryIds = Object.keys(taskRequiredCounts).length
    ? Object.keys(taskRequiredCounts)
    : (selectedModel?.selected_accessory_ids || []);
  const taskRuleRows = taskAccessoryIds.map((accessoryId, index) => ({
    id: accessoryId,
    label:
      taskAccessoryLabels[accessoryId] ||
      currentTask?.accessory_names?.[index] ||
      selectedModel?.accessory_names?.[index] ||
      accessoryId,
    count: taskRequiredCounts[accessoryId] || 1
  }));
  const ruleThreshold = Number(
    isDefaultTask
      ? status?.rule?.confidence_threshold
      : currentTask?.confidence_threshold ?? selectedModel?.confidence_threshold ?? status?.rule?.confidence_threshold ?? 0.25
  ) || 0.25;

  useEffect(() => {
    if (!taskOptions.length) return;
    if (!taskOptions.some((task) => task.id === selectedTaskId)) {
      setSelectedTaskId("__default__");
      return;
    }
    const options = (taskOptions.find((task) => task.id === selectedTaskId) || taskOptions[0]).models || [];
    if (!options.some((model) => model.id === selectedModelId && (model.exists || isAiModel(model)))) {
      const fallback = selectedTaskId === "__default__"
        ? options.find((model) => model.id === status?.active_model_id && (model.exists || isAiModel(model))) || options.find((model) => model.exists || isAiModel(model))
        : options.find((model) => model.exists || isAiModel(model));
      setSelectedModelId(fallback?.id || "");
    }
  }, [selectedModelId, selectedTaskId, status?.active_model_id, taskOptions]);

  useEffect(() => {
    if (!isAi || !aiTasks.length) return;
    if (!aiTasks.some((task) => task.id === selectedAiTaskId)) {
      setSelectedAiTaskId(aiTasks[0]?.id || "");
    }
  }, [aiTasks, isAi, selectedAiTaskId]);

  useEffect(() => {
    return () => {
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [stream]);

  async function refreshCameras() {
    if (!navigator.mediaDevices?.enumerateDevices) {
      setDevices([]);
      setCameraStatus("当前浏览器不支持摄像头枚举。");
      return [];
    }
    const next = (await navigator.mediaDevices.enumerateDevices()).filter((device) => device.kind === "videoinput");
    setDevices(next);
    if (!selectedDeviceId && next[0]?.deviceId) setSelectedDeviceId(next[0].deviceId);
    setCameraStatus(next.length ? `检测到 ${next.length} 个摄像头。` : "未检测到摄像头。");
    return next;
  }

  async function startCamera(deviceId = selectedDeviceId) {
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraStatus("当前浏览器不支持摄像头预览。");
      return;
    }
    setBusy("camera");
    setError("");
    try {
      stream?.getTracks().forEach((track) => track.stop());
      const nextStream = await navigator.mediaDevices.getUserMedia({
        video: deviceId ? { deviceId: { exact: deviceId } } : true,
        audio: false
      });
      setStream(nextStream);
      if (videoRef.current) {
        videoRef.current.srcObject = nextStream;
        await videoRef.current.play();
      }
      const track = nextStream.getVideoTracks()[0];
      const settings = track?.getSettings?.() || {};
      if (settings.deviceId) setSelectedDeviceId(settings.deviceId);
      await refreshCameras();
      setCameraStatus(`摄像头已连接：${track?.label || "当前摄像头"}`);
    } catch (nextError) {
      const message = nextError instanceof Error ? nextError.message : String(nextError);
      setCameraStatus(`摄像头不可用：${message}`);
      setError(message);
      notify({ title: "摄像头不可用", description: message, tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function runAnalysis(kind: SourceMode, file: File) {
    if (!activeModelId) {
      notify({ title: isAi ? "请选择 AI 检测任务" : "请选择可用模型", tone: "error" });
      return;
    }
    setBusy(kind);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("model_id", activeModelId);
      const next = kind === "video" ? await analyzeVideo(form) : await analyzeImage(form);
      setResult(next);
      setSource(kind);
      notify({ title: kind === "video" ? "视频分析完成" : isAi ? "AI 图片检测完成" : "图片检测完成", tone: "success" });
    } catch (nextError) {
      const message = nextError instanceof Error ? nextError.message : String(nextError);
      setError(message);
      notify({ title: "检测失败", description: message, tone: "error" });
    } finally {
      setBusy("");
    }
  }

  async function runCamera() {
    try {
      if (!stream) await startCamera();
      const file = await captureVideoFrame(videoRef.current, isAi ? "ai_camera_capture" : "camera_capture");
      await runAnalysis("camera", file);
    } catch (nextError) {
      const message = nextError instanceof Error ? nextError.message : String(nextError);
      setError(message);
      notify({ title: "摄像头检测失败", description: message, tone: "error" });
    }
  }

  function handleRulesSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const confidence_threshold = Number(data.get("confidence_threshold") || ruleThreshold);
    if (isDefaultTask) {
      globalRuleMutation.mutate({
        confidence_threshold,
        required_classes: (status?.classes || [])
          .filter((item) => data.get(`required_${item.class_id}`) === "on")
          .map((item) => item.class_id),
        min_counts: Object.fromEntries(
          (status?.classes || []).map((item) => [
            String(item.class_id),
            Math.max(1, Number(data.get(`count_${item.class_id}`) || defaultMinCounts[String(item.class_id)] || 1))
          ])
        )
      });
      return;
    }
    const required_accessory_counts = Object.fromEntries(
      taskRuleRows
        .filter((item) => data.get(`required_${item.id}`) === "on")
        .map((item) => [
          item.id,
          Math.max(1, Number(data.get(`count_${item.id}`) || item.count || 1))
        ])
    );
    if (!Object.keys(required_accessory_counts).length) {
      notify({ title: "至少保留一个必检配件", tone: "error" });
      return;
    }
    taskRuleMutation.mutate({
      taskId: selectedTaskId,
      payload: { confidence_threshold, required_accessory_counts }
    });
  }

  if (statusQuery.isLoading || (isAi && aiTasksQuery.isLoading)) return <LoadingState label="正在加载检测工作台" />;
  if (statusQuery.isError) return <ErrorState error={statusQuery.error} action={<button onClick={() => statusQuery.refetch()}>重试</button>} />;
  if (isAi && aiTasksQuery.isError) return <ErrorState error={aiTasksQuery.error} action={<button onClick={() => aiTasksQuery.refetch()}>重试</button>} />;

  return (
    <section className="view active detection-workbench">
      <header className="page-head">
        <div>
          <h2>{title}</h2>
          <p className="page-desc">
            {isAi ? "基于配件画像调用 AI 检测任务，输出结构化存在性判断。" : "上传图片、视频或使用摄像头，按当前任务规则输出通过 / 不通过。"}
          </p>
        </div>
        <div className="page-head-actions detection-head-actions">
          <strong className={`pill ${statusBadge.includes("就绪") || statusBadge.includes("加载") ? "ok" : "neutral"}`}>{statusBadge}</strong>
          {!isAi ? (
            <button className="secondary compact-action" type="button" onClick={() => setRulesOpen(true)}>
              <Settings size={16} aria-hidden="true" />
              设置规则
            </button>
          ) : null}
          <span className={`result-badge ${result ? (result.passed ? "pass" : "fail") : "waiting"}`}>
            {result ? (result.passed ? "通过" : "不通过") : "等待输入"}
          </span>
        </div>
      </header>

      {isAi ? (
        <section className="panel page-panel detection-toolbar">
          <label className="toolbar-field">
            任务
            <select value={selectedAiTaskId} onChange={(event) => setSelectedAiTaskId(event.currentTarget.value)}>
              {aiTasks.length ? (
                aiTasks.map((task) => (
                  <option value={task.id} key={task.id}>
                    {task.name || task.accessory_names?.join(" + ") || task.id}
                  </option>
                ))
              ) : (
                <option value="">暂无 AI 检测任务</option>
              )}
            </select>
          </label>
          <div className="selected-task-card">
            <strong>{selectedAiTask?.name || "未选择任务"}</strong>
            <span>{selectedAiTask ? `模型 ID：${selectedAiModelId}` : "请先在训练流水线创建 AI 检测任务。"}</span>
            <span>配件：{selectedAiTask?.accessory_names?.length ? selectedAiTask.accessory_names.join("、") : selectedAiTask?.selected_accessory_ids?.join(", ") || "-"}</span>
          </div>
        </section>
      ) : (
        <section className="panel page-panel detection-toolbar">
          <label className="toolbar-field">
            检测任务
            <select value={selectedTaskId} onChange={(event) => {
              setSelectedTaskId(event.currentTarget.value);
              setSelectedModelId("");
            }}>
              {taskOptions.map((task) => (
                <option value={task.id} key={task.id}>
                  {task.label}
                </option>
              ))}
            </select>
          </label>
          <label className="toolbar-field">
            使用模型
            <select value={selectedModelId} onChange={(event) => setSelectedModelId(event.currentTarget.value)}>
              {modelOptions.length ? (
                modelOptions.map((model) => (
                  <option value={model.id} key={model.id} disabled={!model.exists && !isAiModel(model)}>
                    {modelOptionLabel(model)} · {modelOptionMeta(model)}
                  </option>
                ))
              ) : (
                <option value="">暂无可用模型</option>
              )}
            </select>
          </label>
        </section>
      )}

      <div className="inspect-grid">
        <section className="panel page-panel input-panel">
          <div className="section-title">
            <h3>输入源</h3>
          </div>
          <div className="tabbar" role="tablist" aria-label={`${title}输入源`}>
            {SOURCE_TABS.map(({ value, label, Icon }) => (
              <button
                className={`mode-tab ${source === value ? "active" : ""}`}
                type="button"
                role="tab"
                aria-selected={source === value}
                onClick={() => setSource(value)}
                key={value}
              >
                <Icon size={15} aria-hidden="true" />
                {label}
              </button>
            ))}
          </div>

          {source === "image" ? (
            <div className="tabpane active">
              <label className="dropzone">
                <input type="file" accept="image/*" onChange={(event) => setImageFile(event.currentTarget.files?.[0] || null)} />
                <span className="dropzone-file-action">选择图片</span>
                <strong>{isAi ? "上传 AI 检测图片" : "上传检测图片"}</strong>
                <span className="dropzone-file-name">{imageFile?.name || "支持 PNG / JPG / JPEG"}</span>
              </label>
              <button className="primary icon-label" type="button" disabled={!imageFile || Boolean(busy)} onClick={() => imageFile && runAnalysis("image", imageFile)}>
                <Play size={16} aria-hidden="true" />
                {isAi ? "开始 AI 检测" : "开始检测"}
              </button>
            </div>
          ) : null}

          {source === "video" ? (
            <div className="tabpane active">
              <label className="dropzone">
                <input type="file" accept="video/*" onChange={(event) => setVideoFile(event.currentTarget.files?.[0] || null)} />
                <span className="dropzone-file-action">选择视频</span>
                <strong>{isAi ? "上传 AI 检测视频" : "上传检测视频"}</strong>
                <span className="dropzone-file-name">{videoFile?.name || "抽帧检测并应用同一套通过规则"}</span>
              </label>
              <button className="primary icon-label" type="button" disabled={!videoFile || Boolean(busy)} onClick={() => videoFile && runAnalysis("video", videoFile)}>
                <Play size={16} aria-hidden="true" />
                {isAi ? "AI 分析视频" : "分析视频"}
              </button>
            </div>
          ) : null}

          {source === "camera" ? (
            <div className="tabpane active">
              <label className="toolbar-field">
                摄像头
                <select value={selectedDeviceId} onChange={(event) => {
                  setSelectedDeviceId(event.currentTarget.value);
                  if (event.currentTarget.value) startCamera(event.currentTarget.value);
                }}>
                  {devices.length ? (
                    devices.map((device, index) => (
                      <option value={device.deviceId} key={device.deviceId || index}>
                        {device.label || `摄像头 ${index + 1}`}
                      </option>
                    ))
                  ) : (
                    <option value="">未检测到摄像头</option>
                  )}
                </select>
              </label>
              <div className="camera-preview">
                <video ref={videoRef} autoPlay playsInline muted />
                {!stream ? <div className="camera-empty">选择摄像头后显示实时画面</div> : null}
              </div>
              <div className="camera-actions">
                <button className="secondary compact-action" type="button" disabled={busy === "camera"} onClick={async () => {
                  await refreshCameras();
                  await startCamera();
                }}>
                  <RefreshCw size={15} aria-hidden="true" />
                  检测摄像头
                </button>
                <button className="primary compact-action" type="button" disabled={Boolean(busy)} onClick={runCamera}>
                  <Camera size={15} aria-hidden="true" />
                  {isAi ? "拍照 AI 检测" : "拍照检测"}
                </button>
              </div>
              <p className={`hint-line ${error ? "danger-text" : ""}`}>{error || cameraStatus}</p>
            </div>
          ) : null}
        </section>

        <section className="panel page-panel result-panel">
          <div className="section-title title-with-action">
            <h3>{isAi ? "AI 结果预览" : "结果预览"}</h3>
            {canViewDiagnostics ? (
              <button className="secondary compact-action" type="button" onClick={() => setDebugOpen(true)}>
                开发诊断
              </button>
            ) : null}
          </div>
          <div className={`progress-panel ${busy ? "active" : ""}`} aria-live="polite">
            <div className="progress-copy">
              <strong>{busy === "video" ? "正在分析视频" : busy ? "正在检测" : "准备检测"}</strong>
              <span>{busy ? "处理中" : "0%"}</span>
            </div>
            <progress className="native-progress" value={busy ? 72 : 0} max={100} />
            <p>{busy ? "文件已提交，等待服务返回检测结果。" : "上传图片或视频后开始检测。"}</p>
          </div>
          <div className="preview-frame">
            {resultImage ? <img src={resultImage} alt={isAi ? "AI 检测结果" : "带标注的检测结果"} /> : <div className="empty-state">检测标注图会显示在这里</div>}
          </div>
          {error && source !== "camera" ? <p className="hint-line danger-text">{error}</p> : null}
        </section>
      </div>

      <DetectionMetrics result={result} mode={mode} source={source} requiredCounts={requiredCounts} />

      {rulesOpen && !isAi ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-panel wide task-rule-modal" role="dialog" aria-modal="true" aria-label="设置检测通过规则">
            <header className="modal-head">
              <div>
                <h3>设置规则</h3>
                <span>{currentTask?.label || "当前检测任务"}</span>
              </div>
              <button className="icon-only" type="button" aria-label="关闭" onClick={() => setRulesOpen(false)}>
                <X size={18} aria-hidden="true" />
              </button>
            </header>
            <form className="modal-body settings-form" key={selectedTaskId} onSubmit={handleRulesSubmit}>
              <label className="field range-field">
                置信度阈值
                <input
                  name="confidence_threshold"
                  type="range"
                  min="0.05"
                  max="0.95"
                  step="0.05"
                  defaultValue={ruleThreshold}
                  onInput={(event) => {
                    const output = event.currentTarget.closest(".range-field")?.querySelector("output");
                    if (output) output.textContent = Number(event.currentTarget.value).toFixed(2);
                  }}
                />
                <output>{ruleThreshold.toFixed(2)}</output>
              </label>
              {isDefaultTask ? (
                status?.classes?.length ? (
                  <div className="rule-grid task-rule-grid">
                    {status.classes.map((item) => (
                      <label className="check-row" key={item.class_id}>
                        <input
                          name={`required_${item.class_id}`}
                          type="checkbox"
                          defaultChecked={defaultRequiredClasses.has(item.class_id)}
                        />
                        <span>{classLabel(item)}</span>
                        <input
                          name={`count_${item.class_id}`}
                          type="number"
                          min="1"
                          max="99"
                          defaultValue={defaultMinCounts[String(item.class_id)] || 1}
                        />
                      </label>
                    ))}
                  </div>
                ) : (
                  <div className="empty-panel">当前模型未返回类别。</div>
                )
              ) : taskRuleRows.length ? (
                <div className="rule-grid task-rule-grid">
                  {taskRuleRows.map((item) => (
                    <label className="check-row" key={item.id}>
                      <input name={`required_${item.id}`} type="checkbox" defaultChecked={item.count > 0} />
                      <span>{item.label}</span>
                      <input name={`count_${item.id}`} type="number" min="1" max="99" defaultValue={item.count || 1} />
                    </label>
                  ))}
                </div>
              ) : (
                <div className="empty-panel">当前任务没有可配置的配件规则。</div>
              )}
              <div className="button-row">
                <button className="primary compact-action" type="submit" disabled={rulesBusy || (!isDefaultTask && !taskRuleRows.length)}>
                  <Save size={16} aria-hidden="true" />
                  保存规则
                </button>
                <button className="secondary compact-action" type="button" onClick={() => setRulesOpen(false)}>
                  取消
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}

      {debugOpen && canViewDiagnostics ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-panel wide" role="dialog" aria-modal="true" aria-label="检测开发诊断">
            <header className="modal-head">
              <div>
                <h3>开发诊断</h3>
                <span>{result?.request_id || "暂无检测结果"}</span>
              </div>
              <button className="icon-only" type="button" aria-label="关闭" onClick={() => setDebugOpen(false)}>
                <X size={18} aria-hidden="true" />
              </button>
            </header>
            <div className="modal-body">
              <pre className="json-panel">{JSON.stringify(resultDebugPayload(result), null, 2)}</pre>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}

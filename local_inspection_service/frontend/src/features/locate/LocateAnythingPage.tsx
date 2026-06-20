import { useEffect, useMemo, useRef, useState } from "react";
import { Camera, FileImage, Play, RefreshCw, Save, Search, Square, X } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { hasPermission } from "../../app/permissions";
import {
  getLocateAccessories,
  getLocateConfig,
  getLocateStatus,
  inspectLocateAnything,
  locateAnythingPrompt,
  queryKeys,
  saveLocateConfig,
  startLocateRuntime
} from "../../api/queries";
import type { LocateConfigResponse, LocateInspectResult, LocateInspectionRule, LocateSourceItem } from "../../api/types";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { MetricCard } from "../../components/MetricCard";
import { useToast } from "../../components/ToastProvider";
import { useAuth } from "../auth/auth-context";

type LocateRule = LocateInspectionRule & {
  enabled: boolean;
  source?: string;
  task_type?: string;
};

type BusyState = "status" | "runtime" | "config" | "inspect" | "camera" | null;

const DEFAULT_CONFIG = {
  enabled: true,
  endpoint_url: "http://127.0.0.1:8000/locate",
  generation_mode: "fast",
  max_side: 640,
  max_new_tokens: 512,
  timeout_seconds: 300
};

function cacheUrl(url = "", token = "") {
  if (!url) return "";
  const suffix = token || String(Date.now());
  return `${url}${url.includes("?") ? "&" : "?"}t=${encodeURIComponent(suffix)}`;
}

function numeric(value: unknown, fallback: number) {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

function statusText(payload: LocateConfigResponse | null | undefined) {
  if (!payload) return "未检查";
  if (payload.ok || payload.status === "ready") return "服务就绪";
  if (payload.status === "starting") return "启动中";
  if (payload.status === "reachable") return "端点可达";
  if (payload.status === "not_configured" || !payload.configured) return "未启动";
  return "不可用";
}

function statusTone(payload: LocateConfigResponse | null | undefined): "neutral" | "ok" | "fail" | "warn" {
  if (!payload) return "neutral";
  if (payload.ok || payload.status === "ready") return "ok";
  if (payload.status === "starting" || payload.status === "reachable") return "warn";
  if (payload.status === "failed" || payload.status === "unavailable") return "fail";
  return "neutral";
}

function resultBadgeClass(result: LocateInspectResult | null, busy: boolean) {
  if (busy) return "result-badge waiting";
  if (!result) return "result-badge waiting";
  if (result.overall_pass || (result.ok && Array.isArray(result.boxes) && result.boxes.length > 0)) return "result-badge pass";
  return "result-badge fail";
}

function resultStatusText(result: LocateInspectResult | null) {
  if (!result) return "等待检测";
  if (result.overall_pass) return "通过";
  if (result.ok && Array.isArray(result.boxes) && result.boxes.length > 0) return "已定位";
  return result.error || "不通过";
}

function resultTone(result: LocateInspectResult | null): "neutral" | "ok" | "fail" | "warn" {
  if (!result) return "neutral";
  if (result.overall_pass || (result.ok && Array.isArray(result.boxes) && result.boxes.length > 0)) return "ok";
  return result.configured === false ? "warn" : "fail";
}

function locateBoxCount(result: LocateInspectResult | null | undefined) {
  return result?.items?.reduce((total, item) => total + numeric(item.box_count, 0), 0) ?? (Array.isArray(result?.boxes) ? result?.boxes.length : 0);
}

function locateStatusLabel(status = "") {
  return (
    {
      found: "已找到",
      missing: "缺失",
      count_mismatch: "数量不符",
      uncertain: "不确定",
      unexpected: "不应出现",
      not_expected_absent: "未出现"
    }[status] || status || "-"
  );
}

function sourceLabel(item: LocateSourceItem | LocateRule) {
  return String(item.display_label || item.label || item.id);
}

function clampText(value = "", limit = 132) {
  const compact = value.replace(/\s+/g, " ").trim();
  if (compact.length <= limit) return compact;
  return `${compact.slice(0, Math.max(0, limit - 1)).trim()}...`;
}

function compactLocateDescription(item: LocateSourceItem | LocateRule) {
  const parts = [item.source === "accessory" ? "配件" : "类别", item.material_type || ""].filter(Boolean);
  const prompt = clampText(String(item.visual_prompt || ""), 96);
  return [parts.join(" · "), prompt].filter(Boolean).join(" / ");
}

function ruleFromSource(item: LocateSourceItem): LocateRule {
  return {
    id: item.id,
    label: item.label || item.display_label || item.id,
    display_label: item.display_label || item.label || item.id,
    source: item.source || "",
    material_type: item.material_type || "",
    task_type: item.task_type || "",
    visual_prompt: item.visual_prompt || "",
    expected_present: item.default_expected_present !== false,
    expected_count: numeric(item.default_expected_count, 1),
    prompt_override: "",
    enabled: true
  };
}

function matchSourceSearch(item: LocateSourceItem, query: string) {
  if (!query) return true;
  const haystack = [
    item.id,
    item.label,
    item.display_label,
    item.material_type,
    item.source,
    item.visual_prompt,
    ...(item.search_terms || [])
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(query.toLowerCase());
}

function selectedPayload(rules: LocateRule[]) {
  return rules
    .filter((rule) => rule.enabled)
    .map((rule) => ({
      id: rule.id,
      label: rule.label || rule.display_label || rule.id,
      display_label: rule.display_label || rule.label || rule.id,
      source: rule.source || "",
      material_type: rule.material_type || "",
      visual_prompt: rule.visual_prompt || "",
      expected_present: rule.expected_present !== false,
      expected_count: rule.expected_present === false ? 0 : numeric(rule.expected_count, 1),
      prompt_override: String(rule.prompt_override || "").trim()
    }));
}

async function captureVideoFrame(video: HTMLVideoElement | null) {
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
    canvas.toBlob((next) => (next ? resolve(next) : reject(new Error("摄像头采样失败"))), "image/jpeg", 0.9);
  });
  return new File([blob], `locate_camera_${Date.now()}.jpg`, { type: "image/jpeg" });
}

export function LocateAnythingPage() {
  const auth = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const canConfigure = hasPermission(auth.user, "locate_config");
  const [configForm, setConfigForm] = useState(DEFAULT_CONFIG);
  const [manualStatus, setManualStatus] = useState<LocateConfigResponse | null>(null);
  const [rules, setRules] = useState<LocateRule[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [recipeOpen, setRecipeOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [freePrompt, setFreePrompt] = useState("");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [result, setResult] = useState<LocateInspectResult | null>(null);
  const [busy, setBusy] = useState<BusyState>(null);
  const [debugOpen, setDebugOpen] = useState(false);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [cameraStatus, setCameraStatus] = useState("打开摄像头或上传图片。");
  const [frameCount, setFrameCount] = useState(0);
  const [loopActive, setLoopActive] = useState(false);
  const [sampleSeconds, setSampleSeconds] = useState(1);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const loopActiveRef = useRef(false);
  const loopTimerRef = useRef<number | null>(null);
  const inFlightRef = useRef(false);
  const canViewDiagnostics = auth.user.role === "admin";

  const configQuery = useQuery({
    queryKey: queryKeys.locateConfig,
    queryFn: getLocateConfig,
    enabled: canConfigure
  });
  const statusQuery = useQuery({
    queryKey: queryKeys.locateStatus(""),
    queryFn: () => getLocateStatus(""),
    refetchInterval: 30_000
  });
  const accessoriesQuery = useQuery({
    queryKey: queryKeys.locateAccessories(auth.dataUserId),
    queryFn: () => getLocateAccessories(auth)
  });

  const sources = accessoriesQuery.data?.items || [];
  const status = manualStatus || statusQuery.data || configQuery.data || null;
  const enabledRules = selectedPayload(rules);
  const expectedTotal = enabledRules.reduce((total, rule) => total + numeric(rule.expected_count, 1), 0);
  const resultToken = String(result?.diagnostic_url || result?.latency_ms || Date.now());
  const imagePreviewUrl = useMemo(() => (imageFile ? URL.createObjectURL(imageFile) : ""), [imageFile]);
  const resultImage = result?.overlay_url ? cacheUrl(result.overlay_url, resultToken) : imagePreviewUrl;
  const filteredSources = sources.filter((item) => matchSourceSearch(item, searchQuery)).slice(0, 48);
  const boxCount = locateBoxCount(result);

  useEffect(() => () => {
    if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl);
  }, [imagePreviewUrl]);

  useEffect(() => {
    const payload = configQuery.data || statusQuery.data;
    if (!payload) return;
    setConfigForm((current) => ({
      ...current,
      enabled: payload.enabled ?? current.enabled,
      endpoint_url: payload.endpoint_url || current.endpoint_url,
      generation_mode: payload.generation_mode || "fast",
      max_side: numeric(payload.max_side, current.max_side),
      max_new_tokens: numeric(payload.max_new_tokens, current.max_new_tokens),
      timeout_seconds: numeric(payload.timeout_seconds, current.timeout_seconds)
    }));
  }, [configQuery.data, statusQuery.data]);

  useEffect(() => {
    if (!sources.length || rules.length) return;
    const defaults = sources.filter((item) => item.default_selected).slice(0, 4);
    setRules((defaults.length ? defaults : sources.slice(0, 2)).map(ruleFromSource));
  }, [sources, rules.length]);

  function stopCamera() {
    loopActiveRef.current = false;
    setLoopActive(false);
    if (loopTimerRef.current) window.clearTimeout(loopTimerRef.current);
    loopTimerRef.current = null;
    for (const track of streamRef.current?.getTracks?.() || []) track.stop();
    streamRef.current = null;
    setStream(null);
    if (videoRef.current) videoRef.current.srcObject = null;
  }

  useEffect(() => () => stopCamera(), []);

  function updateRule(id: string, updates: Partial<LocateRule>) {
    setRules((current) => current.map((rule) => (rule.id === id ? { ...rule, ...updates } : rule)));
  }

  function removeRule(id: string) {
    setRules((current) => current.filter((rule) => rule.id !== id));
  }

  function upsertRule(source: LocateSourceItem, enabled = true) {
    setRules((current) => {
      if (current.some((rule) => rule.id === source.id)) {
        return current.map((rule) => (rule.id === source.id ? { ...rule, ...ruleFromSource(source), enabled } : rule));
      }
      return [...current, ruleFromSource(source)];
    });
  }

  async function checkStatus(quiet = false) {
    setBusy("status");
    try {
      const payload = await getLocateStatus(canConfigure ? configForm.endpoint_url : "");
      setManualStatus(payload);
      if (!quiet) toast.notify({ title: payload.ok ? "检测服务已就绪" : "检测服务暂不可用", description: payload.message || statusText(payload), tone: payload.ok ? "success" : "info" });
      return payload;
    } catch (error) {
      const message = error instanceof Error ? error.message : "请求失败";
      const payload = { ok: false, configured: true, status: "unavailable", message };
      setManualStatus(payload);
      if (!quiet) toast.notify({ title: "检查检测服务失败", description: message, tone: "error" });
      return payload;
    } finally {
      setBusy(null);
    }
  }

  async function saveConfig() {
    if (!canConfigure) return;
    setBusy("config");
    try {
      const payload = await saveLocateConfig(configForm);
      setManualStatus(payload);
      await queryClient.invalidateQueries({ queryKey: queryKeys.locateConfig });
      toast.notify({ title: "检测服务设置已保存", tone: "success" });
    } catch (error) {
      toast.notify({
        title: "保存检测服务设置失败",
        description: error instanceof Error ? error.message : "请求失败",
        tone: "error"
      });
    } finally {
      setBusy(null);
    }
  }

  async function startRuntime() {
    if (!canConfigure) return;
    setBusy("runtime");
    setManualStatus({ status: "starting", message: "正在启动本地模型...", configured: true });
    try {
      const payload = await startLocateRuntime();
      setManualStatus(payload);
      toast.notify({ title: payload.ok ? "本地模型已就绪" : "本地模型启动中", description: payload.message || statusText(payload), tone: payload.ok ? "success" : "info" });
      window.setTimeout(() => checkStatus(true), 2200);
    } catch (error) {
      const message = error instanceof Error ? error.message : "请求失败";
      setManualStatus({ status: "failed", message, configured: true });
      toast.notify({ title: "启动本地模型失败", description: message, tone: "error" });
    } finally {
      setBusy(null);
    }
  }

  function appendConfigFields(form: FormData) {
    form.append("max_side", String(configForm.max_side));
    form.append("max_new_tokens", String(configForm.max_new_tokens));
    form.append("timeout_seconds", String(configForm.timeout_seconds));
    if (canConfigure && configForm.endpoint_url.trim()) form.append("endpoint_url", configForm.endpoint_url.trim());
  }

  async function runInspectWithFile(file: File | null, quiet = false) {
    if (!file) {
      if (!quiet) toast.notify({ title: "请先选择图片或打开摄像头", tone: "error" });
      return null;
    }
    const payloadRules = selectedPayload(rules);
    if (!payloadRules.length) {
      if (!quiet) toast.notify({ title: "请至少选择一个检测项", tone: "error" });
      return null;
    }
    if (inFlightRef.current) {
      if (!quiet) toast.notify({ title: "检测正在进行", description: "请等待当前帧完成。", tone: "info" });
      return null;
    }
    inFlightRef.current = true;
    setBusy("inspect");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("rules", JSON.stringify(payloadRules));
      appendConfigFields(form);
      const nextResult = await inspectLocateAnything(form);
      setResult(nextResult);
      if (!quiet) toast.notify({ title: nextResult.overall_pass ? "检测通过" : "检测不通过", description: nextResult.error || `${locateBoxCount(nextResult)} 框`, tone: nextResult.overall_pass ? "success" : "info" });
      return nextResult;
    } catch (error) {
      const message = error instanceof Error ? error.message : "请求失败";
      const nextResult = { ok: false, configured: status?.configured, overall_pass: false, error: message, items: [], latency_ms: 0 };
      setResult(nextResult);
      if (!quiet) toast.notify({ title: "检测失败", description: message, tone: "error" });
      return nextResult;
    } finally {
      inFlightRef.current = false;
      setBusy(null);
    }
  }

  async function runPromptWithFile(file: File | null) {
    const prompt = freePrompt.trim();
    if (!file) {
      toast.notify({ title: "请先选择图片或打开摄像头", tone: "error" });
      return null;
    }
    if (!prompt) {
      toast.notify({ title: "请填写提示词", tone: "error" });
      return null;
    }
    if (inFlightRef.current) return null;
    inFlightRef.current = true;
    setBusy("inspect");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("prompt", prompt);
      form.append("generation_mode", "fast");
      appendConfigFields(form);
      const nextResult = await locateAnythingPrompt(form);
      setResult(nextResult);
      toast.notify({ title: nextResult.ok ? "定位完成" : "定位失败", description: nextResult.error || `${nextResult.boxes?.length || 0} 框`, tone: nextResult.ok ? "success" : "info" });
      return nextResult;
    } catch (error) {
      const message = error instanceof Error ? error.message : "请求失败";
      const nextResult = { ok: false, configured: status?.configured, overall_pass: false, error: message, items: [], latency_ms: 0 };
      setResult(nextResult);
      toast.notify({ title: "定位失败", description: message, tone: "error" });
      return nextResult;
    } finally {
      inFlightRef.current = false;
      setBusy(null);
    }
  }

  async function refreshCameras() {
    if (!navigator.mediaDevices?.enumerateDevices) {
      setCameraStatus("当前浏览器不支持摄像头枚举。");
      setDevices([]);
      return [];
    }
    const nextDevices = (await navigator.mediaDevices.enumerateDevices()).filter((device) => device.kind === "videoinput");
    setDevices(nextDevices);
    if (!selectedDeviceId && nextDevices[0]?.deviceId) setSelectedDeviceId(nextDevices[0].deviceId);
    return nextDevices;
  }

  async function startCamera(deviceId = selectedDeviceId) {
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraStatus("当前浏览器不支持摄像头。");
      return null;
    }
    setBusy("camera");
    try {
      stopCamera();
      const nextStream = await navigator.mediaDevices.getUserMedia({
        video: deviceId ? { deviceId: { exact: deviceId } } : true,
        audio: false
      });
      streamRef.current = nextStream;
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
      return nextStream;
    } catch (error) {
      stopCamera();
      const message = error instanceof Error ? error.message : "摄像头不可用";
      setCameraStatus(`摄像头不可用：${message}`);
      toast.notify({ title: "摄像头不可用", description: message, tone: "error" });
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function runCameraOnce(quiet = false) {
    if (!streamRef.current) await startCamera();
    const file = await captureVideoFrame(videoRef.current);
    setImageFile(file);
    setFrameCount((current) => current + 1);
    return runInspectWithFile(file, quiet);
  }

  function stopLoop() {
    loopActiveRef.current = false;
    setLoopActive(false);
    if (loopTimerRef.current) window.clearTimeout(loopTimerRef.current);
    loopTimerRef.current = null;
  }

  async function loopOnce() {
    if (!loopActiveRef.current) return;
    try {
      await runCameraOnce(true);
    } catch (error) {
      setResult({ ok: false, configured: status?.configured, overall_pass: false, error: error instanceof Error ? error.message : "请求失败", items: [], latency_ms: 0 });
    } finally {
      if (loopActiveRef.current) {
        loopTimerRef.current = window.setTimeout(loopOnce, Math.round(Math.min(2, Math.max(0.5, sampleSeconds)) * 1000));
      }
    }
  }

  async function startLoop() {
    if (!enabledRules.length) {
      toast.notify({ title: "请至少选择一个检测项", tone: "error" });
      return;
    }
    if (!streamRef.current) await startCamera();
    if (!streamRef.current) return;
    loopActiveRef.current = true;
    setLoopActive(true);
    loopOnce();
  }

  if (accessoriesQuery.isLoading || statusQuery.isLoading || (canConfigure && configQuery.isLoading)) {
    return <LoadingState label="读取开放定位配置" />;
  }
  if (accessoriesQuery.isError) {
    return <ErrorState error={accessoriesQuery.error} action={<button className="secondary compact-action" type="button" onClick={() => accessoriesQuery.refetch()}>重试</button>} />;
  }

  return (
    <section className="view active">
      <header className="page-head">
        <div>
          <h2>开放定位</h2>
          <p className="page-desc">LocateAnything 开放词汇定位，作为辅助与兜底定位工具。</p>
        </div>
        <div className="page-head-actions">
          <div className={resultBadgeClass(result, busy === "inspect")}>{busy === "inspect" ? "检测中" : resultStatusText(result)}</div>
          <button className="secondary compact-action" type="button" disabled={busy === "status"} onClick={() => checkStatus()}>
            <RefreshCw size={15} aria-hidden="true" />
            检查服务
          </button>
        </div>
      </header>

      <div className="inspect-grid locate-worker-grid">
        <section className="panel page-panel locate-source-panel">
          <div className="section-title title-with-action">
            <h3>检测源</h3>
            <span className={`pill ${statusTone(status)}`}>{statusText(status)}</span>
          </div>
          <p className="hint-line">{status?.message || (status?.ok ? "本地检测服务已连接，可以开始相机检测。" : "检测服务未启动。")}</p>
          <div className="button-row locate-runtime-actions">
            {canConfigure ? (
              <button className="primary compact-action" type="button" disabled={busy === "runtime"} onClick={startRuntime}>
                <Play size={15} aria-hidden="true" />
                启动本地模型
              </button>
            ) : null}
            <button className="secondary compact-action" type="button" disabled={busy === "status"} onClick={() => checkStatus()}>
              <RefreshCw size={15} aria-hidden="true" />
              检查服务
            </button>
          </div>

          <label className="toolbar-field locate-camera-field">
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
          <div className="camera-preview locate-live-frame">
            <video ref={videoRef} autoPlay playsInline muted />
            {!stream && imagePreviewUrl ? <img src={imagePreviewUrl} alt="待检测图片" /> : null}
            {!stream && !imagePreviewUrl ? <div className="camera-empty">打开摄像头或上传图片</div> : null}
          </div>
          <div className="camera-actions locate-camera-actions">
            <button className="secondary compact-action" type="button" disabled={busy === "camera"} onClick={async () => {
              await refreshCameras();
              await startCamera();
            }}>
              <RefreshCw size={15} aria-hidden="true" />
              打开摄像头
            </button>
            <button className="secondary compact-action" type="button" disabled={Boolean(busy) || loopActive} onClick={() => runCameraOnce()}>
              <Camera size={15} aria-hidden="true" />
              检测一帧
            </button>
            {!loopActive ? (
              <button className="primary compact-action" type="button" disabled={Boolean(busy)} onClick={startLoop}>
                <Play size={15} aria-hidden="true" />
                连续检测
              </button>
            ) : (
              <button className="secondary danger compact-action" type="button" onClick={stopLoop}>
                <Square size={15} aria-hidden="true" />
                停止
              </button>
            )}
          </div>
          <p className="hint-line">{cameraStatus}</p>

          <label className="dropzone compact-dropzone">
            <input type="file" accept="image/*" onChange={(event) => setImageFile(event.currentTarget.files?.[0] || null)} />
            <strong>图片输入</strong>
            <span>{imageFile?.name || "摄像头不可用时上传单张图片检测"}</span>
          </label>
          <div className="button-row">
            <button className="secondary compact-action" type="button" disabled={!imageFile || Boolean(busy)} onClick={() => runInspectWithFile(imageFile)}>
              <FileImage size={15} aria-hidden="true" />
              检测图片
            </button>
            <button className="secondary compact-action" type="button" disabled={!imageFile || Boolean(busy) || !freePrompt.trim()} onClick={() => runPromptWithFile(imageFile)}>
              <Search size={15} aria-hidden="true" />
              提示词定位
            </button>
          </div>

          <details className="tune-drawer locate-advanced-panel" open={canConfigure}>
            <summary>
              <span className="tune-drawer-title">微调设置</span>
              <span className="tune-drawer-hint">{canConfigure ? "端点、采样与推理参数" : "只读参数"}</span>
            </summary>
            <div className="tune-drawer-body">
              <div className="field">
                <label htmlFor="locate-endpoint-url">Endpoint URL</label>
                <input
                  id="locate-endpoint-url"
                  type="url"
                  value={configForm.endpoint_url}
                  disabled={!canConfigure}
                  onChange={(event) => setConfigForm((current) => ({ ...current, endpoint_url: event.currentTarget.value }))}
                />
              </div>
              <div className="field locate-sampling-field">
                <label htmlFor="locate-sample-seconds">采样间隔(秒)</label>
                <input
                  id="locate-sample-seconds"
                  type="number"
                  min="0.5"
                  max="2"
                  step="0.1"
                  value={sampleSeconds}
                  onChange={(event) => setSampleSeconds(numeric(event.currentTarget.value, 1))}
                />
              </div>
              <div className="locate-param-grid">
                <div className="field">
                  <label htmlFor="locate-max-side">Max Side</label>
                  <input
                    id="locate-max-side"
                    type="number"
                    min="256"
                    max="2560"
                    step="64"
                    value={configForm.max_side}
                    onChange={(event) => setConfigForm((current) => ({ ...current, max_side: numeric(event.currentTarget.value, 640) }))}
                  />
                </div>
                <div className="field">
                  <label htmlFor="locate-max-tokens">Max Tokens</label>
                  <input
                    id="locate-max-tokens"
                    type="number"
                    min="64"
                    max="8192"
                    step="64"
                    value={configForm.max_new_tokens}
                    onChange={(event) => setConfigForm((current) => ({ ...current, max_new_tokens: numeric(event.currentTarget.value, 512) }))}
                  />
                </div>
              </div>
              {canConfigure ? (
                <button className="secondary icon-label" type="button" disabled={busy === "config"} onClick={saveConfig}>
                  <Save size={15} aria-hidden="true" />
                  保存微调设置
                </button>
              ) : null}
            </div>
          </details>
          <p className="hint-line locate-license-note">{status?.license || "NVIDIA non-commercial license: research and validation only; commercial use is not permitted."}</p>
        </section>

        <section className="panel page-panel locate-config-panel">
          <div className="section-title title-with-action">
            <h3>检测配方</h3>
            <button className="secondary compact-action" type="button" onClick={() => setRecipeOpen((current) => !current)}>
              {recipeOpen ? "收起" : "展开"}
            </button>
          </div>
          <div className="locate-recipe-summary">
            <MetricCard label="已配置" value={rules.length} />
            <MetricCard label="启用" value={enabledRules.length} />
            <MetricCard label="期望总数" value={expectedTotal} />
          </div>
          <div className="field">
            <label htmlFor="locate-free-prompt">自由提示词</label>
            <textarea
              id="locate-free-prompt"
              value={freePrompt}
              onChange={(event) => setFreePrompt(event.currentTarget.value)}
              placeholder="Locate all instances that match..."
            />
          </div>
          <button className="secondary compact-action" type="button" onClick={() => setPickerOpen((current) => !current)}>
            <Search size={15} aria-hidden="true" />
            添加检测项
          </button>
          {pickerOpen ? (
            <div className="locate-recipe-picker">
              <label className="search-field">
                <Search size={15} aria-hidden="true" />
                <input type="search" value={searchQuery} placeholder="搜索配件 / 类别" onChange={(event) => setSearchQuery(event.currentTarget.value)} />
              </label>
              <div className="locate-picker-list">
                {filteredSources.length ? (
                  filteredSources.map((item) => {
                    const selected = rules.find((rule) => rule.id === item.id);
                    return (
                      <label className="locate-picker-row" key={item.id}>
                        <input type="checkbox" checked={Boolean(selected?.enabled)} onChange={(event) => upsertRule(item, event.currentTarget.checked)} />
                        <span>
                          <strong>{sourceLabel(item)}</strong>
                          <small className="locate-short-description">{[compactLocateDescription(item), selected ? "已配置" : "未添加"].filter(Boolean).join(" · ")}</small>
                        </span>
                      </label>
                    );
                  })
                ) : (
                  <p className="hint-line">没有匹配项。</p>
                )}
              </div>
            </div>
          ) : null}

          <div className={`locate-rule-list ${recipeOpen ? "expanded" : ""}`}>
            {rules.length ? (
              rules.map((rule) => {
                const expectedPresent = rule.expected_present !== false;
                return (
                  <article className={`locate-rule-row ${rule.enabled ? "" : "disabled"}`} key={rule.id}>
                    <label className="locate-rule-main">
                      <input type="checkbox" checked={rule.enabled} onChange={(event) => updateRule(rule.id, { enabled: event.currentTarget.checked })} />
                      <span>
                        <strong>{sourceLabel(rule)}</strong>
                        <small className="locate-short-description">{compactLocateDescription(rule)}</small>
                      </span>
                    </label>
                    <label className="locate-presence-toggle">
                      <input type="checkbox" checked={expectedPresent} onChange={(event) => updateRule(rule.id, { expected_present: event.currentTarget.checked })} />
                      <span>应出现</span>
                    </label>
                    <label className="locate-count-field">
                      <span>数量</span>
                      <input type="number" min="0" max="99" value={rule.expected_count ?? 1} onChange={(event) => updateRule(rule.id, { expected_count: numeric(event.currentTarget.value, 1) })} />
                    </label>
                    <button className="icon-only locate-remove-rule" type="button" aria-label="移除检测项" onClick={() => removeRule(rule.id)}>
                      <X size={16} aria-hidden="true" />
                    </button>
                    {recipeOpen ? (
                      <div className="field locate-rule-prompt">
                        <label htmlFor={`prompt-${rule.id}`}>提示词覆盖</label>
                        <input
                          id={`prompt-${rule.id}`}
                          type="text"
                          value={rule.prompt_override || ""}
                          placeholder={rule.visual_prompt || "可选：覆盖自动生成提示词"}
                          onChange={(event) => updateRule(rule.id, { prompt_override: event.currentTarget.value })}
                        />
                      </div>
                    ) : null}
                  </article>
                );
              })
            ) : (
              <div className="empty-state compact-empty">还没有检测项</div>
            )}
          </div>
        </section>
      </div>

      <section className="panel page-panel locate-result-panel">
        <div className="section-title title-with-action">
          <h3>检测结果</h3>
          <div className="button-row">
            <span className="pill neutral">{result?.latency_ms ? `${result.latency_ms} ms` : "-"}</span>
            {canViewDiagnostics ? (
              <button className="secondary compact-action" type="button" onClick={() => setDebugOpen(true)}>
                开发诊断
              </button>
            ) : null}
          </div>
        </div>
        <div className="metric-grid four">
          <MetricCard label="结果" value={resultStatusText(result)} tone={resultTone(result)} />
          <MetricCard label="定位框" value={boxCount} />
          <MetricCard label="帧数" value={frameCount} />
          <MetricCard label="配置" value={status?.configured ? "已配置" : "未配置"} tone={status?.configured ? "ok" : "warn"} />
        </div>
        <div className="locate-result-grid">
          <div className="table-wrap locate-item-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>检测项</th>
                  <th>结论</th>
                  <th>要求</th>
                  <th>找到</th>
                </tr>
              </thead>
              <tbody>
                {(result?.items || []).length ? (
                  (result?.items || []).map((item) => (
                    <tr key={`${item.id || item.label}-${item.status}`}>
                      <td>{String(item.label || item.display_label || item.id || "-")}</td>
                      <td><span className={`pill ${item.passed ? "ok" : "fail"}`}>{locateStatusLabel(String(item.status || ""))}</span></td>
                      <td>{item.expected_present === false ? "不应出现" : String(item.expected_count ?? 1)}</td>
                      <td>{numeric(item.box_count, 0)}</td>
                    </tr>
                  ))
                ) : result?.boxes?.length ? (
                  <tr>
                    <td>{result.prompt || freePrompt || "自由提示词"}</td>
                    <td><span className="pill ok">已定位</span></td>
                    <td>-</td>
                    <td>{result.boxes.length}</td>
                  </tr>
                ) : (
                  <tr>
                    <td colSpan={4}>{result?.error || "暂无检测项"}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="preview-frame locate-preview-frame">
            {resultImage ? <img src={resultImage} alt="检测结果 overlay" /> : <div className="empty-state">检测结果会显示在这里</div>}
          </div>
        </div>
      </section>

      {debugOpen && canViewDiagnostics ? (
        <div className="modal-backdrop" role="presentation">
          <section className="modal-panel wide" role="dialog" aria-modal="true" aria-label="LocateAnything 开发诊断">
            <header className="modal-head">
              <div>
                <h3>开发诊断</h3>
                <span>{result?.diagnostic_url || "暂无检测结果"}</span>
              </div>
              <button className="icon-only" type="button" aria-label="关闭" onClick={() => setDebugOpen(false)}>
                <X size={18} aria-hidden="true" />
              </button>
            </header>
            <div className="modal-body">
              <pre className="json-panel">{JSON.stringify(result || { message: "暂无检测结果。" }, null, 2)}</pre>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}

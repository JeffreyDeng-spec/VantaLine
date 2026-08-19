import { FormEvent, useEffect, useRef, useState } from "react";
import { KeyRound, PlugZap, Plus, RefreshCw, Save, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { hasPermission } from "../../app/permissions";
import {
  deleteActiveAiKey,
  getAgentConfig,
  getAiConfig,
  getApiCostLedger,
  getPlcWorkstation,
  listPlcWorkstations,
  pairPlcWorkstation,
  queryKeys,
  saveAgentConfig,
  saveAiConfig,
  savePlcWorkstationConfig,
  testAgentConfig,
  verifyPlcWorkstationProfile,
} from "../../api/queries";
import type { AgentConfigResponse, AiConfigResponse, AiKeySummary, ApiCostDailyPoint, ApiCostLedgerResponse, PlcWebSerialConfig } from "../../api/types";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { MetricCard } from "../../components/MetricCard";
import { useToast } from "../../components/ToastProvider";
import { toneForStatus } from "../../utils/format";
import { useAuth } from "../auth/auth-context";

const AI_PROVIDER_OPTIONS = [
  { value: "gemini", label: "Gemini" },
  { value: "qwen", label: "Qwen" }
];

const IMAGE_PROVIDER_OPTIONS = [
  { value: "gemini", label: "Gemini" },
  { value: "agnes", label: "Agnes Image" },
  { value: "qwen_image", label: "Qwen Image" }
];

const AGENT_PROVIDER_OPTIONS = [
  { value: "openai_compatible", label: "OpenAI 兼容" },
  { value: "cursor", label: "Cursor" }
];

const IMAGE_PROVIDER_DEFAULTS: Record<string, { model: string; base_url: string }> = {
  gemini: {
    model: "gemini-3.1-flash-image",
    base_url: "https://generativelanguage.googleapis.com/v1beta"
  },
  agnes: {
    model: "agnes-image-2.0-flash",
    base_url: "https://apihub.agnes-ai.com/v1/images/generations"
  },
  qwen_image: {
    model: "qwen-image-2.0-pro",
    base_url: "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
  }
};

const AI_PROVIDER_DEFAULTS: Record<string, { model: string; base_url: string }> = {
  gemini: {
    model: "gemini-2.5-flash",
    base_url: "https://generativelanguage.googleapis.com/v1beta"
  },
  qwen: {
    model: "qwen3-vl-flash",
    base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
  }
};

type SettingsTab = "ai" | "image" | "agent" | "plc" | "cost-ledger";
type ApiKeyDialogTarget = "ai" | "image" | "agent";

const SETTINGS_TABS: Array<{ value: SettingsTab; label: string }> = [
  { value: "ai", label: "AI 检测" },
  { value: "image", label: "图片生成" },
  { value: "agent", label: "Agent 接入" },
  { value: "plc", label: "PLC 同步" },
  { value: "cost-ledger", label: "成本账本" }
];

function formatUsd(value?: number) {
  const amount = Number(value || 0);
  if (amount >= 100) return `$${amount.toFixed(2)}`;
  if (amount >= 1) return `$${amount.toFixed(3)}`;
  return `$${amount.toFixed(6)}`;
}

function formatDateTime(seconds?: number) {
  if (!seconds) return "-";
  return new Date(seconds * 1000).toLocaleString("zh-CN", { hour12: false });
}

function CostTrendChart({ points }: { points: ApiCostDailyPoint[] }) {
  const maxCost = Math.max(...points.map((point) => Number(point.total_cost_usd || 0)), 0.000001);
  const ticks = [1, 0.75, 0.5, 0.25, 0].map((ratio) => ({
    ratio,
    value: maxCost * ratio
  }));
  if (!points.length) {
    return <div className="cost-empty-state">还没有可计价的 API 调用记录。</div>;
  }
  return (
    <div className="cost-chart-frame" role="img" aria-label="每日 API 支出趋势，横轴为日期，纵轴为美元成本">
      <div className="cost-axis-title y">成本 / 美元</div>
      <div className="cost-chart-body">
        <div className="cost-y-axis" aria-hidden="true">
          {ticks.map((tick) => (
            <span key={tick.ratio}>{formatUsd(tick.value)}</span>
          ))}
        </div>
        <div className="cost-trend-chart">
          <div className="cost-grid-lines" aria-hidden="true">
            {ticks.map((tick) => (
              <span key={tick.ratio} />
            ))}
          </div>
          {points.map((point) => {
            const height = Math.max(4, Math.round((Number(point.total_cost_usd || 0) / maxCost) * 100));
            return (
              <div className="cost-trend-column" key={point.date} title={`${point.date} · ${formatUsd(point.total_cost_usd)} · ${point.call_count} 次`}>
                <div className="cost-trend-bar" style={{ height: `${height}%` }} />
                <span>{point.date.slice(5)}</span>
              </div>
            );
          })}
        </div>
      </div>
      <div className="cost-axis-title x">日期</div>
    </div>
  );
}

function CostLedgerPanel({ ledger }: { ledger: ApiCostLedgerResponse }) {
  const summary = ledger.summary;
  return (
    <div className="cost-ledger-stack">
      <div className="metric-grid">
        <MetricCard label="实际总成本" value={formatUsd(summary.total_cost_usd)} detail={`已记录 ${summary.call_count} 次含 usage 的 API 调用`} />
        <MetricCard label="做一张图均价" value={formatUsd(summary.avg_image_generation_cost_usd)} detail="生图 / AI mask 平均" />
        <MetricCard label="单次调用均价" value={formatUsd(summary.avg_cost_per_call_usd)} detail="所有可计价调用平均" />
        <MetricCard label="训练样本摊薄" value={formatUsd(summary.avg_cost_per_training_sample_usd)} detail={`${summary.training_sample_count} 张可训练样本`} />
      </div>
      <div className="cost-ledger-note">
        <span>更新时间：{formatDateTime(ledger.updated_at)}</span>
        <span>实际 usage {formatUsd(summary.known_cost_usd)} · 未计价 {summary.unpriced_call_count} 次 · 不做估算</span>
      </div>
      <section className="cost-ledger-section">
        <div className="section-title compact">
          <h4>API 分类总结</h4>
        </div>
        <div className="cost-category-grid">
          {ledger.categories.map((category) => (
            <article className="cost-category-card" key={category.key}>
              <div>
                <h5>{category.label}</h5>
                <strong>{formatUsd(category.cost_usd)}</strong>
              </div>
              <p>
                {category.call_count} 次含 usage 调用 · 均价 {formatUsd(category.avg_cost_usd)}
              </p>
              <div className="cost-subcategory-list">
                {(category.subcategories || []).slice(0, 4).map((item) => (
                  <span key={item.label}>
                    {item.label} · {item.call_count} · {formatUsd(item.cost_usd)}
                  </span>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>
      <section className="cost-ledger-section">
        <div className="section-title compact">
          <h4>每日支出趋势</h4>
        </div>
        <CostTrendChart points={ledger.daily || []} />
      </section>
      <section className="cost-ledger-section">
        <div className="section-title compact">
          <h4>最近调用</h4>
          <span className="muted-text">只展示最近 80 条</span>
        </div>
        <div className="cost-call-table">
          <div className="cost-call-row head">
            <span>日期</span>
            <span>类别</span>
            <span>模型</span>
            <span>成本</span>
          </div>
          {(ledger.recent_calls || []).slice(0, 12).map((call) => (
            <div className="cost-call-row" key={call.id}>
              <span>{call.day}</span>
              <span>{call.subcategory}</span>
              <span>{call.model}</span>
              <strong>{formatUsd(call.cost_usd)}</strong>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function compactKeySource(value?: string) {
  const text = String(value || "").trim();
  if (text.length <= 18) return text;
  return `${text.slice(0, 11)}...${text.slice(-4)}`;
}

function providerLabel(provider: string | undefined, options: Array<{ value: string; label: string }>) {
  return options.find((option) => option.value === provider)?.label || "";
}

function keyProviderLabel(key: AiKeySummary) {
  const provider = String(key.provider || "").trim();
  return (
    providerLabel(provider, IMAGE_PROVIDER_OPTIONS) ||
    providerLabel(provider, AI_PROVIDER_OPTIONS) ||
    providerLabel(provider, AGENT_PROVIDER_OPTIONS)
  );
}

function keyOptionLabel(key: AiKeySummary) {
  const source = compactKeySource(key.env_name || key.masked_key || "");
  const provider = keyProviderLabel(key);
  const prefix = provider && !key.label.toLowerCase().includes(provider.toLowerCase()) ? `${provider} · ` : "";
  return source ? `${prefix}${key.label} · ${source}` : `${prefix}${key.label}`;
}

function keysForProvider(keys: AiKeySummary[] | undefined, provider: string) {
  const cleanProvider = String(provider || "").trim();
  return (keys || []).filter((key) => String(key.provider || "").trim() === cleanProvider);
}

function defaultAiKeyEnv(provider: string) {
  if (provider === "qwen") return "DASHSCOPE_API_KEY";
  return "GEMINI_API_KEY";
}

function defaultImageKeyEnv(provider: string) {
  if (provider === "agnes") return "AGNES_API_KEY";
  return "GEMINI_IMAGE_API_KEY";
}

function defaultAgentKeyEnv(provider: string) {
  return provider === "cursor" ? "CURSOR_API_KEY" : "VANTALINE_AGENT_API_KEY";
}

function readAgentPayload(form: HTMLFormElement) {
  const data = new FormData(form);
  const payload: Partial<AgentConfigResponse> & { api_key?: string } = {
    enabled: true,
    provider: String(data.get("provider") || "openai_compatible"),
    base_url: String(data.get("base_url") || "").trim(),
    model: String(data.get("model") || "").trim(),
    timeout_seconds: Number(data.get("timeout_seconds") || 45),
    auto_advance_default: data.get("auto_advance_default") === "on"
  };
  const apiKeyEnv = data.get("api_key_env");
  if (apiKeyEnv !== null) payload.api_key_env = String(apiKeyEnv || "").trim();
  const apiKey = String(data.get("api_key") || "").trim();
  if (apiKey) payload.api_key = apiKey;
  return payload;
}

function readAiPayload(form: HTMLFormElement, initialProvider = "") {
  const data = new FormData(form);
  const selectedProvider = String(data.get("provider") || "").trim();
  const normalizedInitialProvider = String(initialProvider || "").trim();
  const payload: Partial<AiConfigResponse> & { api_key?: string } = {
    model: String(data.get("model") || "").trim(),
    base_url: String(data.get("base_url") || "").trim(),
    timeout_seconds: Number(data.get("timeout_seconds") || 10)
  };
  const apiKeyEnv = data.get("api_key_env");
  if (apiKeyEnv !== null) payload.api_key_env = String(apiKeyEnv || "").trim();
  if (selectedProvider && selectedProvider !== normalizedInitialProvider) {
    payload.provider = selectedProvider;
  }
  const apiKey = String(data.get("api_key") || "").trim();
  if (apiKey) payload.api_key = apiKey;
  return payload;
}

function readImagePayload(form: HTMLFormElement) {
  const data = new FormData(form);
  const payload: {
    image_provider: string;
    image_model: string;
    image_base_url: string;
    image_timeout_seconds: number;
    image_api_key_env?: string;
    image_api_key?: string;
  } = {
    image_provider: String(data.get("image_provider") || "gemini").trim(),
    image_model: String(data.get("image_model") || "").trim(),
    image_base_url: String(data.get("image_base_url") || "").trim(),
    image_timeout_seconds: Number(data.get("image_timeout_seconds") || 120)
  };
  const apiKeyEnv = data.get("image_api_key_env");
  if (apiKeyEnv !== null) payload.image_api_key_env = String(apiKeyEnv || "").trim();
  const apiKey = String(data.get("image_api_key") || "").trim();
  if (apiKey) payload.image_api_key = apiKey;
  return payload;
}

function readPlcPayload(form: HTMLFormElement): PlcWebSerialConfig {
  const data = new FormData(form);
  return {
    schema_version: 4,
    transport_mode: "web_serial",
    profile_id: "fx_ascii_16x16_spec_v1",
    enabled: data.get("enabled") === "on",
    protocol: "fx_programming_port_ascii",
    checksum_mode: "include_etx",
    baudrate: 9600,
    parity: "E",
    data_bits: 7,
    stop_bits: 1,
    result_register: String(data.get("result_register") || "D206").trim().toUpperCase(),
    output_control_point: String(data.get("output_control_point") ?? "").trim().toUpperCase(),
    ack_timeout_ms: 500,
    retries: 0
  };
}

function plcStatusLabel(status?: string) {
  if (status === "acknowledged") return "已确认";
  if (status === "partial_success") return "部分成功";
  if (status === "uncertain") return "结果不确定";
  if (status === "browser_attempt_declared") return "浏览器正在执行";
  if (status === "planned") return "待浏览器执行";
  if (status === "failed") return "失败";
  if (status === "sent") return "已发送";
  if (status === "attempting") return "正在尝试";
  if (status === "queued") return "排队中";
  if (status === "disabled") return "未启用";
  return status || "暂无记录";
}

export function RulesPage() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const agentFormRef = useRef<HTMLFormElement>(null);
  const aiFormRef = useRef<HTMLFormElement>(null);
  const imageFormRef = useRef<HTMLFormElement>(null);
  const plcFormRef = useRef<HTMLFormElement>(null);
  const [aiProviderDraft, setAiProviderDraft] = useState("gemini");
  const [imageProvider, setImageProvider] = useState("gemini");
  const [agentProviderDraft, setAgentProviderDraft] = useState("openai_compatible");
  const [settingsTab, setSettingsTab] = useState<SettingsTab>("ai");
  const [apiKeyDialog, setApiKeyDialog] = useState<ApiKeyDialogTarget | null>(null);

  const agentAllowed = hasPermission(auth.user, "agent_config");
  const aiAllowed = hasPermission(auth.user, "ai_config");
  const adminAllowed = auth.user?.role === "admin";
  const systemAllowed = hasPermission(auth.user, "system_settings");

  const agentQuery = useQuery({
    queryKey: queryKeys.agentConfig,
    queryFn: getAgentConfig,
    enabled: agentAllowed
  });
  const aiQuery = useQuery({
    queryKey: queryKeys.aiConfig,
    queryFn: getAiConfig,
    enabled: aiAllowed
  });
  const plcQuery = useQuery({
    queryKey: queryKeys.plcWorkstation,
    queryFn: getPlcWorkstation,
    enabled: systemAllowed
  });
  const plcWorkstationsQuery = useQuery({
    queryKey: queryKeys.plcWorkstations,
    queryFn: listPlcWorkstations,
    enabled: systemAllowed && settingsTab === "plc"
  });
  const costLedgerQuery = useQuery({
    queryKey: queryKeys.apiCostLedger,
    queryFn: getApiCostLedger,
    enabled: adminAllowed && settingsTab === "cost-ledger",
    refetchInterval: settingsTab === "cost-ledger" ? 30_000 : false
  });

  const agentMutation = useMutation({
    mutationFn: saveAgentConfig,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentConfig });
      notify({ title: "Agent 设置已保存", tone: "success" });
      const key = agentFormRef.current?.elements.namedItem("api_key");
      if (key instanceof HTMLInputElement) key.value = "";
    },
    onError: (error: Error) => notify({ title: "Agent 保存失败", description: error.message, tone: "error" })
  });

  const agentTestMutation = useMutation({
    mutationFn: async () => {
      if (agentFormRef.current) await saveAgentConfig(readAgentPayload(agentFormRef.current));
      return testAgentConfig();
    },
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentConfig });
      notify({ title: result.ok ? "Agent 连接成功" : "Agent 连接失败", description: result.message, tone: result.ok ? "success" : "error" });
    },
    onError: (error: Error) => notify({ title: "Agent 测试失败", description: error.message, tone: "error" })
  });

  const aiMutation = useMutation({
    mutationFn: saveAiConfig,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.aiConfig });
      notify({ title: "AI 设置已保存", tone: "success" });
      if (aiFormRef.current) {
        const key = aiFormRef.current.elements.namedItem("api_key");
        if (key instanceof HTMLInputElement) key.value = "";
      }
    },
    onError: (error: Error) => notify({ title: "AI 保存失败", description: error.message, tone: "error" })
  });

  const imageMutation = useMutation({
    mutationFn: saveAiConfig,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.aiConfig });
      notify({ title: "图片生成设置已保存", tone: "success" });
      if (imageFormRef.current) {
        const key = imageFormRef.current.elements.namedItem("image_api_key");
        if (key instanceof HTMLInputElement) key.value = "";
      }
    },
    onError: (error: Error) => notify({ title: "图片生成保存失败", description: error.message, tone: "error" })
  });

  const plcMutation = useMutation({
    mutationFn: savePlcWorkstationConfig,
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.plcWorkstation });
      await plcQuery.refetch();
      notify({
        title: "PLC 设置已保存",
        description: saved.config?.enabled ? "联动已允许；检测人员仍需在本机点击连接 PLC。" : "配置已保存，PLC 联动尚未启用。",
        tone: "success"
      });
    },
    onError: (error: Error) => notify({ title: "PLC 保存失败", description: error.message, tone: "error" })
  });

  const plcPairMutation = useMutation({
    mutationFn: pairPlcWorkstation,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.plcWorkstation });
      await queryClient.invalidateQueries({ queryKey: queryKeys.plcWorkstations });
      notify({ title: "本机工作站已绑定", description: "退出账号不会删除此电脑的工作站绑定。", tone: "success" });
    },
    onError: (error: Error) => notify({ title: "工作站绑定失败", description: error.message, tone: "error" })
  });

  const plcVerifyMutation = useMutation({
    mutationFn: verifyPlcWorkstationProfile,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.plcWorkstation });
      notify({ title: "PLC 验证状态已更新", tone: "success" });
    },
    onError: (error: Error) => notify({ title: "验证状态更新失败", description: error.message, tone: "error" })
  });

  const aiKeyDeleteMutation = useMutation({
    mutationFn: deleteActiveAiKey,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.aiConfig });
      notify({ title: "API Key 已删除", tone: "success" });
    },
    onError: (error: Error) => notify({ title: "API Key 删除失败", description: error.message, tone: "error" })
  });
  function handleAgentSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    agentMutation.mutate(readAgentPayload(event.currentTarget));
  }

  function handleAiSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    aiMutation.mutate(readAiPayload(event.currentTarget, ai?.provider));
  }

  function handleImageSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    imageMutation.mutate(readImagePayload(event.currentTarget));
  }

  function handlePlcSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = readPlcPayload(event.currentTarget);
    if (payload.enabled) {
      const summary = [
        `检测结果将写入 ${payload.result_register}`,
        payload.output_control_point ? `将直接控制 ${payload.output_control_point}` : "不会直接控制流水线",
        "只有本机摄像头检测会生成指令"
      ].join("；");
      if (!window.confirm(`${summary}。请确认这些地址已经由 PLC 编程人员分配且未被占用。`)) return;
    }
    plcMutation.mutate(payload);
  }

  function handleAiActiveKeyChange(event: React.ChangeEvent<HTMLSelectElement>) {
    aiMutation.mutate({ provider: aiProviderDraft, active_key_id: event.currentTarget.value });
  }

  function handleAiProviderChange(event: React.ChangeEvent<HTMLSelectElement>) {
    const nextProvider = event.currentTarget.value;
    setAiProviderDraft(nextProvider);
    const defaults = AI_PROVIDER_DEFAULTS[nextProvider];
    if (!defaults || !aiFormRef.current) return;
    const model = aiFormRef.current.elements.namedItem("model");
    const baseUrl = aiFormRef.current.elements.namedItem("base_url");
    if (model instanceof HTMLInputElement) model.value = defaults.model;
    if (baseUrl instanceof HTMLInputElement) baseUrl.value = defaults.base_url;
  }

  function handleAgentActiveKeyChange(event: React.ChangeEvent<HTMLSelectElement>) {
    agentMutation.mutate({ provider: agentProviderDraft, active_key_id: event.currentTarget.value });
  }

  function handleImageActiveKeyChange(event: React.ChangeEvent<HTMLSelectElement>) {
    imageMutation.mutate({ image_provider: imageProvider, image_active_key_id: event.currentTarget.value });
  }

  function handleImageProviderChange(event: React.ChangeEvent<HTMLSelectElement>) {
    const nextProvider = event.currentTarget.value;
    setImageProvider(nextProvider);
    const defaults = IMAGE_PROVIDER_DEFAULTS[nextProvider];
    if (!defaults || !imageFormRef.current) return;
    const model = imageFormRef.current.elements.namedItem("image_model");
    const baseUrl = imageFormRef.current.elements.namedItem("image_base_url");
    if (model instanceof HTMLInputElement) model.value = defaults.model;
    if (baseUrl instanceof HTMLInputElement) baseUrl.value = defaults.base_url;
  }

  function handleApiKeyDialogSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!apiKeyDialog) return;
    const data = new FormData(event.currentTarget);
    const envName = String(data.get("api_key_env") || "").trim();
    const apiKey = String(data.get("api_key") || "").trim();
    if (!apiKey) {
      notify({ title: "请输入 API Key", tone: "error" });
      return;
    }
    if (apiKeyDialog === "ai") {
      const payload = aiFormRef.current ? readAiPayload(aiFormRef.current, ai?.provider) : {};
      aiMutation.mutate({ ...payload, api_key_env: envName, api_key: apiKey }, { onSuccess: () => setApiKeyDialog(null) });
      return;
    }
    if (apiKeyDialog === "image") {
      const payload = imageFormRef.current
        ? readImagePayload(imageFormRef.current)
        : {
            image_provider: imageProvider,
            image_model: IMAGE_PROVIDER_DEFAULTS[imageProvider]?.model || IMAGE_PROVIDER_DEFAULTS.gemini.model,
            image_base_url: IMAGE_PROVIDER_DEFAULTS[imageProvider]?.base_url || IMAGE_PROVIDER_DEFAULTS.gemini.base_url,
            image_timeout_seconds: image?.timeout_seconds || 120
          };
      imageMutation.mutate(
        { ...payload, image_api_key_env: envName, image_api_key: apiKey },
        { onSuccess: () => setApiKeyDialog(null) }
      );
      return;
    }
    const payload = agentFormRef.current ? readAgentPayload(agentFormRef.current) : {};
    agentMutation.mutate({ ...payload, api_key_env: envName, api_key: apiKey }, { onSuccess: () => setApiKeyDialog(null) });
  }

  const agent = agentQuery.data;
  const ai = aiQuery.data;
  const image = ai?.image_generation;
  const plcResponse = plcQuery.data;
  const plc = plcResponse?.config;
  const latestPlcDispatch = plcResponse?.recent_dispatches?.[0];
  const costLedger = costLedgerQuery.data;
  const agentBusy = agentMutation.isPending || agentTestMutation.isPending;
  const aiBusy = aiMutation.isPending || aiKeyDeleteMutation.isPending;
  const imageBusy = imageMutation.isPending;
  const agentStatusLabel = agent?.connection_status || "检查中";
  const aiProvider = ai?.provider || "gemini";
  const agentProvider = agent?.provider || "openai_compatible";
  const aiProviderIsKnown = AI_PROVIDER_OPTIONS.some((option) => option.value === aiProviderDraft);
  const imageProviderIsKnown = IMAGE_PROVIDER_OPTIONS.some((option) => option.value === imageProvider);
  const agentProviderIsKnown = AGENT_PROVIDER_OPTIONS.some((option) => option.value === agentProviderDraft);
  const selectedAiProviderLabel = providerLabel(aiProviderDraft, AI_PROVIDER_OPTIONS) || aiProviderDraft;
  const selectedAgentProviderLabel = providerLabel(agentProviderDraft, AGENT_PROVIDER_OPTIONS) || agentProviderDraft;
  const savedImageProvider = image?.provider || "gemini";
  const aiProviderSaved = aiProviderDraft === aiProvider;
  const imageProviderSaved = imageProvider === savedImageProvider;
  const agentProviderSaved = agentProviderDraft === agentProvider;
  const selectedImageProviderLabel = IMAGE_PROVIDER_OPTIONS.find((option) => option.value === imageProvider)?.label || imageProvider;
  const selectedImageProviderDefaults = IMAGE_PROVIDER_DEFAULTS[imageProvider] || IMAGE_PROVIDER_DEFAULTS.gemini;
  const selectedAiProviderDefaultEnv = defaultAiKeyEnv(aiProviderDraft);
  const selectedImageProviderDefaultEnv = defaultImageKeyEnv(imageProvider);
  const selectedAgentProviderDefaultEnv = defaultAgentKeyEnv(agentProviderDraft);
  const visibleAiKeys = keysForProvider(ai?.api_keys, aiProviderDraft);
  const visibleAiActiveKeyId = aiProviderSaved ? ai?.active_key_id || "" : "";
  const visibleImageKeys = keysForProvider(image?.api_keys, imageProvider);
  const visibleImageActiveKeyId = imageProviderSaved ? image?.active_key_id || "" : "";
  const visibleAgentKeys = keysForProvider(agent?.api_keys, agentProviderDraft);
  const visibleAgentActiveKeyId = agentProviderSaved ? agent?.active_key_id || "" : "";
  const imageStatusLabel = imageProviderSaved ? image?.status || "检查中" : "未保存";
  const imageStatusTone = imageProviderSaved ? toneForStatus(image?.status) : "neutral";
  const apiKeyDialogTitle = apiKeyDialog === "ai" ? "添加 AI 检测 API Key" : apiKeyDialog === "image" ? "添加图片生成 API Key" : "添加 Agent API Key";
  const apiKeyDialogEnv =
    apiKeyDialog === "ai"
      ? selectedAiProviderDefaultEnv
      : apiKeyDialog === "image"
        ? selectedImageProviderDefaultEnv
        : selectedAgentProviderDefaultEnv;
  const apiKeyDialogHint =
    apiKeyDialog === "ai"
      ? `${selectedAiProviderLabel} AI 检测 Key 会保存到该环境变量，并在保存后成为当前 active key。`
      : apiKeyDialog === "image"
      ? `${selectedImageProviderLabel} AI mask / 图片生成 Key 会保存到该环境变量，并在保存后成为当前 image active key；不会修改 AI 检测 Key。`
      : `${selectedAgentProviderLabel} Key 会保存到该环境变量，并在保存后成为当前 active key。`;
  const apiKeyDialogBusy = apiKeyDialog === "ai" ? aiBusy : apiKeyDialog === "image" ? imageBusy : agentBusy;

  useEffect(() => {
    setAiProviderDraft(ai?.provider || "gemini");
  }, [ai?.provider]);

  useEffect(() => {
    setImageProvider(image?.provider || "gemini");
  }, [image?.provider]);

  useEffect(() => {
    setAgentProviderDraft(agent?.provider || "openai_compatible");
  }, [agent?.provider]);

  useEffect(() => {
    if (!aiAllowed && systemAllowed && (settingsTab === "ai" || settingsTab === "image")) setSettingsTab("plc");
  }, [aiAllowed, settingsTab, systemAllowed]);

  return (
    <section className="view active">
      <header className="page-head">
        <div>
          <h2>设置</h2>
          <p className="page-desc">管理 AI Provider 与流水线 Agent 接入参数。</p>
        </div>
        <button
          className="secondary compact-action"
          type="button"
          onClick={() => {
            agentQuery.refetch();
            aiQuery.refetch();
            plcQuery.refetch();
            costLedgerQuery.refetch();
          }}
        >
          <RefreshCw size={16} aria-hidden="true" />
          刷新
        </button>
      </header>

      <div className="mode-tabs settings-tabs" role="tablist" aria-label="设置分页">
        {SETTINGS_TABS.filter((tab) => {
          if (tab.value === "agent") return agentAllowed;
          if (tab.value === "plc") return systemAllowed;
          if (tab.value === "cost-ledger") return adminAllowed;
          return aiAllowed;
        }).map((tab) => (
          <button
            className={`mode-tab ${settingsTab === tab.value ? "active" : ""}`}
            type="button"
            role="tab"
            aria-selected={settingsTab === tab.value}
            key={tab.value}
            onClick={() => setSettingsTab(tab.value)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {aiAllowed && (settingsTab === "ai" || settingsTab === "image") ? (
        <section className="panel page-panel">
          <div className="section-title">
            <h3>{settingsTab === "ai" ? "AI 检测配置" : "图片生成配置"}</h3>
            <span className={`pill ${settingsTab === "ai" ? toneForStatus(ai?.status) : imageStatusTone}`}>
              {settingsTab === "ai" ? ai?.status || "检查中" : imageStatusLabel}
            </span>
          </div>
          {aiQuery.isLoading ? (
            <LoadingState label="正在加载 AI 设置" />
          ) : aiQuery.isError ? (
            <ErrorState error={aiQuery.error} />
          ) : (
            <>
            {settingsTab === "ai" ? (
            <>
            <div className="settings-subhead">
              <div>
                <h4>AI 检测</h4>
                <p>检测工作台和资料卡画像使用，Provider 与图片生成独立。</p>
              </div>
              <span className={`pill ${toneForStatus(ai?.status)}`}>{ai?.status || "检查中"}</span>
            </div>
            <form className="settings-form" ref={aiFormRef} onSubmit={handleAiSubmit}>
              <div className="form-grid">
                <label className="field">
                  Provider
                  <select name="provider" value={aiProviderDraft} onChange={handleAiProviderChange}>
                    {!aiProviderIsKnown ? (
                      <option value={aiProviderDraft}>{ai?.provider_label || aiProviderDraft}</option>
                    ) : null}
                    {AI_PROVIDER_OPTIONS.map((option) => (
                      <option value={option.value} key={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Model
                  <input name="model" list="ai-model-options" defaultValue={ai?.model || AI_PROVIDER_DEFAULTS.gemini.model} />
                  <datalist id="ai-model-options">
                    {(ai?.model_options || []).map((option) => (
                      <option value={option.id} key={option.id}>
                        {option.label || option.id}
                      </option>
                    ))}
                  </datalist>
                </label>
                <label className="field">
                  Base URL
                  <input name="base_url" type="url" defaultValue={ai?.base_url || ""} />
                </label>
                <label className="field">
                  Timeout
                  <input name="timeout_seconds" type="number" min="0.5" max="300" step="0.5" defaultValue={ai?.timeout_seconds || 10} />
                </label>
              </div>
              <div className="form-grid key-grid action">
                <label className="field">
                  Active API Key
                  <select value={visibleAiActiveKeyId} onChange={handleAiActiveKeyChange} disabled={aiBusy || !visibleAiKeys.length}>
                    <option value="">{visibleAiKeys.length ? "环境变量 / 未选择" : `${selectedAiProviderLabel} 暂无 Key`}</option>
                    {visibleAiKeys.map((key) => (
                      <option value={key.id} key={key.id}>
                        {keyOptionLabel(key)}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="field key-action-field">
                  API Key
                  <button className="secondary compact-action" type="button" onClick={() => setApiKeyDialog("ai")} disabled={aiBusy}>
                    <Plus size={16} aria-hidden="true" />
                    添加 API Key
                  </button>
                </div>
              </div>
              {!aiProviderSaved ? (
                <p className="hint-line">当前正在编辑 {selectedAiProviderLabel}；新增或选择 Key 会同时切换到该 Provider。</p>
              ) : null}
              <div className="button-row">
                <button className="primary compact-action" type="submit" disabled={aiBusy}>
                  <Save size={16} aria-hidden="true" />
                  保存 AI 设置
                </button>
                <button
                  className="secondary icon-label danger"
                  type="button"
                  disabled={aiBusy || !aiProviderSaved || !visibleAiActiveKeyId}
                  onClick={() => {
                    if (window.confirm("确认删除当前 API Key？")) aiKeyDeleteMutation.mutate();
                  }}
                >
                  <Trash2 size={16} aria-hidden="true" />
                  删除当前 Key
                </button>
              </div>
            </form>
            </>
            ) : null}
            {settingsTab === "image" ? (
            <>
            <div className="settings-subhead">
              <div>
                <h4>图片生成</h4>
                <p>任务流水线生成样本素材时使用，和 AI 检测 Provider 分开配置。</p>
              </div>
              <span className={`pill ${imageStatusTone}`}>{imageStatusLabel}</span>
            </div>
            <form className="settings-form" ref={imageFormRef} onSubmit={handleImageSubmit}>
              <div className="form-grid">
                <label className="field">
                  Provider
                  <select name="image_provider" value={imageProvider} onChange={handleImageProviderChange}>
                    {!imageProviderIsKnown ? (
                      <option value={imageProvider}>{image?.provider_label || imageProvider}</option>
                    ) : null}
                    {IMAGE_PROVIDER_OPTIONS.map((option) => (
                      <option value={option.value} key={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Model
                  <input name="image_model" list="image-model-options" defaultValue={image?.model || selectedImageProviderDefaults.model} />
                  <datalist id="image-model-options">
                    {(image?.model_options || []).map((option) => (
                      <option value={option.id} key={option.id}>
                        {option.label || option.id}
                      </option>
                    ))}
                  </datalist>
                </label>
                <label className="field">
                  Base URL
                  <input name="image_base_url" type="url" defaultValue={image?.base_url || selectedImageProviderDefaults.base_url} />
                </label>
                <label className="field">
                  Timeout
                  <input name="image_timeout_seconds" type="number" min="10" max="300" step="5" defaultValue={image?.timeout_seconds || 120} />
                </label>
              </div>
              <div className="form-grid key-grid action">
                <label className="field">
                  Active API Key
                  <select value={visibleImageActiveKeyId} onChange={handleImageActiveKeyChange} disabled={imageBusy || !visibleImageKeys.length}>
                    <option value="">{visibleImageKeys.length ? "环境变量 / 未选择" : `${selectedImageProviderLabel} 暂无 Key`}</option>
                    {visibleImageKeys.map((key) => (
                      <option value={key.id} key={key.id}>
                        {keyOptionLabel(key)}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="field key-action-field">
                  API Key
                  <button className="secondary compact-action" type="button" onClick={() => setApiKeyDialog("image")} disabled={imageBusy}>
                    <Plus size={16} aria-hidden="true" />
                    添加 API Key
                  </button>
                </div>
              </div>
              {!imageProviderSaved ? (
                <p className="hint-line">当前正在编辑 {selectedImageProviderLabel}；新增或选择 Key 会同时切换到该 Provider。</p>
              ) : image?.message ? (
                <p className="hint-line">{image.message}</p>
              ) : null}
              <div className="button-row">
                <button className="primary compact-action" type="submit" disabled={imageBusy}>
                  <Save size={16} aria-hidden="true" />
                  保存图片生成设置
                </button>
              </div>
            </form>
            </>
            ) : null}
            </>
          )}
        </section>
      ) : null}

      {systemAllowed && settingsTab === "plc" ? (
        <section className="panel page-panel">
          <div className="section-title">
            <h3>本机 PLC 结果同步</h3>
            <span className={`pill ${plcResponse?.effective_enabled ? toneForStatus(latestPlcDispatch?.status) : "neutral"}`}>
              {plcResponse?.effective_enabled ? "本机浏览器已连接" : "当前未连接"}
            </span>
          </div>
          {plcQuery.isLoading ? (
            <LoadingState label="正在加载 PLC 设置" />
          ) : plcQuery.isError ? (
            <ErrorState error={plcQuery.error} />
          ) : !plcResponse?.paired ? (
            <form
              className="settings-form"
              onSubmit={(event) => {
                event.preventDefault();
                const data = new FormData(event.currentTarget);
                const name = String(data.get("station_name") || "").trim();
                const stationId = String(data.get("station_id") || "").trim();
                if (name) plcPairMutation.mutate({ name, station_id: stationId || undefined });
              }}
            >
              <div className="settings-subhead">
                <div>
                  <h4>首次绑定这台产线电脑</h4>
                  <p>配置保存在工作站记录中，不跟登录账号走；退出并重新登录后仍会读取这台电脑的设置。</p>
                </div>
                <span className="pill neutral">未绑定</span>
              </div>
              <label className="field">
                本机工作站名称
                <input name="station_name" required minLength={1} maxLength={80} placeholder="例如：一号流水线电脑" />
              </label>
              {plcWorkstationsQuery.data?.items.length ? (
                <label className="field">
                  更换浏览器时重新绑定已有工作站（可不选）
                  <select name="station_id" defaultValue="">
                    <option value="">创建新工作站</option>
                    {plcWorkstationsQuery.data.items.map((item) => (
                      <option value={item.id} key={item.id}>{item.name}</option>
                    ))}
                  </select>
                  <span className="field-hint">选择后会使旧 Edge / Chrome 的绑定和活动租约立即失效。</span>
                </label>
              ) : null}
              <div className="button-row">
                <button className="primary compact-action" type="submit" disabled={plcPairMutation.isPending}>绑定本机工作站</button>
              </div>
            </form>
          ) : plc ? (
            <>
              <div className="settings-subhead">
                <div>
                  <h4>{plcResponse.station?.name}</h4>
                  <p>Edge / Chrome 网页直接连接这台电脑上的 PLC；服务器永远不会打开串口。</p>
                </div>
                <span className={`pill ${plcResponse.station?.profile_verified ? "ok" : "neutral"}`}>
                  {plcResponse.station?.profile_verified ? "正式 PLC（已验证）" : "测试 PLC（未验证）"}
                </span>
              </div>
              <form
                className="settings-form"
                ref={plcFormRef}
                key={`${plcResponse.config_generation}-${plc.enabled}-${plc.result_register}-${plc.output_control_point}`}
                onSubmit={handlePlcSubmit}
              >
                <div className="form-grid settings-option-grid">
                  <label className="toggle-row">
                    <input name="enabled" type="checkbox" defaultChecked={plc.enabled} />
                    <span>允许这台工作站启用 PLC 联动</span>
                  </label>
                </div>
                <div className="form-grid">
                  <label className="field">
                    输出寄存器
                    <input name="result_register" pattern="D(?:0|[1-9][0-9]{0,2})" defaultValue={plc.result_register} placeholder="例如 D206" required />
                    <span className="field-hint">测试范围 D0–D255；通过写 1，不通过写 0。</span>
                  </label>
                  <label className="field">
                    输出控制点（可不填）
                    <input name="output_control_point" pattern="Y(?:0[0-7]|1[0-7])" defaultValue={plc.output_control_point} placeholder="例如 Y04；留空则不控制" />
                    <span className="field-hint">测试范围 Y00–Y17（八进制）；留空时计划和串口都不会产生 Y 指令。</span>
                  </label>
                </div>
                <details className="settings-advanced">
                  <summary>高级设置与诊断</summary>
                  <p className="hint-line">通信固定为 9600 / 偶校验 / 7 数据位 / 1 停止位；校验和包含 ETX；ACK 超时 500ms；自动重试 0 次。</p>
                  <p className="hint-line">协议地址（只读）：输出寄存器 {plcResponse.resolved_addresses.result_register || "—"}；输出控制点 {plcResponse.resolved_addresses.output_control_point || "不控制"}。工人无需理解或填写这些数值。</p>
                  <p className="hint-line">配置 generation：{plcResponse.config_generation}；协议版本：{plcResponse.protocol_version}。</p>
                </details>
                <p className="hint-line danger-text">未取得现场真实 ACK 并确认安全地址前，请保持“测试 PLC”。本版本不读取 16 个输入端口，也不自动拍照。</p>
                <p className="hint-line">检测通过写 {plc.result_register}=1，检测不通过写 {plc.result_register}=0；{plc.output_control_point ? `D 得到 ACK 后才控制 ${plc.output_control_point}` : "不直接控制流水线"}。</p>
                <div className="button-row">
                  <button className="primary compact-action" type="submit" disabled={plcMutation.isPending}>
                    <PlugZap size={16} aria-hidden="true" />
                    保存 PLC 设置
                  </button>
                  <button
                    className="secondary compact-action"
                    type="button"
                    disabled={plcVerifyMutation.isPending}
                    onClick={() => {
                      const next = !plcResponse.station?.profile_verified;
                      if (next && !window.confirm("只应在真实 PLC 已返回 ACK、地址已由 PLC 工程师确认后标记为正式。确认继续？")) return;
                      plcVerifyMutation.mutate(next);
                    }}
                  >
                    {plcResponse.station?.profile_verified ? "改回测试 PLC" : "标记真实 ACK 已验证"}
                  </button>
                </div>
              </form>

              <section className="cost-ledger-section">
                <div className="section-title compact">
                  <h4>最近同步状态</h4>
                  <span className="muted-text">当前显示最近 {plcResponse.recent_dispatches.length} 条</span>
                </div>
                <div className="cost-call-table">
                  <div className="cost-call-row head">
                    <span>时间</span>
                    <span>来源</span>
                    <span>结论</span>
                    <span>状态</span>
                  </div>
                  {plcResponse.recent_dispatches.slice(0, 12).map((item) => (
                    <div className="cost-call-row" key={item.dispatch_id}>
                      <span>{formatDateTime(item.updated_at)}</span>
                      <span>{item.source}</span>
                      <span>{item.passed ? "PASS" : "FAIL"}</span>
                      <strong className={`pill ${toneForStatus(item.status)}`}>{plcStatusLabel(item.status)}</strong>
                    </div>
                  ))}
                  {!plcResponse.recent_dispatches.length ? <div className="cost-empty-state">还没有本机摄像头同步记录。</div> : null}
                </div>
              </section>
            </>
          ) : (
            <div className="cost-empty-state">PLC 设置不可用。</div>
          )}
        </section>
      ) : null}

      {adminAllowed && settingsTab === "cost-ledger" ? (
        <section className="panel page-panel">
          <div className="section-title">
            <h3>API 成本账本</h3>
            <span className="pill neutral">管理员可见</span>
          </div>
          <div className="settings-subhead">
            <div>
              <h4>动态记账</h4>
              <p>汇总生图、AI mask、结构化输出和 Agent 调用的成本；只统计 provider 返回并保存的实际 usage，缺 usage 的历史记录不做估算。</p>
            </div>
          </div>
          {costLedgerQuery.isLoading ? (
            <LoadingState label="正在统计 API 成本" />
          ) : costLedgerQuery.isError ? (
            <ErrorState error={costLedgerQuery.error} />
          ) : costLedger ? (
            <CostLedgerPanel ledger={costLedger} />
          ) : (
            <div className="cost-empty-state">还没有成本记录。</div>
          )}
        </section>
      ) : null}

      {agentAllowed && settingsTab === "agent" ? (
        <section className="panel page-panel">
          <div className="section-title">
            <h3>Agent 接入配置</h3>
            <span className={`pill ${toneForStatus(agent?.connection_status)}`}>{agentStatusLabel}</span>
          </div>
          {agentQuery.isLoading ? (
            <LoadingState label="正在加载 Agent 设置" />
          ) : agentQuery.isError ? (
            <ErrorState error={agentQuery.error} />
          ) : (
            <>
            <div className="settings-subhead">
              <div>
                <h4>Agent 接入</h4>
                <p>任务流水线参数推荐使用；API Key 写入环境变量后在下拉框选择。</p>
              </div>
              <span className={`pill ${toneForStatus(agent?.connection_status)}`}>{agentStatusLabel}</span>
            </div>
            <form className="settings-form" ref={agentFormRef} onSubmit={handleAgentSubmit}>
              <div className="form-grid">
                <label className="field">
                  Provider
                  <select name="provider" value={agentProviderDraft} onChange={(event) => setAgentProviderDraft(event.currentTarget.value)}>
                    {!agentProviderIsKnown ? (
                      <option value={agentProviderDraft}>{agent?.provider_label || agentProviderDraft}</option>
                    ) : null}
                    {AGENT_PROVIDER_OPTIONS.map((option) => (
                      <option value={option.value} key={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Model
                  <input name="model" list="agent-model-options" defaultValue={agent?.model || ""} />
                  <datalist id="agent-model-options">
                    {(agent?.model_options || []).map((option) => (
                      <option value={option.id} key={option.id}>
                        {option.label || option.id}
                      </option>
                    ))}
                  </datalist>
                </label>
                <label className="field">
                  Base URL
                  <input name="base_url" type="url" defaultValue={agent?.base_url || ""} placeholder="https://api.openai.com/v1" />
                </label>
                <label className="field">
                  Timeout
                  <input name="timeout_seconds" type="number" min="5" max="300" step="5" defaultValue={agent?.timeout_seconds || 45} />
                </label>
              </div>
              <div className="form-grid key-grid action">
                <label className="field">
                  Active API Key
                  <select value={visibleAgentActiveKeyId} onChange={handleAgentActiveKeyChange} disabled={agentBusy || !visibleAgentKeys.length}>
                    <option value="">{visibleAgentKeys.length ? "环境变量 / 未选择" : `${selectedAgentProviderLabel} 暂无 Key`}</option>
                    {visibleAgentKeys.map((key) => (
                      <option value={key.id} key={key.id}>
                        {keyOptionLabel(key)}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="field key-action-field">
                  API Key
                  <button className="secondary compact-action" type="button" onClick={() => setApiKeyDialog("agent")} disabled={agentBusy}>
                    <Plus size={16} aria-hidden="true" />
                    添加 API Key
                  </button>
                </div>
              </div>
              {!agentProviderSaved ? (
                <p className="hint-line">当前正在编辑 {selectedAgentProviderLabel}；新增或选择 Key 会同时切换到该 Provider。</p>
              ) : null}
              <div className="form-grid settings-option-grid">
                <label className="toggle-row">
                  <input name="auto_advance_default" type="checkbox" defaultChecked={Boolean(agent?.auto_advance_default)} />
                  <span>新任务默认自动推进</span>
                </label>
              </div>
              {agent?.connection_message ? <p className="hint-line">{agent.connection_message}</p> : null}
              <div className="button-row">
                <button className="primary compact-action" type="submit" disabled={agentBusy}>
                  <KeyRound size={16} aria-hidden="true" />
                  保存 Agent 设置
                </button>
                <button
                  className="secondary compact-action"
                  type="button"
                  disabled={agentBusy}
                  onClick={() => agentTestMutation.mutate()}
                >
                  <PlugZap size={16} aria-hidden="true" />
                  测试连接
                </button>
              </div>
            </form>
            </>
          )}
        </section>
      ) : null}

      {apiKeyDialog ? (
        <div className="modal-backdrop" role="presentation">
          <form className="modal-panel api-key-modal" role="dialog" aria-modal="true" aria-label={apiKeyDialogTitle} onSubmit={handleApiKeyDialogSubmit}>
            <header className="modal-head">
              <div>
                <h3>{apiKeyDialogTitle}</h3>
                <span>{apiKeyDialogHint}</span>
              </div>
              <button className="secondary compact-action" type="button" onClick={() => setApiKeyDialog(null)} disabled={apiKeyDialogBusy}>
                取消
              </button>
            </header>
            <div className="modal-body settings-form">
              <label className="field">
                保存到环境变量
                <input name="api_key_env" type="text" defaultValue={apiKeyDialogEnv} placeholder={apiKeyDialogEnv} autoComplete="off" required />
              </label>
              <label className="field">
                API Key
                <input name="api_key" type="password" autoComplete="off" placeholder="输入新的 API Key" required autoFocus />
              </label>
            </div>
            <footer className="modal-footer">
              <button className="secondary compact-action" type="button" onClick={() => setApiKeyDialog(null)} disabled={apiKeyDialogBusy}>
                取消
              </button>
              <button className="primary compact-action" type="submit" disabled={apiKeyDialogBusy}>
                <Save size={16} aria-hidden="true" />
                保存 API Key
              </button>
            </footer>
          </form>
        </div>
      ) : null}
    </section>
  );
}

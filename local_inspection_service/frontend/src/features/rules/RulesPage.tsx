import { FormEvent, useRef } from "react";
import { KeyRound, PlugZap, RefreshCw, Save, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { hasPermission } from "../../app/permissions";
import {
  deleteActiveAiKey,
  getAgentConfig,
  getAiConfig,
  queryKeys,
  saveAgentConfig,
  saveAiConfig,
  testAgentConfig,
} from "../../api/queries";
import type { AgentConfigResponse, AiConfigResponse } from "../../api/types";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { useToast } from "../../components/ToastProvider";
import { toneForStatus } from "../../utils/format";
import { useAuth } from "../auth/auth-context";

const AI_PROVIDER_OPTIONS = [
  { value: "gemini", label: "Gemini" },
  { value: "openai", label: "OpenAI" },
  { value: "openai_compatible", label: "OpenAI 兼容" }
];

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
  if (selectedProvider && selectedProvider !== normalizedInitialProvider) {
    payload.provider = selectedProvider;
  }
  const apiKey = String(data.get("api_key") || "").trim();
  if (apiKey) payload.api_key = apiKey;
  return payload;
}

export function RulesPage() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const agentFormRef = useRef<HTMLFormElement>(null);
  const aiFormRef = useRef<HTMLFormElement>(null);

  const agentAllowed = hasPermission(auth.user, "agent_config");
  const aiAllowed = hasPermission(auth.user, "ai_config");

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

  function handleAiActiveKeyChange(event: React.ChangeEvent<HTMLSelectElement>) {
    aiMutation.mutate({ active_key_id: event.currentTarget.value });
  }

  const agent = agentQuery.data;
  const ai = aiQuery.data;
  const agentBusy = agentMutation.isPending || agentTestMutation.isPending;
  const aiBusy = aiMutation.isPending || aiKeyDeleteMutation.isPending;
  const aiProvider = ai?.provider || "gemini";
  const aiProviderIsKnown = AI_PROVIDER_OPTIONS.some((option) => option.value === aiProvider);

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
          }}
        >
          <RefreshCw size={16} aria-hidden="true" />
          刷新
        </button>
      </header>

      {aiAllowed ? (
        <section className="panel page-panel">
          <div className="section-title">
            <h3>AI 服务配置</h3>
            <span className={`pill ${toneForStatus(ai?.status)}`}>{ai?.status || "检查中"}</span>
          </div>
          {aiQuery.isLoading ? (
            <LoadingState label="正在加载 AI 设置" />
          ) : aiQuery.isError ? (
            <ErrorState error={aiQuery.error} />
          ) : (
            <form className="settings-form" ref={aiFormRef} onSubmit={handleAiSubmit}>
              <div className="form-grid">
                <label className="field">
                  Provider
                  <select name="provider" defaultValue={aiProvider}>
                    {!aiProviderIsKnown ? (
                      <option value={aiProvider}>{ai?.provider_label || aiProvider}</option>
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
                  <input name="model" list="ai-model-options" defaultValue={ai?.model || "gemini-2.5-flash-lite"} />
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
              <div className="form-grid key-grid">
                <label className="field">
                  Active API Key
                  <select value={ai?.active_key_id || ""} onChange={handleAiActiveKeyChange} disabled={aiBusy}>
                    <option value="">环境变量 / 未选择</option>
                    {(ai?.api_keys || []).map((key) => (
                      <option value={key.id} key={key.id}>
                        {key.label} · {key.masked_key}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  New API Key
                  <input name="api_key" type="password" autoComplete="off" placeholder={ai?.masked_key || "保存后只显示掩码"} />
                </label>
              </div>
              <div className="button-row">
                <button className="primary compact-action" type="submit" disabled={aiBusy}>
                  <Save size={16} aria-hidden="true" />
                  保存 AI 设置
                </button>
                <button
                  className="secondary icon-label danger"
                  type="button"
                  disabled={aiBusy || !ai?.active_key_id}
                  onClick={() => {
                    if (window.confirm("确认删除当前 API Key？")) aiKeyDeleteMutation.mutate();
                  }}
                >
                  <Trash2 size={16} aria-hidden="true" />
                  删除当前 Key
                </button>
              </div>
            </form>
          )}
        </section>
      ) : null}

      {agentAllowed ? (
        <section className="panel page-panel">
          <div className="section-title">
            <h3>Agent 接入</h3>
            <span className={`pill ${toneForStatus(agent?.connection_status)}`}>
              {agent?.connection_status || "检查中"}
            </span>
          </div>
          {agentQuery.isLoading ? (
            <LoadingState label="正在加载 Agent 设置" />
          ) : agentQuery.isError ? (
            <ErrorState error={agentQuery.error} />
          ) : (
            <form className="settings-form" ref={agentFormRef} onSubmit={handleAgentSubmit}>
              <div className="form-grid">
                <label className="field">
                  Provider
                  <select name="provider" defaultValue={agent?.provider || "openai_compatible"}>
                    <option value="openai_compatible">OpenAI 兼容</option>
                    <option value="cursor">Cursor</option>
                  </select>
                </label>
                <label className="field">
                  Base URL
                  <input name="base_url" type="url" defaultValue={agent?.base_url || ""} placeholder="https://api.openai.com/v1" />
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
                  Timeout
                  <input name="timeout_seconds" type="number" min="5" max="300" step="5" defaultValue={agent?.timeout_seconds || 45} />
                </label>
                <label className="field">
                  API Key
                  <input
                    name="api_key"
                    type="password"
                    autoComplete="off"
                    placeholder={agent?.has_api_key ? `已保存:${agent.api_key_masked}` : "保存后只显示掩码"}
                  />
                </label>
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
          )}
        </section>
      ) : null}
    </section>
  );
}

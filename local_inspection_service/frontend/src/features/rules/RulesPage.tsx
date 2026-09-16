import { FormEvent, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { apiClient } from "../../api/client";
import { workspacePath } from "../../app/paths";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { useAuth } from "../auth/auth-context";
import { useToast } from "../../components/ToastProvider";
import { DeviceSettings, LegacyCostLedger } from "./DeviceSettings";
import "./settings.css";

const API = "/api/admin/model-profiles";
type Profile = {
  id: string;
  version: number;
  name: string;
  provider: string;
  model: string;
  base_url: string;
  timeout_seconds: number;
  enabled: boolean;
  pending: boolean;
  masked_key: string;
  capabilities: string[];
  used_by: string[];
  connection_status: string;
};
type Purpose = {
  id: string;
  label: string;
  capability: string;
  advanced: boolean;
};
type Registry = {
  revision: number;
  bindings: Record<string, string>;
  profiles: Profile[];
  purposes: Purpose[];
  providers: { id: string; model: string; base_url: string }[];
};
type Engine = { name: string; engine: string; status: string; path: string };
type Call = {
  profile_id: string;
  version: number;
  purpose: string;
  model: string;
  elapsed_ms: number;
  ok: boolean;
  usage: Record<string, number>;
  priced: boolean;
  cost: number | null;
  at: number;
};

export function RulesPage() {
  const { user } = useAuth();
  return user?.role === "admin" ? (
    <AdminSettings />
  ) : (
    <section className="view active">
      <header className="page-head">
        <h2>个人与设备</h2>
      </header>
      <section className="panel page-panel">
        <h3>本机设备</h3>
        <p>相机选择与获授权的 PLC 连接操作在检测工作页进行。</p>
        <Link to={workspacePath("/inspect")}>打开检测中心</Link>
      </section>
    </section>
  );
}

function AdminSettings() {
  const { notify } = useToast();
  const [params, setParams] = useSearchParams();
  const tab = params.get("section") || "models";
  const editor = params.get("profile");
  const purpose = params.get("purpose") || "pipeline";
  const query = useQuery({
    queryKey: ["modelProfiles"],
    queryFn: () => apiClient.get<Registry>(API),
    refetchOnWindowFocus: false,
  });
  const engines = useQuery({
    queryKey: ["modelEngines"],
    queryFn: () => apiClient.get<{ items: Engine[] }>(API + "/engines"),
  });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (query.data && revision === 0) {
      setDraft(query.data.bindings);
      setRevision(query.data.revision);
    }
  }, [query.data, revision]);
  const data = query.data;
  const dirty = Boolean(
    data && JSON.stringify(draft) !== JSON.stringify(data.bindings),
  );
  async function save() {
    setBusy(true);
    try {
      const value = await apiClient.put<Registry>(API + "/bindings", {
        revision,
        bindings: draft,
      });
      setDraft(value.bindings);
      setRevision(value.revision);
      await query.refetch();
      notify({ title: "设置已保存，仅对新任务生效", tone: "success" });
    } catch (e) {
      notify({
        title: "保存失败",
        description: (e as Error).message,
        tone: "error",
      });
    } finally {
      setBusy(false);
    }
  }
  function cancel() {
    if (data) {
      setDraft(data.bindings);
      setRevision(data.revision);
    }
  }
  function open(p: string, id = "new") {
    setParams({ section: "models", profile: id, purpose: p });
  }
  async function saved(id: string) {
    const result = await query.refetch();
    if (result.data) {
      if (
        JSON.stringify(result.data.bindings) === JSON.stringify(data?.bindings)
      )
        setRevision(result.data.revision);
      if (editor === "new") setDraft((d) => ({ ...d, [purpose]: id }));
    }
    setParams({ section: "models" });
  }
  function row(p: Purpose) {
    const selected = data?.profiles.find((x) => x.id === draft[p.id]);
    return (
      <div className="model-setting-row" key={p.id}>
        <label htmlFor={"model-" + p.id}>{p.label}</label>
        <select
          id={"model-" + p.id}
          value={draft[p.id] || ""}
          disabled={busy}
          onChange={(e) => setDraft({ ...draft, [p.id]: e.target.value })}
        >
          <option value="">未配置</option>
          {data?.profiles
            .filter(
              (x) =>
                x.id === draft[p.id] ||
                (x.enabled &&
                  !x.pending &&
                  x.capabilities.includes(p.capability)),
            )
            .map((x) => (
              <option value={x.id} key={x.id}>
                {x.name} · {x.model || "待完善"} · {x.masked_key}
              </option>
            ))}
        </select>
        <button
          className="secondary compact-action"
          type="button"
          disabled={busy}
          onClick={() => open(p.id)}
        >
          添加 key
        </button>
        <span className="muted-text">
          {draft[p.id] !== data?.bindings[p.id]
            ? "待保存"
            : selected
              ? "已配置"
              : "未配置"}
        </span>
      </div>
    );
  }
  if (editor && data)
    return (
      <ProfileEditor
        key={editor}
        data={data}
        purpose={purpose}
        profile={data.profiles.find((x) => x.id === editor)}
        onBack={() => setParams({ section: "models" })}
        onSaved={saved}
      />
    );
  return (
    <section className="view active settings-workspace">
      <header className="page-head">
        <div>
          <h2>设置</h2>
          <p className="page-desc">管理模型用途、设备和 API 用量。</p>
        </div>
      </header>
      <div
        className="mode-tabs settings-tabs"
        role="tablist"
        aria-label="设置分页"
      >
        {[
          ["models", "模型与 API"],
          ["devices", "设备与运行"],
          ["usage", "用量与成本"],
        ].map(([id, label]) => (
          <button
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={"mode-tab " + (tab === id ? "active" : "")}
            key={id}
            onClick={() => setParams({ section: id })}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "models" && (
        <section className="panel page-panel">
          {query.isLoading ? (
            <LoadingState label="正在加载模型配置" />
          ) : query.isError ? (
            <ErrorState error={query.error} />
          ) : data ? (
            <>
              <section className="model-purpose-group">
                <h3>文字检验</h3>
                {data.purposes
                  .filter((p) => ["label", "manual"].includes(p.id))
                  .map(row)}
                <div className="engine-summary">
                  <strong>标签检查 Beta</strong>
                  <span>Codex 专用引擎</span>
                  <span>
                    {engines.data?.items.find((x) => x.name === "标签检查 Beta")
                      ?.status || "状态加载中"}
                  </span>
                </div>
              </section>
              <section className="model-purpose-group">
                <h3>流水线检测</h3>
                {data.purposes.filter((p) => p.id === "pipeline").map(row)}
              </section>
              <section className="model-purpose-group">
                <h3>图片生成</h3>
                {data.purposes.filter((p) => p.id === "image").map(row)}
              </section>
              <details className="settings-advanced">
                <summary>高级用途与配置管理</summary>
                {data.purposes.filter((p) => p.advanced).map(row)}
                <p className="hint-line">
                  训练助手用于参数建议、任务对话与阶段推进；不可用时回退规则逻辑。专用
                  OCR 仅支持已适配的模型。
                </p>
                <h3>配置库</h3>
                <p className="hint-line">
                  同一个配置可被多个用途选用。编辑已使用配置会为新任务生成新版本，历史任务保留原版本。
                </p>
                <div className="profile-library">
                  {data.profiles.map((p) => (
                    <div className="profile-library-row" key={p.id}>
                      <div>
                        <strong>{p.name}</strong>
                        <p>
                          {p.model || "待完善模型"} · {p.masked_key}
                        </p>
                        <small>
                          {p.used_by
                            .map(
                              (id) =>
                                data.purposes.find((x) => x.id === id)?.label,
                            )
                            .join("、") || "未被使用"}{" "}
                          · v{p.version} · {p.enabled ? "启用" : "停用"}
                        </small>
                      </div>
                      <button
                        className="secondary compact-action"
                        type="button"
                        onClick={() => open(p.used_by[0] || "pipeline", p.id)}
                      >
                        管理
                      </button>
                    </div>
                  ))}
                </div>
              </details>
              <div className="model-settings-footer">
                <span>
                  {dirty ? "有未保存的更改" : "模型选择仅对新提交的任务生效"}
                </span>
                <button
                  className="secondary"
                  type="button"
                  disabled={!dirty || busy}
                  onClick={cancel}
                >
                  取消更改
                </button>
                <button
                  className="primary"
                  type="button"
                  disabled={!dirty || busy}
                  onClick={save}
                >
                  {busy ? "保存中…" : "保存更改"}
                </button>
              </div>
            </>
          ) : null}
        </section>
      )}
      {tab === "devices" && (
        <>
          <section className="panel page-panel">
            <h3>运行状态</h3>
            {engines.isError ? (
              <ErrorState error={engines.error} />
            ) : (
              engines.data?.items.map((e) => (
                <div className="engine-summary" key={e.name}>
                  <strong>{e.name}</strong>
                  <span>
                    {e.engine} · {e.status}
                  </span>
                  <Link to={workspacePath(e.path)}>查看</Link>
                </div>
              ))
            )}
            <div className="engine-summary">
              <strong>本机相机与连接</strong>
              <span>由检测工作页管理</span>
              <Link to={workspacePath("/inspect")}>打开检测中心</Link>
            </div>
          </section>
          <DeviceSettings />
        </>
      )}
      {tab === "usage" && (
        <Usage
          profiles={data?.profiles || []}
          purposes={data?.purposes || []}
        />
      )}
    </section>
  );
}

function ProfileEditor({
  data,
  purpose,
  profile,
  onBack,
  onSaved,
}: {
  data: Registry;
  purpose: string;
  profile?: Profile;
  onBack: () => void;
  onSaved: (id: string) => Promise<void>;
}) {
  const { notify } = useToast();
  const [busy, setBusy] = useState(false);
  const [test, setTest] = useState("");
  const initial =
    profile?.provider ||
    (purpose === "label"
      ? "doubao"
      : purpose === "image"
        ? "qwen_image"
        : purpose === "training_assistant"
          ? "openai_compatible"
          : "qwen");
  const [provider, setProvider] = useState(initial);
  const [model, setModel] = useState(
    profile?.model ||
      (purpose === "ocr"
        ? "qwen-vl-ocr-2025-11-20"
        : data.providers.find((p) => p.id === initial)?.model || ""),
  );
  const [url, setUrl] = useState(
    profile?.base_url ||
      data.providers.find((p) => p.id === initial)?.base_url ||
      "",
  );
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    setBusy(true);
    try {
      const body = {
        name: fields.get("name"),
        provider,
        model,
        base_url: url,
        api_key: fields.get("api_key"),
        timeout_seconds: Number(fields.get("timeout_seconds")),
        enabled: fields.get("enabled") === "on",
        version: profile?.version,
      };
      const result = profile
        ? await apiClient.put<{ id: string }>(API + "/" + profile.id, body)
        : await apiClient.post<{ id: string }>(API, body);
      notify({
        title: profile ? "配置版本已保存" : "配置已添加，请保存用途选择",
        tone: "success",
      });
      await onSaved(result.id);
    } catch (e) {
      notify({
        title: "保存失败",
        description: (e as Error).message,
        tone: "error",
      });
    } finally {
      setBusy(false);
    }
  }
  async function check() {
    if (!profile) return;
    setBusy(true);
    try {
      const r = await apiClient.post<{ message: string }>(
        API + "/" + profile.id + "/test",
      );
      setTest(r.message);
    } catch (e) {
      setTest((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="view active settings-workspace">
      <header className="page-head">
        <div>
          <button
            className="secondary compact-action"
            disabled={busy}
            onClick={onBack}
          >
            返回模型与 API
          </button>
          <h2>{profile ? "管理配置" : "添加 key"}</h2>
          <p className="page-desc">
            一个配置包含一个模型及其 API Key，可供多个用途选用。
          </p>
        </div>
      </header>
      <form
        className="panel page-panel settings-form profile-editor"
        onSubmit={submit}
      >
        <label className="field">
          配置名称
          <input
            name="name"
            required
            maxLength={100}
            defaultValue={profile?.name}
            placeholder="例如：豆包 · 标签主配置"
          />
        </label>
        <label className="field">
          服务商
          <select
            value={provider}
            onChange={(e) => {
              const p = data.providers.find((p) => p.id === e.target.value)!;
              setProvider(p.id);
              setModel(p.model);
              setUrl(p.base_url);
            }}
          >
            {data.providers.map((p) => (
              <option key={p.id} value={p.id}>
                {(
                  {
                    doubao: "豆包 / 火山方舟",
                    qwen: "千问 / 百炼",
                    gemini: "Gemini",
                    qwen_image: "千问图片生成",
                    agnes: "Agnes Image",
                    openai_compatible: "OpenAI 兼容",
                    cursor: "Cursor",
                  } as Record<string, string>
                )[p.id] || p.id}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          模型 ID
          <input
            required
            value={model}
            onChange={(e) => setModel(e.target.value)}
            maxLength={200}
          />
        </label>
        <label className="field">
          API Key
          <input
            name="api_key"
            type="password"
            autoComplete="new-password"
            required={!profile}
            maxLength={8192}
            placeholder={
              profile
                ? "留空保留现有 Key " + profile.masked_key
                : "输入 API Key"
            }
          />
        </label>
        <details className="settings-advanced">
          <summary>接口地址与高级参数</summary>
          <label className="field">
            接口地址
            <input
              type="url"
              required
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </label>
          <label className="field">
            请求超时（秒）
            <input
              type="number"
              name="timeout_seconds"
              min={1}
              max={600}
              defaultValue={
                profile?.timeout_seconds || (purpose === "label" ? 180 : 30)
              }
            />
          </label>
          <label className="toggle-row">
            <input
              name="enabled"
              type="checkbox"
              defaultChecked={profile?.enabled ?? true}
            />
            <span>启用配置（已被使用的配置须先解除绑定才能停用）</span>
          </label>
        </details>
        <p className="hint-line">
          连接测试针对已保存版本，不会保存本页修改，也不代表检测准确率达标。
        </p>
        {test && <p role="status">{test}</p>}
        <div className="button-row">
          <button
            type="button"
            className="secondary"
            disabled={!profile || busy}
            onClick={check}
          >
            测试已保存配置
          </button>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "保存中…" : "保存配置"}
          </button>
        </div>
      </form>
    </section>
  );
}

function Usage({
  profiles,
  purposes,
}: {
  profiles: Profile[];
  purposes: Purpose[];
}) {
  const query = useQuery({
    queryKey: ["profileUsage"],
    queryFn: () => apiClient.get<{ items: Call[] }>(API + "/usage"),
    refetchInterval: 30000,
  });
  const [filter, setFilter] = useState("");
  const [groupBy, setGroupBy] = useState("purpose");
  const rows = (query.data?.items || []).filter(
    (r) => !filter || r.purpose === filter,
  );
  const tokens = (r: Call) =>
    r.usage.total_tokens ??
    r.usage.totalTokenCount ??
    (r.usage.prompt_tokens ?? r.usage.input_tokens ?? 0) +
      (r.usage.completion_tokens ?? r.usage.output_tokens ?? 0);
  const grouped = new Map<string, Call[]>();
  for (const call of rows) {
    const key =
      groupBy === "profile"
        ? call.profile_id
        : groupBy === "model"
          ? call.model
          : call.purpose;
    grouped.set(key, [...(grouped.get(key) || []), call]);
  }
  const groupLabel = (key: string) =>
    groupBy === "profile"
      ? profiles.find((p) => p.id === key)?.name || key
      : groupBy === "purpose"
        ? purposes.find((p) => p.id === key)?.label || key
        : key;
  return (
    <section className="panel page-panel">
      <h3>模型调用</h3>
      <p className="hint-line">
        最近 500 次已记录调用；历史成本单独显示。没有返回 usage
        或未配置价格的调用不做估算。
      </p>
      <label className="field">
        业务用途
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">全部用途</option>
          {purposes.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      <p>
        {rows.length} 次调用 · {rows.filter((r) => !r.ok).length} 次失败 ·{" "}
        {rows.reduce((n, r) => n + tokens(r), 0)} tokens
      </p>
      <label className="field">
        汇总方式
        <select value={groupBy} onChange={(e) => setGroupBy(e.target.value)}>
          <option value="purpose">按业务用途</option>
          <option value="profile">按配置对象</option>
          <option value="model">按模型</option>
        </select>
      </label>
      <div className="settings-table-scroll">
        <table className="settings-usage-table">
          <thead>
            <tr>
              <th>分组</th>
              <th>调用 / 失败</th>
              <th>平均耗时</th>
              <th>Token</th>
              <th>已计价费用</th>
              <th>未计价调用</th>
            </tr>
          </thead>
          <tbody>
            {[...grouped].map(([key, calls]) => (
              <tr key={key}>
                <td>{groupLabel(key)}</td>
                <td>
                  {calls.length} / {calls.filter((r) => !r.ok).length}
                </td>
                <td>
                  {Math.round(
                    calls.reduce((n, r) => n + r.elapsed_ms, 0) / calls.length,
                  )}{" "}
                  ms
                </td>
                <td>{calls.reduce((n, r) => n + tokens(r), 0)}</td>
                <td>
                  {calls.some((r) => r.priced)
                    ? `$${calls.reduce((n, r) => n + (r.cost ?? 0), 0).toFixed(6)}`
                    : "未计价"}
                </td>
                <td>{calls.filter((r) => !r.priced).length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="settings-advanced">
        <summary>调用明细</summary>
        {query.isError ? (
          <ErrorState error={query.error} />
        ) : (
          <div className="settings-table-scroll">
            <table className="settings-usage-table">
              <thead>
                <tr>
                  <th>用途 / 配置</th>
                  <th>模型</th>
                  <th>耗时</th>
                  <th>Token</th>
                  <th>结果</th>
                  <th>费用</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td>
                      {purposes.find((p) => p.id === r.purpose)?.label ||
                        r.purpose}
                      <br />
                      {profiles.find((p) => p.id === r.profile_id)?.name ||
                        r.profile_id}{" "}
                      · v{r.version}
                    </td>
                    <td>{r.model}</td>
                    <td>{r.elapsed_ms} ms</td>
                    <td>{tokens(r) || "未返回"}</td>
                    <td>{r.ok ? "完成" : "失败"}</td>
                    <td>
                      {r.priced && r.cost !== null
                        ? `$${r.cost.toFixed(6)}`
                        : "未计价"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </details>
      <details className="settings-advanced">
        <summary>历史成本账本</summary>
        <LegacyCostLedger />
      </details>
    </section>
  );
}

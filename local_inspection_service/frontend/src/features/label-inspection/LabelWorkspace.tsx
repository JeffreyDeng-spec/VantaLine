import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../../api/client";
import { FileDropZone } from "../../components/FileDropZone";
import { useAuth } from "../auth/auth-context";
import {
  ComparisonResult,
  type SavedComparison,
} from "../text-compare/ComparisonResult";
import "./label-workspace.css";

const API = "/api/label-inspection";
const PAGE = "/workspace/label-inspection";
type Media = {
  original: string;
  image: string;
  preview: string;
  size: [number, number];
};
type Asset = {
  id: string;
  name: string;
  ordinal: number;
  enabled: boolean;
  media?: Media;
  error?: string;
  duplicate_of?: string;
  legacy_url?: string;
};
type Issue = {
  id: number;
  type: string;
  category: string;
  description: string;
  standardText: string;
  actualText: string;
  severity: string;
  confidence: string;
  position_note?: string;
  reference_box?: number[];
  actual_box?: number[];
};
type Run = {
  id: string;
  task_id: string;
  created_at: number;
  status: string;
  decision: string;
  revision: number;
  phase?: string;
  elapsed?: number;
  reference?: Asset;
  actual?: Media;
  crop?: number[];
  scope?: string;
  error?: string;
  legacy_record_id?: string;
  result?: { decision: string; similarity: number; issues: Issue[] };
};
type Task = {
  id: string;
  name: string;
  revision: number;
  assets: Asset[];
  runs: Run[];
  missing?: string;
};
type Row = {
  id: string;
  name: string;
  source: string;
  updated_at: number;
  standard_count: number;
  run_count: number;
  decision: string;
  status: string;
  url?: string;
};
const labels: Record<string, string> = {
  word: "Word 导入",
  legacy: "旧文字检验",
  beta: "标签检查 Beta",
  MATCH: "未发现差异",
  DIFFERENCES: "发现差异",
  REVIEW_REQUIRED: "待复核",
  queued: "排队中",
  running: "检测中",
  ready: "未检测",
  completed: "已完成",
  failed: "检测失败",
  interrupted: "检测中断",
  high: "高",
  medium: "中",
  low: "低",
  layout: "识别标签布局",
  compare: "对比标签",
  missing_line: "缺失整行",
  missing_text: "缺失文字",
  extra: "多余内容",
  wrong_char: "错字",
  case_diff: "大小写差异",
  punctuation_diff: "标点差异",
  icon_diff: "图标差异",
  shape_diff: "外形差异",
};
const text = (value: string) => labels[value] || value;
const when = (stamp: number) => new Date(stamp * 1000).toLocaleString();
const key = () => crypto.randomUUID();
const mediaURL = (task: string, sha: string) =>
  `${API}/tasks/${encodeURIComponent(task)}/media/${sha}`;
function form(file: File, values: Record<string, string | number> = {}) {
  const data = new FormData();
  data.set("file", file);
  data.set("request_id", key());
  for (const [k, v] of Object.entries(values)) data.set(k, String(v));
  return data;
}
function Evidence({
  url,
  title,
  size,
  crop,
  box,
  onZoom,
}: {
  url: string;
  title: string;
  size?: number[];
  crop?: number[];
  box?: number[];
  onZoom: (url: string) => void;
}) {
  const [bad, setBad] = useState(false);
  useEffect(() => setBad(false), [url]);
  return bad ? (
    <p role="status">图片缺失或无法读取</p>
  ) : (
    <button
      className="li-image"
      onClick={() => onZoom(url)}
      aria-label={`放大${title}`}
    >
      <span>
        <img src={url} alt={title} onError={() => setBad(true)} />
        {(crop && size) || box ? (
          <svg
            viewBox="0 0 1000 1000"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            {crop && size ? (
              <rect
                className="li-crop"
                x={(crop[0] / size[0]) * 1000}
                y={(crop[1] / size[1]) * 1000}
                width={(crop[2] / size[0]) * 1000}
                height={(crop[3] / size[1]) * 1000}
              />
            ) : null}
            {box ? (
              <rect
                x={box[0] * 1000}
                y={box[1] * 1000}
                width={box[2] * 1000}
                height={box[3] * 1000}
              />
            ) : null}
          </svg>
        ) : null}
      </span>
    </button>
  );
}
function Camera({
  onPhoto,
  onError,
}: {
  onPhoto: (file: File) => void;
  onError: (e: unknown) => void;
}) {
  const video = useRef<HTMLVideoElement>(null),
    stream = useRef<MediaStream | null>(null),
    generation = useRef(0);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]),
    [device, setDevice] = useState(""),
    [active, setActive] = useState(false),
    [starting, setStarting] = useState(false);
  function stop() {
    ++generation.current;
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    setActive(false);
    setStarting(false);
  }
  useEffect(() => {
    const pause = () => {
      if (document.hidden) stop();
    };
    document.addEventListener("visibilitychange", pause);
    return () => {
      document.removeEventListener("visibilitychange", pause);
      stop();
    };
  }, []);
  async function start() {
    stop();
    const token = generation.current;
    setStarting(true);
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        video: device
          ? { deviceId: { exact: device } }
          : { facingMode: "environment" },
        audio: false,
      });
      if (token !== generation.current) {
        s.getTracks().forEach((t) => t.stop());
        return;
      }
      stream.current = s;
      if (video.current) {
        video.current.srcObject = s;
        await video.current.play();
      }
      if (token !== generation.current) return;
      setActive(true);
      setDevices(
        (await navigator.mediaDevices.enumerateDevices()).filter(
          (x) => x.kind === "videoinput",
        ),
      );
      s.getVideoTracks()[0].onended = () => {
        stop();
        onError(new Error("摄像头已断开，请重新开启"));
      };
    } catch (e) {
      if (token === generation.current) {
        stop();
        onError(e);
      }
    } finally {
      if (token === generation.current) setStarting(false);
    }
  }
  function capture() {
    const v = video.current;
    if (!v || !v.videoWidth || !active) return;
    const canvas = document.createElement("canvas");
    const scale = Math.min(
      1,
      Math.sqrt(16_000_000 / (v.videoWidth * v.videoHeight)),
    );
    canvas.width = Math.floor(v.videoWidth * scale);
    canvas.height = Math.floor(v.videoHeight * scale);
    canvas.getContext("2d")!.drawImage(v, 0, 0, canvas.width, canvas.height);
    const token = generation.current;
    canvas.toBlob(
      (blob) => {
        if (blob && token === generation.current) {
          onPhoto(new File([blob], "实物拍照.jpg", { type: "image/jpeg" }));
          stop();
        }
      },
      "image/jpeg",
      0.95,
    );
  }
  return (
    <div className="li-camera">
      <video ref={video} muted playsInline hidden={!active && !starting} />
      <div className="li-actions">
        <select
          aria-label="选择摄像头"
          value={device}
          onChange={(e) => {
            stop();
            setDevice(e.target.value);
          }}
        >
          <option value="">默认摄像头</option>
          {devices.map((d, i) => (
            <option value={d.deviceId} key={d.deviceId}>
              {d.label || `摄像头 ${i + 1}`}
            </option>
          ))}
        </select>
        <button onClick={() => void start()} disabled={starting}>
          {starting ? "正在开启…" : active ? "重新连接" : "开启摄像头 / 重拍"}
        </button>
        {active ? (
          <>
            <button onClick={capture}>拍照</button>
            <button onClick={stop}>关闭摄像头</button>
          </>
        ) : null}
      </div>
    </div>
  );
}
function Diagnostics({ id }: { id: string }) {
  const [open, setOpen] = useState(false);
  const data = useQuery({
    queryKey: ["label-diagnostics", id],
    queryFn: () => apiClient.get(`${API}/runs/${id}/diagnostics`),
    enabled: open,
    retry: false,
  });
  return (
    <details onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>调用诊断（默认折叠）</summary>
      {open ? (
        <pre>
          {data.isError ? "诊断读取失败" : JSON.stringify(data.data, null, 2)}
        </pre>
      ) : null}
    </details>
  );
}
function LegacyResult({
  id,
  onZoom,
}: {
  id: string;
  onZoom: (url: string) => void;
}) {
  const result = useQuery({
    queryKey: ["label-legacy-result", id],
    queryFn: () =>
      apiClient.get<SavedComparison>(`/api/text-inspection/history/${id}`),
    retry: false,
  });
  return result.data ? (
    <ComparisonResult result={result.data} onZoom={onZoom} />
  ) : (
    <p role="status">{result.isError ? "旧记录读取失败" : "正在读取旧结果…"}</p>
  );
}
export function LabelWorkspace() {
  const { user, logout } = useAuth();
  const cache = useQueryClient();
  const [params, setParams] = useSearchParams();
  const taskId = params.get("task") || "",
    runId = params.get("run") || "",
    isNew = params.get("view") === "new";
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [selected, setSelected] = useState(""),
    [gallery, setGallery] = useState(true),
    [hidden, setHidden] = useState(false),
    [actual, setActual] = useState<File | null>(null),
    [preview, setPreview] = useState(""),
    [zoom, setZoom] = useState(""),
    [issue, setIssue] = useState<number | null>(null),
    [rename, setRename] = useState(""),
    [parent, setParent] = useState("");
  const [q, setQ] = useState(""),
    [source, setSource] = useState("all"),
    [decision, setDecision] = useState("all"),
    [cursor, setCursor] = useState(""),
    [rows, setRows] = useState<Row[]>([]);
  const mounted = useRef(true),
    submission = useRef(false);
  const pendingKey = `label-submit:${user.id}:${taskId}`;
  const [pending, setPending] = useState("");
  useEffect(
    () => setPending(sessionStorage.getItem(pendingKey) || ""),
    [pendingKey],
  );
  const recovery = useQuery({
    queryKey: ["label-request", user.id, pending],
    queryFn: () =>
      apiClient.get<{ run: Run | null }>(`${API}/requests/${pending}`),
    enabled: !!pending,
    retry: false,
    refetchInterval: 1500,
  });
  useEffect(() => {
    if (recovery.data?.run && pending && recovery.data.run.task_id === taskId) {
      sessionStorage.removeItem(pendingKey);
      setPending("");
      setParams({ task: recovery.data.run.task_id, run: recovery.data.run.id });
    }
  }, [recovery.data, pending, pendingKey, setParams, taskId]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    if (!actual) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(actual);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [actual]);
  useEffect(() => {
    setActual(null);
    setSelected("");
    setGallery(true);
    setError("");
    setParent("");
  }, [taskId]);
  useEffect(() => {
    setIssue(null);
    setActual(null);
  }, [runId]);
  useEffect(() => {
    setCursor("");
    setRows([]);
  }, [q, source, decision]);
  const capabilities = useQuery({
    queryKey: ["label-capabilities", user.id],
    queryFn: () => apiClient.get<{ enabled: boolean }>(`${API}/capabilities`),
    retry: false,
  });
  const list = useQuery({
    queryKey: ["label-list", user.id, q, source, decision, cursor],
    queryFn: () =>
      apiClient.get<{ items: Row[]; next_cursor: string | null }>(
        `${API}/tasks?${new URLSearchParams({ q, source, result: decision, cursor })}`,
      ),
    enabled: !taskId && !isNew,
    retry: false,
  });
  useEffect(() => {
    if (list.data)
      setRows((old) =>
        cursor
          ? [
              ...old.filter(
                (x) => !list.data!.items.some((y) => y.id === x.id),
              ),
              ...list.data!.items,
            ]
          : list.data!.items,
      );
  }, [list.data, cursor]);
  const task = useQuery({
    queryKey: ["label-task", user.id, taskId],
    queryFn: () =>
      apiClient.get<Task>(`${API}/tasks/${encodeURIComponent(taskId)}`),
    enabled: !!taskId,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.runs.some((r) =>
        ["queued", "running"].includes(r.status),
      )
        ? 1500
        : false,
  });
  const value = task.data,
    run = value?.runs.find((r) => r.id === runId),
    running = value?.runs.find((r) => ["queued", "running"].includes(r.status)),
    reference = run?.reference || value?.assets.find((a) => a.id === selected),
    activeIssue = run?.result?.issues.find((i) => i.id === issue);
  useEffect(() => {
    if (value) setRename(value.name);
  }, [value?.name]);
  function fail(e: unknown) {
    setError(e instanceof Error ? e.message : "操作失败，请重试");
  }
  async function perform(fn: () => Promise<void>) {
    if (submission.current) return;
    submission.current = true;
    setBusy(true);
    setError("");
    try {
      await fn();
      await cache.invalidateQueries({ queryKey: ["label-task"] });
      await cache.invalidateQueries({ queryKey: ["label-list"] });
    } catch (e) {
      fail(e);
    } finally {
      submission.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  function openTask(id: string) {
    setParams({ task: id });
  }
  function photo(file: File) {
    if (file.size > 10 * 1024 * 1024) {
      fail(new Error("实物图片不能超过 10 MiB"));
      return;
    }
    setActual(file);
  }
  function fresh() {
    if (runId) setParent(runId.startsWith("legacy:") ? "" : runId);
    if (run?.reference) setSelected(run.reference.id);
    setParams({ task: taskId });
    setActual(null);
    setGallery(false);
  }
  async function edit(operation: string, value: string) {
    if (!task.data) return;
    await apiClient.patch(`${API}/tasks/${task.data.id}`, {
      request_id: key(),
      revision: task.data.revision,
      operation,
      value,
    });
  }
  const permitted =
    user.role === "admin" || (user.permissions || []).includes("inspection");
  return (
    <main className="label-workspace">
      <header className="li-header">
        <Link
          to={PAGE}
          onClick={() => {
            setRows([]);
            setCursor("");
          }}
        >
          文字检验
        </Link>
        <span>标签对比</span>
        <nav>
          <Link to={`${PAGE}?view=new`}>新建任务</Link>
          <Link to="/workspace/text-compare-beta?mode=manual">说明书检验</Link>
          <Link to="/workspace">返回主平台</Link>
          <button onClick={() => void logout().catch(fail)}>退出登录</button>
        </nav>
      </header>
      {!permitted ? (
        <p role="alert">当前账号没有文字检验权限</p>
      ) : (
        <>
          {pending ? (
            <p className="li-warning">
              正在查询上次提交状态，页面刷新不会再次调用模型。
              <button onClick={() => void recovery.refetch()}>
                查询提交状态
              </button>
              {!busy && recovery.data && !recovery.data.run ? (
                <button
                  onClick={() => {
                    setPending("");
                  }}
                >
                  尚未找到记录，手动重新提交同一请求
                </button>
              ) : null}
            </p>
          ) : null}
          {error || list.error || task.error ? (
            <div className="li-error" role="alert">
              {error || (task.error || list.error)?.message}
              <button
                onClick={() => {
                  setError("");
                  void task.refetch();
                  void list.refetch();
                }}
              >
                刷新
              </button>
            </div>
          ) : null}
          {capabilities.data && !capabilities.data.enabled ? (
            <p className="li-warning">
              新检测服务暂不可用，您仍可管理任务和查看历史。
            </p>
          ) : null}
          {!taskId && !isNew ? (
            <section className="li-list">
              <div className="li-title">
                <div>
                  <h1>检测任务</h1>
                  <p>导入一份 Word，保存标准，持续检查每一件产品。</p>
                </div>
                <Link className="li-primary" to={`${PAGE}?view=new`}>
                  ＋ 新建任务
                </Link>
              </div>
              <div className="li-actions">
                <input
                  aria-label="搜索任务名称"
                  placeholder="搜索任务名称"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
                <select
                  aria-label="任务来源"
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                >
                  {["all", "word", "legacy", "beta"].map((x) => (
                    <option key={x} value={x}>
                      {x === "all" ? "全部来源" : text(x)}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="结果筛选"
                  value={decision}
                  onChange={(e) => setDecision(e.target.value)}
                >
                  {["all", "MATCH", "DIFFERENCES", "REVIEW_REQUIRED"].map(
                    (x) => (
                      <option key={x} value={x}>
                        {x === "all" ? "全部结果" : text(x)}
                      </option>
                    ),
                  )}
                </select>
              </div>
              <div className="li-table">
                <table>
                  <thead>
                    <tr>
                      <th>任务名称</th>
                      <th>来源</th>
                      <th>标准</th>
                      <th>检测次数</th>
                      <th>最近结果</th>
                      <th>最近活动</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.id}>
                        <td>
                          <Link
                            to={
                              row.url ||
                              `${PAGE}?task=${encodeURIComponent(row.id)}`
                            }
                          >
                            {row.name}
                          </Link>
                        </td>
                        <td>{text(row.source)}</td>
                        <td>{row.standard_count}</td>
                        <td>{row.run_count}</td>
                        <td>
                          {row.run_count ? text(row.decision) : "未检测"} ·{" "}
                          {text(row.status)}
                        </td>
                        <td>{when(row.updated_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {list.isLoading ? (
                <p>正在读取任务…</p>
              ) : !rows.length ? (
                <p>没有符合条件的任务。</p>
              ) : null}
              {list.data?.next_cursor ? (
                <button
                  onClick={() => setCursor(list.data!.next_cursor!)}
                  disabled={list.isFetching}
                >
                  加载更多
                </button>
              ) : null}
            </section>
          ) : null}
          {isNew && !taskId ? (
            <section className="li-import">
              <Link to={PAGE}>← 返回任务列表</Link>
              <h1>新建检测任务</h1>
              <p>
                直接提取文档中的全部图片，保留重复图片；导入后手动选择标准检测。
              </p>
              <FileDropZone
                accept=".doc,.docx"
                disabled={busy}
                ariaLabel="导入 Word 创建任务"
                onFiles={(files) => {
                  if (files[0])
                    void perform(async () => {
                      const created = await apiClient.upload<Task>(
                        `${API}/tasks`,
                        form(files[0]),
                      );
                      openTask(created.id);
                    });
                }}
              >
                <strong>
                  {busy ? "正在提取图片…" : "拖入 Word 文档，或点击选择"}
                </strong>
                <span>DOC ≤ 30 MiB · DOCX ≤ 100 MiB · 最多 500 个标准条目</span>
              </FileDropZone>
            </section>
          ) : null}
          {taskId && !value ? <p>正在读取任务…</p> : null}
          {value ? (
            <>
              <section className="li-title">
                <div>
                  <Link to={PAGE}>← 任务列表</Link>
                  <h1>{value.name}</h1>
                  <span>
                    标准版本 {value.revision || "旧版"} · {value.assets.length}{" "}
                    张标准 · {value.runs.length} 次检测
                  </span>
                </div>
                <div className="li-actions">
                  {value.revision ? (
                    <>
                      <input
                        aria-label="任务名称"
                        value={rename}
                        onChange={(e) => setRename(e.target.value)}
                        maxLength={200}
                      />
                      <button
                        disabled={busy || !rename.trim()}
                        onClick={() => void perform(() => edit("name", rename))}
                      >
                        保存名称
                      </button>
                    </>
                  ) : (
                    <button
                      disabled={busy || !!value.missing}
                      onClick={() =>
                        void perform(async () => {
                          const continued = await apiClient.post<Task>(
                            `${API}/tasks/${encodeURIComponent(value.id)}/continue`,
                          );
                          openTask(continued.id);
                        })
                      }
                    >
                      继续检测（建立标准快照）
                    </button>
                  )}
                </div>
              </section>
              {value.missing ? <p role="alert">{value.missing}</p> : null}
              <div className="li-columns">
                <section className="li-panel">
                  <header>
                    <h2>标准标签</h2>
                    <span>
                      {run
                        ? `本次检测冻结版本 ${run.revision}`
                        : "手动选择标准"}
                    </span>
                    {!run && !gallery ? (
                      <button onClick={() => setGallery(true)}>
                        返回缩略图
                      </button>
                    ) : null}
                  </header>
                  {reference && (run || !gallery) ? (
                    <>
                      <Evidence
                        url={
                          reference.media
                            ? mediaURL(value.id, reference.media.image)
                            : reference.legacy_url || ""
                        }
                        title="标准图"
                        onZoom={setZoom}
                        box={activeIssue?.reference_box}
                      />
                      <p>{reference.name}</p>
                    </>
                  ) : (
                    <div className="li-gallery">
                      {value.assets
                        .filter((a) => hidden || a.enabled || !value.revision)
                        .map((a) => (
                          <article
                            key={a.id}
                            className={selected === a.id ? "selected" : ""}
                          >
                            <button
                              aria-label={`选择标准 ${a.ordinal}`}
                              disabled={!!run}
                              onClick={() => {
                                setSelected(a.id);
                                setGallery(false);
                              }}
                            >
                              {a.media || a.legacy_url ? (
                                <img
                                  loading="lazy"
                                  src={
                                    a.media
                                      ? mediaURL(value.id, a.media.preview)
                                      : a.legacy_url
                                  }
                                  alt={a.name}
                                />
                              ) : (
                                <span>无法读取图片</span>
                              )}
                              <strong>
                                {a.ordinal}. {a.name}
                              </strong>
                            </button>
                            {a.error ? <small>{a.error}</small> : null}
                            {a.duplicate_of ? (
                              <small>重复出现的图片</small>
                            ) : null}
                            {value.revision ? (
                              <button
                                disabled={
                                  busy || !!run || (!a.enabled && !a.media)
                                }
                                onClick={() =>
                                  void perform(() =>
                                    edit(a.enabled ? "hide" : "restore", a.id),
                                  )
                                }
                              >
                                {a.enabled ? "隐藏标准" : "恢复标准"}
                              </button>
                            ) : null}
                          </article>
                        ))}
                    </div>
                  )}
                  {!run && !!value.revision ? (
                    <>
                      <label>
                        <input
                          type="checkbox"
                          checked={hidden}
                          onChange={(e) => setHidden(e.target.checked)}
                        />{" "}
                        显示已隐藏 / 无效标准
                      </label>
                      <FileDropZone
                        accept="image/*"
                        disabled={busy}
                        ariaLabel="追加标准图片"
                        onFiles={(files) => {
                          if (files[0])
                            void perform(async () => {
                              await apiClient.upload(
                                `${API}/tasks/${value.id}/assets`,
                                form(files[0], { revision: value.revision }),
                              );
                            });
                        }}
                      >
                        ＋ 追加标准图片（创建新版本）
                      </FileDropZone>
                    </>
                  ) : null}
                </section>
                <section className="li-panel">
                  <header>
                    <h2>实物标签</h2>
                    <span>{run ? "历史原图" : "拍照或上传一张实物照片"}</span>
                  </header>
                  {run?.actual ? (
                    <Evidence
                      url={mediaURL(value.id, run.actual.image)}
                      title="实物图"
                      onZoom={setZoom}
                      size={run.actual.size}
                      crop={run.crop}
                      box={activeIssue?.actual_box}
                    />
                  ) : preview ? (
                    <Evidence
                      url={preview}
                      title="待检实物图"
                      onZoom={setZoom}
                    />
                  ) : (
                    <div className="li-placeholder">等待实物照片</div>
                  )}
                  {run?.scope ? (
                    <p className={run.crop ? "li-warning" : ""}>
                      {run.scope}
                      {run.crop ? "；框外其他标签没有检测。" : ""}
                    </p>
                  ) : null}
                  {!run && !!value.revision ? (
                    <>
                      <FileDropZone
                        accept="image/*"
                        disabled={busy || !!running}
                        ariaLabel="上传实物照片"
                        onFiles={(files) => {
                          if (files[0]) photo(files[0]);
                        }}
                      >
                        {actual
                          ? `重新上传 · ${actual.name}`
                          : "拖入实物图片，或点击上传（≤ 10 MiB / 1600 万像素）"}
                      </FileDropZone>
                      <Camera
                        key={taskId + runId}
                        onPhoto={photo}
                        onError={fail}
                      />
                    </>
                  ) : null}
                </section>
              </div>
              {!run ? (
                <div className="li-detect">
                  <button
                    className="li-primary"
                    disabled={
                      busy ||
                      !!pending ||
                      !!running ||
                      !reference?.enabled ||
                      !actual ||
                      !capabilities.data?.enabled
                    }
                    onClick={() =>
                      void perform(async () => {
                        if (!actual || !reference) return;
                        const requestId =
                          sessionStorage.getItem(pendingKey) || key();
                        sessionStorage.setItem(pendingKey, requestId);
                        setPending(requestId);
                        const created = await apiClient.upload<Run>(
                          `${API}/tasks/${value.id}/runs`,
                          form(actual, {
                            request_id: requestId,
                            revision: value.revision,
                            asset_id: reference.id,
                            parent_id: parent,
                          }),
                        );
                        sessionStorage.removeItem(pendingKey);
                        setPending("");
                        setParams({ task: value.id, run: created.id });
                      })
                    }
                  >
                    {busy
                      ? "正在提交…"
                      : running
                        ? "任务已有检测进行中"
                        : "开始检测"}
                  </button>
                  <p>自动选择一张标签，检查文字、大小写、图标和外形。</p>
                  {running ? (
                    <button
                      onClick={() =>
                        setParams({ task: value.id, run: running.id })
                      }
                    >
                      查看进行中的检测
                    </button>
                  ) : null}
                </div>
              ) : null}
              {run ? (
                <section className="li-results">
                  <header>
                    <h2
                      className={
                        run.status === "completed" && run.decision === "MATCH"
                          ? "li-pass"
                          : run.decision === "DIFFERENCES"
                            ? "li-diff"
                            : ""
                      }
                    >
                      {run.status === "completed"
                        ? text(run.decision)
                        : text(run.status)}
                    </h2>
                    <span>
                      {when(run.created_at)} · {run.elapsed?.toFixed(1) ?? "—"}{" "}
                      秒
                    </span>
                    <button
                      disabled={["queued", "running"].includes(run.status)}
                      onClick={fresh}
                    >
                      检测下一件
                    </button>
                  </header>
                  {run.error ? <p role="alert">{run.error}</p> : null}
                  {["queued", "running"].includes(run.status) ? (
                    <p role="status">
                      {text(run.phase || run.status)}…
                      可以关闭页面，结果会自动保存，请勿重复提交。
                    </p>
                  ) : null}
                  {run.legacy_record_id ? (
                    <LegacyResult id={run.legacy_record_id} onZoom={setZoom} />
                  ) : null}
                  {run.result ? (
                    <>
                      <p>
                        {run.result.issues.length} 项差异 · 模型评分{" "}
                        {run.result.similarity} / 100（不是系统准确率）
                      </p>
                      {run.result.issues.map((i) => (
                        <button
                          className={`li-issue ${issue === i.id ? "selected" : ""}`}
                          key={i.id}
                          onClick={() => setIssue(i.id)}
                        >
                          <strong>
                            {i.id}. {text(i.type)} · 严重程度：
                            {text(i.severity) || "未提供"} · 模型置信度：
                            {text(i.confidence) || "未提供"}
                          </strong>
                          <span>
                            标准：{i.standardText || "未提供"}　实物：
                            {i.actualText || "未提供"}
                          </span>
                          <p>{i.description}</p>
                          {i.position_note ? (
                            <small>{i.position_note}</small>
                          ) : null}
                        </button>
                      ))}
                    </>
                  ) : null}
                  {!run.legacy_record_id ? <Diagnostics id={run.id} /> : null}
                </section>
              ) : runId ? (
                <p role="alert">当前任务内不存在该检测记录。</p>
              ) : null}
              <section className="li-history">
                <h2>任务内历史</h2>
                {value.runs.map((r) => (
                  <button
                    className={r.id === runId ? "selected" : ""}
                    key={r.id}
                    onClick={() => setParams({ task: value.id, run: r.id })}
                  >
                    {when(r.created_at)} ·{" "}
                    {r.legacy_record_id ? "旧文字检验" : "Evolving"} ·{" "}
                    {text(r.decision)} · {text(r.status)} · 版本{" "}
                    {r.revision ?? "未留存"}
                  </button>
                ))}
                {!value.runs.length ? <p>还没有检测记录。</p> : null}
              </section>
            </>
          ) : null}
        </>
      )}
      {zoom ? (
        <div
          className="li-modal"
          role="dialog"
          aria-modal="true"
          aria-label="图片放大"
          onClick={() => setZoom("")}
          onKeyDown={(e) => {
            if (e.key === "Escape") setZoom("");
          }}
        >
          <button autoFocus onClick={() => setZoom("")}>
            关闭放大
          </button>
          <img
            src={zoom}
            alt="原尺寸图片"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      ) : null}
    </main>
  );
}

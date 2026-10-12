import { FormEvent, useState } from "react";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { apiClient } from "../../api/client";
import type { AuthUser } from "../../api/types";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { AdminConfirm, AdminConfirmation, AdminDialog } from "./AdminDialog";

type Resource = {
  resource_id: string;
  kind: string;
  id?: string;
  job_id?: string;
  name?: string;
  label?: string;
  display_name?: string;
  status?: string;
  stage?: string;
  params?: Record<string, number>;
  auto_advance?: boolean;
  archived: boolean;
  control_kind?: string;
  control_id?: string;
  control_enabled?: boolean;
  control_reason?: string;
  params_locked?: boolean;
  control_available?: boolean;
  sample_count?: number;
  job_note?: string;
  pause_requested?: boolean;
};
type Photo = {
  task_id: string;
  enabled: boolean;
  available?: boolean;
  candidate_count: number;
  pause_reason?: string;
  datasets: { id: string; sample_count: number }[];
  candidate_models: { model_id: string; status: string }[];
};
type Audit = {
  created_at: number;
  actor_username: string;
  action: string;
  resource_id: string;
  reason: string;
  result: string;
  change?: Record<string, unknown>;
};
type LegacyPhoto = { task_id: string; enabled: boolean; sample_count: number };
export type UserSnapshot = {
  user: AuthUser;
  actor: AuthUser;
  tasks: Resource[];
  resources: Resource[];
  references: {
    resource_id: string;
    name: string;
    enabled: boolean;
    usage: string;
  }[];
  real_photo: Photo[];
  legacy_feedback?: LegacyPhoto[];
  audit: Audit[];
  business?: Record<string, Record<string, string | number | boolean>[]>;
  counts: Record<string, number>;
};
type Sample = {
  geometry?: { width: number; height: number };
  sample_id: string;
  current_status: string;
  source_group: string;
  usage_enabled: boolean;
  frozen: boolean;
  review?: { reason: string };
  annotation?: { objects?: { bbox: number[]; class_id: string }[] };
};
type SamplePage = {
  samples: Sample[];
  total: number;
  next_cursor: string | null;
};
const labels: Record<string, string> = {
  running: "运行中",
  queued: "排队中",
  completed: "已完成",
  failed: "失败",
  stopped: "已停止",
  paused: "已暂停",
  blocked: "阻塞",
  usage_disabled: "训练用途已停用",
  ready: "就绪",
  draft: "草稿",
  requested: "已记录请求",
  succeeded: "成功",
  uncertain: "待核查",
  accept_positive: "合格正样本",
  accept_negative: "合格负样本",
  exclude: "Agent 排除",
  pending_review: "等待 Agent 审核",
  annotation_failed: "标注失败",
  pending_annotation: "等待标注",
  unconfirmed_source: "来源待核实",
};
const autoEnabled = (t: Resource) => t.control_enabled ?? t.auto_advance;
const sampleStatusLabel = (v?: string) =>
  v === "uncertain" ? "Agent 不确定" : statusLabel(v);
export const statusLabel = (v?: string) => (v ? labels[v] || v : "—");
const enc = encodeURIComponent;
export function dataPath(owner: string) {
  return `/api/auth/users/${enc(owner)}/data`;
}
export function useUserSnapshot(owner: string) {
  return useQuery({
    queryKey: ["admin-user-data", owner],
    queryFn: () => apiClient.get<UserSnapshot>(dataPath(owner)),
    staleTime: 15_000,
  });
}

export function UserDataWorkbench({
  owner,
  tab,
}: {
  owner: string;
  tab: string;
}) {
  const q = useUserSnapshot(owner),
    qc = useQueryClient();
  const [confirmation, setConfirmation] = useState<AdminConfirmation | null>(
      null,
    ),
    [params, setParams] = useState<Resource | null>(null),
    [detail, setDetail] = useState<Resource | null>(null);
  const [search, setSearch] = useState(""),
    [filter, setFilter] = useState(""),
    [archived, setArchived] = useState(false),
    [photoId, setPhotoId] = useState("");
  async function refresh() {
    await qc.invalidateQueries({ queryKey: ["admin-user-data", owner] });
    await qc.invalidateQueries({ queryKey: ["admin-samples", owner] });
    await qc.invalidateQueries({ queryKey: ["admin-sample-versions", owner] });
    await qc.invalidateQueries({ queryKey: ["admin-user-counts"] });
  }
  function prepare(
    title: string,
    impact: string,
    request: Record<string, unknown>,
  ) {
    setConfirmation({
      title,
      impact,
      operation: async (reason) => {
        await apiClient.post(dataPath(owner) + "/operations", {
          ...request,
          reason,
        });
        await refresh();
      },
    });
  }
  if (q.isLoading) return <LoadingState label="正在读取用户数据" />;
  if (q.isError) return <ErrorState error={q.error} />;
  if (!q.data) return null;
  const data = q.data;
  const photos = data.real_photo;
  const legacy = data.legacy_feedback || [];
  const selectedPhoto = photos.find((p) => p.task_id === photoId) || photos[0];
  const tasks = data.tasks.filter(
    (t) =>
      (archived || !t.archived) &&
      (!filter || t.status === filter) &&
      `${t.name || t.label || ""}${t.resource_id}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const resources = data.resources.filter((t) => archived || !t.archived);
  function archive(r: Resource) {
    prepare(
      r.archived ? "恢复资源" : "归档资源",
      r.kind === "pipeline"
        ? "归档会暂停任务的新调度；恢复保留暂停状态。历史样本与训练证据不删除。"
        : "仅改变管理员列表的归档状态，原文件与历史引用保留。活动训练无法归档，模型不会自动上线。",
      {
        action: r.archived ? "restore" : "archive",
        kind: r.kind,
        resource_id: r.resource_id,
      },
    );
  }
  function paramSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!params) return;
    const fd = new FormData(e.currentTarget);
    const values = Object.fromEntries(
      (params.control_kind === "legacy"
        ? ["epochs", "image_size"]
        : ["epochs", "image_size", "sample_count"]
      ).map((k) => [k, Number(fd.get(k))]),
    );
    const changes = Object.entries(values)
      .map(([k, n]) => `${k}: ${params.params?.[k] ?? "默认"} → ${n}`)
      .join("；");
    prepare(
      "确认参数修改",
      `${changes}。只影响任务后续工作，已发出的训练和冻结快照不变。实拍训练仍使用固定配置。`,
      {
        action: "params",
        kind: params.control_kind || "pipeline",
        resource_id: params.control_id || params.resource_id,
        ...values,
      },
    );
    setParams(null);
  }
  return (
    <div className="admin-data">
      <div className="admin-data-toolbar">
        <span>
          数据归属：{data.user.username} · 操作人：{data.actor.username}
        </span>
        <button type="button" onClick={refresh} disabled={q.isFetching}>
          刷新数据
        </button>
      </div>
      {tab === "overview" && (
        <>
          <div className="admin-stats">
            {[
              ["任务", data.counts.tasks],
              ["训练记录", data.counts.training],
              ["图片资产（参考 / 实拍）", data.counts.images],
              ["数据集与模型", data.counts.resources],
            ].map(([name, n]) => (
              <div className="panel" key={name}>
                <span>{name}</span>
                <strong>{n}</strong>
              </div>
            ))}
          </div>
          <div className="admin-columns">
            <section className="panel page-panel">
              <h3>当前任务</h3>
              {data.tasks
                .filter((t) => !t.archived)
                .slice(0, 6)
                .map((t) => (
                  <div
                    className="admin-list-row"
                    key={`${t.kind}:${t.resource_id}`}
                  >
                    <div>
                      <strong>{t.name || t.label || t.resource_id}</strong>
                      <small>{t.stage || t.kind}</small>
                    </div>
                    <span className="pill neutral">
                      {statusLabel(t.status)}
                    </span>
                    <button onClick={() => setDetail(t)}>详情</button>
                  </div>
                ))}
              {!data.tasks.length && (
                <p className="hint-line">暂无任务与训练记录。</p>
              )}
            </section>
            <section className="panel page-panel">
              <h3>最近管理员操作</h3>
              {data.audit.slice(0, 5).map((a, i) => (
                <div className="admin-list-row" key={i}>
                  <div>
                    <strong>
                      {a.action} · {statusLabel(a.result)}
                    </strong>
                    <small>
                      {a.actor_username} · {a.reason}
                    </small>
                  </div>
                </div>
              ))}
              {!data.audit.length && (
                <p className="hint-line">新工作台启用后的操作会在这里记录。</p>
              )}
            </section>
          </div>
        </>
      )}
      {tab === "tasks" && (
        <>
          <section className="panel page-panel">
            <div className="admin-filters">
              <input
                aria-label="搜索任务"
                placeholder="搜索名称或任务 ID"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <select
                aria-label="任务状态"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              >
                <option value="">全部状态</option>
                {[
                  ...new Set(data.tasks.map((t) => t.status).filter(Boolean)),
                ].map((s) => (
                  <option key={s} value={s}>
                    {statusLabel(s)}
                  </option>
                ))}
              </select>
              <label>
                <input
                  type="checkbox"
                  checked={archived}
                  onChange={(e) => setArchived(e.target.checked)}
                />
                显示已归档
              </label>
            </div>
            <div className="admin-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>任务</th>
                    <th>类型</th>
                    <th>状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((t) => (
                    <tr key={`${t.kind}:${t.resource_id}`}>
                      <td>
                        <strong>{t.name || t.label || t.resource_id}</strong>
                        <small>
                          {t.resource_id} {t.archived ? "· 已归档" : ""}
                        </small>
                      </td>
                      <td>
                        {t.control_kind === "real_photo"
                          ? "实拍回流"
                          : t.control_kind === "legacy"
                            ? "旧回流训练"
                            : t.kind === "pipeline"
                              ? "流水线任务"
                              : "训练记录"}
                      </td>
                      <td>
                        {statusLabel(t.status)}
                        {t.control_reason && <small>{t.control_reason}</small>}
                        {t.pause_requested && <small>等待暂停检查点</small>}
                      </td>
                      <td>
                        <div className="admin-actions">
                          <button onClick={() => setDetail(t)}>详情</button>
                          {t.kind === "pipeline" && (
                            <>
                              <button
                                disabled={
                                  t.archived ||
                                  (autoEnabled(t) === false &&
                                    t.control_available === false) ||
                                  (autoEnabled(t) === false &&
                                    data.user.active === false)
                                }
                                onClick={() =>
                                  prepare(
                                    autoEnabled(t)
                                      ? "暂停自动调度"
                                      : "恢复自动调度",
                                    autoEnabled(t)
                                      ? "停止新增调度；当前不可中断步骤在检查点停止，不会重放付费调用。"
                                      : "允许后续自动推进，可能产生新的调用费用。恢复不会自动重试不确定或失败调用。",
                                    {
                                      action: autoEnabled(t)
                                        ? "pause"
                                        : "resume",
                                      kind: t.control_kind || "pipeline",
                                      resource_id:
                                        t.control_id || t.resource_id,
                                    },
                                  )
                                }
                              >
                                {(t.control_enabled ?? autoEnabled(t))
                                  ? "暂停调度"
                                  : "恢复调度"}
                              </button>
                              <button
                                disabled={t.params_locked || (t.control_kind === "legacy" && autoEnabled(t) === true)}
                                title={
                                  t.params_locked
                                    ? "实拍训练固定 80 轮 / 640 px"
                                    : undefined
                                }
                                onClick={() => setParams(t)}
                              >
                                修改参数
                              </button>
                            </>
                          )}
                          <button onClick={() => archive(t)}>
                            {t.archived ? "恢复" : "归档"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!tasks.length && (
              <p className="empty-panel">没有符合条件的任务。</p>
            )}
          </section>
          <PhotoControls
            photos={photos}
            inactive={data.user.active === false}
            prepare={prepare}
          />
          <LegacyControls
            legacy={legacy}
            inactive={data.user.active === false}
            prepare={prepare}
          />
        </>
      )}
      {tab === "images" && (
        <>
          <section className="panel page-panel">
            <h3>配件参考图 · 按参考用途启停</h3>
            <p className="hint-line">
              不删除原图，也不修改冻结版本。每类配件至少保留一张启用参考图。
            </p>
            <div className="admin-image-grid">
              {data.references.map((r) => (
                <article className="panel" key={r.resource_id}>
                  <img
                    className="admin-detail-image"
                    loading="lazy"
                    src={`${dataPath(owner)}/references/${enc(r.resource_id)}/image`}
                    alt={`${r.name}参考图`}
                  />
                  <div>
                    <strong>{r.name}</strong>
                    <label className="admin-usage">
                      <input
                        type="checkbox"
                        aria-label={`${r.name}参考用途`}
                        checked={r.enabled}
                        onChange={(e) =>
                          prepare(
                            e.target.checked ? "启用参考用途" : "停用参考用途",
                            "影响配件后续参考选择。原图和历史训练证据保留，已有审核需继续遵守版本有效性检查。",
                            {
                              action: "image_usage",
                              kind: "reference",
                              resource_id: r.resource_id,
                              enabled: e.target.checked,
                            },
                          )
                        }
                      />
                      作为参考使用
                    </label>
                  </div>
                </article>
              ))}
            </div>
            {!data.references.length && (
              <p className="hint-line">暂无配件参考图。</p>
            )}
          </section>
          <PhotoControls
            photos={photos}
            inactive={data.user.active === false}
            prepare={prepare}
          />
          <LegacyControls
            legacy={legacy}
            inactive={data.user.active === false}
            prepare={prepare}
          />
          {selectedPhoto ? (
            <>
              <label className="field">
                任务样本
                <select
                  aria-label="选择图片任务"
                  value={selectedPhoto.task_id}
                  onChange={(e) => setPhotoId(e.target.value)}
                >
                  {photos.map((p) => (
                    <option key={p.task_id} value={p.task_id}>
                      {p.task_id} · {p.candidate_count} 张
                    </option>
                  ))}
                </select>
              </label>
              <SampleGallery
                key={selectedPhoto.task_id}
                owner={owner}
                photo={selectedPhoto}
                prepare={prepare}
              />
            </>
          ) : (
            <section className="panel page-panel">
              <p>暂无实拍样本。</p>
            </section>
          )}
        </>
      )}
      {tab === "images" &&
        legacy.map((p) => (
          <LegacyGallery key={p.task_id} owner={owner} photo={p} />
        ))}
      {tab === "assets" && (
        <>
          <section className="panel page-panel">
            <div className="section-title">
              <h3>数据集与模型</h3>
              <label>
                <input
                  type="checkbox"
                  checked={archived}
                  onChange={(e) => setArchived(e.target.checked)}
                />
                显示已归档
              </label>
            </div>
            <div className="admin-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>资源</th>
                    <th>类型</th>
                    <th>样本数</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {resources.map((r) => (
                    <tr key={`${r.kind}:${r.resource_id}`}>
                      <td>
                        {r.display_name || r.resource_id}
                        <small>
                          {r.resource_id} {r.archived ? "· 已归档" : ""}
                        </small>
                      </td>
                      <td>{r.kind === "dataset" ? "数据集" : "模型"}</td>
                      <td>{r.sample_count ?? "—"}</td>
                      <td>
                        <div className="admin-actions">
                          <button onClick={() => setDetail(r)}>详情</button>
                          <button onClick={() => archive(r)}>
                            {r.archived ? "恢复" : "归档"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          {photos.map((p) => (
            <section className="panel page-panel" key={p.task_id}>
              <h3>实拍冻结版本 · {p.task_id}</h3>
              {p.datasets.map((d) => (
                <p key={d.id}>
                  {d.id} · {d.sample_count} 张 · 不可变训练集
                </p>
              ))}
              {p.candidate_models.map((m) => (
                <p key={m.model_id}>
                  {m.model_id} · {statusLabel(m.status)}
                </p>
              ))}
              {!p.datasets.length && (
                <p className="hint-line">尚未生成实拍训练集。</p>
              )}
            </section>
          ))}
          <p className="hint-line">
            候选模型仍通过检测工作台手动选择。历史版本不提供原地增删或永久清理。
          </p>
        </>
      )}
      {tab === "audit" && (
        <>
          <section className="panel page-panel">
            <h3>检测记录与业务证据</h3>
            <p className="hint-line">
              原始结果只读，纠错须追加复核证据。不会覆盖检测结果。
            </p>
            {Object.entries(data.business || {})
              .filter(([k]) => k !== "accessories")
              .map(([kind, records]) => (
                <details key={kind}>
                  <summary>
                    {{
                      text_inspection_standards: "文字标准 / 订单",
                      text_inspection_records: "文字检测记录",
                      incoming_text_inspections: "历史包材检测",
                      data_analysis_records: "检测分析记录",
                      label_inspection_objects: "标签检测与准备记录",
                      codex_comparison_tasks: "文字对比任务",
                    }[kind] || kind}{" "}
                    · {records.length} 条
                  </summary>
                  <div className="admin-table-wrap">
                    <table>
                      <tbody>
                        {records.map((r, i) => (
                          <tr key={i}>
                            <td>
                              {String(
                                r.name ||
                                  r.title ||
                                  r.display_name ||
                                  r.id ||
                                  r.record_id ||
                                  "历史记录",
                              )}
                            </td>
                            <td>
                              {statusLabel(
                                String(r.decision || r.status || ""),
                              )}
                            </td>
                            <td>
                              {r.created_at
                                ? new Date(
                                    Number(r.created_at) * 1000,
                                  ).toLocaleString()
                                : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              ))}
          </section>
          <section className="panel page-panel">
            <h3>管理员操作记录 · 最近 50 条</h3>
            <p className="hint-line">
              请求、结果分别记录；“待核查”需检查当前状态，不能自动重试。密码不会进入记录。
            </p>
            <div className="admin-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>时间 / 操作人</th>
                    <th>动作 / 资源</th>
                    <th>原因与变更</th>
                    <th>结果</th>
                  </tr>
                </thead>
                <tbody>
                  {data.audit.map((a, i) => (
                    <tr key={i}>
                      <td>
                        {new Date(a.created_at * 1000).toLocaleString()}
                        <small>{a.actor_username}</small>
                      </td>
                      <td>
                        {a.action}
                        <small>{a.resource_id}</small>
                      </td>
                      <td>
                        {a.reason}
                        {a.change && (
                          <details>
                            <summary>变更记录</summary>
                            <pre>{JSON.stringify(a.change, null, 2)}</pre>
                          </details>
                        )}
                      </td>
                      <td>{statusLabel(a.result)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
      {detail && (
        <AdminDialog title="资源详情" onClose={() => setDetail(null)}>
          <div className="admin-dialog-body">
            <h3>
              {detail.name ||
                detail.label ||
                detail.display_name ||
                detail.resource_id}
            </h3>
            <p>
              {detail.resource_id} · {statusLabel(detail.status)}
            </p>
            <p>{detail.job_note}</p>
            <pre>{JSON.stringify(detail.params || {}, null, 2)}</pre>
            <p className="hint-line">
              数据归属：{data.user.username}
              。历史训练记录不覆盖；停止新调度不等同于远程训练已取消。
            </p>
          </div>
        </AdminDialog>
      )}
      {params && (
        <AdminDialog title="修改后续训练参数" onClose={() => setParams(null)}>
          <form onSubmit={paramSubmit}>
            <div className="admin-dialog-body">
              <p>{params.name || params.resource_id}</p>
              {[
                ["epochs", "训练轮次", 1, 500, 80],
                ["image_size", "训练图像尺寸", 320, 1280, 640],
                ["sample_count", "合成样本数", 50, 20000, 500],
              ]
                .filter(
                  ([key]) =>
                    params.control_kind !== "legacy" || key !== "sample_count",
                )
                .map(([key, label, min, max, fallback]) => (
                  <label className="field" key={key}>
                    {label}
                    <input
                      name={String(key)}
                      type="number"
                      required
                      min={Number(min)}
                      max={Number(max)}
                      defaultValue={
                        params.params?.[String(key)] ?? Number(fallback)
                      }
                    />
                  </label>
                ))}
              <p className="hint-line">
                这些参数属于原训练流水线。实拍训练固定为 80 轮 / 640
                px，审核阈值不在此调整。
              </p>
            </div>
            <footer>
              <button type="submit" className="primary">
                预览修改
              </button>
            </footer>
          </form>
        </AdminDialog>
      )}
      {confirmation && (
        <AdminConfirm
          value={confirmation}
          onClose={() => setConfirmation(null)}
        />
      )}
    </div>
  );
}
type Prepare = (
  title: string,
  impact: string,
  request: Record<string, unknown>,
) => void;
function PhotoControls({
  photos,
  inactive,
  prepare,
}: {
  photos: Photo[];
  inactive: boolean;
  prepare: Prepare;
}) {
  return (
    <>
      {photos.map((p) => (
        <section className="panel page-panel admin-photo-row" key={p.task_id}>
          <div>
            <strong>实拍回流 · {p.task_id}</strong>
            <small>
              {p.candidate_count} 张 · {p.enabled ? "运行中" : "已暂停"}
            </small>
            {p.pause_reason && <p>{p.pause_reason}</p>}
          </div>
          <button
            disabled={!p.enabled && (inactive || p.available === false)}
            title={
              p.available === false
                ? "账户不在实拍回流允许名单中，只可查看历史数据"
                : undefined
            }
            onClick={() =>
              prepare(
                p.enabled ? "暂停实拍回流" : "恢复实拍回流",
                p.enabled
                  ? "停止新增审核与训练调度，保留样本、标注与历史证据。已发出调用允许结算。"
                  : "恢复自动采集、审核和后续训练，可能产生费用。失败或不确定尝试仍须显式恢复，不会自动重放。",
                {
                  action: p.enabled ? "pause" : "resume",
                  kind: "real_photo",
                  resource_id: p.task_id,
                },
              )
            }
          >
            {p.enabled ? "暂停回流" : "恢复回流"}
          </button>
        </section>
      ))}
    </>
  );
}
function SampleGallery({
  owner,
  photo,
  prepare,
}: {
  owner: string;
  photo: Photo;
  prepare: Prepare;
}) {
  const [detail, setDetail] = useState<Sample | null>(null);
  const base = `${dataPath(owner)}/tasks/${enc(photo.task_id)}/samples`;
  const q = useInfiniteQuery({
    queryKey: ["admin-samples", owner, photo.task_id],
    initialPageParam: "",
    queryFn: ({ pageParam }) =>
      apiClient.get<SamplePage>(
        base + (pageParam ? `?cursor=${enc(pageParam)}` : ""),
      ),
    getNextPageParam: (last) => last.next_cursor || undefined,
  });
  const history = useQuery({
    queryKey: [
      "admin-sample-versions",
      owner,
      photo.task_id,
      detail?.sample_id,
    ],
    enabled: !!detail,
    queryFn: () =>
      apiClient.get<Record<string, unknown>>(
        `${base}/${enc(detail!.sample_id)}/versions`,
      ),
  });
  if (q.isLoading) return <LoadingState label="正在读取样本" />;
  if (q.isError) return <ErrorState error={q.error} />;
  return (
    <>
      <p className="hint-line">
        全部 {q.data?.pages[0].total || 0} 张 · 每页 24
        张。训练用途开关保留原审核结论；先暂停回流后才可修改。
      </p>
      <div className="admin-image-grid">
        {q.data?.pages
          .flatMap((p) => p.samples)
          .map((s) => (
            <article className="panel" key={s.sample_id}>
              <button
                className="admin-image-preview"
                onClick={() => setDetail(s)}
                aria-label={`查看样本 ${s.sample_id}`}
              >
                <img
                  loading="lazy"
                  src={`${base}/${enc(s.sample_id)}/image`}
                  alt="实拍样本"
                />
              </button>
              <div>
                <strong>{s.sample_id}</strong>
                <small>
                  {sampleStatusLabel(s.current_status)} · {s.source_group}
                </small>
                <label className="admin-usage">
                  <input
                    type="checkbox"
                    aria-label={`${s.sample_id}训练用途`}
                    checked={s.usage_enabled !== false}
                    disabled={s.frozen || photo.enabled}
                    onChange={(e) =>
                      prepare(
                        e.target.checked
                          ? "启用图片训练用途"
                          : "停用图片训练用途",
                        "只影响此样本的后续训练使用，保留原图、标注与 Agent 判定。开启排除样本也不会获得训练准入。",
                        {
                          action: "image_usage",
                          kind: "sample",
                          resource_id: s.sample_id,
                          task_id: photo.task_id,
                          enabled: e.target.checked,
                        },
                      )
                    }
                  />
                  参与后续训练
                </label>
                <small>
                  {s.frozen
                    ? "冻结证据不可原地修改"
                    : photo.enabled
                      ? "先暂停回流后可调整用途"
                      : "历史证据保留"}
                </small>
              </div>
            </article>
          ))}
      </div>
      {q.hasNextPage && (
        <button
          onClick={() => q.fetchNextPage()}
          disabled={q.isFetchingNextPage}
        >
          {q.isFetchingNextPage ? "正在加载…" : "加载下一页"}
        </button>
      )}
      {detail && (
        <AdminDialog title="样本详情与历史" onClose={() => setDetail(null)}>
          <div className="admin-dialog-body">
            <svg
              className="admin-detail-image"
              role="img"
              aria-label="样本原图与 bbox"
              viewBox={`0 0 ${detail.geometry?.width || 1000} ${detail.geometry?.height || 1000}`}
            >
              <image
                href={`${base}/${enc(detail.sample_id)}/image`}
                width={detail.geometry?.width || 1000}
                height={detail.geometry?.height || 1000}
              />
              {detail.annotation?.objects?.map((o, i) => (
                <rect
                  key={i}
                  x={o.bbox[0]}
                  y={o.bbox[1]}
                  width={o.bbox[2] - o.bbox[0]}
                  height={o.bbox[3] - o.bbox[1]}
                  fill="none"
                  stroke="#22c55e"
                  strokeWidth={(detail.geometry?.width || 1000) / 250}
                />
              ))}
            </svg>
            <h3>{detail.sample_id}</h3>
            <p>
              {sampleStatusLabel(detail.current_status)} ·{" "}
              {detail.review?.reason}
            </p>
            <details open>
              <summary>当前 bbox 标注</summary>
              <pre>
                {JSON.stringify(detail.annotation?.objects || [], null, 2)}
              </pre>
            </details>
            <details>
              <summary>版本历史</summary>
              {history.isLoading ? (
                <p>正在读取历史…</p>
              ) : history.isError ? (
                <ErrorState error={history.error} />
              ) : (
                <pre>{JSON.stringify(history.data, null, 2)}</pre>
              )}
            </details>
          </div>
        </AdminDialog>
      )}
    </>
  );
}

function LegacyControls({
  legacy,
  inactive,
  prepare,
}: {
  legacy: LegacyPhoto[];
  inactive: boolean;
  prepare: Prepare;
}) {
  return (
    <>
      {legacy.map((p) => (
        <section className="panel page-panel admin-photo-row" key={p.task_id}>
          <div>
            <strong>旧回流训练 · {p.task_id}</strong>
            <small>
              {p.sample_count} 张历史样本 ·{" "}
              {p.enabled ? "自动流程已启用" : "自动流程已暂停"}
            </small>
          </div>
          <button
            disabled={!p.enabled && inactive}
            onClick={() =>
              prepare(
                p.enabled ? "暂停旧回流" : "恢复旧回流",
                "复用旧训练后端的启停规则；保留历史样本与模型，已发出工作允许结算。恢复可能产生后续费用，已选择实拍模式的任务不能退回旧流程。",
                {
                  action: p.enabled ? "pause" : "resume",
                  kind: "legacy",
                  resource_id: p.task_id,
                },
              )
            }
          >
            {p.enabled ? "暂停旧回流" : "恢复旧回流"}
          </button>
        </section>
      ))}
    </>
  );
}
function LegacyGallery({
  owner,
  photo,
}: {
  owner: string;
  photo: LegacyPhoto;
}) {
  const base = `${dataPath(owner)}/tasks/${enc(photo.task_id)}/legacy-samples`;
  const q = useInfiniteQuery({
    queryKey: ["admin-samples", owner, "legacy", photo.task_id],
    initialPageParam: "",
    queryFn: ({ pageParam }) =>
      apiClient.get<{
        samples: { sample_id: string; label_status?: string }[];
        total: number;
        next_cursor: string | null;
      }>(base + (pageParam ? `?cursor=${enc(pageParam)}` : "")),
    getNextPageParam: (p) => p.next_cursor || undefined,
  });
  if (q.isLoading) return <LoadingState label="正在读取旧回流样本" />;
  if (q.isError) return <ErrorState error={q.error} />;
  return (
    <section className="panel page-panel">
      <h3>旧回流样本 · {photo.task_id}</h3>
      <p className="hint-line">
        共 {q.data?.pages[0].total || 0}{" "}
        张历史图像。只读查看；旧标注不能未经坐标核实就加入当前实拍训练集。
      </p>
      <div className="admin-image-grid">
        {q.data?.pages
          .flatMap((p) => p.samples)
          .map((s) => (
            <article className="panel" key={s.sample_id}>
              <img
                className="admin-detail-image"
                loading="lazy"
                src={`${base}/${enc(s.sample_id)}/image`}
                alt="旧回流原图"
              />
              <div>
                <strong>{s.sample_id}</strong>
                <small>历史状态：{statusLabel(s.label_status)} · 只读</small>
              </div>
            </article>
          ))}
      </div>
      {q.hasNextPage && (
        <button
          onClick={() => q.fetchNextPage()}
          disabled={q.isFetchingNextPage}
        >
          加载更多旧样本
        </button>
      )}
    </section>
  );
}

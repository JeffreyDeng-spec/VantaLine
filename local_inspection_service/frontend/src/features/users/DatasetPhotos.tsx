import { useEffect, useRef, useState } from "react";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { apiClient } from "../../api/client";
import { AdminDialog } from "./AdminDialog";

const labels: Record<string, string> = {
  eligible: "当前合格",
  excluded: "已排除",
  uncertain: "不确定",
  processing: "处理中",
  annotation_failed: "标注失败",
  disabled: "已停用",
  not_collected: "未采集",
  unknown: "关联未知",
};
const splits: Record<string, string> = {
  train: "训练",
  val: "验证",
  test: "测试",
  unknown: "划分未知",
};
type Membership = {
  dataset_id: string;
  name: string;
  splits: string[];
  member_count: number;
};
type Sample = {
  sample_id: string;
  mode: string;
  status: string;
  sample_type?: string;
  reason: string;
  versions_url?: string;
  annotation?: unknown;
};
type Photo = {
  record_id: string;
  task_id: string;
  task_name: string;
  created_at: number;
  status: string;
  reason: string;
  image_url: string;
  image_type: string;
  memberships: Membership[];
  samples: Sample[];
};
type Page = {
  items: Photo[];
  total: number;
  record_total: number;
  counts: Record<string, number>;
  next_cursor: string | null;
  refresh_cursor: string | null;
  latest_record_id: string | null;
  revision: string;
  tasks: { id: string; name: string }[];
};
type Member = {
  id: string;
  sample_id: string;
  record_id: string;
  split: string;
  annotation_version?: number;
  label_count?: number;
  current_status: string;
  current_reason?: string;
  versions_url?: string;
  sample_type?: string;
  image_url: string;
};
type MemberPage = {
  dataset: {
    id: string;
    name: string;
    sample_count: number;
    members_available: boolean;
  };
  items: Member[];
  total: number;
  next_cursor: string | null;
  reason?: string;
};
const base = (owner: string) =>
  `/api/auth/users/${encodeURIComponent(owner)}/data`;
const time = (value: number) =>
  value ? new Date(value * 1000).toLocaleString() : "时间未知";
function Image({ url, alt }: { url: string; alt: string }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [url]);
  return failed ? (
    <div className="admin-photo-unavailable" role="status">
      图片不可用 · 记录已保留
    </div>
  ) : (
    <img src={url} alt={alt} loading="lazy" onError={() => setFailed(true)} />
  );
}
function State({ photo }: { photo: Photo }) {
  return (
    <span className={`admin-photo-status status-${photo.status}`}>
      {photo.status === "eligible" && photo.memberships.length
        ? "当前合格"
        : photo.status === "eligible"
          ? "合格待纳入"
          : labels[photo.status] || "关联未知"}
    </span>
  );
}
function Memberships({
  values,
  status,
  onOpen,
}: {
  values: Membership[];
  status: string;
  onOpen: (id: string) => void;
}) {
  return values.length ? (
    <div className="admin-photo-memberships">
      {values.map((m) => (
        <button key={m.dataset_id} onClick={() => onOpen(m.dataset_id)}>
          {status === "eligible" ? "已纳入" : "曾纳入"}：{m.name} ·{" "}
          {m.splits.map((s) => splits[s] || "划分未知").join("／")}
        </button>
      ))}
    </div>
  ) : (
    <small>尚无已冻结训练集归属证据</small>
  );
}
function Versions({ sample }: { sample: Sample }) {
  const [open, setOpen] = useState(false);
  const q = useQuery({
    queryKey: ["admin-photo-history", sample.versions_url],
    queryFn: () =>
      apiClient.get<{
        annotations?: { version: number; status: string }[];
        reviews?: { decision: string; reason: string }[];
      }>(sample.versions_url!),
    enabled: open && !!sample.versions_url,
  });
  return (
    <details onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>版本历史 · {sample.sample_id}</summary>
      {q.isLoading ? (
        <p>正在读取历史…</p>
      ) : q.error ? (
        <p role="alert">{q.error.message}</p>
      ) : sample.versions_url ? (
        <>
          <p className="hint-line">历史结论仅供追溯，不代表当前训练准入。</p>
          {q.data?.annotations?.map((a, i) => (
            <p key={`a${i}`}>
              标注版本 {a.version} · {a.status}
            </p>
          ))}
          {q.data?.reviews?.map((r, i) => (
            <p key={`r${i}`}>
              {(
                {
                  accept_positive: "合格正样本",
                  accept_negative: "合格负样本",
                  exclude: "排除",
                  uncertain: "不确定",
                } as Record<string, string>
              )[r.decision] || "历史审核"}{" "}
              · {r.reason}
            </p>
          ))}
        </>
      ) : (
        <p>旧模式没有实拍版本历史；保留其来源与冻结清单证据。</p>
      )}
    </details>
  );
}
function PhotoDetail({
  owner,
  id,
  close,
  onDataset,
}: {
  owner: string;
  id: string;
  close: () => void;
  onDataset: (id: string) => void;
}) {
  const q = useQuery({
    queryKey: ["admin-dataset-photos", owner, "detail", id],
    queryFn: () =>
      apiClient.get<Photo>(
        `${base(owner)}/detection-photos/${encodeURIComponent(id)}`,
      ),
  });
  return (
    <AdminDialog title="检测照片与数据集去向" onClose={close}>
      <div className="admin-dialog-body admin-photo-detail">
        {q.isLoading ? (
          <p>正在读取照片详情…</p>
        ) : q.error ? (
          <p role="alert">{q.error.message}</p>
        ) : (
          q.data && (
            <>
              <Image url={q.data.image_url} alt="检测照片" />
              <p>
                {q.data.image_type === "original"
                  ? "检测原图"
                  : q.data.image_type === "annotated"
                    ? "检测标注图"
                    : "图片文件不可用"}{" "}
                · {time(q.data.created_at)}
              </p>
              <p>
                {q.data.task_name} · {q.data.record_id}
              </p>
              <State photo={q.data} />
              <p>{q.data.reason}</p>
              <Memberships
                values={q.data.memberships}
                status={q.data.status}
                onOpen={onDataset}
              />
              {q.data.samples.map((s) => (
                <section key={`${s.mode}:${s.sample_id}`}>
                  <p>
                    {s.sample_type === "positive"
                      ? "合格正样本"
                      : s.sample_type === "negative"
                        ? "合格负样本"
                        : "来源样本"}{" "}
                    · {s.sample_id}
                  </p>
                  <details>
                    <summary>标注信息</summary>
                    <pre>{JSON.stringify(s.annotation || {}, null, 2)}</pre>
                  </details>
                  <Versions sample={s} />
                </section>
              ))}
              <p className="hint-line">
                当前筛选结论与历史训练集成员分别记录。这里的查看不会启动训练。
              </p>
            </>
          )
        )}
      </div>
    </AdminDialog>
  );
}
export function DatasetMembers({
  owner,
  id,
  onClose,
}: {
  owner: string;
  id: string;
  onClose: () => void;
}) {
  const [member, setMember] = useState<Member | null>(null);
  const q = useInfiniteQuery({
    queryKey: ["admin-dataset-members", owner, id],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      apiClient.get<MemberPage>(
        `${base(owner)}/datasets/${encodeURIComponent(id)}/members?limit=24${pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : ""}`,
      ),
    getNextPageParam: (p) => p.next_cursor,
  });
  const first = q.data?.pages[0];
  return (
    <AdminDialog title="冻结训练集图片" onClose={onClose}>
      <div className="admin-dialog-body">
        {q.isLoading ? (
          <p>正在读取训练集…</p>
        ) : q.error ? (
          <p role="alert">{q.error.message}</p>
        ) : (
          first && (
            <>
              <h4>{first.dataset.name}</h4>
              <p>
                冻结版本记录 {first.dataset.sample_count} 张 · 可读取成员{" "}
                {first.total} 张
              </p>
              <p className="hint-line">
                此处是该版本实际保存的训练图片，旧模式可能包含派生图片。当前停用或审核变化不会改写历史版本。
              </p>
              {first.reason && <p role="status">{first.reason}</p>}
              {member ? (
                <section className="admin-photo-detail">
                  <button onClick={() => setMember(null)}>返回成员列表</button>
                  <Image url={member.image_url} alt="冻结训练集成员" />
                  <p>
                    {member.sample_id || "来源样本未知"} ·{" "}
                    {splits[member.split] || "划分未知"} · 标注版本{" "}
                    {member.annotation_version ?? "未知"}
                  </p>
                  <p>
                    当前来源状态：{labels[member.current_status] || "关联未知"}
                  </p>
                  <p>{member.current_reason}</p>
                  <Versions
                    sample={{
                      sample_id: member.sample_id,
                      mode: "real_photo",
                      status: member.current_status,
                      reason: member.current_reason || "",
                      versions_url: member.versions_url,
                    }}
                  />
                </section>
              ) : (
                <div className="admin-dataset-photo-grid">
                  {q.data?.pages
                    .flatMap((p) => p.items)
                    .map((m) => (
                      <article key={m.id}>
                        <button
                          className="admin-photo-preview"
                          onClick={() => setMember(m)}
                          aria-label={`查看训练图片 ${m.id}`}
                        >
                          <Image url={m.image_url} alt={`训练集成员 ${m.id}`} />
                        </button>
                        <strong>{splits[m.split] || "划分未知"}</strong>
                        <small>{m.sample_id || "无来源样本 ID"}</small>
                        <small>
                          当前：{labels[m.current_status] || "关联未知"}
                        </small>
                      </article>
                    ))}
                </div>
              )}
              {q.hasNextPage && !member && (
                <button
                  disabled={q.isFetchingNextPage}
                  onClick={() => q.fetchNextPage()}
                >
                  加载更多训练图片
                </button>
              )}
            </>
          )
        )}
      </div>
    </AdminDialog>
  );
}
export function DatasetPhotos({ owner }: { owner: string }) {
  const [task, setTask] = useState("");
  const [status, setStatus] = useState("");
  const [detail, setDetail] = useState<string | null>(null);
  const [dataset, setDataset] = useState<string | null>(null);
  const [latest, setLatest] = useState<Page | null>(null);
  const [newPhotos, setNewPhotos] = useState(false);
  const [pollError, setPollError] = useState("");
  const anchors = useRef<Record<string, string | null>>({});
  const scope = JSON.stringify([owner, task, status]);
  const qc = useQueryClient();
  const key = ["admin-dataset-photos", owner, "list", task, status];
  const path = `${base(owner)}/detection-photos?limit=24${task ? `&task_id=${encodeURIComponent(task)}` : ""}${status ? `&status=${encodeURIComponent(status)}` : ""}`;
  const q = useInfiniteQuery({
    queryKey: key,
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      const cursor = pageParam || anchors.current[scope];
      const p = await apiClient.get<Page>(
        `${path}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
      );
      if (!pageParam) anchors.current[scope] = p.refresh_cursor;
      return p;
    },
    getNextPageParam: (p) => p.next_cursor,
  });
  const first = q.data?.pages[0];
  useEffect(() => {
    let stopped = false;
    const poll = async () => {
      if (document.hidden) return;
      try {
        const value = await apiClient.get<Page>(path);
        if (stopped) return;
        setLatest(value);
        setPollError("");
        setNewPhotos(value.latest_record_id !== first?.latest_record_id);
        if (first?.latest_record_id)
          await qc.invalidateQueries({ queryKey: key, exact: true });
      } catch (e) {
        if (!stopped)
          setPollError(e instanceof Error ? e.message : "自动刷新失败");
      }
    };
    const timer = setInterval(poll, 30000);
    document.addEventListener("visibilitychange", poll);
    return () => {
      stopped = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", poll);
    };
  }, [path, first?.latest_record_id]);
  function filters(nextTask: string, nextStatus: string) {
    setLatest(null);
    setNewPhotos(false);
    setTask(nextTask);
    setStatus(nextStatus);
  }
  async function refresh() {
    anchors.current[scope] = null;
    setLatest(null);
    setNewPhotos(false);
    setPollError("");
    await qc.resetQueries({ queryKey: key, exact: true });
  }
  const summary = latest || first;
  return (
    <section className="panel page-panel">
      <div className="section-title">
        <h3>检测照片与筛选状态</h3>
        <button onClick={refresh} disabled={q.isFetching}>
          刷新照片
        </button>
      </div>
      <p className="hint-line">
        按检测记录展示照片；训练集按冻结成员统计。合格待纳入与实际已纳入分别显示。页面可见时每
        30 秒更新。
      </p>
      <div className="admin-filters">
        <label>
          检测任务
          <select
            value={task}
            onChange={(e) => filters(e.target.value, status)}
          >
            <option value="">全部任务</option>
            {summary?.tasks.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          照片状态
          <select
            value={status}
            onChange={(e) => filters(task, e.target.value)}
          >
            <option value="">全部状态</option>
            <option value="included">已纳入过训练集</option>
            {Object.entries(labels).map(([s, l]) => (
              <option key={s} value={s}>
                {l}
              </option>
            ))}
          </select>
        </label>
      </div>
      {summary && (
        <div className="admin-photo-counts">
          <span>检测记录：{summary.record_total}</span>
          <span>匹配：{summary.total}</span>
          <span>有冻结归属：{summary.counts.included || 0}</span>
          {Object.entries(labels).map(([s, l]) => (
            <span key={s}>
              {l}：{summary.counts[s] || 0}
            </span>
          ))}
        </div>
      )}
      {newPhotos && (
        <p role="status">
          有新增照片，<button onClick={refresh}>刷新并查看新增照片</button>
          ；当前分页继续保留。
        </p>
      )}
      {pollError && (
        <p role="alert">自动更新失败：{pollError}；当前列表已保留。</p>
      )}
      {q.error && (
        <p role="alert">
          {q.error.message}{" "}
          <button onClick={() => q.refetch()}>重试读取照片</button>
        </p>
      )}
      {q.isLoading ? (
        <p>正在读取检测照片…</p>
      ) : q.data ? (
        <>
          <div className="admin-dataset-photo-grid">
            {q.data?.pages
              .flatMap((p) => p.items)
              .map((p) => (
                <article key={p.record_id}>
                  <button
                    className="admin-photo-preview"
                    onClick={() => setDetail(p.record_id)}
                    aria-label={`查看检测照片 ${p.record_id}`}
                  >
                    <Image url={p.image_url} alt={p.task_name} />
                  </button>
                  <strong>{p.task_name}</strong>
                  <small>
                    {time(p.created_at)} ·{" "}
                    {p.image_type === "original"
                      ? "检测原图"
                      : p.image_type === "annotated"
                        ? "检测标注图"
                        : "图片不可用"}
                  </small>
                  <State photo={p} />
                  <p>{p.reason}</p>
                  <Memberships
                    values={p.memberships}
                    status={p.status}
                    onOpen={setDataset}
                  />
                </article>
              ))}
          </div>
          {!first?.items.length && <p>该账号当前筛选下暂无检测照片记录。</p>}
          {q.hasNextPage && (
            <button
              disabled={q.isFetchingNextPage}
              onClick={() => q.fetchNextPage()}
            >
              加载更多检测照片
            </button>
          )}
        </>
      ) : null}
      {detail && !dataset && (
        <PhotoDetail
          owner={owner}
          id={detail}
          close={() => setDetail(null)}
          onDataset={setDataset}
        />
      )}
      {dataset && (
        <DatasetMembers
          owner={owner}
          id={dataset}
          onClose={() => setDataset(null)}
        />
      )}
    </section>
  );
}

import { FormEvent, useRef } from "react";
import { PlugZap } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getPlcWorkstation,
  listPlcWorkstations,
  pairPlcWorkstation,
  queryKeys,
  savePlcWorkstationConfig,
  verifyPlcWorkstationProfile,
  getApiCostLedger,
} from "../../api/queries";
import type {
  PlcWebSerialConfig,
  ApiCostDailyPoint,
  ApiCostLedgerResponse,
} from "../../api/types";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { MetricCard } from "../../components/MetricCard";
import { useToast } from "../../components/ToastProvider";
import { toneForStatus } from "../../utils/format";
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
  const maxCost = Math.max(
    ...points.map((point) => Number(point.total_cost_usd || 0)),
    0.000001,
  );
  const ticks = [1, 0.75, 0.5, 0.25, 0].map((ratio) => ({
    ratio,
    value: maxCost * ratio,
  }));
  if (!points.length) {
    return (
      <div className="cost-empty-state">还没有可计价的 API 调用记录。</div>
    );
  }
  return (
    <div
      className="cost-chart-frame"
      role="img"
      aria-label="每日 API 支出趋势，横轴为日期，纵轴为美元成本"
    >
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
            const height = Math.max(
              4,
              Math.round((Number(point.total_cost_usd || 0) / maxCost) * 100),
            );
            return (
              <div
                className="cost-trend-column"
                key={point.date}
                title={`${point.date} · ${formatUsd(point.total_cost_usd)} · ${point.call_count} 次`}
              >
                <div
                  className="cost-trend-bar"
                  style={{ height: `${height}%` }}
                />
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
        <MetricCard
          label="已计价总成本"
          value={formatUsd(summary.total_cost_usd)}
          detail={`已记录 ${summary.call_count} 次含 usage 的 API 调用`}
        />
        <MetricCard
          label="做一张图均价"
          value={formatUsd(summary.avg_image_generation_cost_usd)}
          detail="生图 / AI mask 平均"
        />
        <MetricCard
          label="单次调用均价"
          value={formatUsd(summary.avg_cost_per_call_usd)}
          detail="所有可计价调用平均"
        />
        <MetricCard
          label="训练样本摊薄"
          value={formatUsd(summary.avg_cost_per_training_sample_usd)}
          detail={`${summary.training_sample_count} 张可训练样本`}
        />
      </div>
      <div className="cost-ledger-note">
        <span>更新时间：{formatDateTime(ledger.updated_at)}</span>
        <span>
          实际 usage {formatUsd(summary.known_cost_usd)} · 未计价{" "}
          {summary.unpriced_call_count} 次 · 不做估算
        </span>
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
                {category.call_count} 次含 usage 调用 · 均价{" "}
                {formatUsd(category.avg_cost_usd)}
              </p>
              <div className="cost-subcategory-list">
                {(category.subcategories || []).slice(0, 4).map((item) => (
                  <span key={item.label}>
                    {item.label} · {item.call_count} ·{" "}
                    {formatUsd(item.cost_usd)}
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
              <strong>{call.priced ? formatUsd(call.cost_usd) : "未计价"}</strong>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function readPlcPayload(form: HTMLFormElement): PlcWebSerialConfig {
  const data = new FormData(form);
  return {
    schema_version: 5,
    transport_mode: "web_serial",
    profile_id: "mitsubishi_fx3ga_40mr",
    enabled: data.get("enabled") === "on",
    protocol: "fx_programming_port_ascii",
    checksum_mode: "include_etx",
    baudrate: 9600,
    parity: "E",
    data_bits: 7,
    stop_bits: 1,
    result_register: String(data.get("result_register") || "D206")
      .trim()
      .toUpperCase(),
    output_control_point: String(data.get("output_control_point") ?? "")
      .trim()
      .toUpperCase(),
    capture_trigger_enabled: data.get("capture_trigger_enabled") === "on",
    capture_input_register: String(data.get("capture_input_register") || "D205")
      .trim()
      .toUpperCase(),
    capture_trigger_value: Number(data.get("capture_trigger_value") ?? 1),
    capture_poll_interval_ms: 200,
    ack_timeout_ms: 500,
    retries: 0,
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

export function DeviceSettings() {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const plcFormRef = useRef<HTMLFormElement>(null);
  const plcQuery = useQuery({
    queryKey: queryKeys.plcWorkstation,
    queryFn: getPlcWorkstation,
  });
  const plcWorkstationsQuery = useQuery({
    queryKey: queryKeys.plcWorkstations,
    queryFn: listPlcWorkstations,
  });
  const plcResponse = plcQuery.data;
  const plc = plcResponse?.config;
  const latestPlcDispatch = plcResponse?.recent_dispatches?.[0];
  const plcMutation = useMutation({
    mutationFn: savePlcWorkstationConfig,
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.plcWorkstation,
      });
      await plcQuery.refetch();
      notify({
        title: "PLC 设置已保存",
        description: saved.config?.enabled
          ? "联动已允许；检测人员仍需在本机点击连接 PLC。"
          : "配置已保存，PLC 联动尚未启用。",
        tone: "success",
      });
    },
    onError: (error: Error) =>
      notify({
        title: "PLC 保存失败",
        description: error.message,
        tone: "error",
      }),
  });

  const plcPairMutation = useMutation({
    mutationFn: pairPlcWorkstation,
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.plcWorkstation,
      });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.plcWorkstations,
      });
      notify({
        title: "本机工作站已绑定",
        description: "退出账号不会删除此电脑的工作站绑定。",
        tone: "success",
      });
    },
    onError: (error: Error) =>
      notify({
        title: "工作站绑定失败",
        description: error.message,
        tone: "error",
      }),
  });

  const plcVerifyMutation = useMutation({
    mutationFn: verifyPlcWorkstationProfile,
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.plcWorkstation,
      });
      notify({ title: "PLC 验证状态已更新", tone: "success" });
    },
    onError: (error: Error) =>
      notify({
        title: "验证状态更新失败",
        description: error.message,
        tone: "error",
      }),
  });

  function handlePlcSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = readPlcPayload(event.currentTarget);
    if (payload.enabled) {
      const summary = [
        `检测结果将写入 ${payload.result_register}`,
        payload.output_control_point
          ? `将直接控制 ${payload.output_control_point}`
          : "不会直接控制流水线",
        payload.capture_trigger_enabled
          ? `从 ${payload.capture_input_register}=${payload.capture_trigger_value} 接收拍照信号`
          : "不会自动读取到位信号",
        "只有本机摄像头检测会生成指令",
      ].join("；");
      if (
        !window.confirm(
          `${summary}。请确认这些地址已经由 PLC 编程人员分配且未被占用。`,
        )
      )
        return;
    }
    plcMutation.mutate(payload);
  }

  return (
    <section className="panel page-panel">
      <div className="section-title">
        <h3>本机 PLC 结果同步</h3>
        <span
          className={`pill ${plcResponse?.effective_enabled ? toneForStatus(latestPlcDispatch?.status) : "neutral"}`}
        >
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
            if (name)
              plcPairMutation.mutate({
                name,
                station_id: stationId || undefined,
              });
          }}
        >
          <div className="settings-subhead">
            <div>
              <h4>首次绑定这台产线电脑</h4>
              <p>
                配置保存在工作站记录中，不跟登录账号走；退出并重新登录后仍会读取这台电脑的设置。
              </p>
            </div>
            <span className="pill neutral">未绑定</span>
          </div>
          <label className="field">
            本机工作站名称
            <input
              name="station_name"
              required
              minLength={1}
              maxLength={80}
              placeholder="例如：一号流水线电脑"
            />
          </label>
          {plcWorkstationsQuery.data?.items.length ? (
            <label className="field">
              更换浏览器时重新绑定已有工作站（可不选）
              <select name="station_id" defaultValue="">
                <option value="">创建新工作站</option>
                {plcWorkstationsQuery.data.items.map((item) => (
                  <option value={item.id} key={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
              <span className="field-hint">
                选择后会使旧 Edge / Chrome 的绑定和活动租约立即失效。
              </span>
            </label>
          ) : null}
          <div className="button-row">
            <button
              className="primary compact-action"
              type="submit"
              disabled={plcPairMutation.isPending}
            >
              绑定本机工作站
            </button>
          </div>
        </form>
      ) : plc ? (
        <>
          <div className="settings-subhead">
            <div>
              <h4>{plcResponse.station?.name}</h4>
              <p>
                Edge / Chrome 网页直接连接这台电脑上的
                PLC；服务器永远不会打开串口。
              </p>
            </div>
            <span
              className={`pill ${plcResponse.station?.profile_verified ? "ok" : "neutral"}`}
            >
              {plcResponse.station?.profile_verified
                ? "正式 PLC（已验证）"
                : "测试 PLC（未验证）"}
            </span>
          </div>
          <form
            className="settings-form"
            ref={plcFormRef}
            key={`${plcResponse.config_generation}-${plc.enabled}-${plc.result_register}-${plc.output_control_point}-${plc.capture_trigger_enabled}-${plc.capture_input_register}-${plc.capture_trigger_value}`}
            onSubmit={handlePlcSubmit}
          >
            <div className="form-grid settings-option-grid">
              <label className="toggle-row">
                <input
                  name="enabled"
                  type="checkbox"
                  defaultChecked={plc.enabled}
                />
                <span>允许这台工作站启用 PLC 联动</span>
              </label>
              <label className="toggle-row">
                <input
                  name="capture_trigger_enabled"
                  type="checkbox"
                  defaultChecked={plc.capture_trigger_enabled}
                />
                <span>启用 PLC 到位拍照</span>
              </label>
            </div>
            <div className="form-grid">
              <label className="field">
                输出寄存器
                <input
                  name="result_register"
                  pattern="D(?:0|[1-9][0-9]{0,2})"
                  defaultValue={plc.result_register}
                  placeholder="例如 D206"
                  required
                />
                <span className="field-hint">
                  测试范围 D0–D255；通过写 1，不通过写 0。
                </span>
              </label>
              <label className="field">
                输出控制点（可不填）
                <input
                  name="output_control_point"
                  pattern="Y(?:0[0-7]|1[0-7])"
                  defaultValue={plc.output_control_point}
                  placeholder="例如 Y04；留空则不控制"
                />
                <span className="field-hint">
                  测试范围 Y00–Y17（八进制）；留空时计划和串口都不会产生 Y
                  指令。
                </span>
              </label>
            </div>
            <div className="form-grid">
              <label className="field">
                输入寄存器
                <input
                  name="capture_input_register"
                  pattern="D(?:0|[1-9][0-9]{0,2})"
                  defaultValue={plc.capture_input_register}
                  placeholder="例如 D205"
                  required
                />
                <span className="field-hint">
                  FX3GA 测试范围 D0–D255；不得与输出寄存器相同。
                </span>
              </label>
              <label className="field">
                拍照触发值
                <input
                  name="capture_trigger_value"
                  type="number"
                  min={0}
                  max={65535}
                  step={1}
                  defaultValue={plc.capture_trigger_value}
                  required
                />
                <span className="field-hint">
                  默认 1；必须先读到其他值，再变为此值才触发一次。
                </span>
              </label>
            </div>
            <details className="settings-advanced">
              <summary>高级设置与诊断</summary>
              <p className="hint-line">
                预设 PLC：三菱 FX3GA-40MR；通信固定为 9600 / 偶校验 / 7 数据位 /
                1 停止位；校验和包含 ETX；超时 500ms；自动重试 0 次。
              </p>
              <p className="hint-line">
                协议地址（只读）：输入寄存器{" "}
                {plcResponse.resolved_addresses.capture_input_register || "—"}
                ；输出寄存器{" "}
                {plcResponse.resolved_addresses.result_register || "—"}
                ；输出控制点{" "}
                {plcResponse.resolved_addresses.output_control_point ||
                  "不控制"}
                。工人无需理解或填写这些数值。
              </p>
              <p className="hint-line">
                配置 generation：{plcResponse.config_generation}；协议版本：
                {plcResponse.protocol_version}。
              </p>
            </details>
            <p className="hint-line danger-text">
              未取得现场真实读帧、ACK 并确认安全地址前，请保持“测试 PLC”。
            </p>
            <p className="hint-line">
              {plc.capture_trigger_enabled
                ? `每 200ms 读取 ${plc.capture_input_register}；先读到非 ${plc.capture_trigger_value} 后，再变为 ${plc.capture_trigger_value} 时拍照一次。`
                : "PLC 到位自动拍照未启用。"}{" "}
              检测通过写 {plc.result_register}=1，检测不通过写{" "}
              {plc.result_register}=0；
              {plc.output_control_point
                ? `D 得到 ACK 后才控制 ${plc.output_control_point}`
                : "不直接控制流水线"}
              。
            </p>
            <div className="button-row">
              <button
                className="primary compact-action"
                type="submit"
                disabled={plcMutation.isPending}
              >
                <PlugZap size={16} aria-hidden="true" />
                保存 PLC 设置
              </button>
              <button
                className="secondary compact-action"
                type="button"
                disabled={plcVerifyMutation.isPending}
                onClick={() => {
                  const next = !plcResponse.station?.profile_verified;
                  if (
                    next &&
                    !window.confirm(
                      "只应在真实 PLC 已返回 ACK、地址已由 PLC 工程师确认后标记为正式。确认继续？",
                    )
                  )
                    return;
                  plcVerifyMutation.mutate(next);
                }}
              >
                {plcResponse.station?.profile_verified
                  ? "改回测试 PLC"
                  : "标记真实 ACK 已验证"}
              </button>
            </div>
          </form>

          <section className="cost-ledger-section">
            <div className="section-title compact">
              <h4>最近同步状态</h4>
              <span className="muted-text">
                当前显示最近 {plcResponse.recent_dispatches.length} 条
              </span>
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
                  <strong className={`pill ${toneForStatus(item.status)}`}>
                    {plcStatusLabel(item.status)}
                  </strong>
                </div>
              ))}
              {!plcResponse.recent_dispatches.length ? (
                <div className="cost-empty-state">
                  还没有本机摄像头同步记录。
                </div>
              ) : null}
            </div>
          </section>
        </>
      ) : (
        <div className="cost-empty-state">PLC 设置不可用。</div>
      )}
    </section>
  );
}
export function LegacyCostLedger() {
  const query = useQuery({
    queryKey: queryKeys.apiCostLedger,
    queryFn: getApiCostLedger,
  });
  return query.isLoading ? (
    <LoadingState label="正在加载历史成本" />
  ) : query.isError ? (
    <ErrorState error={query.error} />
  ) : query.data ? (
    <CostLedgerPanel ledger={query.data} />
  ) : null;
}

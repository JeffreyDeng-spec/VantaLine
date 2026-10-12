export type PlcConnectionDisplay = {
  state: "disconnected" | "connecting" | "connected" | "fault";
  detail: string;
  disconnectedAt: number | null;
};

type Props = PlcConnectionDisplay & {
  disabled: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
  onSettings?: () => void;
};

export function PlcConnectionStatusBar(props: Props) {
  const connected = props.state === "connected";
  const labels = { disconnected: "PLC 未连接", connecting: "PLC 连接中", connected: "PLC 已连接", fault: "PLC 已断开" };
  return <section className={`plc-connection-bar plc-connection-bar--${props.state}`} aria-label="PLC 连接状态">
    <div className="plc-connection-bar-copy" role="status" aria-live="polite" aria-atomic="true">
      <strong><i aria-hidden="true" />{labels[props.state]}</strong>
      <span title={props.detail}>{props.detail}</span>
      {props.disconnectedAt && <time dateTime={new Date(props.disconnectedAt).toISOString()}>
        断开时间：{new Date(props.disconnectedAt).toLocaleTimeString("zh-CN", { hour12: false })}
      </time>}
    </div>
    <div className="plc-connection-bar-actions">
      <button type="button" className={connected ? "secondary compact-action" : "primary compact-action"} disabled={props.disabled} onClick={connected ? props.onDisconnect : props.onConnect}>
        {connected ? "断开 PLC" : props.state === "connecting" ? "连接中…" : props.state === "fault" ? "重新连接 PLC" : "连接 PLC"}
      </button>
      {props.onSettings && <button type="button" className="secondary compact-action" disabled={props.disabled} onClick={props.onSettings}>本机 PLC 设置</button>}
    </div>
  </section>;
}

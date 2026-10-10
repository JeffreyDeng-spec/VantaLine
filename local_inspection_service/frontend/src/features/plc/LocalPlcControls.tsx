import { FormEvent, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getPlcWorkstation, queryKeys, selfPairPlcWorkstation, selfSavePlcWorkstationConfig } from "../../api/queries";
import type { PlcWebSerialConfig } from "../../api/types";
import { PlcWebSerialClient } from "./webSerialClient";
import "./localPlcControls.css";

const DEFAULTS: PlcWebSerialConfig = {
  schema_version: 5, transport_mode: "web_serial", profile_id: "mitsubishi_fx3ga_40mr",
  enabled: true, protocol: "fx_programming_port_ascii", checksum_mode: "include_etx",
  baudrate: 9600, parity: "E", data_bits: 7, stop_bits: 1, result_register: "D206",
  output_control_point: "", capture_trigger_enabled: true, capture_input_register: "D205",
  capture_trigger_value: 1, capture_poll_interval_ms: 200, ack_timeout_ms: 500, retries: 0
};

type Props = {
  client?: PlcWebSerialClient; modelId?: string; connected?: boolean; externalStatus?: string;
  productionReady?: boolean; disabled?: boolean; onConnectionChange?: (connected: boolean) => void;
};

export function LocalPlcControls(props: Props) {
  const ownClient = useRef(new PlcWebSerialClient());
  const mounted = useRef(true);
  const dialogRef = useRef<HTMLElement>(null);
  const client = props.client || ownClient.current;
  const cache = useQueryClient();
  const workstation = useQuery({ queryKey: queryKeys.plcWorkstation, queryFn: getPlcWorkstation, refetchOnWindowFocus: false });
  const [localConnected, setLocalConnected] = useState(false);
  const connected = props.connected ?? localConnected;
  const [phase, setPhase] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const pendingRef = useRef(false);
  const [editing, setEditing] = useState(false);
  const [connectAfterSave, setConnectAfterSave] = useState(false);
  const data = workstation.data;
  const config = data?.config || DEFAULTS;
  const blocked = pending || Boolean(props.disabled);

  function report(value: boolean) {
    setLocalConnected(value);
    props.onConnectionChange?.(value);
  }

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (!props.client) void ownClient.current.disconnect(true);
    };
  }, [props.client]);

  useEffect(() => {
    if (!editing) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    dialog?.querySelector<HTMLInputElement>("input")?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !pendingRef.current) {
        event.preventDefault();
        setEditing(false);
      }
      if (event.key !== "Tab" || !dialog) return;
      const controls = Array.from(dialog.querySelectorAll<HTMLElement>("input, button, summary"))
        .filter((node) => !node.hasAttribute("disabled") && node.getClientRects().length > 0);
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", handleKey);
    return () => { document.removeEventListener("keydown", handleKey); previous?.focus(); };
  }, [editing]);

  async function refresh() {
    await cache.invalidateQueries({ queryKey: queryKeys.plcWorkstation });
  }

  async function perform(connect: boolean, payload?: { name: string; config: PlcWebSerialConfig }) {
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPending(true);
    setError("");
    let port: SerialPort | undefined;
    try {
      // Must happen before ANY network await to preserve the browser click grant.
      if (connect) {
        setPhase("请选择本机 PLC 串口");
        if (!PlcWebSerialClient.supported() || !navigator.serial) throw new Error("请通过 HTTPS 使用桌面 Edge 或 Chrome 连接 PLC。");
        port = await navigator.serial.requestPort();
      }
      if (!mounted.current) return;
      if (payload) {
        await client.disconnect(true);
        report(false);
        await selfPairPlcWorkstation({ name: payload.name });
        if (!mounted.current) return;
        await selfSavePlcWorkstationConfig(payload.config);
        setEditing(false);
      }
      if (connect) {
        setPhase("正在打开本机串口…");
        const station = await selfPairPlcWorkstation();
        if (!station.station || !station.config?.enabled) throw new Error("请先确认本机 PLC 配置并启用联动。");
        if (!mounted.current) return;
        await client.connect(station.station.id, props.modelId || "", (message) => {
          report(false);
          setError(message);
          setPhase("");
          void refresh();
        }, port, setPhase);
        report(true);
        setPhase("PLC 通信正常");
      } else {
        setPhase("本机配置已保存，当前 PLC 未连接");
      }
      await refresh();
    } catch (e) {
      // Cancellation can leave an existing production connection untouched.
      if (!(e instanceof DOMException && e.name === "NotFoundError" && client.state())) {
        await client.disconnect(true);
        report(false);
      }
      setError(e instanceof DOMException && e.name === "NotFoundError" ? "未选择串口，请连接 PLC 后重试。" : e instanceof Error ? e.message : String(e));
      setPhase("");
    } finally {
      pendingRef.current = false;
      setPending(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const payload = {
      name: String(values.get("name") || "产线电脑").trim(),
      config: { ...config, enabled: true,
        capture_input_register: String(values.get("input") || "").trim().toUpperCase(),
        result_register: String(values.get("result") || "").trim().toUpperCase(),
        capture_trigger_value: Number(values.get("trigger")),
        output_control_point: String(values.get("output") || "").trim().toUpperCase(),
        capture_trigger_enabled: values.get("auto") === "on" }
    };
    void perform(connectAfterSave, payload);
  }

  function requestConnection() {
    if (!data?.paired || !data.config?.enabled) {
      setConnectAfterSave(true);
      setEditing(true);
    } else {
      void perform(true);
    }
  }

  const readiness = props.productionReady ? "相机与模型就绪，等待 PLC 复位后到位信号" : "等待相机／模型就绪后生产";
  return <section className="local-plc-controls" aria-label="本机 PLC">
    <div className="button-row">
      {connected ? <button type="button" className="secondary compact-action" disabled={blocked} onClick={() => {
        void client.disconnect(true).then(() => { report(false); setPhase(""); void refresh(); });
      }}>断开 PLC</button> : <button type="button" className="primary compact-action" disabled={blocked || workstation.isLoading || workstation.isError || !PlcWebSerialClient.supported()} onClick={requestConnection}>
        {pending ? "连接中…" : "连接 PLC"}
      </button>}
      <button type="button" className="secondary compact-action" disabled={blocked || workstation.isLoading || workstation.isError} onClick={() => { setConnectAfterSave(false); setEditing(true); }}>本机 PLC 设置</button>
      {workstation.isError && <button type="button" onClick={() => void workstation.refetch()}>重新加载</button>}
    </div>
    <p role="status" aria-live="polite" className={`hint-line ${error ? "danger-text" : connected ? "success-text" : ""}`}>
      {pending ? phase : connected ? `PLC 通信正常；${config.capture_trigger_enabled ? readiness : "已关闭到位自动拍照，可手动检测"}。` : `当前 PLC 未连接，PLC 联动未生效。${error || props.externalStatus || phase}`}
    </p>
    {!PlcWebSerialClient.supported() && <p className="hint-line">连接需要桌面 Edge / Chrome，并通过 HTTPS 打开网站。</p>}
    {workstation.isError && <p role="alert">本机 PLC 配置加载失败：{String(workstation.error)}</p>}
    {editing && <div className="modal-backdrop" role="presentation">
      <section ref={dialogRef} className="modal-panel local-plc-dialog" role="dialog" aria-modal="true" aria-label="本机 PLC 配置">
        <h3>本机 PLC 配置</h3>
        <p>三菱 FX3GA-40MR · 9600 / 7E1。请确认地址与本条产线的 PLC 程序一致；自动校验只检查通信。</p>
        <form onSubmit={submit} key={`${data?.config_generation}-${editing}`}>
          <div className="form-grid">
            <label className="field">到位输入寄存器<input autoFocus name="input" required pattern="[Dd](?:0|[1-9][0-9]{0,2})" defaultValue={config.capture_input_register} /></label>
            <label className="field">到位触发值<input name="trigger" type="number" required min={0} max={65535} step={1} defaultValue={config.capture_trigger_value} /></label>
            <label className="field">检测结果寄存器<input name="result" required pattern="[Dd](?:0|[1-9][0-9]{0,2})" defaultValue={config.result_register} /></label>
          </div>
          <label className="toggle-row"><input name="auto" type="checkbox" defaultChecked={config.capture_trigger_enabled} />启用到位自动拍照</label>
          <details><summary>名称与输出控制</summary>
            <label className="field">本机名称<input name="name" required maxLength={80} defaultValue={data?.station?.name || "产线电脑"} /></label>
            <label className="field">可选 Y 控制点<input name="output" pattern="[Yy](?:0[0-7]|1[0-7])" defaultValue={config.output_control_point} placeholder="留空不控制 Y" /></label>
          </details>
          <p className="hint-line">修改设置会先断开本机连接；保存后需重新连接校验。</p>
          {error && <p role="alert" className="danger-text">{error}</p>}
          <div className="button-row">
            <button className="primary" type="submit" disabled={blocked}>{connectAfterSave ? "确认并连接" : "确认并保存"}</button>
            <button className="secondary" type="button" disabled={pending} onClick={() => setEditing(false)}>取消</button>
          </div>
        </form>
      </section>
    </div>}
  </section>;
}

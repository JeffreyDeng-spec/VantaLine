import { guardPlcConnectionGesture } from "../version/runtime";
import { useVersionParticipant } from "../version/hooks";
import { createPortal } from "react-dom";
import { PlcConnectionStatusBar } from "./PlcConnectionStatusBar";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getPlcWorkstation, queryKeys, selfPairPlcWorkstation, selfSavePlcWorkstationConfig } from "../../api/queries";
import type { PlcWebSerialConfig } from "../../api/types";
import { PlcWebSerialClient } from "./webSerialClient";
import { diagnosticErrorDetail, diagnosticMessages, diagnosticTransport } from "./diagnosticLog";
import { PlcDiagnosticPanel } from "./PlcDiagnosticPanel";
import "./localPlcControls.css";

const DEFAULTS: PlcWebSerialConfig = {
  schema_version: 5, transport_mode: "web_serial", profile_id: "mitsubishi_fx3ga_40mr",
  enabled: true, protocol: "fx_programming_port_ascii", checksum_mode: "include_etx",
  baudrate: 9600, parity: "E", data_bits: 7, stop_bits: 1, result_register: "D206",
  result_pass_value: 1, result_fail_value: 0,
  output_control_point: "", capture_trigger_enabled: true, capture_input_register: "D205",
  capture_trigger_value: 1, capture_poll_interval_ms: 200, ack_timeout_ms: 500, retries: 0
};

type Props = {
  client?: PlcWebSerialClient; modelId?: string; connected?: boolean; externalStatus?: string;
  statusTarget?: HTMLElement | null; fullscreenStatusTarget?: HTMLElement | null; captureStatus?: string;
  productionReady?: boolean; disabled?: boolean; onConnectionChange?: (connected: boolean) => void;
};

export function LocalPlcControls(props: Props) {
  const ownClient = useRef(new PlcWebSerialClient());
  const mounted = useRef(true);
  const dialogRef = useRef<HTMLElement>(null);
  const grantedPorts = useRef<SerialPort[]>([]);
  useEffect(() => {
    if (!navigator.serial?.getPorts) return;
    let active = true;
    const refreshPorts = () => { void navigator.serial!.getPorts().then(ports => {
      if (active) grantedPorts.current = ports;
    }).catch(() => { if (active) grantedPorts.current = []; }); };
    refreshPorts();
    navigator.serial.addEventListener("connect", refreshPorts);
    navigator.serial.addEventListener("disconnect", refreshPorts);
    return () => {
      active = false;
      navigator.serial?.removeEventListener("connect", refreshPorts);
      navigator.serial?.removeEventListener("disconnect", refreshPorts);
    };
  }, []);
  const client = props.client || ownClient.current;
  const cache = useQueryClient();
  const workstation = useQuery({ queryKey: queryKeys.plcWorkstation, queryFn: getPlcWorkstation, refetchOnWindowFocus: false });
  const [localConnected, setLocalConnected] = useState(false);
  const connected = props.connected ?? localConnected;
  const [phase, setPhase] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [, refreshDiagnosticStatus] = useState(0);
  useEffect(() => diagnosticTransport.subscribe(() => refreshDiagnosticStatus(value => value+1)), []);
  const pendingRef = useRef(false);
  const [editing, setEditing] = useState(false);
  const [connectAfterSave, setConnectAfterSave] = useState(false);
  const data = workstation.data;
  const config = data?.config || DEFAULTS;
  const blocked = pending || Boolean(props.disabled);
  const lastConnected = useRef(connected);
  const [fault, setFault] = useState<{message: string; at: number} | null>(null);
  useEffect(() => {
    if (connected) setFault(null);
    else if (error || lastConnected.current) {
      setFault(previous => previous || { message: error || props.externalStatus || "PLC 连接已中断，请重新连接", at: Date.now() });
    }
    lastConnected.current = connected;
  }, [connected, error, props.externalStatus]);


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

  useVersionParticipant({ busy: () => pendingRef.current, cleanup: () => client.drainForReload() });
  async function perform(connect: boolean, payload?: { name: string; config: PlcWebSerialConfig }) {
    if (connect && !guardPlcConnectionGesture()) return;
    if (pendingRef.current) return;
    pendingRef.current = true;
    setPending(true);
    setError("");
    let port: SerialPort | undefined;
    let diagnosticStep: "selection"|"workstation" = "selection";
    if(connect) client.diagnostics.begin();
    try {
      // Must happen before ANY network await to preserve the browser click grant.
      if (connect) {
        setPhase("请选择本机 PLC 串口");
        if (!PlcWebSerialClient.supported() || !navigator.serial) throw new Error("请通过 HTTPS 使用桌面 Edge 或 Chrome 连接 PLC。");
        // Reuse a sole already-authorized port. Multiple ports still require
        // explicit selection; USB adapter IDs cannot identify the PLC model.
        port = grantedPorts.current.length === 1 ? grantedPorts.current[0] : await navigator.serial.requestPort();
        client.diagnostics.record("selection","ok");
      }
      if (!mounted.current) return;
      if (payload) {
        await client.disconnect(true);
        lastConnected.current = false;
        setFault(null);
        report(false);
        await selfPairPlcWorkstation({ name: payload.name });
        if (!mounted.current) return;
        await selfSavePlcWorkstationConfig(payload.config);
        setEditing(false);
      }
      if (connect) {
        setPhase("正在打开本机串口…");
        diagnosticStep="workstation";
        client.diagnostics.record("workstation","started");
        const beforePair = await getPlcWorkstation();
        let station = await selfPairPlcWorkstation();
        if (!beforePair.paired && station.config_generation === 0 && !station.config?.enabled) {
          station = await selfSavePlcWorkstationConfig({...DEFAULTS,capture_trigger_enabled:false});
        }
        if (!station.station || !station.config?.enabled) throw new Error("请先确认本机 PLC 配置并启用联动。");
        if (!mounted.current) return;
        client.diagnostics.bind(station.station.id,station.config_generation);
        client.diagnostics.record("workstation","ok",{config:{baudrate:station.config.baudrate,data_bits:station.config.data_bits,parity:"E",stop_bits:1,input_register:station.config.capture_input_register,result_register:station.config.result_register,output_control_point:station.config.output_control_point,timeout_ms:500,capture_enabled:station.config.capture_trigger_enabled,trigger_value:station.config.capture_trigger_value}});
        await client.connect(station.station.id, props.modelId || "", (message) => {
          report(false);
          setError(`${message}。诊断编号：${client.diagnostics.attemptId}`);
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
      if(connect && !client.diagnostics.lastFailure) client.diagnostics.failure(diagnosticStep,e);
      // Cancellation can leave an existing production connection untouched.
      if (!(e instanceof DOMException && e.name === "NotFoundError" && client.state())) {
        await client.disconnect(true);
        report(false);
      }
      const detail={target:"",...diagnosticErrorDetail(e),...client.diagnostics.lastFailure};
      const code=detail.code || "serial_error";
      setError(connect ? `${code === "serial_error" && e instanceof Error ? e.message : diagnosticMessages[code]}${detail.target ? `（${detail.target}，收到 ${detail.actual_bytes || 0}/${detail.expected_bytes || 8} 字节）` : ""}。诊断编号：${client.diagnostics.attemptId}` : e instanceof Error ? e.message : String(e));
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
        result_pass_value: Number(values.get("result_pass_value")),
        result_fail_value: Number(values.get("result_fail_value")),
        output_control_point: String(values.get("output") || "").trim().toUpperCase(),
        capture_trigger_enabled: values.get("auto") === "on" }
    };
    void perform(connectAfterSave, payload);
  }

  function requestConnection() {
    if (data?.paired && !data.config?.enabled) {
      setConnectAfterSave(true);
      setEditing(true);
    } else {
      void perform(true);
    }
  }

  const readiness = props.productionReady ? "相机与模型就绪" : "等待相机／模型就绪";
  const status = {
    state: pending ? "connecting" as const : connected ? "connected" as const : fault || error ? "fault" as const : "disconnected" as const,
    detail: pending ? phase || "正在校验连接" : connected
      ? `${readiness}；${config.capture_trigger_enabled ? props.captureStatus || "自动拍照已启用，等待复位后触发" : "自动拍照未启用，可手动检测"}`
      : fault?.message || error || props.externalStatus || "PLC 联动未生效",
    disconnectedAt: !connected && !pending ? fault?.at || null : null
  };
  function disconnectManually() {
    void client.disconnect(true).then(() => {
      lastConnected.current = false;
      setFault(null);
      setError("");
      report(false);
      setPhase("");
      void refresh();
    });
  }
  const connectionDisabled = blocked || workstation.isLoading || workstation.isError || !PlcWebSerialClient.supported();
  const bar = (fullscreen = false) => <PlcConnectionStatusBar {...status} disabled={connectionDisabled}
    onConnect={requestConnection} onDisconnect={disconnectManually}
    onSettings={!fullscreen ? () => { setConnectAfterSave(false); setEditing(true); } : undefined} />;
  return <section className="local-plc-controls" aria-label="本机 PLC">
    {props.statusTarget ? createPortal(bar(), props.statusTarget) : bar()}
    {props.fullscreenStatusTarget && createPortal(bar(true), props.fullscreenStatusTarget)}
    {workstation.isError && <button type="button" onClick={() => void workstation.refetch()}>重新加载</button>}
    {client.diagnostics.attemptId && diagnosticTransport.pending(client.diagnostics.attemptId) && <p className="hint-line">诊断记录尚未上传；关页可能丢失。</p>}
    <PlcDiagnosticPanel />
    {!PlcWebSerialClient.supported() && <p className="hint-line">连接需要桌面 Edge / Chrome，并通过 HTTPS 打开网站。</p>}
    {workstation.isError && <p role="alert">本机 PLC 配置加载失败：{String(workstation.error)}</p>}
    {editing && <div className="modal-backdrop" role="presentation">
      <section ref={dialogRef} className="modal-panel local-plc-dialog" role="dialog" aria-modal="true" aria-label="本机 PLC 配置">
        <h3>本机 PLC 配置</h3>
        <form onSubmit={submit} key={`${data?.config_generation}-${editing}`}>
          <div className="form-grid">
            <label className="field">到位输入寄存器<input autoFocus name="input" required pattern="[Dd](?:0|[1-9][0-9]{0,2})" defaultValue={config.capture_input_register} /></label>
            <label className="field">到位触发值<input name="trigger" type="number" required min={0} max={65535} step={1} defaultValue={config.capture_trigger_value} /></label>
            <label className="field">检测结果寄存器<input name="result" required pattern="[Dd](?:0|[1-9][0-9]{0,2})" defaultValue={config.result_register} /></label>
          </div>
          <div className="form-grid">
            <label className="field">通过输出值<input name="result_pass_value" type="number" required min={0} max={65535} step={1} defaultValue={config.result_pass_value ?? 1} /></label>
            <label className="field">不通过输出值<input name="result_fail_value" type="number" required min={0} max={65535} step={1} defaultValue={config.result_fail_value ?? 0} /></label>
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

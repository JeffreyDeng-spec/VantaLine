import {
  activatePlcWorkstationConnection,
  claimPlcWorkstationConnection,
  declarePlcWebSerialAttempt,
  disconnectPlcWorkstationConnection,
  heartbeatPlcWorkstationConnection,
  sendPlcWebSerialReceipt
} from "../../api/queries";
import type {
  PlcSyncStatus,
  PlcWebSerialFrame,
  PlcWebSerialOperation,
  PlcWorkstationLease
} from "../../api/types";

export const PLC_WEB_SERIAL_VERSION = "plc-web-serial-v4";

function bytesFromHex(value: string) {
  if (!/^(?:[0-9A-F]{2})+$/i.test(value)) throw new Error("PLC 指令格式无效");
  const bytes = new Uint8Array(value.length / 2);
  for (let index = 0; index < bytes.length; index += 1) bytes[index] = Number.parseInt(value.slice(index * 2, index * 2 + 2), 16);
  return bytes;
}

function hexFromBytes(value: Uint8Array) {
  return Array.from(value, (item) => item.toString(16).padStart(2, "0")).join("").toUpperCase();
}

function clientInstanceId() {
  const key = "vantaline.plc.web_serial.client_instance";
  const existing = sessionStorage.getItem(key);
  if (existing) return existing;
  const created = `tab_${crypto.randomUUID()}`;
  sessionStorage.setItem(key, created);
  return created;
}

async function acquireStationLock(stationId: string) {
  if (!navigator.locks) throw new Error("当前浏览器不支持网页锁，无法安全连接 PLC");
  let release!: () => void;
  const held = new Promise<void>((resolve) => { release = resolve; });
  let decide!: (value: boolean) => void;
  const acquired = new Promise<boolean>((resolve) => { decide = resolve; });
  void navigator.locks.request(`vantaline-plc-${stationId}`, { ifAvailable: true }, async (lock) => {
    decide(Boolean(lock));
    if (lock) await held;
  }).catch(() => decide(false));
  if (!(await acquired)) throw new Error("此电脑已有另一个标签页连接 PLC");
  return release;
}

export interface PlcBrowserConnectionState {
  connected: boolean;
  sessionId: string;
  leaseEpoch: number;
  configGeneration: number;
  serialInfo: SerialPortInfo;
}

export class PlcWebSerialClient {
  private port: SerialPort | null = null;
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  private writer: WritableStreamDefaultWriter<Uint8Array> | null = null;
  private lease: PlcWorkstationLease | null = null;
  private heartbeatTimer: number | null = null;
  private releaseLock: (() => void) | null = null;
  private queue: Promise<unknown> = Promise.resolve();
  private stopped = true;
  private disconnectListener: ((event: Event) => void) | null = null;
  private pendingRead: Promise<ReadableStreamReadResult<Uint8Array>> | null = null;
  private pendingReadResolved = false;

  static supported() {
    return typeof navigator !== "undefined" && Boolean(navigator.serial) && Boolean(navigator.locks) && window.isSecureContext;
  }

  state(): PlcBrowserConnectionState | null {
    if (!this.port || !this.lease || this.stopped) return null;
    return {
      connected: true,
      sessionId: this.lease.session_id,
      leaseEpoch: this.lease.lease_epoch,
      configGeneration: this.lease.config_generation,
      serialInfo: this.port.getInfo()
    };
  }

  async connect(stationId: string, modelId: string, onFatal: (message: string) => void) {
    if (!PlcWebSerialClient.supported() || !navigator.serial) throw new Error("请使用最新版桌面 Edge 或 Chrome，并通过 HTTPS 打开网站");
    if (this.state()) return this.state();
    try {
      // Keep requestPort at the front of the explicit click handler so Chromium
      // does not lose transient user activation during a network round trip.
      this.port = await navigator.serial.requestPort();
      this.releaseLock = await acquireStationLock(stationId);
      this.lease = await claimPlcWorkstationConnection({
        client_instance_id: clientInstanceId(),
        model_id: modelId,
        bundle_version: PLC_WEB_SERIAL_VERSION
      });
      await this.port.open({ baudRate: 9600, dataBits: 7, stopBits: 1, parity: "even", flowControl: "none" });
      if (!this.port.readable || !this.port.writable) throw new Error("串口未提供读写通道");
      this.reader = this.port.readable.getReader();
      this.writer = this.port.writable.getWriter();
      await this.requireQuietInput(500);
      const info = this.port.getInfo();
      this.lease = await activatePlcWorkstationConnection({
        session_id: this.lease.session_id,
        lease_epoch: this.lease.lease_epoch,
        usb_vendor_id: info.usbVendorId,
        usb_product_id: info.usbProductId
      });
      this.stopped = false;
      this.disconnectListener = (event: Event) => {
        if (event.target === this.port) void this.failClosed("PLC 串口已拔出，请检查线路后人工重连", onFatal);
      };
      navigator.serial.addEventListener("disconnect", this.disconnectListener);
      this.heartbeatTimer = window.setInterval(() => {
        const lease = this.lease;
        if (!lease || this.stopped) return;
        void heartbeatPlcWorkstationConnection(lease.session_id, lease.lease_epoch).then(
          (renewed) => { this.lease = renewed; },
          () => { void this.failClosed("PLC 工作站租约已失效，请人工重新连接", onFatal); }
        );
      }, 5000);
      return this.state();
    } catch (error) {
      await this.disconnect(true);
      throw error;
    }
  }

  async disconnect(notifyServer = true) {
    this.stopped = true;
    if (this.heartbeatTimer !== null) window.clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = null;
    if (this.disconnectListener && navigator.serial) navigator.serial.removeEventListener("disconnect", this.disconnectListener);
    this.disconnectListener = null;
    const lease = this.lease;
    this.lease = null;
    try { await this.reader?.cancel(); } catch { /* best effort */ }
    try { this.reader?.releaseLock(); } catch { /* best effort */ }
    try { this.writer?.releaseLock(); } catch { /* best effort */ }
    this.reader = null;
    this.writer = null;
    this.pendingRead = null;
    this.pendingReadResolved = false;
    try { await this.port?.close(); } catch { /* best effort */ }
    this.port = null;
    if (notifyServer && lease) {
      try { await disconnectPlcWorkstationConnection(lease.session_id, lease.lease_epoch); } catch { /* lease expires fail-closed */ }
    }
    this.releaseLock?.();
    this.releaseLock = null;
  }

  private async failClosed(message: string, onFatal: (message: string) => void) {
    await this.disconnect(true);
    onFatal(message);
  }

  private armRead() {
    if (!this.reader) throw new Error("串口读取器不可用");
    if (!this.pendingRead) {
      this.pendingReadResolved = false;
      this.pendingRead = this.reader.read().then((result) => {
        this.pendingReadResolved = true;
        return result;
      });
    }
    return this.pendingRead;
  }

  private async requireQuietInput(timeoutMs: number) {
    const read = this.armRead();
    let timer = 0;
    const quiet = new Promise<"quiet">((resolve) => { timer = window.setTimeout(() => resolve("quiet"), timeoutMs); });
    const outcome = await Promise.race([read.then(() => "data" as const), quiet]);
    window.clearTimeout(timer);
    if (outcome === "data") throw new Error("串口中存在上一次操作的残留数据，请拔插后重连");
  }

  private async readAck(timeoutMs: number) {
    const read = this.armRead();
    let timer = 0;
    const timeout = new Promise<never>((_, reject) => {
      timer = window.setTimeout(() => reject(new DOMException("ACK timeout", "TimeoutError")), timeoutMs);
    });
    try {
      const result = await Promise.race([read, timeout]);
      this.pendingRead = null;
      this.pendingReadResolved = false;
      if (result.done || !result.value || result.value.length !== 1) {
        return { status: "unexpected_response" as const, response: result.value || new Uint8Array() };
      }
      if (result.value[0] === 0x06) return { status: "acknowledged" as const, response: result.value };
      if (result.value[0] === 0x15) return { status: "nak" as const, response: result.value };
      return { status: "unexpected_response" as const, response: result.value };
    } finally {
      window.clearTimeout(timer);
    }
  }

  private async transact(frame: PlcWebSerialFrame, timeoutMs: number, deadline: number): Promise<PlcWebSerialOperation> {
    const base = { target: frame.target, frame_sha256: frame.frame_sha256, response_hex: "", completed_at: Date.now() };
    if (!this.writer || this.stopped || this.pendingReadResolved || document.visibilityState !== "visible" || performance.now() >= deadline) {
      return { ...base, status: "serial_error", completed_at: Date.now() };
    }
    try {
      this.armRead();
      await Promise.resolve();
      if (this.pendingReadResolved) {
        const stale = await this.pendingRead!;
        this.pendingRead = null;
        this.pendingReadResolved = false;
        return { ...base, status: "unexpected_response", response_hex: hexFromBytes(stale.value || new Uint8Array()), completed_at: Date.now() };
      }
      await this.writer.write(bytesFromHex(frame.frame_hex));
      const reply = await this.readAck(timeoutMs);
      return { ...base, status: reply.status, response_hex: hexFromBytes(reply.response), completed_at: Date.now() };
    } catch (error) {
      return {
        ...base,
        status: error instanceof DOMException && error.name === "TimeoutError" ? "timeout" : "serial_error",
        completed_at: Date.now()
      };
    }
  }

  execute(dispatch: PlcSyncStatus, onFatal: (message: string) => void): Promise<PlcSyncStatus> {
    const operation = async () => {
      const state = this.state();
      if (!state || !dispatch.dispatch_id) throw new Error("PLC 未连接或租约无效");
      const requestStarted = performance.now();
      try {
        const attempt = await declarePlcWebSerialAttempt(dispatch.dispatch_id, {
          session_id: state.sessionId,
          lease_epoch: state.leaseEpoch,
          config_generation: state.configGeneration
        });
        const deadline = requestStarted + attempt.execution_window_ms;
        const operations: PlcWebSerialOperation[] = [];
        const dResult = await this.transact(attempt.frames[0], attempt.ack_timeout_ms, deadline);
        operations.push(dResult);
        if (dResult.status === "acknowledged" && attempt.frames[1]) {
          operations.push(await this.transact(attempt.frames[1], attempt.ack_timeout_ms, deadline));
        }
        const requiresClose = operations.some((item) => item.status !== "acknowledged");
        const uncertain = operations.some((item) => ["timeout", "serial_error", "unexpected_response"].includes(item.status));
        const outcome = dResult.status === "acknowledged"
          ? (operations.length === attempt.frames.length && operations.every((item) => item.status === "acknowledged")
            ? "acknowledged"
            : (uncertain ? "uncertain" : "partial_success"))
          : (dResult.status === "nak" ? "rejected" : "uncertain");
        if (requiresClose) await this.failClosed("PLC 返回异常，端口已关闭；检查线路后人工重连", onFatal);
        return await sendPlcWebSerialReceipt(attempt.dispatch_id, {
          session_id: state.sessionId,
          lease_epoch: state.leaseEpoch,
          attempt_token: attempt.attempt_token,
          outcome,
          operations
        });
      } catch (error) {
        if (this.state()) await this.failClosed("PLC 控制链路中断，端口已关闭；请人工重连", onFatal);
        throw error;
      }
    };
    const next = this.queue.then(operation, operation);
    this.queue = next.catch(() => undefined);
    return next;
  }
}

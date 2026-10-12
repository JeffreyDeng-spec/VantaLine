export type ReleaseIdentity = { release: string; git_commit: string };
export type VersionResponse = ReleaseIdentity & { consistent: boolean };
export type VersionParticipant = {
  dirty?: () => boolean;
  busy?: () => boolean;
  pause?: () => void;
  cleanup?: () => Promise<void> | void;
};
export type VersionState = { pending: boolean; preparing: boolean; stalled: boolean; message: string };
export const identityKey = (value: ReleaseIdentity) => `${value.release}:${value.git_commit}`;
export function validVersion(value: unknown): value is VersionResponse {
  const v = value as VersionResponse | null;
  return Boolean(v && v.consistent === true && /^v[\w.-]+$/.test(v.release) && /^[a-f0-9]{40}$/.test(v.git_commit));
}

type Dependencies = {
  fetchVersion: () => Promise<unknown>;
  now: () => number;
  readAttempt: (key: string) => boolean;
  writeAttempt: (key: string) => void;
  confirmDiscard: () => boolean;
  reload: (url: string) => void;
  currentUrl: () => string;
};

export class VersionCoordinator {
  private participants = new Set<VersionParticipant>();
  private listeners = new Set<() => void>();
  private request: Promise<void> | null = null;
  private transition: Promise<boolean> | null = null;
  private checkedAt = -Infinity;
  private latest: VersionResponse | null = null;
  private operations = 0;
  private waiters = new Set<() => void>();
  private state: VersionState = { pending: false, preparing: false, stalled: false, message: "" };
  constructor(private local: ReleaseIdentity, private deps: Dependencies) {}
  shouldBlockNavigation() { return this.enabled() && (this.state.preparing || this.state.pending || this.deps.now() - this.checkedAt >= 15_000); }
  gestureReady() { return !this.state.preparing && !this.transition && (!this.enabled() || this.deps.now() - this.checkedAt < 15_000 && !this.state.pending); }
  notice(message: string) { this.publish({ message }); }
  snapshot = () => this.state;
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn); }; };
  private publish(next: Partial<VersionState>) {
    this.state = { ...this.state, ...next };
    this.listeners.forEach(fn => fn());
    this.signal();
  }
  register(participant: VersionParticipant) {
    this.participants.add(participant);
    return () => { this.participants.delete(participant); this.signal(); };
  }
  signal() { this.waiters.forEach(fn => fn()); }
  beginOperation() {
    ++this.operations;
    let ended = false;
    return () => { if (!ended) { ended = true; --this.operations; this.signal(); } };
  }
  private enabled() { return /^v[\w.-]+$/.test(this.local.release) && /^[a-f0-9]{40}$/.test(this.local.git_commit); }
  check(force = false): Promise<void> {
    if (!this.enabled()) return Promise.resolve();
    if (this.request) return this.request;
    if (!force && this.deps.now() - this.checkedAt < 15_000) return Promise.resolve();
    this.request = (async () => {
      try {
        const value = await this.deps.fetchVersion();
        // An invalid/unhealthy response cannot authorize a refresh, even after a prior good check.
        this.latest = validVersion(value) ? value : null;
      } catch { this.latest = null; }
      this.checkedAt = this.deps.now();
      const pending = Boolean(this.latest && identityKey(this.latest) !== identityKey(this.local));
      const stalled = Boolean(pending && this.deps.readAttempt(identityKey(this.latest!)));
      this.publish({ pending, stalled, message: stalled ? "更新后仍未取得目标版本，请稍后重试更新。" : pending ? "发现版本更新，下次切换页面或启动主要功能时更新。" : "" });
    })().finally(() => { this.request = null; });
    return this.request;
  }
  async guard(target?: string, manualRetry = false): Promise<boolean> {
    if (this.state.preparing || this.transition) return false;
    this.transition = this.prepare(target, manualRetry);
    try { return await this.transition; } finally { this.transition = null; }
  }
  private async prepare(target?: string, manualRetry = false) {
    await this.check();
    if (!this.latest || identityKey(this.latest) === identityKey(this.local)) return true;
    const key = identityKey(this.latest);
    if (this.deps.readAttempt(key) && !manualRetry) return false;
    this.publish({ preparing: true, message: "正在等待当前操作安全结束，然后更新页面…" });
    try {
      this.participants.forEach(p => p.pause?.());
      await new Promise<void>(resolve => {
        const ready = () => {
          if (this.operations || [...this.participants].some(p => p.busy?.())) return;
          this.waiters.delete(ready); resolve();
        };
        this.waiters.add(ready); ready();
      });
      if ([...this.participants].some(p => p.dirty?.()) && !this.deps.confirmDiscard()) {
        this.publish({ preparing: false, message: "已保留未保存内容，稍后切换时再更新。" });
        return false;
      }
      // Revalidate after a potentially long operation; a rollback or failed deployment can change the target.
      await this.check(true);
      if (!this.latest || identityKey(this.latest) === identityKey(this.local)) {
        this.publish({ preparing: false }); return true;
      }
      const finalKey = identityKey(this.latest);
      if (this.deps.readAttempt(finalKey) && !manualRetry) {
        this.publish({ preparing: false, stalled: true, message: "更新后仍未取得目标版本，请稍后重试更新。" }); return false;
      }
      for (const p of this.participants) await p.cleanup?.();
      this.deps.writeAttempt(finalKey);
      this.deps.reload(target || this.deps.currentUrl());
      return false;
    } catch {
      this.publish({ preparing: false, message: "当前操作尚未安全关闭，请稍后重试更新。" });
      return false;
    }
  }
}

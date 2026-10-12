import { VersionCoordinator } from "./coordinator";

declare const __VANTALINE_RELEASE_IDENTITY__: string;
const [, release, git_commit] = __VANTALINE_RELEASE_IDENTITY__.split(":");
const attemptPrefix = "vantaline.version.attempt.";
const memoryAttempts = new Set<string>();
export const versionCoordinator = new VersionCoordinator({ release, git_commit }, {
  now: () => Date.now(),
  currentUrl: () => window.location.href,
  fetchVersion: async () => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 3000);
    try {
      const response = await fetch("/api/version", { cache: "no-store", credentials: "same-origin", signal: controller.signal });
      if (!response.ok) throw new Error("version unavailable");
      return await response.json();
    } finally { window.clearTimeout(timer); }
  },
  readAttempt: key => {
    try { return memoryAttempts.has(key) || sessionStorage.getItem(attemptPrefix + key) === "1"; }
    catch { return memoryAttempts.has(key); }
  },
  writeAttempt: key => {
    // Fail before reloading when storage is unavailable: an in-memory flag cannot survive navigation.
    sessionStorage.setItem(attemptPrefix + key, "1"); memoryAttempts.add(key);
    sessionStorage.setItem("vantaline.version.updated", "1");
  },
  confirmDiscard: () => window.confirm("当前有未保存内容、未上传文件或标注。放弃这些内容并更新页面？\n选择取消将保留内容并留在当前页。"),
  reload: url => window.location.assign(url)
});
export function guardPlcConnectionGesture() {
  if (versionCoordinator.gestureReady()) return true;
  void versionCoordinator.guard().then(allowed => {
    if (allowed) versionCoordinator.notice("版本已核对，请再次点击连接 PLC，以保留浏览器串口授权手势。");
  });
  return false;
}
export async function guardVersionAction() { return versionCoordinator.guard(); }
export async function runVersionAction<T>(action: () => Promise<T>): Promise<T | undefined> {
  if (!await guardVersionAction()) return;
  const finish = versionCoordinator.beginOperation();
  try { return await action(); } finally { finish(); }
}

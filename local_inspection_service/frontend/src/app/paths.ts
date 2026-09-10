/** Router paths exclude the optional preview basename. API/media URLs never use this helper. */
export const WORKSPACE_PATH = "/workspace";
export const legacyWorkspacePages = [
  "status", "inspect", "text-compare-beta", "ai-inspect", "accessories",
  "training-library", "tasks", "pipeline", "rules", "users", "data-analysis"
] as const;

export function workspacePath(path = "/") {
  if (path === "/" || path === "") return WORKSPACE_PATH;
  return `${WORKSPACE_PATH}${path.startsWith("/") ? path : `/${path}`}`;
}

export function isWorkspacePage(pathname: string) {
  if (pathname === WORKSPACE_PATH || pathname === `${WORKSPACE_PATH}/`) return true;
  const page = pathname.slice(WORKSPACE_PATH.length + 1).replace(/\/$/, "");
  return pathname.startsWith(`${WORKSPACE_PATH}/`) && (
    ([...legacyWorkspacePages.filter((page) => page !== "tasks"), "about"] as readonly string[]).includes(page)
    || /^tasks\/[^/]+(?:\/inspect)?$/.test(page)
  );
}

export function legacyWorkspaceDestination(pathname: string): string | null {
  const page = pathname.replace(/^\//, "");
  if (!legacyWorkspacePages.some((key) => page === key || page.startsWith(`${key}/`))) return null;
  const destination = workspacePath(pathname);
  return isWorkspacePage(destination) ? destination : null;
}

/** Never accept an origin, encoded separator, dot segment or arbitrary route as a login return URL. */
export function safeWorkspaceNext(value: string | null | undefined) {
  if (!value || !value.startsWith("/workspace") || /[\\\u0000-\u0020]/.test(value)) return WORKSPACE_PATH;
  const pathname = value.split(/[?#]/, 1)[0];
  let decoded: string;
  try { decoded = decodeURIComponent(pathname); } catch { return WORKSPACE_PATH; }
  if (/[\\?#\u0000-\u0020%]/.test(decoded) || decoded.split("/").some((part) => part === "." || part === "..")) return WORKSPACE_PATH;
  if (decoded.split("/").length !== pathname.split("/").length || !isWorkspacePage(decoded)) return WORKSPACE_PATH;
  return value;
}

export function loginPath(next: string) {
  return `/login?next=${encodeURIComponent(safeWorkspaceNext(next))}`;
}

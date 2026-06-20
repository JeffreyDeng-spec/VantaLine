import type { ApiRequestOptions, AuthUser } from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly path: string;
  readonly detail: string;

  constructor(message: string, status: number, path: string, detail = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
    this.detail = detail;
  }
}

function apiErrorMessage(response: Response, body = "", path = "") {
  const cleanPath = String(path || "").split("?", 1)[0];
  let detail = "";
  try {
    const parsed = body ? JSON.parse(body) : null;
    if (typeof parsed?.detail === "string") {
      detail = parsed.detail;
    } else if (Array.isArray(parsed?.detail)) {
      detail = parsed.detail
        .map((item: { msg?: string; message?: string }) => item?.msg || item?.message || JSON.stringify(item))
        .filter(Boolean)
        .join("；");
    } else if (parsed?.message) {
      detail = String(parsed.message);
    }
  } catch {
    detail = "";
  }
  const raw = detail || body || response.statusText || `HTTP ${response.status}`;
  if (response.status === 401 && cleanPath === "/api/auth/login" && /invalid username or password/i.test(raw)) {
    return "用户名或密码不正确。";
  }
  if (response.status === 401 && /authentication required/i.test(raw)) {
    return "请先登录。";
  }
  if (response.status === 403 && /permission denied/i.test(raw)) {
    return "没有权限执行此操作。";
  }
  if (response.status === 503 && /first admin setup required/i.test(raw)) {
    return "需要先创建管理员。";
  }
  return raw;
}

async function request<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const body = options.body;
  if (body && !(body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers
  });
  const parseAs = options.parseAs ?? "json";
  const raw = parseAs === "void" ? "" : await response.text();
  if (!response.ok) {
    throw new ApiError(apiErrorMessage(response, raw, path), response.status, path, raw);
  }
  if (parseAs === "void") return undefined as T;
  if (parseAs === "text") return raw as T;
  return (raw ? JSON.parse(raw) : null) as T;
}

function jsonBody(value: unknown) {
  return JSON.stringify(value ?? {});
}

export function withAuthScope(path: string, user: AuthUser | null | undefined, dataUserId: string) {
  if (user?.role !== "admin" || !dataUserId || !path.startsWith("/api/")) return path;
  const joiner = path.includes("?") ? "&" : "?";
  return `${path}${joiner}user_id=${encodeURIComponent(dataUserId)}`;
}

export const apiClient = {
  get<T>(path: string, options?: ApiRequestOptions) {
    return request<T>(path, { ...options, method: "GET" });
  },
  post<T>(path: string, payload?: unknown, options?: ApiRequestOptions) {
    return request<T>(path, { ...options, method: "POST", body: jsonBody(payload) });
  },
  patch<T>(path: string, payload?: unknown, options?: ApiRequestOptions) {
    return request<T>(path, { ...options, method: "PATCH", body: jsonBody(payload) });
  },
  put<T>(path: string, payload?: unknown, options?: ApiRequestOptions) {
    return request<T>(path, { ...options, method: "PUT", body: jsonBody(payload) });
  },
  delete<T>(path: string, options?: ApiRequestOptions) {
    return request<T>(path, { ...options, method: "DELETE" });
  },
  upload<T>(path: string, form: FormData, options?: ApiRequestOptions) {
    return request<T>(path, { ...options, method: options?.method ?? "POST", body: form });
  }
};

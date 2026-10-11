/** Cliente HTTP do painel: sessão do Django + cabeçalho CSRF. */

export class ApiError extends Error {
  status: number;
  data: unknown;
  constructor(status: number, data: unknown) {
    super(errorMessage(data) || `Erro ${status}`);
    this.status = status;
    this.data = data;
  }
}

function errorMessage(data: unknown): string {
  if (!data) return "";
  if (typeof data === "string") return data;
  if (Array.isArray(data)) return data.map(errorMessage).join(" ");
  if (typeof data === "object") {
    const obj = data as Record<string, unknown>;
    if (typeof obj.detail === "string") return obj.detail;
    return Object.entries(obj)
      .map(([k, v]) => (k === "non_field_errors" ? errorMessage(v) : `${k}: ${errorMessage(v)}`))
      .join(" ");
  }
  return String(data);
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

type Json = Record<string, unknown> | unknown[];

async function request<T>(method: string, path: string, body?: Json | FormData): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") headers["X-CSRFToken"] = csrfToken();
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`/api/${path}`, { method, headers, body: payload, credentials: "same-origin" });
  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    if (res.status === 403 && path !== "auth/me") window.dispatchEvent(new Event("auth:expired"));
    throw new ApiError(res.status, data);
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: Json | FormData) => request<T>("POST", path, body ?? {}),
  patch: <T>(path: string, body: Json | FormData) => request<T>("PATCH", path, body),
  put: <T>(path: string, body: Json) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "" && v !== false) search.set(k, String(v));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

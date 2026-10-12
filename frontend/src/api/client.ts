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

// Nome que a pessoa vê no formulário, no lugar do nome interno do campo
const FIELD_LABELS: Record<string, string> = {
  nome: "Nome",
  email: "E-mail",
  password: "Senha",
  first_name: "Nome",
  role: "Perfil",
  otp: "Código",
  category: "Categoria",
  municipality: "Cidade",
  termo_livre: "Termo de busca",
  bairro: "Bairro",
  telefone: "Telefone",
  endereco: "Endereço",
  cnpj: "CNPJ",
  url: "Endereço do site",
  texto: "Texto",
  termos_busca: "Termos de busca",
  cnaes: "CNAEs",
  osm_tags: "Tags do OpenStreetMap",
  item: "Item do checklist",
  nome_empresa: "Empresa",
  cor_primaria: "Cor principal",
  whatsapp: "WhatsApp",
  link_agenda: "Link de agenda",
  email_contato: "E-mail de contato",
  site: "Site",
  logo: "Logo",
  texto_abertura: "Texto de abertura",
  resumo: "Resumo",
  achados_ids: "Achados",
  concorrentes_ids: "Concorrentes",
  expira_em: "Data de expiração",
  titulo: "Título",
  dimensao: "Dimensão",
  severidade: "Severidade",
  impacto_negocio: "Impacto no negócio",
  melhoria_proposta: "Melhoria proposta",
  evidencia: "Evidência",
  modelo: "Modelo",
};

function fieldLabel(key: string): string {
  if (FIELD_LABELS[key]) return FIELD_LABELS[key];
  const text = key.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function errorMessage(data: unknown): string {
  if (!data) return "";
  if (typeof data === "string") return data;
  if (Array.isArray(data)) return data.map(errorMessage).join(" ");
  if (typeof data === "object") {
    const obj = data as Record<string, unknown>;
    if (typeof obj.detail === "string") return obj.detail;
    return Object.entries(obj)
      .map(([k, v]) => (k === "non_field_errors" ? errorMessage(v) : `${fieldLabel(k)}: ${errorMessage(v)}`))
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

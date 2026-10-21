// Thin fetch wrapper: same-origin cookies, CSRF header on writes, problem+json errors.

export class ApiError extends Error {
  status: number;
  code: string;
  errors?: { loc: (string | number)[]; msg: string }[];
  constructor(status: number, code: string, detail: string, errors?: ApiError["errors"]) {
    super(detail);
    this.status = status;
    this.code = code;
    this.errors = errors;
  }
}

function csrfToken(): string {
  const m = document.cookie.match(/(?:^|; )wd_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function request<T>(method: string, path: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
  const init: RequestInit = { method, credentials: "same-origin", headers: { ...headers } };
  if (method !== "GET") (init.headers as Record<string, string>)["X-CSRF-Token"] = csrfToken();
  if (body !== undefined) {
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const res = await fetch(`/api/v1${path}`, init);
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, data.code ?? "error", data.detail ?? res.statusText, data.errors);
  return data as T;
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, b?: unknown, h?: Record<string, string>) => request<T>("POST", p, b ?? {}, h),
  put: <T>(p: string, b: unknown) => request<T>("PUT", p, b),
  patch: <T>(p: string, b: unknown) => request<T>("PATCH", p, b),
  del: <T>(p: string) => request<T>("DELETE", p),
};

// --- types (mirror backend/app/schemas.py) ---------------------------------------------------

export interface Page<T> { items: T[]; total: number; limit: number; offset: number }
export interface User { id: string; email: string; display_name: string; is_platform_admin: boolean }
export interface Org { id: string; name: string; slug: string; role: string | null }
export interface Me { user: User; organizations: Org[]; csrf_token: string }
export interface Project { id: string; name: string; description: string; created_at: string; updated_at: string }
export interface FieldSpec {
  name: string; label?: string; type: string; semantic?: string; required?: boolean; description?: string;
  rules?: Record<string, unknown>; max_length?: number;
}
export interface Spec {
  title: string; entity: string; record_scope: "site" | "page"; fields: FieldSpec[]; deduplication_keys: string[];
  crawl: { start_urls: string[]; allowed_domains: string[]; max_pages: number; max_depth: number;
           max_pages_per_site: number; use_sitemaps: boolean; follow_links: boolean; priority_keywords: string[] };
  discovery: { providers: string[]; industry: string | null; countries: string[]; strict_countries?: boolean; region: string | null;
               keywords: string[]; max_results: number; technology?: string | null;
               technology_aliases?: string[]; evidence_years?: number; parent_company?: string | null };
  export: Record<string, unknown>;
}
export interface Schema { id: string; project_id: string; version: number; nl_request: string; spec: Spec;
  status: string; interpreter: string; created_at: string; notes?: string[] }
export interface UrlCheck { url: string; normalized: string | null; allowed: boolean; reason: string }
export interface Preview { spec: Spec; urls: UrlCheck[]; discovery_providers: string[]; estimated_max_pages: number;
  estimated_llm_calls: number; warnings: string[] }
export interface Job { id: string; project_id: string; schema_id: string; state: string; counters: Record<string, number>;
  settings: Record<string, unknown>; error: string | null; created_at: string; started_at: string | null;
  finished_at: string | null; heartbeat_at: string | null }
export interface Progress { id: string; state: string; counters: Record<string, number>; records: number;
  valid_records: number; elapsed_seconds: number | null; error: string | null; terminal: boolean }
export interface JobEvent { id: number; type: string; from_state: string | null; to_state: string | null;
  message: string; created_at: string; data?: Record<string, unknown> }
export interface Activity extends JobEvent {
  data: { kind: string; site?: string | null; url?: string | null; [k: string]: unknown } }
export interface CrawlUrl { id: string; url: string; method: string; depth: number; status: string;
  status_reason: string | null; referrer_url: string | null; attempts: number; discovered_at: string }
export interface RecordRow { id: string; data: Record<string, unknown>; status: string; quality_score: number;
  excluded: boolean; user_edited: boolean; source_urls: string[]; updated_at: string }
export interface FieldValue { field_name: string; value: unknown; value_status: string; method: string;
  source_url: string | null; evidence: string | null; confidence: number | null; error: string | null; selected: boolean }
export interface RecordDetail extends RecordRow { fields: FieldValue[] }
export interface ExportRow { id: string; job_id: string; status: string; row_count: number; file_bytes: number;
  expires_at: string | null; error: string | null; created_at: string; download_url: string | null }
export interface Usage { period: string; pages: number; llm_requests: number; export_rows: number; active_jobs: number;
  limits: Record<string, number> }
export interface Member { user_id: string; email: string; display_name: string; role: string; created_at: string }

export function display(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join("; ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

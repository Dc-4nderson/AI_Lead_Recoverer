// Typed API client (§2). Consumes the shared types so the dashboard and backend
// never drift silently.
import type {
  BusinessSettings,
  Lead,
  Organization,
  PhoneNumber,
  TokenPair,
} from "@lead-recovery/shared";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const API = `${BASE_URL}/api/v1`;

interface RequestOptions {
  token?: string;
  orgId?: string;
  method?: string;
  body?: unknown;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (opts.token) headers["Authorization"] = `Bearer ${opts.token}`;
  const res = await fetch(`${API}${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail?.error?.message ?? `Request failed: ${res.status}`);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  signup: (email: string, password: string, organization_name: string) =>
    request<TokenPair>("/auth/signup", {
      method: "POST",
      body: { email, password, organization_name },
    }),

  login: (email: string, password: string) =>
    request<TokenPair>("/auth/login", { method: "POST", body: { email, password } }),

  getOrganization: (orgId: string, token: string) =>
    request<Organization>(`/organizations/${orgId}`, { token }),

  listLeads: (orgId: string, token: string) =>
    request<Lead[]>(`/organizations/${orgId}/leads`, { token }),

  listPhoneNumbers: (orgId: string, token: string) =>
    request<PhoneNumber[]>(`/organizations/${orgId}/phone-numbers`, { token }),

  saveBusinessSettings: (orgId: string, token: string, settings: BusinessSettings) =>
    request<BusinessSettings>(`/organizations/${orgId}/business-settings`, {
      token,
      method: "PUT",
      body: settings,
    }),
};

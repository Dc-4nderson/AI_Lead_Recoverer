// Typed API client (§2). Consumes the shared types so the dashboard and backend
// never drift silently.
import type {
  ApiCallRecord,
  BusinessSettings,
  EventTypeInfo,
  Lead,
  Organization,
  PhoneNumber,
  ReplayEventResponse,
  SimulationRunRequest,
  SimulationRunResponse,
  SimulatorScenario,
  TokenPair,
  WorkflowInfo,
} from "@lead-recovery/shared";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const API = `${BASE_URL}/api/v1`;

interface RequestOptions {
  token?: string;
  method?: string;
  body?: unknown;
}

// In-memory log of every call this client makes to the backend — the "API
// Inspector" panel reads this. Accurate for the simulator specifically because
// running a simulation makes no *internal* HTTP calls of its own (it's all
// in-process); this log is genuinely the complete request/response record.
const apiCallLog: ApiCallRecord[] = [];

export function getApiCallLog(): ApiCallRecord[] {
  return apiCallLog;
}

export function clearApiCallLog(): void {
  apiCallLog.length = 0;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (opts.token) headers["Authorization"] = `Bearer ${opts.token}`;
  const method = opts.method ?? "GET";
  const started = performance.now();
  const res = await fetch(`${API}${path}`, {
    method,
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const latency_ms = performance.now() - started;

  let responseBody: unknown = undefined;
  const cloned = res.clone();
  try {
    responseBody = res.status === 204 ? undefined : await cloned.json();
  } catch {
    responseBody = undefined;
  }

  apiCallLog.push({
    method,
    route: path,
    status: res.status,
    latency_ms: Math.round(latency_ms * 100) / 100,
    request_body: opts.body,
    response_body: responseBody,
    timestamp: new Date().toISOString(),
  });

  if (!res.ok) {
    const detail = (responseBody as { error?: { message?: string } }) ?? {};
    throw new Error(detail?.error?.message ?? `Request failed: ${res.status}`);
  }
  return res.status === 204 ? (undefined as T) : (responseBody as T);
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

  listMyOrganizations: (token: string) => request<Organization[]>("/organizations", { token }),

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

  // --- Workflow Simulator ---
  simulator: {
    listWorkflows: (orgId: string, token: string) =>
      request<WorkflowInfo[]>(`/organizations/${orgId}/simulator/workflows`, { token }),

    listEventTypes: (orgId: string, token: string) =>
      request<EventTypeInfo[]>(`/organizations/${orgId}/simulator/event-types`, { token }),

    run: (orgId: string, token: string, body: SimulationRunRequest) =>
      request<SimulationRunResponse>(`/organizations/${orgId}/simulator/run`, {
        token,
        method: "POST",
        body,
      }),

    replayEvent: (
      orgId: string,
      token: string,
      event_type: string,
      payload: Record<string, unknown>
    ) =>
      request<ReplayEventResponse>(`/organizations/${orgId}/simulator/replay-event`, {
        token,
        method: "POST",
        body: { event_type, payload },
      }),

    reset: (orgId: string, token: string, conversation_id: string) =>
      request<{ reset: string; deleted_runs: number }>(
        `/organizations/${orgId}/simulator/reset`,
        { token, method: "POST", body: { conversation_id } }
      ),

    listScenarios: (orgId: string, token: string) =>
      request<SimulatorScenario[]>(`/organizations/${orgId}/simulator/scenarios`, { token }),

    saveScenario: (
      orgId: string,
      token: string,
      name: string,
      payload: SimulationRunRequest
    ) =>
      request<SimulatorScenario>(`/organizations/${orgId}/simulator/scenarios`, {
        token,
        method: "POST",
        body: { name, payload },
      }),

    deleteScenario: (orgId: string, token: string, scenarioId: string) =>
      request<void>(`/organizations/${orgId}/simulator/scenarios/${scenarioId}`, {
        token,
        method: "DELETE",
      }),
  },
};

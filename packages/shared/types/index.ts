// Shared TypeScript types mirroring the backend Pydantic schemas (§2).
//
// SOURCE OF TRUTH: the FastAPI Pydantic models. In a full build these are
// regenerated from the backend's OpenAPI spec (e.g. `openapi-typescript`) and
// checked in CI, so a backend schema change that isn't reflected here fails the
// build rather than surfacing at runtime. The hand-kept subset below covers the
// MVP surface the dashboard consumes today.

export type OrgStatus = "trial" | "active" | "suspended" | "cancelled";

export type LeadStatus =
  | "new"
  | "qualifying"
  | "qualified"
  | "appointment_requested"
  | "closed";

export type Classification =
  | "new_lead"
  | "existing_customer"
  | "emergency"
  | "spam";

export type ConnectionType = "twilio_provisioned" | "forwarded";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Organization {
  id: string;
  name: string;
  industry: string | null;
  timezone: string;
  status: OrgStatus;
  created_at: string;
}

export interface Lead {
  id: string;
  organization_id: string;
  phone_number: string;
  name: string | null;
  service_requested: string | null;
  location: string | null;
  urgency: string | null;
  preferred_time: string | null;
  classification: Classification | null;
  status: LeadStatus;
  created_at: string;
}

export interface PhoneNumber {
  id: string;
  connection_type: ConnectionType;
  e164_number: string;
  business_number: string | null;
  forwarding_status: string | null;
  status: string;
}

export interface BusinessSettings {
  address_line1: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string | null;
  business_hours: Record<string, unknown>;
  services_offered: string[];
  emergency_service_enabled: boolean;
  ai_tone: string | null;
  ai_custom_instructions: string | null;
  notification_preferences: Record<string, unknown>;
}

// --- Workflow Simulator (Developer Tools) -----------------------------------
// Mirrors app/schemas/simulator.py. The simulator is a thin front-end over the
// production backend; these types describe its trace + control surface only.

export interface WorkflowInfo {
  name: string;
  trigger_event: string;
  steps: string[];
}

export interface EventTypeInfo {
  name: string;
  event_type: string;
  fields: string[];
}

export interface SimulationRunRequest {
  workflow: string;
  caller_number: string;
  business_number: string;
  conversation_turns: string[];
  use_real_ai: boolean;
  business_settings_overrides?: Record<string, unknown> | null;
}

export interface TraceRecord {
  seq: number;
  ts: string;
  [key: string]: unknown;
}

export interface SimulationTrace {
  events: TraceRecord[];
  subscribers: TraceRecord[];
  workflow_steps: TraceRecord[];
  queue_jobs: TraceRecord[];
  ai_calls: TraceRecord[];
  db_changes: TraceRecord[];
  sms: TraceRecord[];
  timeline: TraceRecord[];
}

export interface SimulationRunResponse {
  call_sid: string;
  conversation_id: string | null;
  workflow_run: {
    id: string;
    workflow_name: string;
    status: string;
    state: Record<string, unknown>;
  } | null;
  lead: {
    id: string;
    name: string | null;
    service_requested: string | null;
    classification: string | null;
    urgency: string | null;
    status: string;
  } | null;
  trace: SimulationTrace;
}

export interface ReplayEventResponse {
  replayed: string;
  trace: SimulationTrace;
}

export interface SimulatorScenario {
  id: string;
  name: string;
  payload: SimulationRunRequest;
  created_at: string;
}

// Client-side record of a call the simulator UI made to its own backend
// (the "API Inspector" — accurate because in-process simulation makes no
// internal HTTP calls of its own).
export interface ApiCallRecord {
  method: string;
  route: string;
  status: number;
  latency_ms: number;
  request_body?: unknown;
  response_body?: unknown;
  timestamp: string;
}

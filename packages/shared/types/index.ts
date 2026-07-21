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

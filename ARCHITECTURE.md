# AI Lead Recovery Platform — Architecture (v1 / MVP)

Status: **Proposed — pending review, no implementation yet.**

## 0. Guiding constraint

Every design decision below is filtered through one question: *can the next
customer onboard and operate this without a developer touching code?* Where a
shortcut would violate that, the tradeoff is called out explicitly.

---

## 1. Overall Architecture

Single FastAPI monolith (modular, not microservices) behind a task queue,
backed by Postgres, talking to Twilio (SMS) and OpenAI (qualification), with
async background jobs for anything Twilio-triggered.

```
                         ┌─────────────────────┐
                         │   Dashboard (SPA)    │  customer + admin portal
                         └──────────┬───────────┘
                                    │ HTTPS/JSON
                         ┌──────────▼───────────┐
                         │   FastAPI API layer   │  auth, tenant routing,
                         │  (routers → services) │  request validation
                         └──────────┬───────────┘
                    ┌───────────────┼────────────────┐
                    │               │                │
             ┌──────▼─────┐  ┌──────▼──────┐  ┌───────▼──────┐
             │  Postgres   │  │  Redis      │  │  Job Queue    │
             │ (tenant     │  │ (cache,     │  │ (Celery/RQ/   │
             │  scoped)    │  │  rate-limit)│  │  arq worker)  │
             └─────────────┘  └─────────────┘  └───────┬──────┘
                                                        │
                             ┌──────────────────────────┼───────────────────┐
                             │                          │                   │
                      ┌──────▼──────┐          ┌────────▼───────┐   ┌───────▼──────┐
                      │  Twilio      │          │   OpenAI        │   │  Notification │
                      │  (webhook in,│          │ (qualification, │   │  (SMS/email/  │
                      │   SMS out)   │          │  classification)│   │   push out)   │
                      └──────────────┘          └─────────────────┘   └──────────────┘
```

Why a monolith, not microservices: at "hundreds of businesses, thousands of
conversations," the bottleneck is never inter-service scaling — it's
onboarding friction and prompt/config correctness. Microservices add
deployment and operational complexity with no payoff at this scale. The
service layer inside the monolith is already split by domain (see §9), so
extracting a service later (e.g. a dedicated Voice AI service) is a lift-and-shift,
not a rewrite.

Why a queue for Twilio events: the missed-call → SMS SLA is 30 seconds, and
OpenAI/Twilio calls have variable latency. The webhook handler's only job is
"validate signature, persist the event, enqueue job, return 200 fast." All
qualification logic runs in a worker so Twilio never sees a timeout and
retries don't create duplicate leads (see idempotency in §10).

---

## 2. Folder Structure

```
ai-lead-recovery/
├── app/
│   ├── main.py                     # FastAPI app factory, middleware, routers
│   ├── core/
│   │   ├── config.py                # env-driven settings (pydantic-settings)
│   │   ├── security.py              # JWT, password hashing, tenant context
│   │   ├── logging.py                # structured logging setup
│   │   └── db.py                     # engine, session factory
│   ├── models/                      # SQLAlchemy ORM models (one file per aggregate)
│   │   ├── organization.py
│   │   ├── user.py
│   │   ├── business_settings.py
│   │   ├── lead.py
│   │   ├── conversation.py
│   │   ├── message.py
│   │   ├── phone_number.py
│   │   └── audit_log.py
│   ├── schemas/                     # Pydantic request/response DTOs
│   │   └── ... (mirrors models)
│   ├── repositories/                # DB access, always tenant-scoped
│   │   └── ...
│   ├── services/                    # business logic, orchestration
│   │   ├── auth_service.py
│   │   ├── organization_service.py
│   │   ├── twilio_service.py
│   │   ├── ai_qualification_service.py
│   │   ├── lead_service.py
│   │   ├── notification_service.py
│   │   └── prompt_service.py         # renders per-tenant AI prompt config
│   ├── api/
│   │   ├── v1/
│   │   │   ├── router.py
│   │   │   ├── auth.py
│   │   │   ├── organizations.py
│   │   │   ├── business_settings.py
│   │   │   ├── leads.py
│   │   │   ├── conversations.py
│   │   │   └── webhooks/
│   │   │       └── twilio.py
│   │   └── deps.py                   # get_db, get_current_user, get_tenant
│   ├── workers/
│   │   ├── celery_app.py (or arq worker.py)
│   │   ├── tasks/
│   │   │   ├── handle_missed_call.py
│   │   │   ├── process_inbound_sms.py
│   │   │   └── send_notification.py
│   ├── integrations/
│   │   ├── twilio_client.py
│   │   ├── openai_client.py
│   │   ├── calendar/                 # google.py, outlook.py (future)
│   │   └── crm/                      # future
│   └── shared/
│       ├── exceptions.py
│       └── enums.py
├── alembic/                          # migrations
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── scripts/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── .env.example
```

Each domain gets: model → schema → repository → service → router. No
business logic in routers or ORM models — routers validate/authorize and
delegate; models are data only; services own logic; repositories own queries.

---

## 3. Database Schema (MVP)

All tenant-owned tables carry `organization_id` with a composite FK/index and
`NOT NULL`. No table holds business logic in its structure (e.g., no
`plumbing_leads` table) — industry-specific fields live in JSONB config, not
schema.

```
organizations
  id (uuid, pk)
  name
  industry                 -- free text initially, enum later
  timezone
  status                    -- trial | active | suspended | cancelled
  created_at, updated_at

business_settings            (1:1 with organizations)
  id (uuid, pk)
  organization_id (fk, unique)
  address_line1, city, state, postal_code, country
  business_hours (jsonb)     -- {mon: [{open,close}], ...}
  services_offered (jsonb)   -- ["drain cleaning", "install", ...]
  emergency_service_enabled (bool)
  ai_tone (text)             -- "friendly", "formal", custom instructions
  ai_custom_instructions (text)
  notification_preferences (jsonb) -- {sms: true, email: [...], owner_phone: ...}
  created_at, updated_at

users
  id (uuid, pk)
  email (unique)
  hashed_password
  is_email_verified (bool)
  created_at, updated_at

memberships                  -- user <-> org, many-to-many with role
  id (uuid, pk)
  user_id (fk)
  organization_id (fk)
  role                        -- owner | admin | staff  (RBAC hook)
  created_at
  UNIQUE(user_id, organization_id)

phone_numbers
  id (uuid, pk)
  organization_id (fk)
  twilio_sid
  e164_number (unique)
  status                      -- provisioning | active | released
  created_at

leads
  id (uuid, pk)
  organization_id (fk)
  phone_number (e164)         -- caller's number
  name
  service_requested
  location
  urgency                     -- low | normal | emergency
  preferred_time (text/timestamptz nullable)
  classification              -- new_lead | existing_customer | emergency | spam
  status                      -- new | qualifying | qualified | appointment_requested | closed
  created_at, updated_at
  INDEX(organization_id, phone_number)

conversations
  id (uuid, pk)
  organization_id (fk)
  lead_id (fk, nullable until qualified enough to link)
  twilio_conversation_sid / call_sid
  channel                     -- sms | voice (future)
  state                       -- machine state for qualification flow (jsonb)
  started_at, last_message_at

messages
  id (uuid, pk)
  conversation_id (fk)
  direction                   -- inbound | outbound
  body (text)
  provider_message_sid
  created_at
  UNIQUE(provider_message_sid)   -- idempotency guard

audit_logs
  id (uuid, pk)
  organization_id (fk, nullable for platform-level)
  actor_user_id (fk, nullable for system actions)
  action, entity_type, entity_id
  metadata (jsonb)
  created_at
```

Entity relationships: `organizations 1—1 business_settings`,
`organizations 1—N phone_numbers/leads/conversations`, `users N—N organizations`
via `memberships`, `conversations 1—N messages`, `leads 1—N conversations`
(a lead can re-engage in a new conversation).

---

## 4. Authentication Flow

- Email/password signup → email verification token (short-lived, single-use,
  stored hashed) → account active.
- JWT access token (short TTL, ~15 min) + refresh token (rotated, stored
  hashed in DB so it can be revoked) — refresh tokens let us kill sessions on
  suspicious activity without waiting for expiry.
- A user can belong to multiple organizations (`memberships`); the JWT
  carries `user_id` only — **not** `organization_id`. Organization context is
  resolved per-request from an `X-Org-Id` header or path param, then
  validated against `memberships` on every request. This avoids stale-token
  problems if a user is removed from an org mid-session.
- Password hashing: argon2id (bcrypt as fallback if platform constraints
  demand it).
- Future SSO/OAuth (Google/Outlook for calendar) is a separate concern from
  login auth — calendar connection is a per-organization integration
  credential, not an identity provider swap.

---

## 5. Tenant Isolation Strategy

MVP choice: **shared database, shared schema, `organization_id` on every
tenant-owned row, enforced at the repository layer** — not Postgres RLS, not
schema-per-tenant, not database-per-tenant.

Why: schema/DB-per-tenant kills the "zero engineering work" onboarding goal —
every new customer would need infra provisioning. Shared-schema with an
enforced tenant column lets onboarding be a single `INSERT INTO organizations`.

Enforcement mechanism (this is the part that actually matters, not the
schema choice):
- Every repository method requires an `organization_id` argument — there is
  no "get lead by id" without a tenant scope, only "get lead by id for org X."
- A `TenantScopedRepository` base class makes an unscoped query a type error,
  not a runtime hope.
- `get_current_org` dependency in FastAPI resolves and validates org
  membership before any router body runs; the resolved `org_id` is threaded
  through the service/repository calls explicitly (not via thread-local
  globals — explicit is testable, globals are not).
- Postgres Row-Level Security is added as a **defense-in-depth** layer once
  the app is stable (policy: `organization_id = current_setting('app.org_id')`),
  set via `SET LOCAL` per request/transaction. This is recommended for v1.1,
  not deferred indefinitely — RLS catches the bug where a repository method
  gets it wrong.
- Twilio webhooks resolve tenant by looking up the *receiving* phone number
  in `phone_numbers`, never by trusting caller-supplied data.

Tradeoff acknowledged: shared-schema means one noisy/large tenant can affect
others without care (index bloat, query plans). Mitigated by
`organization_id` being the leading column in every composite index, and by
the fact that per-tenant conversation volume in this domain is inherently
small (missed calls, not high-frequency events).

---

## 6. Configuration System

This is the actual product, not a side detail — "configuration replaces
code" lives here.

- **Business settings** (hours, services, tone, notifications) live in
  `business_settings` as structured JSONB + typed columns, editable via
  dashboard CRUD — no deploy required, ever.
- **AI prompt composition**: a `PromptService` builds the system prompt at
  runtime from: (1) a versioned base template (platform-owned, industry-
  agnostic qualification flow), (2) tenant overrides (`ai_tone`,
  `ai_custom_instructions`, `services_offered`, `emergency_service_enabled`).
  Templates use a constrained variable-substitution format (Jinja2 with
  autoescape and no arbitrary code execution) — never string-eval customer
  input into a prompt-building code path.
- **Feature flags per org** (future: voice AI, CRM sync) live in an
  `organization_features` table or JSONB column, not in code branches per
  customer — a flag off just means a UI section is hidden and a worker task
  is skipped.
- Platform-level config (Twilio account, OpenAI keys, default templates)
  comes from environment/secrets manager, never from tenant-editable tables.

Rule of thumb enforced in code review: if a new industry ("plumbing" vs
"dental") requires a new `if industry == "plumbing"` branch anywhere outside
seed data, that's a design smell — it should be a config value the seed data
sets differently.

---

## 7. API Routes (MVP surface)

```
POST   /api/v1/auth/signup
POST   /api/v1/auth/verify-email
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout

POST   /api/v1/organizations                # create org during onboarding
GET    /api/v1/organizations/{org_id}
PATCH  /api/v1/organizations/{org_id}

GET    /api/v1/organizations/{org_id}/business-settings
PUT    /api/v1/organizations/{org_id}/business-settings

POST   /api/v1/organizations/{org_id}/phone-numbers   # provision/connect
GET    /api/v1/organizations/{org_id}/phone-numbers

GET    /api/v1/organizations/{org_id}/leads
GET    /api/v1/organizations/{org_id}/leads/{lead_id}
PATCH  /api/v1/organizations/{org_id}/leads/{lead_id}

GET    /api/v1/organizations/{org_id}/conversations/{id}

POST   /api/v1/webhooks/twilio/voice-status     # missed-call detection
POST   /api/v1/webhooks/twilio/sms-inbound       # lead SMS replies

GET    /api/v1/health
```

All non-webhook, non-auth routes require `X-Org-Id` + JWT, validated against
`memberships`. Webhook routes validate Twilio's request signature instead of
JWT.

---

## 8. Service Layer

Routers depend on services; services depend on repositories + integration
clients; nothing skips a layer.

- `AuthService` — signup, verification, login, token issuance/rotation.
- `OrganizationService` — org + membership lifecycle.
- `BusinessSettingsService` — validated CRUD over settings, emits
  `audit_log` entries on change.
- `TwilioService` — thin wrapper: validate webhook signature, provision
  numbers, send SMS. No business logic.
- `PromptService` — composes the AI system prompt from base template + org
  config (§6).
- `AIQualificationService` — calls OpenAI with the composed prompt +
  conversation history, parses structured output (function-calling /
  JSON schema response) into name/service/location/urgency/time +
  classification. Never trusts free-text parsing when structured output is
  available.
- `ConversationService` — owns the SMS state machine: which question to ask
  next, when qualification is "done," when to hand off to notification.
- `LeadService` — persists/updates lead records, transitions status.
- `NotificationService` — sends owner notifications (SMS/email), reads
  `notification_preferences`, provider-agnostic interface so a Slack/email
  channel can be added later without touching callers.

Dependency injection via FastAPI's `Depends` for request-scoped services;
constructor injection for anything used inside workers (no FastAPI `Depends`
available there).

---

## 9. Background Job Architecture

Queue: **Celery + Redis** (or `arq` if the team prefers a lighter async-native
option — both satisfy the requirement; recommend `arq` for an async-first
FastAPI codebase, Celery if broader ecosystem/monitoring tooling matters more
at scale). Decision needed from you before implementation — flagged as an
open question in §15.

Jobs:
- `handle_missed_call(org_id, call_sid)` — triggered by Twilio voice-status
  webhook when a call is marked `no-answer`/`busy`. Enqueued with the 30-second
  SLA in mind: webhook returns immediately, worker picks up within seconds.
  Idempotency key: `call_sid` (unique constraint) so Twilio's at-least-once
  webhook delivery can't send two SMS for one missed call.
- `process_inbound_sms(org_id, message_sid, body, from_number)` — runs the
  AI qualification turn, updates conversation state, decides next question or
  triggers completion. Idempotency key: `provider_message_sid` unique
  constraint on `messages`.
- `send_notification(org_id, lead_id, channel)` — owner alert once a lead is
  qualified/classified.

Retry policy: exponential backoff, max 3 attempts, dead-letter queue (a
`failed_jobs` table or Celery's built-in) with alerting — a failed
qualification job must not silently drop a lead.

---

## 10. Idempotency & Reliability Notes

- Twilio can retry webhooks — every webhook handler is a fast, idempotent
  "record + enqueue," never inline processing.
- Unique constraints (`call_sid`, `provider_message_sid`) are the actual
  idempotency guarantee, not "we probably won't get duplicates."
- Conversation state machine persists to `conversations.state` after every
  transition so a worker crash mid-conversation resumes correctly rather than
  restarting the qualification flow.

---

## 11. Deployment Architecture

- Containerized: `Dockerfile` for API, same image for worker (different
  entrypoint/command) — one image, two run modes, avoids drift.
- `docker-compose.yml` for local dev (Postgres, Redis, API, worker).
- Target production: any container platform (Fly.io/Render/ECS/Railway) —
  architecture doesn't lock into one; the requirement is: API is stateless
  and horizontally scalable, worker pool scales independently from API
  pool (qualification jobs are the actual bottleneck under load, not HTTP
  request handling).
- Migrations via Alembic, run as a release step before new API/worker
  versions receive traffic — never auto-migrate on app boot in production.
- Secrets (Twilio, OpenAI, DB URL, JWT signing key) via environment
  variables sourced from the platform's secret manager, never committed.
- Twilio webhook URLs point at a stable public API domain; local dev uses
  a tunnel (ngrok) for webhook testing.

---

## 12. Monitoring and Logging

- Structured JSON logging (one log line per request/job, with `org_id`,
  `request_id`, `duration_ms`) — plain-text logs are not queryable once
  you have hundreds of tenants.
- `request_id` generated at the edge (or read from a header) and threaded
  through service/worker calls via context var, so a support question ("what
  happened to lead X") is one log query, not a grep.
- Metrics: request latency/error rate, job queue depth, job failure rate,
  Twilio webhook failure rate, OpenAI call latency/error rate/cost —
  exported to whatever platform (Prometheus/Datadog/hosted APM) is chosen at
  deploy time; the app just needs to emit them via a metrics abstraction, not
  a vendor SDK sprinkled through business logic.
- `audit_logs` table is product-facing (a customer/admin can see "what
  changed"), distinct from operational logs which are engineering-facing.
- Alerting on: job dead-letter growth, webhook signature-validation
  failures (signal of misconfiguration or attack), missed-call → SMS latency
  exceeding the 30s SLA.

---

## 13. Testing Strategy

- **Unit tests**: services and repositories in isolation, DB access mocked
  or hit a test transaction that's rolled back. `PromptService` and the
  qualification state machine are the highest-value targets — this is where
  "config replaces code" bugs would hide.
- **Integration tests**: real Postgres (test container), real request/response
  cycle through FastAPI's TestClient, Twilio/OpenAI clients mocked at the
  integration boundary (never hit real external APIs in CI).
- **Contract tests** for Twilio webhook payloads and OpenAI structured-output
  schemas — these are the two external contracts most likely to change
  underneath us.
- **Tenant-isolation tests** are a first-class category, not incidental: a
  test that asserts org A can never read/write org B's leads/settings/
  conversations, run against every new endpoint.
- Target: fast unit suite runs on every commit; integration suite on PR;
  no code merges without tenant-isolation tests passing for any new
  tenant-scoped table/route.

---

## 14. Future Scaling Strategy

- **Voice AI**: add as a new `channel` on `conversations` + a new
  integration module (`integrations/voice/`); qualification/prompt logic is
  already channel-agnostic if `ConversationService` is built against a
  message abstraction rather than "SMS" concretely — worth the small extra
  abstraction now.
- **CRM integrations**: `integrations/crm/` with a common interface
  (`push_lead(lead) -> external_id`); per-tenant CRM credentials stored like
  calendar credentials (§ below); sync triggered as a background job on lead
  qualification, not inline.
- **Calendar (Google/Outlook)**: OAuth credentials stored encrypted per
  organization; `integrations/calendar/` common interface
  (`get_availability`, `create_event`); appointment-request flow calls this
  interface, agnostic to provider.
- **Stripe subscriptions**: `subscriptions`/`plans` tables tied to
  `organizations`; middleware checks `organization.status` (trial/active/
  past_due/cancelled) to gate access — billing state, not code, controls
  access.
- **Multiple AI agents / different industries**: industry becomes a seed
  value that selects a base prompt template + default services list; still
  one codebase.
- **RBAC**: `memberships.role` already exists in the MVP schema; enforcement
  today only checks org membership, but the column is there so permission
  checks can tighten without a migration.
- **White-labeling**: `organizations` gains branding fields (logo, colors,
  custom domain) consumed by the dashboard/customer-facing SMS sender name;
  no backend architecture change required.
- **API access for customers**: versioned `/api/v1/...` already in place;
  add per-org API keys + rate limiting (Redis) as an additive auth method
  alongside JWT.
- **Horizontal scale**: stateless API pods behind a load balancer, worker
  pool scaled by queue depth, Postgres read replicas for reporting/analytics
  once dashboard read load matters — none of this requires an architecture
  change, only infra scaling, because tenant isolation and service
  boundaries were established up front.

---

## 15. Open Questions for You (need a decision before implementation)

1. **Job queue**: Celery+Redis vs. `arq` (lighter, async-native, less
   ecosystem/tooling maturity)? Recommendation: `arq`, given the codebase is
   async-first FastAPI, unless you already have ops familiarity with Celery.
2. **Number provisioning**: does every customer get a Twilio number
   provisioned by us (Twilio API), or do they connect/forward an existing
   business number? Changes the phone_numbers onboarding step significantly.
3. **OpenAI usage**: standard Chat Completions with function-calling for
   structured extraction, or the Assistants/Responses API? Recommendation:
   Chat Completions + structured outputs (JSON schema) — simpler, cheaper,
   fully sufficient for qualification extraction.
4. **Dashboard stack**: not specified — do you want this repo to include the
   frontend (e.g., Next.js) or is the dashboard a separate repo consuming
   this API? Affects folder structure and whether CORS/session strategy
   needs finalizing now.
5. **Hosting target**: any existing preference (Render/Fly/AWS) affects how
   concretely I write the deployment config (§11) vs. keeping it generic.

---

## Next Step

This document is the architecture review checkpoint you specified — please
confirm or redirect before I scaffold the MVP codebase (§2 folder structure,
models, Alembic migrations, and the missed-call → SMS happy path end to end).

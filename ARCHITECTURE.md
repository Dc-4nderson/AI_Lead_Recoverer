# AI Lead Recovery Platform — Architecture (v1 / MVP)

Status: **Proposed — decisions incorporated, pending final review, no implementation yet.**

Changelog: v2 incorporates seven confirmed decisions — arq behind a queue
abstraction, dual-path phone number system (forwarding-first), OpenAI
Responses API with structured JSON schemas, monorepo (FastAPI + Next.js +
shared package), Render as initial target with portable infra, an internal
typed event bus, and a workflow-engine architecture (AI does NLU/extraction
only; workflows own every decision and side effect).

## 0. Guiding constraint

Every design decision below is filtered through one question: *can the next
customer onboard and operate this without a developer touching code?* Where a
shortcut would violate that, the tradeoff is called out explicitly.

---

## 1. Overall Architecture

A monorepo containing a FastAPI backend (modular monolith) and a Next.js
dashboard, sharing a types/config package. The backend is built around three
pillars instead of a single "chatbot service":

1. **Integrations** — Twilio, OpenAI, calendar, CRM. Pure I/O adapters, no
   business logic.
2. **AI extraction layer** — takes raw conversation input, returns
   structured, schema-validated data (name, service, urgency, classification).
   It never decides what happens next.
3. **Workflow engine** — the only layer allowed to make business decisions
   and cause side effects (send SMS, notify owner, create appointment). It
   reacts to typed events on an internal event bus.

```
                         ┌─────────────────────┐
                         │  Next.js Dashboard   │  customer + admin portal
                         └──────────┬───────────┘
                                    │ HTTPS/JSON (shared types package)
                         ┌──────────▼───────────┐
                         │   FastAPI API layer   │  auth, tenant routing,
                         │  (routers → services) │  request validation
                         └──────────┬───────────┘
                                    │ publishes
                         ┌──────────▼───────────┐
                         │    Event Bus          │  typed domain events
                         │ (in-process now,      │  (§16)
                         │  Redis pub/sub later) │
                         └──────────┬───────────┘
                    ┌───────────────┼────────────────────┐
                    │               │                    │
             ┌──────▼──────┐ ┌──────▼───────┐   ┌────────▼────────┐
             │ Workflow     │ │ AI Extraction │   │ Notification /   │
             │ Engine (§17) │ │ Layer (OpenAI │   │ Audit / Analytics│
             │ deterministic│ │ Responses API,│   │ subscribers      │
             │ decisions    │ │ JSON schema)  │   │                  │
             └──────┬───────┘ └───────────────┘   └──────────────────┘
                    │
             ┌──────▼───────┐        ┌─────────────┐       ┌─────────────┐
             │ Job Queue     │◄──────►│  Postgres   │       │  Redis       │
             │ (arq, behind  │        │ (tenant     │       │ (cache,      │
             │  abstraction) │        │  scoped)    │       │  rate-limit, │
             └──────┬────────┘        └─────────────┘       │  queue store)│
                    │                                        └─────────────┘
             ┌──────▼──────┐
             │  Twilio      │  webhook in (missed call, inbound SMS), SMS out
             └──────────────┘
```

Why a monolith, not microservices: at "hundreds of businesses, thousands of
conversations," the bottleneck is never inter-service scaling — it's
onboarding friction and correctness of the workflow/config logic.
Microservices add deployment and operational complexity with no payoff yet.
Domain boundaries (event bus, workflow engine, AI extraction) are already
process-internal module boundaries, so extracting any one into its own
service later is lift-and-shift, not a rewrite.

Why AI-extraction vs. workflow-engine as separate layers (the most important
structural decision in this revision): an AI chatbot architecture makes the
LLM responsible for both understanding *and* deciding — which means business
logic ends up encoded in prompts, is non-deterministic, and is nearly
impossible to unit test or audit. Splitting them means:
- The AI layer's contract is "text/context in → validated JSON out," nothing
  else. It can be swapped, prompt-tuned, or A/B tested without touching
  business behavior.
- The workflow engine's contract is "typed event in → decision + side
  effects out," fully deterministic and unit-testable without ever calling
  OpenAI.
- New industries or business rules become workflow configuration (§6, §17),
  not new prompts to hand-tune.

---

## 2. Folder Structure (monorepo)

```
ai-lead-recovery/
├── apps/
│   ├── api/                          # FastAPI backend
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── core/
│   │   │   │   ├── config.py          # pydantic-settings, env-driven
│   │   │   │   ├── security.py        # JWT, password hashing, tenant context
│   │   │   │   ├── logging.py
│   │   │   │   └── db.py
│   │   │   ├── models/                # SQLAlchemy ORM (one file per aggregate)
│   │   │   │   ├── organization.py
│   │   │   │   ├── user.py
│   │   │   │   ├── business_settings.py
│   │   │   │   ├── lead.py
│   │   │   │   ├── conversation.py
│   │   │   │   ├── message.py
│   │   │   │   ├── phone_number.py
│   │   │   │   ├── workflow_run.py
│   │   │   │   ├── event_log.py
│   │   │   │   └── audit_log.py
│   │   │   ├── schemas/                # Pydantic DTOs — generated into
│   │   │   │   └── ...                 # packages/shared-types for the frontend
│   │   │   ├── repositories/           # DB access, always tenant-scoped
│   │   │   ├── events/                 # event bus (§16)
│   │   │   │   ├── bus.py               # publish/subscribe abstraction
│   │   │   │   ├── types.py             # typed event definitions (pydantic)
│   │   │   │   └── handlers/            # subscriber registration per domain
│   │   │   ├── workflows/              # workflow engine (§17)
│   │   │   │   ├── engine.py
│   │   │   │   ├── definitions/         # declarative workflow configs
│   │   │   │   │   └── missed_call_recovery.py
│   │   │   │   └── steps/               # reusable deterministic steps
│   │   │   ├── ai/                     # extraction-only layer
│   │   │   │   ├── extraction_service.py
│   │   │   │   ├── prompt_service.py     # composes per-tenant instructions
│   │   │   │   └── schemas.py             # JSON-schema response contracts
│   │   │   ├── services/               # auth, org, settings, phone, notification
│   │   │   ├── api/
│   │   │   │   ├── v1/
│   │   │   │   │   ├── router.py
│   │   │   │   │   ├── auth.py
│   │   │   │   │   ├── organizations.py
│   │   │   │   │   ├── business_settings.py
│   │   │   │   │   ├── phone_numbers.py
│   │   │   │   │   ├── leads.py
│   │   │   │   │   ├── conversations.py
│   │   │   │   │   └── webhooks/twilio.py
│   │   │   │   └── deps.py
│   │   │   ├── queue/                  # job queue abstraction (§9)
│   │   │   │   ├── interface.py         # QueueClient protocol
│   │   │   │   ├── arq_backend.py
│   │   │   │   └── tasks/
│   │   │   ├── integrations/
│   │   │   │   ├── twilio_client.py
│   │   │   │   ├── openai_client.py
│   │   │   │   ├── calendar/            # future
│   │   │   │   └── crm/                 # future
│   │   │   └── shared/
│   │   │       ├── exceptions.py
│   │   │       └── enums.py
│   │   ├── alembic/
│   │   ├── tests/{unit,integration}/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   └── web/                           # Next.js dashboard
│       ├── app/                       # App Router: onboarding, dashboard, admin
│       ├── components/
│       ├── lib/api-client.ts           # typed client using packages/shared-types
│       ├── Dockerfile
│       └── package.json
├── packages/
│   └── shared/
│       ├── types/                      # generated/hand-kept TS types mirroring
│       │                                # Pydantic schemas (OpenAPI-generated)
│       └── config/                     # shared lint/tsconfig/env schema
├── docker-compose.yml                  # postgres, redis, api, worker, web
├── render.yaml                         # Render blueprint (§11)
├── turbo.json / pnpm-workspace.yaml    # monorepo task runner + workspaces
└── package.json
```

Each backend domain still gets: model → schema → repository → service/
workflow → router. No business logic in routers, ORM models, or the AI
layer — routers validate/authorize and delegate; the workflow engine is the
only place decisions and side effects are made.

Frontend/backend type sharing: Pydantic schemas are the source of truth;
`packages/shared/types` holds OpenAPI-generated TypeScript types consumed by
`apps/web`, checked in CI so a backend schema change that isn't reflected in
the frontend fails the build rather than surfacing at runtime.

---

## 3. Database Schema (MVP)

All tenant-owned tables carry `organization_id` with a composite FK/index and
`NOT NULL`. No table holds business logic in its structure — industry- and
workflow-specific behavior lives in config (JSONB / workflow definitions),
not schema.

```
organizations
  id (uuid, pk)
  name
  industry
  timezone
  status                    -- trial | active | suspended | cancelled
  created_at, updated_at

business_settings            (1:1 with organizations)
  id (uuid, pk)
  organization_id (fk, unique)
  address_line1, city, state, postal_code, country
  business_hours (jsonb)
  services_offered (jsonb)
  emergency_service_enabled (bool)
  ai_tone (text)
  ai_custom_instructions (text)
  notification_preferences (jsonb)
  created_at, updated_at

users
  id (uuid, pk)
  email (unique)
  hashed_password
  is_email_verified (bool)
  created_at, updated_at

memberships
  id (uuid, pk)
  user_id (fk)
  organization_id (fk)
  role                        -- owner | admin | staff
  created_at
  UNIQUE(user_id, organization_id)

phone_numbers
  id (uuid, pk)
  organization_id (fk)
  connection_type             -- 'twilio_provisioned' | 'forwarded'
  e164_number (unique)        -- the number Twilio actually receives calls/SMS on
  business_number (e164, nullable)   -- customer's real number, set when
                                     -- connection_type = 'forwarded'
  twilio_sid (nullable)       -- set for twilio_provisioned; also set for the
                               -- forwarding target number if we provision one
                               -- to receive forwarded calls
  forwarding_status           -- nullable; 'pending_verification' | 'verified' | 'failed'
                               -- used only for the forwarding path (§17a)
  status                      -- provisioning | active | released
  created_at, updated_at

leads
  id (uuid, pk)
  organization_id (fk)
  phone_number (e164)
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
  lead_id (fk, nullable)
  twilio_conversation_sid / call_sid
  channel                     -- sms | voice (future)
  started_at, last_message_at

messages
  id (uuid, pk)
  conversation_id (fk)
  direction                   -- inbound | outbound
  body (text)
  provider_message_sid
  created_at
  UNIQUE(provider_message_sid)

workflow_runs                  -- one row per workflow instance execution
  id (uuid, pk)
  organization_id (fk)
  workflow_name                -- e.g. 'missed_call_recovery'
  trigger_event_id (fk -> event_log.id)
  conversation_id (fk, nullable)
  lead_id (fk, nullable)
  state                        -- jsonb: current step, accumulated extracted data
  status                       -- running | waiting_on_reply | completed | failed
  created_at, updated_at

event_log                      -- durable record of every published event (§16)
  id (uuid, pk)
  organization_id (fk, nullable for platform-level events)
  event_type                   -- e.g. 'missed_call.detected', 'lead.qualified'
  payload (jsonb)
  occurred_at
  INDEX(organization_id, event_type, occurred_at)

audit_logs
  id (uuid, pk)
  organization_id (fk, nullable)
  actor_user_id (fk, nullable)
  action, entity_type, entity_id
  metadata (jsonb)
  created_at
```

Entity relationships: `organizations 1—1 business_settings`,
`organizations 1—N phone_numbers/leads/conversations/workflow_runs`,
`users N—N organizations` via `memberships`, `conversations 1—N messages`,
`leads 1—N conversations`, `event_log 1—N workflow_runs` (a workflow run is
always caused by exactly one triggering event, though it may consume more
events as it progresses — modeled via `workflow_runs.state`, not new FKs).

`event_log` is intentionally a durable table, not just an in-memory pub/sub
channel: it's the audit trail for "what happened and when" across the whole
platform, and it's what lets a future subscriber (analytics, a new
integration) backfill/replay history instead of only seeing events from the
moment it started listening.

---

## 4. Authentication Flow

Unchanged from v1:
- Email/password signup → email verification token (short-lived,
  single-use, stored hashed) → account active.
- JWT access token (~15 min TTL) + rotated refresh token (hashed in DB,
  revocable).
- JWT carries `user_id` only; org context resolved per-request via
  `X-Org-Id` header/path param, validated against `memberships` every
  request — avoids stale-token problems on membership changes.
- Password hashing: argon2id.
- Calendar/CRM OAuth are per-organization integration credentials, not
  identity-provider concerns.

---

## 5. Tenant Isolation Strategy

Unchanged from v1: shared database, shared schema, `organization_id` on
every tenant-owned row, enforced at the repository layer via a
`TenantScopedRepository` base class and a `get_current_org` FastAPI
dependency validated against `memberships`. Postgres RLS added as
defense-in-depth once stable (v1.1). Twilio webhooks resolve tenant by
looking up the *receiving* number in `phone_numbers` — critical now that
that table has two connection types (§3, §17a): a forwarded call arrives on
the Twilio-side number regardless of which real business number the
customer publishes, so tenant resolution logic doesn't change based on
`connection_type`, only how the number got there.

Event log and workflow_runs are tenant-scoped the same way — no event bus
subscriber gets to bypass tenant scoping just because it operates on
"events" rather than "requests."

---

## 6. Configuration System

Unchanged principle, extended surface:
- Business settings (hours, services, tone, notifications) — structured
  JSONB + typed columns, dashboard CRUD, zero deploys.
- `PromptService` composes the AI extraction prompt from a versioned base
  template + tenant overrides, using constrained Jinja2 (autoescape, no
  arbitrary code execution).
- **Workflow definitions are configuration, not code branches.** A workflow
  (§17) is a declarative sequence of steps + conditions; industry
  differences (e.g. "always ask about emergency availability" vs. not) are
  expressed as workflow config parameters read from `business_settings`,
  not new Python branches per industry.
- Feature flags per org (voice AI, CRM sync) — JSONB/table-driven.
- Platform-level config (Twilio account, OpenAI keys, default templates,
  event bus backend choice) from environment/secrets manager only.

Rule of thumb: if a new industry requires a new `if industry == "plumbing"`
branch anywhere outside seed data, that's a design smell.

---

## 7. API Routes (MVP surface)

```
POST   /api/v1/auth/signup
POST   /api/v1/auth/verify-email
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout

POST   /api/v1/organizations
GET    /api/v1/organizations/{org_id}
PATCH  /api/v1/organizations/{org_id}

GET    /api/v1/organizations/{org_id}/business-settings
PUT    /api/v1/organizations/{org_id}/business-settings

# Phone number onboarding — dual path (§17a)
POST   /api/v1/organizations/{org_id}/phone-numbers/forward   # start forwarding-connect flow
POST   /api/v1/organizations/{org_id}/phone-numbers/provision # provision a new Twilio number
GET    /api/v1/organizations/{org_id}/phone-numbers
GET    /api/v1/organizations/{org_id}/phone-numbers/{id}/forwarding-instructions
POST   /api/v1/organizations/{org_id}/phone-numbers/{id}/verify-forwarding

GET    /api/v1/organizations/{org_id}/leads
GET    /api/v1/organizations/{org_id}/leads/{lead_id}
PATCH  /api/v1/organizations/{org_id}/leads/{lead_id}

GET    /api/v1/organizations/{org_id}/conversations/{id}

GET    /api/v1/organizations/{org_id}/workflow-runs/{id}     # transparency into
                                                               # in-flight automation

POST   /api/v1/webhooks/twilio/voice-status
POST   /api/v1/webhooks/twilio/sms-inbound

GET    /api/v1/health
```

All non-webhook, non-auth routes require `X-Org-Id` + JWT validated against
`memberships`. Webhook routes validate Twilio's request signature instead.

---

## 8. Service Layer

- `AuthService`, `OrganizationService`, `BusinessSettingsService` — as v1.
- `PhoneNumberService` — owns both onboarding paths: initiating Twilio
  provisioning, and generating/validating forwarding setup (carrier-specific
  forwarding codes, verification calls) for the "connect your existing
  number" path (§17a).
- `TwilioService` — thin I/O wrapper: validate webhook signature, provision
  numbers, send SMS. No business logic, no decisions.
- `PromptService` / `AIExtractionService` (in `app/ai/`) — composes prompt,
  calls OpenAI Responses API with a JSON-schema response format, returns a
  validated Pydantic object. Never decides what happens with the result.
- `WorkflowEngine` (in `app/workflows/`) — the only service that reacts to
  events and produces decisions/side effects (§17).
- `NotificationService` — sends owner notifications, reads
  `notification_preferences`, provider-agnostic interface.
- `EventBus` (in `app/events/`) — publish/subscribe abstraction (§16).

Dependency injection via FastAPI's `Depends` for request-scoped services;
constructor injection inside workers/event handlers.

---

## 9. Background Job Architecture

**Queue: `arq` + Redis, behind a `QueueClient` protocol** so Celery (or
anything else) can be substituted without touching call sites:

```python
# app/queue/interface.py
class QueueClient(Protocol):
    async def enqueue(self, task_name: str, *args, **kwargs) -> str: ...
    async def enqueue_at(self, task_name: str, when: datetime, *args, **kwargs) -> str: ...
```

`app/queue/arq_backend.py` implements this against arq; services and event
handlers depend only on `QueueClient`, injected via settings/DI — never
import `arq` directly outside that one module. Swapping to Celery later
means writing `celery_backend.py` and changing one binding, not touching
workflow or service code.

Jobs (now invoked primarily by event-bus subscribers, not called directly by
webhooks — see §16):
- `handle_missed_call(org_id, call_sid)` — idempotency key `call_sid`
  (unique constraint).
- `process_inbound_sms(org_id, message_sid, body, from_number)` —
  idempotency key `provider_message_sid` (unique constraint on `messages`).
- `run_workflow_step(workflow_run_id, event_id)` — advances a
  `workflow_runs` state machine (§17).
- `send_notification(org_id, lead_id, channel)`.

Retry policy: exponential backoff, max 3 attempts, dead-letter queue with
alerting — a failed qualification/workflow job must not silently drop a
lead.

---

## 10. Idempotency & Reliability Notes

Unchanged from v1: webhook handlers are fast + idempotent "record, publish
event, return 200." Unique constraints (`call_sid`, `provider_message_sid`)
are the actual guarantee. `workflow_runs.state` persists after every step so
a crash mid-workflow resumes rather than restarts. `event_log` gives full
replayability — if a subscriber had a bug and needs to reprocess a window of
events, that's a query + republish, not data recovery.

---

## 11. Deployment Architecture — Render (initial), portable by design

- Monorepo, three deployable units from one repo: `apps/api` (web service),
  a worker process (same image as API, `arq worker` entrypoint instead of
  `uvicorn`), and `apps/web` (Next.js, separate Render web service).
- `render.yaml` blueprint defines: API web service, worker background
  service (same Docker image, different start command), Next.js web
  service, managed Postgres, managed Redis (Render Key Value) — one file,
  reproducible environments (preview apps get their own via Render's PR
  previews).
- Portability constraint: nothing in application code references
  Render-specific APIs. Postgres/Redis are reached via standard connection
  strings (`DATABASE_URL`, `REDIS_URL`) injected as env vars — moving to AWS
  (RDS + ElastiCache) or anywhere else is a `render.yaml` → Terraform/ECS
  task-def swap, not a code change. The `QueueClient` abstraction (§9)
  means even the queue backend itself isn't a lock-in point.
- Migrations via Alembic as a Render "pre-deploy" release command — never
  auto-migrate on app boot.
- Secrets via Render's environment/secret groups; same variable names
  locally via `.env` for `docker-compose`.
- Twilio webhook URLs point at the Render-assigned (or custom) API domain;
  local dev uses a tunnel for webhook testing.

---

## 12. Monitoring and Logging

Unchanged from v1, with one addition: `event_log` doubles as a
platform-level observability primitive — "show me every event for org X in
the last hour" is a debugging tool independent of application log lines.
Structured JSON logs still carry `org_id`, `request_id`, and now
`workflow_run_id`/`event_id` where applicable, so tracing a lead from missed
call through notification is a single correlated query. Alerting adds:
workflow runs stuck in `waiting_on_reply`/`running` past an expected
duration (signal of a stalled workflow step or a downstream integration
outage).

---

## 13. Testing Strategy

Unchanged core strategy (unit/integration/contract/tenant-isolation), with
the workflow-engine split making the highest-value tests cheaper:
- **Workflow engine tests are pure unit tests** — given a workflow
  definition, a starting event, and a sequence of (mocked) extraction
  results, assert the exact sequence of decisions/side effects, with zero
  OpenAI or Twilio calls. This is now the primary place business-logic bugs
  are caught, and it's fast and deterministic by construction.
- **AI extraction tests** assert schema conformance and mapping from raw
  model output to the Pydantic contract — mocked OpenAI responses, no live
  calls in CI.
- **Event bus tests**: publishing an event triggers all registered
  subscribers exactly once; a subscriber failure doesn't prevent others
  from running (isolation between subscribers).
- Tenant-isolation tests remain first-class, extended to `event_log` and
  `workflow_runs`.

---

## 14. Future Scaling Strategy

Unchanged from v1 in substance (voice AI, CRM, calendar, Stripe, RBAC,
white-labeling, API access, horizontal scale) — all of it slots into the
event bus/workflow engine even more cleanly than the original chatbot
design:
- A new integration (CRM, calendar) is a new **event subscriber**, not a
  change to existing workflow logic — "on `lead.qualified`, push to CRM" is
  additive.
- Voice AI is a new event source (`call.transcribed`) feeding the same
  extraction contract and the same workflow engine.
- Multi-agent / multi-industry support becomes multiple workflow
  *definitions* selectable per organization, not new prompts or new
  services.
- When scale eventually justifies it, the event bus backend swaps from
  in-process/Postgres-durable to Redis pub/sub or a real broker (§16)
  without changing any publisher or subscriber code, since they only ever
  depend on the `EventBus` interface.

---

## 15. Decisions (resolved)

1. **Job queue**: `arq` + Redis, behind a `QueueClient` abstraction (§9).
2. **Phone numbers**: dual-path (§17a) — forwarding-connect is the primary
   onboarding flow, Twilio provisioning is an equally supported optional
   path; both converge on the same `phone_numbers` model and the same
   inbound-webhook handling.
3. **OpenAI usage**: Responses API, structured JSON-schema outputs only
   (§17b). The AI layer never makes decisions — only extracts/classifies.
4. **Repo/stack**: monorepo, `apps/api` (FastAPI) + `apps/web` (Next.js) +
   `packages/shared` for generated types and shared config.
5. **Hosting**: Render for launch (managed Postgres + Redis), with explicit
   portability constraints (§11) so AWS/other-cloud migration is
   infra-config work, not application rework.
6. **Event bus**: internal typed event bus from day one (§16), durable via
   `event_log`, in-process pub/sub initially with a swappable backend.
7. **Workflow engine**: business logic lives in declarative workflow
   definitions (§17), not in the AI layer or scattered service methods.

---

## 16. Event Bus

Every major action emits a typed, versioned event. Two responsibilities are
kept separate on purpose: **publishing** (fire-and-forget from the
originator's point of view) and **durability + fan-out** (the bus's job).

```python
# app/events/types.py
class MissedCallDetected(BaseEvent):
    organization_id: UUID
    phone_number_id: UUID
    caller_number: str
    call_sid: str

class SMSSent(BaseEvent):
    organization_id: UUID
    conversation_id: UUID
    message_sid: str

class MessageReceived(BaseEvent):
    organization_id: UUID
    conversation_id: UUID
    body: str
    provider_message_sid: str

class LeadQualified(BaseEvent):
    organization_id: UUID
    lead_id: UUID
    classification: Literal["new_lead", "existing_customer", "emergency", "spam"]

class AppointmentRequested(BaseEvent):
    organization_id: UUID
    lead_id: UUID
    preferred_time: datetime | None
```

- `EventBus.publish(event)`: (1) writes the event to `event_log`
  (durability/audit/replay — §3), (2) dispatches to in-process subscribers
  synchronously registered for that event type, each subscriber wrapped so
  one subscriber's exception can't block others or the publisher.
- Subscribers are typically thin: "on `MissedCallDetected`, enqueue
  `handle_missed_call`" or "on `LeadQualified`, enqueue `send_notification`."
  The workflow engine itself is the primary subscriber for the events that
  drive multi-step flows (§17).
- MVP transport: in-process, synchronous dispatch within the request/worker
  process — no new infra required, and `event_log` already gives durability
  and replay. This satisfies "typed events downstream services can
  subscribe to" without over-building for day one.
- Scaling path: swap the in-process dispatcher for Redis pub/sub (already in
  the stack) or a broker (SNS/SQS, NATS) once a subscriber needs to run in a
  genuinely separate process/service — the `EventBus` interface
  (`publish`/`subscribe`) doesn't change, only its implementation, mirroring
  the `QueueClient` pattern in §9.
- Every event is versioned (`event_type` string embeds a version, e.g.
  `lead.qualified.v1`) so schema evolution doesn't break historical
  `event_log` rows or slow subscribers.

---

## 17. Workflow Engine

The workflow engine is the deterministic decision layer. It subscribes to
domain events and drives named, declarative workflows; it is the only place
where "what happens next" is decided, and the only place allowed to cause
side effects (send SMS, notify, create appointment, update lead status).

```python
# app/workflows/definitions/missed_call_recovery.py
MISSED_CALL_RECOVERY = WorkflowDefinition(
    name="missed_call_recovery",
    trigger=MissedCallDetected,
    steps=[
        SendInitialSMS(template="ai_tone_greeting"),
        AwaitReply(timeout_minutes=30, on_timeout="mark_unresponsive"),
        ExtractLeadInfo(),               # calls AI extraction layer, structured output only
        Branch(
            condition="classification == 'emergency'",
            then=[NotifyOwner(urgent=True), MarkLeadStatus("qualified")],
            else_=[
                Branch(
                    condition="missing_fields",
                    then=[AskFollowUpQuestion()],   # loops back to AwaitReply
                    else_=[NotifyOwner(), MarkLeadStatus("qualified"),
                           MaybeRequestAppointment()],
                ),
            ],
        ),
    ],
)
```

- **Definition, not code branch, per business rule.** Whether emergency
  handling applies at all, which follow-up questions to ask, and how many
  retries before giving up are workflow *parameters*, sourced from
  `business_settings` (e.g. `emergency_service_enabled`), not new Python
  `if` branches — same "config replaces code" principle as §6, applied to
  business process instead of just business data.
- Each `workflow_runs` row tracks current step + accumulated data in
  `state` (jsonb), so a reply arriving hours later resumes the exact step
  rather than restarting (this is what `AwaitReply` relies on).
- The engine calls the AI extraction layer as a **step**, never inline logic
  — `ExtractLeadInfo()` calls `AIExtractionService`, gets back a validated
  Pydantic object, and only the *workflow* decides what that means for
  lead status, notifications, or next questions.
- New workflows (voice AI intake, a different industry's qualification
  flow) are new `WorkflowDefinition`s selected per organization — the engine
  itself doesn't change.
- Advancing a workflow step happens via the job queue (`run_workflow_step`,
  §9), keeping the event-handling path fast and retryable.

### 17a. Phone Number Onboarding — Dual Path

Primary path (**call/missed-call forwarding**, default in onboarding UI):
1. Customer enters their existing business number.
2. `PhoneNumberService` provisions (or reuses a pool of) a Twilio-side
   number as the forwarding target and generates carrier-specific
   forwarding instructions (conditional call forwarding on no-answer/busy —
   the customer's phone still rings first; only unanswered calls forward).
3. `phone_numbers` row created with `connection_type='forwarded'`,
   `business_number` = their real number, `e164_number` = the Twilio-side
   number, `forwarding_status='pending_verification'`.
4. Dashboard walks the customer through carrier-specific dial codes (e.g.
   `*61*<twilio_number>#` patterns per carrier — a config-driven lookup
   table, not hardcoded per customer).
5. `POST .../verify-forwarding` places a test call (or waits for the first
   real forwarded call) to confirm the forward is live; flips
   `forwarding_status` to `verified`.

Optional path (**Twilio-provisioned number**):
1. Customer picks/searches an available number via Twilio's number
   search API.
2. `PhoneNumberService` purchases it via Twilio API,
   `connection_type='twilio_provisioned'`, `status='active'` once
   webhooks are configured.
3. Customer is instructed to publish this number as their business line
   (or set up their own forwarding to it) — simpler backend, more change
   for the customer's existing marketing/signage.

Both paths converge immediately after provisioning: Twilio only ever calls
our webhooks against the `e164_number` on the `phone_numbers` row, so
`handle_missed_call`/`process_inbound_sms` and everything in §17 are
completely agnostic to `connection_type`. The only thing that differs is
the onboarding UX and which instructions/verification step run first.

### 17b. AI Extraction Layer — OpenAI Responses API

- Every call to OpenAI uses the **Responses API** with a `response_format`
  bound to a versioned JSON schema (Pydantic model → JSON schema), e.g.
  `LeadExtractionResult(name, service_requested, location, urgency,
  preferred_time, classification, missing_fields)`.
- `AIExtractionService.extract(conversation_history, org_context) ->
  LeadExtractionResult` is the entire public surface — deterministic in the
  sense that its *output shape* is always schema-valid (SDK-level parsing
  failure is a hard error, not silently swallowed), even though model
  content itself is inherently non-deterministic token-to-token.
- The service never triggers side effects, never writes to `leads` or
  `conversations` directly, and never decides classification-driven
  behavior — it hands the validated object back to whichever workflow step
  called it.
- Schema versioning lives next to event versioning (§16): a schema change is
  a new Pydantic model version, old `workflow_runs.state` blobs remain
  parseable against the schema version they were created with.

---

## Next Step

This revision incorporates all seven decisions. Please confirm before I
scaffold the monorepo (§2), initial Alembic migrations (§3), the event bus +
workflow engine skeleton (§16–17), and the missed-call → SMS →
qualification → notification happy path end to end, targeting the
forwarding-connect onboarding path first since it's the primary flow.

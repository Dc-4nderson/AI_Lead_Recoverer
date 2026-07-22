# AI Lead Recovery Platform

Multi-tenant SaaS that recovers missed-call leads: a business misses a call,
Twilio notifies us, and within seconds an AI assistant texts the caller,
qualifies the lead through a deterministic workflow, and notifies the owner.

> **Architecture first.** See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full
> design (multi-tenancy, event bus, workflow engine, config-over-code, scaling
> path). This README covers the code layout and how to run it.

## Core design in one paragraph

The **AI layer only extracts and classifies** — text in, schema-validated JSON
out (OpenAI Responses API). It never decides anything. A deterministic
**workflow engine** owns every decision and side effect (send SMS, notify,
qualify), driven by a typed **event bus**. This makes business logic
unit-testable without ever calling OpenAI or Twilio, and makes new integrations
(CRM, calendar, voice) additive event subscribers rather than rewrites.

## Monorepo layout

```
apps/
  api/     FastAPI backend (modular monolith): events, workflows, ai, queue, services
  web/     Next.js dashboard (typed API client)
packages/
  shared/  TypeScript types mirroring the backend Pydantic schemas
render.yaml         Render blueprint (api + worker + web + Postgres + Redis)
docker-compose.yml  Local dev stack
```

Backend request path: `router → service/workflow → repository`. Nothing skips a
layer; the workflow engine is the only place side effects happen.

## Running locally

Prerequisites: Docker (+ Compose). Copy env and start the stack:

```bash
cp .env.example .env          # fill in Twilio / OpenAI keys for live behavior
docker compose up --build
```

This starts Postgres, Redis, the API (`:8000`), the arq worker, and the web app
(`:3000`). Run migrations once the DB is up:

```bash
docker compose exec api alembic upgrade head
```

API docs: http://localhost:8000/docs · Dashboard: http://localhost:3000

### Backend without Docker

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload            # API
arq app.queue.arq_backend.WorkerSettings # worker (separate shell)
pytest                                   # tests
```

## The missed-call → qualified-lead flow

1. Twilio `voice-status` webhook fires on a missed call → handler validates the
   signature, resolves the tenant by the **receiving** number, publishes
   `MissedCallDetected`.
2. An event subscriber enqueues `handle_missed_call`, which creates the
   lead/conversation/workflow-run and starts `missed_call_recovery`, sending the
   first SMS within the 30s SLA.
3. Caller replies → `sms-inbound` webhook publishes `MessageReceived` →
   `process_inbound_sms` stores the message and resumes the workflow.
4. The workflow calls the AI extraction step, decides (ask a follow-up, or
   qualify), and on qualification emits `LeadQualified` — whose subscriber
   notifies the owner. Adding a CRM push later is just another subscriber.

## Phone number onboarding (dual path)

- **Forwarding (primary):** connect an existing business number via
  conditional call forwarding; unanswered calls forward to a Twilio-side number.
- **Twilio-provisioned (optional):** provision a fresh number.

Both converge on the same webhook handling — the workflow is agnostic to how the
number was connected.

## Workflow Simulator (Developer Tools)

`Developer Tools → Workflow Simulator` (`/dev-tools/simulator` in the
dashboard) drives the exact production backend — real event bus, real
workflow engine, real AI extraction contract, real repositories, real
database — with only Twilio/Redis/OpenAI transport swapped for synthetic
events, inline execution, and (by default) a deterministic mock AI client.
Use it to:

- Run a full missed-call → SMS → qualify → notify flow with no Twilio call
  and no OpenAI cost (toggle "use real AI" to hit OpenAI for real).
- Watch the event bus, workflow steps, queue jobs, AI extraction I/O, and
  every DB row created/changed, on one timeline.
- Step through a paused workflow one engine step at a time.
- Replay any generated event through the real event bus.
- Save/load reusable scenarios (Emergency Plumbing, Spam Caller, etc.).

To connect: sign up via `/auth/signup`, paste the returned access token into
the simulator's Connection panel, then click "Look up my organizations" (uses
`GET /organizations`) to pick the org to simulate against.

See `ARCHITECTURE.md` §18 for the design (what's swapped vs. real, and why).

## Tests

`apps/api/tests/` — the workflow engine and event bus have deterministic unit
tests (no external calls). Tenant-isolation and integration tests are the next
layer to build out (see `ARCHITECTURE.md` §13).

## Deployment

`render.yaml` provisions the API, worker, web app, managed Postgres, and managed
Redis. Application code only reads `DATABASE_URL` / `REDIS_URL`, so migrating to
AWS or elsewhere is an infra-config change, not application rework.

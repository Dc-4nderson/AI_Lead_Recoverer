"""End-to-end simulator test against a real database.

Proves the simulator drives the REAL production flow (event bus → inline queue →
same task functions → workflow engine → AI extraction → repositories → DB →
more events) with only Twilio/OpenAI transport swapped. Requires a Postgres
reachable via DATABASE_URL; skipped otherwise so the fast unit suite is unaffected.
"""
from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    "postgresql" not in os.getenv("DATABASE_URL", ""),
    reason="requires a Postgres DATABASE_URL",
)


async def _seed_org(session) -> uuid.UUID:
    from app.models import Organization

    org = Organization(name="Sim Test Co", industry="plumbing")
    session.add(org)
    await session.flush()
    org_id = org.id
    await session.commit()
    return org_id


@pytest.mark.asyncio
async def test_full_missed_call_recovery_simulation():
    from app.core.db import SessionFactory
    from app.simulator.runner import SimulationRunner

    async with SessionFactory() as session:
        org_id = await _seed_org(session)

    async with SessionFactory() as session:
        runner = SimulationRunner(session, org_id)
        result = await runner.run(
            workflow="missed_call_recovery",
            caller_number="+15551234567",
            business_number=f"+1555{uuid.uuid4().int % 10_000_000:07d}",
            conversation_turns=["I need emergency plumbing at 123 Main St ASAP"],
            use_real_ai=False,
        )

    trace = result["trace"]
    event_types = [e["event_type"] for e in trace["events"]]
    step_names = [s["step"] for s in trace["workflow_steps"]]
    job_names = [j["task_name"] for j in trace["queue_jobs"]]
    db_tables = {c["table"] for c in trace["db_changes"]}

    # The real event chain travelled through the real bus.
    assert "missed_call.detected.v1" in event_types
    assert "message.received.v1" in event_types
    assert "lead.qualified.v1" in event_types

    # The real workflow engine executed real steps.
    assert "SendInitialSMS" in step_names
    assert "ExtractLeadInfo" in step_names
    assert "QualifyAndRoute" in step_names

    # The SAME task functions ran (inline, via the QueueClient interface).
    assert "handle_missed_call" in job_names
    assert "process_inbound_sms" in job_names
    assert "send_notification" in job_names
    assert all(j["status"] == "completed" for j in trace["queue_jobs"])

    # Real repositories wrote real rows.
    assert {"leads", "conversations", "workflow_runs", "event_log"} <= db_tables

    # AI extraction was exposed (mock client), classified emergency.
    assert trace["ai_calls"], "expected an AI extraction record"
    assert trace["ai_calls"][0]["schema_version"] == "lead_extraction.v1"

    # Outbound SMS captured, not sent to Twilio.
    assert any(s["sms_kind"] == "outbound_sms" for s in trace["sms"])

    # Final workflow state reflects qualification.
    run = result["workflow_run"]
    assert run is not None
    assert run["state"].get("qualified") is True
    assert result["lead"]["classification"] == "emergency"

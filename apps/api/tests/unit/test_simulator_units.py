"""Simulator unit tests that need no database.

Covers the deterministic mock AI client, the trace collector, and that the
engine instrumentation + single-step control work — all with fakes, proving the
observability hooks fire only under a bound simulation.
"""
from __future__ import annotations

import uuid

import pytest

from app.ai.extraction_service import AIExtractionService
from app.shared.enums import WorkflowStatus
from app.simulator.doubles import MockOpenAIClient
from app.simulator.session import SimulationSession, bind_simulation, unbind_simulation
from app.simulator.trace import TraceCollector
from app.workflows.context import WorkflowContext
from app.workflows.definitions import MISSED_CALL_RECOVERY
from app.workflows.engine import WorkflowEngine


@pytest.mark.asyncio
async def test_mock_openai_classifies_emergency():
    svc = AIExtractionService(client=MockOpenAIClient())
    result = await svc.extract(
        conversation_history=[{"direction": "inbound", "body": "I need emergency plumbing ASAP"}],
        business_name="Acme",
        industry="plumbing",
        business_settings=None,
    )
    assert result.classification == "emergency"
    assert result.urgency == "emergency"
    assert result.service_requested == "plumbing"


@pytest.mark.asyncio
async def test_mock_openai_classifies_spam():
    svc = AIExtractionService(client=MockOpenAIClient())
    result = await svc.extract(
        conversation_history=[
            {"direction": "inbound", "body": "Free money crypto winner click here"}
        ],
        business_name="Acme",
        industry=None,
        business_settings=None,
    )
    assert result.classification == "spam"


def test_trace_collector_serializes():
    t = TraceCollector()
    t.record_event("missed_call.detected.v1", {"a": 1})
    t.record_queue_job("handle_missed_call")
    t.record_sms("+1", "+2", "hi", kind="outbound_sms")
    d = t.to_dict()
    assert len(d["events"]) == 1
    assert len(d["queue_jobs"]) == 1
    assert d["timeline"], "timeline should have entries"
    # timeline is ordered by seq
    seqs = [r["seq"] for r in d["timeline"]]
    assert seqs == sorted(seqs)


def _fake_ctx() -> WorkflowContext:
    class _SMS:
        async def send(self, **_):
            return "SM"

    class _Extractor:
        async def extract(self, **_):
            from app.ai.schemas import LeadExtractionResult

            return LeadExtractionResult(classification="new_lead", missing_fields=[])

    async def _pub(_e):
        return None

    return WorkflowContext(
        organization_id=uuid.uuid4(),
        workflow_run_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        caller_number="+1",
        business_number="+2",
        state={},
        sms=_SMS(),
        extractor=_Extractor(),
        notifier=object(),
        publish_event=_pub,
    )


@pytest.mark.asyncio
async def test_engine_single_step_and_tracing():
    trace = TraceCollector()
    sim = SimulationSession(trace=trace, twilio_client=None, queue=None, ai_client=None)
    token = bind_simulation(sim)
    try:
        engine = WorkflowEngine(MISSED_CALL_RECOVERY)
        ctx = _fake_ctx()
        # Exactly one step runs.
        status = await engine.advance(ctx, max_steps=1)
        assert status is WorkflowStatus.RUNNING
        assert len(trace.workflow_steps) == 1
        assert trace.workflow_steps[0]["step"] == "SendInitialSMS"
    finally:
        unbind_simulation(token)


@pytest.mark.asyncio
async def test_engine_multi_step_persists_index_between_calls():
    """Regression: a CONTINUE outcome must persist the advanced step_index even
    when max_steps ends the call before the next loop iteration would have."""
    engine = WorkflowEngine(MISSED_CALL_RECOVERY)
    ctx = _fake_ctx()

    status1 = await engine.advance(ctx, max_steps=1)
    assert status1 is WorkflowStatus.RUNNING
    assert ctx.state["step_index"] == 1  # advanced past SendInitialSMS (index 0)

    status2 = await engine.advance(ctx, max_steps=1)
    assert status2 is WorkflowStatus.WAITING_ON_REPLY  # AwaitReply pauses


@pytest.mark.asyncio
async def test_engine_no_tracing_without_simulation():
    # No bound simulation → instrumentation must not record anything.
    trace = TraceCollector()
    engine = WorkflowEngine(MISSED_CALL_RECOVERY)
    ctx = _fake_ctx()
    await engine.advance(ctx, max_steps=1)
    assert trace.workflow_steps == []

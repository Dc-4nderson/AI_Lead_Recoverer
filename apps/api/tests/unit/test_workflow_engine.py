"""Workflow engine unit tests (§13).

The whole point of the AI-extraction / workflow-engine split: business logic is
tested deterministically with fakes, zero OpenAI or Twilio calls. These assert
the exact sequence of decisions/side effects the engine produces.
"""
from __future__ import annotations

import uuid

import pytest

from app.ai.schemas import LeadExtractionResult
from app.events.types import LeadQualified
from app.shared.enums import WorkflowStatus
from app.workflows.context import WorkflowContext
from app.workflows.definitions import MISSED_CALL_RECOVERY
from app.workflows.engine import WorkflowEngine


class FakeSMS:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, *, to_number: str, from_number: str, body: str) -> str:
        self.sent.append(body)
        return "SM_fake"


class FakeExtractor:
    def __init__(self, result: LeadExtractionResult) -> None:
        self.result = result

    async def extract(self, *, conversation_id: uuid.UUID) -> LeadExtractionResult:
        return self.result


class FakeNotifier:
    async def notify_owner(self, **_: object) -> None:  # pragma: no cover - unused now
        ...


def make_ctx(extraction: LeadExtractionResult, published: list) -> WorkflowContext:
    async def publish(event) -> None:
        published.append(event)

    return WorkflowContext(
        organization_id=uuid.uuid4(),
        workflow_run_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        caller_number="+15551230000",
        business_number="+15559990000",
        state={},
        sms=FakeSMS(),
        extractor=FakeExtractor(extraction),
        notifier=FakeNotifier(),
        publish_event=publish,
    )


@pytest.mark.asyncio
async def test_missed_call_pauses_after_initial_sms():
    engine = WorkflowEngine(MISSED_CALL_RECOVERY)
    ctx = make_ctx(LeadExtractionResult(), published=[])

    status = await engine.advance(ctx)

    assert status is WorkflowStatus.WAITING_ON_REPLY
    assert ctx.sms.sent == ["Hi! Sorry we missed your call. How can we help you today?"]
    assert ctx.state["initial_sms_sent"] is True


@pytest.mark.asyncio
async def test_qualified_lead_completes_and_emits_event():
    engine = WorkflowEngine(MISSED_CALL_RECOVERY)
    published: list = []
    ctx = make_ctx(
        LeadExtractionResult(
            name="Jane", service_requested="drain cleaning",
            location="123 Main St", urgency="normal",
            classification="new_lead", missing_fields=[],
        ),
        published,
    )

    # Phase 1: initial SMS, then pause.
    await engine.advance(ctx)
    # Phase 2: a reply arrived — resume.
    ctx.state["resumed"] = True
    status = await engine.advance(ctx)

    assert status is WorkflowStatus.COMPLETED
    assert ctx.state["qualified"] is True
    assert len(published) == 1
    assert isinstance(published[0], LeadQualified)
    assert published[0].classification == "new_lead"


@pytest.mark.asyncio
async def test_missing_fields_asks_followup_and_pauses():
    engine = WorkflowEngine(MISSED_CALL_RECOVERY)
    ctx = make_ctx(
        LeadExtractionResult(
            name=None, missing_fields=["name"],
            suggested_reply="What's your name?", classification="new_lead",
        ),
        published=[],
    )

    await engine.advance(ctx)
    ctx.state["resumed"] = True
    status = await engine.advance(ctx)

    assert status is WorkflowStatus.WAITING_ON_REPLY
    assert "What's your name?" in ctx.sms.sent
    # Looped back to the AwaitReply step, not past it.
    assert ctx.state["step_index"] == ctx.state["await_step_index"]

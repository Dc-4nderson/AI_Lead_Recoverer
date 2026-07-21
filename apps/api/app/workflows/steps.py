"""Reusable, deterministic workflow steps (§17).

Every step is a small unit that either advances the run, pauses it (waiting on
a caller reply), or completes it. Steps are the ONLY place side effects happen,
and they cause them through injected collaborators on WorkflowContext — so the
same step is exercised in tests with fakes.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol

from app.events.types import LeadQualified
from app.workflows.context import WorkflowContext


class Outcome(Enum):
    CONTINUE = auto()   # proceed to the next step
    PAUSE = auto()      # persist state, wait for an external event (a reply)
    COMPLETE = auto()   # workflow finished


class Step(Protocol):
    async def run(self, ctx: WorkflowContext) -> Outcome: ...  # pragma: no cover


@dataclass
class SendInitialSMS:
    """First contact within the 30s SLA. Template resolved from tenant tone."""

    body: str = "Hi! Sorry we missed your call. How can we help you today?"

    async def run(self, ctx: WorkflowContext) -> Outcome:
        if ctx.state.get("initial_sms_sent"):
            return Outcome.CONTINUE
        sid = await ctx.sms.send(
            to_number=ctx.caller_number, from_number=ctx.business_number, body=self.body
        )
        ctx.state["initial_sms_sent"] = True
        ctx.state["last_outbound_sid"] = sid
        return Outcome.CONTINUE


@dataclass
class AwaitReply:
    """Pause until a MessageReceived event resumes the run. On resume, the
    engine sets state['resumed'] = True so this step falls through."""

    timeout_minutes: int = 30

    async def run(self, ctx: WorkflowContext) -> Outcome:
        if ctx.state.pop("resumed", False):
            return Outcome.CONTINUE
        return Outcome.PAUSE


@dataclass
class ExtractLeadInfo:
    """Calls the AI extraction layer as a step — never inline logic. The result
    is data; the following steps decide what it means."""

    async def run(self, ctx: WorkflowContext) -> Outcome:
        ctx.last_extraction = await ctx.extractor.extract(conversation_id=ctx.conversation_id)
        ctx.state["extraction"] = ctx.last_extraction.model_dump(mode="json")
        return Outcome.CONTINUE


@dataclass
class QualifyAndRoute:
    """Deterministic decision layer: given the extraction, decide whether to ask
    a follow-up, or finish by emitting LeadQualified.

    Side effects the owner cares about (notify, CRM push) happen via subscribers
    to LeadQualified (§16) — NOT inline here — so adding an integration is
    additive and this step stays a pure decision + one event emission."""

    async def run(self, ctx: WorkflowContext) -> Outcome:
        extraction = ctx.last_extraction
        if extraction is None:
            return Outcome.PAUSE

        is_emergency = extraction.classification == "emergency"
        still_missing = extraction.missing_fields and not is_emergency

        if still_missing:
            question = extraction.suggested_reply or (
                f"Got it — could you tell me your {extraction.missing_fields[0].replace('_', ' ')}?"
            )
            await ctx.sms.send(
                to_number=ctx.caller_number, from_number=ctx.business_number, body=question
            )
            # Loop back to awaiting another reply.
            ctx.state["step_index"] = ctx.state["await_step_index"]
            return Outcome.PAUSE

        # Qualified (or emergency): record the outcome and emit the event. The
        # runtime persists extraction → Lead; subscribers handle notification.
        ctx.state["qualified"] = True
        if ctx.lead_id is not None:
            await ctx.publish_event(
                LeadQualified(
                    organization_id=ctx.organization_id,
                    lead_id=ctx.lead_id,
                    classification=extraction.classification or "new_lead",
                )
            )
        return Outcome.COMPLETE

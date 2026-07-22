"""SimulationRunner — orchestrates production components via synthetic events.

It binds a SimulationSession (trace + I/O doubles), then drives the flow purely
by publishing real domain events through the real event bus. Everything
downstream — handlers, inline queue, the SAME task functions, the workflow
engine, AI extraction, repositories, the database — is production code.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.bus import event_bus
from app.events.types import MessageReceived, MissedCallDetected
from app.models import BusinessSettings, Conversation, Lead, PhoneNumber, WorkflowRun
from app.repositories.repositories import (
    ConversationRepository,
    PhoneNumberRepository,
)
from app.shared.enums import ConnectionType, PhoneStatus
from app.simulator.doubles import InlineQueueClient, MockOpenAIClient, SimulatedTwilioClient
from app.simulator.session import SimulationSession, bind_simulation, unbind_simulation
from app.simulator.trace import TraceCollector


class SimulationRunner:
    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self.session = session
        self.org_id = organization_id

    async def run(
        self,
        *,
        workflow: str,
        caller_number: str,
        business_number: str,
        conversation_turns: list[str],
        use_real_ai: bool = False,
        business_settings_overrides: dict | None = None,
    ) -> dict[str, Any]:
        trace = TraceCollector()
        ai_client = None if use_real_ai else MockOpenAIClient()
        sim = SimulationSession(
            trace=trace,
            twilio_client=SimulatedTwilioClient(trace),
            queue=InlineQueueClient(trace),
            ai_client=ai_client,
        )
        # Ensure event-bus subscribers are wired (idempotent). In the API process
        # this already ran at startup; calling again is safe and makes the runner
        # self-sufficient (e.g. in tests / scripts).
        from app.events.handlers import register_all_handlers

        register_all_handlers()

        token = bind_simulation(sim)
        try:
            # --- Simulator setup (not business logic): ensure org has a phone
            # number + optional business-settings overrides, committed so the
            # task functions' own sessions see them.
            phone = await self._ensure_phone_number(business_number)
            if business_settings_overrides:
                await self._apply_settings(business_settings_overrides)
            await self.session.commit()

            call_sid = f"CA_sim_{uuid.uuid4().hex[:16]}"

            # --- Entry event: identical to what the Twilio voice webhook emits.
            await event_bus.publish(
                MissedCallDetected(
                    organization_id=self.org_id,
                    phone_number_id=phone.id,
                    caller_number=caller_number,
                    call_sid=call_sid,
                )
            )

            # handle_missed_call ran inline and created the conversation.
            conversation = await self._find_conversation(call_sid)

            # --- Each customer message is a synthetic inbound SMS event, exactly
            # as the Twilio sms-inbound webhook would emit.
            for turn in conversation_turns:
                if conversation is None:
                    break
                await event_bus.publish(
                    MessageReceived(
                        organization_id=self.org_id,
                        conversation_id=conversation.id,
                        body=turn,
                        provider_message_sid=f"SM_in_{uuid.uuid4().hex[:16]}",
                    )
                )

            return await self._result(trace, call_sid, conversation)
        finally:
            unbind_simulation(token)

    # ----------------------------------------------------------------- setup
    async def _ensure_phone_number(self, business_number: str) -> PhoneNumber:
        repo = PhoneNumberRepository(self.session)
        existing = await repo.get_by_e164(business_number)
        if existing is not None and existing.organization_id == self.org_id:
            return existing
        phone = PhoneNumber(
            organization_id=self.org_id,
            connection_type=ConnectionType.FORWARDED,
            e164_number=business_number,
            business_number=business_number,
            status=PhoneStatus.ACTIVE,
        )
        return await repo.add(phone)

    async def _apply_settings(self, overrides: dict) -> None:
        row = (
            await self.session.execute(
                select(BusinessSettings).where(BusinessSettings.organization_id == self.org_id)
            )
        ).scalar_one_or_none()
        if row is None:
            row = BusinessSettings(organization_id=self.org_id)
            self.session.add(row)
        for key, value in overrides.items():
            if hasattr(row, key):
                setattr(row, key, value)

    # ----------------------------------------------------------------- reads
    async def _find_conversation(self, call_sid: str) -> Conversation | None:
        # A committed row from the inline task's own session; read fresh.
        await self.session.commit()
        return await ConversationRepository(self.session).get_by_call_sid(self.org_id, call_sid)

    async def _result(
        self, trace: TraceCollector, call_sid: str, conversation: Conversation | None
    ) -> dict[str, Any]:
        await self.session.commit()
        workflow_run = None
        lead = None
        if conversation is not None:
            workflow_run = (
                await self.session.execute(
                    select(WorkflowRun)
                    .where(WorkflowRun.conversation_id == conversation.id)
                    .order_by(WorkflowRun.created_at.desc())
                )
            ).scalars().first()
            if workflow_run and workflow_run.lead_id:
                lead = await self.session.get(Lead, workflow_run.lead_id)

        return {
            "call_sid": call_sid,
            "conversation_id": str(conversation.id) if conversation else None,
            "workflow_run": _run_snapshot(workflow_run),
            "lead": _lead_snapshot(lead),
            "trace": trace.to_dict(),
        }


def _run_snapshot(run: WorkflowRun | None) -> dict | None:
    if run is None:
        return None
    return {
        "id": str(run.id),
        "workflow_name": run.workflow_name,
        "status": run.status,
        "state": run.state,
    }


def _lead_snapshot(lead: Lead | None) -> dict | None:
    if lead is None:
        return None
    return {
        "id": str(lead.id),
        "name": lead.name,
        "service_requested": lead.service_requested,
        "classification": lead.classification,
        "urgency": lead.urgency,
        "status": lead.status,
    }

"""arq task functions (§9).

Tasks are thin: they own idempotency + persistence and delegate all logic to
the workflow engine. They are the primary consumers of the job queue, enqueued
by event-bus subscribers rather than called directly from webhooks.
"""
from __future__ import annotations

import logging
import uuid

from app.core.db import session_scope
from app.core.logging import bind_log_context
from app.events.handlers import register_all_handlers
from app.models import Conversation, Lead, Message, WorkflowRun
from app.repositories.repositories import (
    ConversationRepository,
    MessageRepository,
    PhoneNumberRepository,
)
from app.shared.enums import LeadStatus, MessageDirection, WorkflowStatus
from app.workflows.runtime import run_workflow

logger = logging.getLogger("queue.tasks")


async def startup(ctx: dict) -> None:
    # Worker process registers the same event-bus subscribers as the API (§16).
    register_all_handlers()
    logger.info("arq worker started")


async def shutdown(ctx: dict) -> None:
    logger.info("arq worker stopped")


async def handle_missed_call(
    ctx: dict,
    organization_id: str,
    phone_number_id: str,
    caller_number: str,
    call_sid: str,
) -> None:
    """Create the lead/conversation/workflow-run and kick off recovery.

    Idempotency key: call_sid — a conversation already carrying this call_sid
    means Twilio re-delivered; we no-op."""
    org_id = uuid.UUID(organization_id)
    bind_log_context(org_id=organization_id, call_sid=call_sid)

    async with session_scope() as session:
        conv_repo = ConversationRepository(session)
        if await conv_repo.get_by_call_sid(org_id, call_sid):
            logger.info("duplicate missed-call webhook ignored")
            return

        # The receiving Twilio-side number is the SMS "from" for the recovery.
        phone = await PhoneNumberRepository(session).get(org_id, uuid.UUID(phone_number_id))
        business_number = phone.e164_number if phone else ""

        lead = Lead(
            organization_id=org_id, phone_number=caller_number, status=LeadStatus.QUALIFYING
        )
        session.add(lead)
        await session.flush()

        conversation = Conversation(
            organization_id=org_id,
            lead_id=lead.id,
            call_sid=call_sid,
            twilio_sid=business_number,
        )
        session.add(conversation)
        await session.flush()

        run = WorkflowRun(
            organization_id=org_id,
            workflow_name="missed_call_recovery",
            conversation_id=conversation.id,
            lead_id=lead.id,
            state={
                "caller_number": caller_number,
                "business_number": business_number,
                "phone_number_id": phone_number_id,
            },
            status=WorkflowStatus.RUNNING,
        )
        session.add(run)
        await session.flush()

        await run_workflow(session, run.id)


async def process_inbound_sms(
    ctx: dict,
    organization_id: str,
    conversation_id: str,
    body: str,
    provider_message_sid: str,
) -> None:
    """Store the inbound message and resume the paused workflow.

    Idempotency key: provider_message_sid (unique constraint on messages)."""
    org_id = uuid.UUID(organization_id)
    conv_id = uuid.UUID(conversation_id)
    bind_log_context(org_id=organization_id)

    async with session_scope() as session:
        await MessageRepository(session).add(
            Message(
                conversation_id=conv_id,
                direction=MessageDirection.INBOUND,
                body=body,
                provider_message_sid=provider_message_sid,
            )
        )

        # Find the active run for this conversation and resume it past AwaitReply.
        from sqlalchemy import select

        run = (
            await session.execute(
                select(WorkflowRun).where(
                    WorkflowRun.organization_id == org_id,
                    WorkflowRun.conversation_id == conv_id,
                    WorkflowRun.status == WorkflowStatus.WAITING_ON_REPLY,
                )
            )
        ).scalar_one_or_none()
        if run is None:
            logger.info("inbound SMS with no waiting workflow run; stored only")
            return

        run.state = {**run.state, "resumed": True}
        run.status = WorkflowStatus.RUNNING
        await session.flush()
        await run_workflow(session, run.id)


async def run_workflow_step(ctx: dict, workflow_run_id: str) -> None:
    """Advance a specific workflow run (generic re-entry point)."""
    async with session_scope() as session:
        await run_workflow(session, uuid.UUID(workflow_run_id))


async def send_notification(
    ctx: dict, organization_id: str, lead_id: str, channel: str, urgent: bool = False
) -> None:
    from app.integrations.twilio_client import TwilioClient
    from app.services.notification_service import NotificationService

    async with session_scope() as session:
        notifier = NotificationService(session, TwilioClient())
        await notifier.notify_owner(
            organization_id=uuid.UUID(organization_id),
            lead_id=uuid.UUID(lead_id),
            urgent=urgent,
        )

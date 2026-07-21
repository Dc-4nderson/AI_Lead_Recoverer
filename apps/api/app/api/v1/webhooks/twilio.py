"""Twilio webhook handlers (§7, §10).

These are the fast, idempotent edge: validate signature, resolve tenant by the
RECEIVING number (never trust caller-supplied data — §5), persist minimally,
publish a domain event, return 200. All real work happens in the workflow
engine via queued jobs the event subscribers enqueue.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response

from app.api.deps import DbSession
from app.core.config import get_settings
from app.events.bus import event_bus
from app.events.types import MessageReceived, MissedCallDetected
from app.integrations.twilio_client import TwilioClient
from app.models import Conversation
from app.repositories.repositories import PhoneNumberRepository

logger = logging.getLogger("webhooks.twilio")
settings = get_settings()

router = APIRouter(prefix="/webhooks/twilio", tags=["webhooks"])

MISSED_STATUSES = {"no-answer", "busy", "failed"}


async def _validate(request: Request, form: dict[str, str]) -> bool:
    signature = request.headers.get("X-Twilio-Signature", "")
    url = f"{settings.public_api_base_url}{request.url.path}"
    return TwilioClient().validate_signature(url, form, signature)


@router.post("/voice-status")
async def voice_status(request: Request, db: DbSession) -> Response:
    form = dict(await request.form())
    if not await _validate(request, form):
        logger.warning("rejected voice-status webhook: bad signature")
        return Response(status_code=403)

    if form.get("CallStatus") not in MISSED_STATUSES:
        return Response(status_code=204)  # answered call — nothing to recover

    receiving_number = form.get("To", "")
    phone = await PhoneNumberRepository(db).get_by_e164(receiving_number)
    if phone is None:
        logger.warning("voice-status for unknown number %s", receiving_number)
        return Response(status_code=204)

    await event_bus.publish(
        MissedCallDetected(
            organization_id=phone.organization_id,
            phone_number_id=phone.id,
            caller_number=form.get("From", ""),
            call_sid=form.get("CallSid", ""),
        )
    )
    return Response(status_code=200)


@router.post("/sms-inbound")
async def sms_inbound(request: Request, db: DbSession) -> Response:
    form = dict(await request.form())
    if not await _validate(request, form):
        logger.warning("rejected sms-inbound webhook: bad signature")
        return Response(status_code=403)

    receiving_number = form.get("To", "")
    body = form.get("Body", "")
    message_sid = form.get("MessageSid", "")

    phone = await PhoneNumberRepository(db).get_by_e164(receiving_number)
    if phone is None:
        return Response(status_code=204)

    org_id = phone.organization_id
    # Find the most recent open conversation for this caller; the workflow's
    # AwaitReply step is what actually consumes the message.
    from sqlalchemy import select

    conversation = (
        await db.execute(
            select(Conversation)
            .where(
                Conversation.organization_id == org_id,
                Conversation.lead_id.isnot(None),
            )
            .order_by(Conversation.started_at.desc())
        )
    ).scalars().first()

    if conversation is None:
        # Inbound with no prior missed-call context — start a bare conversation.
        conversation = Conversation(organization_id=org_id, twilio_sid=receiving_number)
        db.add(conversation)
        await db.flush()

    # The message is persisted by process_inbound_sms (enqueued via the event),
    # keeping the webhook a fast "resolve + publish + 200" with no duplicate write.
    await event_bus.publish(
        MessageReceived(
            organization_id=org_id,
            conversation_id=conversation.id,
            body=body,
            provider_message_sid=message_sid,
        )
    )
    return Response(status_code=200)

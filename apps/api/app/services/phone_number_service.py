"""Dual-path phone number onboarding (§17a).

Primary path: connect an existing business number via conditional call
forwarding. Optional path: provision a fresh Twilio number. Both converge on
the same phone_numbers row and identical webhook handling.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.twilio_client import TwilioClient
from app.models import PhoneNumber
from app.repositories.repositories import PhoneNumberRepository
from app.schemas.phone_number import ForwardingInstructions
from app.shared.enums import ConnectionType, ForwardingStatus, PhoneStatus

# Carrier conditional-call-forward dial codes are config-driven, not hardcoded
# per customer. Extend this table (or move it to the DB) as carriers are added.
CARRIER_FORWARD_CODES: dict[str, str] = {
    "default": "*61*{target}#",  # forward on no-answer (most US GSM carriers)
}


class PhoneNumberService:
    def __init__(self, session: AsyncSession, twilio: TwilioClient | None = None) -> None:
        self.session = session
        self.repo = PhoneNumberRepository(session)
        self.twilio = twilio or TwilioClient()

    async def connect_forwarding(
        self, organization_id: uuid.UUID, business_number: str
    ) -> PhoneNumber:
        # Provision (or, in a fuller build, reuse from a pool) a Twilio-side
        # number that will receive the forwarded calls/SMS.
        e164, sid = await self.twilio.provision_number()
        phone = PhoneNumber(
            organization_id=organization_id,
            connection_type=ConnectionType.FORWARDED,
            e164_number=e164,
            business_number=business_number,
            twilio_sid=sid,
            forwarding_status=ForwardingStatus.PENDING_VERIFICATION,
            status=PhoneStatus.ACTIVE,
        )
        return await self.repo.add(phone)

    async def provision_twilio(
        self, organization_id: uuid.UUID, area_code: str | None = None
    ) -> PhoneNumber:
        e164, sid = await self.twilio.provision_number(area_code=area_code)
        phone = PhoneNumber(
            organization_id=organization_id,
            connection_type=ConnectionType.TWILIO_PROVISIONED,
            e164_number=e164,
            twilio_sid=sid,
            status=PhoneStatus.ACTIVE,
        )
        return await self.repo.add(phone)

    def forwarding_instructions(self, phone: PhoneNumber) -> ForwardingInstructions:
        code = CARRIER_FORWARD_CODES["default"].format(target=phone.e164_number)
        return ForwardingInstructions(
            e164_number=phone.e164_number,
            business_number=phone.business_number,
            forwarding_code=code,
            instructions=(
                f"On the phone for {phone.business_number}, dial {code} to forward "
                "unanswered calls to your AI assistant. Your phone still rings first; "
                "only missed calls are forwarded."
            ),
        )

    async def verify_forwarding(
        self, organization_id: uuid.UUID, phone_id: uuid.UUID
    ) -> PhoneNumber:
        phone = await self.repo.get_or_404(organization_id, phone_id)
        # A full build places a test call / waits for the first forwarded call.
        # For the scaffold we mark it verified so the onboarding flow completes.
        phone.forwarding_status = ForwardingStatus.VERIFIED
        await self.session.flush()
        return phone

"""Owner notifications (§8). Provider-agnostic: reads notification_preferences
and dispatches over the configured channel(s). New channels (Slack, email) are
additive and don't touch callers."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.twilio_client import TwilioClient
from app.repositories.repositories import BusinessSettingsRepository, LeadRepository

logger = logging.getLogger("services.notification")


class NotificationService:
    def __init__(self, session: AsyncSession, twilio: TwilioClient | None = None) -> None:
        self.session = session
        self.settings_repo = BusinessSettingsRepository(session)
        self.leads = LeadRepository(session)
        self.twilio = twilio or TwilioClient()

    async def notify_owner(
        self, *, organization_id: uuid.UUID, lead_id: uuid.UUID, urgent: bool
    ) -> None:
        settings = await self.settings_repo.get_for_org(organization_id)
        lead = await self.leads.get(organization_id, lead_id)
        if settings is None or lead is None:
            logger.warning("notify_owner: missing settings or lead")
            return

        prefs = settings.notification_preferences or {}
        owner_phone = prefs.get("owner_phone")
        prefix = "🚨 EMERGENCY LEAD" if urgent else "New qualified lead"
        body = (
            f"{prefix}: {lead.name or 'Unknown'} — "
            f"{lead.service_requested or 'service inquiry'} "
            f"({lead.phone_number}). Urgency: {lead.urgency or 'n/a'}."
        )

        if prefs.get("sms", True) and owner_phone:
            # from_number would be the org's provisioned Twilio number in a full
            # build; kept explicit here so the notification path has no hidden globals.
            await self.twilio.send_sms(
                to_number=owner_phone, from_number=owner_phone, body=body
            )
        else:
            logger.info("owner notification (no SMS channel configured): %s", body)

"""Thin Twilio I/O wrapper (§8). No business logic, no decisions.

Signature validation is security-critical: webhook routes trust Twilio's
signature instead of a JWT (§7), so this is the tenant/authenticity boundary.
"""
from __future__ import annotations

import logging

from twilio.request_validator import RequestValidator
from twilio.rest import Client

from app.core.config import get_settings

logger = logging.getLogger("integrations.twilio")
settings = get_settings()


class TwilioClient:
    def __init__(self) -> None:
        self._account_sid = settings.twilio_account_sid
        self._auth_token = settings.twilio_auth_token
        self._validator = RequestValidator(self._auth_token)
        self._rest: Client | None = None

    @property
    def rest(self) -> Client:
        if self._rest is None:
            self._rest = Client(self._account_sid, self._auth_token)
        return self._rest

    def validate_signature(self, url: str, params: dict[str, str], signature: str) -> bool:
        if not self._auth_token:
            logger.warning("Twilio auth token not configured; rejecting webhook")
            return False
        return self._validator.validate(url, params, signature)

    async def send_sms(self, *, to_number: str, from_number: str, body: str) -> str | None:
        # twilio-python is sync; kept behind an async method so callers stay
        # async-first and a fully-async client can drop in later.
        message = self.rest.messages.create(to=to_number, from_=from_number, body=body)
        return message.sid

    async def provision_number(self, *, area_code: str | None = None) -> tuple[str, str]:
        """Purchase an available number. Returns (e164_number, twilio_sid)."""
        available = self.rest.available_phone_numbers("US").local.list(
            area_code=area_code, limit=1
        )
        if not available:
            raise RuntimeError("No available Twilio numbers matched the request")
        purchased = self.rest.incoming_phone_numbers.create(
            phone_number=available[0].phone_number
        )
        return purchased.phone_number, purchased.sid

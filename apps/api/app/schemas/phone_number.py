from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.schemas.common import ORMModel


class ForwardConnectRequest(BaseModel):
    """Primary onboarding path (§17a): connect an existing business number."""

    business_number: str


class ProvisionRequest(BaseModel):
    """Optional path: provision a new Twilio number."""

    area_code: str | None = None


class PhoneNumberOut(ORMModel):
    id: uuid.UUID
    connection_type: str
    e164_number: str
    business_number: str | None
    forwarding_status: str | None
    status: str


class ForwardingInstructions(BaseModel):
    e164_number: str
    business_number: str | None
    # Carrier-specific conditional-call-forward dial code, config-driven (§17a).
    forwarding_code: str
    instructions: str

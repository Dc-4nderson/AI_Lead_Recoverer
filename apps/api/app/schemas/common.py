from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OrganizationOut(ORMModel):
    id: uuid.UUID
    name: str
    industry: str | None
    timezone: str
    status: str
    created_at: datetime


class CreateOrganizationRequest(BaseModel):
    name: str
    industry: str | None = None
    timezone: str = "UTC"


class BusinessSettingsIn(BaseModel):
    address_line1: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    business_hours: dict = {}
    services_offered: list[str] = []
    emergency_service_enabled: bool = False
    ai_tone: str | None = None
    ai_custom_instructions: str | None = None
    notification_preferences: dict = {}


class BusinessSettingsOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    address_line1: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str | None
    business_hours: dict
    services_offered: list[str]
    emergency_service_enabled: bool
    ai_tone: str | None
    ai_custom_instructions: str | None
    notification_preferences: dict


class LeadOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    phone_number: str
    name: str | None
    service_requested: str | None
    location: str | None
    urgency: str | None
    preferred_time: datetime | None
    classification: str | None
    status: str
    created_at: datetime


class WorkflowRunOut(ORMModel):
    id: uuid.UUID
    workflow_name: str
    status: str
    state: dict
    created_at: datetime

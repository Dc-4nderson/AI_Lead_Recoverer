"""Shared domain enums. Kept string-valued for stable DB storage + JSON."""
from __future__ import annotations

from enum import StrEnum


class OrgStatus(StrEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    STAFF = "staff"


class ConnectionType(StrEnum):
    TWILIO_PROVISIONED = "twilio_provisioned"
    FORWARDED = "forwarded"


class ForwardingStatus(StrEnum):
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    FAILED = "failed"


class PhoneStatus(StrEnum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    RELEASED = "released"


class Urgency(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    EMERGENCY = "emergency"


class Classification(StrEnum):
    NEW_LEAD = "new_lead"
    EXISTING_CUSTOMER = "existing_customer"
    EMERGENCY = "emergency"
    SPAM = "spam"


class LeadStatus(StrEnum):
    NEW = "new"
    QUALIFYING = "qualifying"
    QUALIFIED = "qualified"
    APPOINTMENT_REQUESTED = "appointment_requested"
    CLOSED = "closed"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class Channel(StrEnum):
    SMS = "sms"
    VOICE = "voice"


class WorkflowStatus(StrEnum):
    RUNNING = "running"
    WAITING_ON_REPLY = "waiting_on_reply"
    COMPLETED = "completed"
    FAILED = "failed"

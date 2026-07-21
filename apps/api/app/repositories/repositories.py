"""Concrete repositories.

Tenant-scoped entities extend TenantScopedRepository. A few tables
(users, memberships, phone lookup by number, event_log) need query shapes
that aren't a simple org+id lookup and are defined explicitly here.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BusinessSettings,
    Conversation,
    EventLog,
    Lead,
    Membership,
    Message,
    Organization,
    PhoneNumber,
    User,
    WorkflowRun,
)
from app.repositories.base import TenantScopedRepository


class LeadRepository(TenantScopedRepository[Lead]):
    model = Lead


class ConversationRepository(TenantScopedRepository[Conversation]):
    model = Conversation

    async def get_by_call_sid(
        self, organization_id: uuid.UUID, call_sid: str
    ) -> Conversation | None:
        stmt = select(Conversation).where(
            Conversation.organization_id == organization_id,
            Conversation.call_sid == call_sid,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()


class WorkflowRunRepository(TenantScopedRepository[WorkflowRun]):
    model = WorkflowRun


class BusinessSettingsRepository(TenantScopedRepository[BusinessSettings]):
    model = BusinessSettings

    async def get_for_org(self, organization_id: uuid.UUID) -> BusinessSettings | None:
        stmt = select(BusinessSettings).where(
            BusinessSettings.organization_id == organization_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()


class PhoneNumberRepository(TenantScopedRepository[PhoneNumber]):
    model = PhoneNumber

    async def get_by_e164(self, e164_number: str) -> PhoneNumber | None:
        """Tenant resolution entry point for webhooks (§5): the receiving
        number is the *only* trusted signal for which org owns the call."""
        stmt = select(PhoneNumber).where(PhoneNumber.e164_number == e164_number)
        return (await self.session.execute(stmt)).scalar_one_or_none()


# --- Non-tenant-scoped repositories (identity + platform tables) ---


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower())
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user


class MembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID, organization_id: uuid.UUID) -> Membership | None:
        stmt = select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[Membership]:
        stmt = select(Membership).where(Membership.user_id == user_id)
        return list((await self.session.execute(stmt)).scalars().all())

    async def add(self, membership: Membership) -> Membership:
        self.session.add(membership)
        await self.session.flush()
        return membership


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, organization_id: uuid.UUID) -> Organization | None:
        return await self.session.get(Organization, organization_id)

    async def add(self, org: Organization) -> Organization:
        self.session.add(org)
        await self.session.flush()
        return org


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, message: Message) -> Message:
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_for_conversation(self, conversation_id: uuid.UUID) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())


class EventLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, event: EventLog) -> EventLog:
        self.session.add(event)
        await self.session.flush()
        return event

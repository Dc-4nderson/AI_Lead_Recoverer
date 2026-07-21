"""Signup, login, token issuance (§4, §8)."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models import Membership, Organization, User
from app.repositories.repositories import (
    MembershipRepository,
    OrganizationRepository,
    UserRepository,
)
from app.schemas.auth import SignupRequest, TokenPair
from app.shared.enums import Role
from app.shared.exceptions import AuthenticationError, ConflictError


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.orgs = OrganizationRepository(session)
        self.memberships = MembershipRepository(session)

    async def signup(self, req: SignupRequest) -> TokenPair:
        if await self.users.get_by_email(req.email):
            raise ConflictError("An account with this email already exists")

        user = await self.users.add(
            User(email=req.email.lower(), hashed_password=hash_password(req.password))
        )
        org = await self.orgs.add(Organization(name=req.organization_name))
        await self.memberships.add(
            Membership(user_id=user.id, organization_id=org.id, role=Role.OWNER)
        )
        return self._issue_tokens(user.id)

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self.users.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")
        return self._issue_tokens(user.id)

    @staticmethod
    def _issue_tokens(user_id: uuid.UUID) -> TokenPair:
        return TokenPair(
            access_token=create_access_token(str(user_id)),
            refresh_token=create_refresh_token(str(user_id)),
        )

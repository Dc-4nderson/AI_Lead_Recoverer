"""Shared FastAPI dependencies (§4, §5).

get_current_org is the tenant-isolation gate: it resolves the org from the
path and validates the caller's membership BEFORE any router body runs. The
resolved org_id is threaded explicitly into services/repositories.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

import jwt
from fastapi import Depends, Path
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionFactory
from app.core.security import decode_token
from app.models import User
from app.repositories.repositories import MembershipRepository
from app.shared.exceptions import AuthenticationError, TenantIsolationError

# auto_error=False so we raise our own AuthenticationError (consistent JSON
# error shape) instead of FastAPI's default 403. Declaring this scheme also
# gives Swagger UI (/docs) an "Authorize" button that attaches the bearer token.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer token")
    token = credentials.credentials
    try:
        payload = decode_token(token, expected_type="access")
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired token") from exc

    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None:
        raise AuthenticationError("User not found")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_org(
    db: DbSession,
    user: CurrentUser,
    org_id: Annotated[uuid.UUID, Path(alias="org_id")],
) -> uuid.UUID:
    """Validate that the authenticated user belongs to the org in the path."""
    membership = await MembershipRepository(db).get(user.id, org_id)
    if membership is None:
        raise TenantIsolationError("You do not have access to this organization")
    return org_id


CurrentOrg = Annotated[uuid.UUID, Depends(get_current_org)]

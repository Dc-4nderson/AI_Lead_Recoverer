from __future__ import annotations

import jwt
from fastapi import APIRouter

from app.api.deps import DbSession
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenPair,
)
from app.services.auth_service import AuthService
from app.shared.exceptions import AuthenticationError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenPair, status_code=201)
async def signup(req: SignupRequest, db: DbSession) -> TokenPair:
    return await AuthService(db).signup(req)


@router.post("/login", response_model=TokenPair)
async def login(req: LoginRequest, db: DbSession) -> TokenPair:
    return await AuthService(db).login(req.email, req.password)


@router.post("/refresh", response_model=TokenPair)
async def refresh(req: RefreshRequest) -> TokenPair:
    try:
        payload = decode_token(req.refresh_token, expected_type="refresh")
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired refresh token") from exc
    user_id = payload["sub"]
    return TokenPair(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.post("/logout", status_code=204)
async def logout() -> None:
    # Stateless access tokens; a full build revokes the refresh token's jti in a
    # revocation store (§4). No-op placeholder keeps the client contract stable.
    return None

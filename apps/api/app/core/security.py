"""Authentication primitives (§4): password hashing + JWT issue/verify.

argon2id for password hashing. JWT carries user_id only — never org_id;
org context is resolved and validated per-request (§5).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

settings = get_settings()
_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def _encode(claims: dict[str, Any], ttl: timedelta, token_type: str) -> str:
    now = datetime.now(UTC)
    payload = {
        **claims,
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str) -> str:
    return _encode(
        {"sub": user_id},
        timedelta(minutes=settings.jwt_access_token_ttl_minutes),
        "access",
    )


def create_refresh_token(user_id: str) -> str:
    return _encode(
        {"sub": user_id},
        timedelta(days=settings.jwt_refresh_token_ttl_days),
        "refresh",
    )


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    """Raises jwt.PyJWTError on invalid/expired tokens."""
    payload = jwt.decode(
        token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected {expected_type} token")
    return payload

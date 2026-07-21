"""Domain exceptions mapped to HTTP responses in app.main (§2)."""
from __future__ import annotations


class DomainError(Exception):
    """Base for all application-level errors."""

    status_code = 400
    code = "domain_error"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class AuthenticationError(DomainError):
    status_code = 401
    code = "authentication_error"


class AuthorizationError(DomainError):
    status_code = 403
    code = "authorization_error"


class TenantIsolationError(AuthorizationError):
    """Raised when a request touches a resource outside the current tenant."""

    code = "tenant_isolation_error"


class ValidationError(DomainError):
    status_code = 422
    code = "validation_error"

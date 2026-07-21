"""Tenant-scoped repository base (§5).

This is the enforcement mechanism, not just a convenience. Every query for a
tenant-owned entity goes through here and is *always* filtered by
organization_id. There is deliberately no "get by id" without a tenant scope.
"""
from __future__ import annotations

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Base
from app.shared.exceptions import NotFoundError

ModelT = TypeVar("ModelT", bound=Base)


class TenantScopedRepository(Generic[ModelT]):
    """Base for repositories over tables carrying ``organization_id``.

    Subclasses set ``model``. Every read/write requires an explicit
    ``organization_id`` argument — an unscoped query is not expressible
    through this API.
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, organization_id: uuid.UUID, entity_id: uuid.UUID) -> ModelT | None:
        stmt = select(self.model).where(
            self.model.id == entity_id,
            self.model.organization_id == organization_id,  # type: ignore[attr-defined]
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_404(self, organization_id: uuid.UUID, entity_id: uuid.UUID) -> ModelT:
        obj = await self.get(organization_id, entity_id)
        if obj is None:
            raise NotFoundError(f"{self.model.__name__} not found")
        return obj

    async def list(
        self, organization_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[ModelT]:
        stmt = (
            select(self.model)
            .where(self.model.organization_id == organization_id)  # type: ignore[attr-defined]
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity

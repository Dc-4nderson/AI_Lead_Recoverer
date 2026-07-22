"""Async SQLAlchemy engine + session factory (§2).

Session is request-scoped in the API (via a FastAPI dependency) and
task-scoped in the worker (via an explicit context manager).
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event, inspect
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

SessionFactory = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _column_values(obj: object) -> dict[str, object]:
    mapper = inspect(obj).mapper
    out: dict[str, object] = {}
    for col in mapper.columns:
        try:
            out[col.key] = getattr(obj, col.key)
        except Exception:  # noqa: BLE001 - best-effort snapshot for the inspector
            out[col.key] = "<unavailable>"
    return out


def _before_after(obj: object) -> tuple[dict, dict]:
    """Per-column before/after using SQLAlchemy attribute history."""
    state = inspect(obj)
    before: dict[str, object] = {}
    after: dict[str, object] = {}
    for attr in state.attrs:
        hist = attr.history
        if not hist.has_changes():
            continue
        before[attr.key] = hist.deleted[0] if hist.deleted else None
        after[attr.key] = hist.added[0] if hist.added else None
    return before, after


@event.listens_for(Session, "after_flush")
def _record_db_changes(session: Session, flush_context) -> None:
    """Observability only: when a simulation is active, record every INSERT/
    UPDATE/DELETE into its trace. No-op in production (no bound simulation)."""
    from app.simulator.session import get_current_simulation

    sim = get_current_simulation()
    if sim is None:
        return

    def _pk(obj: object) -> str:
        ident = inspect(obj).identity
        return str(ident[0]) if ident else "<pending>"

    for obj in session.new:
        sim.trace.record_db_change(
            obj.__tablename__, "insert", _pk(obj), None, _to_jsonable(_column_values(obj))
        )
    for obj in session.dirty:
        if not session.is_modified(obj, include_collections=False):
            continue
        before, after = _before_after(obj)
        if before or after:
            sim.trace.record_db_change(
                obj.__tablename__, "update", _pk(obj), _to_jsonable(before), _to_jsonable(after)
            )
    for obj in session.deleted:
        sim.trace.record_db_change(
            obj.__tablename__, "delete", _pk(obj), _to_jsonable(_column_values(obj)), None
        )


def _to_jsonable(d: dict) -> dict:
    return {k: (str(v) if not isinstance(v, (str, int, float, bool, type(None), dict, list)) else v)
            for k, v in d.items()}


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional session for workers / event handlers.

    Commits on success, rolls back on exception. The API uses a separate
    dependency (app.api.deps.get_db) with the same semantics.
    """
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

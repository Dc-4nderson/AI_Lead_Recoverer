"""Event bus unit tests (§13): subscriber isolation + fan-out.

Persistence to event_log is patched out here so the bus can be tested without a
database — the durability path has its own integration coverage.
"""
from __future__ import annotations

import uuid

import pytest

from app.events.bus import EventBus
from app.events.types import LeadQualified


@pytest.mark.asyncio
async def test_all_subscribers_run_even_if_one_fails(monkeypatch):
    bus = EventBus()
    monkeypatch.setattr(bus, "_persist", _noop_persist)
    calls: list[str] = []

    async def bad(_event):
        calls.append("bad")
        raise RuntimeError("boom")

    async def good(_event):
        calls.append("good")

    bus.subscribe(LeadQualified, bad)
    bus.subscribe(LeadQualified, good)

    await bus.publish(
        LeadQualified(
            organization_id=uuid.uuid4(), lead_id=uuid.uuid4(), classification="new_lead"
        )
    )

    # A failing subscriber must not prevent later subscribers from running.
    assert calls == ["bad", "good"]


async def _noop_persist(_event) -> None:
    return None

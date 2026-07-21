"""Queue abstraction (§9).

Services and event handlers depend on this Protocol only — never on arq
directly. Substituting Celery later means writing a new backend module and
changing one binding, not touching call sites.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class QueueClient(Protocol):
    async def enqueue(self, task_name: str, *args, **kwargs) -> str:
        """Enqueue a task for immediate processing. Returns a job id."""
        ...

    async def enqueue_at(self, task_name: str, when: datetime, *args, **kwargs) -> str:
        """Enqueue a task to run at a specific time. Returns a job id."""
        ...

"""arq implementation of the QueueClient interface (§9).

This is the ONLY module that imports arq. It also defines the worker's
``WorkerSettings`` (the entrypoint referenced by docker-compose / render.yaml:
``arq app.queue.arq_backend.WorkerSettings``).
"""
from __future__ import annotations

from datetime import datetime

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings
from app.queue.tasks import (
    handle_missed_call,
    process_inbound_sms,
    run_workflow_step,
    send_notification,
    shutdown,
    startup,
)

settings = get_settings()


class ArqQueueClient:
    """Adapts arq's pool to the QueueClient Protocol."""

    def __init__(self, pool: ArqRedis) -> None:
        self._pool = pool

    async def enqueue(self, task_name: str, *args, **kwargs) -> str:
        job = await self._pool.enqueue_job(task_name, *args, **kwargs)
        return job.job_id if job else ""

    async def enqueue_at(self, task_name: str, when: datetime, *args, **kwargs) -> str:
        job = await self._pool.enqueue_job(task_name, *args, _defer_until=when, **kwargs)
        return job.job_id if job else ""


_pool: ArqRedis | None = None


async def get_queue_client() -> ArqQueueClient:
    """Lazily create a shared arq pool for API-side enqueuing."""
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return ArqQueueClient(_pool)


class WorkerSettings:
    """arq worker configuration — the background service entrypoint."""

    functions = [
        handle_missed_call,
        process_inbound_sms,
        run_workflow_step,
        send_notification,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_tries = 3  # exponential backoff by default (§9)

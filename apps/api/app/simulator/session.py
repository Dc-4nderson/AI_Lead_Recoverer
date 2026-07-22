"""SimulationSession + the single contextvar every production component checks.

When no session is bound (production), every instrumentation hook is a no-op, so
the simulator adds zero overhead and zero behavior change to the live system.
When a session IS bound (a simulation request), the hooks record to the trace
and the injected doubles (sms/notifier/queue/ai_client) replace only the I/O
transports Twilio/OpenAI/Redis.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.simulator.trace import TraceCollector


@dataclass
class SimulationSession:
    trace: TraceCollector
    twilio_client: Any       # SimulatedTwilioClient — swaps Twilio I/O only; the
                             # real TwilioService/NotificationService run unchanged
    queue: Any               # InlineQueueClient (QueueClient protocol)
    ai_client: Any | None    # OpenAI-compatible client, or None to use real OpenAI


_current: ContextVar[SimulationSession | None] = ContextVar("current_simulation", default=None)


def get_current_simulation() -> SimulationSession | None:
    return _current.get()


def bind_simulation(session: SimulationSession):
    """Bind a session for the current async context. Returns the reset token."""
    return _current.set(session)


def unbind_simulation(token) -> None:
    _current.reset(token)

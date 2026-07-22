"""I/O doubles used during a simulation.

These replace ONLY the external transports the architecture already treats as
swappable — Twilio, the Redis queue round-trip, and (by default) the OpenAI
client. The workflow engine, event bus, AI extraction service, repositories,
queue *interface*, and business services all run as the real production code.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any

from app.ai.schemas import LeadExtractionResult
from app.shared.enums import Classification, Urgency
from app.simulator.trace import TraceCollector


# --------------------------------------------------------------------------- #
# Twilio double — records outbound SMS instead of calling Twilio.
# Implements the small surface TwilioClient exposes that the workflow/notifier
# actually use, so the real TwilioService/NotificationService run unchanged.
# --------------------------------------------------------------------------- #
class SimulatedTwilioClient:
    def __init__(self, trace: TraceCollector) -> None:
        self._trace = trace

    async def send_sms(self, *, to_number: str, from_number: str, body: str) -> str:
        self._trace.record_sms(to_number, from_number, body, kind="outbound_sms")
        return f"SM_sim_{uuid.uuid4().hex[:12]}"

    async def send(self, *, to_number: str, from_number: str, body: str) -> str:
        # SMSSender protocol method the workflow steps call.
        return await self.send_sms(to_number=to_number, from_number=from_number, body=body)

    def validate_signature(self, url: str, params: dict[str, str], signature: str) -> bool:
        return True  # not exercised in-process, but keep the surface complete


# --------------------------------------------------------------------------- #
# Inline queue — implements the QueueClient protocol but runs the SAME arq task
# functions synchronously, capturing status/duration/retries in the trace.
# --------------------------------------------------------------------------- #
class InlineQueueClient:
    def __init__(self, trace: TraceCollector) -> None:
        self._trace = trace

    def _registry(self) -> dict[str, Any]:
        # Lazy import avoids an import cycle (tasks -> handlers -> queue).
        from app.queue.arq_backend import WorkerSettings

        return {fn.__name__: fn for fn in WorkerSettings.functions}

    async def enqueue(self, task_name: str, *args, **kwargs) -> str:
        job = self._trace.record_queue_job(task_name)
        fn = self._registry().get(task_name)
        if fn is None:
            job["status"] = "failed"
            job["error"] = f"unknown task {task_name}"
            return job["seq"] and str(job["seq"])

        job["status"] = "running"
        started = time.perf_counter()
        try:
            # arq tasks take a ctx dict as the first positional arg.
            await fn({}, *args, **kwargs)
            job["status"] = "completed"
        except Exception as exc:  # noqa: BLE001 — surface failures in the trace
            job["status"] = "failed"
            job["error"] = repr(exc)
            raise
        finally:
            job["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return str(job["seq"])

    async def enqueue_at(self, task_name: str, when: datetime, *args, **kwargs) -> str:
        # In simulation there is no deferral; run immediately and note the intent.
        return await self.enqueue(task_name, *args, **kwargs)


# --------------------------------------------------------------------------- #
# Mock OpenAI client — mirrors the exact surface AIExtractionService calls:
#   response = await client.responses.parse(model=, input=, text_format=Model)
#   result = response.output_parsed
# Returns a schema-valid LeadExtractionResult derived from the conversation, so
# the AIExtractionService (and everything downstream) is genuinely unchanged.
# --------------------------------------------------------------------------- #
class _ParsedResponse:
    def __init__(self, parsed: LeadExtractionResult, raw: dict[str, Any]) -> None:
        self.output_parsed = parsed
        self.raw = raw


class _MockResponses:
    async def parse(self, *, model: str, input: list[dict], text_format: type, **_: Any):
        transcript = "\n".join(
            m.get("content", "") for m in input if m.get("role") == "user"
        ).lower()
        result = _extract_from_text(transcript)
        raw = {
            "model": model,
            "mock": True,
            "output_parsed": result.model_dump(mode="json"),
        }
        return _ParsedResponse(result, raw)


class MockOpenAIClient:
    def __init__(self) -> None:
        self.responses = _MockResponses()


_EMERGENCY = ("emergency", "urgent", "asap", "right now", "flood", "burst", "no heat", "gas leak")
_SPAM = ("free money", "crypto", "loan offer", "click here", "winner", "prize")
_EXISTING = ("existing customer", "account number", "last time", "you serviced", "returning")
_APPOINTMENT = ("appointment", "schedule", "book", "come out", "tomorrow", "next week")


def _extract_from_text(text: str) -> LeadExtractionResult:
    """Deterministic stand-in for the model. Keyword rules only — no business
    decisions (those stay in the workflow engine)."""
    classification = Classification.NEW_LEAD
    urgency = Urgency.NORMAL
    if any(k in text for k in _SPAM):
        classification = Classification.SPAM
    elif any(k in text for k in _EMERGENCY):
        classification = Classification.EMERGENCY
        urgency = Urgency.EMERGENCY
    elif any(k in text for k in _EXISTING):
        classification = Classification.EXISTING_CUSTOMER

    service = None
    for kw in ("plumbing", "ac", "hvac", "roof", "electric", "detail", "cleaning", "heat"):
        if kw in text:
            service = kw
            break

    missing: list[str] = []
    if not service and classification != Classification.SPAM:
        missing.append("service_requested")
    if "at " not in text and "street" not in text and "address" not in text:
        missing.append("location")

    return LeadExtractionResult(
        name=None,
        service_requested=service,
        location=None,
        urgency=urgency,
        preferred_time=None,
        classification=classification,
        missing_fields=missing,
        suggested_reply=(
            "Thanks! Could you share your address and the service you need?"
            if missing
            else "Got it — we'll be in touch shortly."
        ),
    )

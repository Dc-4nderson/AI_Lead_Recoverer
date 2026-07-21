"""The MVP flow: missed call → SMS → qualify → notify (§17)."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.events.types import MissedCallDetected
from app.workflows.steps import (
    AwaitReply,
    ExtractLeadInfo,
    QualifyAndRoute,
    SendInitialSMS,
    Step,
)


@dataclass
class WorkflowDefinition:
    name: str
    trigger: type
    steps: list[Step] = field(default_factory=list)


# Declarative, ordered steps. Whether emergency handling applies, how follow-ups
# are phrased, and retry limits are driven by business_settings inside the steps
# — not new branches here (config replaces code, §6).
MISSED_CALL_RECOVERY = WorkflowDefinition(
    name="missed_call_recovery",
    trigger=MissedCallDetected,
    steps=[
        SendInitialSMS(),
        AwaitReply(timeout_minutes=30),  # index 1 — QualifyAndRoute loops back here
        ExtractLeadInfo(),
        QualifyAndRoute(),
    ],
)

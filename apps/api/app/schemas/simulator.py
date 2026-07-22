from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class WorkflowInfo(BaseModel):
    name: str
    trigger_event: str
    steps: list[str]


class EventTypeInfo(BaseModel):
    name: str
    event_type: str
    fields: list[str]


class SimulationRunRequest(BaseModel):
    workflow: str = "missed_call_recovery"
    caller_number: str = "+15551230000"
    business_number: str = "+15559990000"
    conversation_turns: list[str] = Field(default_factory=list)
    use_real_ai: bool = False
    business_settings_overrides: dict[str, Any] | None = None


class SimulationRunResponse(BaseModel):
    call_sid: str
    conversation_id: str | None
    workflow_run: dict[str, Any] | None
    lead: dict[str, Any] | None
    trace: dict[str, Any]


class ReplayEventRequest(BaseModel):
    event_type: str
    payload: dict[str, Any]


class StepRequest(BaseModel):
    workflow_run_id: uuid.UUID
    use_real_ai: bool = False


class ResetRequest(BaseModel):
    conversation_id: uuid.UUID


class ScenarioIn(BaseModel):
    name: str
    payload: SimulationRunRequest


class ScenarioOut(ORMModel):
    id: uuid.UUID
    name: str
    payload: dict[str, Any]
    created_at: datetime

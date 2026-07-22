"""Workflow Simulator API (developer/QA tool).

Thin endpoints over the production backend. `run` drives real components via
synthetic events; `replay-event` republishes through the real event bus; the
rest manage saved scenarios and cleanup. All org-scoped + membership-checked
via the standard deps.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentOrg, DbSession
from app.events.bus import event_bus
from app.events.types import (
    AppointmentRequested,
    LeadQualified,
    MessageReceived,
    MissedCallDetected,
    SMSSent,
)
from app.models import Conversation, Lead, SimulatorScenario, WorkflowRun
from app.repositories.repositories import WorkflowRunRepository
from app.schemas.simulator import (
    EventTypeInfo,
    ReplayEventRequest,
    ResetRequest,
    ScenarioIn,
    ScenarioOut,
    SimulationRunRequest,
    SimulationRunResponse,
    StepRequest,
    WorkflowInfo,
)
from app.shared.exceptions import NotFoundError, ValidationError
from app.simulator.doubles import InlineQueueClient, MockOpenAIClient, SimulatedTwilioClient
from app.simulator.runner import SimulationRunner, _lead_snapshot, _run_snapshot
from app.simulator.session import SimulationSession, bind_simulation, unbind_simulation
from app.simulator.trace import TraceCollector
from app.workflows.definitions import REGISTRY
from app.workflows.runtime import run_workflow

router = APIRouter(prefix="/organizations/{org_id}/simulator", tags=["simulator"])

# Every event type the platform publishes. Adding a new event here makes it
# replayable + listable in the simulator.
EVENT_TYPES: dict[str, type] = {
    cls.event_type: cls
    for cls in (
        MissedCallDetected,
        SMSSent,
        MessageReceived,
        LeadQualified,
        AppointmentRequested,
    )
}


@router.get("/workflows", response_model=list[WorkflowInfo])
async def list_workflows(org_id: CurrentOrg) -> list[WorkflowInfo]:
    # Auto-discovers every registered workflow definition (§17).
    return [
        WorkflowInfo(
            name=defn.name,
            trigger_event=defn.trigger.event_type,
            steps=[type(step).__name__ for step in defn.steps],
        )
        for defn in REGISTRY.values()
    ]


@router.get("/event-types", response_model=list[EventTypeInfo])
async def list_event_types(org_id: CurrentOrg) -> list[EventTypeInfo]:
    return [
        EventTypeInfo(
            name=cls.__name__,
            event_type=event_type,
            fields=[f for f in cls.model_fields if f != "occurred_at"],
        )
        for event_type, cls in EVENT_TYPES.items()
    ]


@router.post("/run", response_model=SimulationRunResponse)
async def run_simulation(
    org_id: CurrentOrg, req: SimulationRunRequest, db: DbSession
) -> SimulationRunResponse:
    if req.workflow not in REGISTRY:
        raise ValidationError(f"Unknown workflow '{req.workflow}'")
    runner = SimulationRunner(db, org_id)
    result = await runner.run(
        workflow=req.workflow,
        caller_number=req.caller_number,
        business_number=req.business_number,
        conversation_turns=req.conversation_turns,
        use_real_ai=req.use_real_ai,
        business_settings_overrides=req.business_settings_overrides,
    )
    return SimulationRunResponse(**result)


@router.post("/step", response_model=SimulationRunResponse)
async def step_workflow(
    org_id: CurrentOrg, req: StepRequest, db: DbSession
) -> SimulationRunResponse:
    """Advance an existing, paused workflow run by exactly ONE engine step
    (engine.advance(max_steps=1), §17) — the same run_workflow production
    entrypoint the queue task uses, just step-bounded for debugging."""
    owned = await WorkflowRunRepository(db).get(org_id, req.workflow_run_id)
    if owned is None:
        raise NotFoundError("WorkflowRun not found")

    trace = TraceCollector()
    sim = SimulationSession(
        trace=trace,
        twilio_client=SimulatedTwilioClient(trace),
        queue=InlineQueueClient(trace),
        ai_client=None if req.use_real_ai else MockOpenAIClient(),
    )
    token = bind_simulation(sim)
    try:
        run = await run_workflow(db, req.workflow_run_id, max_steps=1)
        await db.commit()
        lead = await db.get(Lead, run.lead_id) if run.lead_id else None
    finally:
        unbind_simulation(token)

    return SimulationRunResponse(
        call_sid="",
        conversation_id=str(run.conversation_id) if run.conversation_id else None,
        workflow_run=_run_snapshot(run),
        lead=_lead_snapshot(lead),
        trace=trace.to_dict(),
    )


@router.post("/replay-event")
async def replay_event(
    org_id: CurrentOrg, req: ReplayEventRequest, db: DbSession
) -> dict:
    """Republish a prior event through the REAL event bus (not a manual
    downstream call), captured under a fresh simulation trace."""
    cls = EVENT_TYPES.get(req.event_type)
    if cls is None:
        raise ValidationError(f"Unknown event type '{req.event_type}'")
    try:
        event = cls(**{**req.payload, "organization_id": str(org_id)})
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(f"Invalid payload for {req.event_type}: {exc}") from exc

    # Idempotent — the API lifespan already does this at startup; repeating here
    # keeps the endpoint self-sufficient (e.g. under test).
    from app.events.handlers import register_all_handlers

    register_all_handlers()

    trace = TraceCollector()
    sim = SimulationSession(
        trace=trace,
        twilio_client=SimulatedTwilioClient(trace),
        queue=InlineQueueClient(trace),
        ai_client=MockOpenAIClient(),
    )
    token = bind_simulation(sim)
    try:
        await event_bus.publish(event)
        await db.commit()
    finally:
        unbind_simulation(token)
    return {"replayed": req.event_type, "trace": trace.to_dict()}


@router.post("/reset")
async def reset_simulation(org_id: CurrentOrg, req: ResetRequest, db: DbSession) -> dict:
    """Delete rows a simulation created for one conversation (read-only inspector
    stays read-only; cleanup is an explicit action). Messages cascade."""
    conv = (
        await db.execute(
            select(Conversation).where(
                Conversation.id == req.conversation_id,
                Conversation.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if conv is None:
        raise NotFoundError("Conversation not found")

    runs = (
        await db.execute(
            select(WorkflowRun).where(WorkflowRun.conversation_id == conv.id)
        )
    ).scalars().all()
    lead_ids = {r.lead_id for r in runs if r.lead_id}
    if conv.lead_id:
        lead_ids.add(conv.lead_id)

    for run in runs:
        await db.delete(run)
    await db.delete(conv)  # cascades messages
    for lead_id in lead_ids:
        lead = await db.get(Lead, lead_id)
        if lead is not None:
            await db.delete(lead)
    return {"reset": str(req.conversation_id), "deleted_runs": len(runs)}


# --------------------------------------------------------------- scenarios
@router.get("/scenarios", response_model=list[ScenarioOut])
async def list_scenarios(org_id: CurrentOrg, db: DbSession) -> list[ScenarioOut]:
    rows = (
        await db.execute(
            select(SimulatorScenario)
            .where(SimulatorScenario.organization_id == org_id)
            .order_by(SimulatorScenario.created_at.desc())
        )
    ).scalars().all()
    return [ScenarioOut.model_validate(r) for r in rows]


@router.post("/scenarios", response_model=ScenarioOut, status_code=201)
async def save_scenario(org_id: CurrentOrg, req: ScenarioIn, db: DbSession) -> ScenarioOut:
    row = SimulatorScenario(
        organization_id=org_id, name=req.name, payload=req.payload.model_dump()
    )
    db.add(row)
    await db.flush()
    return ScenarioOut.model_validate(row)


@router.delete("/scenarios/{scenario_id}", status_code=204)
async def delete_scenario(
    org_id: CurrentOrg, scenario_id: uuid.UUID, db: DbSession
) -> None:
    row = (
        await db.execute(
            select(SimulatorScenario).where(
                SimulatorScenario.id == scenario_id,
                SimulatorScenario.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("Scenario not found")
    await db.delete(row)

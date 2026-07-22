"""Runtime glue between the pure engine and the outside world.

Builds a WorkflowContext from persisted state + injected adapters, runs the
engine, and persists the resulting state/status back to the WorkflowRun row.
The engine stays free of DB/integration concerns; this module owns them.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.extraction_service import AIExtractionService
from app.ai.schemas import LeadExtractionResult
from app.events.bus import event_bus
from app.integrations.twilio_client import TwilioClient
from app.models import WorkflowRun
from app.repositories.repositories import (
    BusinessSettingsRepository,
    ConversationRepository,
    MessageRepository,
    OrganizationRepository,
)
from app.services.notification_service import NotificationService
from app.shared.exceptions import NotFoundError
from app.workflows.context import WorkflowContext
from app.workflows.definitions import REGISTRY
from app.workflows.engine import WorkflowEngine


class _ExtractorAdapter:
    """Conforms to the Extractor protocol: pulls conversation history + tenant
    context from the DB and delegates to the AI extraction layer."""

    def __init__(
        self, session: AsyncSession, organization_id: uuid.UUID, ai_client: object | None = None
    ) -> None:
        self.session = session
        self.organization_id = organization_id
        self.messages = MessageRepository(session)
        self.settings_repo = BusinessSettingsRepository(session)
        self.orgs = OrganizationRepository(session)
        # ai_client is only supplied during a simulation (a deterministic mock,
        # or a real OpenAI client for the "use real AI" toggle). Production
        # passes None → AIExtractionService builds its own real client.
        self.ai = AIExtractionService(client=ai_client)

    async def extract(self, *, conversation_id: uuid.UUID) -> LeadExtractionResult:
        history = await self.messages.list_for_conversation(conversation_id)
        settings = await self.settings_repo.get_for_org(self.organization_id)
        org = await self.orgs.get(self.organization_id)
        return await self.ai.extract(
            conversation_history=[
                {"direction": m.direction, "body": m.body} for m in history
            ],
            business_name=org.name if org else "our business",
            industry=org.industry if org else None,
            business_settings=settings,
        )


async def run_workflow(
    session: AsyncSession, workflow_run_id: uuid.UUID, max_steps: int | None = None
) -> WorkflowRun:
    """Load a run, advance it through the engine, persist the result.

    ``max_steps`` (None in production) bounds how many engine steps run in this
    call — used by the simulator's "Step Forward" control (§17 engine.advance).
    """
    run = await session.get(WorkflowRun, workflow_run_id)
    if run is None:
        raise NotFoundError("WorkflowRun not found")

    definition = REGISTRY[run.workflow_name]
    engine = WorkflowEngine(definition)

    conv_repo = ConversationRepository(session)
    conversation = await conv_repo.get(run.organization_id, run.conversation_id)

    # During a simulation, swap Twilio I/O + AI client for doubles; the real
    # NotificationService, AIExtractionService, engine and repositories all run
    # unchanged (only external transports differ — §16/§17 seams).
    from app.simulator.session import get_current_simulation

    sim = get_current_simulation()
    twilio = sim.twilio_client if sim is not None else TwilioClient()
    ai_client = sim.ai_client if sim is not None else None
    phone_from = conversation.twilio_sid if conversation else ""

    ctx = WorkflowContext(
        organization_id=run.organization_id,
        workflow_run_id=run.id,
        conversation_id=run.conversation_id,
        lead_id=run.lead_id,
        caller_number=run.state.get("caller_number", ""),
        business_number=run.state.get("business_number", phone_from),
        state=dict(run.state),
        sms=twilio,
        extractor=_ExtractorAdapter(session, run.organization_id, ai_client),
        notifier=NotificationService(session, twilio),
        publish_event=event_bus.publish,
    )

    status = await engine.advance(ctx, max_steps=max_steps)

    # Persist any extraction the run produced onto the Lead (the AI layer never
    # writes to the DB itself — §17b; the workflow owns that side effect).
    if ctx.last_extraction is not None and run.lead_id is not None:
        await _apply_extraction_to_lead(session, run, ctx)

    run.state = ctx.state
    run.status = status
    await session.flush()
    return run


async def _apply_extraction_to_lead(
    session: AsyncSession, run: WorkflowRun, ctx: WorkflowContext
) -> None:
    from app.models import Lead
    from app.shared.enums import LeadStatus

    extraction = ctx.last_extraction
    lead = await session.get(Lead, run.lead_id)
    if lead is None or extraction is None:
        return
    lead.name = extraction.name or lead.name
    lead.service_requested = extraction.service_requested or lead.service_requested
    lead.location = extraction.location or lead.location
    lead.urgency = extraction.urgency or lead.urgency
    lead.classification = extraction.classification or lead.classification
    if ctx.state.get("qualified"):
        lead.status = LeadStatus.QUALIFIED

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentOrg, DbSession
from app.repositories.repositories import LeadRepository, WorkflowRunRepository
from app.schemas.common import LeadOut, WorkflowRunOut

router = APIRouter(prefix="/organizations/{org_id}", tags=["leads"])


@router.get("/leads", response_model=list[LeadOut])
async def list_leads(org_id: CurrentOrg, db: DbSession) -> list[LeadOut]:
    leads = await LeadRepository(db).list(org_id)
    return [LeadOut.model_validate(lead) for lead in leads]


@router.get("/leads/{lead_id}", response_model=LeadOut)
async def get_lead(org_id: CurrentOrg, lead_id: uuid.UUID, db: DbSession) -> LeadOut:
    lead = await LeadRepository(db).get_or_404(org_id, lead_id)
    return LeadOut.model_validate(lead)


@router.get("/workflow-runs/{run_id}", response_model=WorkflowRunOut)
async def get_workflow_run(
    org_id: CurrentOrg, run_id: uuid.UUID, db: DbSession
) -> WorkflowRunOut:
    run = await WorkflowRunRepository(db).get_or_404(org_id, run_id)
    return WorkflowRunOut.model_validate(run)

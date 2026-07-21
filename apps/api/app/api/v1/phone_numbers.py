from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentOrg, DbSession
from app.repositories.repositories import PhoneNumberRepository
from app.schemas.phone_number import (
    ForwardConnectRequest,
    ForwardingInstructions,
    PhoneNumberOut,
    ProvisionRequest,
)
from app.services.phone_number_service import PhoneNumberService

router = APIRouter(prefix="/organizations/{org_id}/phone-numbers", tags=["phone-numbers"])


@router.post("/forward", response_model=PhoneNumberOut, status_code=201)
async def connect_forwarding(
    org_id: CurrentOrg, req: ForwardConnectRequest, db: DbSession
) -> PhoneNumberOut:
    phone = await PhoneNumberService(db).connect_forwarding(org_id, req.business_number)
    return PhoneNumberOut.model_validate(phone)


@router.post("/provision", response_model=PhoneNumberOut, status_code=201)
async def provision(
    org_id: CurrentOrg, req: ProvisionRequest, db: DbSession
) -> PhoneNumberOut:
    phone = await PhoneNumberService(db).provision_twilio(org_id, req.area_code)
    return PhoneNumberOut.model_validate(phone)


@router.get("", response_model=list[PhoneNumberOut])
async def list_numbers(org_id: CurrentOrg, db: DbSession) -> list[PhoneNumberOut]:
    numbers = await PhoneNumberRepository(db).list(org_id)
    return [PhoneNumberOut.model_validate(n) for n in numbers]


@router.get("/{phone_id}/forwarding-instructions", response_model=ForwardingInstructions)
async def forwarding_instructions(
    org_id: CurrentOrg, phone_id: uuid.UUID, db: DbSession
) -> ForwardingInstructions:
    svc = PhoneNumberService(db)
    phone = await PhoneNumberRepository(db).get_or_404(org_id, phone_id)
    return svc.forwarding_instructions(phone)


@router.post("/{phone_id}/verify-forwarding", response_model=PhoneNumberOut)
async def verify_forwarding(
    org_id: CurrentOrg, phone_id: uuid.UUID, db: DbSession
) -> PhoneNumberOut:
    phone = await PhoneNumberService(db).verify_forwarding(org_id, phone_id)
    return PhoneNumberOut.model_validate(phone)

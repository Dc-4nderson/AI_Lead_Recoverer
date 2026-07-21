from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentOrg, DbSession
from app.models import BusinessSettings
from app.repositories.repositories import BusinessSettingsRepository
from app.schemas.common import BusinessSettingsIn, BusinessSettingsOut
from app.shared.exceptions import NotFoundError

router = APIRouter(prefix="/organizations/{org_id}/business-settings", tags=["business-settings"])


@router.get("", response_model=BusinessSettingsOut)
async def get_settings(org_id: CurrentOrg, db: DbSession) -> BusinessSettings:
    settings = await BusinessSettingsRepository(db).get_for_org(org_id)
    if settings is None:
        raise NotFoundError("Business settings not configured yet")
    return settings


@router.put("", response_model=BusinessSettingsOut)
async def upsert_settings(
    org_id: CurrentOrg, payload: BusinessSettingsIn, db: DbSession
) -> BusinessSettings:
    repo = BusinessSettingsRepository(db)
    settings = await repo.get_for_org(org_id)
    if settings is None:
        settings = BusinessSettings(organization_id=org_id)
        db.add(settings)
    for field, value in payload.model_dump().items():
        setattr(settings, field, value)
    await db.flush()
    return settings

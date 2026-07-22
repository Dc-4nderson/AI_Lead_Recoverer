from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentOrg, CurrentUser, DbSession
from app.models import Membership, Organization
from app.repositories.repositories import MembershipRepository, OrganizationRepository
from app.schemas.common import CreateOrganizationRequest, OrganizationOut
from app.shared.enums import Role
from app.shared.exceptions import NotFoundError

router = APIRouter(tags=["organizations"])


@router.get("/organizations", response_model=list[OrganizationOut])
async def list_my_organizations(user: CurrentUser, db: DbSession) -> list[Organization]:
    """Organizations the current user belongs to. There is no other way for a
    signed-up user to discover their organization_id (the JWT deliberately
    carries only user_id — §4/§5), so this is required for onboarding/tooling."""
    rows = (
        await db.execute(
            select(Organization)
            .join(Membership, Membership.organization_id == Organization.id)
            .where(Membership.user_id == user.id)
            .order_by(Organization.created_at)
        )
    ).scalars().all()
    return list(rows)


@router.post("/organizations", response_model=OrganizationOut, status_code=201)
async def create_organization(
    req: CreateOrganizationRequest, user: CurrentUser, db: DbSession
) -> Organization:
    orgs = OrganizationRepository(db)
    org = await orgs.add(
        Organization(name=req.name, industry=req.industry, timezone=req.timezone)
    )
    await MembershipRepository(db).add(
        Membership(user_id=user.id, organization_id=org.id, role=Role.OWNER)
    )
    return org


@router.get("/organizations/{org_id}", response_model=OrganizationOut)
async def get_organization(org_id: CurrentOrg, db: DbSession) -> Organization:
    org = await OrganizationRepository(db).get(org_id)
    if org is None:
        raise NotFoundError("Organization not found")
    return org

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    business_settings,
    health,
    leads,
    organizations,
    phone_numbers,
)
from app.api.v1.webhooks import twilio

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(business_settings.router)
api_router.include_router(phone_numbers.router)
api_router.include_router(leads.router)
api_router.include_router(twilio.router)

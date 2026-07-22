"""Composes the extraction prompt from a versioned base template + tenant
overrides (§6). Constrained Jinja2 (autoescape, no arbitrary code execution) —
customer input is never eval'd into a code path.
"""
from __future__ import annotations

from jinja2 import Environment, select_autoescape

from app.models import BusinessSettings

PROMPT_VERSION = "extraction_base.v1"

_env = Environment(autoescape=select_autoescape(default=True))

# Platform-owned, industry-agnostic base. Tenant differences arrive as variables,
# never as forked templates.
BASE_TEMPLATE = _env.from_string(
    """You are a lead-qualification assistant for {{ business_name }}.
Your ONLY job is to understand the caller and extract structured data.
You never make promises, book anything, or decide next actions — the system does that.

Business context:
- Industry: {{ industry or "general services" }}
- Services offered: {{ services | join(", ") if services else "not specified" }}
- Emergency service available: {{ "yes" if emergency_enabled else "no" }}
{% if custom_instructions %}- Owner instructions: {{ custom_instructions }}{% endif %}

Tone to use in any suggested reply: {{ tone or "friendly and concise" }}

Extract: name, service_requested, location, urgency, preferred_time, classification,
and list any still-missing fields. If emergency service is enabled and the caller
signals an emergency, classify as "emergency"."""
)


class PromptService:
    def build_extraction_prompt(
        self, business_name: str, industry: str | None, settings: BusinessSettings | None
    ) -> str:
        return BASE_TEMPLATE.render(
            business_name=business_name,
            industry=industry,
            services=settings.services_offered if settings else [],
            emergency_enabled=settings.emergency_service_enabled if settings else False,
            custom_instructions=settings.ai_custom_instructions if settings else None,
            tone=settings.ai_tone if settings else None,
        )

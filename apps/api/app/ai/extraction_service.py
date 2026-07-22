"""AI extraction layer (§17b).

Public surface is a single method: text/context in → schema-valid
LeadExtractionResult out. It never triggers side effects, never writes to the
DB, never decides classification-driven behavior. The workflow engine consumes
the result and owns every decision.

Uses the OpenAI Responses API with a JSON schema response format so the output
*shape* is always valid (a parse failure is a hard error, not silently
swallowed), even though model content is inherently non-deterministic.
"""
from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.ai.prompt_service import PromptService
from app.ai.schemas import LeadExtractionResult
from app.core.config import get_settings
from app.models import BusinessSettings

logger = logging.getLogger("ai.extraction")
settings = get_settings()


class AIExtractionService:
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self._client = client or AsyncOpenAI(api_key=settings.openai_api_key)
        self._prompts = PromptService()

    async def extract(
        self,
        *,
        conversation_history: list[dict[str, str]],
        business_name: str,
        industry: str | None,
        business_settings: BusinessSettings | None,
    ) -> LeadExtractionResult:
        system_prompt = self._prompts.build_extraction_prompt(
            business_name, industry, business_settings
        )
        transcript = "\n".join(
            f"{m['direction']}: {m['body']}" for m in conversation_history
        )
        model_input = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Conversation so far:\n{transcript}"},
        ]

        response = await self._client.responses.parse(
            model=settings.openai_model,
            input=model_input,
            text_format=LeadExtractionResult,
        )
        result = response.output_parsed
        if result is None:  # pragma: no cover - SDK guarantees shape or raises
            raise RuntimeError("AI extraction returned no parsed output")

        self._trace_call(system_prompt, model_input, response, result, business_name, industry)
        return result

    def _trace_call(self, system_prompt, model_input, response, result, business_name, industry):
        """Expose the extraction I/O to an active simulation (no-op in prod)."""
        from app.ai.prompt_service import PROMPT_VERSION
        from app.ai.schemas import SCHEMA_VERSION
        from app.simulator.session import get_current_simulation

        sim = get_current_simulation()
        if sim is None:
            return
        sim.trace.record_ai_call(
            model=settings.openai_model,
            prompt=system_prompt,
            input=model_input,
            organization_context={"business_name": business_name, "industry": industry},
            raw_response=getattr(response, "raw", None),
            validated_model=result.model_dump(mode="json"),
            missing_fields=result.missing_fields,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
        )

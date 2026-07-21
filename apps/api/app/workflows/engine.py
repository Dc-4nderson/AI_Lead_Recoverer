"""Workflow engine (§17).

Deterministic step runner. Given a definition and a context, it advances
through steps from the persisted ``state['step_index']`` until a step PAUSEs
(waiting on a reply) or COMPLETEs. It is pure orchestration — it calls no
integration client directly, only steps, which act through injected
collaborators. This is what makes it unit-testable with zero OpenAI/Twilio.
"""
from __future__ import annotations

import logging

from app.shared.enums import WorkflowStatus
from app.workflows.context import WorkflowContext
from app.workflows.definitions.missed_call_recovery import WorkflowDefinition
from app.workflows.steps import AwaitReply, Outcome

logger = logging.getLogger("workflows.engine")


class WorkflowEngine:
    def __init__(self, definition: WorkflowDefinition) -> None:
        self.definition = definition
        # Record where the AwaitReply step lives so QualifyAndRoute can loop back.
        self._await_index = next(
            (i for i, s in enumerate(definition.steps) if isinstance(s, AwaitReply)),
            None,
        )

    async def advance(self, ctx: WorkflowContext) -> WorkflowStatus:
        """Run steps until PAUSE or COMPLETE. Returns the resulting status.

        The caller is responsible for persisting ctx.state and the returned
        status to the WorkflowRun row (keeps the engine free of DB concerns).
        """
        if self._await_index is not None:
            ctx.state.setdefault("await_step_index", self._await_index)
        index = ctx.state.get("step_index", 0)

        while index < len(self.definition.steps):
            step = self.definition.steps[index]
            ctx.state["step_index"] = index
            outcome = await step.run(ctx)
            logger.info(
                "workflow step executed",
                extra={
                    "workflow": self.definition.name,
                    "step": type(step).__name__,
                    "outcome": outcome.name,
                    "workflow_run_id": str(ctx.workflow_run_id),
                },
            )

            if outcome is Outcome.PAUSE:
                # A step may have redirected step_index (e.g. loop back to AwaitReply).
                return WorkflowStatus.WAITING_ON_REPLY
            if outcome is Outcome.COMPLETE:
                ctx.state["step_index"] = len(self.definition.steps)
                return WorkflowStatus.COMPLETED

            index = ctx.state.get("step_index", index) + 1

        return WorkflowStatus.COMPLETED

    def resume(self, ctx: WorkflowContext) -> None:
        """Mark a paused run as ready to continue past its AwaitReply step."""
        ctx.state["resumed"] = True

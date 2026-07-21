"""Workflow definitions. A definition is configuration (a named, ordered list
of steps), not code branches per customer (§6, §17). New industries/flows are
new definitions selected per organization — the engine itself never changes.
"""
from app.workflows.definitions.missed_call_recovery import MISSED_CALL_RECOVERY

REGISTRY = {MISSED_CALL_RECOVERY.name: MISSED_CALL_RECOVERY}

__all__ = ["MISSED_CALL_RECOVERY", "REGISTRY"]

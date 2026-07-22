"""Workflow Simulator — a thin observability + orchestration layer.

The simulator runs the EXACT production components (event bus, workflow engine,
AI extraction service, queue task functions, repositories, database). It only
swaps *transport*: synthetic events instead of Twilio inbound, inline execution
instead of a Redis round-trip, and (by default) a deterministic OpenAI-compatible
client instead of live OpenAI. No business logic is duplicated here.
"""

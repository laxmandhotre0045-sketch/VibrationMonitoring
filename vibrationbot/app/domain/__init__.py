"""Vibration-analysis domain logic.

Deterministic math only — no LangChain, no OpenAI, no I/O beyond reading the
bundled reference tables in ``data/``. Everything here is unit-testable against
published known answers, which is the point: an LLM must never be the thing
that computes a fault frequency or decides an ISO severity zone.

The LangGraph tool wrappers live in ``app/graph/tools_domain.py``.
"""

"""Single place that knows how to build a chat model.

Two reasons this exists rather than instantiating ChatOpenAI inline:

1. Provider swapping. ``LLM_PROVIDER=anthropic`` changes one function, not
   every node.
2. Testing. Every graph node calls ``get_chat_model``, so monkeypatching this
   one function keeps the whole test suite off the network. That is the seam
   ``tests/conftest.py`` uses.

``purpose`` lets cheap, high-volume calls (classification, relevance grading)
run with tighter token budgets than the answer-generating call, without
scattering magic numbers through the nodes.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from app.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    VISION_MODEL,
)

logger = logging.getLogger(__name__)

Purpose = Literal["classify", "grade", "verify", "agent", "generate", "vision", "chart"]

# max_tokens per purpose. Classification and grading emit small structured
# objects; letting them share the 1024-token answer budget just wastes money on
# a ceiling they never approach.
#
# "grade" (excerpt relevance) and "verify" (answer groundedness) are separate
# even though both are cheap structured checks: they are different jobs, they
# may want different models later, and keeping them distinct is what lets tests
# script one without accidentally answering the other.
_PURPOSE_SETTINGS: dict[str, dict[str, Any]] = {
    "classify": {"temperature": 0.0, "max_tokens": 400},
    "grade": {"temperature": 0.0, "max_tokens": 600},
    "verify": {"temperature": 0.0, "max_tokens": 600},
    "agent": {"temperature": DEFAULT_TEMPERATURE, "max_tokens": DEFAULT_MAX_TOKENS},
    "generate": {"temperature": DEFAULT_TEMPERATURE, "max_tokens": DEFAULT_MAX_TOKENS},
    "vision": {"temperature": DEFAULT_TEMPERATURE, "max_tokens": DEFAULT_MAX_TOKENS},
    "chart": {"temperature": 0.0, "max_tokens": 1200},
}


def _settings(purpose: str) -> dict[str, Any]:
    return dict(_PURPOSE_SETTINGS.get(purpose, _PURPOSE_SETTINGS["agent"]))


def get_chat_model(purpose: Purpose = "agent", **overrides: Any):
    """Build the chat model for a given purpose.

    ``max_retries=0`` is deliberate and must not be relaxed. ChatOpenAI
    defaults to 2, but app/services/openai_utils.py sets 0 on purpose so that a
    quota or auth failure surfaces immediately and the retrieval-only fallback
    can fire. With retries on, every such failure would stall roughly 30
    seconds before degrading.
    """
    settings = _settings(purpose)
    settings.update(overrides)

    if LLM_PROVIDER == "anthropic":
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set."
            )
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "LLM_PROVIDER=anthropic requires langchain-anthropic. "
                "Install with: pip install langchain-anthropic==1.4.0"
            ) from exc
        return ChatAnthropic(
            model=ANTHROPIC_MODEL,
            api_key=ANTHROPIC_API_KEY,
            max_retries=0,
            **settings,
        )

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set")

    from langchain_openai import ChatOpenAI

    model = VISION_MODEL if purpose in ("vision", "chart") else OPENAI_MODEL
    return ChatOpenAI(
        model=model,
        api_key=OPENAI_API_KEY,
        max_retries=0,
        **settings,
    )


def provider_name() -> str:
    return "anthropic" if LLM_PROVIDER == "anthropic" else "openai"

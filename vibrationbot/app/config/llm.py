"""Chat/vision model selection, API keys, and the provider switch."""

import os as _os

OPENAI_MODEL = _os.getenv("OPENAI_MODEL", "gpt-4o-mini")
VISION_MODEL = _os.getenv("VISION_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = _os.getenv("OPENAI_API_KEY", "")

# Chat model behind mode=graph only. The legacy agent/simple modes always use
# the raw OpenAI client in app/llm/openai_utils.py.
LLM_PROVIDER = _os.getenv("LLM_PROVIDER", "openai").lower()
ANTHROPIC_API_KEY = _os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = _os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

# When OpenAI is unavailable (quota/auth), return retrieved excerpts instead of 503.
ENABLE_RETRIEVAL_FALLBACK = _os.getenv("ENABLE_RETRIEVAL_FALLBACK", "true").lower() in (
    "1",
    "true",
    "yes",
)

DEFAULT_TEMPERATURE = float(_os.getenv("DEFAULT_TEMPERATURE", "0.1"))
DEFAULT_MAX_TOKENS = int(_os.getenv("DEFAULT_MAX_TOKENS", "1024"))

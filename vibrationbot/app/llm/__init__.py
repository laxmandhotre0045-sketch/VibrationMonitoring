"""LLM client construction.

Two independent stacks, deliberately:

    provider.py       LangChain chat models (mode=graph), OpenAI or Anthropic
    openai_utils.py   the raw OpenAI SDK client used by the legacy agent/simple
                      modes, plus error classification and the retrieval-only
                      fallback answer

``provider.get_chat_model`` is the single seam the test suite injects a fake
model through, which is much of why the factory exists.
"""

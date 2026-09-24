"""Knowledge-base agent — cited answers from the indexed vibration library.

Not a service and not a UI. Import it, call it, get a fixed envelope back:

    from kb_agent import KnowledgeBaseAgent

    agent = KnowledgeBaseAgent()
    result = agent.ask("what causes oil whirl in journal bearings?")
    if result.ok:
        print(result.meta["answer"])        # cited prose
        for p in result.data:               # every passage the model saw
            print(p["citation"], p["text"][:200])
    else:
        handle(result.error)                # failures are values, not exceptions

``search`` and ``documents`` call no model at all, so they work without an API
key and are the right way to check whether a topic is in the corpus.

Unlike ``sql_agent``, this package does import the chatbot's retrieval stack
(``app.retrieval``) — the knowledge base *is* that stack, and a second search
implementation would give two agents two different answers from one corpus.
"""

from kb_agent.agent import (  # noqa: F401
    AgentResult,
    KnowledgeBaseAgent,
    kb_agent,
)
from kb_agent.config import (  # noqa: F401
    CAVEATS,
    KB_MAX_ITERATIONS,
    KB_TOP_K,
)
from kb_agent.library import (  # noqa: F401
    CHUNK_TYPES,
    PassageStore,
    cite,
    format_excerpts,
    list_documents,
    passage,
    resolve_documents,
    search,
)
from kb_agent.tools import build_tools  # noqa: F401

__all__ = [
    "AgentResult",
    "KnowledgeBaseAgent",
    "kb_agent",
    "CAVEATS",
    "CHUNK_TYPES",
    "KB_MAX_ITERATIONS",
    "KB_TOP_K",
    "PassageStore",
    "build_tools",
    "cite",
    "format_excerpts",
    "list_documents",
    "passage",
    "resolve_documents",
    "search",
]

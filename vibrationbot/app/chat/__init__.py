"""The three chat modes, and the LangGraph analyst behind the default one.

    graph/                LangGraph orchestration (mode=graph, the default)
    graph_rag_service.py  adapter: HTTP request -> graph state -> ChatResponse
    agent_rag_service.py  legacy hand-rolled OpenAI tool loop (mode=agent)
    rag_service.py        single-shot retrieve-and-answer (mode=simple)
    sessions.py           in-memory, LRU-bounded chat history

All three modes are live and reachable from routes_chat.MODES. Nothing outside
api/ imports this package, and it depends downward only on retrieval, llm,
domain, schemas and config - never on ingestion, so serving a chat request
never loads Docling or PyMuPDF.
"""

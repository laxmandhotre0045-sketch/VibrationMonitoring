"""LangGraph orchestration for the vibration analysis assistant (mode=graph).

Layered so the expensive parts stay testable:

    state.py            GraphState + reducers
    prompts.py          every prompt string, in one place
    tools_retrieval.py  the existing retrieval service, exposed as tools
    tools_domain.py     app/domain wrapped as tools with Pydantic arg schemas
    nodes.py            node functions (all sync def — see build.py)
    build.py            StateGraph wiring, checkpointer, compiled singletons

Nothing here reimplements retrieval. ``retrieve_across_documents`` and
``index_service`` are used exactly as the legacy agent mode uses them, so both
modes retrieve identically and only the orchestration differs.
"""

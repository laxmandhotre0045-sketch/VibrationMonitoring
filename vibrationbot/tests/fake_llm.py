"""A scriptable fake chat model for graph tests.

Every graph node obtains its model through ``llm.provider.get_chat_model``, so
monkeypatching that one function is enough to keep the whole suite offline.
That single seam is a large part of why the provider factory exists.

The fake supports the three shapes the nodes actually use:
``.invoke(...)``, ``.with_structured_output(Schema).invoke(...)``, and
``.bind_tools(tools).invoke(...)``.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage


class FakeChatModel:
    """Returns scripted responses and records how it was called.

    Responses are supplied per purpose. A list is consumed one entry per call,
    with the last entry repeating once exhausted — which is what lets a test say
    "the grader always rejects everything" without knowing the loop count in
    advance.
    """

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[dict[str, Any]] = []
        self._counts: dict[str, int] = {}
        self.purpose = "agent"
        self._schema = None
        self._tools: list[Any] = []

    # -- configuration -----------------------------------------------------

    def for_purpose(self, purpose: str) -> "FakeChatModel":
        clone = FakeChatModel(self.responses)
        clone.calls = self.calls
        clone._counts = self._counts
        clone.purpose = purpose
        return clone

    def with_structured_output(self, schema, **_kwargs) -> "FakeChatModel":
        clone = self.for_purpose(self.purpose)
        clone._schema = schema
        return clone

    def bind_tools(self, tools, **_kwargs) -> "FakeChatModel":
        clone = self.for_purpose(self.purpose)
        clone._schema = self._schema
        clone._tools = list(tools)
        return clone

    # -- invocation --------------------------------------------------------

    def count(self, purpose: str) -> int:
        return self._counts.get(purpose, 0)

    def invoke(self, messages, **_kwargs):
        self._counts[self.purpose] = self._counts.get(self.purpose, 0) + 1
        self.calls.append({"purpose": self.purpose, "messages": messages, "schema": self._schema})

        scripted = self.responses.get(self.purpose)
        if isinstance(scripted, list):
            index = min(self._counts[self.purpose] - 1, len(scripted) - 1)
            scripted = scripted[index] if scripted else None
        if callable(scripted):
            scripted = scripted(messages)

        if scripted is None:
            return AIMessage(content=f"(fake {self.purpose} response)")
        if isinstance(scripted, str):
            return AIMessage(content=scripted)
        return scripted


def make_get_chat_model(fake: FakeChatModel):
    """Build a ``get_chat_model`` replacement bound to this fake."""

    def _get_chat_model(purpose: str = "agent", **_kwargs):
        return fake.for_purpose(purpose)

    return _get_chat_model


def tool_call_message(name: str, args: dict[str, Any], call_id: str = "call_1") -> AIMessage:
    """An AIMessage that requests one tool call."""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )

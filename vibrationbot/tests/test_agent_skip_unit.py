"""Tests for the agent's final-call skip optimization (Phase 2.4)."""

import types

import pytest

from app.chat import agent_rag_service as ars


class _Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self):
        return {"role": "assistant", "content": self.content}


class _Resp:
    def __init__(self, msg):
        self.choices = [types.SimpleNamespace(message=msg)]


class FakeCompletions:
    """Returns queued messages; records how many calls were made."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self._script:
            return _Resp(self._script.pop(0))
        return _Resp(_Msg(content="fallback"))


class FakeClient:
    def __init__(self, script):
        self.completions = FakeCompletions(script)
        self.chat = types.SimpleNamespace(completions=self.completions)


@pytest.fixture
def wired(monkeypatch):
    """Stub every external dependency of agent_answer except the logic we test."""
    monkeypatch.setattr(ars, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ars, "AGENT_SKIP_FINAL_CALL", True)

    monkeypatch.setattr(ars.session_service, "get_or_create", lambda s: "sess")
    monkeypatch.setattr(ars.session_service, "get_last_question", lambda s: None)
    monkeypatch.setattr(ars.session_service, "get_history", lambda s: [])
    monkeypatch.setattr(ars.session_service, "add_turn", lambda *a, **k: None)
    monkeypatch.setattr(ars, "_log_interaction", lambda payload: None)

    monkeypatch.setattr(ars.index_service, "list_ready_doc_ids", lambda: ["d"])
    monkeypatch.setattr(ars.index_service, "load_index", lambda d: object())

    # Deterministic retrieval; type controls the image branch.
    state = {"chunk_type": "clause"}

    def fake_retrieve(indexes, query, top_k=6, allowed_docs=None, chunk_types=None):
        return [
            {
                "chunk_id": "chunk_000001",
                "doc_id": "d",
                "text": "vibration limit is 4.5 mm/s",
                "section_path": "S",
                "page_start": 1,
                "page_end": 1,
                "score": 0.9,
                "chunk_type": state["chunk_type"],
                "asset_path": "assets/f.png" if state["chunk_type"] == "image" else "",
            }
        ]

    monkeypatch.setattr(ars, "retrieve_across_documents", fake_retrieve)
    return state


def _run(monkeypatch, client):
    monkeypatch.setattr(ars, "make_openai_client", lambda: client)
    return ars.agent_answer("what is the vibration limit?", session_id="sess")


def test_skips_final_call_for_text_only_answer(wired, monkeypatch):
    # Loop: turn 1 requests a tool, turn 2 returns final text (no tool_calls).
    tool_call = types.SimpleNamespace(
        id="t1",
        function=types.SimpleNamespace(name="semantic_search", arguments='{"query":"limit"}'),
    )
    client = FakeClient([_Msg(tool_calls=[tool_call]), _Msg(content="The limit is 4.5 mm/s.\n- from p.1")])
    resp = _run(monkeypatch, client)

    assert "4.5 mm/s" in resp.answer
    # 2 loop calls only — the separate final-answer call was skipped.
    assert client.completions.calls == 2


def test_keeps_final_call_when_images_present(wired, monkeypatch):
    wired["chunk_type"] = "image"
    tool_call = types.SimpleNamespace(
        id="t1",
        function=types.SimpleNamespace(name="semantic_search", arguments='{"query":"chart"}'),
    )
    # 3rd scripted msg is the dedicated vision/final answer.
    client = FakeClient(
        [
            _Msg(tool_calls=[tool_call]),
            _Msg(content="ignored agent text"),
            _Msg(content="Final answer from the figure."),
        ]
    )
    # Avoid touching the filesystem for the image.
    monkeypatch.setattr(ars, "_image_to_base64", lambda d, a: None)
    resp = _run(monkeypatch, client)

    assert "figure" in resp.answer.lower()
    # 2 loop calls + 1 dedicated final call.
    assert client.completions.calls == 3


def test_keeps_final_call_when_agent_never_wrote_text(wired, monkeypatch):
    # Every loop turn keeps calling tools; no final text is ever produced.
    tc = types.SimpleNamespace(
        id="t",
        function=types.SimpleNamespace(name="semantic_search", arguments="{}"),
    )
    # Exactly AGENT_MAX_ITERATIONS tool-only turns, then the loop exits on the
    # cap; the next scripted message answers the dedicated final call.
    script = [_Msg(tool_calls=[tc]) for _ in range(ars.AGENT_MAX_ITERATIONS)]
    script.append(_Msg(content="synth"))
    client = FakeClient(script)
    resp = _run(monkeypatch, client)
    assert resp.answer == "synth"
    assert client.completions.calls == ars.AGENT_MAX_ITERATIONS + 1


def test_flag_off_always_makes_final_call(wired, monkeypatch):
    monkeypatch.setattr(ars, "AGENT_SKIP_FINAL_CALL", False)
    tool_call = types.SimpleNamespace(
        id="t1",
        function=types.SimpleNamespace(name="semantic_search", arguments="{}"),
    )
    client = FakeClient(
        [_Msg(tool_calls=[tool_call]), _Msg(content="agent text"), _Msg(content="dedicated final")]
    )
    resp = _run(monkeypatch, client)
    assert "dedicated final" in resp.answer
    assert client.completions.calls == 3

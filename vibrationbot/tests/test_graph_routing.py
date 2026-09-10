"""Routing and loop-bound tests.

The point of these is termination. A self-correcting graph that can retry
retrieval and regenerate answers has two cycles in it, and both must be
provably bounded — an unbounded one burns the user's quota and eventually
raises GraphRecursionError instead of answering.
"""

from __future__ import annotations

import pytest

from app.chat.graph import nodes
from app.chat.graph.build import RECURSION_LIMIT, build_graph
from app.chat.graph.state import GraphState, new_state
from app.chat.graph.tools_domain import DomainContext
from app.chat.graph.tools_retrieval import RetrievalContext
from app.config import AGENT_MAX_ITERATIONS, GRAPH_MAX_REGENS, GRAPH_MAX_REWRITES
from tests.fake_llm import FakeChatModel, make_get_chat_model, tool_call_message

SESSION = "routing-session"


def state(**overrides) -> GraphState:
    base = new_state(question="q", session_id=SESSION, top_k=6)
    base.update(overrides)
    return base


class TestClassifyRouting:
    @pytest.mark.parametrize(
        "route,expected",
        [
            ("chitchat", "generate"),
            ("theory", "retrieve"),
            ("numeric", "resolve_machine_context"),
            ("data", "resolve_machine_context"),
            ("hybrid", "resolve_machine_context"),
        ],
    )
    def test_route_targets(self, route, expected):
        assert nodes.route_after_classify(state(route=route)) == expected

    def test_missing_route_falls_back_to_hybrid_path(self):
        assert nodes.route_after_classify(state()) == "resolve_machine_context"


class TestRewriteLoop:
    def test_weak_retrieval_triggers_one_rewrite(self):
        weak = state(retrieved=[{"x": 1}] * 6, graded=[], rewrite_count=0)
        assert nodes.route_after_grade(weak) == "rewrite"

    def test_rewrite_is_bounded(self):
        """A second weak retrieval proceeds rather than looping forever."""
        weak = state(retrieved=[{"x": 1}] * 6, graded=[], rewrite_count=GRAPH_MAX_REWRITES)
        assert nodes.route_after_grade(weak) == "agent"

    def test_enough_relevant_excerpts_skips_the_rewrite(self):
        good = state(retrieved=[{"x": 1}] * 6, graded=[{"x": 1}] * 4, rewrite_count=0)
        assert nodes.route_after_grade(good) == "agent"

    def test_empty_retrieval_still_bounded(self):
        """No documents indexed at all must not spin the rewrite loop."""
        assert nodes.route_after_grade(state(retrieved=[], graded=[], rewrite_count=GRAPH_MAX_REWRITES)) == "agent"


class TestToolLoop:
    def test_tool_calls_are_executed(self):
        s = state(messages=[tool_call_message("bearing_fault_frequencies", {})], tool_loops=0)
        assert nodes.route_after_agent(s) == "execute_tools"

    def test_no_tool_calls_moves_on(self):
        from langchain_core.messages import AIMessage

        s = state(messages=[AIMessage(content="done")])
        assert nodes.route_after_agent(s) == "ground_computations"

    def test_tool_loop_is_bounded(self):
        s = state(
            messages=[tool_call_message("bearing_fault_frequencies", {})],
            tool_loops=AGENT_MAX_ITERATIONS,
        )
        assert nodes.route_after_agent(s) == "ground_computations"
        assert nodes.route_after_tools(s) == "ground_computations"

    def test_agent_error_degrades_to_generation(self):
        """An API failure must still produce an answer from what was retrieved."""
        assert nodes.route_after_agent(state(error="quota exceeded")) == "generate"


class TestVisionRouting:
    def test_figures_trigger_the_vision_pass(self):
        s = state(graded=[{"chunk_type": "image", "doc_id": "d", "asset_path": "a.png"}])
        assert nodes.route_after_generate(s) == "vision_answer"

    def test_plots_trigger_the_vision_pass(self):
        assert nodes.route_after_generate(state(plots=[{"path": "x.png"}])) == "vision_answer"

    def test_text_only_skips_it(self):
        s = state(graded=[{"chunk_type": "clause"}])
        assert nodes.route_after_generate(s) == "check_groundedness"


class TestGroundednessLoop:
    def test_ungrounded_answer_regenerates(self):
        assert nodes.route_after_groundedness(state(grounded=False, regen_count=1)) == "generate"

    def test_regeneration_is_bounded(self):
        s = state(grounded=False, regen_count=GRAPH_MAX_REGENS + 1)
        assert nodes.route_after_groundedness(s) == "finalize"

    def test_grounded_answer_finalizes(self):
        assert nodes.route_after_groundedness(state(grounded=True)) == "finalize"


class TestCompiledGraph:
    """End-to-end through the compiled graph, still fully offline."""

    @pytest.fixture
    def harness(self, monkeypatch, tmp_path):
        retrieval = RetrievalContext(allowed_docs=[], top_k=6)
        domain = DomainContext()
        nodes.set_turn_contexts(SESSION, retrieval, domain)

        fake = FakeChatModel()
        monkeypatch.setattr(nodes, "get_chat_model", make_get_chat_model(fake))
        monkeypatch.setattr(nodes.index_service, "list_ready_doc_ids", lambda: [])

        from langgraph.checkpoint.memory import MemorySaver

        graph = build_graph().compile(checkpointer=MemorySaver())
        yield graph, fake
        nodes.clear_turn_contexts(SESSION)

    def _config(self):
        return {"configurable": {"thread_id": SESSION}, "recursion_limit": RECURSION_LIMIT}

    def test_chitchat_never_retrieves(self, harness, monkeypatch):
        """"hi" must not cost an embedding pass and a ~900 ms rerank."""
        graph, fake = harness
        calls = []
        monkeypatch.setattr(
            "app.chat.graph.tools_retrieval.retrieve_across_documents",
            lambda *a, **k: calls.append(1) or [],
        )
        fake.responses["classify"] = nodes.RouteDecision(route="chitchat", rewritten_query="hi")
        fake.responses["generate"] = "Hello — ask me about bearing frequencies."

        result = graph.invoke(new_state("hi", SESSION, 6), self._config())

        assert calls == []
        assert "Hello" in result["answer"]

    def test_relentlessly_negative_grader_still_terminates(self, harness):
        """The rewrite loop must converge even when nothing is ever relevant."""
        graph, fake = harness
        fake.responses["classify"] = nodes.RouteDecision(route="theory", rewritten_query="q")
        fake.responses["grade"] = nodes.GradeResult(grades=[])
        fake.responses["verify"] = nodes.GroundednessResult(grounded=True)
        fake.responses["agent"] = "no tools needed"
        fake.responses["generate"] = "an answer"

        result = graph.invoke(new_state("q", SESSION, 6), self._config())

        assert result["rewrite_count"] <= GRAPH_MAX_REWRITES
        assert result["answer"] == "an answer"

    def test_permanently_ungrounded_answer_still_terminates(self, harness):
        graph, fake = harness
        fake.responses["classify"] = nodes.RouteDecision(route="numeric", rewritten_query="q")
        fake.responses["verify"] = nodes.GroundednessResult(grounded=False, unsupported_claims=["x"])
        fake.responses["agent"] = "no tools"
        fake.responses["generate"] = "draft"

        result = graph.invoke(new_state("q", SESSION, 6), self._config())

        assert result["regen_count"] <= GRAPH_MAX_REGENS + 1
        assert result["answer"] == "draft"

    def test_tool_loop_terminates_when_the_agent_never_stops_calling(self, harness):
        """A model stuck in a tool-call loop must be cut off, not run to the limit."""
        graph, fake = harness
        fake.responses["classify"] = nodes.RouteDecision(route="numeric", rewritten_query="q")
        fake.responses["verify"] = nodes.GroundednessResult(grounded=True)
        fake.responses["agent"] = tool_call_message(
            "bearing_fault_frequencies", {"designation": "6205", "shaft_rpm": 1750}
        )
        fake.responses["generate"] = "answer"

        result = graph.invoke(new_state("q", SESSION, 6), self._config())

        assert result["tool_loops"] <= AGENT_MAX_ITERATIONS
        assert result["answer"] == "answer"
        assert len(result["computations"]) >= 1

    def test_a_real_computation_flows_into_the_answer_prompt(self, harness):
        """The full path: tool -> artifact -> <COMPUTED> block."""
        graph, fake = harness
        fake.responses["classify"] = nodes.RouteDecision(
            route="numeric", rewritten_query="bpfo 6205", bearing_designation="6205", shaft_rpm=1750
        )
        fake.responses["verify"] = nodes.GroundednessResult(grounded=True)
        fake.responses["agent"] = [
            tool_call_message("bearing_fault_frequencies", {"designation": "6205", "shaft_rpm": 1750}),
            "done",
        ]
        fake.responses["generate"] = "BPFO is 104.56 Hz (3.585x)."

        result = graph.invoke(new_state("BPFO for a 6205 at 1750 rpm?", SESSION, 6), self._config())

        assert result["computations"][0]["outputs"]["BPFO_hz"] == pytest.approx(104.56, abs=0.05)
        generate_prompt = next(
            c["messages"][-1].content for c in reversed(fake.calls) if c["purpose"] == "generate"
        )
        assert "104.56" in generate_prompt
        assert "<COMPUTED>" in generate_prompt
